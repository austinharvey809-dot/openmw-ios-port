#pragma once
#include "Exterior.hpp"
#include "Traversal.hpp"
#include "Material.hpp"
#include "MaterialShader.hpp"
#include <osg/ComputeBoundsVisitor>
#include <osg/Depth>
#include <osg/GLExtensions>
#include <osg/Notify>
#include <osg/Program>
#include <osg/Shader>
#include <osg/State>
#include <osg/Version>
#include <osg/Vec3d>
#include <osg/Uniform>
#include <osgViewer/GraphicsWindow>
#include <osgViewer/Viewer>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <stdexcept>
#include <utility>

// Defined in the Objective-C++ application; validates bundle provenance and genuine parsing.
G3::Environment LoadGeometry();

class SceneLog : public osg::NotifyHandler {
public:
    std::function<void(const std::string&)> write;
    unsigned warnings = 0;
    explicit SceneLog(std::function<void(const std::string&)> callback) : write(std::move(callback)) {}
    void notify(osg::NotifySeverity level, const char* message) override {
        if (level <= osg::WARN) ++warnings;
        write("OSG[" + std::to_string(level) + "] " + message);
    }
};

class OSGScene {
    osg::ref_ptr<osgViewer::GraphicsWindowEmbedded> window;
    osg::ref_ptr<osgViewer::Viewer> viewer;
    osg::ref_ptr<osg::Program> program;
    osg::ref_ptr<SceneLog> log;
    osg::ref_ptr<osg::NotifyHandler> previousLog;
    G3::Environment owned;
    osg::ref_ptr<osg::Uniform> lightPositions;
    osg::Vec3d center;
    double radius = 0;
    int width = 0, height = 0;
public:
    G3::Traversal navigation;
    unsigned long long frames = 0;
    double traversalWallMs = 0;
    bool shaderLinked = false;
    unsigned contextID() const { return window->getState()->getContextID(); }
    unsigned warnings() const { return log->warnings; }
    bool grounded() const{return owned.physics->grounded();}
    unsigned long long physicsSteps() const{return owned.physics->steps;}
    double droppedPhysicsSeconds() const{return owned.physics->droppedSeconds;}
    explicit OSGScene(std::function<void(const std::string&)> callback) {
        owned = LoadGeometry(); // Actual decoded arrays only; failure cannot fall back to a mesh.
        navigation.attach(owned.physics,owned.entry,owned.entryYaw);
        osg::ComputeBoundsVisitor bounds; owned.scene->accept(bounds); const auto bound = bounds.getBoundingBox();
        if (!bound.valid()) throw std::runtime_error("Invalid decoded geometry bound");
        center = osg::Vec3d(bound.center());
        radius = osg::Vec3d(bound.xMax() - bound.xMin(), bound.yMax() - bound.yMin(),
            bound.zMax() - bound.zMin()).length() * .5;
        if (!std::isfinite(radius) || radius <= 0) throw std::runtime_error("Invalid decoded geometry extent");
        previousLog = osg::getNotifyHandler();
        log = new SceneLog(std::move(callback));
        osg::setNotifyHandler(log.get());
        osg::setNotifyLevel(osg::INFO);
        try {
            for (const char* name : {"glCreateShader", "glBindVertexArray", "glDrawElements"})
                if (!osg::getGLExtensionFuncPtr(name)) throw std::runtime_error(std::string("ANGLE resolver missing ") + name);
            window = new osgViewer::GraphicsWindowEmbedded(0, 0, 1, 1);
            window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE);
            window->getState()->setUseModelViewAndProjectionUniforms(true);
            window->getState()->setUseVertexAttributeAliasing(true);
            window->getState()->resetVertexAttributeAlias(false);
            viewer = new osgViewer::Viewer;
            viewer->setThreadingModel(osgViewer::Viewer::SingleThreaded);
            viewer->setReleaseContextAtEndOfFrameHint(false);
            viewer->setCameraManipulator(nullptr);
            viewer->getCamera()->setGraphicsContext(window.get());
            viewer->getCamera()->setClearMask(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
            viewer->getCamera()->setClearColor(osg::Vec4(.45f, .62f, .78f, 1));
            program = new osg::Program;
            program->addShader(new osg::Shader(osg::Shader::VERTEX, R"(#version 300 es
precision highp float;
in vec4 osg_Vertex;
in vec4 osg_Color;
in vec3 osg_Normal;
in vec2 nifUV;
in vec2 terrainUV;
uniform mat4 osg_ModelViewProjectionMatrix;
uniform mat4 osg_ModelViewMatrix;
uniform mat3 osg_NormalMatrix;
out vec4 color;
out vec2 uv;
out vec2 layerUV;
out vec3 eyePosition;
out vec3 eyeNormal;
void main() {
    gl_Position=osg_ModelViewProjectionMatrix*osg_Vertex;
    eyePosition=(osg_ModelViewMatrix*osg_Vertex).xyz;
    eyeNormal=osg_NormalMatrix*osg_Normal;
    color=osg_Color; uv=nifUV; layerUV=terrainUV;
}
)"));
            program->addShader(new osg::Shader(osg::Shader::FRAGMENT, std::string("#version 300 es\nprecision highp float;\n")+G3Shader::Material+R"(
uniform Material material;
in vec4 color;
in vec2 uv;
in vec2 layerUV;
in vec3 eyePosition;
in vec3 eyeNormal;
uniform sampler2D baseTexture;
uniform vec3 ambientLight;
uniform vec3 sunDirection;
uniform int terrainLayer;
uniform sampler2D blendTexture;
uniform int lightCount;
uniform vec3 lightPosition[8];
uniform vec3 lightColor[8];
uniform float lightRadius[8];
uniform int alphaTestMode;
uniform float alphaThreshold;
out vec4 result;
void main() {
    vec4 diffuse=getDiffuseColor(material,color);
    result=texture(baseTexture, uv);result.a*=diffuse.a;
    float a=result.a;
    bool pass=alphaTestMode==0 || (alphaTestMode==1 && a<alphaThreshold)
        || (alphaTestMode==2 && a==alphaThreshold) || (alphaTestMode==3 && a<=alphaThreshold)
        || (alphaTestMode==4 && a>alphaThreshold) || (alphaTestMode==5 && a!=alphaThreshold)
        || (alphaTestMode==6 && a>=alphaThreshold);
    if (!pass) discard; // mode 7 is NEVER; test final texture * color alpha.
    vec3 illumination=vec3(0);
    vec3 normal=normalize(eyeNormal);
    illumination+=vec3(.65)*max(0.0,dot(normal,normalize(sunDirection)));
    for(int i=0;i<8;++i) {
        if(i>=lightCount) break;
        vec3 delta=lightPosition[i]-eyePosition;
        float distanceToLight=length(delta);
        float attenuation=max(0.0,1.0-distanceToLight/lightRadius[i]);
        illumination+=lightColor[i]*max(0.0,dot(normal,delta/max(distanceToLight,0.001)))
            *attenuation*attenuation;
    }
    result.rgb*=max(diffuse.rgb*illumination+getAmbientColor(material,color).rgb*ambientLight+getEmissionColor(material,color).rgb*material.emissiveMult,vec3(0));
    if(terrainLayer!=0){result.rgb*=texture(blendTexture,layerUV).r;result.a=1.0;} // genuine negative lights subtract illumination
}
)"));
            program->addBindAttribLocation("osg_Vertex", 0);
            program->addBindAttribLocation("osg_Color", 3);
            program->addBindAttribLocation("osg_Normal", 2);
            program->addBindAttribLocation("nifUV", 6);
            program->addBindAttribLocation("terrainUV", 7);
            // Colors, UVs and Texture2D are owned copies of genuinely decoded records.
            auto* state = owned.scene->getOrCreateStateSet();
            SceneUtil::MaterialConfig defaults;defaults.mVertexColorMode=SceneUtil::VertexColorModes::AmbientAndDiffuse;
            osg::ref_ptr<SceneUtil::Material> rootMaterial=new SceneUtil::Material(defaults);rootMaterial->setStateSet(state);
            state->setAttributeAndModes(program.get(), osg::StateAttribute::ON);
            state->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
            state->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
            state->addUniform(new osg::Uniform("ambientLight",owned.ambient));
            state->addUniform(new osg::Uniform("terrainLayer",0));
            state->addUniform(new osg::Uniform("blendTexture",1));
            state->addUniform(new osg::Uniform("sunDirection",osg::Vec3f(0,0,1)));
            state->addUniform(new osg::Uniform("lightCount",int(owned.lights.size())));
            lightPositions=new osg::Uniform(osg::Uniform::FLOAT_VEC3,"lightPosition",8);
            osg::ref_ptr<osg::Uniform> colors=new osg::Uniform(osg::Uniform::FLOAT_VEC3,"lightColor",8);
            osg::ref_ptr<osg::Uniform> radii=new osg::Uniform(osg::Uniform::FLOAT,"lightRadius",8);
            for(unsigned i=0;i<8;++i){
                colors->setElement(i,i<owned.lights.size()?owned.lights[i].color:osg::Vec3f());
                radii->setElement(i,i<owned.lights.size()?owned.lights[i].radius:1.f);
                lightPositions->setElement(i,osg::Vec3f());
            }
            state->addUniform(lightPositions);state->addUniform(colors);state->addUniform(radii);
            // Each shape owns winding/culling state, including mirrored transforms.
            viewer->setSceneData(owned.scene.get());
            viewer->realize();
            log->write("G3 original exterior attached; deterministic daylight approximation; effects/actors omitted; physical visibility UNVERIFIED");
        } catch (...) {
            osg::setNotifyHandler(previousLog.get());
            throw;
        }
    }
    void frame(double time, int w, int h) {
        if (w <= 0 || h <= 0) return;
        { // Z-up, fixed-step Bullet grounded traversal; no gameplay acceptance claim.
            width = w; height = h;
            window->resized(0, 0, w, h);
            window->getEventQueue()->windowResize(0, 0, w, h);
            const double aspect = double(w) / h;
            navigation.update(time);
            auto* camera = viewer->getCamera();
            camera->setViewport(0, 0, w, h);
            camera->setProjectionMatrixAsPerspective(65.,aspect,2.,32768.);
            camera->setViewMatrixAsLookAt(navigation.eye,navigation.eye+navigation.direction(),osg::Vec3d(0,0,1));
            const auto view=camera->getViewMatrix();
            osg::Vec3d sun(.3,-.4,.8660254);sun=osg::Matrixd::transform3x3(sun,view);
            owned.scene->getOrCreateStateSet()->getUniform("sunDirection")->set(osg::Vec3f(sun));
            for(unsigned i=0;i<owned.lights.size();++i)lightPositions->setElement(i,osg::Vec3f(osg::Vec3d(owned.lights[i].position)*view));
        }
        const auto begin = std::chrono::steady_clock::now();
        viewer->frame(time);
        traversalWallMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
        ++frames;
        if (frames == 5) window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_FRAME);
        if (!shaderLinked) {
            auto* linked = program->getPCP(*window->getState());
            if (!linked) throw std::runtime_error("Missing per-context ESSL300 program");
            std::string message;
            linked->getInfoLog(message);
            log->write("G3 exterior program link log: " + message);
            if (!linked->isLinked()) throw std::runtime_error("Exterior shader failed to link: " + message);
            shaderLinked = true;
        }
    }
    ~OSGScene() {
        if (viewer) { viewer->setDone(true); viewer->stopThreading(); viewer = nullptr; }
        osg::setNotifyHandler(previousLog.get());
    }
};
