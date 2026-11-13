#pragma once
#include "TextureAdapter.hpp"
#include <osg/Depth>
#include <osg/GLExtensions>
#include <osg/Notify>
#include <osg/Program>
#include <osg/Shader>
#include <osg/State>
#include <osg/Version>
#include <osg/Vec3d>
#include <osgViewer/GraphicsWindow>
#include <osgViewer/Viewer>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <stdexcept>
#include <utility>

// Defined in the Objective-C++ application; validates bundle provenance and genuine parsing.
G1C::Scene LoadGeometry();

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
    G1A::OwnedGeometry owned;
    osg::Vec3d center;
    double radius = 0;
    int width = 0, height = 0;
public:
    unsigned long long frames = 0;
    double traversalWallMs = 0;
    bool shaderLinked = false;
    unsigned contextID() const { return window->getState()->getContextID(); }
    unsigned warnings() const { return log->warnings; }
    explicit OSGScene(std::function<void(const std::string&)> callback) {
        auto textured = LoadGeometry(); owned = std::move(textured.geometry); // Actual decoded arrays only; failure cannot fall back to a mesh.
        const auto bound = owned.drawable->getBoundingBox();
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
            viewer->getCamera()->setClearColor(osg::Vec4(.05f, .07f, .12f, 1));
            program = new osg::Program;
            program->addShader(new osg::Shader(osg::Shader::VERTEX, R"(#version 300 es
precision highp float;
in vec4 osg_Vertex;
in vec4 osg_Color;
in vec2 nifUV;
uniform mat4 osg_ModelViewProjectionMatrix;
out vec4 color;
out vec2 uv;
void main() { gl_Position=osg_ModelViewProjectionMatrix*osg_Vertex; color=osg_Color; uv=nifUV; }
)"));
            program->addShader(new osg::Shader(osg::Shader::FRAGMENT, R"(#version 300 es
precision mediump float;
in vec4 color;
in vec2 uv;
uniform sampler2D baseTexture;
out vec4 result;
void main() { result=texture(baseTexture, uv)*color; }
)"));
            program->addBindAttribLocation("osg_Vertex", 0);
            program->addBindAttribLocation("osg_Color", 3);
            program->addBindAttribLocation("nifUV", 6);
            // Colors, UVs and Texture2D are owned copies of genuinely decoded records.
            auto* state = owned.geode->getOrCreateStateSet();
            state->setAttributeAndModes(program.get(), osg::StateAttribute::ON);
            state->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
            state->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
            state->setMode(GL_CULL_FACE, osg::StateAttribute::OFF);
            viewer->setSceneData(owned.geode.get());
            viewer->realize();
            log->write("G1C decoded texture/geometry attached; visibility requires independent physical-device review");
        } catch (...) {
            osg::setNotifyHandler(previousLog.get());
            throw;
        }
    }
    void frame(double time, int w, int h) {
        if (w <= 0 || h <= 0) return;
        if (w != width || h != height) {
            width = w; height = h;
            window->resized(0, 0, w, h);
            window->getEventQueue()->windowResize(0, 0, w, h);
            const double aspect = double(w) / h;
            const double halfFov = std::atan(std::tan(25. * 3.141592653589793 / 180.) * std::min(1., aspect));
            const double distance = 1.4 * radius / std::sin(halfFov);
            auto* camera = viewer->getCamera();
            camera->setViewport(0, 0, w, h);
            camera->setProjectionMatrixAsPerspective(50., aspect, std::max(.001, distance - 2 * radius), distance + 4 * radius);
            camera->setViewMatrixAsLookAt(center + osg::Vec3d(0, 0, distance), center, osg::Vec3d(0, 1, 0));
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
            log->write("G1C textured program link log: " + message);
            if (!linked->isLinked()) throw std::runtime_error("Decoded triangle shader failed to link: " + message);
            shaderLinked = true;
        }
    }
    ~OSGScene() {
        if (viewer) { viewer->setDone(true); viewer->stopThreading(); viewer = nullptr; }
        osg::setNotifyHandler(previousLog.get());
    }
};
