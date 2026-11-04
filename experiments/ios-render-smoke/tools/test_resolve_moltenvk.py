"""Host-only resolver tests. No Apple SDK, libraries, downloads or builds needed."""

from pathlib import Path
import plistlib
import tempfile
import unittest

from resolve_moltenvk import ResolutionError, ResolvedMoltenVK, main, render_cmake, resolve_moltenvk


class ResolveMoltenVKTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def framework(self, name="static", *, variant=None, platform="ios", architectures=None,
                  library_path="libMoltenVK.a", headers=True, identifier="ios-arm64"):
        framework = self.root / name / "MoltenVK.xcframework"
        framework.mkdir(parents=True)
        entry = {
            "LibraryIdentifier": identifier,
            "LibraryPath": library_path,
            "SupportedArchitectures": architectures if architectures is not None else ["arm64"],
            "SupportedPlatform": platform,
            "HeadersPath": "Headers",
        }
        if variant is not None:
            entry["SupportedPlatformVariant"] = variant
        with (framework / "Info.plist").open("wb") as output:
            plistlib.dump({"AvailableLibraries": [entry]}, output)
        slice_dir = framework / identifier
        slice_dir.mkdir(parents=True)
        library = slice_dir / library_path
        library.parent.mkdir(parents=True, exist_ok=True)
        library.write_bytes(b"!<arch>\n")
        if headers:
            (slice_dir / "Headers" / "vulkan").mkdir(parents=True)
            (slice_dir / "Headers" / "vulkan" / "vulkan.h").write_text("/* fixture */", encoding="utf-8")
        return framework, entry

    def write_metadata(self, framework, entries):
        with (framework / "Info.plist").open("wb") as output:
            plistlib.dump({"AvailableLibraries": entries}, output)

    def test_selects_device_among_simulator_and_dynamic(self):
        device, _ = self.framework()
        self.framework("simulator", variant="simulator")
        self.framework("dynamic", library_path="MoltenVK.framework/MoltenVK")
        resolved = resolve_moltenvk(self.root)
        self.assertEqual(resolved.xcframework, device.resolve())
        self.assertEqual(resolved.library, (device / "ios-arm64" / "libMoltenVK.a").resolve())
        self.assertTrue((resolved.include_dir / "vulkan" / "vulkan.h").is_file())

    def test_root_can_be_xcframework(self):
        framework, _ = self.framework()
        self.assertEqual(resolve_moltenvk(framework).xcframework, framework.resolve())

    def test_rejects_wrong_platform_architecture_and_variant(self):
        for arguments in (
            {"variant": "simulator"}, {"variant": "maccatalyst"},
            {"platform": "macos"}, {"architectures": ["x86_64"]},
            {"library_path": "MoltenVK.framework/MoltenVK"}, {"library_path": "libMoltenVK.dylib"},
        ):
            with self.subTest(arguments=arguments):
                framework, _ = self.framework(str(len(list(self.root.iterdir()))), **arguments)
                with self.assertRaisesRegex(ResolutionError, "No static arm64 iOS device"):
                    resolve_moltenvk(framework)

    def test_rejects_missing_headers(self):
        framework, _ = self.framework(headers=False)
        with self.assertRaisesRegex(ResolutionError, "No Vulkan headers"):
            resolve_moltenvk(framework)

    def test_finds_distribution_headers_next_to_static(self):
        framework, _ = self.framework(headers=False)
        headers = self.root / "include" / "vulkan"
        headers.mkdir(parents=True)
        (headers / "vulkan.h").write_text("/* distribution fixture */", encoding="utf-8")
        self.assertEqual(resolve_moltenvk(framework).include_dir, headers.parent.resolve())

    def test_official_static_layout_without_xcframework_headers(self):
        # MoltenVK 1.4.2 omits -headers when creating the XCFramework and
        # separately packages MoltenVK/include next to MoltenVK/static/.
        framework, entry = self.framework("MoltenVK/static", headers=False)
        del entry["HeadersPath"]
        self.write_metadata(framework, [entry])
        headers = self.root / "MoltenVK" / "include" / "vulkan"
        headers.mkdir(parents=True)
        (headers / "vulkan.h").write_text("/* official layout fixture */", encoding="utf-8")
        self.assertEqual(resolve_moltenvk(self.root).include_dir, headers.parent.resolve())

    def test_prefers_headers_from_exact_slice(self):
        framework, _ = self.framework()
        headers = self.root / "include" / "vulkan"
        headers.mkdir(parents=True)
        (headers / "vulkan.h").write_text("/* other version */", encoding="utf-8")
        self.assertEqual(resolve_moltenvk(framework).include_dir, (framework / "ios-arm64" / "Headers").resolve())

    def test_rejects_multiple_static_frameworks(self):
        self.framework("first")
        self.framework("second")
        with self.assertRaisesRegex(ResolutionError, "Ambiguous static arm64 iOS device"):
            resolve_moltenvk(self.root)

    def test_rejects_multiple_device_entries_in_one_framework(self):
        framework, entry = self.framework()
        self.write_metadata(framework, [entry, entry.copy()])
        with self.assertRaisesRegex(ResolutionError, "Ambiguous static arm64 iOS device"):
            resolve_moltenvk(framework)

    def test_rejects_missing_archive(self):
        framework, _ = self.framework()
        (framework / "ios-arm64" / "libMoltenVK.a").unlink()
        with self.assertRaisesRegex(ResolutionError, "archive is missing"):
            resolve_moltenvk(framework)

    def test_rejects_metadata_path_traversal(self):
        for field in ("LibraryIdentifier", "LibraryPath", "HeadersPath"):
            with self.subTest(field=field):
                framework, entry = self.framework(field)
                entry[field] = "../outside.a" if field == "LibraryPath" else "../outside"
                self.write_metadata(framework, [entry])
                with self.assertRaisesRegex(ResolutionError, "escapes"):
                    resolve_moltenvk(framework)

    def test_rejects_malformed_metadata(self):
        framework, _ = self.framework()
        (framework / "Info.plist").write_bytes(b"not a plist")
        with self.assertRaisesRegex(ResolutionError, "Cannot read XCFramework metadata"):
            resolve_moltenvk(framework)

    def test_cmake_paths_are_literal_and_delimiter_safe(self):
        # A synthetic path avoids host filename restrictions (quotes on Windows).
        unusual = Path('/dependency space/${unexpanded};"quote"]=]/libMoltenVK.a')
        result = render_cmake(ResolvedMoltenVK(unusual, unusual.parent, unusual.parent))
        self.assertIn("set(SMOKE_MOLTENVK_LIBRARY [==[", result)
        self.assertIn(unusual.as_posix(), result)
        self.assertIn("${unexpanded};", result)
        self.assertEqual(result.count("\nset("), 3)

    def test_cli_writes_only_literal_cmake_variables(self):
        framework, _ = self.framework()
        output = self.root / "generated" / "dependency.cmake"
        self.assertEqual(main(["--root", str(framework), "--output", str(output)]), 0)
        generated = output.read_text(encoding="utf-8")
        self.assertIn("set(SMOKE_MOLTENVK_LIBRARY", generated)
        self.assertIn("set(SMOKE_VULKAN_INCLUDE_DIR", generated)
        self.assertIn("set(SMOKE_MOLTENVK_XCFRAMEWORK", generated)


if __name__ == "__main__":
    unittest.main()
