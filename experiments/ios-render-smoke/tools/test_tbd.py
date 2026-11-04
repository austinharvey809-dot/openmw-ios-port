"""SDK target regressions using small TAPI fixtures, never a downloaded SDK."""

import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from package_ios import ValidationError, probe_arm64_system_stub, read_tbd_metadata, system_dependency
from test_package_ios import binary


UIKIT = "/System/Library/Frameworks/UIKit.framework/UIKit"
OTHER = "/System/Library/Frameworks/Other.framework/Other"


def v4(targets=("arm64-ios",), name=UIKIT):
    return (
        "--- !tapi-tbd\n"
        "tbd-version: 4\n"
        f"targets: [ {', '.join(targets)} ]\n"
        f"install-name: '{name}'\n"
        "...\n"
    )


def v5(targets=("arm64-ios",), names=None, **extra):
    library = {
        "target_info": [{"target": target, "min_deployment": "18.0"} for target in targets],
        "install_names": names if names is not None else [{"name": UIKIT}],
    }
    library.update(extra)
    return json.dumps({"tapi_tbd_version": 5, "main_library": library})


class TBDTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.sdk = Path(self.temporary.name) / "iPhoneOS.sdk"
        self.sdk.mkdir()
        (self.sdk / "SDKSettings.plist").write_bytes(plistlib.dumps({"CanonicalName": "iphoneos27.0"}))
        self.stub = self.sdk / "System/Library/Frameworks/UIKit.framework/UIKit.tbd"
        self.stub.parent.mkdir(parents=True)

    def write(self, text):
        self.stub.write_text(text, encoding="utf-8")

    def assert_supported(self, text):
        self.write(text)
        with patch("package_ios.probe_arm64_system_stub") as probe:
            report = system_dependency(UIKIT, self.sdk)
        self.assertEqual(report["kind"], "iphoneos-sdk")
        self.assertEqual(report["stub"], str(self.stub))
        probe.assert_not_called()

    def assert_unsupported(self, text):
        self.write(text)
        with patch("package_ios.probe_arm64_system_stub") as probe:
            with self.assertRaises(ValidationError):
                system_dependency(UIKIT, self.sdk)
        probe.assert_not_called()

    def test_v4_device_target_and_install_name_are_structured(self):
        result = read_tbd_metadata(v4())
        self.assertEqual(result["targets"], {"arm64-ios"})
        self.assertEqual(result["install_names"], {UIKIT: {"arm64-ios"}})
        self.assertTrue(result["format"])
        self.assert_supported(v4())

    def test_v4_quoted_multiline_flow_targets_and_comments(self):
        text = """--- !tapi-tbd
tbd-version: 4
targets: [ 'arm64-macos', # a different platform
           "arm64-ios", 'arm64-ios-simulator' ]
install-name: '/System/Library/Frameworks/UIKit.framework/UIKit' # actual install name
...
"""
        result = read_tbd_metadata(text)
        self.assertEqual(result["targets"], {"arm64-macos", "arm64-ios", "arm64-ios-simulator"})
        self.assert_supported(text)

    def test_v4_block_target_sequence(self):
        text = """--- !tapi-tbd
tbd-version: 4
targets:
  - arm64-ios
  - arm64-ios-simulator
install-name: /System/Library/Frameworks/UIKit.framework/UIKit
...
"""
        self.assert_supported(text)

    def test_v4_unsupported_platform_and_architecture_matrix(self):
        for target in ("arm64-macos", "arm64-ios-simulator", "arm64-maccatalyst",
                       "x86_64-ios-simulator", "x86_64-ios", "arm64_32-ios", "armv7-ios"):
            with self.subTest(target=target):
                self.assert_unsupported(v4([target]))

    def test_v5_device_target_and_install_name_are_structured(self):
        result = read_tbd_metadata(v5())
        self.assertEqual(result["targets"], {"arm64-ios"})
        self.assertEqual(result["install_names"], {UIKIT: {"arm64-ios"}})
        self.assertTrue(result["format"])
        self.assert_supported(v5())

    def test_v5_escaped_json_targets_and_install_name(self):
        text = v5().replace('"arm64-ios"', '"\\u0061rm64-ios"').replace("UIKit", "UI\\u004bit")
        self.assertNotIn('"arm64-ios"', text)
        self.assert_supported(text)

    def test_v5_unsupported_platform_and_architecture_matrix(self):
        for target in ("arm64-macos", "arm64-ios-simulator", "arm64-maccatalyst",
                       "x86_64-ios-simulator", "x86_64-ios", "arm64_32-ios", "armv7-ios"):
            with self.subTest(target=target):
                self.assert_unsupported(v5([target]))

    def test_v5_matching_install_name_must_apply_to_device_target(self):
        targets = ["arm64-ios", "arm64-macos"]
        names = [
            {"name": UIKIT, "targets": ["arm64-macos"]},
            {"name": OTHER, "targets": ["arm64-ios"]},
        ]
        text = v5(targets, names)
        result = read_tbd_metadata(text)
        self.assertEqual(result["install_names"][UIKIT], {"arm64-macos"})
        self.assert_unsupported(text)

    def test_v5_target_scoped_device_install_name_is_supported(self):
        self.assert_supported(v5(["arm64-ios", "arm64-macos"], [
            {"name": UIKIT, "targets": ["arm64-ios"]},
            {"name": OTHER, "targets": ["arm64-macos"]},
        ]))

    def test_v5_nested_library_and_symbol_targets_do_not_authorize_main_library(self):
        document = json.loads(v5(["arm64-macos"], exported_symbols=[{
            "targets": ["arm64-ios"], "text": {"global": ["_arm64-ios"]},
        }]))
        document["libraries"] = [json.loads(v5())["main_library"]]
        self.assert_unsupported(json.dumps(document))

    def test_v4_comment_and_export_target_decoys_do_not_authorize_library(self):
        text = """--- !tapi-tbd
tbd-version: 4
targets: [ arm64-macos ] # arm64-ios is deliberately a decoy
install-name: /System/Library/Frameworks/UIKit.framework/UIKit
exports:
  - targets: [ arm64-ios ]
    symbols: [ '_arm64-ios' ]
...
"""
        self.assert_unsupported(text)

    def test_v4_second_document_does_not_authorize_first(self):
        text = v4(["arm64-macos"]) + v4(["arm64-ios"], OTHER)
        # Rejecting unsupported multi-document syntax is also fail-closed.
        try:
            result = read_tbd_metadata(text)
        except ValidationError:
            return
        self.assertNotIn("arm64-ios", result["targets"])
        self.assert_unsupported(text)

    def test_install_name_substring_and_reexport_decoys_rejected(self):
        self.assert_unsupported(v4(["arm64-ios"], UIKIT + "Extra"))
        self.assert_unsupported(v5(["arm64-ios"], [{"name": OTHER}],
                                   reexported_libraries=[{"names": [UIKIT]}]))

    def test_v3_legacy_device_architecture_and_platform(self):
        text = """--- !tapi-tbd-v3
archs: [ arm64, arm64e ]
platform: ios
install-name: /System/Library/Frameworks/UIKit.framework/UIKit
...
"""
        self.assert_supported(text)

    def test_v3_mac_and_wrong_architecture_rejected(self):
        for platform, architecture in (("macosx", "arm64"), ("ios", "x86_64"), ("ios", "arm64_32")):
            with self.subTest(platform=platform, architecture=architecture):
                text = (f"--- !tapi-tbd-v3\narchs: [ {architecture} ]\nplatform: {platform}\n"
                        f"install-name: {UIKIT}\n...\n")
                self.assert_unsupported(text)

    def test_arm64e_device_sdk_requires_successful_native_linker_probe(self):
        for text in (v4(["arm64e-ios", "arm64e.x1-ios"]), v5(["arm64e-ios", "arm64e.x1-ios"])):
            with self.subTest(format=text[:20]):
                self.write(text)
                with patch("package_ios.probe_arm64_system_stub") as probe:
                    report = system_dependency(UIKIT, self.sdk, minimum_os="18.0")
                self.assertEqual(report["kind"], "iphoneos-sdk")
                probe.assert_called_once_with(self.stub, self.sdk, UIKIT, "18.0")

    def test_arm64e_device_probe_failure_remains_a_blocker(self):
        self.write(v4(["arm64e-ios"]))
        with patch("package_ios.probe_arm64_system_stub", side_effect=ValidationError("native linker rejected stub")):
            with self.assertRaisesRegex(ValidationError, "native linker rejected"):
                system_dependency(UIKIT, self.sdk)

    def test_arm64e_other_platform_and_unknown_variant_never_probed(self):
        for target in ("arm64e-macos", "arm64e-ios-simulator", "arm64e-maccatalyst",
                       "arm64e.x1-ios-simulator", "arm64e.unknown-ios"):
            with self.subTest(target=target):
                self.assert_unsupported(v4([target]))

    def test_native_probe_uses_exact_sdk_stub_device_triple_and_forced_load(self):
        self.write(v4(["arm64e-ios"]))
        def run(arguments, **kwargs):
            self.assertEqual(arguments[:6], ["xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios18.0"])
            self.assertEqual(arguments[arguments.index("-isysroot") + 1], str(self.sdk))
            position = arguments.index("-needed_library")
            self.assertEqual(arguments[position - 1:position + 3], ["-Xlinker", "-needed_library", "-Xlinker", str(self.stub)])
            self.assertIn("-dynamiclib", arguments)
            self.assertIn("-Wl,-fatal_warnings", arguments)
            self.assertIn("-Wl,-no_adhoc_codesign", arguments)
            self.assertIn("ios_sdk_abi_probe", kwargs["input"])
            output = Path(arguments[arguments.index("-o") + 1])
            output.write_bytes(binary(filetype=6, dependencies=[UIKIT]))
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")
        with patch("package_ios.subprocess.run", side_effect=run) as tool:
            probe_arm64_system_stub(self.stub, self.sdk, UIKIT, "18.0")
        tool.assert_called_once()

    def test_native_probe_rejects_linker_failure_or_unavailable_tool(self):
        failures = [
            subprocess.CompletedProcess([], 1, stdout="", stderr="unsupported target"),
            OSError("xcrun unavailable"),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                arguments = {"side_effect": failure} if isinstance(failure, OSError) else {"return_value": failure}
                with patch("package_ios.subprocess.run", **arguments), self.assertRaises(ValidationError):
                    probe_arm64_system_stub(self.stub, self.sdk, UIKIT, "18.0")

    def test_native_probe_rejects_wrong_architecture_platform_or_dependency(self):
        for options in ({"cpu": 0x01000007}, {"platform": 1}, {"platform": 7}, {"dependencies": [OTHER]}):
            with self.subTest(options=options):
                def run(arguments, **kwargs):
                    details = {"filetype": 6, "dependencies": [UIKIT], **options}
                    Path(arguments[arguments.index("-o") + 1]).write_bytes(binary(**details))
                    return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")
                with patch("package_ios.subprocess.run", side_effect=run), self.assertRaises(ValidationError):
                    probe_arm64_system_stub(self.stub, self.sdk, UIKIT, "18.0")

    def test_native_probe_rejects_missing_output(self):
        with patch("package_ios.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")):
            with self.assertRaisesRegex(ValidationError, "did not produce"):
                probe_arm64_system_stub(self.stub, self.sdk, UIKIT, "18.0")

    def test_invalid_and_unknown_formats_fail_closed(self):
        malformed = [
            "not a text stub",
            "{broken JSON",
            json.dumps({"tapi_tbd_version": 6, "main_library": {}}),
            '{"tapi_tbd_version": 5, "tapi_tbd_version": 6, "main_library": {}}',
            json.dumps({"tapi_tbd_version": 5, "main_library": []}),
            json.dumps({"tapi_tbd_version": 5, "main_library": {"install_names": [{"name": UIKIT}]}}),
            v5().replace('"target_info": [', '"unknown_targets": ['),
            v4().replace("tbd-version: 4", "tbd-version: 99"),
            v4().replace("targets: [ arm64-ios ]", "targets: [ arm64-ios"),
            v4().replace("targets: [ arm64-ios ]", "targets: [ arm64-ios ]\ntargets: [ arm64-macos ]"),
        ]
        for text in malformed:
            with self.subTest(text=text[:60]), self.assertRaises(ValidationError):
                read_tbd_metadata(text)


if __name__ == "__main__":
    unittest.main()
