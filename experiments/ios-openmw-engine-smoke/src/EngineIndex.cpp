#include "EngineIndex.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/misc/strings/algorithm.hpp>
#include <algorithm>
#include <unordered_set>
#include <stdexcept>

namespace G5 {
namespace {
void validateWorldContainers(ESM::ESMReader& reader) {
    // Preserve G4's explicit unsupported-container-deletion gate. The pinned
    // Store<Cell>/Store<Land> do not implement DynamicStore::eraseStatic;
    // passing DELE through ESMStore would otherwise leave old world data alive.
    // Use genuine codecs, and stop before CELL reference DELE subrecords.
    const auto start=reader.getContext();unsigned records=0;
    while(reader.hasMoreRecs()) {
        if(++records>4000000)throw std::runtime_error("G5 content record budget exceeded");
        const auto type=reader.getRecName();reader.getRecHeader();
        bool deleted=false;
        if(!(reader.getRecordFlags()&ESM::FLAG_Ignored)) {
            if(type=="CELL") {ESM::Cell cell;cell.loadNameAndData(reader,deleted);}
            else if(type=="LAND") {ESM::Land land;land.load(reader,deleted);}
        }
        if(deleted)throw std::runtime_error("G5 deleted "+type.toString()+" unsupported by the pinned world-container store");
        reader.skipRecord();
    }
    reader.restoreContext(start);
}
}
EngineIndex::EngineIndex(const std::vector<std::filesystem::path>& content)
    : cells(engine.getWritable<ESM::Cell>()), lands(engine.getWritable<ESM::Land>()),
      textures(engine.getWritable<ESM::LandTexture>()) {
    if(content.empty() || content.size()>254) throw std::runtime_error("G5 content count outside 1..254");
    std::unordered_set<std::string,Misc::StringUtils::CiHash,Misc::StringUtils::CiEqual> loaded;
    for(std::size_t index=0;index<content.size();++index) {
        const auto name=content[index].filename().string();
        if(!loaded.insert(name).second) throw std::runtime_error("G5 duplicate content filename: "+name);
        auto item=readers.get(index);auto& reader=*item;
        reader.setEncoder(&encoder);reader.setIndex(static_cast<int>(index));reader.open(content[index]);
        for(const auto& master:reader.getGameFiles()) {
            const auto found=std::find_if(content.begin(),content.begin()+index,[&](const auto& path){
                return Misc::StringUtils::ciEqual(path.filename().string(),master.name);
            });
            if(found==content.begin()+index) throw std::runtime_error("G5 missing or out-of-order master: "+master.name);
        }
        reader.resolveParentFileIndices(readers);
        validateWorldContainers(reader);
        ESM::Dialogue* dialogue=nullptr;
        // Genuine engine dispatcher: FLAG_Ignored, record deletion, dialogue,
        // indexed skills/magic effects and Lua content use upstream behavior.
        engine.load(reader,nullptr,dialogue);
    }
    engine.setUp(); // Native ID index and every native Store's setup.
}

EngineIndex::Base EngineIndex::base(const ESM::RefId& id) const {
    const int type=engine.find(id);
    if(!type) return {};
    std::string name(4,'\0');
    for(unsigned i=0;i<4;++i) name[i]=static_cast<char>((static_cast<unsigned>(type)>>(8*i))&255);
    switch(type) {
        case ESM::REC_STAT:return {name,engine.get<ESM::Static>().find(id)->mModel.getOriginal()};
        case ESM::REC_ACTI:return {name,engine.get<ESM::Activator>().find(id)->mModel.getOriginal()};
        case ESM::REC_CONT:return {name,engine.get<ESM::Container>().find(id)->mModel.getOriginal()};
        case ESM::REC_DOOR:return {name,engine.get<ESM::Door>().find(id)->mModel.getOriginal()};
        case ESM::REC_LIGH:return {name,engine.get<ESM::Light>().find(id)->mModel.getOriginal()};
        case ESM::REC_MISC:return {name,engine.get<ESM::Miscellaneous>().find(id)->mModel.getOriginal()};
        default:return {name,{}}; // Full metadata retained; actors/gameplay not activated.
    }
}
}
