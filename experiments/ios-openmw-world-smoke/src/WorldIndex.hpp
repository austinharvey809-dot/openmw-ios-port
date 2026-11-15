#pragma once
#include <apps/openmw/mwworld/store.hpp>
#include <components/esm3/readerscache.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/esm3/loadacti.hpp>
#include <components/esm3/loadcont.hpp>
#include <components/esm3/loaddoor.hpp>
#include <components/esm3/loadligh.hpp>
#include <components/esm3/loadmisc.hpp>
#include <components/esm3/loadltex.hpp>
#include <components/toutf8/toutf8.hpp>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace G4 {
// Uses the genuine Store specializations, not a substitute for ESMStore/CellStore.
// Cell metadata stays indexed; references are read only when a cell is requested.
class WorldIndex {
    ToUTF8::Utf8Encoder encoder{ToUTF8::WINDOWS_1252};
    ESM::ReadersCache readers{16};
    std::map<ESM::RefId, std::string> types;
    MWWorld::Store<ESM::Static> statics;
    MWWorld::Store<ESM::Activator> activators;
    MWWorld::Store<ESM::Container> containers;
    MWWorld::Store<ESM::Door> doors;
    MWWorld::Store<ESM::Light> lights;
    MWWorld::Store<ESM::Miscellaneous> misc;
    template<class T> void loadBase(ESM::ESMReader& reader, MWWorld::Store<T>& store, const std::string& type);
    template<class T> void excludedBase(ESM::ESMReader& reader,const std::string& type);
public:
    MWWorld::Store<ESM::Cell> cells;
    MWWorld::Store<ESM::Land> lands;
    MWWorld::Store<ESM::LandTexture> textures;
    explicit WorldIndex(const std::vector<std::filesystem::path>& content);
    std::vector<ESM::CellRef> references(const ESM::Cell& cell);
    struct Base {std::string type, model;};
    Base base(const ESM::RefId& id) const;
    const ESM::Light* light(const ESM::RefId& id)const{return lights.search(id);}
};
}
