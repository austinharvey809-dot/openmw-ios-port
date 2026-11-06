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
from package_ios import Entry, ValidationError, expand_path, validate_bundle, validate_ipa, write_ipa
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

    def test_chromium_device_framework_rpaths_and_peer_dependency_accepted(self):
        rpaths = ["@executable_path/Frameworks", "@loader_path/Frameworks"]
        for name in ("libEGL", "libGLESv2"):
            self.write(f"Frameworks/{name}.framework/{name}", binary(filetype=6,
                install_name=f"@rpath/{name}.framework/{name}", rpaths=rpaths,
                dependencies=["@rpath/libGLESv2.framework/libGLESv2"] if name == "libEGL" else []))
        products = frameworks(self.root)
        self.assertEqual(len(products), 2)
        for _, details in products.values():
            self.assertEqual(details["rpaths"], rpaths)  # Validate, never rewrite upstream binaries.
        self.hashes()
        with tempfile.TemporaryDirectory() as directory:
            resolve(self.root, Path(directory) / "resolved.cmake")

    def test_existing_exact_framework_rpaths_remain_accepted(self):
        for runpath in ("@loader_path", "@loader_path/..", "@executable_path/Frameworks", "@loader_path/Frameworks"):
            with self.subTest(runpath=runpath):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL", rpaths=[runpath]))
                self.assertEqual(len(frameworks(self.root)), 2)

    def test_framework_rpath_allowlist_rejects_host_unsafe_and_prefix_variants(self):
        for runpath in ("/tmp/host-libs", "/opt/homebrew/lib", "/usr/lib",
                        "/Users/runner/work/build", "/Applications/Xcode.app/Frameworks",
                        "Frameworks", "@rpath/Frameworks", "@unknown/Frameworks",
                        "@loader_path/Frameworks/..", "@loader_path/Frameworks/extra",
                        "@loader_path/../../../../outside", "@executable_path/Frameworks/../..",
                        "@executable_path/Frameworks-extra", "@loader_path\\Frameworks"):
            with self.subTest(runpath=runpath):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL",
                    rpaths=["@executable_path/Frameworks", runpath]))
                with self.assertRaisesRegex(ValidationError, "runtime search paths"):
                    frameworks(self.root)

    def test_accepted_rpaths_do_not_relax_install_names(self):
        for name in (None, "@rpath/libEGL.dylib", "@rpath/libGLESv2.framework/libGLESv2",
                     "@loader_path/libEGL", "/tmp/libEGL.framework/libEGL",
                     "@rpath/libEGL.framework/Versions/A/libEGL"):
            with self.subTest(name=name):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6, install_name=name,
                    rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"]))
                with self.assertRaisesRegex(ValidationError, "install name"):
                    frameworks(self.root)

    def test_accepted_rpaths_do_not_relax_dependencies(self):
        for dependency in ("@rpath/Missing.framework/Missing", "@rpath/libGLESv2.dylib",
                           "@loader_path/../libGLESv2.framework/libGLESv2",
                           "/opt/homebrew/lib/libEGL.dylib",
                           "/System/Library/Frameworks/OpenGLES.framework/OpenGLES",
                           "@rpath/MoltenVK.framework/MoltenVK"):
            with self.subTest(dependency=dependency):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL", dependencies=[dependency],
                    rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"]))
                with self.assertRaises(ValidationError): frameworks(self.root)

    def test_accepted_rpaths_do_not_relax_device_binary_or_plist_checks(self):
        for options in ({"platform": 1}, {"platform": 7}, {"cpu": 0x01000007}, {"minimum": 0x1A0000},
                        {"extra": (struct.pack("<IIII", 0x1D, 16, 0, 0),)}):
            with self.subTest(options=options):
                self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
                    install_name="@rpath/libEGL.framework/libEGL",
                    rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"], **options))
                with self.assertRaises(ValidationError): frameworks(self.root)
        self.write("Frameworks/libEGL.framework/libEGL", binary(filetype=6,
            install_name="@rpath/libEGL.framework/libEGL",
            rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"]))
        plist_path = self.root / "Frameworks/libEGL.framework/Info.plist"
        info = plistlib.loads(plist_path.read_bytes())
        for platforms in (["iPhoneSimulator"], ["MacOSX"]):
            with self.subTest(platforms=platforms):
                plist_path.write_bytes(plistlib.dumps(dict(info, CFBundleSupportedPlatforms=platforms)))
                with self.assertRaisesRegex(ValidationError, "not iPhoneOS"): frameworks(self.root)

    def test_application_resolves_angle_peers_without_treating_loader_path_as_app_root(self):
        egl, gles = "Frameworks/libEGL.framework/libEGL", "Frameworks/libGLESv2.framework/libGLESv2"
        paths = ["@executable_path/Frameworks", "@loader_path/Frameworks"]
        files = bundle(dependencies=["@rpath/libEGL.framework/libEGL"], rpaths=["@executable_path/Frameworks"])
        files[egl] = Entry(binary(filetype=6, install_name="@rpath/libEGL.framework/libEGL", rpaths=paths,
                                  dependencies=["@rpath/libGLESv2.framework/libGLESv2"]), EXECUTABLE)
        files[gles] = Entry(binary(filetype=6, install_name="@rpath/libGLESv2.framework/libGLESv2", rpaths=paths), EXECUTABLE)
        report = validate_bundle(files)
        self.assertEqual({(item["loader"], item["target"]) for item in report["dependencies"]},
                         {("IOSANGLESmoke", egl), (egl, gles)})
        self.assertEqual(expand_path("@executable_path/Frameworks", egl), "Frameworks")
        self.assertEqual(expand_path("@loader_path/Frameworks", egl), "Frameworks/libEGL.framework/Frameworks")
        # Reach EGL directly, with no inherited app rpath. The loader-only search
        # location must not be silently replaced by the sibling framework folder.
        files["IOSANGLESmoke"] = Entry(binary(dependencies=["@executable_path/" + egl]), EXECUTABLE)
        files[egl] = Entry(binary(filetype=6, install_name="@rpath/libEGL.framework/libEGL",
                                  rpaths=["@loader_path/Frameworks"],
                                  dependencies=["@rpath/libGLESv2.framework/libGLESv2"]), EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "Unresolved bundled dependency"):
            validate_bundle(files)

    def angle_application_bundle(self):
        files = bundle(dependencies=["@rpath/libEGL.framework/libEGL", "@rpath/libGLESv2.framework/libGLESv2"],
                       rpaths=["@executable_path/Frameworks"])
        for name in ("libEGL", "libGLESv2"):
            files[f"Frameworks/{name}.framework/{name}"] = Entry(binary(filetype=6,
                install_name=f"@rpath/{name}.framework/{name}",
                dependencies=["@rpath/libGLESv2.framework/libGLESv2"] if name == "libEGL" else [],
                rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"]), EXECUTABLE)
        return files

    def test_distributable_angle_bundle_preserves_framework_ids_paths_and_ipa_closure(self):
        files = self.angle_application_bundle()
        report = validate_bundle(files)
        self.assertEqual(report["binaries"]["IOSANGLESmoke"]["rpaths"], ["@executable_path/Frameworks"])
        for name in ("libEGL", "libGLESv2"):
            path = f"Frameworks/{name}.framework/{name}"
            self.assertEqual(report["binaries"][path]["install_name"], f"@rpath/{name}.framework/{name}")
            self.assertEqual(report["binaries"][path]["rpaths"],
                             ["@executable_path/Frameworks", "@loader_path/Frameworks"])
        self.assertEqual({item["target"] for item in report["dependencies"]},
                         {"Frameworks/libEGL.framework/libEGL", "Frameworks/libGLESv2.framework/libGLESv2"})
        ipa = self.root / "angle-unsigned.ipa"
        write_ipa(files, ipa)
        reopened = validate_ipa(ipa, expected=files)
        self.assertEqual(reopened["binaries"], report["binaries"])

    def test_runner_rpaths_are_rejected_in_executable_and_each_embedded_framework(self):
        report = validate_bundle(self.angle_application_bundle())
        runner = "/Users/runner/work/_temp/angle-ios-arm64/Frameworks"
        for loader, details in report["binaries"].items():
            with self.subTest(loader=loader):
                files = self.angle_application_bundle()
                files[loader] = Entry(binary(filetype=details["filetype"], install_name=details["install_name"],
                    dependencies=details["dependencies"], rpaths=details["rpaths"] + [runner]), EXECUTABLE)
                with self.assertRaisesRegex(ValidationError, "Unsupported/non-bundled runpath"):
                    validate_bundle(files)

    def test_runner_dependency_references_are_rejected_in_all_angle_bundle_binaries(self):
        report = validate_bundle(self.angle_application_bundle())
        dependency = "/Users/runner/work/_temp/angle-ios-arm64/Frameworks/libGLESv2.framework/libGLESv2"
        for loader, details in report["binaries"].items():
            with self.subTest(loader=loader):
                files = self.angle_application_bundle()
                files[loader] = Entry(binary(filetype=details["filetype"], install_name=details["install_name"],
                    dependencies=[dependency], rpaths=details["rpaths"]), EXECUTABLE)
                with self.assertRaisesRegex(ValidationError, "Unexpected host dependency"):
                    validate_bundle(files)

    def test_missing_or_misplaced_angle_framework_is_not_found_via_a_build_directory(self):
        original = "Frameworks/libGLESv2.framework/libGLESv2"
        for destination in (None, "libGLESv2.framework/libGLESv2", "Frameworks/Other.framework/libGLESv2"):
            with self.subTest(destination=destination):
                files = self.angle_application_bundle()
                entry = files.pop(original)
                if destination:
                    files[destination] = entry
                with self.assertRaises(ValidationError): validate_bundle(files)

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
