#include "LiveWorld.hpp"
#include "G6Defaults.hpp"
#include <apps/openmw/mwrender/fogmanager.hpp>
#include <components/fallback/fallback.hpp>
#include <components/settings/values.hpp>
#include <MyGUI_UString.h>
#include <unicode/numfmt.h>
#include <LinearMath/btScalar.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <limits>
#include <thread>
static_assert(sizeof(btScalar) == 8, "G6 must share the genuine double-precision Bullet ABI");

namespace {
unsigned checks = 0;
void require(bool value, const char* reason) {
    ++checks;
    std::fprintf(stderr, "G6 assertion=%u result=%s\n", checks, value ? "PASS" : "FAIL");
    std::fflush(stderr);
    if (!value) throw std::runtime_error(reason);
}
template<class Action> void rejected(Action action, const char* diagnostic) {
    try { action(); }
    catch (const std::exception& error) {
        require(std::string(error.what()).find(diagnostic) != std::string::npos, "Wrong explicit rejection"); return;
    }
    throw std::runtime_error("Expected rejection missing");
}
G6::Object floor(const std::vector<G6::Object>& objects) {
    const auto found = std::find_if(objects.begin(), objects.end(), [](const auto& value) {
        return value.type == ESM::REC_STAT && value.reference.mRefNum.mIndex == 5;
    });
    if (found == objects.end()) throw std::runtime_error("Authored floor reference 5 missing");
    return *found;
}
bool contains(const std::vector<G6::Object>& objects, G6::Handle handle) {
    return std::any_of(objects.begin(), objects.end(), [&](const auto& value) {
        return value.handle.reference == handle.reference && value.handle.epoch == handle.epoch;
    });
}
}
int main(int argc, char** argv) {
    auto* original = std::cout.rdbuf(std::cerr.rdbuf());
    try {
        if (argc < 4) throw std::runtime_error("directory defaults case [private plugin filenames] required");
        const std::filesystem::path root = argv[1], defaults = argv[2];
        const std::string mode = argv[3];
        std::vector<std::filesystem::path> content{root / "Morrowind.esm"};
        if (std::filesystem::is_regular_file(root / "Authored.esp")) content.push_back(root / "Authored.esp");
        if (argc > 4 && mode != "private") throw std::runtime_error("Extra content requires explicit private mode");
        for (int i = 4; i < argc; ++i) {
            const std::filesystem::path name = argv[i];
            if (name.is_absolute() || name.has_parent_path()) throw std::runtime_error("Private plugin must be a filename");
            content.push_back(root / name);
        }
        G6::Limits limits;
        if (mode == "cell-budget") limits.cells = 1;
        if (mode == "reference-budget") limits.rawReferencesPerCell = 1;
        if (mode == "total-budget") limits.rawReferencesTotal = 1;
        if (mode == "zero-budget") limits.cells = 0;
        G6::LiveWorld world(content, defaults, limits);
        require(world.diagnostics().loadedCells == 0, "WorldModel must load cells lazily");
        const auto& center = *world.cells.find(-2, -9);
        const auto& neighbor = *world.cells.find(-1, -9);
        if (mode == "private") {
            std::size_t references = 0, actors = 0, custom = 0;
            for (int y = -10; y <= -8; ++y) for (int x = -3; x <= -1; ++x) {
                if (const auto* cell = world.cells.search(x, y))
                    for (const auto& object : world.objects(*cell)) {
                        ++references; actors += object.actor; custom += object.customData;
                        require(object.handle.reference.hasContentFile(), "Original object identity lost");
                    }
            }
            const auto& interior = *world.cells.find("Seyda Neen, Fargoth's House");
            auto values = world.objects(interior);
            require(values.size() == 46, "Accepted original interior reference inventory changed");
            require(references > 1679, "Original exterior live references missing");
            require(actors > 0, "Actual NPC/creature references not genuinely owned");
            require(custom == 0, "Data loading must not initialize unsupported actor mechanics");
            const auto before = world.diagnostics();
            require(before.loadedCells == 10, "Original lazy cell inventory mismatch");
            require(before.registeredObjects >= references + values.size(), "Genuine Ptr registry incomplete");
            world.clear(); require(world.diagnostics().registeredObjects == 0, "Private world retirement leaked registry");
            std::cout.rdbuf(original);
            std::printf("{\"status\":\"PASS\",\"checks\":%u,\"exterior_references\":%zu,\"actor_references\":%zu,\"interior_references\":%zu,\"loaded_cells\":%zu,\"registered_objects\":%zu,\"maximum_cell_preparation_ms\":%.6f}\n",
                checks, references, actors, values.size(), before.loadedCells, before.registeredObjects, before.maximumPreparationMs);
            return 0;
        }
        if (mode == "missing-base" || mode == "deleted-base" || mode == "reference-budget" || mode == "total-budget") {
            world.objects(center); throw std::runtime_error("Required invalid input unexpectedly loaded");
        }
        if (mode == "plugin-move") {
            const auto from = world.objects(center), to = world.objects(neighbor);
            require(std::none_of(from.begin(), from.end(), [](const auto& o) { return o.reference.mRefNum.mIndex == 5; }), "Moved lease remained in origin CELL");
            const auto object = floor(to);
            require(object.reference.mPos.pos[2] == 64, "Genuine destination lease placement lost");
            require(object.handle.reference.mContentFile == 0, "Master content identity remapping lost");
        } else if (mode == "plugin-delete") {
            auto active = world.objects(center);
            require(std::none_of(active.begin(), active.end(), [](const auto& o) { return o.reference.mRefNum.mIndex == 5; }), "Deleted content reference visible");
            require(world.objects(center, true).size() > active.size(), "Deleted reference ownership must remain inspectable");
        } else {
            const auto values = world.objects(center);
            const auto object = floor(values); const auto handle = object.handle;
            require(object.reference.mRefID == ESM::RefId::stringRefId("floor"), "Real typed base identity mismatch");
            require(object.handle.reference.mContentFile == 0, "Content index changed");
            require(!object.actor && !object.customData, "Static reference allocated actor state");
            require(world.inspect(handle).type == ESM::REC_STAT, "Genuine registry lookup lost typed object");
            require(world.diagnostics().registeredObjects == world.objects(center, true).size(), "Real registry does not own every loaded reference");
            if (mode == "ownership") {
                require(world.references(center).size() == values.size(), "Renderer input not derived from live objects");
                require(world.diagnostics().loadedCells == 1, "Loading one CELL eagerly loaded neighbors");
                require(world.objects(center).front().handle.epoch == handle.epoch, "Repeat visit replaced live world");
            } else if (mode == "transform") {
                auto position = object.reference.mPos; position.pos[2] += 123; position.rot[2] += .5f;
                world.setPosition(handle, position);
                const auto changed = floor(world.objects(center));
                require(changed.reference.mPos.pos[2] == position.pos[2], "Live RefData position not exposed to renderer");
                require(changed.reference.mPos.rot[2] == position.rot[2], "Live RefData rotation lost");
                require(changed.handle.reference == handle.reference, "Transform replaced identity");
                position.pos[0] = std::numeric_limits<float>::quiet_NaN();
                rejected([&] { world.setPosition(handle, position); }, "nonfinite live position");
            } else if (mode == "enabled") {
                world.setEnabled(handle, false);
                require(!world.inspect(handle).enabled, "RefData disable ignored");
                require(world.references(center).size() + 1 == values.size(), "Disabled object still reaches renderer");
                world.setEnabled(handle, true);
                require(world.references(center).size() == values.size(), "Enabled object did not return");
            } else if (mode == "count") {
                world.setCount(handle, 2);
                require(world.inspect(handle).reference.mCount == 2, "Real CellRef count not updated");
                require(contains(world.objects(center), handle), "Nonzero count removed live object");
                rejected([&] { world.setCount(handle, 0); }, "runtime deletion requires genuine MWWorld::World");
                require(world.inspect(handle).reference.mCount == 2, "Rejected deletion mutated reference before checking services");
                world.setCount(handle, 1); require(world.inspect(handle).reference.mCount == 1, "Count restore failed");
                rejected([&] { world.setCount(handle, -1); }, "negative live count");
            } else if (mode == "runtime-delete") {
                world.setCount(handle, 0); throw std::runtime_error("Unsupported script lifecycle unexpectedly accepted");
            } else if (mode == "move") {
                const auto before = world.objects(neighbor).size();
                world.move(handle, neighbor);
                require(!contains(world.objects(center), handle), "Moved object remained in source");
                require(contains(world.objects(neighbor), handle), "Genuine moveTo did not install destination object");
                require(world.objects(neighbor).size() == before + 1, "Moving duplicated or dropped another reference");
                require(world.inspect(handle).handle.reference == handle.reference, "Move changed identity");
                rejected([&] { world.move(handle, neighbor); }, "move to same CELL");
                world.move(handle, center); require(contains(world.objects(center), handle), "Native return-to-origin ownership failed");
            } else if (mode == "retirement") {
                world.clear(); require(world.diagnostics().registeredObjects == 0, "Registry not cleared");
                rejected([&] { world.inspect(handle); }, "retired object handle");
                const auto fresh = floor(world.objects(center));
                require(fresh.handle.epoch != handle.epoch, "Content RefNum aliases a retired generation");
            } else if (mode == "foreign") {
                G6::LiveWorld other(content, defaults);
                rejected([&] { other.inspect(handle); }, "foreign or retired object handle");
                require(world.inspect(handle).handle.epoch == handle.epoch, "Other world destroyed first owner");
            } else if (mode == "cell-budget") {
                rejected([&] { world.objects(neighbor); }, "CELL budget exhausted");
                require(world.inspect(handle).handle.reference == handle.reference, "Capacity failure discarded live state");
                require(world.diagnostics().loadedCells == 1, "Cell budget exceeded");
            } else if (mode == "quarantine") {
                const auto& invalid = *world.cells.find(0, -9);
                rejected([&] { world.objects(invalid); }, "G6 missing base");
                rejected([&] { world.objects(invalid); }, "quarantined CELL");
                require(world.diagnostics().failedLoads == 1, "Quarantine repeated partial native loading");
                require(world.inspect(handle).handle.reference == handle.reference, "Failed CELL damaged previous live scene data");
            } else if (mode == "duplicate-id") {
                world.objects(neighbor); throw std::runtime_error("Duplicate content identity unexpectedly accepted");
            } else if (mode == "plugin-override") {
                require(object.reference.mPos.pos[2] == 64, "CellStore plugin override lost");
            } else if (mode == "plugin-new") {
                require(values.size() == 3, "Plugin reference with separate content identity was merged away");
            } else if (mode == "actors") {
                const auto actor = std::find_if(values.begin(), values.end(), [](const auto& o) { return o.actor; });
                require(actor != values.end(), "Genuine NPC class missing from CELL ownership");
                require(actor->type == ESM::REC_NPC_, "Actor not backed by actual NPC LiveCellRef");
                require(!actor->customData, "Data-only load initialized gameplay services");
            } else if (mode == "concurrency") {
                std::atomic<bool> failed{false}; std::vector<std::thread> threads;
                for (int i = 0; i < 4; ++i) threads.emplace_back([&] {
                    try { for (int n = 0; n < 25; ++n) if (world.objects(center).size() != values.size()) failed = true; }
                    catch (...) { failed = true; }
                });
                for (auto& thread : threads) thread.join();
                require(!failed, "Concurrent genuine Environment/CellStore access corrupted state");
                require(world.diagnostics().successfulLoads == 1, "Concurrent reads repeated native loading");
            } else if (mode == "unicode") {
                const std::string utf8 = "\xc3\xa9\xf0\x9f\x8e\xae";
                MyGUI::UString string(utf8);
                require(string.asUTF8() == utf8, "MyGUI UTF8 round trip failed");
                MyGUI::UString utf16(u"\u00e9\U0001f3ae");
                require(utf16.asUTF8() == utf8, "MyGUI UTF16 surrogate pair failed");
                MyGUI::UString utf32(U"\u00e9\U0001f3ae");
                require(utf32.asUTF8() == utf8, "MyGUI UTF32 round trip failed");
                UErrorCode error = U_ZERO_ERROR;
                std::unique_ptr<icu::NumberFormat> format(icu::NumberFormat::createInstance(icu::Locale("fr_FR"), error));
                require(U_SUCCESS(error) && format != nullptr, "Real ICU locale data unavailable");
                icu::UnicodeString number; format->format(2.5, number); std::string result; number.toUTF8String(result);
                require(result == "2,5", "Genuine ICU French numeric formatting failed");
            } else if (mode == "fog") {
                Fallback::Map::init(G6Defaults::Values);
                require(!Settings::fog().mUseDistantFog, "Upstream default no longer selects ordinary fog");
                MWRender::FogManager fog;
                const float depth = Fallback::Map::getFloat("Weather_Clear_Land_Fog_Day_Depth");
                const auto color = Fallback::Map::getColour("Weather_Clear_Fog_Day_Color");
                fog.configure(8192, depth, Fallback::Map::getFloat("Water_UnderwaterIndoorFog"), 1, 0, color);
                const float start = fog.getFogStart(false), end = fog.getFogEnd(false);
                require(std::abs(start - 8192 * (1 - depth)) < .01f, "Accepted clear-day fog differs from native FogManager");
                require(end == 8192, "Accepted far fog differs from native FogManager");
                require(fog.getFogColor(false) == color, "Accepted fog color differs from native FogManager");
                for (const float distance : {2048.f, 4096.f, 6144.f, 8192.f}) {
                    const float value = std::clamp((distance - start) / (end - start), 0.f, 1.f);
                    std::fprintf(stderr, "G6 ordinary linear fog reference distance=%.0f factor=%.6f color=%.6f,%.6f,%.6f; CPU equation, not observed pixels\n",
                        distance, value, color.r(), color.g(), color.b());
                }
                fog.configure(8192, 0, 1, 1, 0, color);
                require(fog.getFogStart(false) == 0 && fog.getFogEnd(false) == std::numeric_limits<float>::max(), "Native no-fog branch changed");
                const auto& interior = *world.cells.find("Seyda Neen, Fargoth's House");
                fog.configure(8192, MWWorld::Cell(interior));
                const auto expectedStart = interior.mAmbi.mFogDensity == 0 ? 0 : 8192 * (1 - interior.mAmbi.mFogDensity);
                require(std::abs(fog.getFogStart(false) - expectedStart) < .01f, "Interior ordinary fog differs from native engine");
                auto authored = interior; authored.mAmbi.mFogDensity = .25f;
                fog.configure(8192, MWWorld::Cell(authored));
                require(fog.getFogStart(false) == 6144 && fog.getFogEnd(false) == 8192, "Authored nonzero interior fog differs from native engine");
            } else throw std::runtime_error("Unknown native G6 case");
        }
        std::cout.rdbuf(original);
        std::printf("{\"status\":\"PASS\",\"checks\":%u}\n", checks); return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "G6 checks_completed=%u: %s\n", checks, error.what());
        std::cout.rdbuf(original); return 1;
    }
}
