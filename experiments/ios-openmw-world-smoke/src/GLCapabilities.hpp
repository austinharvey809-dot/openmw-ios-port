#pragma once
#include <components/sceneutil/glextensions.hpp>
#include <osg/GraphicsContext>
#include <osg/State>
#include <functional>
#include <stdexcept>
#include <string>

namespace G4 {
using StartupTrace=std::function<void(const std::string&)>;
using CurrentGLContext=std::function<bool()>;

// Probe the actual platform context handle, never a context-dependent GL entry
// point or GraphicsWindowEmbedded::isCurrent() (which assumes an external owner).
inline void requireCurrentGLContext(const CurrentGLContext& current){
    if(!current||!current())
        throw std::runtime_error("G4 startup stage=capabilities: no current GL context");
}

inline osg::State& capabilityState(osg::GraphicsContext* context){
    if(!context||!context->getState())
        throw std::runtime_error("G4 startup stage=capabilities: missing graphics context/state");
    return *context->getState();
}

// OpenMW's operation expects State::initializeExtensionProcs() to have run.
// In the pinned OSG, State::get<GLExtensions>() only returns the stored pointer;
// it does not lazily initialize it. Never pass a null pointer into the observer.
inline void registerGLCapabilities(osg::GraphicsContext* context){
    if(!capabilityState(context).get<osg::GLExtensions>())
        throw std::runtime_error("G4 startup stage=capabilities: OSG extension procedures are uninitialized");
    SceneUtil::GetGLExtensionsOperation operation;
    operation(context);
    if(!SceneUtil::glExtensionsReady())
        throw std::runtime_error("G4 startup stage=capabilities: OpenMW registration did not complete");
}

// Caller owns the genuine current GL context and CapabilityRegistryMutex.
// No dummy capabilities, decoder substitutes or extension strings are injected.
inline void initializeGLCapabilities(osg::GraphicsContext* context,const CurrentGLContext& current,const StartupTrace& trace={}){
    auto& state=capabilityState(context);
    requireCurrentGLContext(current);
    if(!glGetString(GL_VERSION))
        throw std::runtime_error("G4 startup stage=capabilities: current context has no GL version");
    if(trace)trace("osg.extension-procs.begin");
    state.initializeExtensionProcs();
    if(trace)trace("osg.extension-procs.complete");
    if(trace)trace("openmw.capabilities.begin");
    registerGLCapabilities(context);
    if(trace)trace("openmw.capabilities.complete");
}
}
