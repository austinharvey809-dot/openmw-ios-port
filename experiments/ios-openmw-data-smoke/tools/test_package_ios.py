"""Packaging contracts using synthetic Mach-O/SDK metadata, never native build evidence."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import plistlib
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import package_ios as package

REGULAR, EXECUTABLE = stat.S_IFREG | 0o644, stat.S_IFREG | 0o755
DEPENDENCIES = ('/System/Library/Frameworks/UIKit.framework/UIKit',
                '/System/Library/Frameworks/Foundation.framework/Foundation', '/usr/lib/libc++.1.dylib')


def command(kind, value):
    prefix = 12 if kind == 0x8000001C else 24
    encoded = value.encode() + b'\0'
    size = (prefix + len(encoded) + 7) & ~7
    return struct.pack('<III', kind, size, prefix) + bytes(prefix - 12) + encoded + bytes(size - prefix - len(encoded))


def binary(filetype=2, cpu=0x0100000C, subtype=0, target=2, minimum=18 << 16, dependencies=DEPENDENCIES,
           rpaths=(), extra=()):
    commands = [struct.pack('<6I', 0x32, 24, target, minimum, 26 << 16, 0)]
    commands += [command(0xC, name) for name in dependencies]
    commands += [command(0x8000001C, name) for name in rpaths]
    commands += list(extra)
    body = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, subtype, filetype, len(commands), len(body), 0, 0) + body


def fixture_inputs():
    path = package.REPO / 'experiments/ios-openmw-esm-vfs/tools/fixtures.py'
    spec = importlib.util.spec_from_file_location('_data_smoke_packaging_fixture_bytes', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    generated = module.inputs()
    resource = {'id': 'eIOSStatic', 'model': 'TeSt.NIF', 'key': 'meshes/test.nif',
                'size': len(module.BASE_PAYLOAD), 'hex': module.BASE_PAYLOAD.hex(),
                'sha256': hashlib.sha256(module.BASE_PAYLOAD).hexdigest()}
    inputs = {name: generated[name] for name in ('valid.esm', 'base.bsa')}
    manifest = {'schema_version': 1, 'inputs': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in inputs.items()}, 'resource': resource}
    return inputs, manifest


def bundle(manifest, inputs, **binary_options):
    info = {'CFBundleExecutable': package.EXECUTABLE, 'CFBundleIdentifier': package.BUNDLE_ID,
            'CFBundlePackageType': 'APPL', 'CFBundleSupportedPlatforms': ['iPhoneOS'], 'UIDeviceFamily': [1],
            'MinimumOSVersion': '18.0', 'LSRequiresIPhoneOS': True, 'UILaunchScreen': {},
            'UIFileSharingEnabled': True, 'LSSupportsOpeningDocumentsInPlace': True,
            'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False,
                'UISceneConfigurations': {'UIWindowSceneSessionRoleApplication': [{'UISceneDelegateClassName': 'DataSceneDelegate'}]}}}
    metadata = {'source_commit': 'a' * 40, 'osg_revision': package.OSG_REVISION, 'genuine_engine_units': 20,
                'registration_helper_units': 1, 'scope': 'prepared source provenance; not device runtime proof'}
    return {'Info.plist': package.Entry(plistlib.dumps(info), REGULAR),
            package.EXECUTABLE: package.Entry(binary(**binary_options), EXECUTABLE),
            'Fixtures/fixtures.json': package.Entry(manifest, REGULAR),
            'Fixtures/valid.esm': package.Entry(inputs['valid.esm'], REGULAR),
            'Fixtures/base.bsa': package.Entry(inputs['base.bsa'], REGULAR),
            'data-build.json': package.Entry(json.dumps(metadata).encode(), REGULAR),
            'Licenses/OpenMW-LICENSE.txt': package.Entry(b'License text unit-test fixture only', REGULAR),
            'Licenses/OSG-LICENSE.txt': package.Entry(b'License text unit-test fixture only', REGULAR)}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs, self.manifest = fixture_inputs()
        self.manifest_bytes = (json.dumps(self.manifest, indent=2) + '\n').encode()
        self.reference = self.root / 'fixtures.json'; self.reference.write_bytes(self.manifest_bytes)
        self.reference_patch = patch.object(package, 'REFERENCE', self.reference)
        self.reference_patch.start(); self.addCleanup(self.reference_patch.stop)

    def files(self, **options):
        return bundle(self.manifest_bytes, self.inputs, **options)

    def sdk(self, targets='arm64-ios'):
        sdk = self.root / 'iPhoneOS.sdk'; sdk.mkdir(exist_ok=True)
        (sdk / 'SDKSettings.plist').write_bytes(plistlib.dumps({'CanonicalName': 'iphoneos26.0'}))
        for name in DEPENDENCIES:
            path = sdk / name.lstrip('/')
            stub = path.with_suffix('.tbd') if path.suffix == '.dylib' else Path(str(path) + '.tbd')
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text("--- !tapi-tbd\ntbd-version: 4\ntargets: [ " + targets + " ]\ninstall-name: '" + name + "'\n...\n")
        return sdk

    def custom_zip(self, path, entries):
        with zipfile.ZipFile(path, 'w') as archive:
            for name, entry in entries:
                info = zipfile.ZipInfo(name); info.create_system = 3; info.external_attr = entry.mode << 16
                archive.writestr(info, entry.data)

    def test_valid_bundle_has_exact_pinned_resources_and_no_graphics_dependency(self):
        report = package.validate_bundle(self.files())
        self.assertEqual(report['required_resources'], list(package.REQUIRED))
        self.assertEqual(report['resource_sha256'], self.manifest['resource']['sha256'])
        self.assertEqual(report['osg_revision'], package.OSG_REVISION)
        self.assertFalse(report['sdk_availability_checked'])
        self.assertEqual(package.core.APP_NAME, 'IOSANGLESmoke.app')
        self.assertEqual(package.core.PREFIX, 'Payload/IOSANGLESmoke.app/')

    def test_every_required_resource_is_mandatory(self):
        for name in package.REQUIRED:
            with self.subTest(name=name):
                files = self.files(); files.pop(name)
                with self.assertRaises(package.ValidationError): package.validate_bundle(files)

    def test_fixture_manifest_and_input_hashes_are_strict(self):
        for name in ('Fixtures/fixtures.json', 'Fixtures/valid.esm', 'Fixtures/base.bsa'):
            with self.subTest(name=name):
                files = self.files(); files[name] = package.Entry(files[name].data + b'tampered', REGULAR)
                with self.assertRaises(package.ValidationError): package.validate_bundle(files)
        for change in ('size', 'sha256', 'resource'):
            manifest = json.loads(self.manifest_bytes)
            if change == 'resource': manifest['resource']['sha256'] = '0' * 64
            else: manifest['inputs']['base.bsa'][change] = 0 if change == 'size' else '0' * 64
            raw = json.dumps(manifest).encode(); self.reference.write_bytes(raw)
            files = self.files(); files['Fixtures/fixtures.json'] = package.Entry(raw, REGULAR)
            with self.subTest(change=change), self.assertRaises(package.ValidationError): package.validate_bundle(files)

    def test_plist_identity_device_deployment_scene_export_and_launch_requirements(self):
        for change in ('executable', 'id', 'platform', 'family', 'minimum', 'scene', 'sharing', 'launch', 'storyboard'):
            files = self.files(); info = plistlib.loads(files['Info.plist'].data)
            if change == 'executable': info['CFBundleExecutable'] = 'Other'
            elif change == 'id': info['CFBundleIdentifier'] = 'org.example.other'
            elif change == 'platform': info['CFBundleSupportedPlatforms'] = ['iPhoneSimulator']
            elif change == 'family': info['UIDeviceFamily'] = [2]
            elif change == 'minimum': info['MinimumOSVersion'] = '18.1'
            elif change == 'scene': info['UIApplicationSceneManifest']['UIApplicationSupportsMultipleScenes'] = True
            elif change == 'sharing': info['UIFileSharingEnabled'] = False
            elif change == 'launch': info.pop('UILaunchScreen')
            else: info['UILaunchStoryboardName'] = 'missing'
            files['Info.plist'] = package.Entry(plistlib.dumps(info), REGULAR)
            with self.subTest(change=change), self.assertRaises(package.ValidationError): package.validate_bundle(files)

    def test_build_provenance_wrong_pin_source_count_scope_or_commit_rejected(self):
        changes = {'osg_revision': '0' * 40, 'source_commit': 'not-a-sha', 'genuine_engine_units': 21,
                   'registration_helper_units': 0, 'scope': 'device executed successfully'}
        for key, value in changes.items():
            files = self.files(); build = json.loads(files['data-build.json'].data); build[key] = value
            files['data-build.json'] = package.Entry(json.dumps(build).encode(), REGULAR)
            with self.subTest(key=key), self.assertRaises(package.ValidationError): package.validate_bundle(files)
        for data in (b'{"source_commit":"a","source_commit":"b"}', b'[]'):
            with self.assertRaises(package.ValidationError): package.json_object(data, 'unit-test provenance')
        for value in (True, 1.0):
            files = self.files(); build = json.loads(files['data-build.json'].data)
            build['registration_helper_units'] = value
            files['data-build.json'] = package.Entry(json.dumps(build).encode(), REGULAR)
            with self.assertRaises(package.ValidationError): package.validate_bundle(files)

    def test_executable_rejects_wrong_arch_platform_deployment_signatures_and_ambiguous_metadata(self):
        options = [{'cpu': 0x01000007}, {'subtype': 2}, {'filetype': 6}, {'filetype': 1},
                   *({'target': p} for p in (1, 6, 7)), *({'minimum': v} for v in (17 << 16, (18 << 16) | 256, 19 << 16)),
                   {'extra': (struct.pack('<4I', 0x1D, 16, 0, 0),)},
                   {'extra': (struct.pack('<4I', 0x24, 16, 18 << 16, 26 << 16),)},
                   {'extra': (struct.pack('<6I', 0x32, 24, 2, 18 << 16, 26 << 16, 0),)}]
        for option in options:
            with self.subTest(option=option), self.assertRaises(package.ValidationError): package.validate_device_executable(binary(**option))
        for data in (b'', b'!<arch>\n', binary()[:-1]):
            with self.assertRaises(package.ValidationError): package.validate_device_executable(data)

    def test_any_runtime_path_third_party_or_build_machine_dependency_rejected(self):
        for path in ('@executable_path/Frameworks', '@loader_path', '/Users/runner/work/_temp/lib', '/usr/lib'):
            with self.subTest(path=path), self.assertRaises(package.ValidationError):
                package.validate_device_executable(binary(rpaths=(path,)))
        for name in ('@rpath/libEGL.dylib', '/Users/runner/libexample.dylib', '/opt/homebrew/lib/libc++.dylib',
                     '/System/Library/Frameworks/Metal.framework/Metal'):
            with self.subTest(dependency=name), self.assertRaises(package.ValidationError):
                package.validate_device_executable(binary(dependencies=(*DEPENDENCIES, name)))

    def test_extra_native_libraries_credentials_symlinks_and_executable_resources_rejected(self):
        for name, entry in (('Frameworks/extra.dat', package.Entry(b'x', REGULAR)),
                ('extra.a', package.Entry(b'!<arch>\n', REGULAR)), ('extra.dylib', package.Entry(binary(filetype=6), REGULAR)),
                ('extra-native', package.Entry(binary(), REGULAR)), ('run.sh', package.Entry(b'shell', EXECUTABLE)),
                ('private.key', package.Entry(b'fake key', REGULAR)), ('embedded.mobileprovision', package.Entry(b'fake profile', REGULAR)),
                ('_CodeSignature/CodeResources', package.Entry(b'fake signature', REGULAR)),
                ('link', package.Entry(b'../../outside', stat.S_IFLNK | 0o777))):
            files = self.files(); files[name] = entry
            with self.subTest(name=name), self.assertRaises(package.ValidationError): package.validate_bundle(files)

    def test_sdk_device_stubs_are_checked_and_simulator_or_macos_only_rejected(self):
        sdk = self.sdk()
        self.assertTrue(package.validate_bundle(self.files(), sdk)['sdk_availability_checked'])
        for target in ('arm64-ios-simulator', 'arm64-macos'):
            self.sdk(target)
            with self.subTest(target=target), self.assertRaises(package.ValidationError): package.validate_bundle(self.files(), sdk)

    def test_standard_ipa_roundtrip_preserves_all_files_permissions_and_hashes(self):
        files = self.files(); path = self.root / 'data.ipa'
        package.write_ipa(files, path)
        report = package.validate_ipa(path, expected=files)
        self.assertEqual(report['archive_root'], package.PREFIX)
        self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(report['unsigned'])
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {'Payload/', package.PREFIX, *(package.PREFIX + name for name in files)})
            self.assertEqual(archive.getinfo(package.PREFIX + package.EXECUTABLE).external_attr >> 16, EXECUTABLE)

    def test_archive_rejects_wrong_root_duplicate_entries_traversal_and_modified_files(self):
        files = self.files()
        valid = [('Payload/', package.Entry(b'', stat.S_IFDIR | 0o755)),
                 (package.PREFIX, package.Entry(b'', stat.S_IFDIR | 0o755)),
                 *((package.PREFIX + name, data) for name, data in files.items())]
        variants = [[*valid, ('outside', package.Entry(b'outside', REGULAR))],
                    [*valid, (package.PREFIX + 'Info.plist', files['Info.plist'])],
                    [*valid, (package.PREFIX + '../escape', package.Entry(b'outside', REGULAR))], valid[1:]]
        for entries in variants:
            path = self.root / 'bad.ipa'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning); self.custom_zip(path, entries)
            with self.assertRaises(package.ValidationError): package.validate_ipa(path)
        path = self.root / 'changed.ipa'; changed = self.files(); changed['Fixtures/base.bsa'] = package.Entry(b'changed', REGULAR)
        package.write_ipa(changed, path)
        with self.assertRaises(package.ValidationError): package.validate_ipa(path)

    def test_app_cli_packages_reopens_and_records_evidence_with_mocked_native_otool(self):
        output, evidence = self.root / 'data.ipa', self.root / 'evidence'
        with patch.object(package, 'collect_bundle', return_value=self.files()), \
                patch.object(package.core, 'inspect_dependencies', return_value={package.EXECUTABLE: 'mocked native tool contract\n'}), \
                contextlib.redirect_stdout(io.StringIO()):
            code = package.main(['--app', str(self.root / package.APP_NAME), '--sdk', str(self.sdk()),
                                 '--output', str(output), '--evidence', str(evidence)])
        self.assertEqual(code, 0); self.assertTrue(output.is_file())
        self.assertTrue(json.loads((evidence / 'validation.json').read_text())['valid'])
        self.assertTrue((evidence / 'otool-L.txt').is_file())
        for row in (evidence / 'SHA256SUMS').read_text().splitlines():
            digest, name = row.split('  ', 1)
            self.assertEqual(digest, hashlib.sha256((evidence / name).read_bytes()).hexdigest())

    def test_link_only_cli_requires_real_device_metadata_sdk_and_otool_but_no_bundle(self):
        path, evidence = self.root / 'openmw-data-link-check', self.root / 'link-evidence'
        path.write_bytes(binary(dependencies=('/usr/lib/libc++.1.dylib',)))
        with patch.object(package.core, 'inspect_dependencies', return_value={path.name: 'mocked tool contract\n'}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(package.main(['--link-executable', str(path), '--sdk', str(self.sdk()), '--evidence', str(evidence)]), 0)
        report = json.loads((evidence / 'validation.json').read_text())
        self.assertTrue(report['valid']); self.assertIn('no device runtime proof', report['scope'])
        self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_cli_missing_sdk_failed_native_tools_or_invalid_ipa_fail_with_evidence(self):
        for failure in ('missing-sdk', 'otool', 'bad-ipa'):
            evidence = self.root / failure
            with contextlib.redirect_stdout(io.StringIO()):
                if failure == 'bad-ipa':
                    path = self.root / 'invalid.ipa'; path.write_bytes(b'not zip')
                    result = package.main(['--validate-only', str(path), '--evidence', str(evidence)])
                else:
                    path = self.root / 'link-check'; path.write_bytes(binary())
                    arguments = ['--link-executable', str(path), '--evidence', str(evidence)]
                    if failure == 'otool': arguments += ['--sdk', str(self.sdk())]
                    with patch.object(package.core, 'inspect_dependencies', side_effect=FileNotFoundError('xcrun unavailable')):
                        result = package.main(arguments)
            self.assertEqual(result, 1)
            self.assertFalse(json.loads((evidence / 'validation.json').read_text())['valid'])
            self.assertTrue((evidence / 'SHA256SUMS').is_file())


if __name__ == '__main__':
    unittest.main()
