"""Offline provenance/fixture contracts. Python byte checks are not C++ runtime proof."""
import contextlib
import copy
import hashlib
import io
import json
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

ROOT = auditor.ROOT
REPO = auditor.REPO
OSG = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
CMAKE = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
CHECKER = (ROOT / 'tests/esm_vfs_check.cpp').read_text(encoding='utf-8')


def records(data):
    """Inspect generator framing only; never used by the real C++ fixture."""
    result, offset = [], 0
    while offset < len(data):
        tag, size, unknown, flags = struct.unpack_from('<4sIII', data, offset)
        if unknown or flags or offset + 16 + size > len(data):
            raise ValueError('Invalid generated record framing')
        body, subs, position = data[offset + 16:offset + 16 + size], [], 0
        while position < len(body):
            name, length = struct.unpack_from('<4sI', body, position)
            payload = body[position + 8:position + 8 + length]
            if len(payload) != length:
                raise ValueError('Invalid generated subrecord framing')
            subs.append((name, payload))
            position += 8 + length
        result.append((tag, size, subs))
        offset += 16 + size
    return result


def archive_entries(data):
    """Independent byte-layout check for synthetic original BSA inputs only."""
    magic, directory_size, count = struct.unpack_from('<III', data)
    if magic != 0x100 or directory_size < count * 12:
        raise ValueError('Invalid generated BSA header')
    names_start = 12 + count * 12
    data_start = 12 + directory_size + count * 8
    result = {}
    for i in range(count):
        size, offset = struct.unpack_from('<II', data, 12 + i * 8)
        name_offset, = struct.unpack_from('<I', data, 12 + count * 8 + i * 4)
        end = data.index(b'\0', names_start + name_offset, 12 + directory_size)
        name = data[names_start + name_offset:end]
        self_hash = struct.unpack_from('<II', data, 12 + directory_size + i * 8)
        if self_hash != fixtures.bsa.name_hash(name) or data_start + offset + size > len(data):
            raise ValueError('Invalid generated BSA entry')
        result[name] = data[data_start + offset:data_start + offset + size]
    return result


class ProvenanceTests(unittest.TestCase):
    def test_exact_closure_and_no_native_claim(self):
        result = auditor.audit()
        self.assertEqual((result['translation_units'], result['headers'], result['source_hashes_verified']), (21, 58, 79))
        self.assertEqual(result['genuine_engine_translation_units'], 20)
        self.assertFalse(result['native_compilation_performed'])
        self.assertFalse(result['osg_checkout_verified'])
        self.assertEqual(result['osg_revision'], '9b384d5439977784e5cd250ff8ff7966928ddd27')
        self.assertEqual(set(result['external_includes']) - auditor.esm_audit.STANDARD - {'osg/Vec3f'},
                         {'cerrno', 'cstdlib', 'errno.h', 'fcntl.h', 'format', 'streambuf', 'string.h', 'sys/types.h', 'unistd.h'})

    def test_genuine_osg_revision_and_seven_hashes(self):
        if not OSG.is_dir():
            self.skipTest('Supply existing separate pinned OSG checkout; no download')
        self.assertTrue(auditor.audit(osg_source=OSG)['osg_checkout_verified'])

    def test_wrong_hash_pin_closure_and_reused_build_fail_closed(self):
        original = json.loads(auditor.MANIFEST.read_text())
        for change in ('hash', 'header', 'pin', 'overlap', 'extra-source', 'external', 'reused', 'schema'):
            manifest = copy.deepcopy(original)
            if change == 'hash':
                manifest['project_sha256_lf']['components/esm3/loadstat.cpp'] = '0' * 64
            elif change == 'header':
                manifest['headers'].pop()
            elif change == 'pin':
                manifest['osg_revision'] = '0' * 40
            elif change == 'overlap':
                manifest['additional_sources'][0] = manifest['inherited_sources'][0]
            elif change == 'extra-source':
                manifest['additional_sources'].append('components/esm3/loadcell.cpp')
            elif change == 'external':
                manifest['external_includes'].append('SDL.h')
            elif change == 'reused':
                manifest['reused_build_sha256_lf']['experiments/ios-openmw-esm/CMakeLists.txt'] = '0' * 64
            else:
                manifest['schema_version'] = 99
            with self.subTest(change=change), self.assertRaises(auditor.AuditError):
                auditor.audit(manifest)

    def test_missing_unsafe_paths_rejected(self):
        for path in ('../outside.cpp', 'components/../../outside.cpp', 'components\\esm3\\loadstat.cpp',
                     'components/nonexistent.cpp', 'experiments/ios-openmw-esm/tests/esm_check.cpp'):
            with self.subTest(path=path), self.assertRaises(auditor.AuditError):
                auditor.safe_path(path)

    def test_cli_requires_complete_local_osg_when_requested(self):
        with patch('sys.argv', ['audit_sources', '--require-complete']), contextlib.redirect_stdout(io.StringIO()) as log:
            self.assertEqual(auditor.main(), 1)
        self.assertIn('Pinned OSG checkout required', log.getvalue())

    def test_high_level_loader_is_real_and_lightweight(self):
        source = (REPO / 'components/esm3/loadstat.cpp').read_text()
        self.assertIn('void Static::load(ESMReader& esm, bool& isDeleted)', source)
        for anchor in ('mId = esm.getRefId()', 'mModel = esm.getHString()', 'esm.fail("Unknown subrecord")',
                       'esm.fail("Missing NAME subrecord")', 'isDeleted = true'):
            self.assertIn(anchor, source)
        self.assertNotIn('Missing MODL', source)
        self.assertIn('object.load(reader, deleted)', CHECKER)
        self.assertIn('object.mModel.getNormalized()', CHECKER)
        self.assertIn('VFS::Path::join(VFS::Path::NormalizedView("meshes")', CHECKER)
        helper = (REPO / 'components/misc/resourcehelpers.cpp').read_text()
        self.assertIn('static constexpr VFS::Path::NormalizedView prefix("meshes");', helper)
        self.assertIn('return prefix / resPath;', helper)

    def test_cmake_owns_each_translation_unit_once_and_reuses_d(self):
        manifest = json.loads(auditor.MANIFEST.read_text())
        sources = manifest['inherited_sources'] + manifest['additional_sources']
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(len(manifest['additional_sources']), 6)
        self.assertIn('target_link_libraries(openmw-ios-esm-vfs PUBLIC openmw-ios-esm-reader)', CMAKE)
        self.assertIn('add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm"', CMAKE)
        self.assertIn('OPENMW_IOS_ESM_HOST_TESTS "${OPENMW_IOS_ESM_VFS_HOST_TESTS}"', CMAKE)
        self.assertIn('--require-complete', CMAKE)
        self.assertIn('cxx_std_20', CMAKE)
        self.assertIn('NAME openmw-esm-vfs-runtime', CMAKE)
        commands = re.sub(r'#[^\n]*', '', CMAKE)
        for bad in ('openmw-ios-bsa-reader', 'openmw-ios-bsa-vfs', 'openmw-ios-data-core',
                    'FetchContent', 'ExternalProject', 'target_compile_definitions'):
            self.assertNotIn(bad, commands)
        self.assertNotIn('workflow_dispatch', CMAKE)  # The target remains independent of CI orchestration.

    def test_read_only_registration_borrowed_encoders_and_lifetimes(self):
        self.assertIn('addExistingMorrowindBSA', CHECKER)
        self.assertLess(CHECKER.index('archiveEncoder(ToUTF8::WINDOWS_1252)'), CHECKER.index('resolve(object,'))
        self.assertIn('manager.reset()', CHECKER)
        self.assertIn('checkBytes(*retained, expected)', CHECKER)
        self.assertIn('checkBytes(*afterDestruction, expected)', CHECKER)
        self.assertIn('expected.size() + 8', CHECKER)
        self.assertIn('stream.seekg(-1, std::ios::end)', CHECKER)
        self.assertIn('stream.seekg(static_cast<std::streamoff>(expected.size() + 1))', CHECKER)
        for forbidden in ('std::ofstream', 'std::fstream', '.save(', '.addFile(', 'Engine::go', 'makeBsaArchive('):
            self.assertNotIn(forbidden, CHECKER)


class FixtureTests(unittest.TestCase):
    def test_determinism_and_exact_payload_bytes(self):
        self.assertEqual(fixtures.inputs(), fixtures.inputs())
        self.assertEqual(len(fixtures.inputs()), 14)
        self.assertEqual(fixtures.BASE_PAYLOAD, b'\0OMW-E\xff\n\0synthetic-model')
        self.assertEqual((len(fixtures.BASE_PAYLOAD), len(fixtures.OVERLAY_PAYLOAD)), (24, 12))
        self.assertIn('basePayload("\\x00OMW-E\\xff\\n\\x00synthetic-model", 24)', CHECKER)
        self.assertIn('overlayPayload("Override-E\\x00\\xfe", 12)', CHECKER)

    def test_tes3_stat_id_model_and_esp_framing(self):
        for name, kind in (('valid.esm', 1), ('valid.esp', 0)):
            data = fixtures.inputs()[name]
            parsed = records(data)
            self.assertEqual([r[0] for r in parsed], [b'TES3', b'STAT'])
            self.assertEqual(parsed[0][1], 308)
            hedr = dict(parsed[0][2])[b'HEDR']
            self.assertEqual(len(hedr), 300)
            self.assertEqual(struct.unpack_from('<Ii', hedr), (0x3FA66666, kind))
            self.assertEqual(struct.unpack_from('<i', hedr, 296)[0], 1)
            self.assertEqual(parsed[1][2], [(b'NAME', b'eIOSStatic\0'), (b'MODL', b'TeSt.NIF\0')])
        self.assertEqual(dict(records(fixtures.inputs()['normalized.esm'])[1][2])[b'MODL'], b'\\\\TeSt.NIF\0')

    def test_original_bsa_layout_duplicate_names_and_non_nif_payload(self):
        values = fixtures.inputs()
        base = archive_entries(values['base.bsa'])
        self.assertEqual(base[fixtures.RESOURCE], fixtures.BASE_PAYLOAD)
        self.assertEqual(base[b'Docs\\Adjacent.bin'], b'Adjacent entry sentinel.')
        overlay = archive_entries(values['overlay.bsa'])
        self.assertEqual(overlay[b'mEsHeS//TEST.NIF'], fixtures.OVERLAY_PAYLOAD)
        self.assertNotIn(fixtures.RESOURCE, archive_entries(values['missing-resource.bsa']))
        with self.assertRaises(ValueError):
            archive_entries(values['unsupported.bsa'])
        self.assertFalse(fixtures.BASE_PAYLOAD.startswith(b'NetImmerse'))

    def test_negative_cases_target_actual_guards_and_caller_policy(self):
        values = fixtures.inputs()
        self.assertEqual(len(records(values['no-stat.esm'])), 1)
        self.assertNotIn(b'NAME', dict(records(values['no-name.esm'])[1][2]))
        self.assertNotIn(b'MODL', dict(records(values['no-model.esm'])[1][2]))
        self.assertIn(b'DELE', dict(records(values['deleted.esm'])[1][2]))
        self.assertIn(b'NOPE', dict(records(values['unknown-sub.esm'])[1][2]))
        self.assertEqual(values['wrong-tag.esm'][:4], b'NOPE')
        with self.assertRaises(ValueError):
            records(values['oversized.esm'])

    def test_case_inventory_and_both_precedence_orders(self):
        self.assertEqual(len(fixtures.CASES), 16)
        self.assertEqual(len({c[0] for c in fixtures.CASES}), 16)
        self.assertTrue({'base-first', 'overlay-first', 'missing-resource', 'missing-record',
                         'reject-esm', 'reject-policy', 'missing-esm', 'reject-archive', 'normalized', 'esp'}
                        <= {c[1] for c in fixtures.CASES})

    def test_exact_reruns_unknown_and_changed_files_fail_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'inputs'
            before = fixtures.prepare(directory)
            self.assertEqual(fixtures.prepare(directory), before)
            unknown = directory / 'unexpected'
            unknown.write_bytes(b'preserve')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected existing'):
                fixtures.prepare(directory)
            self.assertEqual(unknown.read_bytes(), b'preserve')
            unknown.unlink()
            changed = directory / 'valid.esm'
            changed.write_bytes(b'preserve changed')
            with self.assertRaisesRegex(RuntimeError, 'bytes differ'):
                fixtures.prepare(directory)
            self.assertEqual(changed.read_bytes(), b'preserve changed')

    def test_driver_contract_only_not_a_substitute_engine(self):
        # Mock only the orchestration boundary. This test proves no C++ behavior.
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(fixtures.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                run.side_effect = [subprocess.CompletedProcess([], 0, c[-1], '') for c in fixtures.CASES]
                fixtures.run_cases(Path('not-executed'), Path(temp))
                self.assertEqual(run.call_count, 16)
                for call, case in zip(run.call_args_list, fixtures.CASES):
                    self.assertEqual(call.args[0][1], case[1])
                    self.assertEqual(len(call.args[0]), 5)
                    self.assertEqual(call.kwargs['timeout'], 60)

    def test_driver_rejects_nonzero_exit_missing_marker_mutation_and_new_files(self):
        for failure in ('exit', 'marker', 'mutation', 'creation'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                def result(*args, **kwargs):
                    if failure == 'mutation':
                        (directory / 'valid.esm').write_bytes(b'changed')
                    if failure == 'creation':
                        (directory / 'must-not-be-created.bsa').write_bytes(b'new')
                    return subprocess.CompletedProcess([], 1 if failure == 'exit' else 0,
                        '' if failure == 'marker' else 'PASS resource:', '')
                with patch.object(fixtures.subprocess, 'run', side_effect=result), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    fixtures.run_cases(Path('not-executed'), directory)

    def test_timeout_still_checks_input_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            def timeout(*args, **kwargs):
                (directory / 'must-not-be-created.esm').write_bytes(b'new')
                raise subprocess.TimeoutExpired('not-executed', 60)
            with patch.object(fixtures.subprocess, 'run', side_effect=timeout), \
                    self.assertRaisesRegex(RuntimeError, 'changed input tree'):
                fixtures.run_cases(Path('not-executed'), directory)

    def test_native_runtime_when_explicit_genuine_fixture_supplied(self):
        executable = os.environ.get('OPENMW_ESM_VFS_CHECK')
        if not executable:
            self.skipTest('No compiled genuine ESM/VFS checker supplied; C++ compilation/runtime not executed')
        self.assertTrue(Path(executable).is_file())
        with tempfile.TemporaryDirectory() as temp:
            fixtures.run_cases(Path(executable), Path(temp))


if __name__ == '__main__':
    unittest.main()
