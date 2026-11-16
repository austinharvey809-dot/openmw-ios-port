#pragma once
#include "EngineIndex.hpp"
#include <apps/openmw/mwworld/worldmodel.hpp>
#include <cstdint>
#include <filesystem>
#include <map>
#include <memory>
#include <vector>

namespace G6 {
// Handles never expose an unowned engine Ptr. A content reference number alone
// is not an identity across WorldModel::clear or across content stacks.
struct Handle {
    ESM::RefNum reference;
    std::uint64_t epoch = 0;
};
struct Object {
    Handle handle;
    ESM::CellRef reference;
    unsigned type = 0;
    bool enabled = false, actor = false, customData = false;
};
struct Limits {
    std::size_t cells = 128;
    std::size_t rawReferencesPerCell = 131072;
    std::size_t rawReferencesTotal = 524288;
};
struct Statistics {
    std::size_t loadedCells = 0, registeredObjects = 0, rawReferences = 0;
    std::size_t successfulLoads = 0, failedLoads = 0;
    double lastPreparationMs = 0, maximumPreparationMs = 0;
};

// Genuine ESMStore -> WorldModel -> CellStore -> typed LiveCellRef ownership.
// This component deliberately does not install dummy MWBase gameplay services.
// It offers data/lifetime operations, not Class::activate or actor simulation.
class LiveWorld : public G6Store::EngineIndex {
    std::unique_ptr<MWWorld::WorldModel> model;
    Limits limits;
    Statistics statistics;
    std::map<ESM::RefId, std::size_t> prepared;
    std::map<ESM::RefId, std::string> rejected;
    std::uint64_t epoch = 0;
    MWWorld::CellStore& load(const ESM::Cell& cell);
    MWWorld::Ptr resolve(Handle handle);
    Object snapshot(const MWWorld::ConstPtr& object) const;
public:
    // defaults is the unchanged upstream files/settings-default.cfg, not a
    // fabricated Settings object. All public operations serialize MWBase access.
    LiveWorld(const std::vector<std::filesystem::path>& content,
        const std::filesystem::path& defaults = {}, Limits limits = {});
    ~LiveWorld();
    LiveWorld(const LiveWorld&) = delete;
    LiveWorld& operator=(const LiveWorld&) = delete;
    std::vector<Object> objects(const ESM::Cell& cell, bool includeDeleted = false);
    std::vector<ESM::CellRef> references(const ESM::Cell& cell);
    Object inspect(Handle handle);
    void setPosition(Handle handle, const ESM::Position& position);
    void setEnabled(Handle handle, bool enabled);
    // Nonzero count changes only. Runtime deletion requires the genuine World
    // service and its script cleanup; content-file deletions remain native.
    void setCount(Handle handle, int count);
    void move(Handle handle, const ESM::Cell& destination);
    Statistics diagnostics();
    // Explicit whole-session reset; never used as silent cache eviction.
    void clear();
};
using WorldIndex = LiveWorld;
}
