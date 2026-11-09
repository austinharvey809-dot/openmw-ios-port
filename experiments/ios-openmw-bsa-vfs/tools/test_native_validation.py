"""Offline workflow/Mach-O contracts. Synthetic object metadata is not native compilation evidence."""
import ast
import contextlib
import hashlib
import importlib.util
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

import validate_vfs_archive as validator

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT.parents[1] / '.github/workflows/ios-openmw-bsa-vfs.yml').read_text(encoding='utf-8')
JOBS = dict(re.findall(r'^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)',
                       TEXT.split('\njobs:\n', 1)[1], re.M | re.S))
ARCHIVES = ('libopenmw-ios-bsa-vfs.a', 'libopenmw-ios-bsa-reader.a', 'libopenmw-ios-data-core.a')


def object_file(cpu=0x0100000C, subtype=0, target=2, minimum=18 << 16, kind=1, commands=None):
    if commands is None:
        commands = [struct.pack('<6I', 0x32, 24, target, minimum, 26 << 16, 0)]
    data = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, subtype, kind, len(commands), len(data), 0, 0) + data


def archive(names=None, replace=None):
    if names is None:
        names = [Path(source).stem + '.o' for source in validator.SOURCES]
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


class ArchiveTests(unittest.TestCase):
    def test_exact_sources_names_platform_metadata_and_checksums(self):
        self.assertEqual(validator.SOURCES, ('experiments/ios-openmw-bsa-vfs/src/register_bsa.cpp',
                                           'components/toutf8/toutf8.cpp', 'components/debug/debuglog.cpp'))
        for names in (None, [Path(s).name + '.o' for s in validator.SOURCES]):
            data = archive(names=names)
            report = validator.validate(data)
            self.assertTrue(report['valid'])
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual({item['source'] for item in report['objects']}, set(validator.SOURCES))
            for item in report['objects']:
                self.assertEqual((item['architecture'], item['platform'], item['minimum_os']), ('arm64', 'IOS', '18.0'))
                self.assertEqual(item['sha256'], hashlib.sha256(object_file()).hexdigest())

    def test_empty_missing_extra_unexpected_duplicate_or_ambiguous_objects_rejected(self):
        names = [Path(s).stem + '.o' for s in validator.SOURCES]
        for variant in ([], names[:2], names + ['bsafile.o'], ['unrelated.o', *names[1:]],
                        [names[0], names[0], names[2]], [names[0], 'register_bsa.cpp.o', names[2]],
                        ['../escape.o', *names[1:]]):
            with self.subTest(names=variant), self.assertRaises(validator.core.ValidationError):
                validator.validate(archive(names=variant))
        for data in (b'', b'not an archive', archive()[:-1], archive(replace={1: b''})):
            with self.subTest(data=data[:20]), self.assertRaises(validator.core.ValidationError):
                validator.validate(data)

    def test_every_object_platform_architecture_and_minimum_are_checked(self):
        invalid = [object_file(target=p) for p in (1, 3, 4, 6, 7, 8, 11, 12)]
        invalid += [object_file(cpu=0x01000007), object_file(subtype=2), object_file(kind=6),
                    object_file(minimum=17 << 16), object_file(minimum=(18 << 16) | (1 << 8)),
                    object_file(minimum=19 << 16), b'BC\xc0\xde' + bytes(60)]
        for index in range(3):
            for payload in invalid:
                with self.subTest(index=index, payload=payload[:16]), self.assertRaises(validator.core.ValidationError):
                    validator.validate(archive(replace={index: payload}))

    def test_missing_legacy_duplicate_and_malformed_load_commands_rejected(self):
        build = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 26 << 16, 0)
        bad = [object_file(commands=[]), object_file(commands=[build, build]), object_file()[:-1],
               object_file(commands=[struct.pack('<4I', 0x25, 16, 18 << 16, 26 << 16)]),
               object_file(commands=[struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 1)])]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(validator.core.ValidationError):
                validator.validate(archive(replace={2: payload}))

    def test_previous_exact_one_and_five_contracts_remain_distinct(self):
        spec = importlib.util.spec_from_file_location('milestone_b_validation',
            ROOT.parent / 'ios-openmw-bsa/tools/validate_bsa_archive.py')
        bsa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bsa)
        self.assertEqual(len(validator.core.SOURCES), 5)
        self.assertTrue(bsa.validate(archive(names=['bsafile.o']))['valid'])
        a_data = archive(names=[Path(s).stem + '.o' for s in validator.core.SOURCES])
        self.assertEqual(len(validator.core.validate(a_data)['objects']), 5)
        with self.assertRaises(validator.core.ValidationError):
            validator.validate(a_data)
        with self.assertRaises(validator.core.ValidationError):
            validator.core.validate(archive())
        with self.assertRaises(bsa.core.ValidationError):
            bsa.validate(archive())

    def test_cli_preserves_three_raw_objects_tools_and_platform_failure_reports(self):
        for target in (2, 7):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, evidence = root / 'device.a', root / 'inspection'
                source.write_bytes(archive(replace={2: object_file(target=target)}))
                def run(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'raw inspection\n', '')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(evidence)]), \
                        patch.object(validator.platform, 'system', return_value='Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run) as mocked, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 0 if target == 2 else 1)
                report = json.loads((evidence / 'archive-validation.json').read_text())
                self.assertEqual(report['valid'], target == 2)
                self.assertEqual(len(list((evidence / 'objects').glob('*.otool.txt'))), 3)
                commands = [call.args[0] for call in mocked.call_args_list]
                self.assertIn(['xcrun', 'lipo', str(source), '-verify_arch', 'arm64'], commands)
                self.assertIn(['xcrun', 'ar', '-t', str(source)], commands)
                self.assertEqual(sum('otool' in c and '-l' in c for c in commands), 3)
                if target != 2:
                    self.assertIn('not iOS device', report['error'])

    def test_cli_missing_tools_inputs_wrong_host_arches_and_tool_failures_fail_closed(self):
        for failure in ('wrong-host', 'missing-input', 'missing-tool', 'tool-error', 'extra-architecture'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, evidence = root / 'device.a', root / 'inspection'
                if failure != 'missing-input':
                    source.write_bytes(archive())
                def run(command, **kwargs):
                    if failure == 'missing-tool':
                        raise FileNotFoundError('xcrun is missing')
                    if failure == 'tool-error':
                        return subprocess.CompletedProcess(command, 1, '', 'Tool failed\n')
                    return subprocess.CompletedProcess(command, 0, 'arm64 x86_64\n' if '-archs' in command else '', '')
                with patch('sys.argv', ['validator', '--archive', str(source), '--evidence', str(evidence)]), \
                        patch.object(validator.platform, 'system', return_value='Windows' if failure == 'wrong-host' else 'Darwin'), \
                        patch.object(validator.subprocess, 'run', side_effect=run) as mocked, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validator.main(), 1)
                self.assertFalse(json.loads((evidence / 'archive-validation.json').read_text())['valid'])
                if failure in ('wrong-host', 'missing-input'):
                    mocked.assert_not_called()


class WorkflowTests(unittest.TestCase):
    def test_only_manual_dispatch_and_independent_proven_runner_jobs(self):
        self.assertEqual(TEXT.split('\non:\n', 1)[1].split('\npermissions:', 1)[0].strip(), 'workflow_dispatch:')
        self.assertEqual(re.findall(r'^([a-z][a-z_-]*):', TEXT, re.M), ['name', 'on', 'permissions', 'env', 'jobs'])
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-compilation'})
        self.assertIn('contents: read', TEXT)
        for job in JOBS.values():
            for expected in ('runs-on: macos-26', 'shell: bash', 'persist-credentials: false',
                             'test "$GITHUB_REF" = refs/heads/ios-port',
                             'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"'):
                self.assertIn(expected, job)
            self.assertNotIn('needs:', job)

    def test_host_real_compile_link_and_exact_runtime_selector_six_case_integrity(self):
        job = JOBS['host-validation']
        for expected in ('-DOPENMW_IOS_BSA_VFS_HOST_TESTS=ON', '--target openmw-bsa-vfs-check',
                         'xcrun --sdk macosx --find clang++', '--config Release --verbose',
                         'ctest --test-dir "$BUILD_DIR" -C Release --verbose --output-on-failure --no-tests=error',
                         "-R '^openmw-bsa-vfs-runtime$'", 'python3 -m unittest discover -s "$EXPERIMENT/tools"',
                         "grep -F 'Six synthetic BSA/VFS cases passed with unchanged input tree.'",
                         '"$BUILD_DIR/Testing/Temporary/LastTest.log"'):
            self.assertIn(expected, job)
        self.assertLess(job.index('cmake -S'), job.index('cmake --build'))
        self.assertLess(job.index('cmake --build'), job.index('ctest --test-dir'))
        code = (ROOT / 'tools/fixtures.py').read_text(encoding='utf-8')
        cases = re.search(r'    cases = \(\n(.*?)\n    \)', code, re.S)[1]
        self.assertEqual(len(re.findall(r"^        \('", cases, re.M)), 6)
        self.assertIn('snapshot(directory) != before or missing.exists()', code)
        self.assertIn('completed.returncode != 0 or marker not in completed.stdout', code)

    def test_device_settings_and_three_separate_strict_consumers(self):
        job = JOBS['iphoneos-compilation']
        for expected in ('-DOPENMW_IOS_BSA_VFS_HOST_TESTS=OFF', '-DCMAKE_SYSTEM_NAME=iOS',
                         '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0',
                         '-DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)"',
                         '--target openmw-ios-bsa-vfs', 'CODE_SIGNING_ALLOWED=NO'):
            self.assertIn(expected, job)
        for variable, script, archive_name, inspection in (
            ('EXPERIMENT', 'validate_vfs_archive.py', ARCHIVES[0], 'vfs-inspection'),
            ('BSA', 'validate_bsa_archive.py', ARCHIVES[1], 'bsa-inspection'),
            ('CORE', 'validate_archive.py', ARCHIVES[2], 'core-inspection')):
            self.assertIn('python3 "$' + variable + '/tools/' + script + '"', job)
            self.assertIn('--archive "$EVIDENCE/' + archive_name + '" --evidence "$EVIDENCE/' + inspection + '"', job)
        condition = "if: ${{ !cancelled() && steps.compile.outcome == 'success' }}"
        self.assertEqual(job.count(condition), 3)  # Also run after archive-location/another validation fails.
        self.assertNotIn('steps.archives.outcome', job)
        cmake = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
        for source in validator.SOURCES:
            self.assertIn('src/register_bsa.cpp' if source.endswith('register_bsa.cpp') else source, cmake)
        self.assertIn('PUBLIC openmw-ios-bsa-reader Threads::Threads', cmake)

    def test_archive_handoff_valid_nested_outputs_missing_empty_and_ambiguous_fail_closed(self):
        locator, = [block for block in python_blocks(TEXT) if 'COMPILE_OUTCOME' in block]
        variants = [('valid', 0), ('failed-compile', 0)] + [(kind, index) for kind in ('missing', 'empty', 'duplicate') for index in range(3)]
        for kind, index in variants:
            with self.subTest(kind=kind, index=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build, evidence = root / 'build', root / 'evidence'
                evidence.mkdir()
                for i, name in enumerate(ARCHIVES):
                    path = build / ('child-' + str(i)) / 'Release-iphoneos' / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if kind in ('missing', 'failed-compile') and i == index:
                        continue
                    path.write_bytes(b'' if kind == 'empty' and i == index else name.encode())
                    if kind == 'duplicate' and i == index:
                        (build / name).write_bytes(b'ambiguous')
                env = {'BUILD_DIR': str(build), 'EVIDENCE': str(evidence),
                       'COMPILE_OUTCOME': 'failure' if kind == 'failed-compile' else 'success'}
                with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                    if kind in ('missing', 'empty', 'duplicate'):
                        with self.assertRaises(SystemExit):
                            exec(compile(locator, '<archive-locator>', 'exec'), {})
                    else:
                        exec(compile(locator, '<archive-locator>', 'exec'), {})
                self.assertTrue((evidence / 'device-archive-paths.json').is_file())
                for i, name in enumerate(ARCHIVES):
                    if kind != 'valid' and i == index:
                        self.assertFalse((evidence / name).exists())
                    else:
                        self.assertEqual((evidence / name).read_bytes(), name.encode())

    def test_failure_collectors_keep_nested_logs_archives_and_valid_checksums(self):
        for name, job in JOBS.items():
            collector, = [block for block in python_blocks(job) if 'SHA256SUMS' in block]
            with self.subTest(job=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build, evidence = root / 'build', root / 'evidence'
                evidence.mkdir()
                log = build / 'bsa-reader/data-core/CMakeFiles/CMakeConfigureLog.yaml'
                log.parent.mkdir(parents=True)
                log.write_text('partial configuration failure\n')
                (evidence / 'build.log').write_text('compiler/linker failure\n')
                if name == 'host-validation':
                    for archive_name in ARCHIVES:
                        (build / archive_name).write_bytes(b'partial archive')
                with patch.dict(os.environ, {'BUILD_DIR': str(build), 'EVIDENCE': str(evidence)}):
                    exec(compile(collector, '<evidence-collector>', 'exec'), {})
                self.assertTrue((evidence / 'cmake-diagnostics/bsa-reader/data-core/CMakeFiles/CMakeConfigureLog.yaml').is_file())
                for row in (evidence / 'SHA256SUMS').read_text().splitlines():
                    digest, relative = row.split('  ', 1)
                    self.assertEqual(digest, hashlib.sha256((evidence / relative).read_bytes()).hexdigest())
                if name == 'host-validation':
                    self.assertEqual(len(json.loads((evidence / 'host-archive-paths.json').read_text())), 3)
                    self.assertTrue(all((evidence / ('host-' + n)).is_file() for n in ARCHIVES))

    def test_failure_uploads_provenance_and_artifact_paths(self):
        for name, job in JOBS.items():
            kind = 'host' if name == 'host-validation' else 'device'
            self.assertLess(job.index('mkdir -p "$EVIDENCE"'), job.index('actions/checkout@v6'))
            for expected in ('git rev-parse HEAD', 'xcode-select -p', 'xcodebuild -version', 'cmake --version',
                             'xcrun --sdk iphoneos --show-sdk-version', 'source-sha256.txt', 'components/toutf8',
                             'components/debug/debuglog.*', 'CMakeCache.txt', 'CMakeConfigureLog.yaml',
                             'SHA256SUMS', 'OpenMW-LICENSE.txt', 'job-status.txt', 'set -x'):
                self.assertIn(expected, job)
            self.assertIn('EVIDENCE="$RUNNER_TEMP/openmw-bsa-vfs-' + kind + '-evidence"', job)
            upload = job.split('- uses: actions/upload-artifact@v6', 1)[1]
            for expected in ('if: always()', 'if-no-files-found: error', 'github.run_attempt',
                             'path: ${{ runner.temp }}/openmw-bsa-vfs-' + kind + '-evidence/'):
                self.assertIn(expected, upload)
            self.assertEqual(job.count('if: always()'), 2 if kind == 'host' else 3)
        host = JOBS['host-validation']
        self.assertIn('cp -R "$BUILD_DIR/synthetic-bsa-vfs" "$EVIDENCE/synthetic-bsa-vfs"', host)

    def test_no_downloads_graphics_dependencies_or_ignored_failures(self):
        for forbidden in ('ios-osg-smoke', 'ios-angle-smoke', 'build_angle.py', 'prepare_osg.py',
                          'brew install', 'pip install', 'curl ', 'wget ', 'continue-on-error',
                          '|| true', '-Wno-', '-include ', 'FetchContent', '[run-osg]', 'SOURCES ='):
            self.assertNotIn(forbidden, TEXT)

    def test_inline_python_and_all_shell_blocks_parse_without_execution(self):
        blocks = list(scripts(TEXT))
        self.assertEqual(len(blocks), 15)
        for script in blocks:
            self.assertIn('set -euo pipefail', script)
        inline = list(python_blocks(TEXT))
        self.assertEqual(len(inline), 3)
        for code in inline:
            ast.parse(code)
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').is_file() else None)
        if not bash:
            self.skipTest('Existing Bash unavailable; shell syntax unverified')
        for index, script in enumerate(blocks):
            result = subprocess.run([bash, '-n'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f'Block {index}: {result.stderr}')


if __name__ == '__main__':
    unittest.main()
