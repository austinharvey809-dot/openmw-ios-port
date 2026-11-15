#include "Exterior.hpp"
#include "Traversal.hpp"
#include "Material.hpp"
#include "TerrainCoordinates.hpp"
#include <osg/ComputeBoundsVisitor>
#include <osg/Geode>
#include <osg/Geometry>
#include <osg/BlendFunc>
#include <osg/Depth>
#include <iostream>
#include <functional>
#include <limits>
#include <stdexcept>
void require(bool value,const char* why){if(!value)throw std::runtime_error(why);}
void checkMultipleTerrainTextures(const G3::Environment& environment){
    std::map<G3::Coord,std::set<unsigned>> layers;
    const osg::PrimitiveSet* shared=nullptr;
    unsigned passes=0;
    for(unsigned child=0;child<environment.scene->getNumChildren();++child){
        auto* geode=environment.scene->getChild(child)->asGeode();if(!geode)continue;
        auto* geometry=dynamic_cast<osg::Geometry*>(geode->getDrawable(0));require(geometry,"Missing terrain drawable");
        auto* vertices=dynamic_cast<osg::Vec3Array*>(geometry->getVertexArray());require(vertices&&vertices->size()==4225,"Terrain vertex inventory differs");
        const int cx=int(std::lround(vertices->front().x()/8192)),cy=int(std::lround(vertices->front().y()/8192));
        const auto* indices=geometry->getPrimitiveSet(0);require(indices->getNumIndices()==24576,"Terrain topology changed for multipass");
        if(!shared)shared=indices;require(shared==indices,"Terrain passes lost shared genuine topology");
        auto* state=geode->getStateSet();require(state,"Missing terrain state");
        auto* diffuse=dynamic_cast<const osg::Texture2D*>(state->getTextureAttribute(0,osg::StateAttribute::TEXTURE));
        auto* blend=dynamic_cast<const osg::Texture2D*>(state->getTextureAttribute(1,osg::StateAttribute::TEXTURE));
        require(diffuse&&diffuse->getImage()&&blend&&blend->getImage(),"Terrain textures missing after VFS release");
        const auto color=diffuse->getImage()->getColor(0,0);
        unsigned id=0;
        if(color.r()>.99&&color.g()>.99&&color.b()>.99)id=1;
        else if(color.r()>.99&&color.g()<.01&&color.b()<.01)id=2;
        else if(color.r()<.01&&color.g()<.01&&color.b()>.99)id=3;
        require(id!=0,"Authored original DDS color not retained");
        auto& cellLayers=layers[{cx,cy}];const auto pass=cellLayers.size();
        require(cellLayers.insert(id).second,"Duplicate terrain layer");
        const auto* mask=blend->getImage();require(mask->s()==34&&mask->t()==34&&!blend->getResizeNonPowerOfTwoHint(),"Doubled blendmask dimensions changed");
        for(int x=0;x<17;++x)for(int y=0;y<17;++y){
            // Independent expected raster: a third ID exists only in west/north halo cells.
            const int gx=cx*16-1+x,gy=cy*16+y;
            const int sourceX=int(std::floor(gx/16.)),sourceY=int(std::floor(gy/16.));
            const int localX=gx-sourceX*16;
            const unsigned expected=sourceX==-4||sourceY==-7?3u:localX<8?1u:2u;
            for(int dx=0;dx<2;++dx)for(int dy=0;dy<2;++dy)
                require(mask->getColor(x*2+dx,y*2+dy).r()==(id==expected?1.f:0.f),"Genuine neighboring VTEX sampling/doubled mask mismatch");
        }
        const auto* depth=dynamic_cast<const osg::Depth*>(state->getAttribute(osg::StateAttribute::DEPTH));
        require(depth&&depth->getFunction()==(pass?osg::Depth::EQUAL:osg::Depth::LEQUAL),"Multipass depth comparison changed");
        require(bool(state->getMode(GL_BLEND)&osg::StateAttribute::ON)==bool(pass),"Multipass blend enable changed");
        if(pass){auto* fn=dynamic_cast<const osg::BlendFunc*>(state->getAttribute(osg::StateAttribute::BLENDFUNC));require(fn&&fn->getSourceRGB()==GL_ONE&&fn->getDestinationRGB()==GL_ONE,"Premultiplied terrain accumulation changed");}
        require(state->getBinNumber()==-100+int(pass),"Terrain pass ordering changed");++passes;
    }
    require(passes==23&&layers.size()==9,"Wrong native multi-texture terrain pass inventory");
    for(const auto& [cell,ids]:layers)require(ids==(cell.first==-3||cell.second==-8?std::set<unsigned>{1,2,3}:std::set<unsigned>{1,2}),"Neighbor-only material omitted or leaked into interior chunk");
}
void checkFrameCadences(){
    for(int fps:{60,30,20,10,5,4}){
        auto world=std::make_shared<G3::Physics>();
        auto floor=std::make_shared<Resource::BulletShape>();floor->mCollisionShape.reset(new btBoxShape(btVector3(2000,2000,8)));
        world->add(floor,osg::Matrix::translate(-12000,-68000,-8));
        G3::Traversal nav;nav.attach(world,{-12000,-68000,88},0);nav.forward=1;nav.update(0);
        for(int i=1;i<=fps*2;++i)nav.update(double(i)/fps);
        require(std::abs(nav.eye.y()+68000-360)<=1.51,"Rendering cadence slowed grounded movement");
        require(world->steps>=239&&world->steps<=240,"Physics did not keep elapsed time at supported cadence");
        nav.forward=0;nav.lookX=1;
        for(int i=1;i<=fps;++i)nav.update(2.+double(i)/fps);
        require(std::abs(nav.yaw+1.8)<1e-6,"Rendering cadence slowed camera turning");
        const auto before=nav.eye;const auto steps=world->steps;
        nav.suspend();nav.forward=1;nav.update(1000);
        require((nav.eye-before).length()==0&&world->steps==steps,"Suspend/resume accumulated background physics");
        nav.update(2000);
        require(world->steps-steps<=G3::Physics::MaxFrameSteps&&(nav.eye-before).length()<=45.01,"Stall catch-up budget unbounded");
        require(world->droppedSeconds>=999.75,"Dropped wall time not diagnosed");
    }
}
int main(int argc,char** argv){try{
    require(argc==2||argc==3,"Usage: exterior-check directory [authored-case]");
    auto environment=G3::load(argv[1]);osg::ComputeBoundsVisitor bounds;environment.scene->accept(bounds);
    require(bounds.getBoundingBox().valid(),"Scene lost ownership after VFS release");
    require(environment.cells==9&&environment.terrainVertices==38025&&environment.terrainTriangles==73728,"Wrong terrain inventory");
    bool arrivalGrounded=false;double walkingDisplacement=0;
    if(argc==2){
        osg::Vec3d eye;for(int i=0;i<600;++i)eye=environment.physics->move({},1./120);
        arrivalGrounded=environment.physics->grounded();require(arrivalGrounded,"Genuine arrival does not ground on original collision");
        auto start=eye;osg::Vec3d forward(-std::sin(environment.entryYaw),std::cos(environment.entryYaw),0);
        for(int i=0;i<600;++i)eye=environment.physics->move(forward*180,1./120);
        for(unsigned i=0;i<3;++i)require(std::isfinite(eye[i]),"Original-content traversal became nonfinite");
        walkingDisplacement=(eye-start).length();
    }
    if(argc==3){
        const bool multi=std::string(argv[2])=="multi-texture";
        require(environment.models.size()==1&&environment.textures.size()==(multi?3u:1u),"Model/terrain shared resource cache mismatch");
        require(environment.decodedBytes==(multi?192u:64u),"Shared DDS pixels decoded repeatedly");
        require(environment.instances==(std::string(argv[2])=="deleted-reference"?8u:9u),"Wrong reference placements");
        require(environment.terrainPasses==(multi?23u:9u),"Unexpected authored terrain passes");
        if(multi)checkMultipleTerrainTextures(environment);
        if(std::string(argv[2])=="good")checkFrameCadences();
        if(std::string(argv[2])=="inherited-emission"||std::string(argv[2])=="emission-override"){
            const osg::Vec4 expected=std::string(argv[2])=="inherited-emission"?osg::Vec4(.2f,.1f,0,1):osg::Vec4(.4f,.2f,.1f,1);
            unsigned checked=0;std::function<void(osg::Node*)> inspect=[&](osg::Node* node){
                if(auto* state=node->getStateSet())if(auto* u=state->getUniform("material.emission")){osg::Vec4 value;require(u->get(value)&&value==expected,"Inherited/overridden emission uniform differs");++checked;}
                if(auto* group=node->asGroup())for(unsigned i=0;i<group->getNumChildren();++i)inspect(group->getChild(i));
            };inspect(environment.scene);require(checked==9,"Emission did not reach every authored model instance");
        }
        const auto blend=G3::blendCoordinates(0,0);require(std::abs(blend.x()-1.5/34)<1e-6&&std::abs(blend.y()-.5/34)<1e-6,"Upstream terrain blendmap nudge mismatch");
        Nif::NiMaterialProperty material;material.mAmbient={.2f,.3f,.4f};material.mDiffuse={.4f,.5f,.6f};material.mEmissive={.1f,.2f,.3f};material.mSpecular={};material.mAlpha=.8f;material.mGlossiness=0;material.mEmissiveMult=1;
        G3::StaticProperties state;state.material=&material;auto config=G3::materialConfig(state,false,"authored");
        require(config.mEmission==osg::Vec4(.1f,.2f,.3f,1)&&config.mAmbient==osg::Vec4(.2f,.3f,.4f,1),"Emission/ambient material fidelity");
        Nif::NiVertexColorProperty vertex;vertex.mController=Nif::NiTimeControllerPtr(nullptr);vertex.mVertexMode=Nif::NiVertexColorProperty::VertexMode::VertMode_SrcAmbDif;vertex.mLightingMode=Nif::NiVertexColorProperty::LightMode::LightMode_Emissive;
        G3::inheritProperty(state,&vertex,"authored");config=G3::materialConfig(state,true,"authored");
        require(config.mDiffuse==osg::Vec4(0,0,0,.8f)&&config.mAmbient==osg::Vec4(),"Emission-only mode lit as diffuse");
        vertex.mVertexMode=Nif::NiVertexColorProperty::VertexMode::VertMode_SrcIgnore;config=G3::materialConfig(state,true,"authored");
        require(config.mDiffuse==osg::Vec4(.4f,.5f,.6f,.8f),"Ignored color mode incorrectly zeroed lighting");
        material.mEmissive.x()=std::numeric_limits<float>::quiet_NaN();bool invalid=false;try{G3::materialConfig(state,false,"authored");}catch(...){invalid=true;}require(invalid,"Nonfinite emission accepted");
        require(environment.physics->objectCount()==9+environment.instances,"Genuine NifBullet/terrain collision inventory");
        osg::Vec3d terrainEye;for(int i=0;i<1200;++i)terrainEye=environment.physics->move({},1./120);
        const double terrainHeight=std::string(argv[2])=="sloped"?terrainEye.x()/16.:0.;
        require(environment.physics->grounded()&&std::abs(terrainEye.z()-terrainHeight-88)<4,"Original LAND topology does not ground the capsule");
        // Bullet grounds on the actual shared diamond topology, then slides into a wall.
        G3::Physics physics;
        auto floor=std::make_shared<Resource::BulletShape>();floor->mCollisionShape.reset(new btBoxShape(btVector3(1000,1000,8)));
        physics.add(floor,osg::Matrix::translate(-12000,-68000,-8));
        auto visual=std::make_shared<Resource::BulletShape>();visual->mCollisionShape.reset(new btBoxShape(btVector3(100,100,100)));visual->mVisualCollisionType=Resource::VisualCollisionType::Default;
        physics.add(visual,osg::Matrix::identity());visual->mVisualCollisionType=Resource::VisualCollisionType::Camera;physics.add(visual,osg::Matrix::identity());
        require(physics.objectCount()==1&&physics.collisionless==2,"NC/NCC incorrectly block player movement");
        auto wall=std::make_shared<Resource::BulletShape>();wall->mCollisionShape.reset(new btBoxShape(btVector3(1000,8,200)));
        physics.add(wall,osg::Matrix::translate(-12000,-67900,100));physics.start({-12000,-68000,16});
        osg::Vec3d eye;for(int i=0;i<240;++i)eye=physics.move({},1./120);
        require(physics.grounded()&&std::abs(eye.z()-88)<3,"Bullet gravity/grounding failed");
        physics.jump();double maximum=eye.z();
        for(int i=0;i<240;++i){eye=physics.move({},1./120);maximum=std::max(maximum,eye.z());}
        require(maximum>110&&physics.grounded(),"Grounded jump/gravity landing failed");
        for(int i=0;i<360;++i)eye=physics.move({0,180,0},1./120);
        require(eye.y()<-67918&&eye.y()>-68000,"Bullet wall collision failed");
        const auto before=physics.steps;physics.move({},1000);require(physics.steps-before<=G3::Physics::MaxFrameSteps,"Resume time step unbounded");
        bool rejected=false;try{physics.move({},std::numeric_limits<double>::quiet_NaN());}catch(...){rejected=true;}
        require(rejected,"Invalid physics dt accepted");
        // Rendering/collision placement use exactly the same ESM matrix including scale.
        auto rotated=G2::placement(ESM::makeBlankCellRef());(void)rotated;
    }
    std::cout<<"{\"status\":\"PASS\",\"cells\":"<<environment.cells<<",\"terrain_triangles\":"<<environment.terrainTriangles
        <<",\"references\":"<<environment.references<<",\"model_instances\":"<<environment.instances<<",\"model_triangles\":"<<environment.triangles<<",\"model_vertices\":"<<environment.vertices<<",\"model_shapes\":"<<environment.shapes
        <<",\"models\":"<<environment.models.size()<<",\"textures\":"<<environment.textures.size()<<",\"decoded_rgba_bytes\":"<<environment.decodedBytes
        <<",\"collision_objects\":"<<environment.physics->objectCount()<<",\"collisionless_instances\":"<<environment.physics->collisionless
        <<",\"excluded_dynamic_references\":"<<environment.excludedReferences<<",\"excluded_effects\":"<<environment.excludedEffects<<",\"editor_markers\":"<<environment.markers
        <<",\"arrival_grounded\":"<<(arrivalGrounded?"true":"false")<<",\"walking_displacement_units\":"<<walkingDisplacement
        <<",\"physical_acceptance\":\"UNVERIFIED\"}\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
