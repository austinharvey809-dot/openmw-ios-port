#pragma once
#include <apps/openmw/mwworld/esmstore.hpp>
#include <apps/openmw/mwworld/store.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/esm3/loadacti.hpp>
#include <components/esm3/loadcont.hpp>
#include <components/esm3/loaddoor.hpp>
#include <components/esm3/loadligh.hpp>
#include <components/esm3/loadmisc.hpp>
#include <components/esm3/loadltex.hpp>
#include <components/esm3/readerscache.hpp>
#include <components/toutf8/toutf8.hpp>
#include <filesystem>

namespace G5 {
// Own the real engine's full ESM3 record store. Geometry remains bounded by
// the accepted streamed resource/scene provider; records are not scene objects.
class EngineIndex {
    ToUTF8::Utf8Encoder encoder{ToUTF8::WINDOWS_1252};
    ESM::ReadersCache readers{16};
    MWWorld::ESMStore engine;
public:
    MWWorld::Store<ESM::Cell>& cells;
    MWWorld::Store<ESM::Land>& lands;
    MWWorld::Store<ESM::LandTexture>& textures;
    explicit EngineIndex(const std::vector<std::filesystem::path>& content);
    EngineIndex(const EngineIndex&) = delete;
    EngineIndex& operator=(const EngineIndex&) = delete;
    const MWWorld::ESMStore& store() const { return engine; }
    std::vector<ESM::CellRef> references(const ESM::Cell& cell);
    struct Base { std::string type, model; };
    Base base(const ESM::RefId& id) const;
    const ESM::Light* light(const ESM::RefId& id) const { return engine.get<ESM::Light>().search(id); }
};
using WorldIndex = EngineIndex;
}
