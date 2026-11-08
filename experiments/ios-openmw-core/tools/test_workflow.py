"""Offline contracts for the dedicated manual workflow; no YAML package required."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from test_core import SOURCES
from validate_archive import SOURCES as VALIDATED_SOURCES

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT.parents[1] / '.github/workflows/ios-openmw-core.yml'
TEXT = WORKFLOW.read_text(encoding='utf-8')
JOBS = dict(re.findall(r'^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)',
                       TEXT.split('\njobs:\n', 1)[1], re.M | re.S))


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


class WorkflowTests(unittest.TestCase):
    def test_manual_dispatch_is_the_only_trigger(self):
        events = TEXT.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(events.strip(), 'workflow_dispatch:')
        self.assertEqual(re.findall(r'^([a-z][a-z_-]*):', TEXT, re.M), ['name', 'on', 'permissions', 'env', 'jobs'])
        self.assertNotRegex(TEXT, r'^\s+(push|pull_request|schedule|workflow_call):')
        self.assertEqual(set(JOBS), {'host-validation', 'iphoneos-compilation'})
        self.assertIn('contents: read', TEXT)
        for job in JOBS.values():
            self.assertIn('runs-on: macos-26', job)
            self.assertIn('persist-credentials: false', job)
            self.assertIn('test "$GITHUB_REF" = refs/heads/ios-port', job)
            self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', job)
            self.assertNotIn('needs:', job)

    def test_host_requires_real_cmake_build_and_ctest_execution(self):
        host = JOBS['host-validation']
        for text in ('-DOPENMW_IOS_CORE_HOST_TESTS=ON', '--target openmw-data-core-check',
                     'ctest --test-dir "$BUILD_DIR" -C Release', '--output-on-failure --no-tests=error',
                     "-R '^openmw-data-core-runtime$'", 'xcrun --sdk macosx --find clang++'):
            self.assertIn(text, host)
        self.assertLess(host.index('cmake -S'), host.index('cmake --build'))
        self.assertLess(host.index('cmake --build'), host.index('ctest --test-dir'))

    def test_device_producer_consumer_and_validator_sources_agree(self):
        device = JOBS['iphoneos-compilation']
        for text in ('-DOPENMW_IOS_CORE_HOST_TESTS=OFF', '-DCMAKE_SYSTEM_NAME=iOS',
                     '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=18.0',
                     '-DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)"',
                     '--target openmw-ios-data-core', 'CODE_SIGNING_ALLOWED=NO',
                     'archive="$BUILD_DIR/Release-iphoneos/libopenmw-ios-data-core.a"',
                     'test -s "$archive"', 'cp "$archive" "$EVIDENCE/libopenmw-ios-data-core.a"',
                     '--archive "$EVIDENCE/libopenmw-ios-data-core.a" --evidence "$EVIDENCE/archive-inspection"'):
            self.assertIn(text, device)
        self.assertEqual(tuple(SOURCES), VALIDATED_SOURCES)
        self.assertLess(device.index('cmake --build'), device.index('tools/validate_archive.py'))

    def test_evidence_survives_failure_in_both_jobs(self):
        for name, job in JOBS.items():
            with self.subTest(job=name):
                self.assertLess(job.index('mkdir -p "$EVIDENCE"'), job.index('actions/checkout@v6'))
                for text in ('git rev-parse HEAD', 'xcodebuild -version', 'cmake --version',
                             'xcrun --sdk iphoneos --show-sdk-version', 'source-sha256.txt',
                             'CMakeCache.txt', 'CMakeConfigureLog.yaml', 'SHA256SUMS', 'OpenMW-LICENSE.txt'):
                    self.assertIn(text, job)
                upload = job.split('- uses: actions/upload-artifact@v6', 1)[1]
                self.assertIn('if: always()', upload)
                kind = 'host' if name == 'host-validation' else 'device'
                self.assertIn('path: ${{ runner.temp }}/openmw-core-' + kind + '-evidence/', upload)
                self.assertIn('EVIDENCE="$RUNNER_TEMP/openmw-core-' + kind + '-evidence"', job)
                self.assertIn('"$EVIDENCE" "$BUILD_DIR" >> "$GITHUB_ENV"', job)
                self.assertIn('if-no-files-found: error', upload)
                self.assertIn('github.run_attempt', upload)
                self.assertEqual(job.count('if: always()'), 2)
        for script in scripts(TEXT):
            self.assertIn('set -euo pipefail', script)

    def test_no_external_engine_graph_or_compilation_bypass(self):
        for forbidden in ('ios-osg-smoke', 'ios-angle-smoke', 'build_angle.py', 'prepare_osg.py',
                          'brew install', 'pip install', 'curl ', 'wget ', 'continue-on-error',
                          '|| true', '-Wno-', '-include ', 'FetchContent', '[run-osg]'):
            self.assertNotIn(forbidden, TEXT)

    def test_all_workflow_bash_blocks_parse_without_execution(self):
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').exists() else None)
        if not bash:
            self.skipTest('Bash unavailable; workflow scripts were not syntax-checked')
        blocks = list(scripts(TEXT))
        self.assertEqual(len(blocks), 12)
        for index, script in enumerate(blocks):
            result = subprocess.run([bash, '-n'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f'Block {index}: {result.stderr}')


if __name__ == '__main__':
    unittest.main()
