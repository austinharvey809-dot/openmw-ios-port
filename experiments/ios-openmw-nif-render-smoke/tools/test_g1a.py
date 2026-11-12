"""Offline contracts and evidence-rejection tests; never native/GPU proof."""
import ast
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import contracts as c
import run_geometry as run


def synthetic_result():
    return {'status': 'PASS', 'scope': 'structural OSG geometry; no GPU rendering',
            'records': 3, 'roots': 1, 'geometry': 1, 'vertices': 3, 'triangles': 1,
            'source_equivalence': True, 'parser_released': True, 'negative_cases': list(c.NEGATIVES),
            'object_id': 'eIOSStatic', 'model': 'TeSt.NIF', 'resource_key': 'meshes/test.nif',
            'resource_sha256': c.LOCK['fixtures']['triangle-candidate.nif']['sha256'],
            'geometry_sha256': run.expected_geometry_hash()}


class FixtureContracts(unittest.TestCase):
    def scratch(self, root):
        path = root / 'fixtures'
        shutil.copytree(c.DATA, path)
        return path

    def test_exact_original_fixture_inventory_and_hashes(self):
        self.assertEqual(len(c.fixture_snapshot()), 12)
        self.assertEqual(set(c.LOCK['fixture_text_lf']), {'fixture-manifest.json', 'nif-source-sha256.json'})

    def test_changed_binary_size_or_bytes_is_rejected(self):
        for extra in (b'', b'x'):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                path = self.scratch(Path(directory)) / 'triangle-candidate.nif'
                data = bytearray(path.read_bytes())
                data[0] ^= 1
                path.write_bytes(bytes(data) + extra)
                with self.assertRaisesRegex(ValueError, 'Fixture inventory/hash/size'):
                    c.fixture_snapshot(path.parent)

    def test_missing_unexpected_and_nonregular_entries_are_rejected(self):
        for mode in ('missing', 'unexpected', 'directory'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                path = self.scratch(Path(directory))
                if mode == 'missing':
                    (path / 'valid.esm').unlink()
                elif mode == 'unexpected':
                    (path / 'extra.txt').write_bytes(b'extra')
                else:
                    (path / 'extra').mkdir()
                with self.assertRaises(ValueError):
                    c.fixture_snapshot(path)

    def test_metadata_newlines_are_portable_but_not_content_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.scratch(Path(directory))
            for name in c.LOCK['fixture_text_lf']:
                file = path / name
                file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            self.assertEqual(len(c.fixture_snapshot(path)), 12)
            file.write_bytes(file.read_bytes() + b' ')
            with self.assertRaises(ValueError):
                c.fixture_snapshot(path)


class EvidenceContracts(unittest.TestCase):
    def test_synthetic_policy_fixture_is_consistent(self):
        run.validate(synthetic_result())

    def test_missing_lifetime_equivalence_or_negative_check_is_rejected(self):
        for key in ('source_equivalence', 'parser_released'):
            value = synthetic_result()
            value[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                run.validate(value)
        value = synthetic_result()
        value['negative_cases'].pop()
        with self.assertRaises(ValueError):
            run.validate(value)
        value['negative_cases'] = list(reversed(c.NEGATIVES))
        with self.assertRaises(ValueError):
            run.validate(value)

    def test_wrong_counts_resource_and_geometry_digest_are_rejected(self):
        for key, replacement in (('vertices', 4), ('triangles', 0), ('resource_key', 'test.nif'),
                                 ('geometry', True),
                                 ('resource_sha256', '0' * 64), ('geometry_sha256', '0' * 64),
                                 ('object_id', 'other'), ('model', 'other'), ('status', 'FAIL')):
            value = synthetic_result()
            value[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                run.validate(value)

    def test_no_gpu_claim_can_replace_structural_scope(self):
        value = synthetic_result()
        value['scope'] = 'visible iPhone rendering'
        with self.assertRaises(ValueError):
            run.validate(value)


class SourceContracts(unittest.TestCase):
    def test_completed_preservation_and_committed_version2_graphics(self):
        self.assertEqual(c.preservation(), 191)
        self.assertEqual(c.graphics_baseline(), 23)
        self.assertEqual(c.LOCK['graphics_sources_copied'], [])

    def test_completed_source_audits_still_pass(self):
        osg = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', c.REPO.parent / 'OpenSceneGraph-pinned'))
        self.assertEqual(c.audit(osg)['completed_audits']['g0b_source_headers'], 59)

    def test_python_syntax(self):
        for path in (c.ROOT / 'tools').glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_single_provider_and_genuine_source_recipes(self):
        cmake = (c.ROOT / 'CMakeLists.txt').read_text()
        self.assertIn('../ios-openmw-nif-smoke', cmake)
        self.assertIn('PUBLIC openmw-ios-nif-parser', cmake)
        self.assertNotIn('add_subdirectory(cmake/osg)', cmake)
        self.assertNotIn('ios-openmw-nif-device-smoke', cmake)
        self.assertNotIn('MACOSX_BUNDLE', cmake)
        self.assertIn('$<TARGET_FILE:openmw-nif-parse-check>', cmake)
        self.assertIn('g1a-owned-geometry-and-six-parser-cases', cmake)

    def test_native_mutations_cover_all_required_cases_without_release_asserts(self):
        source = (c.ROOT / 'tests/geometry_check.cpp').read_text()
        for name in c.NEGATIVES:
            self.assertIn('reject("' + name + '"', source)
        self.assertNotIn('assert(', source.split('namespace', 1)[1])
        self.assertLess(source.index('parsed.file.reset();'), source.index('inspectOwned(owned);'))
        self.assertIn('source.mVertices.begin()', source)
        self.assertIn('source.mTriangles.begin()', source)

    def test_manual_workflow_requires_all_gates_and_retains_failure_evidence(self):
        workflow = (c.REPO / '.github/workflows/ios-openmw-nif-geometry-host-smoke.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('\n  push:', workflow)
        self.assertNotIn('\n  pull_request:', workflow)
        self.assertIn('fetch-depth: 0', workflow)  # Historical baseline blobs must be available.
        self.assertIn('-DCMAKE_POLICY_VERSION_MINIMUM=3.5', workflow)
        self.assertIn('-DCMAKE_OSX_ARCHITECTURES=arm64', workflow)
        self.assertIn('ctest --test-dir', workflow)
        self.assertIn('if: always()', workflow)
        self.assertIn('actions/upload-artifact@v6', workflow)
        self.assertNotIn('continue-on-error', workflow)


if __name__ == '__main__':
    unittest.main()
