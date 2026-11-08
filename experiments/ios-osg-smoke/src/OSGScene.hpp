#pragma once
#include "Checkerboard.hpp"
#include <osg/Depth>
#include <osg/Geode>
#include <osg/Geometry>
#include <osg/Group>
#include <osg/GLExtensions>
#include <osg/MatrixTransform>
#include <osg/Notify>
#include <osg/Program>
#include <osg/Shader>
#include <osg/State>
#include <osg/Image>
#include <osg/Texture2D>
#include <osg/Uniform>
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
    // WARN-or-higher notifications, not a total GL-error count. OSG's GL
    // diagnostics may use other severities; every delivered message is logged.
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
    osg::ref_ptr<osg::Program> texturedProgram;
    osg::ref_ptr<osg::StateSet> coloredState, texturedState;
    osg::ref_ptr<osg::StateSet> profileStates[4];
    osg::ref_ptr<osg::Geode> baseGeode, repeatGeode;
    osg::ref_ptr<osg::Group> minificationGroup;
    osg::ref_ptr<osg::MatrixTransform> comparisonModels[6];
    unsigned textureProfile = 3;
    bool profileRendered[4] = {false, false, false, false};
    osg::ref_ptr<SceneLog> log;
    osg::ref_ptr<osg::NotifyHandler> previousLog;
    bool checkedProgram = false;
    bool checkedTexturedProgram = false;
    bool textured = true;
    int width = 0, height = 0;
public:
    bool mipmapCapabilityChecked = false;
    bool mipmapCapabilitySupported = false;
    bool mipmapEntryPointAvailable = false;
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
        window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE);
        log->write("OSG GL checking: ONCE_PER_ATTRIBUTE for initialization and the first 5 OSG-rendered frames");
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
        osg::ref_ptr<osg::Vec2Array> uvs = new osg::Vec2Array;
        const osg::Vec2 faceUVs[4] = {{0,0},{1,0},{1,1},{0,1}};
        osg::ref_ptr<osg::DrawElementsUShort> indices = new osg::DrawElementsUShort(GL_TRIANGLES);
        const osg::Vec3 corners[] = {{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},
                                     {-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}};
        const unsigned faces[6][4] = {{0,3,2,1},{4,5,6,7},{0,1,5,4},{3,7,6,2},{0,4,7,3},{1,2,6,5}};
        const osg::Vec4 palette[] = {{1,.2f,.1f,1},{.2f,1,.2f,1},{.1f,.4f,1,1},
                                     {1,.8f,.1f,1},{.8f,.2f,1,1},{.1f,1,1,1}};
        for (unsigned face = 0; face < 6; ++face) {
            for (unsigned corner : faces[face]) { vertices->push_back(corners[corner]); colors->push_back(palette[face]); }
            for (const auto& uv : faceUVs) uvs->push_back(uv);
            for (unsigned offset : {0u,1u,2u,0u,2u,3u}) indices->push_back(static_cast<GLushort>(face*4 + offset));
        }
        osg::ref_ptr<osg::Geometry> geometry = new osg::Geometry;
        geometry->setVertexArray(vertices.get());
        geometry->setColorArray(colors.get(), osg::Array::BIND_PER_VERTEX);
        // Explicit generic slot, independent of OSG's conventional texcoord aliases.
        geometry->setVertexAttribArray(6, uvs.get(), osg::Array::BIND_PER_VERTEX);
        geometry->addPrimitiveSet(indices.get());
        geometry->setUseDisplayList(false);
        geometry->setUseVertexBufferObjects(true);
        geometry->setUseVertexArrayObject(true);
        osg::ref_ptr<osg::Geode> geode = new osg::Geode;
        geode->addDrawable(geometry.get());
        baseGeode = geode;
        // A separate VAO/geometry supplies 2x2 tiling; baseline UVs stay untouched.
        osg::ref_ptr<osg::Vec2Array> repeatUVs = new osg::Vec2Array;
        for (const auto& uv : *uvs) repeatUVs->push_back(osg::Vec2(uv.x()*2.0f, uv.y()*2.0f));
        osg::ref_ptr<osg::Geometry> repeatGeometry = new osg::Geometry;
        repeatGeometry->setVertexArray(vertices.get());
        repeatGeometry->setColorArray(colors.get(), osg::Array::BIND_PER_VERTEX);
        repeatGeometry->setVertexAttribArray(6, repeatUVs.get(), osg::Array::BIND_PER_VERTEX);
        repeatGeometry->addPrimitiveSet(indices.get());
        repeatGeometry->setUseDisplayList(false);
        repeatGeometry->setUseVertexBufferObjects(true);
        repeatGeometry->setUseVertexArrayObject(true);
        repeatGeode = new osg::Geode;
        repeatGeode->addDrawable(repeatGeometry.get());
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
        coloredState = new osg::StateSet;
        coloredState->setAttributeAndModes(program.get(), osg::StateAttribute::ON);
        texturedProgram = new osg::Program;
        texturedProgram->addShader(new osg::Shader(osg::Shader::VERTEX, R"(#version 300 es
precision highp float;
in vec4 osg_Vertex;
in vec2 checkerUV;
uniform mat4 osg_ModelViewProjectionMatrix;
out mediump vec2 uv;
void main() { gl_Position=osg_ModelViewProjectionMatrix*osg_Vertex; uv=checkerUV; }
)"));
        texturedProgram->addShader(new osg::Shader(osg::Shader::FRAGMENT, R"(#version 300 es
precision mediump float;
in mediump vec2 uv;
uniform sampler2D checkerTexture;
out vec4 result;
void main() { result=texture(checkerTexture, uv); }
)"));
        texturedProgram->addBindAttribLocation("osg_Vertex", 0);
        texturedProgram->addBindAttribLocation("checkerUV", 6);
        texturedState = new osg::StateSet;
        texturedState->setAttributeAndModes(texturedProgram.get(), osg::StateAttribute::ON);
        osg::ref_ptr<osg::Image> image = new osg::Image;
        image->allocateImage(Checkerboard::Width, Checkerboard::Height, 1, GL_RGBA, GL_UNSIGNED_BYTE);
        if (!image->data()) throw std::runtime_error("OSG checkerboard image allocation failed");
        Checkerboard::fill(image->data());
        osg::ref_ptr<osg::Texture2D> texture = new osg::Texture2D(image.get());
        texture->setUnRefImageDataAfterApply(false);
        texture->setFilter(osg::Texture::MIN_FILTER, osg::Texture::NEAREST);
        texture->setFilter(osg::Texture::MAG_FILTER, osg::Texture::NEAREST);
        texture->setWrap(osg::Texture::WRAP_S, osg::Texture::CLAMP_TO_EDGE);
        texture->setWrap(osg::Texture::WRAP_T, osg::Texture::CLAMP_TO_EDGE);
        texture->setLODBias(0.0f);
        texture->setUseHardwareMipMapGeneration(false);
        // StateSet retains Texture2D, which retains Image and its allocateImage storage.
        // NEAREST minification requests only level zero; no mip chain is supplied.
        texturedState->setTextureAttribute(0, texture.get(), osg::StateAttribute::ON);
        texturedState->addUniform(new osg::Uniform("checkerTexture", 0));
        for (auto* state : {coloredState.get(), texturedState.get()}) {
            state->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
            state->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
        }
        profileStates[0] = texturedState; // Build #10's original state, unchanged.
        for (unsigned profile = 1; profile < 3; ++profile) {
            osg::ref_ptr<osg::Texture2D> variant = new osg::Texture2D(image.get());
            variant->setUnRefImageDataAfterApply(false);
            const auto filter = profile == 1 ? osg::Texture::LINEAR : osg::Texture::NEAREST;
            const auto wrap = profile == 2 ? osg::Texture::REPEAT : osg::Texture::CLAMP_TO_EDGE;
            variant->setFilter(osg::Texture::MIN_FILTER, filter);
            variant->setFilter(osg::Texture::MAG_FILTER, filter);
            variant->setWrap(osg::Texture::WRAP_S, wrap);
            variant->setWrap(osg::Texture::WRAP_T, wrap);
            variant->setLODBias(0.0f);
            variant->setUseHardwareMipMapGeneration(false);
            profileStates[profile] = new osg::StateSet;
            profileStates[profile]->setAttributeAndModes(texturedProgram.get(), osg::StateAttribute::ON);
            profileStates[profile]->setTextureAttribute(0, variant.get(), osg::StateAttribute::ON);
            profileStates[profile]->addUniform(new osg::Uniform("checkerTexture", 0));
            profileStates[profile]->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
            profileStates[profile]->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
        }
        // Build #12: one additional texture; original three profiles stay untouched.
        osg::ref_ptr<osg::Texture2D> mipTexture = new osg::Texture2D(image.get());
        mipTexture->setUnRefImageDataAfterApply(false);
        mipTexture->setFilter(osg::Texture::MIN_FILTER, osg::Texture::LINEAR_MIPMAP_LINEAR);
        mipTexture->setFilter(osg::Texture::MAG_FILTER, osg::Texture::LINEAR);
        mipTexture->setWrap(osg::Texture::WRAP_S, osg::Texture::CLAMP_TO_EDGE);
        mipTexture->setWrap(osg::Texture::WRAP_T, osg::Texture::CLAMP_TO_EDGE);
        mipTexture->setLODBias(0.0f);
        mipTexture->setUseHardwareMipMapGeneration(true);
        profileStates[3] = new osg::StateSet;
        profileStates[3]->setAttributeAndModes(texturedProgram.get(), osg::StateAttribute::ON);
        profileStates[3]->setTextureAttribute(0, mipTexture.get(), osg::StateAttribute::ON);
        profileStates[3]->addUniform(new osg::Uniform("checkerTexture", 0));
        profileStates[3]->setAttributeAndModes(new osg::Depth, osg::StateAttribute::ON);
        profileStates[3]->setMode(GL_DEPTH_TEST, osg::StateAttribute::ON);
        minificationGroup = new osg::Group;
        for (unsigned i = 0; i < 6; ++i) {
            comparisonModels[i] = new osg::MatrixTransform;
            comparisonModels[i]->setStateSet(profileStates[i % 2 == 0 ? 3 : 1].get());
            comparisonModels[i]->addChild(baseGeode.get());
            minificationGroup->addChild(comparisonModels[i].get());
        }
        applySelection();
        log->write("OSG cube startup: mipmapped profile; hardware generation REQUESTED, actual glGenerateMipmap execution UNKNOWN; expected levels 32,16,8,4,2,1");
        viewer->setSceneData(model.get());
        viewer->realize();
        log->write("Embedded OSG viewer realized; single thread, external EGL swap");
    }
    unsigned warnings() const { return log->warnings; }
    static const char* textureProfileName(unsigned profile) {
        const char* names[] = {"NEAREST/CLAMP_TO_EDGE (1x1)", "LINEAR/CLAMP_TO_EDGE (1x1)", "NEAREST/REPEAT (2x2)",
                               "LINEAR_MIPMAP_LINEAR/CLAMP_TO_EDGE (paired minification)"};
        return profile < 4 ? names[profile] : "invalid";
    }
    const char* selectedTextureProfile() const { return textureProfileName(textureProfile); }
    bool textureProfileRendered(unsigned profile) const { return profile < 4 && profileRendered[profile]; }
    void applySelection() {
        model->setStateSet(textured ? profileStates[textureProfile].get() : coloredState.get());
        osg::Node* selected = textured && textureProfile == 2 ? repeatGeode.get() : baseGeode.get();
        model->setChild(0, textured && textureProfile == 3 ? minificationGroup.get() : selected);
    }
    void cycleTextureProfile() {
        textureProfile = (textureProfile + 1) % 4;
        applySelection();
        log->write(std::string("OSG selected texture profile: ") + selectedTextureProfile() +
                   (textured ? " (textured cube selected)" : " (stored while colored cube selected)"));
    }
    bool isTextured() const { return textured; }
    void setTextured(bool value) {
        if (textured == value) return;
        textured = value;
        applySelection();
        log->write(std::string("OSG cube mode: ") + (textured ? "textured" : "colored"));
    }
    void frame(double time, int w, int h) {
        if (w != width || h != height) {
            width=w; height=h;
            window->resized(0,0,w,h);
            window->getEventQueue()->windowResize(0,0,w,h);
            viewer->getCamera()->setViewport(0,0,w,h);
            viewer->getCamera()->setProjectionMatrixAsPerspective(50.0, double(w)/h, 0.1, 100.0);
        }
        model->setMatrix(osg::Matrix::rotate(time*0.55, osg::Vec3(0,0,1)));
        if (textured && textureProfile == 3) {
            if (!mipmapCapabilityChecked) {
                auto* extensions = window->getState()->get<osg::GLExtensions>();
                mipmapEntryPointAvailable = extensions && extensions->glGenerateMipmap;
                mipmapCapabilitySupported = extensions && (extensions->isGenerateMipMapSupported || extensions->isFrameBufferObjectSupported);
                mipmapCapabilityChecked = true;
                log->write(std::string("OSG mipmap gate: capability=") + (mipmapCapabilitySupported ? "true" : "false") +
                           "; glGenerateMipmap pointer=" + (mipmapEntryPointAvailable ? "available" : "missing") +
                           "; request=true; actual execution UNKNOWN (not intercepted)");
                if (!mipmapCapabilitySupported || !mipmapEntryPointAvailable)
                    throw std::runtime_error("Mipmap profile blocked: hardware generation capability/entry point unavailable; CPU fallback is not accepted");
            }
            model->setMatrix(osg::Matrix::identity());
            // Screen-right and screen-up are perpendicular to the fixed view vector.
            // Each row's pair has equal depth, scale, rotation and base UVs.
            const osg::Vec3 screenRight(0.8574929f, 0.5144958f, 0.0f);
            const osg::Vec3 screenUp(-0.2353796f, 0.3922993f, 0.8892118f);
            const float scales[3] = {0.2f, 0.05f, 0.0125f};
            for (unsigned i = 0; i < 6; ++i) {
                const unsigned row = i / 2;
                const osg::Vec3 position = screenRight * (i % 2 == 0 ? -0.65f : 0.65f) + screenUp * (1.0f - row);
                comparisonModels[i]->setMatrix(osg::Matrix::scale(scales[row], scales[row], scales[row]) *
                    osg::Matrix::rotate(time*0.55, osg::Vec3(0,0,1)) * osg::Matrix::translate(position));
            }
        }
        viewer->getCamera()->setClearColor(osg::Vec4(.12f,.14f,.2f,1));
        // Later profiles are outside KHR_debug's original five-frame lifetime.
        // Spend at most one extra fine-grained traversal per first-used profile.
        const bool lateProfileCheck = frames >= 5 && textured && !profileRendered[textureProfile];
        if (lateProfileCheck) {
            window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE);
            log->write(std::string("OSG first-use ONCE_PER_ATTRIBUTE: ") + selectedTextureProfile() +
                       "; KHR_debug initial window is not rearmed; OSG frame " + std::to_string(frames + 1));
        }
        const auto begin = std::chrono::steady_clock::now();
        viewer->frame(time); // advance + event + update + cull/draw traversal
        traversalWallMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now()-begin).count();
        if (lateProfileCheck) {
            window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_FRAME);
            log->write(std::string("OSG ONCE_PER_FRAME restored after first-use traversal: ") + selectedTextureProfile());
        }
        ++frames;
        // Count completed OSG traversals only; clear-only swaps and suspension
        // do not spend or restart this temporary diagnostic window.
        if (frames == 5) {
            window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_FRAME);
            log->write("OSG GL checking: ONCE_PER_FRAME restored after 5 OSG-rendered frames");
        }
        for (unsigned profile = 0; profile < 4; ++profile) {
            const bool visible = textured && (profile == textureProfile || (textureProfile == 3 && profile == 1));
            if (!visible || profileRendered[profile]) continue;
            profileRendered[profile] = true;
            log->write(std::string("OSG texture profile first traversal completed: ") + textureProfileName(profile) +
                       "; OSG frame " + std::to_string(frames) + "; inspect raw GL diagnostics, not a pass certificate");
        }
        bool& checked = textured ? checkedTexturedProgram : checkedProgram;
        osg::Program* activeProgram = textured ? texturedProgram.get() : program.get();
        if (!checked) {
            auto* pcp = activeProgram->getPCP(*window->getState());
            if (!pcp) throw std::runtime_error("OSG did not create a per-context shader program");
            std::string message;
            pcp->getInfoLog(message);
            log->write(std::string("OSG program link log (") + (textured ? "textured" : "colored") + "): " + message);
            if (!pcp->isLinked()) throw std::runtime_error("OSG ESSL300 program failed to link: " + message);
            checked = true;
        }
    }
    ~OSGScene() {
        if (viewer) { viewer->setDone(true); viewer->stopThreading(); viewer = nullptr; }
        osg::setNotifyHandler(previousLog.get());
    }
};
