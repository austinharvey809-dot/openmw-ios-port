#include "Interior.hpp"
#include "Navigation.hpp"
#include <osg/ComputeBoundsVisitor>
#include <iostream>
#include <limits>
#include <stdexcept>
void require(bool b,const char* text){if(!b)throw std::runtime_error(text);}
int main(int argc,char** argv){try{
    require(argc==3||argc==4,"Usage: interior-check directory cell [authored-case]");
    if(argc==4&&(std::string(argv[3])=="image-budget"||std::string(argv[3])=="texture-budget")){
        G2::Resources resources(argv[1]);
        if(std::string(argv[3])=="image-budget")resources.decodedBytes=64u*1024*1024;
        else resources.samplerBytes=128u*1024*1024;
        G2::loadMesh(resources,"Authored/quad.nif");
        throw std::runtime_error("Resource budget not enforced");
    }
    auto env=G2::load(argv[1],argv[2]);osg::ComputeBoundsVisitor bounds;env.scene->accept(bounds);
    require(bounds.getBoundingBox().valid(),"Owned scene invalid after shared reader/VFS release");
    if(argc==4){
        std::string mode=argv[3];require(env.references==(mode=="deleted-reference"?9u:8u),"Reference inventory mismatch");
        require(env.instances==6&&env.models.size()==(mode=="two-models"?2u:1u)&&env.textures.size()==1,"Shared model/texture cache mismatch");
        require(env.samplerCount==1,"Texture objects not shared across model templates");
        require(env.samplerBytes==64,"Unexpected authored texture storage estimate");
        require(env.vertices==24&&env.triangles==12&&env.shapes==6,"Genuine decoded instance counts mismatch");
        require(env.lights.size()==2&&env.markers==1&&env.modelLessLights==1,"Light/marker classification mismatch");
        require(env.lights[0].color.x()==(mode=="negative-light"?-1.f:1.f),"Negative-light sign mismatch");
        if(mode=="attach-light")require((env.lights[0].position-osg::Vec3f(2,3,4)).length()<1e-5,"Genuine NIF light attachment transform mismatch");
        require(env.decodedBytes==64,"DDS cache allocated repeated images");
        require(env.collisionBranches==(mode=="collision"?6u:0u)&&env.particleBranches==(mode=="particles"?6u:0u),"Explicit excluded-branch inventory mismatch");
        const auto* templateNode=env.scene->getChild(0)->asGroup()->getChild(0);
        for(unsigned i=1;i<6;++i)require((env.scene->getChild(i)->asGroup()->getChild(0)==templateNode)==!(mode=="two-models"&&i==1),"Instances do not share the expected owned template");
        ESM::CellRef r=ESM::makeBlankCellRef();r.mScale=2;r.mPos.pos[0]=10;r.mPos.pos[1]=20;r.mPos.pos[2]=30;r.mPos.rot[2]=3.14159265358979323846/2;
        auto point=osg::Vec3d(1,0,0)*G2::placement(r);
        require((point-osg::Vec3d(10,18,30)).length()<1e-5,"ESM negative-axis rotation/scale/translation convention mismatch");
        G2::Navigation nav;nav.start(osg::Vec3d(),0);nav.forward=1;nav.update(10);nav.update(10.05);
        require(nav.eye.y()>8.9&&nav.eye.y()<9.1,"Camera movement mismatch");
        auto before=nav.eye;nav.update(1000);require((nav.eye-before).length()<=9.001,"Resume time step unbounded");
        nav.turn(0,100);require(nav.pitch<=1.4,"Camera pitch not bounded");nav.reset();require(nav.eye.length2()==0,"Reset entry mismatch");
        r.mScale=std::numeric_limits<float>::quiet_NaN();bool rejected=false;try{G2::placement(r);}catch(...){rejected=true;}require(rejected,"Invalid placement accepted");
    }
    std::cout<<"{\"status\":\"PASS\",\"references\":"<<env.references<<",\"instances\":"<<env.instances
        <<",\"vertices\":"<<env.vertices<<",\"triangles\":"<<env.triangles<<",\"shapes\":"<<env.shapes
        <<",\"unique_models\":"<<env.models.size()<<",\"unique_textures\":"<<env.textures.size()
        <<",\"particle_branches_omitted\":"<<env.particleBranches<<",\"physical_acceptance\":\"UNVERIFIED\"}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
