"""Offline contracts for the G0B acquisition and manual host workflow."""

import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import audit_g0
import generate_fixtures
import prepare_bullet
import run_host_cases
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

    def test_cmake_policy_override_preserves_workflow_gates(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(text.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip(),
                         "workflow_dispatch:")
        steps = text.split("      - name: ")[1:]
        gates = [next(step for step in steps if "        id: " + gate + "\n" in step)
                 for gate in ("source_gate", "bullet_gate", "configure_gate", "build_gate", "parser_gate")]
        self.assertEqual([steps.index(step) for step in gates], sorted(steps.index(step) for step in gates))
        for step in gates:
            self.assertIn("set -euo pipefail", step)
            self.assertNotIn("        if:", step)
            self.assertNotIn("||", step)
        self.assertNotIn("continue-on-error:", text)
        configure = gates[2].replace("\\\n", " ")
        command = configure.split("          cmake ", 1)[1].split("2>&1", 1)[0]
        self.assertEqual(command.count("-DCMAKE_POLICY_VERSION_MINIMUM=3.5"), 1)
        for argument in ('-DOPENMW_ESM_OSG_SOURCE="$OPENMW_ESM_OSG_SOURCE"',
                         '-DG0_BULLET_SOURCE="$BULLET_ROOT/source"',
                         '-DCMAKE_CXX_COMPILER="$(xcrun --sdk macosx --find clang++)"',
                         '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'):
            self.assertIn(argument, command)
        for check in ("audit_sources.py", "ci_checks.py", "audit_g0.py", "test_g0_ci.py"):
            self.assertIn(check, gates[0])
        self.assertIn('prepare_bullet.py" --download', gates[1])
        self.assertIn("validate_build.py", gates[2])
        self.assertIn('cmake --build "$BUILD_DIR" --target openmw-nif-parse-check', gates[3])
        self.assertIn("ctest --test-dir", gates[4])
        self.assertIn("-R '^openmw-g0a-parser-candidates$'", gates[4])
        diagnostics = next(step for step in steps if "Preserve diagnostics," in step)
        self.assertIn("        if: always()", diagnostics)
        self.assertIn("PARSER_GATE: ${{ steps.parser_gate.outcome }}", diagnostics)
        self.assertIn("('genuine_parser_runtime', 'PARSER_GATE')", diagnostics)
        self.assertIn("CMakeConfigureLog.yaml", diagnostics)
        self.assertIn('tee "$EVIDENCE/configure.log"', gates[2])
        self.assertIn("        if: always()", steps[-1])
        self.assertIn("uses: actions/upload-artifact@", steps[-1])
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        for contract in (prepare_bullet.URL, prepare_bullet.SHA512,
                         'add_subdirectory("${G0_BULLET_SOURCE}"',
                         'set(USE_DOUBLE_PRECISION ON CACHE BOOL',
                         'set(BUILD_SHARED_LIBS OFF CACHE BOOL',
                         'add_test(NAME openmw-g0a-parser-candidates',
                         '--reader "$<TARGET_FILE:openmw-nif-parse-check>"'):
            self.assertIn(contract, cmake)

    def test_runtime_rejects_an_unavailable_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, r"Genuine C\+\+ parser binary is unavailable"):
                run_host_cases.run(Path(directory) / "missing-parser")


class GeneratedOSGHeaderContracts(unittest.TestCase):
    def setUp(self):
        self.cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

    def test_generated_include_is_derived_from_the_osg_subdirectory_build(self):
        self.assertIn('set(_osg_binary_dir "${CMAKE_CURRENT_BINARY_DIR}/osg")', self.cmake)
        self.assertIn('add_subdirectory("${OPENMW_ESM_OSG_SOURCE}" "${_osg_binary_dir}" EXCLUDE_FROM_ALL)',
                      self.cmake)
        self.assertIn('set(_osg_generated_include "${_osg_binary_dir}/include")', self.cmake)
        self.assertNotIn('set(_osg_generated_include "${OPENMW_ESM_OSG_SOURCE}', self.cmake)
        self.assertNotIn("/Users/runner/", self.cmake)

    def test_parser_and_consumer_receive_generated_headers_before_math_config(self):
        includes = re.findall(r'target_include_directories\(openmw-ios-nif-parser\s+(.*?)\)',
                              self.cmake, re.S)
        generated = [entry for entry in includes if "_osg_generated_include" in entry]
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0].split(),
                         ["BEFORE", "PUBLIC", '"$<BUILD_INTERFACE:${_osg_generated_include}>"'])
        self.assertIn('target_link_libraries(openmw-nif-parse-check PRIVATE openmw-ios-nif-parser)',
                      self.cmake)
        self.assertNotRegex(self.cmake, r'(?im)^\s*include_directories\(')

    def test_all_required_generated_headers_are_guarded_after_osg_configuration(self):
        guard = re.search(r'foreach\(_header IN ITEMS ([^)]+)\)(.*?)endforeach\(\)',
                          self.cmake, re.S)
        self.assertIsNotNone(guard)
        self.assertEqual(guard.group(1).split(),
                         ["OpenThreads/Config", "OpenThreads/Version", "osg/Config", "osg/GL", "osg/Version"])
        self.assertIn('if(NOT EXISTS "${_osg_generated_include}/${_header}"', guard.group(2))
        self.assertIn('OR IS_DIRECTORY "${_osg_generated_include}/${_header}")', guard.group(2))
        self.assertIn('message(FATAL_ERROR "Pinned OSG generated header missing:', guard.group(2))
        self.assertLess(self.cmake.index('add_subdirectory("${OPENMW_ESM_OSG_SOURCE}"'), guard.start())
        self.assertLess(guard.end(), self.cmake.index('add_library(openmw-ios-nif-parser'))
        # Only upstream configuration may produce headers: no local substitutes or copies.
        self.assertNotRegex(self.cmake, r'(?i)\bconfigure_file\s*\(|\bfile\s*\(\s*(?:WRITE|COPY|GENERATE)\b')

    def test_generated_header_fix_preserves_parser_and_dependency_contracts(self):
        self.assertIn('set(_nif_units base controller data effect extra niffile nifstream node particle physics property texture)',
                      self.cmake)
        for contract in (prepare_bullet.URL, prepare_bullet.SHA512,
                         'file(READ "${_bullet_provenance}" _bullet_json)',
                         'OR NOT _bullet_source STREQUAL _bullet_real)',
                         'set(USE_DOUBLE_PRECISION ON CACHE BOOL',
                         'target_compile_definitions(openmw-ios-nif-parser PUBLIC BT_USE_DOUBLE_PRECISION)',
                         'target_compile_features(openmw-ios-nif-parser PUBLIC cxx_std_20)',
                         'target_link_libraries(openmw-ios-nif-parser PUBLIC openmw-ios-esm-vfs ${_bullet_libraries}',
                         '    osg OpenThreads)',
                         'add_test(NAME openmw-g0a-parser-candidates'):
            self.assertIn(contract, self.cmake)
        audit_g0.verify()


class FixtureLayoutContracts(unittest.TestCase):
    """Independent byte/offset contracts; these do not prove parser acceptance."""

    def setUp(self):
        self.candidate = generate_fixtures.triangle_candidate()

    def test_header_record_boundaries_and_object_net_fields(self):
        data = self.candidate
        self.assertEqual(len(data), 392)
        self.assertEqual(data[:40], b"NetImmerse File Format, Version 4.0.0.2\n")
        self.assertEqual(struct.unpack_from("<II", data, 40), (0x04000002, 3))
        for start, name in ((48, b"NiNode"), (162, b"NiTriShape"), (280, b"NiTriShapeData")):
            with self.subTest(record=name):
                self.assertEqual(struct.unpack_from("<I", data, start), (len(name),))
                self.assertEqual(data[start + 4:start + 4 + len(name)], name)
        for start, name in ((58, b"G0Root"), (176, b"G0Triangle")):
            with self.subTest(object=name):
                self.assertEqual(struct.unpack_from("<I", data, start), (len(name),))
                self.assertEqual(data[start + 4:start + 4 + len(name)], name)
                self.assertEqual(struct.unpack_from("<ii", data, start + 4 + len(name)), (-1, -1))

    def test_av_object_matrix_layout_and_transform_boundaries(self):
        data = self.candidate
        identity = (1., 0., 0., 0., 1., 0., 0., 0., 1.)
        self.assertEqual(len(generate_fixtures.av_object("G0Root")), 92)
        self.assertEqual(len(generate_fixtures.av_object("G0Triangle")), 96)
        for flags, translation, rotation, scale, velocity, properties in (
                (76, 78, 90, 126, 130, 142), (198, 200, 212, 248, 252, 264)):
            with self.subTest(rotation=rotation):
                self.assertEqual(struct.unpack_from("<H", data, flags), (0,))
                self.assertEqual(struct.unpack_from("<3f", data, translation), (0., 0., 0.))
                self.assertEqual(struct.unpack_from("<9f", data, rotation), identity)
                self.assertEqual(scale - rotation, 36)
                self.assertEqual(struct.unpack_from("<f", data, scale), (1.,))
                self.assertEqual(struct.unpack_from("<3f", data, velocity), (0., 0., 0.))
                self.assertEqual(struct.unpack_from("<I", data, properties), (0,))

    def test_all_six_old_version_booleans_are_int32(self):
        self.assertEqual(generate_fixtures.mw_bool(False), b"\0\0\0\0")
        self.assertEqual(generate_fixtures.mw_bool(True), b"\1\0\0\0")
        # Bounds on node/shape, vertices, normals, colors, UV presence.
        for offset, value in ((146, 0), (268, 0), (300, 1), (340, 0), (360, 0), (366, 0)):
            with self.subTest(offset=offset):
                self.assertEqual(self.candidate[offset:offset + 4], struct.pack("<i", value))
        # Flags and counts remain uint16; they are not Boolean fields.
        self.assertEqual(struct.unpack_from("<H", self.candidate, 364), (0,))

    def test_declared_references_and_root_list(self):
        self.assertEqual(struct.unpack_from("<IiI", self.candidate, 150), (1, 1, 0))
        self.assertEqual(struct.unpack_from("<ii", self.candidate, 272), (2, -1))
        self.assertEqual(struct.unpack_from("<Ii", self.candidate, 384), (1, 0))
        self.assertEqual(len(self.candidate[384:]), 8)

    def test_geometry_payload_sizes_and_indices(self):
        data = self.candidate
        self.assertEqual(struct.unpack_from("<H", data, 298), (3,))
        self.assertEqual(len(data[304:340]), 3 * 3 * 4)
        self.assertEqual(struct.unpack_from("<9f", data, 304), (0., 0., 0., 1., 0., 0., 0., 1., 0.))
        self.assertEqual(struct.unpack_from("<4f", data, 344), (0., 0., 0., 1.))
        self.assertEqual(struct.unpack_from("<HI", data, 370), (1, 3))
        self.assertEqual(struct.unpack_from("<3H", data, 376), (0, 1, 2))
        self.assertEqual(len(data[376:382]), 3 * 2)
        self.assertEqual(struct.unpack_from("<H", data, 382), (0,))

    def test_bsa_resources_match_each_nif_exactly(self):
        files = generate_fixtures.fixture_bytes()
        for stem in ("triangle-candidate", "invalid-header", "truncated", "invalid-reference"):
            with self.subTest(stem=stem):
                archive, nif = files[stem + ".bsa"], files[stem + ".nif"]
                self.assertEqual(struct.unpack_from("<III", archive), (0x100, 28, 1))
                self.assertEqual(struct.unpack_from("<III", archive, 12), (len(nif), 0, 0))
                self.assertEqual(archive[24:40], b"Meshes\\Test.NIF\0")
                self.assertEqual(archive[48:], nif)
        missing = files["missing-resource.bsa"]
        self.assertEqual(missing[24:38], b"Docs\\Only.txt\0")
        self.assertNotIn(b"Meshes\\Test.NIF", missing)

    def test_negative_fixtures_remain_deliberately_invalid(self):
        files = generate_fixtures.fixture_bytes()
        self.assertEqual(files["invalid-header.nif"], b"X" + self.candidate[1:])
        self.assertEqual(files["truncated.nif"], self.candidate[:-17])
        with self.assertRaises(struct.error):
            struct.unpack_from("<I", files["truncated.nif"], 372)
        invalid = bytearray(self.candidate)
        struct.pack_into("<i", invalid, 272, 99)  # Outside the three declared records.
        self.assertEqual(files["invalid-reference.nif"], bytes(invalid))
        self.assertNotEqual(files["invalid-header.nif"], files["triangle-candidate.nif"])

    def test_manifest_and_regeneration_are_deterministic_and_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data"
            with patch.object(generate_fixtures, "DATA", output), patch("sys.stdout", new_callable=io.StringIO):
                generate_fixtures.generate()
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                generate_fixtures.generate()
                self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)
                manifest = json.loads(before["fixture-manifest.json"])
                expected = generate_fixtures.fixture_bytes()
                self.assertEqual(set(before), set(expected) | {"fixture-manifest.json"})
                self.assertEqual(manifest["status"], "candidate-unvalidated-by-openmw-parser")
                self.assertEqual(manifest["files"], {
                    name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                    for name, data in expected.items()})
                self.assertEqual(before["fixture-manifest.json"].decode("utf-8"),
                                 (ROOT / "data/fixture-manifest.json").read_text(encoding="utf-8"))
                (output / "unexpected.json").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Unexpected file"):
                    generate_fixtures.generate()


class RuntimeFixtureContracts(unittest.TestCase):
    """Harness regressions with mocked processes, never genuine parser evidence."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.data = root / "data"
        shutil.copytree(ROOT / "data", self.data)
        self.reader = root / "mock-parser"
        self.reader.touch()
        data_patch = patch.object(run_host_cases, "DATA", self.data)
        data_patch.start()
        self.addCleanup(data_patch.stop)

    def invoke(self, process):
        with patch.object(run_host_cases.subprocess, "run", side_effect=process) as mocked, \
                patch("sys.stdout", new_callable=io.StringIO):
            run_host_cases.run(self.reader)
        return mocked

    @staticmethod
    def parser_result(command, **kwargs):
        mode = command[1]
        if mode == "positive" and Path(command[-1]).name == "invalid-header.nif":
            return subprocess.CompletedProcess(command, 1, "", "FAIL: VFS NIF bytes differ")
        marker = {"positive": "PASS genuine OpenMW NIF parse",
                  "missing": "PASS missing resource rejected"}.get(
                      mode, "PASS genuine parser rejected " + mode)
        return subprocess.CompletedProcess(command, 0, marker, "")

    def assert_rejected_before_parser(self, message):
        with patch.object(run_host_cases.subprocess, "run") as mocked:
            with self.assertRaisesRegex(RuntimeError, message):
                run_host_cases.run(self.reader)
            mocked.assert_not_called()

    def test_reviewed_inventory_reaches_all_six_parser_invocations(self):
        before = run_host_cases.snapshot()
        self.assertEqual(len(before), 12)
        self.assertIn("nif-source-sha256.json", before)
        mocked = self.invoke(self.parser_result)
        commands = [call.args[0] for call in mocked.call_args_list]
        self.assertEqual([command[1] for command in commands],
                         ["positive", "invalid", "truncated", "invalid-reference", "missing", "positive"])
        self.assertEqual(Path(commands[-1][-1]).name, "invalid-header.nif")
        self.assertEqual(run_host_cases.snapshot(), before)

    def test_missing_source_manifest_is_rejected(self):
        (self.data / "nif-source-sha256.json").unlink()
        self.assert_rejected_before_parser("Fixture inventory mismatch")

    def test_missing_fixture_is_rejected(self):
        (self.data / "triangle-candidate.nif").unlink()
        self.assert_rejected_before_parser("Fixture inventory mismatch")

    def test_unexpected_files_including_other_json_are_rejected(self):
        for name in ("unexpected.nif", "unexpected.json"):
            with self.subTest(name=name):
                extra = self.data / name
                extra.write_bytes(b"unexpected")
                self.assert_rejected_before_parser("Fixture inventory mismatch")
                extra.unlink()

    def test_directory_in_place_of_source_manifest_is_rejected(self):
        path = self.data / "nif-source-sha256.json"
        path.unlink()
        path.mkdir()
        self.assert_rejected_before_parser("Unsafe fixture entry")

    def test_fixture_hash_and_size_are_still_required(self):
        path = self.data / "triangle-candidate.nif"
        original = path.read_bytes()
        for replacement in (bytes([original[0] ^ 1]) + original[1:], original[:-1]):
            with self.subTest(size=len(replacement)):
                path.write_bytes(replacement)
                self.assert_rejected_before_parser("Fixture SHA-256/size mismatch")

    def test_source_manifest_remains_in_input_mutation_checks(self):
        def mutate(command, **kwargs):
            path = self.data / "nif-source-sha256.json"
            path.write_bytes(path.read_bytes() + b"\n")
            return self.parser_result(command, **kwargs)

        with self.assertRaisesRegex(RuntimeError, "parser changed input files"):
            self.invoke(mutate)

    def test_each_parser_case_requires_zero_exit_and_expected_marker(self):
        for mode in ("positive", "invalid", "truncated", "invalid-reference", "missing"):
            for failure in ("exit", "marker"):
                with self.subTest(mode=mode, failure=failure):
                    def fail(command, **kwargs):
                        result = self.parser_result(command, **kwargs)
                        if command[1] == mode:
                            if failure == "exit":
                                result.returncode = 1
                            else:
                                result.stdout = "VFS lookup succeeded"
                        return result

                    with self.assertRaisesRegex(RuntimeError, "Genuine parser case failed: " + mode):
                        self.invoke(fail)

    def test_wrong_resource_bytes_require_failure_and_diagnostic(self):
        for failure in ("exit", "diagnostic"):
            with self.subTest(failure=failure):
                def fail(command, **kwargs):
                    result = self.parser_result(command, **kwargs)
                    if command[1] == "positive" and Path(command[-1]).name == "invalid-header.nif":
                        if failure == "exit":
                            result.returncode = 0
                        else:
                            result.stderr = "FAIL: unrelated error"
                    return result

                with self.assertRaisesRegex(RuntimeError, "Incorrect resource hash/bytes were not rejected"):
                    self.invoke(fail)


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
