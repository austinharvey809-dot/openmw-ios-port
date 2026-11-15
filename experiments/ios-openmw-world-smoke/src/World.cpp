#include "World.hpp"
#include "SceneAudit.hpp"
#include "GLES3Terrain.hpp"
#include <components/bullethelpers/heightfield.hpp>
#include <components/misc/resourcehelpers.hpp>
#include <components/resource/scenemanager.hpp>
#include <components/resource/imagemanager.hpp>
#include <components/sceneutil/lightmanager.hpp>
#include <components/sceneutil/lightcommon.hpp>
#include <components/sceneutil/lightutil.hpp>
#include <osg/MatrixTransform>
#include <BulletCollision/CollisionShapes/btCompoundShape.h>
#include <BulletCollision/CollisionShapes/btHeightfieldTerrainShape.h>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace G4 {
namespace {
void finite(const ESM::Position& position){
    for(unsigned i=0;i<3;++i)if(!std::isfinite(position.pos[i])||!std::isfinite(position.rot[i]))
        throw std::runtime_error("G4 nonfinite original placement/destination");
}
void heightfield(Area& area,std::shared_ptr<const ESMTerrain::LandObject> land,int x,int y){
    const auto* data=land->getData(ESM::Land::DATA_VHGT);
    if(!data)throw std::runtime_error("G4 selected LAND lacks height data");
    for(float height:data->getHeights())if(!std::isfinite(height))throw std::runtime_error("G4 nonfinite LAND height");
    const auto heights=data->getHeights();
    auto child=std::make_unique<btHeightfieldTerrainShape>(65,65,heights.data(),data->getMinHeight(),data->getMaxHeight(),2,false);
    child->setUseDiamondSubdivision(true);child->setLocalScaling(btVector3(128,128,1));child->buildAccelerator();
    Resource::CollisionShapePtr shape(new btCompoundShape);
    auto* compound=static_cast<btCompoundShape*>(shape.get());
    const auto shift=BulletHelpers::getHeightfieldShift(x,y,8192,data->getMinHeight(),data->getMaxHeight());
    compound->addChildShape(btTransform(btQuaternion::getIdentity(),shift),child.get());child.release();
    area.heights.push_back(std::move(land));area.physics->addTerrain(std::move(shape));
}
void cellObjects(Area& area,WorldIndex& index,Resources& resources,const ESM::Cell& cell){
    for(const auto& ref:index.references(cell)){
        if(++area.references>32768)throw std::runtime_error("G4 active area reference budget exceeded");
        const auto base=index.base(ref.mRefID);
        if(base.type.empty())throw std::runtime_error("G4 missing/deleted base reference: "+ref.mRefID.toDebugString());
        if(base.type!="STAT"&&base.type!="ACTI"&&base.type!="CONT"&&base.type!="DOOR"&&base.type!="LIGH"&&base.type!="MISC"){
            ++area.exclusions["record-type:"+base.type];continue;
        }
        if(Misc::ResourceHelpers::isHiddenMarker(ref.mRefID)){++area.exclusions["editor-marker"];continue;}
        if(base.model.empty()&&base.type!="LIGH")throw std::runtime_error("G4 missing static base model: "+ref.mRefID.toDebugString());
        try{
            const auto matrix=placement(ref);
            osg::ref_ptr<osg::MatrixTransform> transform=new osg::MatrixTransform(matrix);
            transform->setName(ref.mRefID.toDebugString());
            if(!base.model.empty()){
                auto node=resources.instance(base.model);
                resources.system.getSceneManager()->attachTo(node,transform);
            }
            transform->addCullCallback(new SceneUtil::LightListCallback);
            if(const auto* light=index.light(ref.mRefID)){
                SceneUtil::LightCommon common(*light);
                if(!common.mOffDefault)SceneUtil::addLight(transform,common,~0u,cell.isExterior());
                else ++area.exclusions["off-default-light"];
            }
            area.scene->addChild(transform);
            if(!base.model.empty()){
                const auto path=Misc::ResourceHelpers::correctMeshPath(VFS::Path::Normalized(base.model));
                auto shape=resources.collision->getShape(path);
                if(shape && shape->isAnimated())++area.exclusions["animated-collision"];
                else if(shape)area.physics->add(std::move(shape),matrix);
                ++area.instances;
            }
            if(base.type=="DOOR"&&ref.mTeleport){
                finite(ref.mDoorDest);
                area.doors.push_back({{ref.mPos.pos[0],ref.mPos.pos[1],ref.mPos.pos[2]},ref.mDoorDest,
                    ref.mDestCell,ref.mIsLocked||ref.mLockLevel>0,!ref.mTrap.empty()});
            }
        }catch(const std::exception& e){throw std::runtime_error("G4 stage=place CELL="+cell.mName+" base="+ref.mRefID.toDebugString()+": "+e.what());}
    }
    ++area.cells;
}
}
osg::Matrix placement(const ESM::CellRef& ref){
    finite(ref.mPos);
    if(!std::isfinite(ref.mScale)||ref.mScale<=0||ref.mScale>100)throw std::runtime_error("G4 invalid original scale");
    // RenderingManager's original non-actor negative X/Y/Z quaternion convention.
    const auto rotation=osg::Quat(ref.mPos.rot[0],osg::Vec3(-1,0,0))*osg::Quat(ref.mPos.rot[1],osg::Vec3(0,-1,0))
        *osg::Quat(ref.mPos.rot[2],osg::Vec3(0,0,-1));
    return osg::Matrix::scale(ref.mScale,ref.mScale,ref.mScale)*osg::Matrix::rotate(rotation)
        *osg::Matrix::translate(ref.mPos.pos[0],ref.mPos.pos[1],ref.mPos.pos[2]);
}
Location exteriorAt(const osg::Vec3d& position){
    for(unsigned i=0;i<3;++i)if(!std::isfinite(position[i]))throw std::runtime_error("G4 nonfinite world position");
    const double x=std::floor(position.x()/8192),y=std::floor(position.y()/8192);
    if(std::abs(x)>100000 || std::abs(y)>100000)throw std::runtime_error("G4 exterior coordinate budget exceeded");
    return {{},int(x),int(y)};
}
std::unique_ptr<Area> prepare(WorldIndex& index,Resources& resources,const Location& location){
    std::lock_guard registry(CapabilityRegistryMutex);
    auto area=std::make_unique<Area>();area->location=location;
    initializeDefaults();area->scene=new SceneUtil::LightManager(SceneUtil::LightSettings{},&resources.system);
    if(!location.interior.empty()){
        const auto* cell=index.cells.find(location.interior);configureEnvironment(*area,cell);cellObjects(*area,index,resources,*cell);
        if(cell->mData.mFlags&ESM::Cell::HasWater){
            if(!std::isfinite(cell->mWater))throw std::runtime_error("G4 nonfinite original water level");
            area->waterLevels[{0,0}]=cell->mWater;
        }
        SceneAudit audit(resources.system.getImageManager()->getWarningImage());area->scene->accept(audit);
        area->drawables=audit.geometry;area->programs=audit.programs.size();return area;
    }
    configureEnvironment(*area,nullptr);
    if(std::abs(double(location.x))>100000||std::abs(double(location.y))>100000)throw std::runtime_error("G4 exterior coordinate budget exceeded");
    area->storage=std::make_unique<TerrainStorage>(index,&resources.vfs);auto* sampling=area->storage.get();
    area->terrain=std::make_unique<Terrain::TerrainGrid>(area->scene,area->scene,&resources.system,
        sampling,~0u,ESM::Cell::sDefaultWorldspaceId,0);
    // In this pinned source World::~World does not delete mStorage, despite its
    // older header comment. Keep explicit ownership and destroy TerrainGrid first.
    for(int y=location.y-1;y<=location.y+1;++y)for(int x=location.x-1;x<=location.x+1;++x){
        const auto* cell=index.cells.search(x,y);
        const auto land=sampling->getLand({x,y,ESM::Cell::sDefaultWorldspaceId});
        // Original oceans may have no CELL or LAND. Do not fabricate geometry.
        if(land){heightfield(*area,land,x,y);area->terrain->loadCell(x,y);}
        if(cell){
            if(!std::isfinite(cell->mWater))throw std::runtime_error("G4 nonfinite original water level");
            cellObjects(*area,index,resources,*cell);area->waterLevels[{x,y}]=cell->mWater;
        }
    }
    area->terrain->setActiveGrid({location.x-1,location.y-1,location.x+2,location.y+2});
    GLES3Terrain backend;area->scene->accept(backend);area->omittedNormalsStates=backend.omittedNormalsStates;
    SceneAudit audit(resources.system.getImageManager()->getWarningImage());area->scene->accept(audit);
    area->drawables=audit.geometry;area->terrainPasses=audit.terrainPasses;area->programs=audit.programs.size();return area;
}
const Door* activationDoor(const Area& area,const osg::Vec3d& eye,const osg::Vec3d& direction){
    if(!std::isfinite(direction.length2())||direction.length2()<1e-9)return nullptr;
    const auto forward=direction/direction.length();const Door* selected=nullptr;double nearest=192;
    for(const auto& door:area.doors){
        auto delta=door.position+osg::Vec3d(0,0,64)-eye;const double distance=delta.length();
        if(distance>1 && distance<nearest && (delta/distance)*forward>.65){selected=&door;nearest=distance;}
    }
    return selected;
}
Location destination(const Door& door){
    finite(door.destination);
    if(door.locked||door.trapped)throw std::runtime_error("G4 locked/trapped door requires genuine gameplay activation");
    if(!door.cell.empty())return {door.cell,0,0};
    return exteriorAt({door.destination.pos[0],door.destination.pos[1],door.destination.pos[2]});
}
}
