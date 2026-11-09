"""Offline workflow/evidence/Mach-O contracts; synthetic metadata is not Apple compilation evidence."""
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
import validate_esm_archive as validator

ROOT, REPO = auditor.ROOT, auditor.REPO
OSG = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
TEXT = (REPO / '.github/workflows/ios-openmw-esm.yml').read_text(encoding='utf-8')
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
    def test_exact_fifteen_sources_names_checksums_and_unchanged_core_contract(self):
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(tuple(manifest['sources']), validator.SOURCES)
        self.assertEqual(len(validator.SOURCES), 15)
        self.assertEqual(len(validator.core.SOURCES), 5)
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
        for data in (b'', b'not ar', archive()[:-1], archive(replace={8: b''})):
            with self.subTest(data=data[:20]), self.assertRaises(validator.core.ValidationError): validator.validate(data)

    def test_all_fifteen_objects_reject_other_platforms_architectures_and_minimums(self):
        bad = [object_file(target=p) for p in (1, 3, 4, 6, 7, 8, 11, 12)]
        bad += [object_file(cpu=0x01000007), object_file(subtype=2), object_file(kind=6),
                object_file(minimum=17 << 16), object_file(minimum=(18 << 16) | (1 << 8)), object_file(minimum=19 << 16)]
        for index in range(15):
            for payload in bad:
                with self.subTest(index=index, payload=payload[:20]), self.assertRaises(validator.core.ValidationError):
                    validator.validate(archive(replace={index: payload}))

    def test_malformed_missing_legacy_duplicate_metadata_and_bitcode_rejected(self):
        build = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 26 << 16, 0)
        bad = [object_file(commands=[]), object_file(commands=[build, build]), object_file()[:-1], b'BC\xc0\xde' + bytes(60),
               object_file(commands=[struct.pack('<4I', 0x25, 16, 18 << 16, 26 << 16)]),
               object_file(commands=[struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 1)])]
        for payload in bad:
            with self.assertRaises(validator.core.ValidationError): validator.validate(archive(replace={14: payload}))

    def test_native_cli_keeps_per_object_tools_and_failure_reports(self):
        for target in (2, 7):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / 'device.a'; output = root / 'inspection'
                source.write_bytes(archive(replace={14: object_file(target=target)}))
                def run(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'raw metadata\n', '')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(output)]), \
                        patch.object(validator.platform, 'system', return_value='Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run) as mocked, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 0 if target == 2 else 1)
                report = json.loads((output / 'archive-validation.json').read_text())
                self.assertEqual(report['valid'], target == 2)
                self.assertEqual(len(list((output / 'objects').glob('*.otool.txt'))), 15)
                commands = [call.args[0] for call in mocked.call_args_list]
                self.assertEqual(sum('otool' in cmd and '-l' in cmd for cmd in commands), 15)
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


class EvidenceTests(unittest.TestCase):
    def test_source_snapshot_contains_complete_raw_canonical_and_validation_manifests(self):
        if not OSG.is_dir(): self.skipTest('Genuine pinned OSG checkout unavailable locally')
        sha = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GITHUB_SHA': sha}):
            output = Path(directory)
            evidence.source_snapshot(OSG, output)
            report = json.loads((output / 'source-provenance.json').read_text())
            self.assertEqual(report['openmw_commit'], sha)
            self.assertEqual((report['openmw_files'], report['osg_files']), (53, 7))
            for name in ('source-sha256.txt', 'source-sha256-lf.txt'):
                self.assertEqual(len((output / name).read_text().splitlines()), 60)
            self.assertTrue((output / 'OSG-LICENSE.txt').is_file())
            self.assertTrue((output / 'validation-input-sha256.txt').is_file())
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GITHUB_SHA': '0' * 40}), self.assertRaises(evidence.EvidenceError):
            evidence.source_snapshot(OSG, Path(directory))

    def test_genuine_config_verification_accepts_exact_settings_and_rejects_missing_blank_or_changed(self):
        if not OSG.is_dir(): self.skipTest('Genuine pinned OSG checkout unavailable locally')
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        template = (OSG / 'src/osg/Config.in').read_text(encoding='utf-8')
        lines = []
        for line in template.splitlines():
            if line.startswith('#cmakedefine '):
                key = line.split()[1]
                line = '#define ' + key if manifest['osg_config_defines'][key] else '/* #undef ' + key + ' */'
            lines.append(line)
        valid = '\n'.join(lines) + '\n'  # Config-verifier input only, not a native configure/build claim.
        for kind in ('valid', 'missing', 'blank', 'changed'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); build = root / 'build'; output = root / 'evidence'; output.mkdir()
                path = build / evidence.CONFIG
                if kind != 'missing':
                    path.parent.mkdir(parents=True)
                    path.write_text('' if kind == 'blank' else valid + ('// changed\n' if kind == 'changed' else ''))
                if kind == 'valid':
                    evidence.verify_config(OSG, build, output)
                    report = json.loads((output / 'config-validation.json').read_text())
                    self.assertTrue(report['valid'])
                    self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                else:
                    with self.assertRaises(evidence.EvidenceError): evidence.verify_config(OSG, build, output)
                    self.assertFalse(json.loads((output / 'config-validation.json').read_text())['valid'])

    def test_archive_location_is_unique_nonempty_and_uses_recorded_path(self):
        for kind in ('valid', 'missing', 'empty', 'ambiguous'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); output = root / 'out'; output.mkdir(); build = root / 'build'
                path = build / 'Release-iphoneos' / evidence.ARCHIVE
                if kind != 'missing':
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b'' if kind == 'empty' else archive())
                if kind == 'ambiguous': (build / evidence.ARCHIVE).write_bytes(archive())
                if kind == 'valid':
                    self.assertTrue(evidence.locate_archive(build, output, True))
                    self.assertEqual((output / evidence.ARCHIVE).read_bytes(), archive())
                else:
                    with self.assertRaises(evidence.EvidenceError): evidence.locate_archive(build, output, True)
                self.assertTrue((output / 'archive-location.json').is_file())

    def test_failure_collection_retains_nested_diagnostics_inputs_config_archive_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); build = root / 'build'; output = root / 'out'; output.mkdir()
            log = build / 'nested/CMakeFiles/CMakeConfigureLog.yaml'; log.parent.mkdir(parents=True); log.write_text('failure\n')
            config = build / evidence.CONFIG; config.parent.mkdir(parents=True); config.write_text('partial failed configuration\n')
            inputs = build / 'synthetic-esm'; inputs.mkdir(); (inputs / 'original.esm').write_bytes(b'original test bytes')
            (build / evidence.ARCHIVE).write_bytes(b'partial archive')
            evidence.collect(build, output, 'device', 'failure')
            self.assertTrue((output / 'build-diagnostics/nested/CMakeFiles/CMakeConfigureLog.yaml').is_file())
            self.assertTrue((output / 'generated/osg/Config').is_file())
            self.assertTrue((output / 'synthetic-esm/original.esm').is_file())
            for row in (output / 'SHA256SUMS').read_text().splitlines():
                digest, relative = row.split('  ', 1)
                self.assertEqual(digest, hashlib.sha256((output / relative).read_bytes()).hexdigest())
            self.assertEqual(json.loads((output / 'job-status.json').read_text())['validation_steps_status'], 'failure')

    def test_success_collection_missing_outputs_fails_instead_of_hiding_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'out'; output.mkdir()
            with self.assertRaises(evidence.EvidenceError): evidence.collect(root / 'missing-build', output, 'device', 'success')
            self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'failure')
            self.assertTrue((output / 'SHA256SUMS').is_file())

    def test_successful_device_handoff_requires_matching_config_and_archive_hashes(self):
        for mutation in ('none', 'config', 'archive'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); build = root / 'build'; output = root / 'out'; output.mkdir(); build.mkdir()
                data = archive()
                (build / evidence.ARCHIVE).write_bytes(data)
                config = build / evidence.CONFIG; config.parent.mkdir(parents=True); config.write_bytes(b'verified config fixture')
                evidence.write_json(output / 'config-validation.json', {'valid': True,
                    'sha256': hashlib.sha256(config.read_bytes()).hexdigest() if mutation != 'config' else '0' * 64})
                evidence.write_json(output / 'source-provenance.json', {'scope': 'Evidence-handoff unit test, not native proof'})
                report = validator.validate(data)
                if mutation == 'archive': report['sha256'] = '0' * 64
                evidence.write_json(output / 'archive-inspection/archive-validation.json', report)
                if mutation == 'none':
                    evidence.collect(build, output, 'device', 'success')
                    self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'success')
                else:
                    with self.assertRaises(evidence.EvidenceError): evidence.collect(build, output, 'device', 'success')
                    self.assertEqual(json.loads((output / 'job-status.json').read_text())['evidence_collection'], 'failure')


class WorkflowTests(unittest.TestCase):
    def test_manual_only_independent_jobs_and_exact_sibling_checkouts(self):
        self.assertEqual(TEXT.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip(), 'workflow_dispatch:')
        self.assertEqual(re.findall(r'^([a-z][a-z_-]*):', TEXT, re.M), ['name', 'on', 'permissions', 'env', 'jobs'])
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-compilation'})
        self.assertIn('OPENMW_SOURCE: ${{ github.workspace }}/openmw', TEXT)
        self.assertIn('OPENMW_ESM_OSG_SOURCE: ${{ github.workspace }}/osg-pinned', TEXT)
        for job in JOBS.values():
            self.assertIn('runs-on: macos-26', job); self.assertNotIn('needs:', job)
            blocks = re.findall(r'uses: actions/checkout@v6\n        with:\n((?:          .*\n)+)', job)
            self.assertEqual(len(blocks), 2)
            self.assertIn('ref: ${{ github.sha }}', blocks[0]); self.assertIn('path: openmw', blocks[0])
            self.assertIn('repository: OpenMW/osg', blocks[1]); self.assertIn('ref: ' + auditor.OSG_REVISION, blocks[1])
            self.assertIn('path: osg-pinned', blocks[1])
            for block in blocks:
                for setting in ('fetch-depth: 1', 'submodules: false', 'lfs: false', 'persist-credentials: false'):
                    self.assertIn(setting, block)
            self.assertIn('test "$GITHUB_REF" = refs/heads/ios-port', job)
            self.assertIn('test "$(git -C "$OPENMW_SOURCE" rev-parse HEAD)" = "$GITHUB_SHA"', job)

    def test_both_jobs_verify_sources_and_generated_config_before_build(self):
        for job in JOBS.values():
            for text in ('--osg-source "$OPENMW_ESM_OSG_SOURCE" --require-complete', 'ci_evidence.py" sources',
                         'ci_evidence.py" config', '-DOPENMW_ESM_OSG_SOURCE="$OPENMW_ESM_OSG_SOURCE"'):
                self.assertIn(text, job)
            self.assertLess(job.index('audit_sources.py'), job.index('cmake -S'))
            self.assertLess(job.index('ci_evidence.py" config'), job.index('cmake --build'))

    def test_host_requires_complete_suite_real_link_exact_ctest_and_ten_case_marker(self):
        job = JOBS['host-validation']
        for text in ('python3 -m unittest discover -s "$OPENMW_SOURCE/$EXPERIMENT/tools"', '-DOPENMW_IOS_ESM_HOST_TESTS=ON',
                     '--target openmw-esm-check', '--config Release --verbose', 'xcrun --sdk macosx --find clang++',
                     '--output-on-failure --no-tests=error', "-R '^openmw-esm-runtime$'",
                     "grep -F 'Ten synthetic ESM cases passed with unchanged input tree.'"):
            self.assertIn(text, job)
        fixture = (ROOT / 'tools/fixtures.py').read_text(encoding='utf-8')
        self.assertIn('snapshot(directory) != before or missing.exists()', fixture)
        self.assertIn('result.returncode != 0 or marker not in result.stdout', fixture)

    def test_device_only_builds_approved_target_and_requires_strict_archive_validation(self):
        job = JOBS['iphoneos-compilation']
        for text in ('-DOPENMW_IOS_ESM_HOST_TESTS=OFF', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES=arm64',
                     '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0', '-DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)"',
                     '--target openmw-ios-esm-reader', 'CODE_SIGNING_ALLOWED=NO', 'ci_evidence.py" archive',
                     'validate_esm_archive.py', '--archive "$EVIDENCE/libopenmw-ios-esm-reader.a" --evidence "$EVIDENCE/archive-inspection"'):
            self.assertIn(text, job)
        self.assertLess(job.index('ci_evidence.py" archive'), job.index('validate_esm_archive.py'))

    def test_evidence_survives_checkout_and_later_failures_in_both_jobs(self):
        for name, job in JOBS.items():
            kind = 'host' if name == 'host-validation' else 'device'
            self.assertLess(job.index('mkdir -p "$EVIDENCE"'), job.index('actions/checkout@v6'))
            self.assertIn('EVIDENCE="$RUNNER_TEMP/openmw-esm-' + kind + '-evidence"', job)
            self.assertIn('ci_evidence.py" collect --kind ' + kind, job)
            self.assertEqual(job.count('if: always()'), 2)
            upload = job.split('- uses: actions/upload-artifact@v6', 1)[1]
            for text in ('if: always()', 'if-no-files-found: error', 'github.run_attempt',
                         'path: ${{ runner.temp }}/openmw-esm-' + kind + '-evidence/'):
                self.assertIn(text, upload)
            for text in ('xcodebuild -version', 'cmake --version', 'xcrun --sdk iphoneos --show-sdk-version',
                         'JOB_STATUS: ${{ job.status }}', 'SHA256SUMS', 'job-status.json'):
                self.assertIn(text, job)

    def test_no_unpinned_downloads_graphics_or_silenced_failures(self):
        for forbidden in ('brew install', 'pip install', 'curl ', 'wget ', 'FetchContent', 'build_angle.py',
                          'prepare_osg.py', 'continue-on-error', '|| true', '-Wno-', '[run-osg]', 'C:/Users'):
            self.assertNotIn(forbidden, TEXT)

    def test_embedded_python_and_all_bash_blocks_parse_offline(self):
        blocks = list(scripts(TEXT)); self.assertEqual(len(blocks), 14)
        python = []
        for script in blocks:
            self.assertIn('set -euo pipefail', script)
            python += re.findall(r"python3 - <<'PY'\n(.*?)^PY$", script, re.M | re.S)
        self.assertEqual(len(python), 2)
        for code in python: ast.parse(code)
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').is_file() else None)
        if not bash: self.skipTest('Existing Bash unavailable; no downloads for shell checking')
        for i, script in enumerate(blocks):
            result = subprocess.run([bash, '-n'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f'Block {i}: {result.stderr}')


if __name__ == '__main__':
    unittest.main()
