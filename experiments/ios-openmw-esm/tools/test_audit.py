"""Real-source audit regressions, not a replacement ESM decoder or OSG implementation."""
import contextlib
import copy
import io
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import audit_sources as auditor
import fixtures

REPO = auditor.REPO
OSG_SOURCE = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
CMAKE = (auditor.ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
CHECKER = (auditor.ROOT / 'tests/esm_check.cpp').read_text(encoding='utf-8')


class ESMAuditTests(unittest.TestCase):
    def test_exact_real_source_closure_and_pin_without_native_success_claim(self):
        result = auditor.audit()
        self.assertTrue(result['project_source_audit_valid'])
        self.assertEqual((result['candidate_translation_units'], result['project_headers'], result['source_hashes_verified']), (15, 38, 53))
        self.assertEqual(result['external_include_roots'], ['osg/Vec3f'])
        self.assertTrue(result['osg_header_closure_audited'])
        self.assertFalse(result['osg_checkout_verified'])
        self.assertFalse(result['link_closure_verified'])
        self.assertFalse(result['native_ready'])

    def test_wrong_hash_omitted_header_and_changed_pin_fail_closed(self):
        original = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        for change in ('hash', 'header', 'pin', 'duplicate', 'external', 'false-proof'):
            manifest = copy.deepcopy(original)
            if change == 'hash':
                manifest['project_sha256_lf']['components/esm3/esmreader.cpp'] = '0' * 64
            elif change == 'header':
                manifest['headers'].pop()
            elif change == 'pin':
                manifest['osg_revision'] = '0' * 40
            elif change == 'duplicate':
                manifest['sources'][0] = manifest['sources'][1]
            elif change == 'external':
                manifest['standard_includes'].append('boost/filesystem.hpp')
            else:
                manifest['link_closure_verified'] = True
            with self.subTest(change=change), self.assertRaises(auditor.AuditError):
                auditor.audit(manifest)

    def test_missing_and_outside_source_paths_fail_without_writing_files(self):
        for name in ('components/../not-a-file.cpp', '../outside.cpp', 'C:/outside.cpp',
                     'components/../../outside.cpp', 'components\\esm3\\esmreader.cpp'):
            with self.subTest(path=name), self.assertRaises(auditor.AuditError):
                auditor.project_path(name)

    def test_osg_dependency_is_the_real_position_header_route(self):
        for path, anchor in (
            ('components/esm3/esmreader.cpp', '#include <components/esm3/loadcell.hpp>'),
            ('components/esm3/loadcell.hpp', '#include "cellref.hpp"'),
            ('components/esm3/cellref.hpp', '#include <components/esm/position.hpp>'),
            ('components/esm/position.hpp', '#include <osg/Vec3f>')):
            self.assertIn(anchor, (REPO / path).read_text(encoding='utf-8'))
        self.assertIn('configure_file("${OSG_MATH_CONFIG_TEMPLATE}"', CMAKE)

    def test_actual_reader_stream_and_header_interfaces(self):
        reader = (REPO / 'components/esm3/esmreader.cpp').read_text(encoding='utf-8')
        header = (REPO / 'components/esm3/esmreader.hpp').read_text(encoding='utf-8')
        tes3 = (REPO / 'components/esm3/loadtes3.cpp').read_text(encoding='utf-8')
        self.assertIn('void ESMReader::open(std::unique_ptr<std::istream>&& stream', reader)
        self.assertIn('if (getRecName() != "TES3")', reader)
        self.assertIn('mHeader.load(*this)', reader)
        for anchor in ('getRecName()', 'getSubNameIs(NAME name)', 'getSubHeader()',
                       'hasMoreRecs()', 'hasMoreSubs()', 'getHNRefId(NAME name)', 'setEncoder('):
            self.assertIn(anchor, header)
        self.assertIn('mFormatVersion = DefaultFormatVersion;', tes3)
        self.assertIn('if (esm.isNextSub("HEDR"))', tes3)  # Optional in the actual loader.

    def test_short_read_policy_and_size_checks_are_documented_source_facts(self):
        header = (REPO / 'components/esm3/esmreader.hpp').read_text(encoding='utf-8')
        body = re.search(r'void getExact\(.*?\n        \}', header, re.S)[0]
        self.assertIn('mEsm->read(', body)
        self.assertNotIn('gcount', body)
        self.assertNotIn('fail(', body)
        opener = (REPO / 'components/files/openfile.cpp').read_text(encoding='utf-8')
        self.assertIn('stream->exceptions(std::ios::badbit)', opener)
        self.assertNotIn('std::ios::failbit', opener)
        reader = (REPO / 'components/esm3/esmreader.cpp').read_text(encoding='utf-8')
        self.assertIn('if (mCtx.leftFile < mCtx.leftRec)', reader)
        self.assertIn('mCtx.leftRec -= mCtx.leftSub;', reader)
        self.assertIn('if (mCtx.leftRec < 0)', reader)
        self.assertIn('if (mCtx.leftSub != size)', header)
        self.assertIn('throw std::runtime_error(ss.str())', reader)

    def test_complete_dependency_gate_fails_and_plain_source_audit_succeeds(self):
        for arguments, expected in ((['audit_sources'], 0), (['audit_sources', '--require-complete'], 1)):
            with self.subTest(arguments=arguments), patch('sys.argv', arguments), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(auditor.main(), expected)
                self.assertIn('"native_ready": false', output.getvalue())
                if expected:
                    self.assertIn('BLOCKED:', output.getvalue())

    def test_real_osg_checkout_headers_template_and_revision_are_verified(self):
        if not OSG_SOURCE.is_dir():
            self.skipTest('Separate genuine pinned OSG checkout not supplied')
        result = auditor.audit(osg_source=OSG_SOURCE)
        self.assertTrue(result['osg_checkout_verified'])
        self.assertFalse(result['native_ready'])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'osg-math.cmake'
            with patch('sys.argv', ['audit_sources', '--osg-source', str(OSG_SOURCE), '--require-complete', '--resolve', str(output)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(auditor.main(), 0)
            self.assertIn('OSG_MATH_CONFIG_TEMPLATE', output.read_text())
            self.assertIn(OSG_SOURCE.resolve().as_posix(), output.read_text())
        math = (OSG_SOURCE / 'include/osg/Math').read_text(encoding='utf-8')
        self.assertIn('extern OSG_EXPORT double asciiToDouble', math)
        self.assertNotIn('asciiToDouble(', CHECKER)

    def test_osg_wrong_revision_or_source_hash_fails_without_modifying_checkout(self):
        if not OSG_SOURCE.is_dir():
            self.skipTest('Separate genuine pinned OSG checkout not supplied')
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        manifest['osg_sha256_lf']['include/osg/Vec3f'] = '0' * 64
        with self.assertRaisesRegex(auditor.AuditError, 'OSG source integrity'):
            auditor.audit(manifest, OSG_SOURCE)
        with patch.object(auditor.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '0' * 40, '')):
            with self.assertRaisesRegex(auditor.AuditError, 'checkout revision mismatch'):
                auditor.audit(osg_source=OSG_SOURCE)
        with patch.object(auditor.subprocess, 'run', side_effect=FileNotFoundError('git missing')):
            with self.assertRaisesRegex(auditor.AuditError, 'Cannot verify'):
                auditor.audit(osg_source=OSG_SOURCE)
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        manifest['osg_config_defines'].pop('OSG_NOTIFY_DISABLED')
        with self.assertRaisesRegex(auditor.AuditError, 'Config template switches changed'):
            auditor.audit(manifest, OSG_SOURCE)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(auditor.AuditError):
            auditor.audit(osg_source=Path(directory) / 'missing')

    def test_target_has_no_renderer_or_dependency_fetch_and_generates_genuine_config(self):
        for required in ('--require-complete', 'OPENMW_ESM_OSG_SOURCE', 'cxx_std_20', 'Threads::Threads',
                         'add_library(openmw-ios-esm-reader STATIC ${OPENMW_ESM_SOURCES})',
                         'string(JSON _relative GET "${_manifest}" sources',
                         'configure_file("${OSG_MATH_CONFIG_TEMPLATE}"',
                         'NAME openmw-esm-runtime', '--reader "$<TARGET_FILE:openmw-esm-check>"',
                         'CMAKE_SYSTEM_NAME STREQUAL "iOS"', 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"',
                         'CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0"', '_sdk MATCHES "iphoneos"'):
            self.assertIn(required, CMAKE)
        for forbidden in ('FetchContent', 'ExternalProject', 'add_subdirectory(', 'find_package(OpenSceneGraph',
                          'libosg', 'ANGLE_ROOT', 'OpenGL', '-Wno-', '-ffunction-sections', 'FORCE'):
            self.assertNotIn(forbidden, CMAKE)

    def test_original_synthetic_layout_values_and_bounded_malformed_inputs(self):
        data = fixtures.synthetic_esm()
        self.assertEqual(len(data), 370)
        self.assertEqual(hashlib.sha256(data).hexdigest(), '20ea83089dfb7a6b9ab83533fc33db0eccb46cb6dcef4ed8e1cb4bb8e06b0eb5')
        self.assertEqual(data[:4], b'TES3')
        self.assertEqual(struct.unpack_from('<III', data, 4), (308, 0, 0))
        self.assertEqual(data[16:20], b'HEDR')
        self.assertEqual(struct.unpack_from('<III', data, 20), (300, 0x3FA66666, 1))
        self.assertEqual(data[32:64].rstrip(b'\0').decode('cp1252'), 'Original Caf\u00e9 fixture')
        self.assertEqual(struct.unpack_from('<i', data, 320)[0], 1)
        self.assertEqual(data[324:328], b'GMST')
        self.assertEqual(struct.unpack_from('<III', data, 328), (30, 0, 0))
        self.assertEqual(data[340:344], b'NAME')
        self.assertEqual(data[348:358], b'iIOSProbe\0')
        self.assertEqual(data[358:362], b'INTV')
        self.assertEqual(struct.unpack_from('<Ii', data, 362), (4, -1234567))
        self.assertEqual(struct.unpack_from('<i', fixtures.synthetic_esm(0), 28)[0], 0)
        inputs = fixtures.inputs()
        self.assertEqual(len(inputs), 8)
        self.assertTrue(all(len(blob) <= 370 for blob in inputs.values()))
        self.assertEqual((len(inputs['short-read.esm']), struct.unpack_from('<I', inputs['short-read.esm'], 328)[0]), (369, 29))
        self.assertEqual(struct.unpack_from('<I', inputs['wrong-value-size.esm'], 362)[0], 3)

    def test_genuine_reader_math_link_probe_and_separate_short_read_policy(self):
        for value in ('ESM::ESMReader reader;', 'ToUTF8::Utf8Encoder encoder', 'reader.setEncoder(&encoder)',
                      '#include <fstream>',
                      'reader.open(std::move(stream), path)', 'reader.open(path)', 'reader.getHNRefId("NAME")',
                      'reader.getHNT(value, "INTV")', 'reader.peekNextSub("NAME")', 'reader.skipRecord()',
                      'std::ios::badbit | std::ios::failbit', 'catch (const std::ios_base::failure& error)',
                      'starts_with("ESM Error: ")', 'first.asVec3()', 'first < later'):
            self.assertIn(value, CHECKER)
        for forbidden in ('ESM::ESMWriter', 'writeHNT(', 'std::ofstream', 'class Vec3f', 'Engine::go'):
            self.assertNotIn(forbidden, CHECKER)
        self.assertLess(CHECKER.index('ToUTF8::Utf8Encoder encoder'), CHECKER.index('ESM::ESMReader reader;'))

    def test_driver_requires_ten_cases_and_unchanged_input_tree(self):
        self.assertEqual(len(fixtures.CASES), 10)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(command, **kwargs):
                if command[1] in ('read', 'strict-read'): marker = 'OpenMW ESM fixture passed;'
                elif command[1] == 'strict-reject': marker = 'REJECTED short read by explicit caller stream policy'
                elif command[1] == 'reject-missing': marker = 'REJECTED missing file by genuine OpenMW file helper'
                else: marker = 'REJECTED by genuine ESM reader check'
                return subprocess.CompletedProcess(command, 0, marker, '')
            with patch.object(fixtures.subprocess, 'run', side_effect=run) as mocked, contextlib.redirect_stdout(io.StringIO()):
                fixtures.run_cases(root / 'reader', root / 'inputs')
            self.assertEqual(mocked.call_count, 10)
            self.assertFalse((root / 'inputs/must-not-be-created.esm').exists())
            for name, value in fixtures.inputs().items():
                self.assertEqual((root / 'inputs' / name).read_bytes(), value)

    def test_driver_rejects_process_failure_missing_marker_mutation_and_created_file(self):
        for failure in ('status', 'marker', 'mutation', 'created'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def run(command, **kwargs):
                    if failure == 'mutation': (root / 'inputs/valid.esm').write_bytes(b'changed')
                    if failure == 'created': (root / 'inputs/must-not-be-created.esm').write_bytes(b'created')
                    return subprocess.CompletedProcess(command, 1 if failure == 'status' else 0,
                        '' if failure == 'marker' else 'OpenMW ESM fixture passed;', '')
                with patch.object(fixtures.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    fixtures.run_cases(root / 'reader', root / 'inputs')

    def test_actual_host_compile_link_and_runtime_when_existing_tools_available(self):
        if os.name == 'nt':
            self.skipTest('Native C++ fixture unexecuted: existing macOS/Linux C++20 and CMake toolchain required')
        compiler, cmake, ctest = shutil.which('clang++') or shutil.which('g++'), shutil.which('cmake'), shutil.which('ctest')
        if not all((compiler, cmake, ctest)) or not OSG_SOURCE.is_dir():
            self.skipTest('Real pinned OSG checkout and existing host toolchain required; no downloads')
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([cmake, '-S', str(auditor.ROOT), '-B', directory, '-DOPENMW_IOS_ESM_HOST_TESTS=ON',
                            '-DOPENMW_ESM_OSG_SOURCE=' + str(OSG_SOURCE), '-DCMAKE_BUILD_TYPE=Release',
                            '-DCMAKE_CXX_COMPILER=' + compiler], check=True)
            subprocess.run([cmake, '--build', directory, '--config', 'Release', '--target', 'openmw-esm-check', '--parallel', '3'], check=True)
            subprocess.run([ctest, '--test-dir', directory, '-C', 'Release', '--verbose', '--output-on-failure',
                            '--no-tests=error', '-R', '^openmw-esm-runtime$'], check=True)


if __name__ == '__main__':
    unittest.main()
