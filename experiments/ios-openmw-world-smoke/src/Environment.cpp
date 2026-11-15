#include "World.hpp"
#include "G4Defaults.hpp"
#include <components/fallback/fallback.hpp>
#include <components/sceneutil/fog.hpp>
#include <components/sceneutil/lightmanager.hpp>
#include <components/sceneutil/util.hpp>
#include <components/sceneutil/texmat.hpp>
#include <components/sceneutil/material.hpp>
#include <components/sceneutil/depth.hpp>
#include <osg/Uniform>
#include <mutex>
#include <cmath>
#include <stdexcept>

namespace G4 {
void initializeDefaults(){
    static std::once_flag once;std::call_once(once,[]{Fallback::Map::init(G4Defaults::Values);});
}
void configureEnvironment(Area& area,const ESM::Cell* interior){
    initializeDefaults();
    auto* lights=dynamic_cast<SceneUtil::LightManager*>(area.scene.get());
    if(!lights)throw std::logic_error("G4 scene lacks upstream LightManager");
    auto sun=std::make_shared<SceneUtil::Light>();
    const auto ambient=interior?SceneUtil::colourFromRGB(interior->mAmbi.mAmbient):Fallback::Map::getColour("Weather_Clear_Ambient_Day_Color");
    const auto diffuse=interior?SceneUtil::colourFromRGB(interior->mAmbi.mSunlight):Fallback::Map::getColour("Weather_Clear_Sun_Day_Color");
    const auto fogColor=interior?SceneUtil::colourFromRGB(interior->mAmbi.mFog):Fallback::Map::getColour("Weather_Clear_Fog_Day_Color");
    const float depth=interior?interior->mAmbi.mFogDensity:Fallback::Map::getFloat("Weather_Clear_Land_Fog_Day_Depth");
    if(!std::isfinite(depth)||depth<0||depth>1)throw std::runtime_error("G4 invalid original fog density");
    sun->setAmbient(ambient);sun->setDiffuse(diffuse);sun->setSpecular(diffuse);
    // Explicit deterministic clear-day comparison direction; no ephemeris claim.
    sun->setPosition({.3f,-.4f,.8660254f,0});lights->setSunlight(std::move(sun));
    auto* state=area.scene->getOrCreateStateSet();
    state->setMode(GL_CULL_FACE,osg::StateAttribute::ON);
    state->setAttributeAndModes(new SceneUtil::AutoDepth,osg::StateAttribute::ON);
    // RenderingManager supplies this inherited default: the NIF loader omits
    // redundant default materials, so missing root uniforms would shade black.
    osg::ref_ptr<SceneUtil::Material> defaultMaterial=new SceneUtil::Material;
    defaultMaterial->updateStateSet(state);
    state->setAttribute(defaultMaterial);
    SceneUtil::initTexMatForStateSet(*state);
    SceneUtil::setFogColor(*state,fogColor);SceneUtil::setFogStart(*state,8192*(1-depth));
    SceneUtil::setFogEnd(*state,depth==0?1e20f:8192);SceneUtil::setFogDepth(*state,-1);
    SceneUtil::setUnderwaterFogColor(*state,fogColor);SceneUtil::setUnderwaterFogStart(*state,0);SceneUtil::setUnderwaterFogEnd(*state,8192);
    state->addUniform(new osg::Uniform("waterEnabled",false));state->addUniform(new osg::Uniform("waterSurface",false));
    state->addUniform(new osg::Uniform("isReflection",false));state->addUniform(new osg::Uniform("waterHeight",0.f));
    state->addUniform(new osg::Uniform("alpha",1.f));state->addUniform(new osg::Uniform("actorFade",1.f));
    state->addUniform(new osg::Uniform("near",2.f));state->addUniform(new osg::Uniform("far",8192.f));
}
}
