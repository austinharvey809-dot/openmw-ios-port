"""Offline workflow and evidence regression tests, never native compilation evidence."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ci_checks as ci
import test_package_ios as packaging_tests
import test_data_app as app_tests

WORKFLOW = ci.REPO / '.github/workflows/ios-openmw-data-smoke.yml'
TEXT = WORKFLOW.read_text(encoding='utf-8')
JOBS = dict(re.findall(r'^  ([a-z][a-z-]+):\n(.*?)(?=^  [a-z][a-z-]+:|\Z)', TEXT.split('\njobs:\n')[1], re.M | re.S))


def scripts(text):
    return ['\n'.join(line[10:] if line.startswith('          ') else '' for line in block.splitlines())
            for block in re.findall(r'        run: \|\n((?:(?:          .*|)\n)+)', text)]


class WorkflowTests(unittest.TestCase):
    def test_only_manual_trigger_and_read_permission(self):
        self.assertEqual(TEXT.split('\non:\n')[1].split('\npermissions:')[0].strip(), 'workflow_dispatch:')
        self.assertEqual(TEXT.split('\npermissions:\n')[1].split('\nenv:')[0].strip(), 'contents: read')
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-native'})
        for job in JOBS.values():
            self.assertIn('runs-on: macos-26', job)
            self.assertNotIn('needs:', job)

    def test_exact_requested_commit_and_pinned_sibling(self):
        for job in JOBS.values():
            self.assertEqual(job.count('uses: actions/checkout@v6'), 2)
            for text in ('ref: ${{ github.sha }}', 'path: openmw', 'path: osg-pinned',
                         'repository: OpenMW/osg', 'ref: ' + ci.package.OSG_REVISION,
                         'test "$GITHUB_REF" = refs/heads/ios-port',
                         'test "$(git -C "$OPENMW_SOURCE" rev-parse HEAD)" = "$GITHUB_SHA"',
                         'test "$(git -C "$OPENMW_ESM_OSG_SOURCE" rev-parse HEAD)" = "$OSG_REVISION"'):
                self.assertIn(text, job)
            for setting in ('persist-credentials: false', 'fetch-depth: 1', 'submodules: false', 'lfs: false'):
                self.assertEqual(job.count(setting), 2)

    def test_both_jobs_audit_before_configure(self):
        for job in JOBS.values():
            for text in ('audit_sources.py', '--require-complete', 'ci_evidence.py" sources',
                         'ci_checks.py" inventory', 'ci_evidence.py" config', 'ci_checks.py" prepared'):
                self.assertIn(text, job)
            self.assertLess(job.index('ci_checks.py" inventory'), job.index('cmake -S'))
            self.assertIn('xcodebuild -version', job)
            self.assertIn('python3 --version', job)

    def test_host_runs_all_reviewed_tests_plus_workflow_and_e_integrity(self):
        job = JOBS['host-validation']
        for text in ('ci_checks.py" regressions', 'ci_checks.py" syntax', "-p 'test_ci*.py' -v",
                     "$E_EXPERIMENT/tools\" -p 'test_*.py' -v", 'prepare_inputs.py',
                     '-DOPENMW_IOS_ESM_VFS_HOST_TESTS=ON', 'git -C "$OPENMW_SOURCE" diff --check'):
            self.assertIn(text, job)
        self.assertNotIn('cmake --build', job)
        self.assertIn('--build "$BUILD_DIR/esm-reader"', job)

    def test_native_device_configuration_and_unsigned_builds(self):
        job = JOBS['iphoneos-native']
        for text in ('-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT="$SDK"',
                     '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0',
                     '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO',
                     '--build "$BUILD_DIR/esm-vfs/esm-reader"'):
            self.assertIn(text, job)
        self.assertEqual(job.count('CODE_SIGNING_ALLOWED=NO'), 4)
        self.assertNotIn('ctest ', job)

    def test_exact_archives_validated_before_normal_link_and_app(self):
        job = JOBS['iphoneos-native']
        anchors = ['--target openmw-ios-esm-reader openmw-ios-esm-vfs', 'ci_evidence.py" archives',
                   'validate_esm_archive.py', 'validate_esm_vfs_archive.py', '--target openmw-data-link-check',
                   '--link-executable "$LINK_PATH"', '--target IOSOpenMWDataSmoke',
                   'ci_checks.py" app', 'package_ios.py" --app', '--validate-only', 'ci_checks.py" ipa']
        indices = [job.index(anchor) for anchor in anchors]
        self.assertEqual(indices, sorted(indices))
        for name in ('libopenmw-ios-esm-reader.a', 'libopenmw-ios-esm-vfs.a',
                     'archive-inspection/milestone-d', 'archive-inspection/milestone-e'):
            self.assertIn(name, job)
        manifest = json.loads(ci.inputs.auditor.MANIFEST.read_text())
        self.assertEqual((len(manifest['inherited_sources']), len(manifest['additional_sources'])), (15, 6))
        self.assertTrue(ci.contracts()['valid'])

    def test_gates_fail_closed_and_metadata_inspection_uses_real_products(self):
        job = JOBS['iphoneos-native']
        self.assertEqual(job.count("if: ${{ success() && steps.link_gate.outcome == 'success' }}"), 2)
        self.assertEqual(job.count("if: ${{ success() && steps.app_gate.outcome == 'success' }}"), 1)
        for gate in ('link_gate', 'app_gate', 'package_gate'):
            self.assertIn('id: ' + gate, job)
        for executable in ('$LINK_PATH', '$APP_PATH/IOSOpenMWDataSmoke'):
            for command in ('xcrun lipo -archs', 'xcrun otool -hv', 'xcrun otool -l', 'xcrun vtool -show-build'):
                self.assertIn(command + ' "' + executable + '"', job)
        self.assertIn('--sdk "$SDK" --evidence "$EVIDENCE/f0-link"', job)
        self.assertIn('--prepared "$BUILD_DIR/prepared" --sdk "$SDK"', job)
        self.assertIn('--validate-only "$EVIDENCE/IOSOpenMWDataSmoke-unsigned.ipa" --sdk "$SDK"', job)

    def test_always_preserve_diagnostics_and_separate_gate_statuses(self):
        for kind, job in zip(('host', 'native'), JOBS.values()):
            self.assertEqual(job.count('if: always()'), 3)
            self.assertIn('ci_checks.py" collect', job)
            self.assertIn('JOB_STATUS: ${{ job.status }}', job)
            self.assertIn("'physical_device_execution': 'not-performed'", job)
            self.assertIn('F0_executable_link', job)
            self.assertIn('F1_UIKit_application', job)
            self.assertIn('packaging_and_reopened_IPA', job)
            self.assertIn('SHA256SUMS', job)
            self.assertIn('uses: actions/upload-artifact@v6\n        if: always()', job)
            self.assertIn('name: ios-openmw-data-' + kind, job)
            self.assertIn('if-no-files-found: error', job)
            self.assertLess(job.index('Initialize failure evidence'), job.index('uses: actions/checkout'))

    def test_failed_build_cannot_be_reported_as_a_skipped_or_successful_gate(self):
        for job in JOBS.values():
            source, = [source for block in scripts(job)
                       for source in re.findall(r"python3 - <<'PY'\n(.*?)\nPY", block, re.S)]
            for build, inspection, expected in (('failure', 'skipped', 'failure'),
                    ('success', 'failure', 'failure'), ('cancelled', 'skipped', 'cancelled'),
                    ('success', 'success', 'success'), ('skipped', 'skipped', 'not-completed')):
                with self.subTest(build=build, inspection=inspection), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    (root / 'compiler.log').write_bytes(b'compiler/linker diagnostics')
                    env = {'EVIDENCE': str(root), 'JOB_STATUS': 'failure', 'F0_BUILD_STATUS': build,
                           'F0_STATUS': inspection, 'F1_BUILD_STATUS': 'skipped', 'F1_STATUS': 'skipped',
                           'PACKAGE_STATUS': 'skipped', 'GITHUB_STEP_SUMMARY': str(root / 'summary')}
                    with patch.dict(os.environ, env):
                        exec(compile(source, 'workflow-finalizer', 'exec'), {})
                    status = json.loads((root / 'job-status.json').read_text())
                    self.assertEqual(status['F0_executable_link'], expected)
                    self.assertEqual(status['F1_UIKit_application'], 'not-completed')
                    self.assertEqual(status['physical_device_execution'], 'not-performed')
                    rows = (root / 'SHA256SUMS').read_text().splitlines()
                    self.assertEqual(len(rows), 2)
                    for row in rows:
                        digest, name = row.split('  ', 1)
                        self.assertEqual(digest, ci.sha(root / name))

    def test_no_fetches_error_suppression_signing_or_extra_libraries(self):
        for forbidden in ('continue-on-error', '|| true', 'brew install', 'pip install', 'curl ', 'wget ',
                          'git clone', 'codesign ', 'security import', 'DEVELOPMENT_TEAM',
                          'PROVISIONING_PROFILE', 'secrets.', 'allow-multiple-definition', 'force_load',
                          'all_load', 'undefined dynamic_lookup', 'ANGLE_ROOT', 'SDL', 'Metal'):
            self.assertNotIn(forbidden, TEXT)
        for script in scripts(TEXT):
            self.assertTrue(script.startswith('set -euo pipefail\n'))

    def test_all_bash_and_embedded_python_syntax(self):
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else None)
        self.assertTrue(bash and Path(bash).is_file(), 'Existing Bash required for workflow syntax validation')
        blocks = scripts(TEXT)
        self.assertEqual(len(blocks), TEXT.count('run: |'))
        embedded = 0
        for block in blocks:
            for source in re.findall(r"python3 - <<'PY'\n(.*?)\nPY", block, re.S):
                ast.parse(source)
                embedded += 1
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'workflow.sh'
                path.write_bytes(block.encode('utf-8'))
                result = subprocess.run([bash, '-n', path.as_posix()], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(embedded, 2)
        self.assertTrue(ci.syntax()['valid'])

    def test_documentation_and_whitespace_contracts(self):
        doc = (ci.ROOT / 'README.md').read_text(encoding='utf-8')
        for text in ('ios-openmw-data-smoke.yml', '28', 'F0', 'F1', 'prior-milestones.json',
                     'ios-openmw-data-host-', 'ios-openmw-data-native-', 'manual review',
                     'No Apple compiler/linker or physical-device test has run for F'):
            self.assertIn(text, doc)
        for old in ('There is no F workflow yet', 'no F workflow is created now'):
            self.assertNotIn(old, doc)
        for path in [WORKFLOW, ci.ROOT / 'README.md', ci.CONTRACT, *sorted((ci.ROOT / 'tools').glob('*.py'))]:
            content = path.read_text(encoding='utf-8')
            self.assertTrue(content.endswith('\n'), str(path))
            self.assertFalse(any(line.rstrip() != line for line in content.splitlines()), str(path))


class EvidenceTests(unittest.TestCase):
    def test_preservation_manifest_covers_all_tracked_a_to_e_files_and_workflows(self):
        paths = subprocess.check_output(['git', '-C', str(ci.REPO), 'ls-files'], text=True).splitlines()
        roots = ('ios-openmw-core', 'ios-openmw-bsa', 'ios-openmw-bsa-vfs', 'ios-openmw-esm', 'ios-openmw-esm-vfs')
        expected = {p for p in paths if any(p.startswith('experiments/' + root + '/')
                    or p == '.github/workflows/' + root + '.yml' for root in roots)}
        self.assertEqual(set(json.loads(ci.CONTRACT.read_text())['sha256_lf']), expected)
        self.assertEqual(ci.contracts()['preserved_files'], len(expected))

    def test_preservation_hash_changes_are_rejected(self):
        manifest = json.loads(ci.CONTRACT.read_text())
        manifest['sha256_lf'][next(iter(manifest['sha256_lf']))] = '0' * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'contract.json'
            ci.write_json(path, manifest)
            with patch.object(ci, 'CONTRACT', path), self.assertRaisesRegex(ValueError, 'Prior milestone changed'):
                ci.contracts()

    def test_regression_runner_rejects_missing_skipped_and_expected_failure_tests(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(unittest.TestSuite, 'countTestCases', return_value=27), self.assertRaises(ValueError):
                ci.regressions(Path(temporary))
            for kind in ('skipped', 'expectedFailures', 'errors'):
                result = unittest.TestResult()
                result.testsRun = 28
                getattr(result, kind).append(('test', 'simulated failure'))
                with patch.object(unittest.TextTestRunner, 'run', return_value=result), self.assertRaises(ValueError):
                    ci.regressions(Path(temporary))
                self.assertFalse(json.loads((Path(temporary) / 'python-regressions.json').read_text())['valid'])

    def test_unique_product_location_rejects_missing_empty_and_ambiguous_outputs(self):
        for kind, name in (('link', 'openmw-data-link-check'), ('app', ci.package.APP_NAME)):
            for failure in ('missing', 'ambiguous', 'none'):
                with self.subTest(kind=kind, failure=failure), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    build, evidence = root / 'build', root / 'evidence'
                    build.mkdir(); evidence.mkdir()
                    if failure != 'missing':
                        path = build / name
                        path.mkdir() if kind == 'app' else path.write_bytes(b'test product, not native evidence')
                    if failure == 'ambiguous':
                        (build / 'second').mkdir()
                        second = build / 'second' / name
                        second.mkdir() if kind == 'app' else second.write_bytes(b'other')
                    with patch.dict(os.environ, {'GITHUB_ENV': str(root / 'env')}):
                        if failure == 'none':
                            self.assertTrue(ci.locate(build, kind, evidence)['valid'])
                            self.assertIn(str(path), (root / 'env').read_text())
                        else:
                            with self.assertRaises(ValueError): ci.locate(build, kind, evidence)
                    if kind == 'link' and failure == 'none':
                        path.write_bytes(b'')
                        with self.assertRaisesRegex(ValueError, 'Empty'): ci.locate(build, kind, evidence)

    def test_prepared_inputs_and_provenance_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            config = root / 'Config'
            config.write_text(app_tests.genuine_config_text(), encoding='utf-8')
            prepared = root / 'prepared'
            ci.inputs.prepare(prepared, app_tests.OSG, config)
            self.assertTrue(ci.prepared(prepared, app_tests.OSG, config)['valid'])
            for relative in ('resources/data-build.json', 'resources/Provenance/osg/Config',
                             'include/FixtureExpectations.hpp', 'resources/Fixtures/base.bsa'):
                path = prepared / relative
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                with self.assertRaisesRegex(ValueError, 'Prepared resources'):
                    ci.prepared(prepared, app_tests.OSG, config)
                path.write_bytes(original)

    def test_built_and_reopened_resources_must_match_prepared_provenance(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            config = root / 'Config'; config.write_text(app_tests.genuine_config_text(), encoding='utf-8')
            prepared = root / 'prepared'; ci.inputs.prepare(prepared, app_tests.OSG, config)
            files = {name: ci.package.Entry(data, packaging_tests.REGULAR)
                     for name, data in ci.tree(prepared / 'resources').items()}
            self.assertTrue(ci.verify_resources(files, prepared))
            for name in ('data-build.json', 'Provenance/osg/Config', 'Fixtures/valid.esm', 'Licenses/OSG-LICENSE.txt'):
                changed = dict(files)
                changed[name] = ci.package.Entry(b'changed', packaging_tests.REGULAR)
                with self.assertRaisesRegex(ValueError, 'Built resource/provenance mismatch'):
                    ci.verify_resources(changed, prepared)
            with patch.dict(os.environ, {'GITHUB_SHA': '0' * 40}), self.assertRaisesRegex(ValueError, 'Requested source'):
                ci.verify_resources(files, prepared)

    def test_reopened_ipa_provenance_is_checked_independently_of_bundle_metadata(self):
        # Real ZIP round trip; synthetic executable is validator test data only.
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            config = root / 'Config'; config.write_text(app_tests.genuine_config_text(), encoding='utf-8')
            prepared = root / 'prepared'; ci.inputs.prepare(prepared, app_tests.OSG, config)
            files = packaging_tests.bundle(ci.inputs.MANIFEST.read_bytes(), ci.inputs.fixture_bytes())
            files.update({name: ci.package.Entry(data, packaging_tests.REGULAR)
                          for name, data in ci.tree(prepared / 'resources').items()})
            ipa = root / 'test.ipa'
            ci.package.write_ipa(files, ipa)
            self.assertTrue(ci.ipa_report(ipa, prepared, None)['valid'])
            files['Provenance/osg/Config'] = ci.package.Entry(b'altered', packaging_tests.REGULAR)
            ci.package.write_ipa(files, ipa)
            with self.assertRaisesRegex(ValueError, 'Built resource/provenance mismatch'):
                ci.ipa_report(ipa, prepared, None)

    def test_failure_collection_preserves_partial_products_without_granting_success(self):
        names = ('CMakeFiles/CMakeConfigureLog.yaml', 'prepare-inputs.log', str(ci.CONFIG),
                 'prepared/resources/data-build.json', 'Release-iphoneos/openmw-data-link-check',
                 'Release-iphoneos/IOSOpenMWDataSmoke.app/Info.plist',
                 'esm-vfs/Release-iphoneos/libopenmw-ios-esm-vfs.a',
                 'esm-vfs/esm-reader/Release-iphoneos/libopenmw-ios-esm-reader.a')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); build = root / 'build'; evidence = root / 'evidence'
            for name in names:
                path = build / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'partial output')
            ci.collect(build, evidence)
            for name in names:
                self.assertEqual((evidence / 'build-products' / name).read_bytes(), b'partial output')
            self.assertFalse((evidence / 'job-status.json').exists())


if __name__ == '__main__':
    unittest.main()
