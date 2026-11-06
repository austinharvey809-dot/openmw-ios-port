"""Offline app configuration and C++ platform-display argument regression checks."""
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST_CXX = next((compiler for name in ("clang++", "g++", "c++") if (compiler := shutil.which(name))), None)


class ApplicationConfigTests(unittest.TestCase):
    def test_plist_and_xcode_use_the_same_bundle_identifier(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        identifier = re.search(r'set\(_angle_bundle_id "([^"]+)"\)', cmake).group(1)
        self.assertEqual(identifier, "org.openmw.experiments.ios-angle-smoke")
        self.assertIn('MACOSX_BUNDLE_GUI_IDENTIFIER "${_angle_bundle_id}"', cmake)
        self.assertIn('XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${_angle_bundle_id}"', cmake)
        info = plistlib.loads((ROOT / "Info.plist.in").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "${MACOSX_BUNDLE_GUI_IDENTIFIER}")

    @unittest.skipUnless(HOST_CXX, "No host C++ compiler on PATH; native type check runs on CI")
    def test_real_platform_display_call_compiles_and_apple_typed_integer_zero_does_not(self):
        source = (ROOT / "src/main.mm").read_text(encoding="utf-8")
        match = re.search(r"\bdisplay\s*=\s*(getDisplay\s*\([^;]+\));", source)
        self.assertIsNotNone(match, "Cannot locate the app's platform-display call")
        # Only the parameter contract is reproduced, from the pinned eglplatform.h,
        # egl.h and eglext.h: Apple native display=int, EXT native display=void*.
        # This host fixture does not stand in for an iOS build with real headers.
        preamble = """
using EGLenum = unsigned int;
using EGLint = int;
using EGLDisplay = void *;
using EGLNativeDisplayType = int;
using PFNEGLGETPLATFORMDISPLAYEXTPROC = EGLDisplay (*)(EGLenum, void *, const EGLint *);
#define EGL_DEFAULT_DISPLAY static_cast<EGLNativeDisplayType>(0)
constexpr EGLenum EGL_PLATFORM_ANGLE_ANGLE = 0x3202;
EGLDisplay create(PFNEGLGETPLATFORMDISPLAYEXTPROC getDisplay) {
    const EGLint attributes[] = {0};
    EGLDisplay display;
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "egl_display_types.cpp"

            def check(call):
                path.write_text(preamble + "display = " + call + ";\nreturn display;\n}\n", encoding="utf-8")
                return subprocess.run([HOST_CXX, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                       "-pedantic-errors", "-fsyntax-only", str(path)],
                                      check=False, capture_output=True, text=True)

            result = check(match.group(1))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            original = check("getDisplay(EGL_PLATFORM_ANGLE_ANGLE, EGL_DEFAULT_DISPLAY, attributes)")
            self.assertNotEqual(original.returncode, 0, "Typed integer zero unexpectedly accepted as void*")


if __name__ == "__main__":
    unittest.main()
