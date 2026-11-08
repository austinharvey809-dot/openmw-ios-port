"""Offline BSA archive and workflow regressions; synthetic Mach-O is not native evidence."""
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

import fixtures
import validate_bsa_archive as validator

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT.parents[1] / '.github/workflows/ios-openmw-bsa.yml'
TEXT = WORKFLOW.read_text(encoding='utf-8')
JOBS = dict(re.findall(r'^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)',
                       TEXT.split('\njobs:\n', 1)[1], re.M | re.S))


def object_file(cpu=0x0100000C, subtype=0, target=2, minimum=18 << 16, kind=1):
    return (struct.pack('<8I', 0xFEEDFACF, cpu, subtype, kind, 1, 24, 0, 0)
            + struct.pack('<6I', 0x32, 24, target, minimum, 26 << 16, 0))


def archive(names=('bsafile.o',), payload=None):
    result = b'!<arch>\n'
    for name in names:
        encoded = name.encode() + b'\0\0'
        body = encoded + (object_file() if payload is None else payload)
        label = '#1/' + str(len(encoded))
        result += (f'{label:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}`\n').encode()
        result += body + (b'\n' if len(body) % 2 else b'')
    return result


def scripts(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != 'run: |':
            continue
        indent = len(line) - len(line.lstrip())
        body = []
        for value in lines[index + 1:]:
            if value.strip() and len(value) - len(value.lstrip()) <= indent:
                break
            body.append(value[indent + 2:] if value.strip() else '')
        yield '\n'.join(body) + '\n'


def python_blocks(text):
    for script in scripts(text):
        yield from re.findall(r"python3 - <<'PY'[^\n]*\n(.*?)^PY$", script, re.M | re.S)


class BSAArchiveValidationTests(unittest.TestCase):
    def test_exact_single_source_device_archive_and_checksums(self):
        for name in ('bsafile.o', 'bsafile.cpp.o'):
            data = archive((name,))
            report = validator.validate(data)
            self.assertTrue(report['valid'])
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(len(report['objects']), 1)
            item = report['objects'][0]
            self.assertEqual(item['source'], 'components/bsa/bsafile.cpp')
            self.assertEqual(item['sha256'], hashlib.sha256(object_file()).hexdigest())
            self.assertEqual((item['architecture'], item['platform'], item['minimum_os']), ('arm64', 'IOS', '18.0'))

    def test_missing_extra_wrong_and_duplicate_objects_are_rejected(self):
        for data in (archive(()), archive(('bsafile.o', 'other.o')), archive(('other.o',)),
                     archive(('bsafile.o', 'bsafile.o')), archive(('bsafile.o', 'bsafile.cpp.o')),
                     archive(('../escape.o',)), b'not-an-archive'):
            with self.subTest(data=data[:30]), self.assertRaises(validator.core.ValidationError):
                validator.validate(data)

    def test_arm64_is_not_enough_platform_deployment_and_object_type_are_strict(self):
        bad = [object_file(target=p) for p in (1, 3, 4, 6, 7, 8, 11, 12)]
        bad += [object_file(cpu=0x01000007), object_file(subtype=2), object_file(kind=6),
                object_file(minimum=17 << 16), object_file(minimum=(18 << 16) | (1 << 8)),
                object_file(minimum=19 << 16), object_file()[:-1], b'BC\xc0\xde' + bytes(60)]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(validator.core.ValidationError):
                validator.validate(archive(payload=payload))

    def test_core_exact_five_contract_is_separate_and_unchanged(self):
        self.assertEqual(len(validator.core.SOURCES), 5)
        self.assertNotIn(validator.SOURCE, validator.core.SOURCES)
        with self.assertRaises(validator.core.ValidationError):
            validator.core.validate(archive())
        data = archive(tuple(Path(source).stem + '.o' for source in validator.core.SOURCES))
        self.assertEqual(len(validator.core.validate(data)['objects']), 5)
        with self.assertRaises(validator.core.ValidationError):
            validator.validate(data)

    def test_cli_records_tools_raw_objects_and_failure_metadata(self):
        for target in (2, 7):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, output = root / 'device.a', root / 'inspection'
                source.write_bytes(archive(payload=object_file(target=target)))
                def run(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'raw tool evidence\n', '')
                with patch('sys.argv', ['validate_bsa_archive', '--archive', str(source), '--evidence', str(output)]), \
                        patch.object(validator.platform, 'system', return_value='Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run) as mocked, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 0 if target == 2 else 1)
                report = json.loads((output / 'archive-validation.json').read_text())
                self.assertEqual(report['valid'], target == 2)
                self.assertEqual(len(list((output / 'objects').glob('*.otool.txt'))), 1)
                commands = [call.args[0] for call in mocked.call_args_list]
                self.assertIn(['xcrun', 'lipo', str(source), '-verify_arch', 'arm64'], commands)
                self.assertIn(['xcrun', 'ar', '-t', str(source)], commands)
                self.assertEqual(sum('otool' in c and '-l' in c for c in commands), 1)
                if target != 2:
                    self.assertIn('not iOS device', report['error'])

    def test_cli_reports_wrong_host_and_missing_tools_without_substitution(self):
        for host in ('Windows', 'Darwin'):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'device.a'
                source.write_bytes(archive())
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(root / 'out')]), \
                        patch.object(validator.platform, 'system', return_value=host), \
                        patch.object(validator.subprocess, 'run', side_effect=FileNotFoundError('Missing xcrun')) as mocked, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 1)
                self.assertFalse(json.loads((root / 'out/archive-validation.json').read_text())['valid'])
                self.assertEqual(mocked.call_count, 0 if host == 'Windows' else 1)

    def test_cli_does_not_accept_failed_tools_or_an_extra_archive_architecture(self):
        for failure in ('tool-error', 'extra-architecture'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, output = root / 'device.a', root / 'inspection'
                source.write_bytes(archive())
                def run(command, **kwargs):
                    if failure == 'tool-error':
                        return subprocess.CompletedProcess(command, 1, '', 'inspection failed\n')
                    return subprocess.CompletedProcess(command, 0, 'arm64 x86_64\n' if '-archs' in command else '', '')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(output)]), \
                        patch.object(validator.platform, 'system', return_value='Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 1)
                report = json.loads((output / 'archive-validation.json').read_text())
                self.assertFalse(report['valid'])
                self.assertTrue((output / 'archive-tools.log').is_file())


class WorkflowTests(unittest.TestCase):
    def test_manual_only_independent_jobs_and_established_runner(self):
        events = TEXT.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(events.strip(), 'workflow_dispatch:')
        self.assertEqual(re.findall(r'^([a-z][a-z_-]*):', TEXT, re.M), ['name', 'on', 'permissions', 'env', 'jobs'])
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-compilation'})
        self.assertIn('contents: read', TEXT)
        for job in JOBS.values():
            for expected in ('runs-on: macos-26', 'shell: bash', 'persist-credentials: false',
                             'test "$GITHUB_REF" = refs/heads/ios-port',
                             'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"'):
                self.assertIn(expected, job)
            self.assertNotIn('needs:', job)

    def test_host_requires_genuine_build_and_all_eight_unchanged_inputs(self):
        job = JOBS['host-validation']
        for expected in ('-DOPENMW_IOS_BSA_HOST_TESTS=ON', '--target openmw-bsa-check',
                         'xcrun --sdk macosx --find clang++', 'ctest --test-dir "$BUILD_DIR" -C Release --verbose',
                         '--output-on-failure --no-tests=error', "-R '^openmw-bsa-runtime$'",
                         "grep -F 'Eight synthetic BSA cases passed with unchanged input bytes.'",
                         'python3 -m unittest discover -s "$EXPERIMENT/tools"', 'Testing/Temporary/LastTest.log'):
            self.assertIn(expected, job)
        self.assertEqual(len(fixtures.cases()), 8)
        self.assertLess(job.index('cmake -S'), job.index('cmake --build'))
        self.assertLess(job.index('cmake --build'), job.index('ctest --test-dir'))
        fixture = (ROOT / 'tools/fixtures.py').read_text(encoding='utf-8')
        self.assertIn('hashlib.sha256(path.read_bytes()).hexdigest() != before', fixture)

    def test_device_build_and_separate_strict_archive_consumers(self):
        job = JOBS['iphoneos-compilation']
        for expected in ('-DOPENMW_IOS_BSA_HOST_TESTS=OFF', '-DCMAKE_SYSTEM_NAME=iOS',
                         '-DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)"',
                         '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0',
                         '--target openmw-ios-bsa-reader', 'CODE_SIGNING_ALLOWED=NO',
                         'python3 "$EXPERIMENT/tools/validate_bsa_archive.py"',
                         '--archive "$EVIDENCE/libopenmw-ios-bsa-reader.a" --evidence "$EVIDENCE/bsa-inspection"',
                         'python3 "$CORE/tools/validate_archive.py"',
                         '--archive "$EVIDENCE/libopenmw-ios-data-core.a" --evidence "$EVIDENCE/core-inspection"'):
            self.assertIn(expected, job)
        # A BSA validator failure must not prevent independent core inspection.
        condition = "if: ${{ !cancelled() && steps.compile.outcome == 'success' && steps.archives.outcome == 'success' }}"
        self.assertEqual(job.count(condition), 2)
        cmake = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('add_library(openmw-ios-bsa-reader STATIC', cmake)
        self.assertIn('PUBLIC openmw-ios-data-core', cmake)

    def test_device_locator_rejects_missing_empty_or_ambiguous_producers(self):
        locator, = [block for block in python_blocks(TEXT) if 'COMPILE_OUTCOME' in block]
        for variant in ('valid', 'missing', 'empty', 'duplicate', 'failed-compile'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build, evidence = root / 'build', root / 'evidence'
                evidence.mkdir()
                build.mkdir()
                bsa, core = 'libopenmw-ios-bsa-reader.a', 'libopenmw-ios-data-core.a'
                (build / bsa).write_bytes(b'archive' if variant != 'empty' else b'')
                if variant not in ('missing', 'failed-compile'):
                    (build / core).write_bytes(b'core')
                if variant == 'duplicate':
                    (build / 'other').mkdir()
                    (build / 'other' / bsa).write_bytes(b'ambiguous')
                env = {'BUILD_DIR': str(build), 'EVIDENCE': str(evidence),
                       'COMPILE_OUTCOME': 'failure' if variant == 'failed-compile' else 'success'}
                with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                    if variant in ('missing', 'empty', 'duplicate'):
                        with self.assertRaises(SystemExit):
                            exec(compile(locator, '<archive-locator>', 'exec'), {})
                    else:
                        exec(compile(locator, '<archive-locator>', 'exec'), {})
                self.assertTrue((evidence / 'device-archive-paths.json').is_file())
                if variant == 'valid':
                    self.assertEqual((evidence / bsa).read_bytes(), b'archive')
                    self.assertEqual((evidence / core).read_bytes(), b'core')
                if variant in ('empty', 'duplicate'):
                    self.assertFalse((evidence / bsa).exists())

    def test_failure_artifacts_and_provenance_are_always_preserved(self):
        for name, job in JOBS.items():
            kind = 'host' if name == 'host-validation' else 'device'
            self.assertLess(job.index('mkdir -p "$EVIDENCE"'), job.index('actions/checkout@v6'))
            for expected in ('xcode-select -p', 'xcodebuild -version', 'cmake --version',
                             'xcrun --sdk iphoneos --show-sdk-version', 'git rev-parse HEAD',
                             'source-sha256.txt', 'CMakeCache.txt', 'CMakeConfigureLog.yaml',
                             'SHA256SUMS', 'OpenMW-LICENSE.txt', 'job-status.txt', 'set -x'):
                self.assertIn(expected, job)
            self.assertIn('EVIDENCE="$RUNNER_TEMP/openmw-bsa-' + kind + '-evidence"', job)
            upload = job.split('- uses: actions/upload-artifact@v6', 1)[1]
            for expected in ('if: always()', 'if-no-files-found: error', 'github.run_attempt',
                             'path: ${{ runner.temp }}/openmw-bsa-' + kind + '-evidence/'):
                self.assertIn(expected, upload)
            self.assertEqual(job.count('if: always()'), 2 if kind == 'host' else 3)

    def test_no_graphics_dependencies_downloads_or_validation_bypasses(self):
        for forbidden in ('ios-osg-smoke', 'ios-angle-smoke', 'prepare_osg', 'build_angle',
                          'brew install', 'pip install', 'curl ', 'wget ', 'continue-on-error',
                          '|| true', '-Wno-', '-include ', 'FetchContent', '[run-osg]', 'SOURCES ='):
            self.assertNotIn(forbidden, TEXT)

    def test_inline_python_and_bash_syntax_without_execution(self):
        blocks = list(scripts(TEXT))
        self.assertEqual(len(blocks), 14)
        for script in blocks:
            self.assertIn('set -euo pipefail', script)
        inline = list(python_blocks(TEXT))
        self.assertEqual(len(inline), 3)
        for code in inline:
            ast.parse(code)
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').is_file() else None)
        if not bash:
            self.skipTest('Bash unavailable; shell syntax was not checked')
        for index, script in enumerate(blocks):
            result = subprocess.run([bash, '-n'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f'Block {index}: {result.stderr}')


if __name__ == '__main__':
    unittest.main()
