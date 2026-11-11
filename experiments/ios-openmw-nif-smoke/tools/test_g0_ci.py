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
            root = Path(directory)
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
            commands = [{"file": str(file), "command": "c++ -DBT_USE_DOUBLE_PRECISION -c " + str(file)}
                        for file in files]
            (build / "compile_commands.json").write_text(json.dumps(commands), encoding="utf-8")
            self.assertEqual(sum(validate_build.audit(build, bullet).values()), 3)
            commands[-1]["command"] = "c++ -c " + str(files[-1])
            (build / "compile_commands.json").write_text(json.dumps(commands), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Double-precision macro"):
                validate_build.audit(build, bullet)


if __name__ == "__main__":
    unittest.main()
