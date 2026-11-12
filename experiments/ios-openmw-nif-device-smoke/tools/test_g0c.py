"""Offline contracts. Synthetic Mach-O/result objects are never native/device proof."""
import copy
import json
import os
from pathlib import Path
import plistlib
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from common import ROOT, REPO, G0B, OSG_REVISION, HOST_COMMIT, sha
import package_ios as package
import prepare
import verify_result


def binary(platform=2, cpu=0x0100000c, minimum=18 << 16, extra=(), dependencies=None):
    dependencies = dependencies or ['/System/Library/Frameworks/UIKit.framework/UIKit',
                                    '/System/Library/Frameworks/Foundation.framework/Foundation']
    commands = [struct.pack('<6I', 0x32, 24, platform, minimum, 26 << 16, 0)]
    for name in dependencies:
        data = name.encode() + b'\0'
        size = (24 + len(data) + 7) & ~7
        commands.append(struct.pack('<6I', 0xc, size, 24, 0, 0, 0) + data + bytes(size - 24 - len(data)))
    commands.extend(extra)
    body = b''.join(commands)
    return struct.pack('<8I', 0xfeedfacf, cpu, 0, 2, len(commands), len(body), 0, 0) + body


def result_fixture():
    manifest = json.loads((G0B / 'data/fixture-manifest.json').read_text())
    before = {p.name: {'sha256': sha(p.read_bytes()), 'size': p.stat().st_size} for p in (G0B / 'data').iterdir()}
    cases = [{'mode': mode, 'passed': True, 'exit_code': 1 if index == 5 else 0,
              'stdout': marker if index != 5 else '', 'stderr': marker if index == 5 else ''}
             for index, (mode, marker) in enumerate(zip(verify_result.MODES, verify_result.MARKERS))]
    cases[0]['stdout'] += ' records=3 roots=1 geometry=1 vertices=3 triangles=1\n'
    return {'status': 'PASS', 'genuine_parser_suite_completed': True, 'inputs_unchanged': True,
            'inputs_before': before, 'inputs_after': copy.deepcopy(before), 'decoded': dict(verify_result.COUNTS),
            'object_id': 'eIOSStatic', 'resource_key': 'meshes/test.nif',
            'resource_sha256': manifest['files']['triangle-candidate.nif']['sha256'], 'cases': cases,
            'device': {'system': 'unit-test metadata'},
            'build': {'source_commit': 'a' * 40, 'g0b_validated_commit': HOST_COMMIT,
                      'osg_revision': OSG_REVISION, 'platform_target': 'iPhoneOS-arm64',
                      'bullet_sha512': prepare.bullet.SHA512,
                      'resources_sha256': {'Fixtures/' + name: entry['sha256'] for name, entry in before.items()}}}


class SourceContracts(unittest.TestCase):
    def test_preserved_g0b_f_a_e_and_osg(self):
        osg = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
        self.assertEqual(prepare.audit(osg)['g0b_source_headers'], 59)

    def test_native_configuration_and_genuine_recipes(self):
        cmake = (ROOT / 'CMakeLists.txt').read_text()
        for token in ('CMAKE_SYSTEM_NAME STREQUAL "iOS"', 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"',
                      'CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0"', 'PUBLIC BT_USE_DOUBLE_PRECISION',
                      'PUBLIC cxx_std_20', 'nif-source-sha256.json', 'openmw-ios-esm-vfs BulletCollision LinearMath osg OpenThreads'):
            self.assertIn(token, cmake)
        adapter = (ROOT / 'cmake/osg/CMakeLists.txt').read_text()
        self.assertIn('${OPENMW_ESM_OSG_SOURCE}/src/osg"', adapter)
        self.assertIn('${OPENMW_ESM_OSG_SOURCE}/src/OpenThreads"', adapter)
        self.assertIn('OPENTHREADS_ATOMIC_USE_MUTEX ON', adapter)
        for name in prepare.GENERATED:
            self.assertIn(name, adapter)
        self.assertNotIn('FetchContent', adapter)
        self.assertNotIn('ANGLE', cmake)

    def test_exact_bullet_recipe_preserved(self):
        cmake = (G0B / 'CMakeLists.txt').read_text()
        expected = cmake[cmake.index('# Build the source'):cmake.index('set(_nif_units')]
        self.assertEqual((ROOT / 'cmake/bullet.cmake').read_text(), expected.rstrip() + '\n')

    def test_proven_reader_reused_in_process(self):
        probe = (ROOT / 'src/NifProbe.cpp').read_text()
        self.assertIn('#define main G0BParserMain', probe)
        self.assertIn('ios-openmw-nif-smoke/tests/nif_parse_check.cpp', probe)
        self.assertIn('G0BParserMain(5, argv)', probe)
        self.assertIn('std::from_chars', probe)
        self.assertIn('manager.get(VFS::Path::NormalizedView', probe)
        self.assertNotIn('system(', probe)
        for marker in verify_result.MARKERS:
            self.assertIn(marker, probe)

    def test_runtime_cannot_skip_negatives_or_input_checks(self):
        runtime = (ROOT / 'src/NifCheck.mm').read_text()
        self.assertIn('index < 6', runtime)
        self.assertIn('Check(observed.passed', runtime)
        self.assertIn('cases.count == 6', runtime)
        self.assertIn('Check([before isEqual:after]', runtime)
        self.assertLess(runtime.index('cases.count == 6'), runtime.index('result[@"status"] = @"PASS"'))
        ui = (ROOT / 'src/main.mm').read_text()
        self.assertIn('BOOL passed = saved &&', ui)
        self.assertIn('nif-smoke.json', ui)
        self.assertIn('nif-smoke.log', ui)

    def test_manual_workflow_separate_required_gates(self):
        workflow = (REPO / '.github/workflows/ios-openmw-nif-device-smoke.yml').read_text()
        self.assertEqual(workflow.split('on:\n', 1)[1].split('\npermissions:', 1)[0].strip(), 'workflow_dispatch:')
        for gate in ('g0c0', 'g0c1', 'g0c2', 'g0c3'):
            self.assertIn('id: ' + gate, workflow)
            self.assertIn('steps.' + gate + '.outcome', workflow)
        native = workflow.split('  native-device:', 1)[1]
        steps = native.split('      - name: ')[1:]
        gates = [next(step for step in steps if '        id: ' + gate + '\n' in step)
                 for gate in ('g0c0', 'g0c1', 'g0c2', 'g0c3')]
        self.assertEqual([steps.index(step) for step in gates], sorted(steps.index(step) for step in gates))
        for step in gates:
            self.assertIn('set -euo pipefail', step)
            self.assertNotIn('        if:', step)
        self.assertIn('needs: host-validation', workflow)
        self.assertIn('package_ios.py" reopen', workflow)
        self.assertNotIn('continue-on-error:', workflow)
        self.assertIn("physical_device_execution='not-performed'", workflow)


class LinkProductContracts(unittest.TestCase):
    def test_workflow_reads_cmake_target_file_and_checks_regular_executable(self):
        cmake = (ROOT / 'CMakeLists.txt').read_text()
        self.assertIn('file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g0c0-executable-$<CONFIG>.txt"', cmake)
        self.assertIn('CONTENT "$<TARGET_FILE:openmw-nif-device-link-check>\\n")', cmake)
        workflow = (REPO / '.github/workflows/ios-openmw-nif-device-smoke.yml').read_text()
        step = workflow.split('        id: g0c0\n', 1)[1].split('      - name:', 1)[0]
        self.assertIn('-DCMAKE_BUILD_TYPE=Release', workflow)
        commands = ('cmake --build "$BUILD_DIR" --target openmw-nif-device-link-check',
                    'IFS= read -r G0C0_EXECUTABLE < "$BUILD_DIR/g0c0-executable-Release.txt"',
                    'test -f "$G0C0_EXECUTABLE"', 'test ! -L "$G0C0_EXECUTABLE"',
                    'link --product "$G0C0_EXECUTABLE" --sdk "$IPHONEOS_SDK"')
        self.assertEqual([step.index(command) for command in commands], sorted(step.index(command) for command in commands))
        self.assertNotIn('--product "$BUILD_DIR/openmw-nif-device-link-check"', step)

    def test_missing_product_rejected_before_macho_inspection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(package, 'device_binary') as inspector:
            with self.assertRaisesRegex(ValueError, 'existing regular file'):
                package.inspect_link(Path(directory) / 'missing', None)
            inspector.assert_not_called()

    def test_directory_in_place_of_executable_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(package, 'device_binary') as inspector:
            with self.assertRaisesRegex(ValueError, 'existing regular file'):
                package.inspect_link(Path(directory), None)
            inspector.assert_not_called()

    def test_nested_app_executable_still_runs_real_macho_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            product = Path(directory) / 'openmw-nif-device-link-check.app/openmw-nif-device-link-check'
            product.parent.mkdir()
            data = binary()
            product.write_bytes(data)
            with patch.object(package, 'device_binary', wraps=package.device_binary) as inspector, \
                    patch.object(package.core, 'inspect_dependencies', return_value={}) as otool:
                report, _ = package.inspect_link(product, None)
                inspector.assert_called_once_with(data, None)
                otool.assert_called_once_with(product.parent, report)
            self.assertEqual(report['binaries'][product.name]['platform'], 'IOS')
            self.assertEqual(report['sha256'], sha(data))
            self.assertIn('no runtime claim', report['scope'])

    def test_existing_host_macos_file_cannot_pass_link_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            product = Path(directory) / 'host-executable'
            product.write_bytes(binary(platform=1))
            with patch.object(package.core, 'inspect_dependencies') as otool:
                with self.assertRaises((ValueError, package.core.ValidationError)):
                    package.inspect_link(product, None)
                otool.assert_not_called()


class NativeMetadataContracts(unittest.TestCase):
    def test_accepts_only_device_metadata_and_known_system_dependencies(self):
        self.assertEqual(package.device_binary(binary())[0]['platform'], 'IOS')
        name = '/System/Library/Frameworks/OpenGLES.framework/OpenGLES'
        self.assertIn(name, package.device_binary(binary(dependencies=[name]))[0]['dependencies'])

    def test_rejects_other_platform_architecture_or_minimum(self):
        for options in ({'platform': 1}, {'platform': 7}, {'cpu': 0x01000007}, {'minimum': 17 << 16}):
            with self.subTest(options=options), self.assertRaises((ValueError, package.core.ValidationError)):
                package.device_binary(binary(**options))

    def test_rejects_signature_and_host_or_angle_dependencies(self):
        signature = struct.pack('<4I', 0x1d, 16, 0, 0)
        for options in ({'extra': [signature]}, {'dependencies': ['/opt/homebrew/lib/libosg.dylib']},
                        {'dependencies': ['@rpath/libEGL.dylib']}):
            with self.subTest(options=options), self.assertRaises((ValueError, package.core.ValidationError)):
                package.device_binary(binary(**options))

    def test_zip_reopening_and_exact_bundle_inventory(self):
        resources = {'nif-build.json': b'{}', 'Fixtures/test.dat': b'synthetic test metadata'}
        info = {'CFBundleExecutable': package.EXECUTABLE, 'CFBundleIdentifier': package.BUNDLE_ID,
                'CFBundlePackageType': 'APPL', 'CFBundleSupportedPlatforms': ['iPhoneOS'], 'UIDeviceFamily': [1],
                'LSRequiresIPhoneOS': True, 'MinimumOSVersion': '18.0', 'UIFileSharingEnabled': True,
                'LSSupportsOpeningDocumentsInPlace': True, 'UILaunchScreen': {},
                'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False, 'UISceneConfigurations':
                    {'UIWindowSceneSessionRoleApplication': [{'UISceneConfigurationName': 'Default', 'UISceneDelegateClassName': 'NifSceneDelegate'}]}}}
        files = {name: package.Entry(data, stat.S_IFREG | 0o644) for name, data in resources.items()}
        files['Info.plist'] = package.Entry(plistlib.dumps(info), stat.S_IFREG | 0o644)
        files[package.EXECUTABLE] = package.Entry(binary() + sha(b'{}').encode(), stat.S_IFREG | 0o755)
        with patch.object(package, 'prepared_resources', return_value=(resources, {'source_commit': 'a' * 40})):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'test.ipa'
                package.write_ipa(files, path)
                self.assertTrue(package.validate_ipa(path, Path(directory), expected=files)['valid'])
                with zipfile.ZipFile(path, 'a') as archive:
                    archive.writestr('other-app/asset', b'unexpected')
                with self.assertRaises((ValueError, package.core.ValidationError)):
                    package.validate_ipa(path, Path(directory))
            wrong = dict(files)
            wrong['Frameworks/extra'] = package.Entry(b'bad', stat.S_IFREG | 0o644)
            with self.assertRaises(ValueError):
                package.validate_bundle(wrong, Path('.'))


class PhoneEvidenceContracts(unittest.TestCase):
    def test_consistent_synthetic_result_contract(self):
        self.assertTrue(verify_result.validate(result_fixture(), 'a' * 40)['valid'])

    def test_each_missing_or_failed_case_rejects_overall_pass(self):
        for index in range(6):
            with self.subTest(index=index):
                result = result_fixture(); result['cases'][index]['passed'] = False
                with self.assertRaises(ValueError):
                    verify_result.validate(result, 'a' * 40)
                result = result_fixture(); result['cases'].pop(index)
                with self.assertRaises(ValueError):
                    verify_result.validate(result, 'a' * 40)

    def test_wrong_geometry_hash_or_immutable_snapshot_rejected(self):
        for field in ('geometry', 'hash', 'snapshot', 'stdout', 'commit'):
            with self.subTest(field=field):
                result = result_fixture()
                if field == 'geometry': result['decoded']['vertices'] = True
                elif field == 'hash': result['resource_sha256'] = '0' * 64
                elif field == 'snapshot': result['inputs_after']['valid.esm']['size'] += 1
                elif field == 'stdout': result['cases'][0]['stdout'] = 'PASS genuine OpenMW NIF parse'
                else: result['build']['source_commit'] = 'b' * 40
                with self.assertRaises(ValueError):
                    verify_result.validate(result, 'a' * 40)


if __name__ == '__main__':
    unittest.main()
