"""Host-only negative device-product and build-plan regression fixtures."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
from unittest.mock import patch

import build_angle
from package_ios import Entry, ValidationError, validate_bundle
from test_package_ios import binary, bundle, EXECUTABLE
from validate_dependency import frameworks, resolve, ROOT


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pin = build_angle.lock()
        for name, data in {
            "angle-lock.json": (ROOT / "data/angle-lock.json").read_bytes(),
            "args.gn": (ROOT / "args.gn").read_bytes(),
            "Licenses/LICENSE": b"upstream license fixture",
            "angle-build.json": json.dumps({"angle_revision": self.pin["angle_revision"],
                "target": "arm64-apple-ios18.0", "metal_only": True,
                "validation": "device-binary-and-sdk-passed", "libraries": {
                    "egl": "Frameworks/libEGL.framework/libEGL", "gles": "Frameworks/libGLESv2.framework/libGLESv2"}}).encode(),
        }.items():
            self.write(name, data)
        for name in ("libEGL", "libGLESv2"):
            self.write(f"Frameworks/{name}.framework/{name}", binary(filetype=6, install_name=f"@rpath/{name}.framework/{name}"))
            self.write(f"Frameworks/{name}.framework/Info.plist", plistlib.dumps({"CFBundleExecutable": name,
                "CFBundlePackageType": "FMWK", "CFBundleSupportedPlatforms": ["iPhoneOS"]}))

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def hashes(self):
        hashes = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file() and p.name != "package-hashes.json"}
        self.write("package-hashes.json", json.dumps(hashes).encode())

    def test_pinned_plan_never_starts_downloads_without_opt_in(self):
        with patch("subprocess.run", side_effect=AssertionError("network/build invoked")), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(build_angle.main(["--workspace", str(self.root / "work"), "--output", str(self.root / "out")]), 0)
        plan = json.loads(output.getvalue())
        self.assertFalse(plan["downloads_enabled"])
        self.assertEqual(plan["targets"], ["libEGL", "libGLESv2"])
        self.assertFalse((self.root / "work").exists())

    def test_windows_download_opt_in_is_still_rejected(self):
        with patch("platform.system", return_value="Windows"), patch("subprocess.run", side_effect=AssertionError), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_angle.main(["--workspace", str(self.root / "work"), "--output", str(self.root / "out"), "--allow-downloads"])

    def test_two_device_frameworks_resolve_and_tampering_is_rejected(self):
        self.assertEqual(len(frameworks(self.root)), 2)
        self.hashes()
        # Output goes outside the immutable package.
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "resolved.cmake"
            resolve(self.root, destination)
            self.assertIn("ANGLE_EGL_LIBRARY", destination.read_text())
            self.write("Licenses/LICENSE", b"tampered")
            with self.assertRaisesRegex(ValidationError, "digest mismatch"):
                resolve(self.root, destination)

    def test_mac_simulator_wrong_cpu_newer_os_and_unsigned_requirement(self):
        for options in ({"platform": 1}, {"platform": 7}, {"cpu": 0x01000007}, {"minimum": 0x1A0000},
                        {"extra": (struct.pack("<IIII", 0x1D, 16, 0, 0),)}):
            with self.subTest(options=options):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL", **options))
                with self.assertRaises(ValidationError): frameworks(self.root)

    def test_unbundled_or_alternate_provider_and_host_rpath_rejected(self):
        for dependency in ("@rpath/missing.dylib", "/System/Library/Frameworks/OpenGLES.framework/OpenGLES", "/opt/homebrew/lib/libEGL.dylib"):
            with self.subTest(dependency=dependency):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL", dependencies=[dependency]))
                with self.assertRaises(ValidationError): frameworks(self.root)
        self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
            install_name="@rpath/libEGL.framework/libEGL", rpaths=["/tmp/host-libs"]))
        with self.assertRaisesRegex(ValidationError, "runtime search"): frameworks(self.root)

    def test_changed_backend_configuration_or_lock_is_rejected(self):
        self.write("args.gn", b'angle_enable_gl = true\n')
        with self.assertRaisesRegex(ValidationError, "GN configuration"): frameworks(self.root)
        self.write("args.gn", (ROOT / "args.gn").read_bytes())
        self.write("angle-lock.json", b'{}')
        with self.assertRaisesRegex(ValidationError, "lock mismatch"): frameworks(self.root)

    def test_ipa_rejects_apple_gles_even_with_valid_sdk_namespace(self):
        files = bundle(dependencies=["/System/Library/Frameworks/OpenGLES.framework/OpenGLES"])
        with self.assertRaisesRegex(ValidationError, "alternate graphics provider"): validate_bundle(files)

    def test_missing_notices_or_wrong_build_provenance_rejected(self):
        files = bundle()
        del files["Licenses/LICENSE"]
        with self.assertRaisesRegex(ValidationError, "licenses"): validate_bundle(files)
        files = bundle()
        files["angle-build.json"] = Entry(b'{"metal_only": false}', EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "provenance"): validate_bundle(files)

    def test_arm64e_app_is_not_accepted_as_generic_arm64(self):
        files = bundle()
        value = bytearray(files["IOSANGLESmoke"].data)
        struct.pack_into("<i", value, 8, 2)
        files["IOSANGLESmoke"] = Entry(bytes(value), EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "CPU subtype"): validate_bundle(files)

    def test_malformed_or_pending_build_provenance_rejected(self):
        for value in (b'[]', b'null', b'invalid', b'{"validation": "pending"}'):
            files = bundle()
            files["angle-build.json"] = Entry(value, EXECUTABLE)
            with self.assertRaisesRegex(ValidationError, "provenance"): validate_bundle(files)


if __name__ == "__main__":
    unittest.main()
