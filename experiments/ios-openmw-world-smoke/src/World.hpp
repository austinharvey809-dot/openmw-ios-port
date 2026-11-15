#pragma once
#include "Resources.hpp"
#include "TerrainStorage.hpp"
#include <experiments/ios-openmw-exterior-smoke/src/Physics.hpp>
#include <components/terrain/terraingrid.hpp>
#include <osg/Group>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace G4 {
struct Location {
    std::string interior;
    int x=-2,y=-9;
    friend bool operator==(const Location&,const Location&)=default;
};
struct Door {
    osg::Vec3d position;
    ESM::Position destination;
    std::string cell;
    bool locked=false,trapped=false;
};
struct Area {
    osg::ref_ptr<osg::Group> scene=new osg::Group;
    std::vector<std::shared_ptr<const ESMTerrain::LandObject>> heights;
    std::shared_ptr<G3::Physics> physics=std::make_shared<G3::Physics>();
    std::unique_ptr<TerrainStorage> storage;
    std::unique_ptr<Terrain::TerrainGrid> terrain;
    Location location;
    std::vector<Door> doors;
    unsigned cells=0,references=0,instances=0;
    unsigned omittedNormalsStates=0;
    unsigned terrainPasses=0,drawables=0,programs=0;
    std::map<std::string,unsigned> exclusions;
    // Original CELL water information is retained; this does not claim swimming.
    std::map<std::pair<int,int>,float> waterLevels;
};
osg::Matrix placement(const ESM::CellRef& reference);
Location exteriorAt(const osg::Vec3d& position);
std::unique_ptr<Area> prepare(WorldIndex& index,Resources& resources,const Location& location);
const Door* activationDoor(const Area& area,const osg::Vec3d& eye,const osg::Vec3d& direction);
Location destination(const Door& door);
void initializeDefaults();
void configureEnvironment(Area& area,const ESM::Cell* interior);
}
