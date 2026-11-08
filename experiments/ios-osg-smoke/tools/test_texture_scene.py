"""Texture scene contracts plus an optional executable test of the actual pixel helper.

Source checks do not prove native OSG/GLES behavior; the C++ fixture needs a compiler.
"""
from pathlib import Path
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
            self.assertEqual(SCENE.count(allocation), 2 if allocation in ('new osg::Program', 'new osg::Texture2D') else 1)
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
        self.assertLess(SCENE.index('model->setStateSet(texturedState.get());'), SCENE.index('viewer->realize();'))
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
        variants = SCENE.split('for (unsigned profile = 1; profile < 3; ++profile)', 1)[1].split('model->setStateSet(texturedState.get());', 1)[0]
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
        self.assertIn('model->setChild(0, textured && textureProfile == 2 ? repeatGeode.get() : baseGeode.get());', SCENE)
        self.assertEqual(SCENE.count('uvs->push_back('), 1)
        self.assertEqual(SCENE.count('repeatUVs->push_back('), 1)

    def test_dpad_right_is_edge_triggered_primed_and_does_not_override_cube_or_clear(self):
        self.assertIn('bool right = pad.dpad.right.isPressed;', MAIN)
        controls = MAIN.split('if (controller != previousController || !buttonsPrimed)', 1)[1].split('if (renderer && !renderer->sceneAvailable)', 1)[0]
        self.assertEqual(controls.count('previousRight = right;'), 2)
        self.assertIn('previousRight = right;', controls.split('} else {', 1)[0])
        self.assertIn('if (right && !previousRight && renderer && renderer->osgScene)\n            renderer->osgScene->cycleTextureProfile();', controls)
        cycle = SCENE.split('void cycleTextureProfile()', 1)[1].split('bool isTextured()', 1)[0]
        self.assertIn('textureProfile = (textureProfile + 1) % 3;', cycle)
        self.assertIn('applySelection();', cycle)
        self.assertNotIn('textured =', cycle)
        self.assertNotIn('clearOnly', cycle)
        self.assertIn('unsigned textureProfile = 0;', SCENE)

    def test_profile_names_and_first_use_evidence_are_exported_without_pass_claim(self):
        for name in ('NEAREST/CLAMP_TO_EDGE (1x1)', 'LINEAR/CLAMP_TO_EDGE (1x1)', 'NEAREST/REPEAT (2x2)'):
            self.assertIn(name, SCENE)
        for key in ('texture_profile', 'texture_profiles', 'first_traversal_completed'):
            self.assertIn('@"' + key + '"', MAIN)
        self.assertIn('Selected texture: %@ | D-pad Right: cycle', MAIN)
        self.assertIn('OSG selected texture profile:', SCENE)
        self.assertIn('inspect raw GL diagnostics, not a pass certificate', SCENE)

    def test_late_first_use_checks_are_bounded_per_profile_and_restore_after_draw(self):
        frame = SCENE.split('void frame(double time, int w, int h)', 1)[1]
        self.assertIn('const bool lateProfileCheck = frames >= 5 && textured && !profileRendered[textureProfile];', frame)
        self.assertIn('bool profileRendered[3] = {false, false, false};', SCENE)
        enable = frame.index('setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE)')
        draw = frame.index('viewer->frame(time);')
        restore = frame.index('setCheckForGLErrors(osg::State::ONCE_PER_FRAME)')
        mark = frame.index('profileRendered[textureProfile] = true;')
        self.assertLess(enable, draw)
        self.assertLess(draw, restore)
        self.assertLess(restore, mark)
        self.assertEqual(frame.count('if (lateProfileCheck)'), 2)
        self.assertIn('if (textured && !profileRendered[textureProfile])', frame)
        self.assertIn('KHR_debug initial window is not rearmed', frame)
        # No extra error poll and no KHR re-registration: the original lifecycle
        # and five-frame callback ownership remain covered by test_gl_debug.py.
        self.assertNotIn('glGetError', frame)
        self.assertNotIn('profileRendered[textureProfile] = false', SCENE)


if __name__ == '__main__':
    unittest.main()
