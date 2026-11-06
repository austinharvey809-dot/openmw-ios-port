#pragma once
#include <osg/Depth>
#include <osg/Geode>
#include <osg/Geometry>
#include <osg/GLExtensions>
#include <osg/MatrixTransform>
#include <osg/Notify>
#include <osg/Program>
#include <osg/Shader>
#include <osg/Version>
#include <osgViewer/GraphicsWindow>
#include <osgViewer/Viewer>
#include <functional>
#include <chrono>
#include <stdexcept>
#include <string>
#include <utility>

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

// UIKit/EGL owns currentness and the one real swap. GraphicsWindowEmbedded's
// context/swap methods are no-ops; it owns only OSG state/context ID bookkeeping.
class OSGScene {
    osg::ref_ptr<osgViewer::GraphicsWindowEmbedded> window;
    osg::ref_ptr<osgViewer::Viewer> viewer;
    osg::ref_ptr<osg::MatrixTransform> model;
    osg::ref_ptr<osg::Program> program;
    osg::ref_ptr<SceneLog> log;
    osg::ref_ptr<osg::NotifyHandler> previousLog;
    bool checkedProgram = false;
    int width = 0, height = 0;
public:
    unsigned long long frames = 0;
    double traversalWallMs = 0;
    unsigned contextID() const { return window->getState()->getContextID(); }
    explicit OSGScene(std::function<void(const std::string&)> callback) {
        previousLog = osg::getNotifyHandler();
        log = new SceneLog(std::move(callback));
        osg::setNotifyHandler(log.get());
        osg::setNotifyLevel(osg::INFO);
        log->write(std::string("OSG runtime ") + osgGetVersion());
        for (const char* name : {"glCreateShader", "glBindVertexArray", "glDrawElements"}) {
            if (!osg::getGLExtensionFuncPtr(name))
                throw std::runtime_error(std::string("OSG ANGLE resolver missing ") + name);
        }
        window = new osgViewer::GraphicsWindowEmbedded(0, 0, 1, 1);
        window->getState()->setUseModelViewAndProjectionUniforms(true);
        window->getState()->setUseVertexAttributeAliasing(true);
        window->getState()->resetVertexAttributeAlias(false); // vertex=0, color=3
        viewer = new osgViewer::Viewer;
        viewer->setThreadingModel(osgViewer::Viewer::SingleThreaded);
        viewer->setReleaseContextAtEndOfFrameHint(false);
        viewer->setCameraManipulator(nullptr);
        auto* camera = viewer->getCamera();
        camera->setGraphicsContext(window.get());
        camera->setClearMask(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        camera->setViewMatrixAsLookAt(osg::Vec3(3,-5,3), osg::Vec3(0,0,0), osg::Vec3(0,0,1));

        osg::ref_ptr<osg::Vec3Array> vertices = new osg::Vec3Array;
        osg::ref_ptr<osg::Vec4Array> colors = new osg::Vec4Array;
        osg::ref_ptr<osg::DrawElementsUShort> indices = new osg::DrawElementsUShort(GL_TRIANGLES);
        const osg::Vec3 corners[] = {{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},
                                     {-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}};
        const unsigned faces[6][4] = {{0,3,2,1},{4,5,6,7},{0,1,5,4},{3,7,6,2},{0,4,7,3},{1,2,6,5}};
        const osg::Vec4 palette[] = {{1,.2f,.1f,1},{.2f,1,.2f,1},{.1f,.4f,1,1},
                                     {1,.8f,.1f,1},{.8f,.2f,1,1},{.1f,1,1,1}};
        for (unsigned face = 0; face < 6; ++face) {
            for (unsigned corner : faces[face]) { vertices->push_back(corners[corner]); colors->push_back(palette[face]); }
            for (unsigned offset : {0u,1u,2u,0u,2u,3u}) indices->push_back(static_cast<GLushort>(face*4 + offset));
        }
        osg::ref_ptr<osg::Geometry> geometry = new osg::Geometry;
        geometry->setVertexArray(vertices.get());
        geometry->setColorArray(colors.get(), osg::Array::BIND_PER_VERTEX);
        geometry->addPrimitiveSet(indices.get());
        geometry->setUseDisplayList(false);
        geometry->setUseVertexBufferObjects(true);
        geometry->setUseVertexArrayObject(true);
        osg::ref_ptr<osg::Geode> geode = new osg::Geode;
        geode->addDrawable(geometry.get());
        model = new osg::MatrixTransform;
        model->addChild(geode.get());
        program = new osg::Program;
        program->addShader(new osg::Shader(osg::Shader::VERTEX, R"(#version 300 es
precision highp float;
in vec4 osg_Vertex;
in vec4 osg_Color;
uniform mat4 osg_ModelViewProjectionMatrix;
out vec4 color;
void main() { gl_Position=osg_ModelViewProjectionMatrix*osg_Vertex; color=osg_Color; }
)"));
        program->addShader(new osg::Shader(osg::Shader::FRAGMENT, R"(#version 300 es
precision mediump float;
in vec4 color;
out vec4 result;
void main() { result=color; }
)"));
        program->addBindAttribLocation("osg_Vertex", 0);
        program->addBindAttribLocation("osg_Color", 3);
        model->getOrCreateStateSet()->setAttributeAndModes(program.get(), osg::StateAttribute::ON);
        model->getOrCreateStateSet()->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
        model->getOrCreateStateSet()->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
        viewer->setSceneData(model.get());
        viewer->realize();
        log->write("Embedded OSG viewer realized; single thread, external EGL swap");
    }
    unsigned warnings() const { return log->warnings; }
    void frame(double time, int w, int h) {
        if (w != width || h != height) {
            width=w; height=h;
            window->resized(0,0,w,h);
            window->getEventQueue()->windowResize(0,0,w,h);
            viewer->getCamera()->setViewport(0,0,w,h);
            viewer->getCamera()->setProjectionMatrixAsPerspective(50.0, double(w)/h, 0.1, 100.0);
        }
        model->setMatrix(osg::Matrix::rotate(time*0.55, osg::Vec3(0,0,1)));
        viewer->getCamera()->setClearColor(osg::Vec4(.12f,.14f,.2f,1));
        const auto begin = std::chrono::steady_clock::now();
        viewer->frame(time); // advance + event + update + cull/draw traversal
        traversalWallMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now()-begin).count();
        ++frames;
        if (!checkedProgram) {
            auto* pcp = program->getPCP(*window->getState());
            if (!pcp) throw std::runtime_error("OSG did not create a per-context shader program");
            std::string message;
            pcp->getInfoLog(message);
            log->write("OSG program link log: " + message);
            if (!pcp->isLinked()) throw std::runtime_error("OSG ESSL300 program failed to link: " + message);
            checkedProgram = true;
        }
    }
    ~OSGScene() {
        if (viewer) { viewer->setDone(true); viewer->stopThreading(); viewer = nullptr; }
        osg::setNotifyHandler(previousLog.get());
    }
};
