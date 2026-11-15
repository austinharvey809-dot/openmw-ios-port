#include "WorldIndex.hpp"
#include <components/esm/records.hpp>
#include <algorithm>
#include <set>
#include <unordered_set>
#include <stdexcept>

namespace G4 {
template<class T> void WorldIndex::excludedBase(ESM::ESMReader& reader,const std::string& type){
    T record;bool deleted=false;record.load(reader,deleted);
    const auto previous=types.find(record.mId);
    if(previous!=types.end()&&previous->second!=type)throw std::runtime_error("G4 base record changes type across load order");
    if(deleted)types.erase(record.mId);else types[record.mId]=type;
}
template<class T> void WorldIndex::loadBase(ESM::ESMReader& reader, MWWorld::Store<T>& store, const std::string& type) {
    const auto loaded=store.load(reader);
    const auto previous=types.find(loaded.mId);
    if(previous!=types.end() && previous->second!=type)
        throw std::runtime_error("G4 base record changes type across load order: "+loaded.mId.toDebugString());
    if(loaded.mIsDeleted){store.eraseStatic(loaded.mId);types.erase(loaded.mId);}
    else types[loaded.mId]=type;
}

WorldIndex::WorldIndex(const std::vector<std::filesystem::path>& content) {
    if(content.empty() || content.size()>254)throw std::runtime_error("G4 content count outside 1..254");
    std::unordered_set<std::string,Misc::StringUtils::CiHash,Misc::StringUtils::CiEqual> loaded;
    for(std::size_t index=0;index<content.size();++index){
        const auto name=content[index].filename().string();
        if(!loaded.insert(name).second)throw std::runtime_error("G4 duplicate content filename: "+name);
        auto item=readers.get(index);auto& reader=*item;
        reader.setEncoder(&encoder);reader.setIndex(static_cast<int>(index));reader.open(content[index]);
        for(const auto& master:reader.getGameFiles()){
            auto found=std::find_if(content.begin(),content.begin()+index,[&](const auto& path){
                return Misc::StringUtils::ciEqual(path.filename().string(),master.name);
            });
            if(found==content.begin()+index)throw std::runtime_error("G4 missing or out-of-order master: "+master.name);
        }
        reader.resolveParentFileIndices(readers);
        unsigned records=0;
        while(reader.hasMoreRecs()){
            if(++records>4000000)throw std::runtime_error("G4 content record budget exceeded");
            const auto type=reader.getRecName();reader.getRecHeader();
            if(type=="CELL"){
                const auto id=cells.load(reader);
                if(id.mIsDeleted)throw std::runtime_error("G4 deleted CELL unsupported by this integration");
            }else if(type=="LAND"){
                const auto id=lands.load(reader);
                if(id.mIsDeleted)throw std::runtime_error("G4 deleted LAND unsupported by this integration");
            }else if(type=="LTEX"){
                const auto id=textures.load(reader);if(id.mIsDeleted)textures.eraseStatic(id.mId);
            }else if(type=="STAT")loadBase(reader,statics,"STAT");
            else if(type=="ACTI")loadBase(reader,activators,"ACTI");
            else if(type=="CONT")loadBase(reader,containers,"CONT");
            else if(type=="DOOR")loadBase(reader,doors,"DOOR");
            else if(type=="LIGH")loadBase(reader,lights,"LIGH");
            else if(type=="MISC")loadBase(reader,misc,"MISC");
            else if(type=="NPC_")excludedBase<ESM::NPC>(reader,"NPC_");
            else if(type=="CREA")excludedBase<ESM::Creature>(reader,"CREA");
            else if(type=="LEVC")excludedBase<ESM::CreatureLevList>(reader,"LEVC");
            else if(type=="LEVI")excludedBase<ESM::ItemLevList>(reader,"LEVI");
            else if(type=="INGR")excludedBase<ESM::Ingredient>(reader,"INGR");
            else if(type=="BOOK")excludedBase<ESM::Book>(reader,"BOOK");
            else if(type=="WEAP")excludedBase<ESM::Weapon>(reader,"WEAP");
            else if(type=="ALCH")excludedBase<ESM::Potion>(reader,"ALCH");
            else if(type=="ARMO")excludedBase<ESM::Armor>(reader,"ARMO");
            else if(type=="CLOT")excludedBase<ESM::Clothing>(reader,"CLOT");
            else if(type=="APPA")excludedBase<ESM::Apparatus>(reader,"APPA");
            else if(type=="PROB")excludedBase<ESM::Probe>(reader,"PROB");
            else if(type=="LOCK")excludedBase<ESM::Lockpick>(reader,"LOCK");
            else if(type=="REPA")excludedBase<ESM::Repair>(reader,"REPA");
            else reader.skipRecord();
        }
    }
    lands.setUp();
}

std::vector<ESM::CellRef> WorldIndex::references(const ESM::Cell& cell) {
    std::map<ESM::RefNum,ESM::CellRef> merged;
    auto apply=[&](const ESM::CellRef& ref,bool deleted){
        if(deleted)merged.erase(ref.mRefNum);else merged[ref.mRefNum]=ref;
        if(merged.size()>65536)throw std::runtime_error("G4 active CELL reference budget exceeded");
    };
    for(std::size_t i=0;i<cell.mContextList.size();++i){
        auto item=readers.get(static_cast<std::size_t>(cell.mContextList[i].index));cell.restore(*item,i);
        ESM::CellRef ref;ESM::MovedCellRef movedRef;bool deleted=false,moved=false;
        while(ESM::Cell::getNextRef(*item,ref,deleted,movedRef,moved,ESM::Cell::GetNextRefMode::LoadOnlyNotMoved)){
            // This mode reports skipped moved pairs without populating ref.
            // Their real destination placements come from Store<Cell>'s leases.
            if(moved)continue;
            if(std::find(cell.mMovedRefs.begin(),cell.mMovedRefs.end(),ref.mRefNum)!=cell.mMovedRefs.end())continue;
            apply(ref,deleted);
        }
    }
    for(const auto& leased:cell.mLeasedRefs)apply(leased.first,leased.second);
    std::vector<ESM::CellRef> result;result.reserve(merged.size());
    for(auto& [number,ref]:merged)result.push_back(std::move(ref));
    return result;
}

WorldIndex::Base WorldIndex::base(const ESM::RefId& id) const {
    const auto it=types.find(id);if(it==types.end())return {};
    const auto& type=it->second;
    if(type=="STAT")return {type,statics.find(id)->mModel.getOriginal()};
    if(type=="ACTI")return {type,activators.find(id)->mModel.getOriginal()};
    if(type=="CONT")return {type,containers.find(id)->mModel.getOriginal()};
    if(type=="DOOR")return {type,doors.find(id)->mModel.getOriginal()};
    if(type=="LIGH")return {type,lights.find(id)->mModel.getOriginal()};
    if(type=="MISC")return {type,misc.find(id)->mModel.getOriginal()};
    return {type,{}}; // Known record class deliberately outside the static world view.
}
}
