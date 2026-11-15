#pragma once
#include <components/terrain/compositemaprenderer.hpp>
#include <components/terrain/terraindrawable.hpp>
#include <osg/Drawable>
#include <osg/NodeVisitor>
#include <osg/Program>
#include <osg/Shader>
#include <osg/StateSet>
#include <osg/Texture>
#include <filesystem>
#include <fstream>
#include <set>
#include <stdexcept>

namespace G4 {
// CPU validation of the actual upstream-generated program inventory. This is
// neither GPU compilation nor proof that a draw reached the physical display.
struct SceneAudit : osg::NodeVisitor {
    std::set<const osg::Program*> programs;
    unsigned geometry=0,terrainPasses=0;
    bool inheritedProgram=false;
    const osg::Image* warningImage=nullptr;
    explicit SceneAudit(const osg::Image* warning=nullptr):NodeVisitor(TRAVERSE_ALL_CHILDREN),warningImage(warning){}
    void state(osg::StateSet* state){
        if(!state)return;
        if(warningImage)for(unsigned unit=0;unit<state->getTextureAttributeList().size();++unit){
            const auto* texture=dynamic_cast<const osg::Texture*>(state->getTextureAttribute(unit,osg::StateAttribute::TEXTURE));
            if(texture)for(unsigned i=0;i<texture->getNumImages();++i)
                if(!texture->getImage(i)||texture->getImage(i)==warningImage||!texture->getImage(i)->data())
                    throw std::runtime_error("G4 terrain/model image fallback rejected");
        }
        auto* program=dynamic_cast<const osg::Program*>(state->getAttribute(osg::StateAttribute::PROGRAM));
        if(!program)return;
        unsigned vertex=0,fragment=0;
        for(unsigned i=0;i<program->getNumShaders();++i){
            const auto* shader=program->getShader(i);
            if(shader->getShaderSource().empty() || !shader->getShaderSource().starts_with("#version 300 es"))
                throw std::runtime_error("G4 missing/non-GLES3 upstream shader");
            if(shader->getType()==osg::Shader::VERTEX)++vertex;
            else if(shader->getType()==osg::Shader::FRAGMENT)++fragment;
            else throw std::runtime_error("G4 unsupported shader stage");
        }
        if(vertex!=1||fragment!=1)throw std::runtime_error("G4 requires exactly one GLES3 shader per stage");
        programs.insert(program);
    }
    bool hasProgram(osg::StateSet* value)const{return value&&value->getAttribute(osg::StateAttribute::PROGRAM);}
    void apply(osg::Node& node)override{
        const bool previous=inheritedProgram;inheritedProgram|=hasProgram(node.getStateSet());
        state(node.getStateSet());traverse(node);inheritedProgram=previous;
    }
    void apply(osg::Drawable& drawable)override{
        state(drawable.getStateSet());
        if(drawable.asGeometry())++geometry;
        if(auto* terrain=dynamic_cast<Terrain::TerrainDrawable*>(&drawable)){
            if(terrain->getPasses().empty())throw std::runtime_error("G4 terrain has no render passes");
            for(const auto& pass:terrain->getPasses()){
                if(!hasProgram(pass))throw std::runtime_error("G4 terrain pass lacks genuine shader");
                state(pass);++terrainPasses;
            }
        }else if(!dynamic_cast<Terrain::CompositeMapRenderer*>(&drawable)&&!inheritedProgram&&!hasProgram(drawable.getStateSet()))
            throw std::runtime_error("G4 drawable lacks genuine shader: "+std::string(drawable.libraryName())+"::"+drawable.className()+" node="+drawable.getName());
    }
    void dump(const std::filesystem::path& directory)const{
        std::filesystem::create_directories(directory);unsigned number=0;
        for(const auto* program:programs){
            for(unsigned i=0;i<program->getNumShaders();++i){
                const auto* shader=program->getShader(i);
                std::ofstream file(directory/(std::to_string(number)+(shader->getType()==osg::Shader::VERTEX?".vert":".frag")));
                file<<shader->getShaderSource();if(!file)throw std::runtime_error("G4 shader evidence write failed");
            }
            ++number;
        }
    }
};
}
