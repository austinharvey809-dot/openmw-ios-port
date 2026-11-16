#pragma once
#include "GLCapabilities.hpp"
#include <osgViewer/GraphicsWindow>
#include <cstdio>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#elif defined(__APPLE__)
#include <TargetConditionals.h>
#if TARGET_OS_IPHONE
#error This contextless regression is a host test, not an iPhone renderer
#endif
#include <OpenGL/OpenGL.h>
#elif defined(__linux__)
#include <GL/glx.h>
#else
#error Supply a genuine native context-handle query for this host platform
#endif

namespace G4Test {
inline bool hostContextCurrent(){
#ifdef _WIN32
    return wglGetCurrentContext()!=nullptr;
#elif defined(__APPLE__)
    return CGLGetCurrentContext()!=nullptr;
#else
    return glXGetCurrentContext()!=nullptr;
#endif
}
inline void startupStage(const char* stage){
    std::fprintf(stderr,"G4 startup-test %s\n",stage);std::fflush(stderr);
}
inline unsigned startupChecks(){
    unsigned checks=0;
    const auto require=[&](bool ok,const char* message){
        if(!ok)throw std::runtime_error(std::string("G4 startup-test: ")+message);
        ++checks;
    };
    const auto reject=[&](const auto& action,const char* expected){
        try{action();}catch(const std::exception& error){
            require(std::string(error.what()).find(expected)!=std::string::npos,"Wrong startup rejection");return;
        }
        throw std::runtime_error(std::string("G4 startup-test: missing rejection: ")+expected);
    };
    startupStage("native-context-query.begin");
    require(!hostContextCurrent(),"Headless test unexpectedly owns a native GL context");
    startupStage("native-context-query.complete");
    require(!SceneUtil::glExtensionsReady(),"Fresh process already has OpenMW capabilities");
    unsigned previousID=0;
    for(unsigned iteration=0;iteration<2;++iteration){
        startupStage("embedded-create.begin");
        osg::ref_ptr<osgViewer::GraphicsWindowEmbedded> window=new osgViewer::GraphicsWindowEmbedded(0,0,1,1);
        startupStage("embedded-create.complete");
        require(window->getState()!=nullptr,"Embedded window has no genuine state");
        require(window->getState()->get<osg::GLExtensions>()==nullptr,"Fresh extensions unexpectedly initialized");
        if(iteration)require(window->getState()->getContextID()==previousID,"Context ID not retired/reused");
        previousID=window->getState()->getContextID();
        startupStage("guard-rejections.begin");
        reject([&]{G4::registerGLCapabilities(window);},"extension procedures are uninitialized");
        reject([&]{G4::registerGLCapabilities(nullptr);},"missing graphics context/state");
        std::vector<std::string> phases;unsigned queries=0;
        reject([&]{G4::initializeGLCapabilities(window,[&]{++queries;return hostContextCurrent();},
            [&](const auto& stage){phases.push_back(stage);});},"no current GL context");
        require(queries==1,"Native context probe was not called exactly once");
        reject([&]{G4::initializeGLCapabilities(window,{});},"no current GL context");
        reject([&]{G4::initializeGLCapabilities(nullptr,G4Test::hostContextCurrent);},"missing graphics context/state");
        require(phases.empty(),"GL initialization started without a genuine current context");
        require(!SceneUtil::glExtensionsReady(),"Rejected startup published fake capabilities");
        require(window->getState()->get<osg::GLExtensions>()==nullptr,"Rejection mutated extension ownership");
        startupStage("guard-rejections.complete");
        // The wrapper assumes an EXTERNAL context exists. It must not be made
        // current/realized to clean up a test which never created that context.
        // This is the pinned base destructor's own contextless close(false) path.
        startupStage("embedded-close.begin");
        window->close(false);
        require(window->getState()==nullptr,"Contextless close did not retire state");
        window=nullptr;
        startupStage("embedded-destroy.complete");
        require(!SceneUtil::glExtensionsReady(),"Destruction published capabilities");
    }
    startupStage("complete");return checks;
}
}
