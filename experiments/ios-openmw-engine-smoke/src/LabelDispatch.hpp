#pragma once
#include <osg/GLExtensions>
#include <osg/State>
#include <cstdio>
#include <stdexcept>
#include <string>

namespace G5 {
enum class LabelAPI { None, Core, KHR };
inline LabelAPI labelAPI(bool es,int major,int minor,bool khr) {
    if(major<1 || minor<0) throw std::runtime_error("G5 invalid actual GL version");
    if(es) return major>3 || (major==3 && minor>=2) ? LabelAPI::Core : khr ? LabelAPI::KHR : LabelAPI::None;
    return major>4 || (major==4 && minor>=3) ? LabelAPI::Core : khr ? LabelAPI::KHR : LabelAPI::None;
}
template<class F> F selectLabel(LabelAPI api,F core,F extension) {
    if(api==LabelAPI::None) return nullptr;
    F selected=api==LabelAPI::KHR?extension:core;
    if(!selected) throw std::runtime_error("G5 advertised object-label API lacks its entry point");
    return selected;
}

// Call with a genuine current context, AFTER State::initializeExtensionProcs(),
// under the accepted capability-registry gate and before compiling resources.
// ANGLE's exported core symbol exists on ES3.0 but validates ES3.2; KHR is a
// different entry point. Do not alter debug message filters or the callback.
inline std::string configureLabels(osg::State& state) {
    auto* extensions=state.get<osg::GLExtensions>();
    if(!extensions) throw std::runtime_error("G5 labels require initialized OSG capabilities");
    const auto* raw=glGetString(GL_VERSION);
    if(!raw) throw std::runtime_error("G5 labels require an actual current GL version");
    const std::string version(reinterpret_cast<const char*>(raw));
    const bool es=version.starts_with("OpenGL ES ");int major=0,minor=0;
    if(std::sscanf(version.c_str()+(es?10:0),"%d.%d",&major,&minor)!=2)
        throw std::runtime_error("G5 unrecognized actual GL version: "+version);
    const bool khr=osg::isGLExtensionSupported(state.getContextID(),"GL_KHR_debug");
    const auto api=labelAPI(es,major,minor,khr);
    using Function=decltype(extensions->glObjectLabel);
    const auto entry=reinterpret_cast<Function>(osg::getGLExtensionFuncPtr(es?"glObjectLabelKHR":"glObjectLabel"));
    extensions->glObjectLabel=selectLabel(api,extensions->glObjectLabel,entry);
    return api==LabelAPI::KHR?"KHR":api==LabelAPI::Core?"core":"unsupported";
}
}
