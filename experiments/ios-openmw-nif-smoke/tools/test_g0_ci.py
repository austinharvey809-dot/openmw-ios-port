"""Offline contracts for the G0B acquisition and manual host workflow."""

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


class BulletAcquisitionContracts(unittest.TestCase):
    def test_exact_upstream_pin_is_still_in_openmw(self):
        prepare_bullet.verify_upstream_pin()
        self.assertEqual(prepare_bullet.URL,
                         "https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz")
        self.assertEqual(len(prepare_bullet.SHA512), 128)

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
