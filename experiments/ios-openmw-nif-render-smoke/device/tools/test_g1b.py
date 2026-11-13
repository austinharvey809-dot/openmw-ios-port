"""Synthetic policy tests; actual device compilation/rendering are separate gates."""
import copy
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import provenance as p
import package_device as package

UIKIT = '/System/Library/Frameworks/UIKit.framework/UIKit'
FOUNDATION = '/System/Library/Frameworks/Foundation.framework/Foundation'
SYSTEM = '/usr/lib/libSystem.B.dylib'
ROLES = {'egl': 'Frameworks/libEGL.framework/libEGL', 'gles': 'Frameworks/libGLESv2.framework/libGLESv2'}


def string_command(command, text, base=24):
    data = text.encode() + b'\0'
    size = (base + len(data) + 7) & ~7
    prefix = struct.pack('<III', command, size, base) + bytes(base - 12)
    return prefix + data + bytes(size - base - len(data))


def binary(dependencies, kind=2, install=None, rpaths=('@executable_path/Frameworks',),
           cpu=0x0100000c, platform=2, minimum=18 << 16, signed=False):
    commands = [struct.pack('<6I', 0x32, 24, platform, minimum, 26 << 16, 0)]
    commands += [string_command(0xc, name) for name in dependencies]
    commands += [string_command(0x8000001c, path, 12) for path in rpaths]
    if install:
        commands.append(string_command(0xd, install))
    if signed:
        commands.append(struct.pack('<4I', 0x1d, 16, 0, 0))
    body = b''.join(commands)
    return struct.pack('<8I', 0xfeedfacf, cpu, 0, kind, len(commands), len(body), 0, 0) + body


def bundle(**options):
    metadata = {'angle_libraries': dict(ROLES), 'source_commit': 'a' * 40}
    resources = {'g1b-build.json': b'{}', 'Fixtures/test.dat': b'synthetic policy fixture'}
    for role, path in ROLES.items():
        install = '@rpath/' + path.removeprefix('Frameworks/')
        dependencies = [SYSTEM] + (['@rpath/libEGL.framework/libEGL'] if role == 'gles' else [])
        resources[path] = binary(dependencies, kind=6, install=install, rpaths=('@loader_path/..',))
        resources[str(Path(path).parent / 'Info.plist').replace('\\', '/')] = plistlib.dumps({
            'CFBundleExecutable': Path(path).name, 'CFBundlePackageType': 'FMWK', 'CFBundleSupportedPlatforms': ['iPhoneOS']})
    entries = {name: package.Entry(data, stat.S_IFREG | (0o755 if name in ROLES.values() else 0o644))
               for name, data in resources.items()}
    text = (p.ROOT / 'Info.plist.in').read_text().replace('${MACOSX_BUNDLE_EXECUTABLE_NAME}', package.EXECUTABLE)
    text = text.replace('${MACOSX_BUNDLE_GUI_IDENTIFIER}', package.BUNDLE_ID)
    entries['Info.plist'] = package.Entry(plistlib.dumps(plistlib.loads(text.encode())), stat.S_IFREG | 0o644)
    dependencies = [UIKIT, FOUNDATION, '@rpath/libEGL.framework/libEGL', '@rpath/libGLESv2.framework/libGLESv2']
    entries[package.EXECUTABLE] = package.Entry(binary(dependencies, **options) + p.sha(b'{}').encode(), stat.S_IFREG | 0o755)
    return entries, resources, metadata


class BinaryAndPackageTests(unittest.TestCase):
    def validate(self, entries, resources, metadata, sdk=None):
        with patch.object(package, 'prepared_resources', return_value=(resources, metadata)):
            return package.validate_bundle(entries, Path('.'), sdk)

    def test_real_macho_reader_accepts_only_matching_synthetic_device_bundle(self):
        entries, resources, metadata = bundle()
        self.assertTrue(self.validate(entries, resources, metadata)['valid'])

    def test_selected_sdk_helper_runs_for_actual_system_dependencies(self):
        entries, resources, metadata = bundle()
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            for name in (UIKIT, FOUNDATION, SYSTEM):
                path = sdk / name.lstrip('/')
                path = path.with_suffix('.tbd') if path.suffix == '.dylib' else Path(str(path) + '.tbd')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("--- !tapi-tbd\ntbd-version: 4\ntargets: [ arm64-ios ]\ninstall-name: '" + name + "'\n...\n")
            with patch.object(package.core, 'system_dependency', wraps=package.core.system_dependency) as helper:
                self.assertTrue(self.validate(entries, resources, metadata, sdk)['valid'])
                self.assertEqual({call.args[0] for call in helper.call_args_list}, {UIKIT, FOUNDATION, SYSTEM})
            (sdk / 'usr/lib/libSystem.B.tbd').unlink()
            with self.assertRaises(ValueError):
                self.validate(entries, resources, metadata, sdk)

    def test_architecture_platform_deployment_and_signatures_rejected(self):
        for options in ({'cpu': 0x01000007}, {'platform': 1}, {'platform': 7}, {'minimum': 17 << 16},
                        {'minimum': 19 << 16}, {'signed': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.validate(*bundle(**options))

    def test_missing_and_unexpected_runpaths_rejected(self):
        for paths in ((), ('/opt/homebrew/lib',), ('@executable_path/Other',)):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.validate(*bundle(rpaths=paths))

    def test_alternate_host_and_unresolved_runtime_dependencies_rejected(self):
        for name in ('/System/Library/Frameworks/OpenGLES.framework/OpenGLES', '/opt/homebrew/lib/libosg.dylib',
                     '@rpath/unknown.framework/unknown', '@rpath/libvulkan.dylib'):
            entries, resources, metadata = bundle()
            original = entries[package.EXECUTABLE]
            entries[package.EXECUTABLE] = package.Entry(binary([UIKIT, FOUNDATION, name]), original.mode)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate(entries, resources, metadata)

    def test_extra_missing_changed_or_executable_resource_rejected(self):
        for mode in ('extra', 'missing', 'changed', 'executable', 'symlink', 'signing'):
            entries, resources, metadata = bundle()
            if mode in ('extra', 'signing'):
                entries['extra.txt' if mode == 'extra' else 'embedded.mobileprovision'] = package.Entry(b'x', stat.S_IFREG | 0o644)
            elif mode == 'missing':
                del entries['Fixtures/test.dat']
            else:
                entries['Fixtures/test.dat'] = package.Entry(b'changed' if mode == 'changed' else b'synthetic policy fixture',
                    stat.S_IFLNK | 0o644 if mode == 'symlink' else stat.S_IFREG | (0o755 if mode == 'executable' else 0o644))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.validate(entries, resources, metadata)

    def test_identity_scene_and_platform_plist_are_mandatory(self):
        for key, value in (('CFBundleIdentifier', 'org.other.app'), ('MinimumOSVersion', '19.0'),
                           ('UIDeviceFamily', [2]), ('UIApplicationSceneManifest', {})):
            entries, resources, metadata = bundle()
            info = plistlib.loads(entries['Info.plist'].data)
            info[key] = value
            entries['Info.plist'] = package.Entry(plistlib.dumps(info), entries['Info.plist'].mode)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(entries, resources, metadata)

    def test_both_angle_roles_must_be_reachable(self):
        entries, resources, metadata = bundle()
        entries[package.EXECUTABLE] = package.Entry(binary([UIKIT, FOUNDATION]) + p.sha(b'{}').encode(), stat.S_IFREG | 0o755)
        with self.assertRaisesRegex(ValueError, 'Unreferenced'):
            self.validate(entries, resources, metadata)

    def test_metadata_contract_must_be_embedded_in_executable(self):
        entries, resources, metadata = bundle()
        entries[package.EXECUTABLE] = package.Entry(entries[package.EXECUTABLE].data[:-64], stat.S_IFREG | 0o755)
        with self.assertRaisesRegex(ValueError, 'metadata contract'):
            self.validate(entries, resources, metadata)

    def test_independent_ipa_reopening_repeats_full_native_inspection(self):
        entries, resources, metadata = bundle()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(package, 'prepared_resources', return_value=(resources, metadata)), \
                patch.object(package, 'native', wraps=package.native) as inspector:
            ipa = Path(directory) / 'test.ipa'
            package.core.write_ipa(entries, ipa)
            self.assertTrue(package.validate_ipa(ipa, Path('.'), expected=entries)['valid'])
            self.assertTrue(package.validate_ipa(ipa, Path('.'))['valid'])
            self.assertEqual(inspector.call_count, 6)
            altered = dict(entries)
            altered[package.EXECUTABLE] = package.Entry(binary([UIKIT, FOUNDATION], platform=1), stat.S_IFREG | 0o755)
            package.core.write_ipa(altered, ipa)
            with self.assertRaises(ValueError):
                package.validate_ipa(ipa, Path('.'))

    def test_duplicate_or_wrong_root_ipa_rejected(self):
        entries, resources, metadata = bundle()
        with tempfile.TemporaryDirectory() as directory:
            ipa = Path(directory) / 'test.ipa'
            for name in ('Payload/Other.app/file', package.PREFIX + 'Info.plist'):
                package.core.write_ipa(entries, ipa)
                with zipfile.ZipFile(ipa, 'a') as archive:
                    archive.writestr(name, b'bad')
                with patch.object(package, 'prepared_resources', return_value=(resources, metadata)), self.assertRaises(ValueError):
                    package.validate_ipa(ipa, Path('.'))


class LanguageStandardTests(unittest.TestCase):
    def test_appleclang_objective_cxx20_draft_spelling(self):
        command = ('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++ '
                   '-x objective-c++ -I/Users/runner/work/_temp/g1b-native-build/osg/include '
                   '-std=c++2a -arch arm64 -isysroot /Applications/Xcode.app/Contents/Developer/Platforms/'
                   'iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk -miphoneos-version-min=18.0 '
                   '-c "/Users/runner/work/openmw/experiments/ios-openmw-nif-render-smoke/device/src/main.mm"')
        p.require_cxx20(shlex.split(command))

    def test_normal_strict_cxx20_spelling(self):
        p.require_cxx20(shlex.split('clang++ -std=c++20 -arch arm64 -c GeometryAdapter.cpp'))

    def test_missing_older_newer_and_non_strict_standards_rejected(self):
        for option in ('', '-std=c++14', '-std=c++17', '-std=c++23', '-std=c++2b', '-std=c++26',
                       '-std=gnu++20', '-std=gnu++2a', '-std=c++20-extra', '-std=', '-std c++20', '--std=c++20'):
            with self.subTest(option=option), self.assertRaises(ValueError):
                p.require_cxx20(shlex.split('clang++ ' + option + ' -c main.mm'))

    def test_multiple_or_conflicting_standard_options_rejected(self):
        for options in ('-std=c++20 -std=c++17', '-std=c++17 -std=c++2a', '-std=c++20 -std=c++23',
                        '-std=c++20 -std=c++2a', '-std=c++20 -std=c++20', '-std=c++2a --std=c++17',
                        '-std=c++20 -std c++14'):
            with self.subTest(options=options), self.assertRaises(ValueError):
                p.require_cxx20(shlex.split('clang++ ' + options + ' -c main.mm'))

    def test_unrelated_arguments_cannot_supply_the_standard(self):
        for argument in ('-DNOTE=c++20', '-DNOTE=-std=c++20', '-DNOTE="text -std=c++20"', '-I/tmp/c++20',
                         '-include /tmp/c++20.hpp', '"/tmp/-std=c++2a/main.mm"'):
            for option in ('', '-std=c++17'):
                with self.subTest(argument=argument, option=option), self.assertRaises(ValueError):
                    p.require_cxx20(shlex.split('clang++ ' + argument + ' ' + option))


class SourceTests(unittest.TestCase):
    def test_completed_preservation_and_verified_baseline(self):
        osg = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', p.REPO.parent / 'OpenSceneGraph-pinned'))
        self.assertEqual(p.audit(osg)['preserved_sources'], 204)

    def test_single_provider_and_all_parser_units(self):
        cmake = (p.ROOT / 'CMakeLists.txt').read_text()
        provider = (p.ROOT / 'cmake/provider.cmake').read_text()
        self.assertEqual(provider.count('add_subdirectory("${OSG_SOURCE}"'), 1)
        self.assertEqual(cmake.count('add_subdirectory('), 1)  # Reused D/E only; provider is separate and unique.
        self.assertIn('nif-source-sha256.json', cmake)
        self.assertIn('BEFORE PUBLIC "$<BUILD_INTERFACE:${_generated}>"', cmake)
        self.assertIn('openmw-ios-esm-reader openmw-ios-esm-vfs', cmake)
        self.assertNotIn('G0C_OSG_INCLUDE', cmake)
        self.assertIn('BulletCollision LinearMath osg OpenThreads', cmake)
        self.assertIn('OPENTHREADS_ATOMIC_USE_MUTEX ON', (p.ROOT / 'cmake/precision.cmake').read_text())

    def test_colored_shader_abi_matches_exact_committed_baseline(self):
        original = p.host.git('show', p.host.LOCK['graphics_baseline_commit'] + ':experiments/ios-osg-smoke/src/OSGScene.hpp').decode()
        actual = (p.ROOT / 'src/OSGScene.hpp').read_text()
        extract = lambda text: re.findall(r'R"\((#version 300 es.*?)\)"', text, re.S)
        self.assertEqual(extract(actual), extract(original)[:2])
        self.assertIn('owned = LoadGeometry()', actual)
        self.assertIn('viewer->setSceneData(owned.geode.get())', actual)
        self.assertNotIn('DrawElementsUShort', actual)
        self.assertNotIn('mipmap', actual.lower())

    def test_lifecycle_and_no_render_acceptance_from_counters(self):
        renderer = (p.ROOT / 'src/AngleRenderer.hpp').read_text()
        main = (p.ROOT / 'src/main.mm').read_text()
        self.assertEqual(renderer.count('eglSwapBuffers(display, surface)'), 1)
        self.assertIn('eglMakeCurrent suspend', renderer)
        self.assertIn('osgScene.reset();', renderer)
        self.assertIn('UNVERIFIED: independent screenshot/export review required', main)
        self.assertIn('parsed.file.reset();', main)
        self.assertIn('for (std::size_t i = 0; i < 6;', main)
        self.assertNotIn('@"PASS"', main)

    def test_manual_fail_fast_workflow_and_target_derived_products(self):
        text = (p.REPO / '.github/workflows/ios-openmw-nif-render-device-smoke.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('\n  push:', text)
        self.assertNotIn('continue-on-error', text)
        for phase in ('link', 'bundle', 'ipa', 'reopen'):
            self.assertIn('package_device.py" ' + phase, text)
        self.assertIn('if: always()', text)
        self.assertIn('needs: [host-regressions, angle-device]', text)
        self.assertIn('$<TARGET_FILE:IOSOpenMWNifTriangle>', (p.ROOT / 'CMakeLists.txt').read_text())


if __name__ == '__main__':
    unittest.main()
