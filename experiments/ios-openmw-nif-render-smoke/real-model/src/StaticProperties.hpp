#pragma once
#include <components/nif/property.hpp>
#include <osg/BlendFunc>
#include <osg/Depth>
#include <osg/FrontFace>
#include <osg/StateSet>
#include <osg/Uniform>
#include <cmath>
#include <stdexcept>
#include <string>

namespace G1D {
// Effective properties travel by value down each branch. A child's property
// replaces the same inherited type; no sibling can change another's state.
struct StaticProperties {
    const Nif::NiMaterialProperty* material = nullptr;
    const Nif::NiTexturingProperty* texture = nullptr;
    const Nif::NiVertexColorProperty* vertex = nullptr;
    const Nif::NiAlphaProperty* alpha = nullptr;
    const Nif::NiZBufferProperty* depth = nullptr;
    const Nif::NiStencilProperty* stencil = nullptr;
};

inline void propertyCheck(bool valid, const Nif::NiProperty* p, const std::string& node,
    const std::string& reason) {
    if (!valid) throw std::runtime_error("G1D stage=properties node=" + node + " property="
        + (p ? p->mRecordName + "#" + std::to_string(p->mRecordIndex) : "<default>") + ": " + reason);
}

inline void inheritProperty(StaticProperties& s, const Nif::NiProperty* p, const std::string& node) {
    auto check = [&](bool b, const char* why) { propertyCheck(b, p, node, why); };
    check(p != nullptr, "Null property");
    check(p->mController.empty(), "Animated property unsupported");
    if (auto* v = dynamic_cast<const Nif::NiMaterialProperty*>(p)) s.material = v;
    else if (auto* v = dynamic_cast<const Nif::NiTexturingProperty*>(p)) s.texture = v;
    else if (auto* v = dynamic_cast<const Nif::NiVertexColorProperty*>(p)) {
        check(static_cast<unsigned>(v->mVertexMode) <= 2, "Invalid vertex color mode");
        check(static_cast<unsigned>(v->mLightingMode) <= 1, "Invalid lighting mode");
        // The current shader is unlit diffuse. Emission needs a separate shader
        // term; accepting those modes as diffuse would silently change the model.
        check(v->mVertexMode != Nif::NiVertexColorProperty::VertexMode::VertMode_SrcEmissive,
            "Emissive vertex colors need lighting shader support");
        check(v->mLightingMode == Nif::NiVertexColorProperty::LightMode::LightMode_EmiAmbDif,
            "Emission-only lighting needs lighting shader support");
        s.vertex = v;
    } else if (auto* v = dynamic_cast<const Nif::NiZBufferProperty*>(p)) s.depth = v;
    else if (auto* v = dynamic_cast<const Nif::NiAlphaProperty*>(p)) {
        check((v->mFlags & ~0x3fffu) == 0, "Unknown alpha flags");
        check(v->sourceBlendMode() <= 10 && v->destinationBlendMode() <= 9, "Invalid GLES blend factors");
        s.alpha = v;
    } else if (auto* v = dynamic_cast<const Nif::NiStencilProperty*>(p)) {
        check(!v->mEnabled, "Stencil testing requires a stencil-capable EGL configuration");
        check(static_cast<unsigned>(v->mDrawMode) <= 3, "Invalid face draw mode");
        s.stencil = v;
    } else if (dynamic_cast<const Nif::NiSpecularProperty*>(p)) {
        // OpenMW disables specular for VER_MW regardless of this enable bit.
    } else if (auto* v = dynamic_cast<const Nif::NiWireframeProperty*>(p)) {
        check(!v->mEnable, "Wireframe needs a separate GLES implementation");
    } else if (auto* v = dynamic_cast<const Nif::NiShadeProperty*>(p)) {
        check(v->mFlags == 1, "Only smooth shading is supported by this shader");
    } else {
        check(false, "Unsupported NIF property; no silent approximation");
    }
}

inline osg::Vec4 diffuseColor(const StaticProperties& s, bool hasColors, const std::string& node) {
    osg::Vec4 color(1, 1, 1, 1);
    if (s.material) {
        const auto& m = *s.material;
        color = osg::Vec4(m.mDiffuse, m.mAlpha);
        for (unsigned i = 0; i < 3; ++i) {
            propertyCheck(std::isfinite(m.mAmbient[i]) && std::isfinite(m.mSpecular[i])
                && std::isfinite(m.mEmissive[i]), &m, node, "Nonfinite material channel");
        }
        propertyCheck(m.mEmissive == osg::Vec3f(), &m, node, "Emissive material needs lighting shader support");
        propertyCheck(std::isfinite(m.mGlossiness), &m, node, "Nonfinite glossiness");
        // Specular is deliberately disabled for MW, exactly as NifOsg::Loader.
    }
    for (unsigned i = 0; i < 4; ++i)
        propertyCheck(std::isfinite(color[i]) && color[i] >= 0 && color[i] <= 1,
            s.material, node, "Invalid material color/alpha");
    const bool useColors = !s.vertex || s.vertex->mVertexMode
        == Nif::NiVertexColorProperty::VertexMode::VertMode_SrcAmbDif;
    // OpenMW's AmbientAndDiffuse fallback without a color array is white,
    // including alpha. Explicit SrcIgnore retains the material instead.
    if (s.vertex && useColors && !hasColors) color.set(1, 1, 1, 1);
    return color;
}

inline void applyStaticState(osg::StateSet& state, const StaticProperties& s, double determinant) {
    // Mirrors upstream handleDepthFlags: MW's encoded comparison is ignored.
    const bool test = !s.depth || s.depth->depthTest();
    const bool write = !s.depth || s.depth->depthWrite();
    state.setAttributeAndModes(new osg::Depth(test ? osg::Depth::LEQUAL : osg::Depth::ALWAYS, 0, 1, write),
        osg::StateAttribute::ON);
    state.setMode(GL_DEPTH_TEST, test || write ? osg::StateAttribute::ON : osg::StateAttribute::OFF);
    using Draw = Nif::NiStencilProperty::DrawMode;
    const Draw draw = s.stencil ? s.stencil->mDrawMode : Draw::Default;
    const bool clockwise = (draw == Draw::Clockwise) != (determinant < 0);
    state.setAttributeAndModes(new osg::FrontFace(clockwise ? osg::FrontFace::CLOCKWISE : osg::FrontFace::COUNTER_CLOCKWISE));
    state.setMode(GL_CULL_FACE, draw == Draw::Both ? osg::StateAttribute::OFF : osg::StateAttribute::ON);
    state.setMode(GL_STENCIL_TEST, osg::StateAttribute::OFF);
    const bool blend = s.alpha && s.alpha->useAlphaBlending();
    state.setMode(GL_BLEND, blend ? osg::StateAttribute::ON : osg::StateAttribute::OFF);
    if (blend) {
        const GLenum modes[] = { GL_ONE, GL_ZERO, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_DST_COLOR,
            GL_ONE_MINUS_DST_COLOR, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA,
            GL_ONE_MINUS_DST_ALPHA, GL_SRC_ALPHA_SATURATE };
        auto destination = modes[s.alpha->destinationBlendMode()];
        if (destination == GL_DST_ALPHA) destination = GL_ONE; // OpenMW's D3D8 compatibility.
        state.setAttributeAndModes(new osg::BlendFunc(modes[s.alpha->sourceBlendMode()], destination));
        if (!s.alpha->noSorter()) state.setRenderingHint(osg::StateSet::TRANSPARENT_BIN);
    }
    // GLES3 has no fixed-function alpha test; test the final sampled alpha in GLSL.
    state.addUniform(new osg::Uniform("alphaTestMode", s.alpha && s.alpha->useAlphaTesting() ? s.alpha->alphaTestMode() : 0));
    state.addUniform(new osg::Uniform("alphaThreshold", s.alpha ? s.alpha->mThreshold / 255.f : 0.f));
}
}
