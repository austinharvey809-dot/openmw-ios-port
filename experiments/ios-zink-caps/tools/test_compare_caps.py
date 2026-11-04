"""Synthetic report comparisons: these fixtures are never physical-device evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from compare_caps import compare, evaluate, evaluate_group, main


def comparison_cases():
    device = {"identity": {"api_version": [1, 2, 0], "device_name": "SYNTHETIC"},
              "extensions": {"VK_TEST_present": 2},
              "features": {"Feature.true": True, "Feature.false": False, "Feature.bad": 1},
              "limits": {"Limit.max": 16, "Limit.min": 4},
              "formats": {"VK_FORMAT_TEST": {"optimalTilingFeatures": 0x11}}}
    rows = [
        ({"kind": "feature", "key": "Feature.true", "value": True}, "supported"),
        ({"kind": "feature", "key": "Feature.false", "value": True}, "unsupported"),
        ({"kind": "feature", "key": "Feature.missing", "value": True}, "unknown"),
        ({"kind": "feature", "key": "Feature.bad", "value": True}, "unknown"),
        ({"kind": "extension", "key": "VK_TEST_present", "op": "ge", "value": 2}, "supported"),
        ({"kind": "extension", "key": "VK_TEST_present", "op": "ge", "value": 3}, "unsupported"),
        ({"kind": "extension", "key": "VK_TEST_missing"}, "unsupported"),
        ({"kind": "extension", "key": "VK_TEST_promoted", "core_since": [1, 2, 0]}, "supported"),
        ({"kind": "extension", "key": "VK_TEST_promoted", "core_since": [1, 3, 0]}, "unsupported"),
        ({"kind": "limit", "key": "Limit.max", "op": "ge", "value": 16}, "supported"),
        ({"kind": "limit", "key": "Limit.max", "op": "ge", "value": 17}, "unsupported"),
        ({"kind": "limit", "key": "Limit.min", "op": "le", "value": 4}, "supported"),
        ({"kind": "limit", "key": "Limit.min", "op": "le", "value": 3}, "unsupported"),
        ({"kind": "api", "op": "ge", "value": [1, 2, 0]}, "supported"),
        ({"kind": "api", "op": "ge", "value": [1, 3, 0]}, "unsupported"),
        ({"kind": "format", "format": "VK_FORMAT_TEST", "key": "optimalTilingFeatures", "op": "bits_all", "value": 0x11}, "supported"),
        ({"kind": "format", "format": "VK_FORMAT_TEST", "key": "optimalTilingFeatures", "op": "bits_all", "value": 0x12}, "unsupported"),
        ({"kind": "format", "format": "VK_FORMAT_MISSING", "key": "optimalTilingFeatures", "op": "bits_all", "value": 1}, "unknown"),
        ({"kind": "manual", "key": "native_UIKit_Zink_WSI"}, "unknown"),
        ({"kind": "unsupported_schema_kind", "value": True}, "unknown"),
    ]
    false = {"kind": "feature", "key": "Feature.false", "value": True}
    missing = {"kind": "feature", "key": "missing", "value": True}
    true = {"kind": "feature", "key": "Feature.true", "value": True}
    rows += [({"kind": "any", "any_of": [false, missing]}, "unknown"),
             ({"kind": "any", "any_of": [missing, true]}, "supported"),
             ({"kind": "any", "any_of": [false, false]}, "unsupported"),
             ({"kind": "any", "any_of": []}, "unknown"),
             ({"kind": "all", "all_of": [true, missing]}, "unknown"),
             ({"kind": "all", "all_of": [true, false]}, "unsupported"),
             ({"kind": "all", "all_of": [true, true]}, "supported"),
             ({"kind": "any", "any_of": [{"kind": "all", "all_of": [true, false]}, {"kind": "all", "all_of": [true, true]}]}, "supported")]
    return [(dict(row, id=f"case-{index}"), copy.deepcopy(device), expected)
            for index, (row, expected) in enumerate(rows)]


class ComparisonTests(unittest.TestCase):
    def test_supported_unsupported_unknown_and_numeric_rules(self):
        for row, device, expected in comparison_cases():
            with self.subTest(row=row):
                self.assertEqual(evaluate(row, device, {})["status"], expected)

    def test_extension_advertisement_does_not_satisfy_feature_requirement(self):
        device = {"extensions": {"VK_EXT_robustness2": 1}, "features": {"VkPhysicalDeviceRobustness2FeaturesEXT.nullDescriptor": False}}
        row = {"kind": "feature", "key": "VkPhysicalDeviceRobustness2FeaturesEXT.nullDescriptor", "value": True}
        self.assertEqual(evaluate(row, device, {})["status"], "unsupported")
        device["features"].clear()
        self.assertEqual(evaluate(row, device, {})["status"], "unknown")

    def test_failed_enumeration_is_unknown_and_instance_extensions_are_separate(self):
        row = {"kind": "extension", "key": "VK_TEST"}
        self.assertEqual(evaluate(row, {}, {})["status"], "unknown")
        self.assertEqual(evaluate(row, {"extensions": {}}, {})["status"], "unsupported")
        row["kind"] = "instance_extension"
        self.assertEqual(evaluate(row, {"extensions": {"VK_TEST": 1}}, {"extensions": {}})["status"], "unsupported")
        self.assertEqual(evaluate(row, {}, {"extensions": {"VK_TEST": 1}})["status"], "supported")

    def test_group_precedence_and_advisory_requirements(self):
        yes = {"kind": "feature", "key": "yes", "value": True}
        no = {"kind": "feature", "key": "no", "value": True}
        unknown = {"kind": "manual"}
        device = {"features": {"yes": True, "no": False}}
        self.assertEqual(evaluate_group([yes, unknown], device, {})["status"], "unknown")
        self.assertEqual(evaluate_group([no, unknown], device, {})["status"], "unsupported")
        report = evaluate_group([yes, dict(no, severity="advisory")], device, {})
        self.assertEqual(report["status"], "supported")
        self.assertEqual(report["counts"]["unsupported"], 1)
        self.assertEqual(evaluate_group([], device, {})["status"], "unknown")

    def test_cli_exports_comparison_without_certifying_viability(self):
        row, device, _ = comparison_cases()[0]
        req = {"mesa_version": "25.1.9", "profiles": {"SYNTHETIC": {"requirements": [row]}}, "runtime_checks": [{"kind": "manual"}]}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            caps, requirements, output = directory / "caps.json", directory / "req.json", directory / "out.json"
            caps.write_text(json.dumps({"devices": [device]}), encoding="utf-8")
            requirements.write_text(json.dumps(req), encoding="utf-8")
            self.assertEqual(main([str(caps), "--requirements", str(requirements), "--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["devices"][0]["groups"]["SYNTHETIC"]["status"], "supported")
            self.assertEqual(report["zink_viability"], "unknown_until_actual_zink_and_presentation_tests")

    def test_manifest_is_pinned_and_has_separate_profile_and_runtime_checks(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "data/mesa-25.1.9-requirements.json").read_text())
        self.assertEqual(manifest["mesa_version"], "25.1.9")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(manifest["sources"])
        self.assertTrue(manifest["profiles"])
        self.assertTrue(manifest["runtime_checks"])


if __name__ == "__main__":
    unittest.main()
