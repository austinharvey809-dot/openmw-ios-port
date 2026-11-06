"""Source-specific shader/program/buffer KHR_debug aliases; no downloaded fixtures."""
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
    def test_aliases_are_only_their_own_source_properties_in_osg_target_directory(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        for source, token in (('Shader.cpp', 'GL_SHADER'), ('Program.cpp', 'GL_PROGRAM'),
                              ('BufferObject.cpp', 'GL_BUFFER')):
            assignment = (f'set_property(SOURCE "${{OSG_SOURCE}}/src/osg/{source}" TARGET_DIRECTORY osg\n'
                          f'    APPEND PROPERTY COMPILE_DEFINITIONS "{token}={token}_KHR")')
            with self.subTest(source=source):
                self.assertIn(assignment, cmake)
                self.assertLess(cmake.index('add_subdirectory("${OSG_SOURCE}"'), cmake.index(assignment))
                self.assertLess(cmake.index('check_angle_gl_header_types()'), cmake.index(assignment))
                # One source property and one scoped probe, no global alias.
                self.assertEqual(cmake.count(f'"{token}={token}_KHR"'), 1)
                self.assertEqual(cmake.count(f'"-D{token}={token}_KHR"'), 1)
                for command in ('add_compile_definitions(', 'target_compile_definitions(', 'add_definitions('):
                    for value in cmake.split(command)[1:]:
                        self.assertNotIn(token + '=', value.split(')', 1)[0])

    def test_native_probe_requires_the_khr_token_and_exact_identifier_value(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        probe = cmake.split('function(check_angle_gl_header_types)', 1)[1].split('endfunction()', 1)[0]
        self.assertIn('set(CMAKE_REQUIRED_DEFINITIONS "-DGL_SHADER=GL_SHADER_KHR" "-DGL_PROGRAM=GL_PROGRAM_KHR" "-DGL_BUFFER=GL_BUFFER_KHR")', probe)
        self.assertIn('static_assert(GL_SHADER_KHR == 0x82E1 && GL_SHADER == GL_SHADER_KHR,', probe)
        self.assertIn('static_assert(GL_PROGRAM_KHR == 0x82E2 && GL_PROGRAM == GL_PROGRAM_KHR,', probe)
        self.assertIn('static_assert(GL_BUFFER_KHR == 0x82E0 && GL_BUFFER == GL_BUFFER_KHR,', probe)
        self.assertIn('unset(OSG_ANGLE_GLES3_HEADER_TYPES_OK CACHE)', probe)

    def test_no_new_source_overlay_or_relaxed_source_inventory(self):
        self.assertEqual(set(LOCK['source_sha256']), {'CMakeLists.txt', 'src/osg/GLExtensions.cpp'})
        for source in ('Shader.cpp', 'Program.cpp', 'BufferObject.cpp'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'Unaudited overlay file'):
                overlay('src/osg/' + source, 'original')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'ios-osg-overlay.json').write_text(json.dumps({
                'revision': LOCK['revision'], 'overlay_version': LOCK['overlay_version'],
                'files': dict(LOCK['source_sha256'])}), encoding='utf-8')
            for name in ('Shader.cpp', 'Program.cpp', 'BufferObject.cpp'):
                changed = '\n'.join([*LOCK['source_sha256'], 'src/osg/' + name])
                with patch('check_osg_source.subprocess.run', side_effect=[
                        SimpleNamespace(stdout=LOCK['revision']), SimpleNamespace(stdout=changed)]):
                    with self.subTest(source=name), self.assertRaisesRegex(ValueError, 'Unexpected OSG tracked modifications'):
                        check_osg_source.check(source)

    def test_cpp11_missing_core_token_reproducer_and_khr_alias(self):
        compiler = next((path for name in ('clang++', 'g++', 'c++')
                         if (path := shutil.which(name))), None)
        if compiler is None:
            self.skipTest('No local C++ compiler; actual ANGLE declaration probe runs on macOS')
        # Synthetic declaration fixture, not a claim of compiling pinned OSG/ANGLE.
        template = '''
typedef unsigned int GLenum;
struct Extensions { void debugObjectLabel(GLenum, unsigned int, const char*); };
struct Object { const char* getName(); };
void label(Extensions* _extensions, unsigned int handle, Object* object) {
    _extensions->debugObjectLabel(TOKEN, handle, object->getName());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'shader-label.cpp'
            for token, value in (('GL_SHADER', '0x82E1'), ('GL_PROGRAM', '0x82E2'), ('GL_BUFFER', '0x82E0')):
                body = template.replace('TOKEN', token)
                for name, header, alias, expected in (
                        ('original missing core token', f'#define {token}_KHR {value}\n', False, False),
                        ('source alias', f'#define {token}_KHR {value}\n', True, True),
                        ('missing KHR token', '', True, False),
                        ('wrong KHR value', f'#define {token}_KHR 0xFFFF\n', True, False)):
                    with self.subTest(token=token, name=name):
                        source.write_text(header + body + f'\nstatic_assert({token}_KHR == {value}, "identifier");\n', encoding='utf-8')
                        command = [compiler, '-std=c++11', '-fsyntax-only']
                        if alias:
                            command.append(f'-D{token}={token}_KHR')
                        result = subprocess.run([*command, str(source)], capture_output=True, text=True)
                        self.assertEqual(result.returncode == 0, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
