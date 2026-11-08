"""Texture scene contracts plus an optional executable test of the actual pixel helper.

Source checks do not prove native OSG/GLES behavior; the C++ fixture needs a compiler.
"""
from pathlib import Path
import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE = (ROOT / 'src/OSGScene.hpp').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/main.mm').read_text(encoding='utf-8')
CHECKER = (ROOT / 'src/Checkerboard.hpp').read_text(encoding='utf-8')


class TextureSceneTests(unittest.TestCase):
    def test_checker_dimensions_palette_marker_and_alpha_contract(self):
        self.assertIn('Width = 32, Height = 32, Channels = 4, Cell = 4;', CHECKER)
        self.assertIn('y < Height', CHECKER)
        self.assertIn('x < Width', CHECKER)
        self.assertIn('(y * Width + x) * Channels', CHECKER)
        self.assertIn('((x / Cell + y / Cell) % 2) ? 240 : 32', CHECKER)
        self.assertIn('marker = x < Cell && y < Cell', CHECKER)
        for channel, value in ((0, 255), (1, 32), (2, 32)):
            self.assertIn(f'pixels[offset + {channel}] = marker ? {value} : shade;', CHECKER)
        self.assertIn('pixels[offset + 3] = 255;', CHECKER)

    def test_actual_cpp_pixel_helper_all_pixels_and_bounds(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable; pixel helper execution requires native host tools')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'checker.cpp'
            binary = Path(directory) / 'checker-test.exe'
            source.write_text('''#include "Checkerboard.hpp"
#include <cassert>
#include <array>
int main() {
    assert(Checkerboard::mipLevelCount(32)==6);
    const unsigned expected[] = {32,16,8,4,2,1};
    for (unsigned level=0; level<6; ++level)
        assert(Checkerboard::mipDimension(32,level)==expected[level]);
    assert(Checkerboard::mipDimension(32,99)==1);
    assert(Checkerboard::mipLevelCount(0)==0 && Checkerboard::mipDimension(0,0)==0);
    assert(Checkerboard::mipLevelCount(1)==1 && Checkerboard::mipLevelCount(31)==5);
    static_assert(Checkerboard::Width == 32 && Checkerboard::Height == 32 &&
                  Checkerboard::Channels == 4, "fixture size");
    std::array<unsigned char, 4098> storage;
    storage.fill(117);
    Checkerboard::fill(storage.data() + 1);
    assert(storage.front() == 117 && storage.back() == 117);
    unsigned markerCount = 0;
    for (unsigned y=0; y<32; ++y) for (unsigned x=0; x<32; ++x) {
        const unsigned char* p = storage.data() + 1 + 4*(32*y+x);
        if (x<4 && y<4) {
            assert(p[0]==255 && p[1]==32 && p[2]==32); ++markerCount;
        } else {
            unsigned expected = ((x/4+y/4)%2) ? 240 : 32;
            assert(p[0]==expected && p[1]==expected && p[2]==expected);
        }
        assert(p[3]==255);
    }
    assert(markerCount==16);
}
''', encoding='utf-8')
            subprocess.run([compiler, '-std=c++11', '-I', str(ROOT / 'src'), str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_osg_owned_storage_retained_through_texture_and_state(self):
        for text in ('osg::ref_ptr<osg::Image> image = new osg::Image;',
                     'image->allocateImage(Checkerboard::Width, Checkerboard::Height, 1, GL_RGBA, GL_UNSIGNED_BYTE);',
                     'if (!image->data()) throw', 'Checkerboard::fill(image->data());',
                     'osg::ref_ptr<osg::Texture2D> texture = new osg::Texture2D(image.get());',
                     'texture->setUnRefImageDataAfterApply(false);',
                     'osg::ref_ptr<osg::StateSet> coloredState, texturedState;',
                     'texturedState->setTextureAttribute(0, texture.get(), osg::StateAttribute::ON);'):
            self.assertIn(text, SCENE)
        self.assertNotIn('setImage(', SCENE)  # no borrowed stack/external pixel storage
        self.assertNotIn('setTextureAttributeAndModes', SCENE)

    def test_uvs_match_face_vertices_and_bind_generic_slot_six(self):
        self.assertIn('const osg::Vec2 faceUVs[4] = {{0,0},{1,0},{1,1},{0,1}};', SCENE)
        loop = SCENE.split('for (unsigned face = 0; face < 6; ++face) {', 1)[1].split('osg::ref_ptr<osg::Geometry>', 1)[0]
        self.assertIn('for (const auto& uv : faceUVs) uvs->push_back(uv);', loop)
        self.assertIn('face*4 + offset', loop)
        self.assertIn('geometry->setVertexAttribArray(6, uvs.get(), osg::Array::BIND_PER_VERTEX);', SCENE)
        self.assertIn('texturedProgram->addBindAttribLocation("checkerUV", 6);', SCENE)
        self.assertIn('texturedProgram->addBindAttribLocation("osg_Vertex", 0);', SCENE)

    def test_texture_shader_samples_unit_zero_without_color_tint(self):
        self.assertIn('texturedState->addUniform(new osg::Uniform("checkerTexture", 0));', SCENE)
        shaders = re.findall(r'R"\((#version 300 es.*?)\)"', SCENE, re.S)
        self.assertEqual(len(shaders), 4)
        self.assertIn('in vec2 checkerUV;', shaders[2])
        self.assertIn('uv=checkerUV;', shaders[2])
        self.assertIn('uniform sampler2D checkerTexture;', shaders[3])
        self.assertIn('void main() { result=texture(checkerTexture, uv); }', shaders[3])
        self.assertNotIn('color', shaders[3])

    def test_colored_shader_baseline_is_exactly_preserved(self):
        shaders = re.findall(r'R"\((#version 300 es.*?)\)"', SCENE, re.S)
        self.assertEqual(shaders[:2], ['''#version 300 es
precision highp float;
in vec4 osg_Vertex;
in vec4 osg_Color;
uniform mat4 osg_ModelViewProjectionMatrix;
out vec4 color;
void main() { gl_Position=osg_ModelViewProjectionMatrix*osg_Vertex; color=osg_Color; }
''', '''#version 300 es
precision mediump float;
in vec4 color;
out vec4 result;
void main() { result=color; }
'''])

    def test_level_zero_nearest_edge_and_zero_bias(self):
        for which in ('MIN_FILTER', 'MAG_FILTER'):
            self.assertIn(f'texture->setFilter(osg::Texture::{which}, osg::Texture::NEAREST);', SCENE)
        for axis in ('S', 'T'):
            self.assertIn(f'texture->setWrap(osg::Texture::WRAP_{axis}, osg::Texture::CLAMP_TO_EDGE);', SCENE)
        self.assertIn('texture->setLODBias(0.0f);', SCENE)
        self.assertIn('texture->setUseHardwareMipMapGeneration(false);', SCENE)
        for forbidden in ('osg::Sampler', 'GL_LINEAR', 'glGenerateMipmap(', 'setMipmapLevels(', 'setMaxAnisotropy('):
            self.assertNotIn(forbidden, SCENE)

    def test_resources_created_once_not_in_frame_or_mode_switch(self):
        after_constructor = SCENE.split('unsigned warnings() const', 1)[1]
        for allocation in ('new osg::Image', 'new osg::Texture2D', 'allocateImage(', 'Checkerboard::fill(', 'new osg::Program'):
            self.assertEqual(SCENE.count(allocation), {'new osg::Program': 2, 'new osg::Texture2D': 3}.get(allocation, 1))
            self.assertNotIn(allocation, after_constructor)

    def test_link_validation_is_independent_and_after_traversal(self):
        self.assertIn('bool checkedProgram = false;', SCENE)
        self.assertIn('bool checkedTexturedProgram = false;', SCENE)
        self.assertIn('bool& checked = textured ? checkedTexturedProgram : checkedProgram;', SCENE)
        self.assertIn('osg::Program* activeProgram = textured ? texturedProgram.get() : program.get();', SCENE)
        self.assertIn('activeProgram->getPCP(*window->getState())', SCENE)
        self.assertLess(SCENE.index('viewer->frame(time);'), SCENE.index('if (!checked)'))
        self.assertLess(SCENE.index('if (!pcp->isLinked()) throw'), SCENE.index('checked = true;'))
        self.assertIn('(textured ? "textured" : "colored") + "): " + message', SCENE)

    def test_startup_and_controller_modes_preserve_clear_selection(self):
        self.assertIn('bool textured = true;', SCENE)
        self.assertLess(SCENE.index('applySelection();'), SCENE.index('viewer->realize();'))
        self.assertIn('model->setStateSet(textured ? profileStates[textureProfile].get() : coloredState.get());', SCENE)
        self.assertIn('applySelection();', SCENE.split('void setTextured(bool value)', 1)[1].split('void frame(', 1)[0])
        controls = MAIN.split('if (controller != previousController || !buttonsPrimed)', 1)[1].split('if (renderer && !renderer->sceneAvailable)', 1)[0]
        self.assertIn('previousController = controller; previousY = y; previousX = x; buttonsPrimed = true;', controls)
        self.assertIn('if (y && !previousY) clearOnly = !clearOnly;', controls)
        self.assertIn('if (x && !previousX && renderer && renderer->osgScene)', controls)
        self.assertIn('renderer->osgScene->setTextured(!renderer->osgScene->isTextured());', controls)
        self.assertNotIn('clearOnly = false', controls)
        self.assertEqual(controls.count('clearOnly ='), 1)
        self.assertIn('result[@"selected_cube"]', MAIN)

    def test_gl_ownership_and_bounded_osg_diagnostic_calls(self):
        self.assertEqual(MAIN.count('eglSwapBuffers(display, surface)'), 1)
        self.assertIn('Viewer::SingleThreaded', SCENE)
        self.assertIn('viewer->frame(time)', SCENE)
        self.assertEqual(re.findall(r'setCheckForGLErrors\(osg::State::(\w+)\)', SCENE),
                         ['ONCE_PER_ATTRIBUTE', 'ONCE_PER_ATTRIBUTE', 'ONCE_PER_FRAME', 'ONCE_PER_FRAME'])
        for forbidden in ('glReadPixels', 'glGetError', 'glFinish', 'eglMakeCurrent'):
            self.assertNotIn(forbidden, SCENE + CHECKER)

    def test_profiles_have_separate_fixed_textures_sharing_one_image(self):
        self.assertIn('profileStates[0] = texturedState;', SCENE)
        variants = SCENE.split('for (unsigned profile = 1; profile < 3; ++profile)', 1)[1].split('// Build #12:', 1)[0]
        for text in ('new osg::Texture2D(image.get())', 'variant->setUnRefImageDataAfterApply(false);',
                     'profile == 1 ? osg::Texture::LINEAR : osg::Texture::NEAREST',
                     'profile == 2 ? osg::Texture::REPEAT : osg::Texture::CLAMP_TO_EDGE',
                     'variant->setLODBias(0.0f);', 'variant->setUseHardwareMipMapGeneration(false);',
                     'profileStates[profile] = new osg::StateSet;',
                     'profileStates[profile]->setTextureAttribute(0, variant.get(), osg::StateAttribute::ON);',
                     'profileStates[profile]->setAttributeAndModes(texturedProgram.get(), osg::StateAttribute::ON);',
                     'profileStates[profile]->addUniform(new osg::Uniform("checkerTexture", 0));'):
            self.assertIn(text, variants)
        for which in ('MIN_FILTER', 'MAG_FILTER'):
            self.assertIn(f'variant->setFilter(osg::Texture::{which}, filter);', variants)
        for axis in ('S', 'T'):
            self.assertIn(f'variant->setWrap(osg::Texture::WRAP_{axis}, wrap);', variants)
        selection = SCENE.split('void applySelection()', 1)[1]
        for forbidden in ('setFilter(', 'setWrap(', 'new osg::Texture2D', 'Checkerboard::fill('):
            self.assertNotIn(forbidden, selection)

    def test_repeat_uvs_double_both_axes_without_mutating_baseline(self):
        self.assertIn('for (const auto& uv : *uvs) repeatUVs->push_back(osg::Vec2(uv.x()*2.0f, uv.y()*2.0f));', SCENE)
        self.assertIn('repeatGeometry->setVertexAttribArray(6, repeatUVs.get(), osg::Array::BIND_PER_VERTEX);', SCENE)
        self.assertIn('repeatGeometry->setVertexArray(vertices.get());', SCENE)
        self.assertIn('repeatGeometry->addPrimitiveSet(indices.get());', SCENE)
        self.assertIn('osg::Node* selected = textured && textureProfile == 2 ? repeatGeode.get() : baseGeode.get();', SCENE)
        self.assertEqual(SCENE.count('uvs->push_back('), 1)
        self.assertEqual(SCENE.count('repeatUVs->push_back('), 1)

    def test_dpad_right_is_edge_triggered_primed_and_does_not_override_cube_or_clear(self):
        self.assertIn('bool right = pad.dpad.right.isPressed;', MAIN)
        controls = MAIN.split('if (controller != previousController || !buttonsPrimed)', 1)[1].split('if (renderer && !renderer->sceneAvailable)', 1)[0]
        self.assertEqual(controls.count('previousRight = right;'), 2)
        self.assertIn('previousRight = right;', controls.split('} else {', 1)[0])
        self.assertIn('if (right && !previousRight && renderer && renderer->osgScene)\n            renderer->osgScene->cycleTextureProfile();', controls)
        cycle = SCENE.split('void cycleTextureProfile()', 1)[1].split('bool isTextured()', 1)[0]
        self.assertIn('textureProfile = (textureProfile + 1) % 4;', cycle)
        self.assertIn('applySelection();', cycle)
        self.assertNotIn('textured =', cycle)
        self.assertNotIn('clearOnly', cycle)
        self.assertIn('unsigned textureProfile = 3;', SCENE)

    def test_profile_names_and_first_use_evidence_are_exported_without_pass_claim(self):
        for name in ('NEAREST/CLAMP_TO_EDGE (1x1)', 'LINEAR/CLAMP_TO_EDGE (1x1)', 'NEAREST/REPEAT (2x2)'):
            self.assertIn(name, SCENE)
        for key in ('texture_profile', 'texture_profiles', 'first_traversal_completed'):
            self.assertIn('@"' + key + '"', MAIN)
        self.assertIn('Active texture profile: %@', MAIN)
        self.assertIn('D-pad Right: profile', MAIN)
        self.assertIn('OSG selected texture profile:', SCENE)
        self.assertIn('inspect raw GL diagnostics, not a pass certificate', SCENE)

    def test_late_first_use_checks_are_bounded_per_profile_and_restore_after_draw(self):
        frame = SCENE.split('void frame(double time, int w, int h)', 1)[1]
        self.assertIn('const bool lateProfileCheck = frames >= 5 && textured && !profileRendered[textureProfile];', frame)
        self.assertIn('bool profileRendered[4] = {false, false, false, false};', SCENE)
        enable = frame.index('setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE)')
        draw = frame.index('viewer->frame(time);')
        restore = frame.index('setCheckForGLErrors(osg::State::ONCE_PER_FRAME)')
        mark = frame.index('profileRendered[profile] = true;')
        self.assertLess(enable, draw)
        self.assertLess(draw, restore)
        self.assertLess(restore, mark)
        self.assertEqual(frame.count('if (lateProfileCheck)'), 2)
        self.assertIn('const bool visible = textured && (profile == textureProfile || (textureProfile == 3 && profile == 1));', frame)
        self.assertIn('if (!visible || profileRendered[profile]) continue;', frame)
        self.assertIn('KHR_debug initial window is not rearmed', frame)
        # No extra error poll and no KHR re-registration: the original lifecycle
        # and five-frame callback ownership remain covered by test_gl_debug.py.
        self.assertNotIn('glGetError', frame)
        self.assertNotIn('profileRendered[textureProfile] = false', SCENE)

    def test_mipmapped_profile_is_exactly_one_additional_fixed_texture(self):
        block = SCENE.split('// Build #12:', 1)[1].split('applySelection();', 1)[0]
        self.assertEqual(block.count('new osg::Texture2D(image.get())'), 1)
        for text in ('mipTexture->setUnRefImageDataAfterApply(false);',
                     'mipTexture->setFilter(osg::Texture::MIN_FILTER, osg::Texture::LINEAR_MIPMAP_LINEAR);',
                     'mipTexture->setFilter(osg::Texture::MAG_FILTER, osg::Texture::LINEAR);',
                     'mipTexture->setWrap(osg::Texture::WRAP_S, osg::Texture::CLAMP_TO_EDGE);',
                     'mipTexture->setWrap(osg::Texture::WRAP_T, osg::Texture::CLAMP_TO_EDGE);',
                     'mipTexture->setLODBias(0.0f);', 'mipTexture->setUseHardwareMipMapGeneration(true);',
                     'profileStates[3]->setTextureAttribute(0, mipTexture.get(), osg::StateAttribute::ON);'):
            self.assertIn(text, block)
        self.assertEqual(SCENE.count('osg::Texture::LINEAR_MIPMAP_LINEAR'), 1)
        self.assertEqual(SCENE.count('setUseHardwareMipMapGeneration(true)'), 1)
        self.assertIn('profileStates[4]', SCENE)
        self.assertIn('textured && textureProfile == 3 ? minificationGroup.get() : selected', SCENE)

    def test_hardware_gate_precedes_traversal_and_does_not_claim_observation(self):
        frame = SCENE.split('void frame(double time, int w, int h)', 1)[1]
        gate = frame.split('if (!mipmapCapabilityChecked)', 1)[1].split('model->setMatrix(osg::Matrix::identity());', 1)[0]
        self.assertIn('extensions && extensions->glGenerateMipmap', gate)
        self.assertIn('extensions->isGenerateMipMapSupported || extensions->isFrameBufferObjectSupported', gate)
        self.assertIn('if (!mipmapCapabilitySupported || !mipmapEntryPointAvailable)', gate)
        self.assertIn('throw std::runtime_error("Mipmap profile blocked:', gate)
        self.assertIn('CPU fallback is not accepted', gate)
        self.assertLess(frame.index('if (!mipmapCapabilityChecked)'), frame.index('viewer->frame(time);'))
        self.assertIn('@"generate_call_observed": [NSNull null]', MAIN)
        self.assertIn('@"capability_checked"', MAIN)
        self.assertIn('@"entry_point_available"', MAIN)
        self.assertIn('actual execution UNKNOWN (not intercepted)', SCENE)
        self.assertNotIn('glGenerateMipmap(', MAIN + SCENE)

    def test_expected_mip_calculation_contract_and_export(self):
        self.assertIn('for (; extent; extent >>= 1) ++count;', CHECKER)
        self.assertIn('while (level-- && extent > 1) extent >>= 1;', CHECKER)
        self.assertIn('if (!extent) return 0;', CHECKER)
        self.assertIn('Checkerboard::mipLevelCount(Checkerboard::Width)', MAIN)
        self.assertIn('Checkerboard::mipDimension(Checkerboard::Width, level)', MAIN)
        self.assertIn('@"expected_dimensions": expectedMipDimensions', MAIN)
        # Actual helper execution (including zero, one, NPOT and chain sizes)
        # is part of the optional C++ pixel fixture above, not this source check.

    def test_state_initializer_precedes_capability_reads_and_uses_state_ownership(self):
        frame = SCENE.split('void frame(double time, int w, int h)', 1)[1]
        gate = frame.split('if (!mipmapCapabilityChecked)', 1)[1].split('model->setMatrix(osg::Matrix::identity());', 1)[0]
        reads = [m.start() for m in re.finditer(re.escape('state->get<osg::GLExtensions>()'), gate)]
        self.assertEqual(len(reads), 2)
        initialize = gate.index('state->initializeExtensionProcs();')
        self.assertLess(reads[0], initialize)
        self.assertLess(initialize, reads[1])
        self.assertLess(reads[1], gate.index('mipmapEntryPointAvailable ='))
        self.assertIn('if (!extensions) {', gate[:initialize])
        self.assertIn('if (!extensions)\n                    throw std::runtime_error(', gate[reads[1]:])
        self.assertLess(gate.index('hardware capability remains untested'), gate.index('mipmapCapabilityChecked = true;'))
        self.assertNotIn('GLExtensions::Get(', SCENE)
        self.assertNotIn('new osg::GLExtensions', SCENE)
        self.assertIn('before initialization:', gate)
        self.assertIn('after initialization:', gate)
        self.assertIn('unavailable after State initialization', gate)

    def test_owning_context_check_dominates_initialization_and_failed_gate_draw(self):
        draw = MAIN.split('bool draw(double seconds, bool clearOnly)', 1)[1].split('~Renderer()', 1)[0]
        self.assertLess(draw.index('eglGetCurrentContext() != context || eglGetCurrentDisplay() != display'),
                        draw.index('osgScene->frame(seconds, width, height);'))
        self.assertIn('throw std::runtime_error("External ANGLE context is not current before OSG frame")', draw)
        self.assertNotIn('eglMakeCurrent(', draw)
        frame = SCENE.split('void frame(double time, int w, int h)', 1)[1]
        self.assertLess(frame.index('state->initializeExtensionProcs();'), frame.index('viewer->frame(time);'))
        self.assertLess(frame.index('CPU fallback is not accepted'), frame.index('viewer->frame(time);'))
        self.assertLess(draw.index('catch (...) { stopDebug("OSG traversal failure"); throw; }'),
                        draw.index('eglSwapBuffers(display, surface)'))
        tick = MAIN.split('- (void)tick:', 1)[1]
        self.assertIn('self.failure = Text(error.what()); Log(self.failure); [self deactivate]; return;', tick)

    def test_actual_gate_control_flow_cpp_fixture(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable; State initialization gate fixture not executed')
        gate = SCENE.split('if (!mipmapCapabilityChecked)', 1)[1].split('model->setMatrix(osg::Matrix::identity());', 1)[0]
        # Execute the production gate body with synthetic State/GL declarations.
        # This tests control flow, not the actual pinned State implementation/ABI.
        fixture = r'''
#include <cassert>
#include <stdexcept>
#include <string>
namespace osg { struct GLExtensions {
    bool glGenerateMipmap = true;
    bool isGenerateMipMapSupported = true;
    bool isFrameBufferObjectSupported = false;
}; }
struct State {
    osg::GLExtensions owned;
    osg::GLExtensions* object = nullptr;
    bool create = true;
    unsigned calls = 0;
    template<class T> T* get() { return object; }
    void initializeExtensionProcs() { ++calls; if (create) object = &owned; }
};
struct Window { State state; State* getState() { return &state; } };
struct Logger { void write(const std::string&) {} };
struct Gate {
    Window storage; Window* window = &storage;
    Logger logger; Logger* log = &logger;
    bool mipmapCapabilityChecked = false;
    bool mipmapEntryPointAvailable = false;
    bool mipmapCapabilitySupported = false;
    unsigned renders = 0;
    void frame() { if (!mipmapCapabilityChecked) GATE_BODY ++renders; }
};
int main() {
    Gate fresh; fresh.frame(); fresh.frame();
    assert(fresh.storage.state.calls == 1 && fresh.renders == 2);
    assert(fresh.mipmapCapabilityChecked && fresh.mipmapCapabilitySupported && fresh.mipmapEntryPointAvailable);
    Gate existing; existing.storage.state.object = &existing.storage.state.owned; existing.frame();
    assert(existing.storage.state.calls == 0 && existing.renders == 1);
    Gate absent; absent.storage.state.create = false;
    try { absent.frame(); assert(false); } catch (const std::runtime_error& e) {
        assert(std::string(e.what()).find("remains untested") != std::string::npos);
    }
    assert(absent.renders == 0 && !absent.mipmapCapabilityChecked);
    Gate unsupported; unsupported.storage.state.owned.isGenerateMipMapSupported = false;
    try { unsupported.frame(); assert(false); } catch (const std::runtime_error& e) {
        assert(std::string(e.what()).find("after State initialization") != std::string::npos);
    }
    assert(unsupported.renders == 0 && unsupported.mipmapCapabilityChecked && !unsupported.mipmapCapabilitySupported);
    Gate missing; missing.storage.state.owned.glGenerateMipmap = false;
    try { missing.frame(); assert(false); } catch (const std::runtime_error&) {}
    assert(missing.renders == 0 && !missing.mipmapEntryPointAvailable);
    Gate fbo; fbo.storage.state.owned.isGenerateMipMapSupported = false;
    fbo.storage.state.owned.isFrameBufferObjectSupported = true; fbo.frame();
    assert(fbo.renders == 1 && fbo.mipmapCapabilitySupported);
}
'''.replace('GATE_BODY', gate)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'state-gate.cpp'
            binary = Path(directory) / 'state-gate.exe'
            source.write_text(fixture, encoding='utf-8')
            subprocess.run([compiler, '-std=c++11', str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_comparison_pairs_are_preallocated_and_equivalent_except_filter(self):
        block = SCENE.split('minificationGroup = new osg::Group;', 1)[1].split('applySelection();', 1)[0]
        self.assertIn('for (unsigned i = 0; i < 6; ++i)', block)
        self.assertIn('profileStates[i % 2 == 0 ? 3 : 1]', block)
        self.assertIn('comparisonModels[i]->addChild(baseGeode.get());', block)
        self.assertIn('const unsigned row = i / 2;', SCENE)
        self.assertIn('osg::Matrix::scale(scales[row], scales[row], scales[row])', SCENE)
        self.assertIn('screenRight * (i % 2 == 0 ? -1.65f : 1.65f)', SCENE)
        self.assertIn('screenUp * rowOffsets[row]', SCENE)
        self.assertIn('MIPMAP — LEFT    |    LINEAR — RIGHT', MAIN)
        scales = [float(x.rstrip('f')) for x in re.search(r'const float scales\[3\] = \{([^}]+)\}', SCENE)[1].split(',')]
        self.assertEqual(scales, [.40, .060, .032])
        eye = (3, -5, 3)
        for axis in ('screenRight', 'screenUp'):
            vector = [float(x.rstrip('f')) for x in re.search(r'const osg::Vec3 ' + axis + r'\(([^)]+)\)', SCENE)[1].split(',')]
            self.assertAlmostEqual(sum(a*b for a,b in zip(vector,eye)), 0, places=5)
            self.assertAlmostEqual(sum(a*a for a in vector), 1, places=5)
        # Conservative projected bounding diameter: smallest cube is well below
        # 32 pixels even for a 1600-pixel drawable height; actual GPU LOD is unknown.
        radius = math.sqrt(3)*scales[-1]
        pixels = 1600*radius/((math.sqrt(43)-radius)*math.tan(math.radians(25)))
        self.assertLess(pixels, 32)

    def test_projected_pairs_remain_visible_minified_and_clear_of_overlay(self):
        def values(pattern):
            return [float(v.rstrip('f')) for v in re.search(pattern, SCENE)[1].split(',')]
        scales = values(r'const float scales\[3\] = \{([^}]+)\}')
        rows = values(r'const float rowOffsets\[3\] = \{([^}]+)\}')
        right = values(r'const osg::Vec3 screenRight\(([^)]+)\)')
        up = values(r'const osg::Vec3 screenUp\(([^)]+)\)')
        self.assertEqual(rows, [.35, -.65, -1.40])
        self.assertIn('setViewMatrixAsLookAt(osg::Vec3(3,-5,3)', SCENE)
        self.assertIn('setProjectionMatrixAsPerspective(50.0, double(w)/h, 0.1, 100.0)', SCENE)
        # Sample the actual geometry constants under the fixed camera. These are
        # mathematical raster estimates, not measured pixels or actual sampled LOD.
        eye = (3, -5, 3)
        distance = math.sqrt(43)
        forward = [-v / distance for v in eye]
        corners = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        edges = [(i, j) for i, a in enumerate(corners) for j, b in enumerate(corners)
                 if i < j and sum(x != y for x, y in zip(a, b)) == 1]
        self.assertEqual(len(edges), 12)
        dot = lambda a, b: sum(x*y for x, y in zip(a, b))
        focal = 1290 / (2 * math.tan(math.radians(25)))
        row_bounds = []
        edge_ranges = []
        for scale, row in zip(scales, rows):
            row_y, lengths, column_x = [], [], [[], []]
            for column, side in enumerate((-1.65, 1.65)):
                center = [r*side + u*row for r, u in zip(right, up)]
                self.assertAlmostEqual(dot(center, forward), 0, places=5)
                for degree in range(0, 360, 2):
                    c, s = math.cos(math.radians(degree)), math.sin(math.radians(degree))
                    projected = []
                    for x, y, z in corners:
                        rotated = (scale*(c*x-s*y), scale*(s*x+c*y), scale*z)
                        relative = [a+b-e for a, b, e in zip(rotated, center, eye)]
                        depth = dot(relative, forward)
                        self.assertGreater(depth, .1)
                        px = 2796/2 + focal*dot(relative, right)/depth
                        py = 1290/2 - focal*dot(relative, up)/depth
                        projected.append((px, py))
                        row_y.append(py)
                        column_x[column].append(px)
                    lengths.extend(math.dist(projected[a], projected[b]) for a, b in edges)
            self.assertLess(max(column_x[0]), min(column_x[1]))
            row_bounds.append((min(row_y), max(row_y)))
            edge_ranges.append((min(lengths), max(lengths)))
        self.assertGreater(edge_ranges[0][1], 150)  # legible large reference
        self.assertLess(edge_ranges[1][1] * 1440/1290, 32)  # still minified at H=1440
        self.assertGreater(edge_ranges[2][0], 7)  # small edges no longer ~1-5 px
        self.assertLess(edge_ranges[2][1], 16)
        self.assertGreater(row_bounds[0][0] / 3, 88 + 8 + 20)  # allow top safe inset
        self.assertLess(row_bounds[0][1], row_bounds[1][0])
        self.assertLess(row_bounds[1][1], row_bounds[2][0])
        self.assertLess(row_bounds[2][1] / 3, 430 - 34 - 8)

    def test_compact_overlay_labels_capability_unknown_call_and_failures(self):
        layout = MAIN.split('- (void)viewDidLoad', 1)[1].split('- (void)exportResults', 1)[0]
        overlay = MAIN.split('- (void)updateOverlay', 1)[1].split('- (void)activate', 1)[0]
        for text in ('self.overlay.numberOfLines = 6;', 'monospacedSystemFontOfSize:10',
                     'self.overlay.lineBreakMode = NSLineBreakByTruncatingTail;',
                     'self.overlay.trailingAnchor constraintEqualToAnchor:',
                     'self.overlay.heightAnchor constraintLessThanOrEqualToConstant:88'):
            self.assertIn(text, layout)
        for text in ('MIPMAP — LEFT', 'LINEAR — RIGHT', 'Active texture profile:',
                     'Mipmap capability:', 'Actual generation call: UNKNOWN',
                     'Display FPS: unmeasured', 'App GL errors:', 'WARN+:', 'BLOCKED:', 'Clear fallback:'):
            self.assertIn(text, overlay)
        self.assertIn('!clearOnly && scene && scene->isTextured()', overlay)
        self.assertIn('scene->mipmapCapabilitySupported && scene->mipmapEntryPointAvailable', overlay)
        for status in ('NOT TESTED', 'AVAILABLE', 'UNAVAILABLE'):
            self.assertIn('@"' + status + '"', overlay)
        self.assertNotIn('Log(', overlay)
        self.assertNotIn('new osg::', overlay)
        tick = MAIN.split('- (void)tick:', 1)[1]
        self.assertLess(tick.index('if (start - rateStart >= 1.0)'), tick.index('[self updateOverlay]'))

    def test_mipmap_startup_and_comparator_diagnostic_inventory(self):
        self.assertIn('unsigned textureProfile = 3;', SCENE)
        self.assertIn('for (unsigned profile = 0; profile < 4; ++profile)', MAIN)
        self.assertIn('profile == textureProfile || (textureProfile == 3 && profile == 1)', SCENE)
        self.assertIn('OSG texture profile first traversal completed: ") + textureProfileName(profile)', SCENE)
        self.assertIn('return profile < 4 ? names[profile]', SCENE)

    def test_locally_available_pinned_mipmap_sources(self):
        reference = Path(os.environ.get('OSG_PINNED_SOURCE_REFERENCE',
                         'C:/Users/austi/Downloads/OpenMW-OSG-pinned-source'))
        paths = {name: reference / 'src/osg' / name for name in ('Texture2D.cpp','Texture.cpp','GLExtensions.cpp')}
        if not all(path.is_file() for path in paths.values()):
            self.skipTest('Original pinned reference files not available; no download attempted')
        hashes = {'Texture2D.cpp': '4373e4c82137e42076d2416eae046230fcf01eca0daabad72abb5cafbbd01268',
                  'Texture.cpp': '294ea04733def9aa072d0f3563dc965dbb3aac9f6dd4afc3853db5a17d86a2f3',
                  'GLExtensions.cpp': 'bd2cb7bc27918acc902848fcde5e1ecc03f6530acfe614e38d3d4740f304a7cc'}
        for name, path in paths.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), hashes[name])
        source = paths['Texture2D.cpp'].read_text()
        self.assertIn('applyTexImage2D_load(state,GL_TEXTURE_2D,image.get(),', source)
        self.assertIn('applyTexImage2D_subload(state,GL_TEXTURE_2D,image.get(),', source)
        self.assertIn('getModifiedCount(contextID) != _image->getModifiedCount()', source)
        texture = paths['Texture.cpp'].read_text()
        self.assertIn('useGluBuildMipMaps = mipmappingRequired && (!useHardwareMipMapGeneration && !image->isMipmap())', texture)
        self.assertIn('ext->glGenerateMipmap(textureObject->target());', texture)


if __name__ == '__main__':
    unittest.main()
