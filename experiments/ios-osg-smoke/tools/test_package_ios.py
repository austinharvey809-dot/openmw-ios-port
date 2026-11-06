"""Host-only unsigned IPA tests using synthetic bundles, SDK stubs and Mach-O data."""

from pathlib import Path
import hashlib
import json
import plistlib
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from package_ios import (
    Entry, PREFIX, ValidationError, inspect_dependencies, macho, main,
    system_dependency, validate_bundle, validate_ipa, write_ipa,
)


REGULAR = stat.S_IFREG | 0o644
EXECUTABLE = stat.S_IFREG | 0o755


def path_command(command, value):
    prefix_size = 12 if command == 0x8000001C else 24
    encoded = value.encode("utf-8") + b"\0"
    size = (prefix_size + len(encoded) + 7) & ~7
    header = struct.pack("<III", command, size, prefix_size)
    return header + bytes(prefix_size - len(header)) + encoded + bytes(size - prefix_size - len(encoded))


def binary(*, filetype=2, dependencies=(), rpaths=(), install_name=None,
           platform=2, cpu=0x0100000C, minimum=0x120000, extra=()):
    commands = [struct.pack("<IIIIII", 0x32, 24, platform, minimum, 0x1A0000, 0)]
    commands += [path_command(0xC, name) for name in dependencies]
    commands += [path_command(0x8000001C, name) for name in rpaths]
    if install_name:
        commands.append(path_command(0xD, install_name))
    commands += list(extra)
    payload = b"".join(commands)
    return struct.pack("<IiiIIIII", 0xFEEDFACF, cpu, 0, filetype, len(commands), len(payload), 0, 0) + payload


def bundle(*, dependencies=(), rpaths=()):
    info = {
        "CFBundleExecutable": "IOSOSGSmoke",
        "CFBundleIdentifier": "org.openmw.experiments.ios-osg-smoke",
        "CFBundlePackageType": "APPL",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "UIDeviceFamily": [1],
        "MinimumOSVersion": "18.0",
        "UILaunchScreen": {},
        "UIApplicationSceneManifest": {
            "UISceneConfigurations": {
                "UIWindowSceneSessionRoleApplication": [{"UISceneDelegateClassName": "OSGSceneDelegate"}]
            }
        },
    }
    requirements = Path(__file__).resolve().parents[1] / "data/angle-lock.json"
    return {"Info.plist": Entry(plistlib.dumps(info), REGULAR),
            "IOSOSGSmoke": Entry(binary(dependencies=dependencies, rpaths=rpaths), EXECUTABLE),
            "angle-lock.json": Entry(requirements.read_bytes(), REGULAR),
            "angle-build.json": Entry(json.dumps({"angle_revision": "6ea96bcca6d7f05199f5565c6d5c4722af7269da", "target": "arm64-apple-ios18.0", "metal_only": True, "validation": "device-binary-and-sdk-passed"}).encode(), REGULAR),
            "Licenses/LICENSE": Entry(b"original upstream notice fixture", REGULAR),
            "osg-lock.json": Entry((Path(__file__).resolve().parents[1] / "data/osg-lock.json").read_bytes(), REGULAR),
            "osg-build.json": Entry(json.dumps({"revision":"9b384d5439977784e5cd250ff8ff7966928ddd27","profile":"GLES3","windowing":"None","static":True,"deployment":"18.0","overlay_version":1}).encode(), REGULAR),
            "Licenses/osg-LICENSE.txt": Entry(b"OSGPL fixture",REGULAR),
            "Licenses/OpenThreads/Thread": Entry(b"MIT fixture",REGULAR)}


class PackageIOSTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def sdk(self):
        sdk = self.root / "iPhoneOS.sdk"
        sdk.mkdir(exist_ok=True)
        (sdk / "SDKSettings.plist").write_bytes(plistlib.dumps({"CanonicalName": "iphoneos26.5"}))
        return sdk

    def stub(self, sdk, install_name, *, targets="arm64-ios", reported_name=None):
        binary_path = sdk / install_name.lstrip("/")
        stub = binary_path.with_suffix(".tbd") if binary_path.suffix == ".dylib" else Path(str(binary_path) + ".tbd")
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(
            f"--- !tapi-tbd\ntbd-version: 4\ntargets: [ {targets} ]\ninstall-name: '{reported_name or install_name}'\n...\n",
            encoding="utf-8",
        )
        return stub

    def write_custom_ipa(self, path, members):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, source in members:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = source.mode << 16
                archive.writestr(info, source.data)

    def test_query_bundle_requires_exact_audited_requirements_resource(self):
        files = bundle()
        report = validate_bundle(files)
        self.assertEqual(report["required_resources"],
                         ["Info.plist", "IOSOSGSmoke", "angle-lock.json", "osg-lock.json", "osg-build.json", "Licenses/osg-LICENSE.txt", "angle-build.json", "Licenses/"])
        self.assertEqual(report["angle_revision"], "6ea96bcca6d7f05199f5565c6d5c4722af7269da")
        self.assertEqual(report["requirements_sha256"],
                         hashlib.sha256(files["angle-lock.json"].data).hexdigest())
        del files["angle-lock.json"]
        with self.assertRaisesRegex(ValidationError, "Missing required pinned"):
            validate_bundle(files)

    def test_malformed_wrong_version_or_changed_requirements_rejected(self):
        original = json.loads(bundle()["angle-lock.json"].data)
        changed = dict(original, angle_revision="wrong-revision")
        same_version_but_changed = dict(original, tampered=True)
        for data in (b"not JSON", b"[]", json.dumps(changed).encode(), json.dumps(same_version_but_changed).encode()):
            with self.subTest(data=data[:32]):
                files = bundle()
                files["angle-lock.json"] = Entry(data, REGULAR)
                with self.assertRaisesRegex(ValidationError, "ANGLE"):
                    validate_bundle(files)

    def test_wrong_scene_delegate_rejected(self):
        files = bundle()
        info = plistlib.loads(files["Info.plist"].data)
        info["UIApplicationSceneManifest"]["UISceneConfigurations"]["UIWindowSceneSessionRoleApplication"][0]["UISceneDelegateClassName"] = "SmokeSceneDelegate"
        files["Info.plist"] = Entry(plistlib.dumps(info), REGULAR)
        with self.assertRaisesRegex(ValidationError, "OSGSceneDelegate"):
            validate_bundle(files)

    def test_v5_json_device_stub_supported_and_simulator_or_mac_rejected(self):
        sdk = self.sdk()
        name = "/System/Library/Frameworks/Metal.framework/Metal"
        stub = self.stub(sdk, name)
        for target in ("arm64-ios", "arm64-ios-simulator", "arm64-macos"):
            stub.write_text(json.dumps({"tapi_tbd_version": 5, "main_library": {
                "target_info": [{"target": target}], "install_names": [{"name": name}]}}), encoding="utf-8")
            if target == "arm64-ios":
                self.assertEqual(system_dependency(name, sdk)["kind"], "iphoneos-sdk")
            else:
                with self.assertRaisesRegex(ValidationError, "ARM64 iOS"):
                    system_dependency(name, sdk)

    def test_ipa_round_trip_preserves_payload_permissions_contents_and_hash(self):
        files = bundle()
        files["resource with spaces.txt"] = Entry(b"resource contents", REGULAR)
        ipa = self.root / "IOSOSGSmoke-unsigned.ipa"
        write_ipa(files, ipa)
        report = validate_ipa(ipa, expected=files)
        with zipfile.ZipFile(ipa) as archive:
            self.assertEqual(set(archive.namelist()), {"Payload/", PREFIX, *(PREFIX + name for name in files)})
            self.assertEqual(archive.read(PREFIX + "IOSOSGSmoke"), files["IOSOSGSmoke"].data)
            self.assertEqual(archive.getinfo(PREFIX + "IOSOSGSmoke").external_attr >> 16, EXECUTABLE)
        self.assertEqual(report["archive_root"], PREFIX)
        self.assertEqual(report["sha256"], hashlib.sha256(ipa.read_bytes()).hexdigest())
        self.assertEqual(report["files"], len(files))
        self.assertTrue(report["unsigned"])

    def test_missing_executable_rejected(self):
        files = bundle()
        del files["IOSOSGSmoke"]
        with self.assertRaisesRegex(ValidationError, "CFBundleExecutable"):
            validate_bundle(files)

    def test_nonexecutable_permission_rejected(self):
        files = bundle()
        files["IOSOSGSmoke"] = Entry(files["IOSOSGSmoke"].data, REGULAR)
        with self.assertRaisesRegex(ValidationError, "executable permissions"):
            validate_bundle(files)

    def test_invalid_plist_and_mismatched_executable_rejected(self):
        files = bundle()
        files["Info.plist"] = Entry(b"not a plist", REGULAR)
        with self.assertRaisesRegex(ValidationError, "Invalid Info.plist"):
            validate_bundle(files)
        files = bundle()
        info = plistlib.loads(files["Info.plist"].data)
        info["CFBundleExecutable"] = "AnotherExecutable"
        files["Info.plist"] = Entry(plistlib.dumps(info), REGULAR)
        with self.assertRaisesRegex(ValidationError, "CFBundleExecutable"):
            validate_bundle(files)

    def test_external_storyboard_configuration_rejected(self):
        files = bundle()
        info = plistlib.loads(files["Info.plist"].data)
        info["UILaunchStoryboardName"] = "MissingStoryboard"
        files["Info.plist"] = Entry(plistlib.dumps(info), REGULAR)
        with self.assertRaisesRegex(ValidationError, "External storyboard"):
            validate_bundle(files)

    def test_wrong_architecture_and_device_platform_rejected(self):
        for arguments in ({"cpu": 0x01000007}, {"platform": 7}, {"platform": 1}):
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                macho(binary(**arguments))
        with self.assertRaisesRegex(ValidationError, "thin"):
            macho(b"\xca\xfe\xba\xbe" + bytes(100))

    def test_signature_and_encrypted_binary_rejected(self):
        signature = struct.pack("<IIII", 0x1D, 16, 0, 0)
        encryption = struct.pack("<IIIIII", 0x2C, 24, 0, 0, 1, 0)
        for command in (signature, encryption):
            with self.subTest(command=command), self.assertRaises(ValidationError):
                macho(binary(extra=[command]))

    def test_truncated_and_malformed_load_commands_rejected(self):
        with self.assertRaisesRegex(ValidationError, "Truncated"):
            macho(binary()[:-1])
        invalid = struct.pack("<II", 0x8000001C, 0)
        with self.assertRaisesRegex(ValidationError, "command length"):
            macho(binary(extra=[invalid]))

    def test_signing_and_credential_files_rejected(self):
        for name in ("embedded.mobileprovision", "_CodeSignature/CodeResources", "certificate.p12", "private.key", "profile.provisionprofile"):
            with self.subTest(name=name):
                files = bundle()
                files[name] = Entry(b"forbidden fixture", REGULAR)
                with self.assertRaisesRegex(ValidationError, "Signing/provisioning/credential"):
                    validate_bundle(files)

    def test_static_archive_and_symlink_rejected(self):
        for name, entry in (("Frameworks/libMoltenVK.a", Entry(b"!<arch>\n", REGULAR)),
                            ("linked-resource", Entry(b"../outside", stat.S_IFLNK | 0o777))):
            with self.subTest(name=name):
                files = bundle()
                files[name] = entry
                with self.assertRaises(ValidationError):
                    validate_bundle(files)

    def test_duplicate_archive_member_rejected(self):
        files = bundle()
        members = [(PREFIX + name, source) for name, source in files.items()]
        members.append((PREFIX + "Info.plist", files["Info.plist"]))
        ipa = self.root / "duplicate.ipa"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.write_custom_ipa(ipa, members)
        with self.assertRaisesRegex(ValidationError, "Duplicate"):
            validate_ipa(ipa)

    def test_extra_application_bad_root_and_traversal_rejected(self):
        for name in ("IOSOSGSmoke.app/Info.plist", "Payload/Other.app/file", "__MACOSX/file", PREFIX + "../outside"):
            with self.subTest(name=name):
                members = [(PREFIX + key, source) for key, source in bundle().items()]
                members.append((name, Entry(b"unexpected", REGULAR)))
                ipa = self.root / "bad-root.ipa"
                self.write_custom_ipa(ipa, members)
                with self.assertRaises(ValidationError):
                    validate_ipa(ipa)

    def test_corrupt_archive_crc_rejected(self):
        ipa = self.root / "corrupt.ipa"
        members = [(PREFIX + name, source) for name, source in bundle().items()]
        self.write_custom_ipa(ipa, members)
        with zipfile.ZipFile(ipa) as archive:
            entry = archive.getinfo(PREFIX + "IOSOSGSmoke")
            offset = entry.header_offset
        data = bytearray(ipa.read_bytes())
        name_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
        data[offset + 30 + name_length + extra_length] ^= 1
        ipa.write_bytes(data)
        with self.assertRaises((ValidationError, zipfile.BadZipFile)):
            validate_ipa(ipa)

    def test_expected_bundle_detects_content_changes(self):
        expected = bundle()
        actual = dict(expected, **{"extra.txt": Entry(b"unexpected", REGULAR)})
        ipa = self.root / "extra.ipa"
        write_ipa(actual, ipa)
        with self.assertRaisesRegex(ValidationError, "contents or permissions differ"):
            validate_ipa(ipa, expected=expected)

    def test_system_dependency_uses_selected_ios_sdk_stub(self):
        sdk = self.sdk()
        framework = "/System/Library/Frameworks/Metal.framework/Metal"
        dylib = "/usr/lib/libSystem.B.dylib"
        for name in (framework, dylib):
            stub = self.stub(sdk, name)
            self.assertEqual(system_dependency(name, sdk), {"kind": "iphoneos-sdk", "stub": str(stub)})
        report = validate_bundle(bundle(dependencies=[framework, dylib]), sdk)
        self.assertTrue(report["sdk_availability_checked"])
        self.assertEqual(len(report["dependencies"]), 2)

    def test_missing_non_ios_and_wrong_install_name_sdk_stubs_rejected(self):
        sdk = self.sdk()
        name = "/usr/lib/libSystem.B.dylib"
        with self.assertRaisesRegex(ValidationError, "No matching"):
            system_dependency(name, sdk)
        self.stub(sdk, name, targets="arm64-macos")
        with self.assertRaisesRegex(ValidationError, "ARM64 iOS"):
            system_dependency(name, sdk)
        self.stub(sdk, name, reported_name="/usr/lib/someOtherLibrary.dylib")
        with self.assertRaisesRegex(ValidationError, "install name"):
            system_dependency(name, sdk)
        with self.assertRaisesRegex(ValidationError, "Non-public"):
            system_dependency("/opt/homebrew/lib/libexample.dylib", sdk)

    def test_simulator_sdk_is_rejected(self):
        sdk = self.sdk()
        (sdk / "SDKSettings.plist").write_bytes(plistlib.dumps({"CanonicalName": "iphonesimulator26.5"}))
        with self.assertRaisesRegex(ValidationError, "SDK is not iphoneos"):
            validate_bundle(bundle(), sdk)

    def test_bundled_transitive_dependencies_resolve_actual_runpaths(self):
        a = "Frameworks/A Framework.framework/A Framework"
        b = "Frameworks/B.framework/B"
        files = bundle(dependencies=["@rpath/A Framework.framework/A Framework"], rpaths=["@executable_path/Frameworks"])
        files[a] = Entry(binary(filetype=6, install_name="@rpath/A Framework.framework/A Framework",
                                dependencies=["@loader_path/../B.framework/B"]), EXECUTABLE)
        files[b] = Entry(binary(filetype=6, install_name="@rpath/B.framework/B"), EXECUTABLE)
        report = validate_bundle(files)
        self.assertEqual({record["target"] for record in report["dependencies"]}, {a, b})

    def test_missing_rpath_is_not_silently_replaced_with_frameworks(self):
        files = bundle(dependencies=["@rpath/A.framework/A"])
        files["Frameworks/A.framework/A"] = Entry(binary(filetype=6), EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "Unresolved bundled"):
            validate_bundle(files)

    def test_bundle_root_runpaths_resolve_without_escaping(self):
        for runpath in ("@executable_path", "@loader_path"):
            with self.subTest(runpath=runpath):
                files = bundle(dependencies=["@rpath/Frameworks/A.framework/A"], rpaths=[runpath])
                files["Frameworks/A.framework/A"] = Entry(binary(filetype=6), EXECUTABLE)
                report = validate_bundle(files)
                self.assertEqual(report["dependencies"][0]["target"], "Frameworks/A.framework/A")

    def test_missing_or_escaping_bundled_dependency_rejected(self):
        for dependency in ("@rpath/Missing.framework/Missing", "@loader_path/../outside"):
            with self.subTest(dependency=dependency), self.assertRaises(ValidationError):
                validate_bundle(bundle(dependencies=[dependency], rpaths=["@executable_path/Frameworks"]))

    def test_unreferenced_or_newer_os_framework_rejected(self):
        files = bundle()
        files["Frameworks/A.framework/A"] = Entry(binary(filetype=6), EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "Unreferenced"):
            validate_bundle(files)
        files = bundle(dependencies=["@rpath/A.framework/A"], rpaths=["@executable_path/Frameworks"])
        files["Frameworks/A.framework/A"] = Entry(binary(filetype=6, minimum=0x130000), EXECUTABLE)
        with self.assertRaisesRegex(ValidationError, "newer iOS"):
            validate_bundle(files)

    def test_otool_install_id_is_compared_but_not_a_dependency(self):
        a = "Frameworks/A Framework.framework/A Framework"
        name = "@rpath/A Framework.framework/A Framework"
        files = bundle(dependencies=[name], rpaths=["@executable_path/Frameworks"])
        files[a] = Entry(binary(filetype=6, install_name=name), EXECUTABLE)
        report = validate_bundle(files)
        self.assertEqual(len(report["dependencies"]), 1)
        def run(arguments, **kwargs):
            self.assertEqual(arguments[:3], ["xcrun", "otool", "-L"])
            output = arguments[-1] + ":\n\t" + name + " (compatibility version 1.0.0, current version 1.0.0)\n"
            return subprocess.CompletedProcess(arguments, 0, stdout=output)
        with patch("package_ios.subprocess.run", side_effect=run) as mocked:
            outputs = inspect_dependencies(self.root / "IOSOSGSmoke.app", report)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(set(outputs), {"IOSOSGSmoke", a})

    def test_otool_disagreement_is_rejected(self):
        report = validate_bundle(bundle())
        unexpected = "app:\n\t/opt/build/libBad.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
        with patch("package_ios.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=unexpected)):
            with self.assertRaisesRegex(ValidationError, "metadata disagree"):
                inspect_dependencies(self.root / "IOSOSGSmoke.app", report)

    def test_validate_only_cli_writes_hash_report_without_apple_tools(self):
        ipa = self.root / "IOSOSGSmoke-unsigned.ipa"
        report_path = self.root / "validation.json"
        write_ipa(bundle(), ipa)
        with patch("package_ios.subprocess.run", side_effect=AssertionError("Apple tools must not run")):
            self.assertEqual(main(["--validate-only", str(ipa), "--report", str(report_path)]), 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["ipa"], str(ipa))
        self.assertTrue(report["unsigned"])
        self.assertFalse(report["sdk_availability_checked"])

    def test_packaging_cli_publishes_validated_ipa_report_and_otool_output(self):
        sdk = self.sdk()
        dependency = "/System/Library/Frameworks/Metal.framework/Metal"
        self.stub(sdk, dependency)
        files = bundle(dependencies=[dependency])
        app = self.root / "IOSOSGSmoke.app"
        output = self.root / "artifacts" / "IOSOSGSmoke-unsigned.ipa"
        report_path = output.parent / "ipa-validation.json"
        listing = str(app / "IOSOSGSmoke") + ":\n\t" + dependency + " (compatibility version 1.0.0, current version 1.0.0)\n"
        with patch("package_ios.collect_bundle", return_value=files), patch(
            "package_ios.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=listing)
        ) as inspect:
            result = main(["--app", str(app), "--sdk", str(sdk), "--output", str(output), "--report", str(report_path)])
        self.assertEqual(result, 0)
        inspect.assert_called_once_with(
            ["xcrun", "otool", "-L", str(app / "IOSOSGSmoke")], check=True, capture_output=True, text=True
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["ipa"], str(output))
        self.assertEqual(report["otool_L"], {"IOSOSGSmoke": listing})
        self.assertTrue(report["sdk_availability_checked"])
        self.assertEqual(report["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(validate_ipa(output, sdk, expected=files)["files"], len(files))
        self.assertEqual(set(output.parent.iterdir()), {output, report_path})

    def test_packaging_cli_rejects_signed_input_without_publishing_ipa(self):
        sdk = self.sdk()
        files = bundle()
        files["embedded.mobileprovision"] = Entry(b"signing fixture", REGULAR)
        app = self.root / "IOSOSGSmoke.app"
        output = self.root / "artifacts" / "IOSOSGSmoke-unsigned.ipa"
        report_path = output.parent / "ipa-validation.json"
        with patch("package_ios.collect_bundle", return_value=files), patch(
            "package_ios.subprocess.run", side_effect=AssertionError("Invalid input must stop before otool")
        ):
            result = main(["--app", str(app), "--sdk", str(sdk), "--output", str(output), "--report", str(report_path)])
        self.assertEqual(result, 1)
        self.assertFalse(output.exists())
        self.assertFalse(report_path.exists())
        self.assertEqual(list(self.root.rglob("*.ipa.tmp")), [])


if __name__ == "__main__":
    unittest.main()
