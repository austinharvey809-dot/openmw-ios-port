#pragma once
#include "Interior.hpp"
#include "Physics.hpp"
#include <components/esm3/loadland.hpp>
#include <map>
#include <memory>
#include <set>
namespace G3 {
using Coord=std::pair<int,int>;
G2::Model loadMesh(G2::Resources& resources,const std::string& model);
struct Door {osg::Vec3d position;ESM::Position destination;std::string cell;};
struct Environment : G2::Environment {
    std::shared_ptr<Physics> physics;
    unsigned cells=0,terrainVertices=0,terrainTriangles=0,terrainPasses=0;
    unsigned excludedReferences=0,excludedEffects=0;
    std::map<std::string,unsigned> exclusions;
    std::vector<Door> doors;
};
inline bool selected(int x,int y){return x>=-3&&x<=-1&&y>=-10&&y<=-8;}
Environment load(const std::filesystem::path& directory);
void buildTerrain(Environment& result,G2::Resources& resources,const std::map<Coord,ESM::Land>& land,
                  const std::map<unsigned,std::string>& textures);
}
