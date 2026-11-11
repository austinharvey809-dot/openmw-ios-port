"""Offline contracts for the G0B acquisition and manual host workflow."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import audit_g0
import prepare_bullet
import validate_build


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT.parents[1] / ".github/workflows/ios-openmw-nif-host-smoke.yml"


def configured_build(root):
    build, bullet = root / "build", root / "bullet"
    build.mkdir()
    settings = ("USE_DOUBLE_PRECISION:BOOL=ON\nBUILD_SHARED_LIBS:BOOL=OFF\n"
                "BUILD_BULLET3:BOOL=OFF\nBUILD_BULLET2_DEMOS:BOOL=OFF\n"
                "BUILD_OPENGL3_DEMOS:BOOL=OFF\nBUILD_PYBULLET:BOOL=OFF\n"
                "DYNAMIC_OPENSCENEGRAPH:BOOL=OFF\nDYNAMIC_OPENTHREADS:BOOL=OFF\n"
                "OSG_USE_FLOAT_BOUNDINGSPHERE:BOOL=ON\nOSG_USE_FLOAT_BOUNDINGBOX:BOOL=ON\n"
                "OSG_USE_FLOAT_MATRIX:BOOL=OFF\nOSG_USE_FLOAT_QUAT:BOOL=OFF\n")
    (build / "CMakeCache.txt").write_text(settings, encoding="utf-8")
    files = (root / "components/nif/node.cpp", bullet / "src/BulletCollision/btShape.cpp",
             bullet / "src/LinearMath/btMath.cpp")
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    write_commands(build, files)
    return build, bullet, files


def write_commands(build, files, missing_precision=()):
    commands = [{"file": str(file),
                 "command": "c++ " + ("" if index in missing_precision else "-DBT_USE_DOUBLE_PRECISION ")
                 + "-c " + str(file)}
                for index, file in enumerate(files)]
    (build / "compile_commands.json").write_text(json.dumps(commands), encoding="utf-8")


class FakeResponse(io.BytesIO):
    def __init__(self, data, content_length=None):
        super().__init__(data)
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


def tiny_bullet_archive(path, unsafe=False):
    with tarfile.open(path, "w:gz") as archive:
        for name, data in (("CMakeLists.txt", b"cmake_minimum_required(VERSION 3.16)\n"),
                           ("LICENSE.txt", b"synthetic test license\n")):
            member = tarfile.TarInfo("bullet3-3.25/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if unsafe:
            member = tarfile.TarInfo("bullet3-3.25/escape")
            member.type = tarfile.SYMTYPE
            member.linkname = "../../escape"
            archive.addfile(member)


class BulletAcquisitionContracts(unittest.TestCase):
    def test_exact_upstream_pin_is_still_in_openmw(self):
        prepare_bullet.verify_upstream_pin()
        self.assertEqual(prepare_bullet.URL,
                         "https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz")
        self.assertEqual(len(prepare_bullet.SHA512), 128)
        self.assertEqual(prepare_bullet.SHA512,
                         "7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674"
                         "e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4")

    def test_checksum_mismatch_stops_before_archive_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-bullet.tar.gz"
            path.write_bytes(b"not the approved Bullet archive")
            with self.assertRaisesRegex(ValueError, "SHA-512 mismatch"):
                prepare_bullet.verify_archive(path)

    def test_archive_members_reject_traversal_links_and_duplicates(self):
        def member(name, kind=tarfile.REGTYPE):
            value = tarfile.TarInfo(name)
            value.type = kind
            return value

        clean = [member("bullet3-3.25", tarfile.DIRTYPE),
                 member("bullet3-3.25/CMakeLists.txt"), member("bullet3-3.25/LICENSE.txt")]
        self.assertIn("bullet3-3.25/LICENSE.txt", prepare_bullet.inspect_members(clean))
        for bad in (member("bullet3-3.25/../escape"),
                    member("/bullet3-3.25/absolute"),
                    member("bullet3-3.25/src\\wrong"),
                    member("bullet3-3.25/link", tarfile.SYMTYPE)):
            with self.subTest(bad=bad.name), self.assertRaises(ValueError):
                prepare_bullet.inspect_members(clean + [bad])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare_bullet.inspect_members(clean + [member("bullet3-3.25/license.TXT")])
        with self.assertRaisesRegex(ValueError, "license"):
            prepare_bullet.inspect_members(clean[:2])


class BulletDownloadContracts(unittest.TestCase):
    def test_sparse_archive_between_old_and_new_limits_passes_size_gate(self):
        self.assertEqual(prepare_bullet.MAX_ARCHIVE, 192 * 1024 * 1024)
        self.assertEqual(prepare_bullet.MAX_EXPANDED, 1024 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.tar.gz"
            with path.open("wb") as target:
                target.seek(101 * 1024 * 1024 - 1)
                target.write(b"\0")
            # Only the size gate is under test; the sparse file is not Bullet.
            with patch.object(prepare_bullet, "digest", return_value=prepare_bullet.SHA512):
                self.assertEqual(prepare_bullet.verify_archive(path), prepare_bullet.SHA512)

    def test_sparse_archive_above_new_limit_is_rejected_before_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "too-large.tar.gz"
            with path.open("wb") as target:
                target.seek(prepare_bullet.MAX_ARCHIVE)
                target.write(b"\0")
            with patch.object(prepare_bullet, "digest") as digest:
                with self.assertRaisesRegex(ValueError, "too large"):
                    prepare_bullet.verify_archive(path)
                digest.assert_not_called()

    def test_excessive_content_length_rejected_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"unused", prepare_bullet.MAX_ARCHIVE + 1)
            with patch.object(prepare_bullet.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "Content-Length exceeds limit"):
                    prepare_bullet.acquire(root / "output", root / "evidence", download=True)
            diagnostic = json.loads((root / "evidence/bullet-acquisition-error.json").read_text())
            self.assertEqual(diagnostic["compressed_archive_limit_bytes"], prepare_bullet.MAX_ARCHIVE)
            self.assertTrue(diagnostic["http_content_length_provided"])
            self.assertEqual(diagnostic["http_content_length_bytes"], prepare_bullet.MAX_ARCHIVE + 1)
            self.assertEqual(diagnostic["bytes_downloaded"], 0)
            self.assertFalse(diagnostic["transfer_completed"])
            self.assertFalse(diagnostic["sha512_verification_attempted"])
            self.assertFalse((root / "output/bullet-3.25.tar.gz").exists())
            self.assertFalse((root / "output/source").exists())

    def test_missing_content_length_still_streams_with_a_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"0123456789")
            with patch.object(prepare_bullet, "MAX_ARCHIVE", 8), \
                    patch.object(prepare_bullet.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "download exceeds limit"):
                    prepare_bullet.acquire(root / "output", root / "evidence", download=True)
            diagnostic = json.loads((root / "evidence/bullet-acquisition-error.json").read_text())
            self.assertEqual(diagnostic["compressed_archive_limit_bytes"], 8)
            self.assertFalse(diagnostic["http_content_length_provided"])
            self.assertIsNone(diagnostic["http_content_length_bytes"])
            self.assertEqual(diagnostic["bytes_downloaded"], 9)
            self.assertEqual(response.read_sizes, [8, 1])
            self.assertFalse(diagnostic["transfer_completed"])
            self.assertFalse(diagnostic["sha512_verification_attempted"])
            self.assertFalse((root / "output/bullet-3.25.tar.gz").exists())
            self.assertFalse((root / "output/source").exists())

    def test_incomplete_declared_transfer_does_not_attempt_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"short", 10)
            with patch.object(prepare_bullet.urllib.request, "urlopen", return_value=response), \
                    patch.object(prepare_bullet, "digest") as digest:
                with self.assertRaisesRegex(ValueError, "length differs"):
                    prepare_bullet.acquire(root / "output", root / "evidence", download=True)
                digest.assert_not_called()
            diagnostic = json.loads((root / "evidence/bullet-acquisition-error.json").read_text())
            self.assertEqual(diagnostic["bytes_downloaded"], 5)
            self.assertEqual(diagnostic["http_content_length_bytes"], 10)
            self.assertFalse(diagnostic["transfer_completed"])
            self.assertNotIn("actual_sha512", diagnostic)
            self.assertFalse((root / "output/bullet-3.25.tar.gz").exists())

    def test_complete_transfer_with_bad_hash_never_reaches_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b"complete but not the pinned Bullet source"
            response = FakeResponse(data, len(data))
            with patch.object(prepare_bullet.urllib.request, "urlopen", return_value=response), \
                    patch.object(prepare_bullet.tarfile, "open") as tar_open:
                with self.assertRaisesRegex(ValueError, "SHA-512 mismatch"):
                    prepare_bullet.acquire(root / "output", root / "evidence", download=True)
                tar_open.assert_not_called()
            diagnostic = json.loads((root / "evidence/bullet-acquisition-error.json").read_text())
            self.assertEqual(diagnostic["bytes_downloaded"], len(data))
            self.assertTrue(diagnostic["transfer_completed"])
            self.assertTrue(diagnostic["sha512_verification_attempted"])
            self.assertEqual(diagnostic["actual_sha512"], hashlib.sha512(data).hexdigest())
            self.assertFalse(diagnostic["archive_verified"])
            self.assertFalse((root / "output/source").exists())
            self.assertFalse((root / "evidence/bullet-provenance.json").exists())

    def test_unsafe_member_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.tar.gz"
            tiny_bullet_archive(archive, unsafe=True)
            # The tiny fixture is not the pinned archive; exercise the member gate in isolation.
            with patch.object(prepare_bullet, "verify_archive", return_value=prepare_bullet.SHA512):
                with self.assertRaisesRegex(ValueError, "Unsafe Bullet archive member"):
                    prepare_bullet.extract_verified(archive, root / "source")
            self.assertFalse((root / "source").exists())

    def test_license_and_provenance_preserved_after_verified_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "synthetic.tar.gz"
            tiny_bullet_archive(archive)
            # Mock only checksum verification: the extraction and evidence paths remain real.
            with patch.object(prepare_bullet, "verify_archive", return_value=prepare_bullet.SHA512):
                report = prepare_bullet.acquire(root / "output", root / "evidence", archive=archive)
            license_data = (root / "evidence/bullet-license-0.txt").read_bytes()
            self.assertEqual(license_data, b"synthetic test license\n")
            self.assertEqual(report["license_evidence_sha256"]["bullet-license-0.txt"],
                             hashlib.sha256(license_data).hexdigest())
            self.assertEqual(report["source_url"], prepare_bullet.URL)
            self.assertEqual(report["archive_sha512"], prepare_bullet.SHA512)
            self.assertEqual(json.loads((root / "evidence/bullet-provenance.json").read_text()), report)
            self.assertEqual(json.loads((root / "output/bullet-provenance.json").read_text()), report)

    def test_network_failure_writes_diagnostic_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(prepare_bullet.urllib.request, "urlopen", side_effect=OSError("offline test")):
                with self.assertRaisesRegex(OSError, "offline test"):
                    prepare_bullet.acquire(root / "output", root / "evidence", download=True)
            diagnostic = json.loads((root / "evidence/bullet-acquisition-error.json").read_text())
            self.assertEqual(diagnostic["failure_reason"], "offline test")
            self.assertEqual(diagnostic["bytes_downloaded"], 0)
            self.assertFalse(diagnostic["transfer_completed"])
            self.assertFalse(diagnostic["sha512_verification_attempted"])
            self.assertEqual((root / "evidence/bullet-acquisition-error.txt").read_text(), "offline test\n")


class SourceAndWorkflowContracts(unittest.TestCase):
    def test_parser_source_and_fixture_bytes_match_reviewed_baseline(self):
        audit_g0.verify()

    def test_source_hash_change_is_rejected(self):
        baseline = json.loads(audit_g0.SOURCE_MANIFEST.read_text(encoding="utf-8"))
        baseline["sha256_lf"]["components/nif/node.cpp"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            replacement = Path(directory) / "wrong.json"
            replacement.write_text(json.dumps(baseline), encoding="utf-8")
            with patch.object(audit_g0, "SOURCE_MANIFEST", replacement):
                with self.assertRaisesRegex(ValueError, "source/header"):
                    audit_g0.verify()

    def test_manual_only_workflow_keeps_separate_runtime_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:", text)
        for trigger in ("  push:", "  pull_request:", "  schedule:"):
            self.assertNotIn(trigger, text)
        self.assertIn("prepare_bullet.py\" --download", text)
        self.assertIn("--target openmw-nif-parse-check", text)
        self.assertIn("openmw-g0a-parser-candidates", text)
        self.assertIn("genuine_parser_runtime", text)
        self.assertIn("if: always()", text)

    def test_build_precision_audit_requires_parser_and_both_bullet_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            build, bullet, files = configured_build(Path(directory))
            self.assertEqual(sum(validate_build.audit(build, bullet).values()), 3)
            write_commands(build, files, missing_precision=(2,))
            with self.assertRaisesRegex(ValueError, "Double-precision macro"):
                validate_build.audit(build, bullet)


class BuildPathContracts(unittest.TestCase):
    def test_canonical_bullet_root_and_compile_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            build, bullet, files = configured_build(Path(directory).resolve())
            write_commands(build, tuple(file.resolve() for file in files))
            self.assertEqual(validate_build.audit(build, bullet.resolve()),
                             {"openmw_nif": 1, "bullet_collision": 1, "bullet_linear_math": 1})

    def test_symlinked_parent_for_bullet_root_and_compile_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            build, bullet, files = configured_build(root)
            alias = root / "alias"
            try:
                alias.symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest("Directory symlinks unavailable: " + str(error))
            write_commands(build, tuple(alias / file.relative_to(root) for file in files))
            self.assertEqual(sum(validate_build.audit(build, alias / "bullet").values()), 3)
            write_commands(build, tuple(file.resolve() for file in files))
            self.assertEqual(sum(validate_build.audit(build, alias / "bullet").values()), 3)

    def test_canonical_compile_paths_with_noncanonical_bullet_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            build, bullet, files = configured_build(root)
            (root / "alias-parent").mkdir()
            unresolved_root = root / "alias-parent" / ".." / "bullet"
            write_commands(build, tuple(file.resolve() for file in files))
            self.assertEqual(sum(validate_build.audit(build, unresolved_root).values()), 3)

    def test_missing_each_required_source_category_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            build, bullet, files = configured_build(Path(directory).resolve())
            for absent in range(3):
                with self.subTest(absent=absent):
                    write_commands(build, files[:absent] + files[absent + 1:])
                    with self.assertRaisesRegex(ValueError, "compile commands missing"):
                        validate_build.audit(build, bullet)

    def test_missing_precision_in_each_category_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            build, bullet, files = configured_build(Path(directory).resolve())
            for absent in range(3):
                with self.subTest(absent=absent):
                    write_commands(build, files, missing_precision=(absent,))
                    with self.assertRaisesRegex(ValueError, "Double-precision macro"):
                        validate_build.audit(build, bullet)

    def test_unrelated_bullet_shaped_paths_cannot_satisfy_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            build, bullet, files = configured_build(root)
            unrelated = root / "unrelated" / "src"
            impostors = (unrelated / "BulletCollision/btShape.cpp",
                         unrelated / "LinearMath/btMath.cpp")
            write_commands(build, (files[0], *impostors))
            with self.assertRaisesRegex(ValueError, "compile commands missing"):
                validate_build.audit(build, bullet)

    def test_malformed_compile_command_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            build, bullet, _ = configured_build(Path(directory).resolve())
            (build / "compile_commands.json").write_text(json.dumps([{"command": "c++ -c unknown.cpp"}]),
                                                          encoding="utf-8")
            with self.assertRaises(KeyError):
                validate_build.audit(build, bullet)


if __name__ == "__main__":
    unittest.main()
