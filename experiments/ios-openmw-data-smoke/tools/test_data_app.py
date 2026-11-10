"""Offline F app/provenance contracts; these tests are not Apple or device execution evidence."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_inputs as preparer

ROOT, REPO = preparer.ROOT, preparer.REPO
OSG = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
CMAKE = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
PROBE = (ROOT / 'src/DataProbe.cpp').read_text(encoding='utf-8')
CHECK = (ROOT / 'src/DataCheck.mm').read_text(encoding='utf-8')
APP = (ROOT / 'src/main.mm').read_text(encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def genuine_config_text():
    """Render the genuine audited template for verifier tests only; not a CMake build claim."""
    manifest = json.loads(preparer.auditor.esm_audit.MANIFEST.read_text(encoding='utf-8'))
    template = (OSG / 'src/osg/Config.in').read_text(encoding='utf-8')
    return re.sub(r'^#cmakedefine (\w+)$', lambda match:
        '#define ' + match[1] if manifest['osg_config_defines'][match[1]]
        else '/* #undef ' + match[1] + ' */', template, flags=re.M)


class BuildAndAppTests(unittest.TestCase):
    def test_real_ios_arm64_18_target_and_minimal_frameworks(self):
        for anchor in ('project(IOSOpenMWDataSmoke VERSION 0.1.0 LANGUAGES CXX OBJCXX)',
                       'CMAKE_SYSTEM_NAME STREQUAL "iOS"', 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"',
                       'CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0"', '_sdk MATCHES "iphoneos"',
                       'cxx_std_20', 'OBJCXX_STANDARD 20', 'XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"',
                       'foreach(_framework UIKit Foundation)'):
            self.assertIn(anchor, CMAKE)
        commands = re.sub(r'#[^\n]*', '', CMAKE)
        for forbidden in ('ANGLE_ROOT', 'EGL_LIBRARY', 'Metal', 'OpenGLES', 'osgViewer', 'SDL',
                          'FetchContent', 'ExternalProject', 'force_load', 'all_load', 'allow-multiple-definition'):
            self.assertNotIn(forbidden, commands)
        self.assertIn('BUILD_RPATH "" INSTALL_RPATH "" SKIP_BUILD_RPATH TRUE', CMAKE)

    def test_exact_existing_e_executable_is_linked_before_app(self):
        self.assertIn('add_executable(openmw-data-link-check "${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm-vfs/tests/esm_vfs_check.cpp")', CMAKE)
        self.assertIn('target_link_libraries(openmw-data-link-check PRIVATE openmw-ios-esm-vfs)', CMAKE)
        self.assertIn('add_dependencies(IOSOpenMWDataSmoke openmw-data-link-check)', CMAKE)
        self.assertLess(CMAKE.index('add_executable(openmw-data-link-check'), CMAKE.index('add_executable(IOSOpenMWDataSmoke'))
        self.assertIn('target_link_libraries(IOSOpenMWDataSmoke PRIVATE openmw-ios-esm-vfs)', CMAKE)
        self.assertNotIn('MACOSX_BUNDLE', CMAKE.split('add_executable(openmw-data-link-check', 1)[1].split('target_link_libraries', 1)[0])
        checker = REPO / 'experiments/ios-openmw-esm-vfs/tests/esm_vfs_check.cpp'
        self.assertTrue(checker.is_file())
        self.assertIn('int main(int argc, char** argv)', checker.read_text(encoding='utf-8'))

    def test_existing_e_to_d_graph_preserves_exact_source_selection(self):
        self.assertIn('set(OPENMW_IOS_ESM_VFS_HOST_TESTS OFF)', CMAKE)
        self.assertIn('add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm-vfs"', CMAKE)
        commands = re.sub(r'#[^\n]*', '', CMAKE)
        for forbidden in ('openmw-ios-data-core', 'openmw-ios-bsa-reader', 'openmw-ios-bsa-vfs', 'add_library('):
            self.assertNotIn(forbidden, commands)
        existing = (ROOT.parent / 'ios-openmw-esm-vfs/CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('target_link_libraries(openmw-ios-esm-vfs PUBLIC openmw-ios-esm-reader)', existing)
        manifest = json.loads(preparer.auditor.MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual((len(manifest['inherited_sources']), len(manifest['additional_sources'])), (15, 6))
        self.assertEqual(len(set(manifest['inherited_sources'] + manifest['additional_sources'])), 21)

    def test_config_must_come_from_existing_d_and_prepare_before_app(self):
        self.assertIn('--config "${CMAKE_CURRENT_BINARY_DIR}/esm-vfs/esm-reader/osg-math/include/osg/Config"', CMAKE)
        self.assertIn('--osg-source "${OPENMW_ESM_OSG_SOURCE}"', CMAKE)
        self.assertLess(CMAKE.index('execute_process('), CMAKE.index('add_executable('))
        self.assertIn('message(FATAL_ERROR "Data-smoke fixture/provenance preparation failed:', CMAKE)
        self.assertIn('"${_generated}/include"', CMAKE)
        self.assertIn('copy_directory "${_generated}/resources" "$<TARGET_BUNDLE_DIR:IOSOpenMWDataSmoke>"', CMAKE)

    def test_info_plist_scene_and_export_contract(self):
        plist = plistlib.loads((ROOT / 'Info.plist.in').read_bytes())
        self.assertEqual(plist['CFBundlePackageType'], 'APPL')
        self.assertTrue(plist['LSRequiresIPhoneOS'])
        self.assertTrue(plist['UIFileSharingEnabled'])
        self.assertTrue(plist['LSSupportsOpeningDocumentsInPlace'])
        manifest = plist['UIApplicationSceneManifest']
        self.assertFalse(manifest['UIApplicationSupportsMultipleScenes'])
        configuration = manifest['UISceneConfigurations']['UIWindowSceneSessionRoleApplication']
        self.assertEqual(len(configuration), 1)
        self.assertEqual(configuration[0]['UISceneDelegateClassName'], 'DataSceneDelegate')
        self.assertIn('@interface DataSceneDelegate : UIResponder <UIWindowSceneDelegate>', APP)
        self.assertIn('initWithWindowScene:', APP)
        self.assertIn('UIApplicationMain(', APP)

    def test_probe_uses_genuine_openmw_apis_and_exact_bounded_result(self):
        for anchor in ('reader.setEncoder(&esmEncoder)', 'reader.open(esm)', 'reader.getRecName() == "STAT"',
                       'reader.getRecHeader()', 'object.load(reader, deleted)',
                       'VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized())',
                       'OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, bsa, archiveEncoder)',
                       'manager.buildIndex()', 'resource = manager.get(key)',
                       'resource->gcount()', 'bytes == wanted', 'resource->seekg(-1, std::ios::end)'):
            self.assertIn(anchor, PROBE)
        self.assertLess(PROBE.index('Utf8Encoder esmEncoder'), PROBE.index('ESM::ESMReader reader'))
        self.assertLess(PROBE.index('StatelessUtf8Encoder archiveEncoder'), PROBE.index('VFS::Manager manager'))
        self.assertIn('!deleted && !object.mModel.empty()', PROBE)
        self.assertIn('std::filesystem::file_size(esm)', PROBE)
        for forbidden in ('class ESMReader', 'struct Static', 'std::ofstream', '.addFile(', '.save(', 'Engine::go'):
            self.assertNotIn(forbidden, PROBE)

    def test_runtime_pass_requires_hashes_real_call_and_unchanged_inputs(self):
        for anchor in ('#import <CommonCrypto/CommonDigest.h>', 'CC_SHA256(', 'TARGET_OS_SIMULATOR',
                       '@"status": @"FAIL"', '@"genuine_openmw_call_completed": @NO',
                       'Expected::BuildMetadataSHA256', 'Expected::FixtureManifestSHA256',
                       'Expected::PayloadSHA256', 'Snapshot(fixtureDirectory)', '[before isEqual:after]',
                       'catch (const std::exception& error)', 'result[@"error"]'):
            self.assertIn(anchor, CHECK)
        self.assertLess(CHECK.index('Expected::BuildMetadataSHA256'), CHECK.index('readResource('))
        self.assertLess(CHECK.index('Bundled input size/SHA-256 mismatch'), CHECK.index('readResource('))
        self.assertLess(CHECK.index('readResource('), CHECK.index('result[@"status"] = @"PASS"'))
        self.assertLess(CHECK.index('Retrieved resource SHA-256 mismatch'), CHECK.index('result[@"status"] = @"PASS"'))
        self.assertLess(CHECK.index('[before isEqual:after]'), CHECK.index('result[@"status"] = @"PASS"'))
        self.assertIn('@[@"valid.esm", @"base.bsa", @"fixtures.json"]', CHECK)
        self.assertIn('files.count == 3', CHECK)
        self.assertIn('NSURLIsSymbolicLinkKey', CHECK)

    def test_app_runs_once_and_exports_failure_evidence_without_render_loop(self):
        for anchor in ('if (self.started) return;', 'self.started = YES;', 'NSDocumentDirectory',
                       '@"data-smoke.json"', '@"data-smoke.log"', 'NSDataWritingAtomic',
                       '@"status": @"RUNNING"', 'RunDataCheck(fixtures, metadata)',
                       'UIActivityViewController', 'dispatch_get_global_queue(QOS_CLASS_UTILITY',
                       'dispatch_get_main_queue()', 'BOOL passed = saved && [result[@"status"] isEqualToString:@"PASS"]'):
            self.assertIn(anchor, APP)
        self.assertLess(APP.index('@"status": @"RUNNING"'), APP.index('RunDataCheck(fixtures, metadata)'))
        for forbidden in ('eglSwapBuffers', 'CAMetalLayer', 'CADisplayLink', 'glReadPixels', 'fork(', 'NSTask', 'posix_spawn'):
            self.assertNotIn(forbidden, APP + CHECK + PROBE)


class FixtureAndProvenanceTests(unittest.TestCase):
    def test_exact_inherited_fixture_sizes_and_hashes(self):
        data = preparer.fixture_bytes()
        self.assertEqual(set(data), {'valid.esm', 'base.bsa'})
        self.assertEqual((len(data['valid.esm']), len(data['base.bsa'])), (376, 134))
        self.assertEqual(digest(data['valid.esm']), '48fdfa9d1aed2bb3d82169cd16574088373c4deaff3a39e9b40ea809157fcd9f')
        self.assertEqual(digest(data['base.bsa']), '3bb579dc79ac3aabbf12159298625d33e0a7a929a80a9550452fae7a47f632be')
        self.assertEqual(data, {name: preparer.fixtures.inputs()[name] for name in data})
        manifest = json.loads(preparer.MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(manifest['resource']['sha256'], '3f164502d39021fecd17102c940caad8e7916ede6863daca51200c44ff65a288')
        self.assertEqual(bytes.fromhex(manifest['resource']['hex']), b'\x00OMW-E\xff\n\x00synthetic-model')
        self.assertEqual(manifest['resource']['key'], 'meshes/test.nif')

    def test_corrupt_missing_extra_and_wrong_resource_expectations_rejected(self):
        original = json.loads(preparer.MANIFEST.read_text(encoding='utf-8'))
        for change in ('hash', 'size', 'missing', 'extra', 'resource', 'schema'):
            manifest = copy.deepcopy(original)
            if change == 'hash': manifest['inputs']['valid.esm']['sha256'] = '0' * 64
            elif change == 'size': manifest['inputs']['base.bsa']['size'] += 1
            elif change == 'missing': del manifest['inputs']['valid.esm']
            elif change == 'extra': manifest['inputs']['extra.bin'] = {'size': 1, 'sha256': '0' * 64}
            elif change == 'resource': manifest['resource']['key'] = 'meshes/other.nif'
            else: manifest['schema_version'] = 2
            with self.subTest(change=change), self.assertRaises(ValueError): preparer.fixture_bytes(manifest)
        original_inputs = preparer.fixtures.inputs()
        original_inputs['valid.esm'] = b'not a genuine generated fixture'
        with patch.object(preparer.fixtures, 'inputs', return_value=original_inputs), self.assertRaises(ValueError):
            preparer.fixture_bytes()

    def test_prepare_with_genuine_pinned_osg_writes_expected_resources_and_bound_constants(self):
        if not OSG.is_dir(): self.skipTest('Separate genuine pinned OSG checkout unavailable; no download')
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp); config = root / 'Config'; config.write_text(genuine_config_text(), encoding='utf-8')
            output = root / 'prepared'
            preparer.prepare(output, OSG, config)
            resources = output / 'resources'
            for name, data in preparer.fixture_bytes().items(): self.assertEqual((resources / 'Fixtures' / name).read_bytes(), data)
            metadata_data = (resources / 'data-build.json').read_bytes()
            metadata = json.loads(metadata_data)
            self.assertEqual(metadata['osg_revision'], '9b384d5439977784e5cd250ff8ff7966928ddd27')
            self.assertEqual((metadata['genuine_engine_units'], metadata['registration_helper_units']), (20, 1))
            self.assertEqual(len(metadata['project_source_sha256_lf']), 79)
            self.assertEqual(len(metadata['osg_source_sha256_lf']), 7)
            self.assertEqual(metadata['osg_config_sha256'], digest(config.read_bytes()))
            self.assertEqual((resources / 'Provenance/osg/Config').read_bytes(), config.read_bytes())
            self.assertEqual((resources / 'Fixtures/fixtures.json').read_bytes(), preparer.MANIFEST.read_bytes())
            for name in ('OpenMW-LICENSE.txt', 'OSG-LICENSE.txt'): self.assertTrue((resources / 'Licenses' / name).is_file())
            header = (output / 'include/FixtureExpectations.hpp').read_text(encoding='utf-8')
            self.assertIn('BuildMetadataSHA256[] = "' + digest(metadata_data) + '"', header)
            self.assertIn('FixtureManifestSHA256[] = "' + digest(preparer.MANIFEST.read_bytes()) + '"', header)
            self.assertIn('std::array<std::uint8_t, 24> Payload', header)
            self.assertIn('0x00, 0x4f, 0x4d, 0x57', header)
            self.assertIn('source provenance; not device runtime proof', metadata['scope'])
            self.assertFalse(metadata['source_audit']['native_compilation_performed'])

    def test_missing_changed_empty_or_fake_config_fails_before_output_creation(self):
        if not OSG.is_dir(): self.skipTest('Separate genuine pinned OSG checkout unavailable; no download')
        for kind in ('missing', 'empty', 'changed', 'fake-header'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); config = root / 'Config'; output = root / 'output'
                if kind != 'missing':
                    config.write_text('' if kind == 'empty' else '#pragma once\n' if kind == 'fake-header'
                                      else genuine_config_text() + '// altered\n', encoding='utf-8')
                with self.assertRaises((OSError, ValueError)): preparer.prepare(output, OSG, config)
                self.assertFalse(output.exists())

    def test_wrong_source_pin_rejected_without_output_or_checkout_changes(self):
        if not OSG.is_dir(): self.skipTest('Separate genuine pinned OSG checkout unavailable; no download')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); config = root / 'Config'; config.write_text(genuine_config_text(), encoding='utf-8')
            output = root / 'prepared'
            with patch.object(preparer.auditor.esm_audit.subprocess, 'run',
                              return_value=subprocess.CompletedProcess([], 0, '0' * 40 + '\n', '')):
                with self.assertRaises(preparer.auditor.AuditError): preparer.prepare(output, OSG, config)
            self.assertFalse(output.exists())

    def test_unsafe_output_locations_rejected_before_any_write(self):
        for output in (REPO, ROOT, ROOT / 'src/output', ROOT / 'data/output', ROOT / 'tools/output',
                       ROOT.parent / 'ios-openmw-esm/output', OSG / 'generated-config'):
            with self.subTest(output=str(output)), self.assertRaises(ValueError):
                preparer.prepare(output, OSG, Path('unused-missing-config'))


if __name__ == '__main__':
    unittest.main()
