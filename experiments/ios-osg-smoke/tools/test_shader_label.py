"""Shader.cpp-only KHR_debug spelling compatibility; no downloaded fixtures."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_osg_source
from prepare_osg import LOCK, ROOT, overlay


class ShaderLabelTests(unittest.TestCase):
    def test_alias_is_only_a_shader_source_property_in_osg_target_directory(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        assignment = ('set_property(SOURCE "${OSG_SOURCE}/src/osg/Shader.cpp" TARGET_DIRECTORY osg\n'
                      '    APPEND PROPERTY COMPILE_DEFINITIONS "GL_SHADER=GL_SHADER_KHR")')
        self.assertIn(assignment, cmake)
        self.assertLess(cmake.index('add_subdirectory("${OSG_SOURCE}"'), cmake.index(assignment))
        # One source property and one scoped declaration probe, no global alias.
        self.assertEqual(cmake.count('"GL_SHADER=GL_SHADER_KHR"'), 1)
        self.assertEqual(cmake.count('"-DGL_SHADER=GL_SHADER_KHR"'), 1)
        for command in ('add_compile_definitions(', 'target_compile_definitions(', 'add_definitions('):
            for value in cmake.split(command)[1:]:
                self.assertNotIn('GL_SHADER=', value.split(')', 1)[0])

    def test_native_probe_requires_the_khr_token_and_exact_identifier_value(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        probe = cmake.split('function(check_angle_gl_header_types)', 1)[1].split('endfunction()', 1)[0]
        self.assertIn('set(CMAKE_REQUIRED_DEFINITIONS "-DGL_SHADER=GL_SHADER_KHR")', probe)
        self.assertIn('static_assert(GL_SHADER_KHR == 0x82E1 && GL_SHADER == GL_SHADER_KHR,', probe)
        self.assertIn('unset(OSG_ANGLE_GLES3_HEADER_TYPES_OK CACHE)', probe)

    def test_no_new_source_overlay_or_relaxed_source_inventory(self):
        self.assertEqual(set(LOCK['source_sha256']), {'CMakeLists.txt', 'src/osg/GLExtensions.cpp'})
        with self.assertRaisesRegex(ValueError, 'Unaudited overlay file'):
            overlay('src/osg/Shader.cpp', 'original')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'ios-osg-overlay.json').write_text(json.dumps({
                'revision': LOCK['revision'], 'overlay_version': LOCK['overlay_version'],
                'files': dict(LOCK['source_sha256'])}), encoding='utf-8')
            changed = '\n'.join([*LOCK['source_sha256'], 'src/osg/Shader.cpp'])
            with patch('check_osg_source.subprocess.run', side_effect=[
                    SimpleNamespace(stdout=LOCK['revision']), SimpleNamespace(stdout=changed)]):
                with self.assertRaisesRegex(ValueError, 'Unexpected OSG tracked modifications'):
                    check_osg_source.check(source)

    def test_cpp11_missing_core_token_reproducer_and_khr_alias(self):
        compiler = next((path for name in ('clang++', 'g++', 'c++')
                         if (path := shutil.which(name))), None)
        if compiler is None:
            self.skipTest('No local C++ compiler; actual ANGLE declaration probe runs on macOS')
        # Synthetic declaration fixture, not a claim of compiling pinned OSG/ANGLE.
        body = '''
typedef unsigned int GLenum;
struct Extensions { void debugObjectLabel(GLenum, unsigned int, const char*); };
struct Shader { const char* getName(); };
void label(Extensions* _extensions, unsigned int _glShaderHandle, Shader* _shader) {
    _extensions->debugObjectLabel(GL_SHADER, _glShaderHandle, _shader->getName());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'shader-label.cpp'
            for name, header, alias, expected in (
                    ('original missing GL_SHADER', '#define GL_SHADER_KHR 0x82E1\n', False, False),
                    ('source alias', '#define GL_SHADER_KHR 0x82E1\n', True, True),
                    ('missing KHR token', '', True, False),
                    ('wrong KHR value', '#define GL_SHADER_KHR 0x82E2\n', True, False)):
                with self.subTest(name=name):
                    source.write_text(header + body + '\nstatic_assert(GL_SHADER_KHR == 0x82E1, "identifier");\n', encoding='utf-8')
                    command = [compiler, '-std=c++11', '-fsyntax-only']
                    if alias:
                        command.append('-DGL_SHADER=GL_SHADER_KHR')
                    result = subprocess.run([*command, str(source)], capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
