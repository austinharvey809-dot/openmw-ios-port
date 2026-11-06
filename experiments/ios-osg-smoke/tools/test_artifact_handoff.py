"""Offline producer/upload/download/consumer and verified tar-layout regressions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import tarfile
import tempfile
import unittest

from test_package_ios import binary

ROOT = Path(__file__).resolve().parents[1]
ANGLE = ROOT.parent / "ios-angle-smoke"
WORKFLOW = ROOT.parents[1] / ".github/workflows/ios-osg-smoke.yml"
spec = importlib.util.spec_from_file_location("osg_handoff_angle_validator", ANGLE / "tools/validate_dependency.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class WorkflowHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = dict(re.findall(r"^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)",
                                  cls.text.split("\njobs:\n", 1)[1], re.M | re.S))

    def test_all_uploads_follow_each_jobs_actual_output_directory(self):
        self.assertEqual(set(self.jobs), {"lightweight-validation", "gate-0-dependency", "gate-1-application"})
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertIn("      EXPERIMENT: experiments/ios-osg-smoke\n", job)
                self.assertIn('mkdir -p "$EXPERIMENT/artifacts"', job)
                uploads = re.findall(r"      - uses: actions/upload-artifact@v6\n(.*?)(?=^      - |\Z)", job, re.M | re.S)
                self.assertEqual(len(uploads), 1)
                self.assertIn("path: ${{ env.EXPERIMENT }}/artifacts/", uploads[0])
                self.assertIn("if-no-files-found: error", uploads[0])
                self.assertIn("if: always()", uploads[0])
        self.assertNotIn("experiments/ios-angle-smoke/artifacts", self.text)

    def test_producer_upload_download_restore_and_cmake_agree(self):
        producer, consumer = self.jobs["gate-0-dependency"], self.jobs["gate-1-application"]
        outputs = re.findall(r'--output "([^"\n]+)"', producer)
        self.assertEqual(outputs, ["$RUNNER_TEMP/angle-ios-arm64"] * 2)
        self.assertIn('tar -czf "$EXPERIMENT/artifacts/angle-ios-arm64.tar.gz" -C "$RUNNER_TEMP" angle-ios-arm64', producer)
        name = "ios-osg-angle-gate-0-${{ github.run_id }}"
        self.assertIn("name: " + name, producer)
        self.assertIn("name: " + name, consumer)
        self.assertIn("path: dependency-artifact", consumer)
        self.assertIn('tar -xzf dependency-artifact/angle-ios-arm64.tar.gz -C "$RUNNER_TEMP"', consumer)
        self.assertIn('-DANGLE_ROOT="$RUNNER_TEMP/angle-ios-arm64"', consumer)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('--root "${ANGLE_ROOT}" --resolve', cmake)

    def test_archive_is_required_and_revalidated_before_osg_source_download(self):
        producer, consumer = self.jobs["gate-0-dependency"], self.jobs["gate-1-application"]
        self.assertIn('test -s "$EXPERIMENT/artifacts/angle-ios-arm64.tar.gz" ||', producer)
        self.assertIn('tar -tzf "$EXPERIMENT/artifacts/angle-ios-arm64.tar.gz"', producer)
        self.assertIn('test -s dependency-artifact/angle-ios-arm64.tar.gz ||', consumer)
        for job, output in ((producer, "angle-produced.cmake"), (consumer, "angle-restored.cmake")):
            self.assertIn('python3 experiments/ios-angle-smoke/tools/validate_dependency.py', job)
            self.assertIn('--root "$RUNNER_TEMP/angle-ios-arm64" --resolve "$EXPERIMENT/artifacts/' + output + '"', job)
        self.assertLess(consumer.index("angle-restored-validation.log"), consumer.index('tools/prepare_osg.py'))

    def test_final_ipa_and_logs_are_in_the_uploaded_directory(self):
        consumer = self.jobs["gate-1-application"]
        self.assertIn('--output "$EXPERIMENT/artifacts/IOSOSGSmoke-unsigned.ipa"', consumer)
        self.assertIn('--report "$EXPERIMENT/artifacts/ipa-validation.json"', consumer)
        self.assertIn('"$EXPERIMENT/artifacts/IOSOSGSmoke-compile-evidence.tar.gz"', consumer)
        self.assertIn('tee "$EXPERIMENT/artifacts/gate-1-build.log"', consumer)


class PackageHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "producer/angle-ios-arm64"
        lock = json.loads((ANGLE / "data/angle-lock.json").read_text(encoding="utf-8"))
        self.write("angle-lock.json", (ANGLE / "data/angle-lock.json").read_bytes())
        self.write("args.gn", (ANGLE / "args.gn").read_bytes())
        self.write("Licenses/LICENSE", b"synthetic license fixture")
        self.write("gclient-revinfo.txt", b"synthetic pinned graph fixture")
        self.write("dependency-validation.json", b"{}")
        libraries = {}
        for role, name in (("egl", "libEGL"), ("gles", "libGLESv2")):
            libraries[role] = f"Frameworks/{name}.framework/{name}"
            self.write(libraries[role], binary(filetype=6, install_name=f"@rpath/{name}.framework/{name}",
                       rpaths=["@executable_path/Frameworks", "@loader_path/Frameworks"]))
            self.write(f"Frameworks/{name}.framework/Info.plist", plistlib.dumps({"CFBundleExecutable": name,
                "CFBundlePackageType": "FMWK", "CFBundleSupportedPlatforms": ["iPhoneOS"]}))
        for header in ("EGL/egl.h", "GLES3/gl3.h", "KHR/khrplatform.h"):
            self.write("include/" + header, b"synthetic header fixture")
        self.write("angle-build.json", json.dumps({"angle_revision": lock["angle_revision"],
            "target": "arm64-apple-ios18.0", "metal_only": True, "validation": "device-binary-and-sdk-passed",
            "libraries": libraries}).encode())
        hashes = {path.relative_to(self.package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in self.package.rglob("*") if path.is_file()}
        self.write("package-hashes.json", json.dumps(hashes).encode())

    def write(self, name, data):
        path = self.package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def restore(self, archive_root="angle-ios-arm64"):
        # Same archive member root as tar -C RUNNER_TEMP angle-ios-arm64, then
        # download-artifact extracts the outer GitHub artifact into its path.
        download = self.root / "dependency-artifact"
        download.mkdir()
        archive = download / "angle-ios-arm64.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(self.package, arcname=archive_root)
        destination = self.root / "consumer-temp"
        destination.mkdir()
        with tarfile.open(archive) as source:
            if hasattr(tarfile, "data_filter"):
                source.extractall(destination, filter="data")
            else:
                # Python 3.10 before extraction-filter backports; this archive
                # contains only the fixture files created immediately above.
                source.extractall(destination)
        return destination / "angle-ios-arm64"

    def test_tar_round_trip_retains_expected_frameworks_headers_metadata_and_hashes(self):
        validator.resolve(self.package, self.root / "produced.cmake")
        restored = self.restore()
        validator.resolve(restored, self.root / "restored.cmake")
        expected = {path.relative_to(self.package).as_posix(): path.read_bytes()
                    for path in self.package.rglob("*") if path.is_file()}
        actual = {path.relative_to(restored).as_posix(): path.read_bytes()
                  for path in restored.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        for name in ("angle-lock.json", "angle-build.json", "package-hashes.json", "dependency-validation.json",
                     "gclient-revinfo.txt", "args.gn", "include/GLES3/gl3.h", "Licenses/LICENSE",
                     "Frameworks/libEGL.framework/libEGL", "Frameworks/libGLESv2.framework/libGLESv2"):
            self.assertIn(name, actual)
        self.assertIn((restored / "Frameworks/libEGL.framework/libEGL").as_posix(),
                      (self.root / "restored.cmake").read_text(encoding="utf-8"))

    def test_wrong_archive_root_fails_before_a_consumer_can_use_the_package(self):
        restored = self.restore("wrong-root")
        with self.assertRaises(OSError): validator.resolve(restored, self.root / "resolved.cmake")

    def test_missing_framework_or_changed_contents_fail_original_verifier(self):
        restored = self.restore()
        (restored / "Licenses/LICENSE").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            validator.resolve(restored, self.root / "resolved.cmake")
        (restored / "Frameworks/libGLESv2.framework/libGLESv2").unlink()
        with self.assertRaises((ValueError, OSError)):
            validator.resolve(restored, self.root / "resolved.cmake")


if __name__ == "__main__":
    unittest.main()
