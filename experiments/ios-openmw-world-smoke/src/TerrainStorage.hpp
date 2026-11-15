#pragma once
#include "WorldIndex.hpp"
#include <components/esmterrain/storage.hpp>
#include <map>
#include <mutex>

namespace G4 {
class TerrainStorage final : public ESMTerrain::Storage {
    WorldIndex& index;
    std::mutex mutex;
    std::map<std::pair<int,int>,std::weak_ptr<const ESMTerrain::LandObject>> objects;
public:
    TerrainStorage(WorldIndex& store,const VFS::Manager* vfs):Storage(vfs),index(store){}
    std::shared_ptr<const ESMTerrain::LandObject> getLand(ESM::ExteriorCellLocation location) override;
    const VFS::Path::Normalized* getLandTexture(std::uint16_t texture,int plugin) override;
    void getBounds(float& minX,float& maxX,float& minY,float& maxY,ESM::RefId worldspace) override;
};
}
