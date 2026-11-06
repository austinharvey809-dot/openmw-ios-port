"""Missing artifact headers and invalid profile/include choices fail before OSG."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from check_angle_headers import check, main, SELECTED, DEPENDENCIES, LABEL_IDENTIFIERS

ROOT = Path(__file__).resolve().parents[1]


class AngleHeaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.headers = ["#include <GLES3/gl3.h>", "#include <GLES2/gl2ext.h>"]
        for name in (*SELECTED, *DEPENDENCIES):
            path = self.root / "include" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"nonempty inventory fixture, not compiler declarations\n")
        self.extensions = self.root / "include/GLES2/gl2ext.h"
        self.extensions.write_text('#define GL_SHADER_KHR 0x82E1\n#define GL_PROGRAM_KHR 0x82E2\n'
                                   '#define GL_BUFFER_KHR 0x82E0\n', encoding='utf-8')

    def test_selected_core_and_shared_extension_header_exist_without_gl3ext(self):
        self.assertFalse((self.root / "include/GLES3/gl3ext.h").exists())
        result = check(self.root, "GLES3", self.headers)
        self.assertEqual(result["selected_headers"], ["GLES3/gl3.h", "GLES2/gl2ext.h"])
        self.assertEqual(set(result["header_sha256"]), set(SELECTED + DEPENDENCIES))
        self.assertEqual(result["label_identifiers"], LABEL_IDENTIFIERS)

    def test_actual_extension_header_requires_each_exact_label_identifier(self):
        original = self.extensions.read_text(encoding='utf-8')
        for token, expected in LABEL_IDENTIFIERS.items():
            definition = f'#define {token} 0x{expected:X}'
            for replacement in ('', f'#define {token} 0xFFFF',
                                f'// {definition}', f'#define {token} OTHER_TOKEN',
                                definition + '\n' + definition):
                with self.subTest(token=token, replacement=replacement):
                    self.extensions.write_text(original.replace(definition, replacement), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, token):
                        check(self.root, 'GLES3', self.headers)
            self.extensions.write_text(original, encoding='utf-8')

    def test_missing_buffer_identifier_cli_fails_explicitly(self):
        self.extensions.write_text('#define GL_SHADER_KHR 0x82E1\n#define GL_PROGRAM_KHR 0x82E2\n', encoding='utf-8')
        with contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as status:
                main(['--root', str(self.root), '--profile', 'GLES3',
                      '--header', self.headers[0], '--header', self.headers[1]])
        self.assertEqual(status.exception.code, 1)
        self.assertIn('GL_BUFFER_KHR', error.getvalue())
        self.assertIn('0x82e0', error.getvalue())

    def test_every_selected_and_transitive_header_is_required(self):
        for name in (*SELECTED, *DEPENDENCIES):
            path = self.root / "include" / name
            value = path.read_bytes()
            for replacement in (None, b""):
                with self.subTest(name=name, replacement=replacement):
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_bytes(replacement)
                    with self.assertRaisesRegex(ValueError, "Missing, empty"):
                        check(self.root, "GLES3", self.headers)
                    path.write_bytes(value)

    def test_desktop_apple_nonexistent_and_wrong_order_selections_rejected(self):
        for headers in (["#include <GLES3/gl3.h>", "#include <GLES3/gl3ext.h>"],
                        ["#include <GL/gl.h>", "#include <GL/glext.h>"],
                        ["#include <OpenGLES/ES3/gl.h>"], ["#include <GLES2/gl2.h>"],
                        self.headers[::-1], self.headers[:1], self.headers + self.headers[:1],
                        ["#include <../outside.h>"], ['#include "GLES3/gl3.h"'], [""],
                        ["#include <GLES3/gl31.h>", "#include <GLES2/gl2ext.h>"]):
            with self.subTest(headers=headers), self.assertRaisesRegex(ValueError, "include selection"):
                check(self.root, "GLES3", headers)

    def test_wrong_profile_is_not_made_valid_by_available_headers(self):
        for profile in ("GL2", "GLCORE", "GLES2", "GLES3.1", ""):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "Expected GLES3"):
                check(self.root, profile, self.headers)

    def test_missing_artifact_fails_instead_of_using_a_system_include(self):
        with self.assertRaisesRegex(ValueError, "artifact include directory"):
            check(self.root / "absent", "GLES3", self.headers)

    def test_cli_failure_is_explicit(self):
        missing = self.root / "include/GLES2/gl2ext.h"
        missing.unlink()
        with contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as status:
                main(["--root", str(self.root), "--profile", "GLES3", "--header", self.headers[0], "--header", self.headers[1]])
        self.assertEqual(status.exception.code, 1)
        self.assertIn("GLES2/gl2ext.h", error.getvalue())

    def test_cmake_checks_real_selections_and_types_before_adding_osg(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('set(OPENGL_PROFILE "GLES3"', cmake)
        self.assertIn('set(OPENGL_HEADER1 "#include <GLES3/gl3.h>"', cmake)
        self.assertIn('set(OPENGL_HEADER2 "#include <GLES2/gl2ext.h>"', cmake)
        self.assertIn('--header "${OPENGL_HEADER1}" --header "${OPENGL_HEADER2}" COMMAND_ERROR_IS_FATAL ANY', cmake)
        self.assertLess(cmake.index("tools/check_angle_headers.py"), cmake.index('add_subdirectory("${OSG_SOURCE}"'))
        self.assertLess(cmake.index("check_angle_gl_header_types()"), cmake.index('add_subdirectory("${OSG_SOURCE}"'))
        self.assertIn('set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)', cmake)
        self.assertIn('set(CMAKE_CXX_STANDARD 11)', cmake)
        self.assertIn('PFNGLGENVERTEXARRAYSOESPROC', cmake)
        self.assertIn('unset(OSG_ANGLE_GLES3_HEADER_TYPES_OK CACHE)', cmake)
        self.assertIn('FATAL_ERROR "Selected ANGLE GLES3/extension declarations failed', cmake)


if __name__ == "__main__":
    unittest.main()
