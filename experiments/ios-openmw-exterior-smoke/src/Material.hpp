#pragma once
#include "StaticProperties.hpp"
#include <components/sceneutil/material.hpp>
namespace G3 {
using G1D::StaticProperties;
inline void inheritProperty(StaticProperties& state,const Nif::NiProperty* property,const std::string& node){
    if(const auto* p=dynamic_cast<const Nif::NiVertexColorProperty*>(property)){
        G1D::propertyCheck(p->mController.empty(),p,node,"Animated property unsupported");
        G1D::propertyCheck(unsigned(p->mVertexMode)<=2,p,node,"Invalid vertex color mode");
        G1D::propertyCheck(unsigned(p->mLightingMode)<=1,p,node,"Invalid lighting mode");state.vertex=p;
    }else G1D::inheritProperty(state,property,node);
}
// Same defaults, vertex mode and emission-only branch as genuine NifOsg::Loader.
inline SceneUtil::MaterialConfig materialConfig(const StaticProperties& state,bool hasColors,const std::string& node){
    SceneUtil::MaterialConfig config;
    config.mVertexColorMode=hasColors?SceneUtil::VertexColorModes::AmbientAndDiffuse:SceneUtil::VertexColorModes::None;
    if(const auto* p=state.material){
        for(const auto* channel:{&p->mAmbient,&p->mDiffuse,&p->mSpecular,&p->mEmissive})for(unsigned i=0;i<3;++i)
            G1D::propertyCheck(std::isfinite((*channel)[i])&&(*channel)[i]>=0&&(*channel)[i]<=1,p,node,"Invalid material channel");
        G1D::propertyCheck(std::isfinite(p->mAlpha)&&p->mAlpha>=0&&p->mAlpha<=1&&std::isfinite(p->mEmissiveMult)&&p->mEmissiveMult>=0&&std::isfinite(p->mGlossiness),p,node,"Invalid material alpha/emission multiplier/glossiness");
        config.mDiffuse=osg::Vec4(p->mDiffuse,p->mAlpha);config.mAmbient=osg::Vec4(p->mAmbient,1);
        config.mEmission=osg::Vec4(p->mEmissive,1);config.mEmissiveMult=p->mEmissiveMult;
    }
    if(const auto* p=state.vertex){
        using V=Nif::NiVertexColorProperty::VertexMode;using L=Nif::NiVertexColorProperty::LightMode;
        if(p->mVertexMode==V::VertMode_SrcIgnore)config.mVertexColorMode=SceneUtil::VertexColorModes::None;
        else if(p->mVertexMode==V::VertMode_SrcEmissive)config.mVertexColorMode=SceneUtil::VertexColorModes::Emission;
        else if(p->mLightingMode==L::LightMode_Emissive){
            config.mVertexColorMode=SceneUtil::VertexColorModes::None;
            config.mDiffuse=osg::Vec4(0,0,0,config.mDiffuse.a());config.mAmbient=osg::Vec4();
        }else config.mVertexColorMode=SceneUtil::VertexColorModes::AmbientAndDiffuse;
    }
    if(!hasColors){
        if(config.mVertexColorMode==SceneUtil::VertexColorModes::AmbientAndDiffuse){config.mDiffuse=osg::Vec4(1,1,1,1);config.mAmbient=osg::Vec4(1,1,1,1);}
        if(config.mVertexColorMode==SceneUtil::VertexColorModes::Emission)config.mEmission=osg::Vec4(1,1,1,1);
        config.mVertexColorMode=SceneUtil::VertexColorModes::None;
    }
    // VER_MW specular is disabled in NifOsg::Loader irrespective of NiSpecularProperty.
    return config;
}
inline void applyMaterial(osg::StateSet& state,const StaticProperties& properties,bool hasColors,const std::string& node){
    osg::ref_ptr<SceneUtil::Material> material=new SceneUtil::Material(materialConfig(properties,hasColors,node));material->setStateSet(&state);
}
}
