"""Offline Milestone E workflow and evidence contracts; synthetic Mach-O bytes are not native build proof."""
import ast
import contextlib
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
import ci_evidence as evidence
import fixtures
import validate_esm_vfs_archive as validator

ROOT, REPO = auditor.ROOT, auditor.REPO
OSG = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
TEXT = (REPO / '.github/workflows/ios-openmw-esm-vfs.yml').read_text(encoding='utf-8')
JOBS = dict(re.findall(r'^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)', TEXT.split('\njobs:\n', 1)[1], re.M | re.S))


def object_file(cpu=0x0100000C, subtype=0, target=2, minimum=18 << 16, kind=1, commands=None):
    if commands is None:
        commands = [struct.pack('<6I', 0x32, 24, target, minimum, 26 << 16, 0)]
    body = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, subtype, kind, len(commands), len(body), 0, 0) + body


def archive(names=None, replace=None):
    if names is None: names = [Path(source).stem + '.o' for source in validator.SOURCES]
    result = b'!<arch>\n'
    for index, name in enumerate(names):
        encoded = name.encode() + b'\0\0'
        body = encoded + (replace or {}).get(index, object_file())
        label = '#1/' + str(len(encoded))
        result += (f'{label:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}`\n').encode()
        result += body + (b'\n' if len(body) % 2 else b'')
    return result


def scripts(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != 'run: |': continue
        indent = len(line) - len(line.lstrip())
        body = []
        for value in lines[index + 1:]:
            if value.strip() and len(value) - len(value.lstrip()) <= indent: break
            body.append(value[indent + 2:] if value.strip() else '')
        yield '\n'.join(body) + '\n'


class ArchiveTests(unittest.TestCase):
    def test_exact_six_sources_names_checksums_and_unchanged_core_contract(self):
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(tuple(manifest['additional_sources']), validator.SOURCES)
        self.assertEqual(len(validator.SOURCES), 6)
        self.assertEqual(len(validator.core.SOURCES), 5)
        self.assertEqual(len(evidence.previous.SOURCES), 15)
        for names in (None, [Path(source).name + '.o' for source in validator.SOURCES]):
            data = archive(names=names)
            report = validator.validate(data)
            self.assertTrue(report['valid'])
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual({obj['source'] for obj in report['objects']}, set(validator.SOURCES))
            for obj in report['objects']:
                self.assertEqual((obj['architecture'], obj['platform'], obj['minimum_os']), ('arm64', 'IOS', '18.0'))
                self.assertEqual(obj['sha256'], hashlib.sha256(object_file()).hexdigest())
        with self.assertRaises(validator.core.ValidationError): validator.core.validate(archive())

    def test_empty_missing_extra_unexpected_duplicate_alias_and_unsafe_objects_rejected(self):
        names = [Path(s).stem + '.o' for s in validator.SOURCES]
        aliases = names.copy(); aliases[-1] = Path(validator.SOURCES[0]).name + '.o'
        for variant in ([], names[:-1], names + ['extra.o'], ['unexpected.o', *names[1:]],
                        [names[0], *names[:-1]], aliases, ['../escape.o', *names[1:]]):
            with self.subTest(names=variant), self.assertRaises(validator.core.ValidationError):
                validator.validate(archive(names=variant))
        for data in (b'', b'not ar', archive()[:-1], archive(replace={3: b''})):
            with self.subTest(data=data[:20]), self.assertRaises(validator.core.ValidationError): validator.validate(data)

    def test_all_six_objects_reject_other_platforms_architectures_and_minimums(self):
        bad = [object_file(target=p) for p in (1, 3, 4, 6, 7, 8, 11, 12)]
        bad += [object_file(cpu=0x01000007), object_file(subtype=2), object_file(kind=6),
                object_file(minimum=17 << 16), object_file(minimum=(18 << 16) | (1 << 8)), object_file(minimum=19 << 16)]
        for index in range(6):
            for payload in bad:
                with self.subTest(index=index, payload=payload[:20]), self.assertRaises(validator.core.ValidationError):
                    validator.validate(archive(replace={index: payload}))

    def test_malformed_missing_legacy_duplicate_metadata_and_bitcode_rejected(self):
        build = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 26 << 16, 0)
        bad = [object_file(commands=[]), object_file(commands=[build, build]), object_file()[:-1], b'BC\xc0\xde' + bytes(60),
               object_file(commands=[struct.pack('<4I', 0x25, 16, 18 << 16, 26 << 16)]),
               object_file(commands=[struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 1)])]
        for payload in bad:
            with self.assertRaises(validator.core.ValidationError): validator.validate(archive(replace={5: payload}))

    def test_native_cli_keeps_per_object_tools_and_failure_reports(self):
        for target in (2, 7):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / 'device.a'; output = root / 'inspection'
                source.write_bytes(archive(replace={5: object_file(target=target)}))
                def run(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'raw metadata\n', '')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(output)]), \
                        patch.object(validator.platform, 'system', return_value='Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run) as mocked, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 0 if target == 2 else 1)
                report = json.loads((output / 'archive-validation.json').read_text())
                self.assertEqual(report['valid'], target == 2)
                self.assertEqual(len(list((output / 'objects').glob('*.otool.txt'))), 6)
                commands = [call.args[0] for call in mocked.call_args_list]
                self.assertEqual(sum('otool' in cmd and '-l' in cmd for cmd in commands), 6)
                self.assertIn(['xcrun', 'lipo', str(source), '-verify_arch', 'arm64'], commands)
                self.assertIn(['xcrun', 'ar', '-t', str(source)], commands)

    def test_missing_inputs_tools_wrong_host_and_failed_or_fat_tool_results_fail_closed(self):
        for failure in ('input', 'tool', 'host', 'status', 'arches'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / 'device.a'; output = root / 'out'
                if failure != 'input': source.write_bytes(archive())
                def run(command, **kwargs):
                    if failure == 'tool': raise FileNotFoundError('xcrun missing')
                    return subprocess.CompletedProcess(command, 1 if failure == 'status' else 0,
                        'arm64 x86_64\n' if '-archs' in command else '', 'tool failure\n')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(output)]), \
                        patch.object(validator.platform, 'system', return_value='Windows' if failure == 'host' else 'Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 1)
                self.assertFalse(json.loads((output / 'archive-validation.json').read_text())['valid'])


def make_build(root):
    """Evidence-format inputs only. Does not substitute for any real C++ runtime test."""
    build, output = root / 'build', root / 'evidence'
    build.mkdir(); output.mkdir()
    for _, (name, sources) in evidence.ARCHIVES.items():
        path = build / 'nested' / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(archive(names=[Path(s).stem + '.o' for s in sources]))
    config = build / evidence.CONFIG
    config.parent.mkdir(parents=True)
    config.write_bytes(b'Config handoff unit-test data; not CMake output')
    evidence.write_json(output / 'config-validation.json', {'valid': True, 'sha256': evidence.sha(config)})
    evidence.write_json(output / 'source-provenance.json', {'scope': 'Evidence-handoff unit test only'})
    return build, output


def make_runtime_reports(build, output):
    fixtures.prepare(build / 'synthetic-esm-vfs')
    text = '\n'.join(c[0] + ': ' + c[-1] for c in fixtures.CASES)
    text += '\nSixteen synthetic ESM/VFS cases passed with unchanged input tree.\n'
    log = build / 'Testing/Temporary/LastTest.log'
    log.parent.mkdir(parents=True)
    log.write_text(text, encoding='utf-8')
    (output / 'ctest-results.xml').write_text(
        '<testsuite tests="1"><testcase name="openmw-esm-vfs-runtime" status="run"/></testsuite>', encoding='utf-8')


class EvidenceTests(unittest.TestCase):
    def test_sources_snapshot_checks_all_86_files_revisions_and_validation_inputs(self):
        if not OSG.is_dir(): self.skipTest('Genuine pinned OSG checkout unavailable')
        sha = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_SHA': sha}):
            output = Path(temp)
            evidence.source_snapshot(OSG, output)
            result = json.loads((output / 'source-provenance.json').read_text())
            self.assertEqual((result['project_files'], result['osg_files']), (79, 7))
            self.assertEqual(result['openmw_commit'], sha)
            self.assertEqual(result['osg_revision'], auditor.esm_audit.OSG_REVISION)
            for name in ('source-sha256.txt', 'source-sha256-lf.txt'):
                self.assertEqual(len((output / name).read_text().splitlines()), 86)
            for name in ('milestone-e-source-audit.json', 'milestone-d-source-audit.json',
                         'OSG-LICENSE.txt', 'OpenMW-LICENSE.txt', 'validation-input-sha256.txt'):
                self.assertTrue((output / name).is_file())
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_SHA': '0' * 40}), self.assertRaises(evidence.EvidenceError):
            evidence.source_snapshot(OSG, Path(temp))

    def test_fifteen_object_validator_retains_original_acceptance_contract(self):
        sources = evidence.previous.SOURCES
        self.assertEqual(len(sources), 15)
        data = archive(names=[Path(s).stem + '.o' for s in sources])
        self.assertTrue(evidence.previous.validate(data)['valid'])
        with self.assertRaises(evidence.previous.core.ValidationError): evidence.previous.validate(archive())
        for index in range(15):
            with self.subTest(index=index), self.assertRaises(evidence.previous.core.ValidationError):
                evidence.previous.validate(archive(names=[Path(s).stem + '.o' for s in sources],
                                                   replace={index: object_file(target=7)}))

    def test_archive_location_requires_both_unique_nonempty_outputs(self):
        for label in evidence.ARCHIVES:
            for failure in ('missing', 'empty', 'ambiguous'):
                with self.subTest(label=label, failure=failure), tempfile.TemporaryDirectory() as temp:
                    build, output = make_build(Path(temp))
                    name = evidence.ARCHIVES[label][0]
                    path = build / 'nested' / name
                    if failure == 'missing': path.unlink()
                    elif failure == 'empty': path.write_bytes(b'')
                    else: (build / name).write_bytes(path.read_bytes())
                    with self.assertRaises(evidence.EvidenceError): evidence.locate_archives(build, output, True)
                    reports = json.loads((output / 'archive-locations.json').read_text())
                    self.assertFalse(reports[label]['valid'])
                    if failure == 'ambiguous':
                        self.assertEqual(len(list((output / 'ambiguous-archives' / label).rglob('*.a'))), 2)

    def test_host_report_validates_sixteen_cases_junit_both_archives_and_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            build, output = make_build(Path(temp)); make_runtime_reports(build, output)
            with patch.object(evidence.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'unit-test ar inventory', '')):
                evidence.host_results(build, output)
            report = json.loads((output / 'host-validation.json').read_text())
            self.assertTrue(report['valid'])
            self.assertEqual(report['runtime_cases'], 16)
            self.assertEqual(report['unchanged_input_files'], 14)
            self.assertEqual([len(report['archives'][k]['objects']) for k in evidence.ARCHIVES], [15, 6])
            evidence.collect(build, output, 'host', 'success')
            self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'success')

    def test_host_report_missing_failed_skipped_or_wrong_ctest_and_case_results_fail_closed(self):
        for failure in ('missing-junit', 'failure', 'skip', 'reported-failure', 'wrong-name', 'extra-test', 'missing-case',
                        'duplicate-case', 'missing-summary', 'changed-input', 'new-file', 'new-directory', 'missing-tool', 'failed-tool'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                build, output = make_build(Path(temp)); make_runtime_reports(build, output)
                junit = output / 'ctest-results.xml'
                log = build / 'Testing/Temporary/LastTest.log'
                if failure == 'missing-junit': junit.unlink()
                elif failure in {'failure', 'skip'}:
                    tag = 'failure' if failure == 'failure' else 'skipped'
                    junit.write_text('<testsuite><testcase name="openmw-esm-vfs-runtime"><' + tag + '/></testcase></testsuite>')
                elif failure == 'wrong-name': junit.write_text('<testsuite><testcase name="openmw-esm-runtime"/></testsuite>')
                elif failure == 'reported-failure':
                    junit.write_text('<testsuite failures="1"><testcase name="openmw-esm-vfs-runtime"/></testsuite>')
                elif failure == 'extra-test': junit.write_text('<testsuite><testcase name="openmw-esm-vfs-runtime"/><testcase name="extra"/></testsuite>')
                elif failure == 'missing-case': log.write_text(log.read_text().replace('esm: PASS resource:', 'esm: FAILURE'))
                elif failure == 'duplicate-case': log.write_text(log.read_text() + 'esm: PASS resource:\n')
                elif failure == 'missing-summary': log.write_text(log.read_text().replace('Sixteen synthetic', 'Not sixteen'))
                elif failure == 'changed-input': (build / 'synthetic-esm-vfs/valid.esm').write_bytes(b'changed')
                elif failure == 'new-file': (build / 'synthetic-esm-vfs/must-not-be-created.bsa').write_bytes(b'new')
                elif failure == 'new-directory': (build / 'synthetic-esm-vfs/unexpected-directory').mkdir()
                def tool(*args, **kwargs):
                    if failure == 'missing-tool': raise FileNotFoundError('xcrun unavailable')
                    return subprocess.CompletedProcess([], 1 if failure == 'failed-tool' else 0, '', '')
                with patch.object(evidence.subprocess, 'run', side_effect=tool), self.assertRaises((OSError, ValueError, RuntimeError)):
                    evidence.host_results(build, output)
                self.assertFalse(json.loads((output / 'host-validation.json').read_text())['valid'])

    def test_host_archive_count_unexpected_or_empty_members_are_rejected(self):
        for label, (name, sources) in evidence.ARCHIVES.items():
            for failure in ('count', 'unexpected', 'alias', 'empty'):
                with self.subTest(label=label, failure=failure), tempfile.TemporaryDirectory() as temp:
                    build, output = make_build(Path(temp)); make_runtime_reports(build, output)
                    names = [Path(s).stem + '.o' for s in sources]
                    if failure == 'count': names.pop()
                    elif failure == 'unexpected': names[0] = 'unexpected.o'
                    elif failure == 'alias': names[-1] = Path(sources[0]).name + '.o'
                    (build / 'nested' / name).write_bytes(archive(names=names, replace={0: b''} if failure == 'empty' else None))
                    with patch.object(evidence.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
                            self.assertRaises(ValueError): evidence.host_results(build, output)

    def test_failure_collection_preserves_partial_logs_config_inputs_and_both_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            build, output = make_build(Path(temp)); make_runtime_reports(build, output)
            log = build / 'esm-reader/CMakeFiles/CMakeConfigureLog.yaml'
            log.parent.mkdir(parents=True); log.write_text('native compiler diagnostics\n')
            evidence.collect(build, output, 'device', 'failure')
            self.assertTrue((output / 'build-diagnostics/esm-reader/CMakeFiles/CMakeConfigureLog.yaml').is_file())
            self.assertTrue((output / 'generated/osg/Config').is_file())
            self.assertEqual(len(list((output / 'synthetic-esm-vfs').iterdir())), 14)
            for name, _ in evidence.ARCHIVES.values(): self.assertTrue((output / name).is_file())
            for row in (output / 'SHA256SUMS').read_text().splitlines():
                digest, name = row.split('  ', 1)
                self.assertEqual(digest, evidence.sha(output / name))
            self.assertEqual(json.loads((output / 'job-status.json').read_text())['validation_steps_status'], 'failure')

    def test_success_handoff_requires_both_correct_object_reports_and_matching_config_archives(self):
        for failure in ('none', 'missing-e', 'wrong-count', 'archive', 'config', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                build, output = make_build(Path(temp))
                for label, (name, _) in evidence.ARCHIVES.items():
                    data = (build / 'nested' / name).read_bytes()
                    report = evidence.previous.validate(data) if label == 'milestone-d' else validator.validate(data)
                    if failure == 'missing-e' and label == 'milestone-e': continue
                    if failure == 'wrong-count' and label == 'milestone-e': report['objects'].pop()
                    if failure == 'archive' and label == 'milestone-d': report['sha256'] = '0' * 64
                    evidence.write_json(output / 'archive-inspection' / label / 'archive-validation.json', report)
                if failure == 'config': (build / evidence.CONFIG).write_bytes(b'changed')
                if failure == 'source': (output / 'source-provenance.json').unlink()
                if failure == 'none':
                    evidence.collect(build, output, 'device', 'success')
                    self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'success')
                else:
                    with self.assertRaises((OSError, ValueError)): evidence.collect(build, output, 'device', 'success')
                    self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'failure')
                self.assertTrue((output / 'SHA256SUMS').is_file())

    def test_success_without_build_outputs_fails_with_report_and_checksums(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with self.assertRaises(evidence.EvidenceError): evidence.collect(output / 'missing', output, 'device', 'success')
            self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'failure')
            self.assertTrue((output / 'SHA256SUMS').is_file())


class WorkflowTests(unittest.TestCase):
    def test_manual_only_independent_macos_jobs_and_exact_sibling_checkouts(self):
        self.assertEqual(TEXT.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip(), 'workflow_dispatch:')
        self.assertEqual(re.findall(r'^([a-z][a-z_-]*):', TEXT, re.M), ['name', 'on', 'permissions', 'env', 'jobs'])
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-compilation'})
        for job in JOBS.values():
            self.assertIn('runs-on: macos-26', job); self.assertNotIn('needs:', job)
            blocks = re.findall(r'uses: actions/checkout@v6\n        with:\n((?:          .*\n)+)', job)
            self.assertEqual(len(blocks), 2)
            self.assertIn('ref: ${{ github.sha }}', blocks[0]); self.assertIn('path: openmw', blocks[0])
            self.assertIn('repository: OpenMW/osg', blocks[1])
            self.assertIn('ref: ' + auditor.esm_audit.OSG_REVISION, blocks[1]); self.assertIn('path: osg-pinned', blocks[1])
            for block in blocks:
                for setting in ('fetch-depth: 1', 'submodules: false', 'lfs: false', 'persist-credentials: false'):
                    self.assertIn(setting, block)
            self.assertIn('test "$GITHUB_REF" = refs/heads/ios-port', job)
            self.assertIn('test "$(git -C "$OPENMW_SOURCE" rev-parse HEAD)" = "$GITHUB_SHA"', job)
            self.assertIn('test "$(git -C "$OPENMW_ESM_OSG_SOURCE" rev-parse HEAD)" = "$OSG_REVISION"', job)

    def test_sources_and_real_nested_config_verified_before_compilation(self):
        for job in JOBS.values():
            for text in ('--osg-source "$OPENMW_ESM_OSG_SOURCE" --require-complete', 'ci_evidence.py" sources',
                         '$OPENMW_SOURCE/experiments/ios-openmw-esm/tools/ci_evidence.py" config',
                         '--build "$BUILD_DIR/esm-reader" --evidence "$EVIDENCE"'):
                self.assertIn(text, job)
            self.assertLess(job.index('audit_sources.py'), job.index('cmake -S'))
            self.assertLess(job.index('ci_evidence.py" config'), job.index('cmake --build'))
        self.assertEqual(evidence.CONFIG.as_posix(), 'esm-reader/osg-math/include/osg/Config')

    def test_host_requires_real_link_exact_ctest_sixteen_cases_and_integrity(self):
        job = JOBS['host-validation']
        for text in ('python3 -m unittest discover', '-DOPENMW_IOS_ESM_VFS_HOST_TESTS=ON', '--target openmw-esm-vfs-check',
                     '--output-on-failure --no-tests=error', "-R '^openmw-esm-vfs-runtime$'", '--output-junit',
                     "grep -F 'Sixteen synthetic ESM/VFS cases passed with unchanged input tree.'", 'ci_evidence.py" host-results'):
            self.assertIn(text, job)
        fixture = (ROOT / 'tools/fixtures.py').read_text()
        self.assertIn('snapshot(directory) != before', fixture)
        self.assertIn('result.returncode != 0 or marker not in result.stdout', fixture)

    def test_device_has_separate_strict_fifteen_and_six_object_inspections(self):
        job = JOBS['iphoneos-compilation']
        for text in ('-DOPENMW_IOS_ESM_VFS_HOST_TESTS=OFF', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES=arm64',
                     '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0', 'xcrun --sdk iphoneos --show-sdk-path',
                     '--target openmw-ios-esm-vfs', 'CODE_SIGNING_ALLOWED=NO',
                     'experiments/ios-openmw-esm/tools/validate_esm_archive.py', 'validate_esm_vfs_archive.py',
                     '--evidence "$EVIDENCE/archive-inspection/milestone-d"', '--evidence "$EVIDENCE/archive-inspection/milestone-e"'):
            self.assertIn(text, job)
        self.assertEqual(job.count("if: ${{ !cancelled() && steps.archives.outcome == 'success' }}"), 2)
        self.assertNotIn('ctest --test-dir', job)
        for forbidden in ('--allow-multiple-definition', 'force_load', 'all_load'):
            self.assertNotIn(forbidden, TEXT)

    def test_both_success_and_failure_artifacts_and_no_downloads_or_ignored_failures(self):
        for kind, job in zip(('host', 'device'), JOBS.values()):
            self.assertIn('ci_evidence.py" collect --kind ' + kind, job)
            self.assertIn('JOB_STATUS: ${{ job.status }}', job)
            self.assertIn('if: always()\n        env:', job)
            self.assertIn('uses: actions/upload-artifact@v6\n        if: always()', job)
            self.assertIn('path: ${{ runner.temp }}/openmw-esm-vfs-' + kind + '-evidence/', job)
            self.assertIn('if-no-files-found: error', job)
            self.assertIn('SHA256SUMS', job)
            self.assertLess(job.index('Initialize failure evidence'), job.index('uses: actions/checkout'))
        for bad in ('continue-on-error', '|| true', 'brew install', 'pip install', 'curl ', 'wget ', 'git clone'):
            self.assertNotIn(bad, TEXT)
        for block in scripts(TEXT): self.assertIn('set -euo pipefail', block)

    def test_all_bash_blocks_and_embedded_python_parse(self):
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else None)
        if not bash or not Path(bash).is_file(): self.skipTest('Existing Bash unavailable; no installation')
        blocks = list(scripts(TEXT))
        self.assertEqual(len(blocks), 17)
        embedded = 0
        for block in blocks:
            for python in re.findall(r"python3 - <<'PY'\n(.*?)\nPY", block, re.S):
                ast.parse(python); embedded += 1
            with tempfile.TemporaryDirectory() as temp:
                script = Path(temp) / 'workflow.sh'; script.write_bytes(block.encode('utf-8'))
                result = subprocess.run([bash, '-n', script.as_posix()], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(embedded, 2)


if __name__ == '__main__':
    unittest.main()
