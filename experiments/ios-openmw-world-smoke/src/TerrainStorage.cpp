#include "TerrainStorage.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>

namespace G4 {
std::shared_ptr<const ESMTerrain::LandObject> TerrainStorage::getLand(ESM::ExteriorCellLocation location){
    if(location.mWorldspace!=ESM::Cell::sDefaultWorldspaceId)return {};
    std::lock_guard lock(mutex);
    const auto key=std::pair(location.mX,location.mY);
    if(const auto found=objects.find(key);found!=objects.end())if(auto alive=found->second.lock())return alive;
    const auto* land=index.lands.search(location.mX,location.mY);if(!land)return {};
    constexpr int flags=ESM::Land::DATA_VHGT|ESM::Land::DATA_VNML|ESM::Land::DATA_VCLR|ESM::Land::DATA_VTEX;
    auto result=std::make_shared<ESMTerrain::LandObject>(*land,flags);
    // Weak entries never retain the world's height arrays. Prune metadata too.
    for(auto it=objects.begin();it!=objects.end();)if(it->second.expired())it=objects.erase(it);else ++it;
    objects[key]=result;return result;
}
const VFS::Path::Normalized* TerrainStorage::getLandTexture(std::uint16_t texture,int plugin){
    const auto* path=index.textures.search(texture,plugin);
    if(!path)return nullptr;
    return &path->getNormalized();
}
void TerrainStorage::getBounds(float& minX,float& maxX,float& minY,float& maxY,ESM::RefId worldspace){
    if(worldspace!=ESM::Cell::sDefaultWorldspaceId)throw std::runtime_error("G4 unsupported terrain worldspace");
    minX=minY=std::numeric_limits<float>::max();maxX=maxY=std::numeric_limits<float>::lowest();
    for(const auto& land:index.lands){
        minX=std::min(minX,float(land.mX));minY=std::min(minY,float(land.mY));
        maxX=std::max(maxX,float(land.mX)+1);maxY=std::max(maxY,float(land.mY)+1);
    }
    if(minX>maxX){minX=minY=maxX=maxY=0;}
}
}
