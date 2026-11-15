#pragma once
#include "Session.hpp"
#include "SceneAudit.hpp"
#include "Notifications.hpp"
#include "GLCapabilities.hpp"
#include <components/fallback/fallback.hpp>
#include <components/misc/constants.hpp>
#include <components/sceneutil/glextensions.hpp>
#include <osg/GLExtensions>
#include <osg/AlphaFunc>
#include <osg/Notify>
#include <osg/State>
#include <osg/Uniform>
#include <osg/Version>
#include <osgViewer/GraphicsWindow>
#include <osgViewer/Viewer>
#include <chrono>
#include <cstdlib>
#include <functional>

class OSGScene {
    G4::NotificationScope notifications; // Last destroyed, after workers/OSG.
    osg::ref_ptr<osgViewer::GraphicsWindowEmbedded> window;
    osg::ref_ptr<osgViewer::Viewer> viewer;
    std::shared_ptr<G4::Session> owned;
    unsigned compiledLoad=0;
    double previousFrame=-1,simulationTime=0;
    static G4::StartupTrace beginNotifications(G4::StartupTrace callback){
        if(callback)callback("G4 startup osg.notifications.begin");
        return callback;
    }
    void acceptArea(const G4::Area& area){
        G4::SceneAudit audit;area.scene->accept(audit);
        if(audit.programs.empty())throw std::runtime_error("G4 area contains no genuine render programs");
        for(const auto* program:audit.programs){
            program->compileGLObjects(*window->getState());
            const auto* linked=program->getPCP(*window->getState());std::string message;
            if(linked)linked->getInfoLog(message);notifications.get()->write("G4 upstream GLES3 program: "+message);
            if(!linked||!linked->isLinked())throw std::runtime_error("G4 genuine upstream shader link failure: "+message);
        }
    }
public:
    unsigned long long frames=0;
    double traversalWallMs=0;
    bool shaderLinked=false;
    unsigned long long backgroundBusyFrames=0;
    unsigned shaderAcceptedLoad()const{return shaderLinked?compiledLoad:0;}
    unsigned contextID()const{return window->getState()->getContextID();}
    unsigned warnings()const{return notifications.get()->warnings();}
    unsigned loggingErrors()const{return notifications.get()->errors();}
    bool ready()const{return bool(owned);}
    G4::Session& session(){if(!owned)throw std::runtime_error("G4 world is still loading");return *owned;}
    G4::Traversal& navigation(){return session().navigation;}
    void suspend(){previousFrame=-1;if(owned)owned->suspend();}
    bool grounded()const{return owned&&owned->area().physics->grounded();}
    unsigned long long physicsSteps()const{return owned?owned->physicsSteps():0;}
    double droppedPhysicsSeconds()const{return owned?owned->droppedPhysicsSeconds():0;}
    explicit OSGScene(std::function<void(const std::string&)> callback):notifications(beginNotifications(std::move(callback))){
        const auto checkpoint=[this](const std::string& stage){notifications.get()->write("G4 startup "+stage);};
        checkpoint("osg.notifications.complete");
        std::lock_guard registry(G4::CapabilityRegistryMutex);
        checkpoint("osg.entry-points.begin");
        for(const char* name:{"glCreateShader","glBindVertexArray","glDrawElements"})
            if(!osg::getGLExtensionFuncPtr(name))throw std::runtime_error(std::string("ANGLE resolver missing ")+name);
        checkpoint("osg.entry-points.complete");
        checkpoint("osg.embedded-window.begin");
        window=new osgViewer::GraphicsWindowEmbedded(0,0,1,1);
        checkpoint("osg.embedded-window.complete");
        auto* state=window->getState();state->setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE);
        state->setUseModelViewAndProjectionUniforms(true);state->setUseVertexAttributeAliasing(true);
        state->resetVertexAttributeAlias(false);
        // Alpha comparison is implemented by the genuine ShaderVisitor/GLSL.
        // GLES3 has no fixed-function GL_ALPHA_TEST capability to enable/disable.
        state->setModeValidity(GL_ALPHA_TEST,false);
        // Canonical upstream order: initialize real GL capabilities before the
        // background ImageManager is allowed to choose DDS upload/decompression.
        // This is an app environment option, not a replacement decoder or fake
        // extension. Actual unsupported S3TC is decompressed by ImageManager.
#ifdef _WIN32
        _putenv_s("OPENMW_DECOMPRESS_TEXTURES","1");
#else
        setenv("OPENMW_DECOMPRESS_TEXTURES","1",1);
#endif
        G4::initializeGLCapabilities(window,checkpoint);
        checkpoint("osg.viewer.begin");
        viewer=new osgViewer::Viewer;viewer->setThreadingModel(osgViewer::Viewer::SingleThreaded);
        viewer->setReleaseContextAtEndOfFrameHint(false);viewer->setCameraManipulator(nullptr);
        viewer->setLightingMode(osg::View::NO_LIGHT); // SceneUtil::LightManager owns lighting.
        viewer->getCamera()->setGraphicsContext(window);viewer->getCamera()->setName(Constants::SceneCamera);
        viewer->getCamera()->setClearMask(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        viewer->getCamera()->setComputeNearFarMode(osg::CullSettings::DO_NOT_COMPUTE_NEAR_FAR);
        checkpoint("osg.viewer.complete");
    }
    void attach(std::shared_ptr<G4::Session> session){
        if(!session)throw std::runtime_error("G4 missing prepared world");
        owned=std::move(session);viewer->setSceneData(owned->scene());shaderLinked=false;compiledLoad=0;
        viewer->getCamera()->setClearColor(Fallback::Map::getColour("Weather_Clear_Sky_Day_Color"));
    }
    void frame(double time,int width,int height){
        if(width<1||height<1)return;
        if(!owned){glClearColor(.05f,.05f,.08f,1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);return;}
        // The pinned OSG NotifyStreamBuffer is process-global. Serialize OSG
        // work, not just its handler. Do not block UIKit waiting for CPU loads:
        // render a clear-only loading frame while the worker owns the gate.
        std::unique_lock registry(G4::CapabilityRegistryMutex,std::try_to_lock);
        if(!registry.owns_lock()){
            ++backgroundBusyFrames;glClearColor(.05f,.05f,.08f,1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);return;
        }
        bool acceptedCandidate=false;
        if(frames==0)notifications.get()->write("G4 startup scene.first-frame.begin");
        const auto* stamp=viewer->getFrameStamp();
        owned->update(time,[&](const G4::Area& candidate){
            const bool previous=shaderLinked;shaderLinked=false;
            try{acceptArea(candidate);acceptedCandidate=true;}
            catch(...){shaderLinked=previous&&compiledLoad==owned->loads;throw;}
        },stamp?stamp->getReferenceTime():0);
        if(acceptedCandidate){compiledLoad=owned->loads;shaderLinked=true;}
        if(compiledLoad!=owned->loads){
            if(frames==0)notifications.get()->write("G4 startup scene.initial-programs.begin");
            shaderLinked=false;acceptArea(owned->area());
            shaderLinked=true;compiledLoad=owned->loads;
            if(frames==0)notifications.get()->write("G4 startup scene.initial-programs.complete");
        }
        window->resized(0,0,width,height);window->getEventQueue()->windowResize(0,0,width,height);
        auto* camera=viewer->getCamera();camera->setViewport(0,0,width,height);
        camera->setProjectionMatrixAsPerspective(65.,double(width)/height,2.,8192.);
        const auto& nav=owned->navigation;
        camera->setViewMatrixAsLookAt(nav.eye,nav.eye+nav.direction(),osg::Vec3d(0,0,1));
        auto* state=owned->scene()->getOrCreateStateSet();
        state->getOrCreateUniform("projectionMatrix",osg::Uniform::FLOAT_MAT4)->set(osg::Matrixf(camera->getProjectionMatrix()));
        state->getOrCreateUniform("osg_ViewMatrixInverse",osg::Uniform::FLOAT_MAT4)->set(osg::Matrixf::inverse(osg::Matrixf(camera->getViewMatrix())));
        state->getOrCreateUniform("screenRes",osg::Uniform::FLOAT_VEC2)->set(osg::Vec2f(width,height));
        // Genuine NIF controllers consume float simulation time. Device uptime
        // is neither a suitable animation epoch nor background catch-up time.
        if(previousFrame>=0)simulationTime+=std::clamp(time-previousFrame,0.,.25);
        previousFrame=time;
        const auto begin=std::chrono::steady_clock::now();viewer->frame(simulationTime);
        traversalWallMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();++frames;
        if(frames==1)notifications.get()->write("G4 startup scene.first-frame.complete");
        if(frames==5)window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_FRAME);
    }
    ~OSGScene(){
        if(owned)owned->shutdown(); // Never join a worker while holding its gate.
        std::lock_guard registry(G4::CapabilityRegistryMutex);
        if(viewer){viewer->setDone(true);viewer->stopThreading();}
        viewer=nullptr;owned.reset();window=nullptr;
    }
};
