#include "LiveWorld.hpp"
#include <apps/openmw/mwbase/environment.hpp>
#include <apps/openmw/mwclass/classes.hpp>
#include <apps/openmw/mwworld/class.hpp>
#include <components/esm3/objectstate.hpp>
#include <components/settings/parser.hpp>
#include <components/settings/settings.hpp>
#include <components/settings/values.hpp>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <mutex>
#include <stdexcept>

namespace G6 {
namespace {
std::mutex engineDispatch;
std::once_flag initialize;
std::atomic<std::uint64_t> nextEpoch{1};
struct Binding {
    MWBase::Environment environment;
    Binding(MWWorld::ESMStore& store, MWWorld::WorldModel& model) {
        environment.setESMStore(store);
        environment.setWorldModel(model);
    }
};
void finite(const ESM::Position& position) {
    for (unsigned i = 0; i < 3; ++i)
        if (!std::isfinite(position.pos[i]) || !std::isfinite(position.rot[i]))
            throw std::runtime_error("G6 nonfinite live position");
}
std::size_t scan(const ESM::Cell& cell, ESM::ReadersCache& readers, std::size_t limit) {
    // Bound genuine decoding before CellStore allocates typed live objects.
    // This does not merge references; override/deletion/move semantics belong
    // exclusively to Store<Cell> and CellStore.
    std::size_t count = cell.mLeasedRefs.size();
    if (count > limit) throw std::runtime_error("G6 reference budget exceeded");
    for (std::size_t i = 0; i < cell.mContextList.size(); ++i) {
        auto item = readers.get(static_cast<std::size_t>(cell.mContextList[i].index));
        cell.restore(*item, i);
        ESM::CellRef ref; ESM::MovedCellRef movedRef; bool deleted = false, moved = false;
        while (ESM::Cell::getNextRef(*item, ref, deleted, movedRef, moved,
                ESM::Cell::GetNextRefMode::LoadOnlyNotMoved)) {
            if (++count > limit) throw std::runtime_error("G6 reference budget exceeded");
        }
    }
    return count;
}
}
LiveWorld::LiveWorld(const std::vector<std::filesystem::path>& content,
    const std::filesystem::path& defaults, Limits value)
    : EngineIndex(content), limits(value) {
    std::lock_guard lock(engineDispatch);
    if (!limits.cells || !limits.rawReferencesPerCell || !limits.rawReferencesTotal)
        throw std::runtime_error("G6 zero live-world budget");
    std::call_once(initialize, [&] {
        Settings::SettingsFileParser parser;
        auto file = defaults;
#ifdef G6_DEFAULT_SETTINGS
        if (file.empty()) file = G6_DEFAULT_SETTINGS;
#endif
        if (file.empty()) throw std::runtime_error("G6 upstream settings resource path required");
        parser.loadSettingsFile(file, Settings::Manager::mDefaultSettings);
        Settings::StaticValues::initDefaults();
        Settings::StaticValues::init();
        MWClass::registerClasses();
    });
    model = std::make_unique<MWWorld::WorldModel>(mutableStore(), readerCache());
    epoch = nextEpoch.fetch_add(1);
}
LiveWorld::~LiveWorld() {
    std::lock_guard lock(engineDispatch);
    Binding binding(mutableStore(), *model);
    model.reset(); // Live refs deregister before their registry/store disappears.
}
MWWorld::CellStore& LiveWorld::load(const ESM::Cell& cell) {
    if (auto it = rejected.find(cell.mId); it != rejected.end())
        throw std::runtime_error("G6 quarantined CELL: " + it->second);
    if (prepared.contains(cell.mId)) return model->getCell(cell.mId);
    if (prepared.size() + rejected.size() >= limits.cells)
        throw std::runtime_error("G6 live CELL budget exhausted; state retained");
    const auto start = std::chrono::steady_clock::now();
    try {
        // Resolve from our actual content store, not a caller-owned CELL.
        const auto* original = cells.search(cell.mId);
        if (!original) throw std::runtime_error("G6 CELL absent from content stack");
        const auto remaining = limits.rawReferencesTotal - statistics.rawReferences;
        const auto count = scan(*original, readerCache(), std::min(limits.rawReferencesPerCell, remaining));
        // Charge the reservation even if genuine loading subsequently fails.
        // Quarantined partial cells remain bounded and are never published.
        statistics.rawReferences += count;
        auto& loaded = model->getCell(original->mId, false);
        loaded.load();
        if (loaded.getState() != MWWorld::CellStore::State_Loaded)
            throw std::runtime_error("G6 genuine CellStore did not finish loading");
        loaded.forEachConst([&](const MWWorld::ConstPtr& ptr) {
            const auto existing = model->getPtr(ptr.getCellRef().getRefNum());
            if (!existing.isEmpty() && existing != ptr)
                throw std::runtime_error("G6 duplicate live content reference identity");
            // The owner is mutable and exclusively locked. Const traversal
            // avoids spuriously setting CellStore's saved-state flag.
            model->registerPtr(MWWorld::Ptr(const_cast<MWWorld::LiveCellRefBase*>(ptr.getBase()), &loaded));
            return true;
        }, true);
        prepared.emplace(original->mId, count);
        ++statistics.successfulLoads;
        statistics.lastPreparationMs = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - start).count();
        statistics.maximumPreparationMs = std::max(statistics.maximumPreparationMs, statistics.lastPreparationMs);
        return loaded;
    } catch (const std::exception& e) {
        ++statistics.failedLoads;
        rejected.emplace(cell.mId, e.what());
        throw std::runtime_error("G6 stage=CellStore.load CELL=" + cell.mId.toDebugString() + ": " + e.what());
    }
}
Object LiveWorld::snapshot(const MWWorld::ConstPtr& ptr) const {
    ESM::ObjectState state;
    ptr.getCellRef().writeState(state);
    state.mRef.mPos = ptr.getRefData().getPosition();
    return {{ptr.getCellRef().getRefNum(), epoch}, std::move(state.mRef), ptr.getType(),
        ptr.getRefData().isEnabled(), ptr.getClass().isActor(), ptr.getRefData().hasCustomData()};
}
MWWorld::Ptr LiveWorld::resolve(Handle handle) {
    if (handle.epoch != epoch) throw std::runtime_error("G6 foreign or retired object handle");
    auto ptr = model->getPtr(handle.reference);
    if (ptr.isEmpty()) throw std::runtime_error("G6 object no longer registered");
    if (rejected.contains(ptr.getCell()->getCell()->getId()))
        throw std::runtime_error("G6 object belongs to quarantined CELL");
    return ptr;
}
std::vector<Object> LiveWorld::objects(const ESM::Cell& cell, bool includeDeleted) {
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    auto& loaded = load(cell); std::vector<Object> result;
    loaded.forEachConst([&](const MWWorld::ConstPtr& ptr) { result.push_back(snapshot(ptr)); return true; }, includeDeleted);
    return result;
}
std::vector<ESM::CellRef> LiveWorld::references(const ESM::Cell& cell) {
    auto values = objects(cell); std::vector<ESM::CellRef> result; result.reserve(values.size());
    for (auto& value : values) if (value.enabled) result.push_back(std::move(value.reference));
    return result;
}
Object LiveWorld::inspect(Handle handle) {
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    return snapshot(resolve(handle));
}
void LiveWorld::setPosition(Handle handle, const ESM::Position& position) {
    finite(position); std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    resolve(handle).getRefData().setPosition(position);
}
void LiveWorld::setEnabled(Handle handle, bool enabled) {
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    auto& data = resolve(handle).getRefData(); if (enabled) data.enable(); else data.disable();
}
void LiveWorld::setCount(Handle handle, int count) {
    if (count < 0) throw std::runtime_error("G6 negative live count");
    // The genuine CellRef::setCount(0) calls World::removeRefScript after
    // changing the reference. G6 has no real World service yet. Reject BEFORE
    // mutation; never replace that gameplay side effect with an empty service.
    if (count == 0) throw std::runtime_error("G6 runtime deletion requires genuine MWWorld::World script lifecycle");
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    resolve(handle).getCellRef().setCount(count);
}
void LiveWorld::move(Handle handle, const ESM::Cell& destination) {
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    const auto ptr = resolve(handle); auto& target = load(destination);
    if (ptr.getCell() == &target) throw std::runtime_error("G6 move to same CELL");
    const auto moved = ptr.getCell()->moveTo(ptr, &target);
    model->registerPtr(moved);
}
Statistics LiveWorld::diagnostics() {
    std::lock_guard lock(engineDispatch); auto result = statistics;
    result.loadedCells = prepared.size();
    const auto registry = model->getPtrRegistryView();
    result.registeredObjects = static_cast<std::size_t>(std::distance(registry.begin(), registry.end()));
    return result;
}
void LiveWorld::clear() {
    std::lock_guard lock(engineDispatch); Binding binding(mutableStore(), *model);
    model->clear(); prepared.clear(); rejected.clear(); statistics = {}; epoch = nextEpoch.fetch_add(1);
}
}
