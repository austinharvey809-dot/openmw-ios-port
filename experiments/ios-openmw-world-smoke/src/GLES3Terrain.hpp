#pragma once
#include <components/terrain/compositemaprenderer.hpp>
#include <components/terrain/terraindrawable.hpp>
#include <osg/Capability>
#include <osg/NodeVisitor>
#include <osg/StateSet>
#include <stdexcept>

namespace G4 {
// The explicit G4 profile has one color attachment and disableNormals=1.
// Upstream terrain still adds indexed blending for its unused normals RT.
// Preserve color blending, depth, programs, uniforms and all texture state;
// omit only that inert second-attachment operation, on private pass copies.
struct GLES3Terrain : osg::NodeVisitor {
    unsigned omittedNormalsStates=0;
    GLES3Terrain():NodeVisitor(TRAVERSE_ALL_CHILDREN){}
    void apply(osg::Drawable& drawable)override{
        auto* terrain=dynamic_cast<Terrain::TerrainDrawable*>(&drawable);if(!terrain)return;
        auto passes=terrain->getPasses();
        for(auto& pass:passes){
            osg::ref_ptr<osg::StateSet> local;
            for(const auto& [key,value]:pass->getAttributeList()){
                const auto* indexed=dynamic_cast<const osg::Capabilityi*>(value.first.get());
                if(!indexed)continue;
                if(!dynamic_cast<const osg::Enablei*>(indexed)||indexed->getCapability()!=GL_BLEND||indexed->getIndex()!=1)
                    throw std::runtime_error("G4 unsupported indexed terrain capability");
                if(!local)local=new osg::StateSet(*pass,osg::CopyOp::SHALLOW_COPY);
                local->removeAttribute(key.first,key.second);++omittedNormalsStates;
            }
            if(local)pass=std::move(local);
        }
        terrain->setPasses(passes);
    }
};
}
