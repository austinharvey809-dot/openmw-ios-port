"""Regression checks for facts extracted from Mesa's exact mesa-25.1.9 tag."""

import json
from pathlib import Path
import unittest


MANIFEST = Path(__file__).resolve().parents[1] / "data/mesa-25.1.9-requirements.json"


def leaves(row):
    if row.get("kind") in ("any", "all"):
        for child in row["any_of" if row["kind"] == "any" else "all_of"]:
            yield from leaves(child)
    else:
        yield row


class PinnedRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def gl21(self):
        return self.manifest["profiles"]["VP_ZINK_gl21_baseline"]["requirements"]

    def test_exact_profile_inventory_and_api_metadata(self):
        self.assertEqual(self.manifest["mesa_version"], "25.1.9")
        profiles = self.manifest["profiles"]
        expected = {f"VP_ZINK_gl{level}_baseline" for level in (21, 30, 31, 32, 33, 40, 41, 42, 43, 44, 45, 46)}
        self.assertEqual(set(profiles), expected | {"VP_ZINK_gl46_optimal"})
        self.assertEqual(self.manifest["normalization"]["capability_block_count"], 50)
        for name, profile in profiles.items():
            expected_api = [1, 2, 0] if name.split("_gl", 1)[1][:2] in ("21", "30", "31", "32", "33", "40", "41", "42") else [1, 3, 0]
            self.assertEqual(profile["requirements"][0]["value"], expected_api)

    def test_gl21_preserves_ten_literal_extensions_and_feature_contract(self):
        flattened = [item for row in self.gl21() for item in leaves(row)]
        extensions = {row["key"] for row in flattened if row["kind"] == "extension"}
        self.assertEqual(extensions, {
            "VK_KHR_maintenance1", "VK_KHR_create_renderpass2", "VK_KHR_imageless_framebuffer",
            "VK_KHR_timeline_semaphore", "VK_EXT_custom_border_color", "VK_EXT_line_rasterization",
            "VK_KHR_swapchain_mutable_format", "VK_KHR_incremental_present", "VK_EXT_border_color_swizzle",
            "VK_KHR_descriptor_update_template", "VK_EXT_scalar_block_layout",
        })  # Ten shared entries plus the extension-path alternative's scalar block layout.
        for row in flattened:
            if row["kind"] == "extension":
                self.assertEqual(row["value"], 1)
                self.assertNotIn("core_since", row)
        keys = {row["key"] for row in flattened}
        for name in ("robustBufferAccess", "logicOp", "fillModeNonSolid", "alphaToOne", "shaderClipDistance"):
            self.assertIn("VkPhysicalDeviceFeatures." + name, keys)
        self.assertNotIn("VkPhysicalDeviceRobustness2FeaturesEXT.nullDescriptor", keys)

    def test_api_alternatives_are_whole_conjunctions_not_mixed_fields(self):
        alternatives = [row for row in self.gl21() if row["kind"] == "any"]
        self.assertEqual(len(alternatives), 2)
        api = alternatives[0]
        self.assertEqual([row["kind"] for row in api["any_of"]], ["all", "all"])
        extension_path, vulkan12_path = [list(leaves(row)) for row in api["any_of"]]
        self.assertEqual(len(extension_path), 4)
        self.assertEqual({row["key"] for row in vulkan12_path}, {
            "VkPhysicalDeviceVulkan12Features.scalarBlockLayout", "VkPhysicalDeviceVulkan12Features.drawIndirectCount",
            "VkPhysicalDeviceVulkan12Features.imagelessFramebuffer", "VkPhysicalDeviceVulkan12Features.timelineSemaphore",
        })
        line = [list(leaves(row)) for row in alternatives[1]["any_of"]]
        self.assertEqual(line[0][0]["key"], "VkPhysicalDeviceLineRasterizationFeaturesEXT.bresenhamLines")
        self.assertEqual((line[1][0]["key"], line[1][0]["value"]), ("VkPhysicalDeviceLimits.strictLines", False))

    def test_startup_four_required_extensions_and_timeline_predicate(self):
        runtime = self.manifest["runtime_checks"]
        required_extensions = {row["key"] for row in runtime if row["id"].startswith("runtime.required.")}
        self.assertEqual(required_extensions, {
            "VK_KHR_maintenance1", "VK_KHR_create_renderpass2", "VK_KHR_imageless_framebuffer",
            "VK_KHR_descriptor_update_template",
        })
        self.assertTrue(all("core_since" in row for row in runtime if row["id"].startswith("runtime.required.")))
        timeline = next(row for row in runtime if row["id"] == "runtime.timeline.startup_predicate")
        self.assertEqual(timeline["kind"], "any")
        self.assertEqual({row["key"] for row in timeline["any_of"]}, {
            "VK_KHR_timeline_semaphore", "VkPhysicalDeviceVulkan12Features.timelineSemaphore"})

    def test_optional_descriptor_path_and_kopper_usage_are_distinct(self):
        runtime = self.manifest["runtime_checks"]
        descriptor = next(row for row in runtime if row["id"] == "runtime.descriptor_buffer.null_descriptor_condition")
        self.assertEqual(descriptor["severity"], "advisory")
        self.assertEqual(descriptor["kind"], "all")
        usage = next(row for row in runtime if row["id"] == "runtime.presentation.kopper_usage")
        self.assertEqual((usage["kind"], usage["op"], usage["value"]), ("surface", "bits_all", 0x17))
        self.assertTrue(any(row["kind"] == "manual" for row in runtime))

    def test_upstream_snapshot_identity_and_gl46_optionals_preserved(self):
        source = self.manifest["sources"][0]
        self.assertEqual(source["sha256_utf8"], "10fed270d703d477e068e42b838d449130011c7ee012eb4a27b7e7821f002983")
        optimal = self.manifest["profiles"]["VP_ZINK_gl46_optimal"]
        self.assertTrue(optimal["optional_blocks"])
        optional_checks = [row for row in optimal["requirements"] if row.get("severity") == "advisory"]
        self.assertEqual(len(optional_checks), len(optimal["optional_blocks"]))
        self.assertTrue(all(row.get("severity") != "advisory" for row in self.gl21()))


if __name__ == "__main__":
    unittest.main()
