import ctypes
import hashlib
import importlib.util
import io
import json
import os
import struct
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


dependencies = module('g6_dependency_tests', 'dependencies.py')
prepare = module('g6_projection_tests', 'prepare.py')
cases = module('g6_case_tests', 'run_cases.py')
audit = module('g6_audit_tests', 'audit.py')
package = module('g6_package_tests', 'package.py')
native = module('g6_preflight_tests', 'native_preflight.py')


class Sources(unittest.TestCase):
    def test_projection_is_checked_and_does_not_rewrite_identical_source(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            products = prepare.prepare(output)
            times = {name: (output / name).stat().st_mtime_ns for name in products}
            self.assertEqual(products, prepare.prepare(output))
            self.assertEqual(times, {name: (output / name).stat().st_mtime_ns for name in products})
            self.assertNotIn('std::vector<ESM::CellRef> references(', (output / 'EngineIndex.hpp').read_text())
            self.assertIn('CellStore::loadRefs', (output / 'cellstore.cpp').read_text())
            self.assertIn('G6 missing base', (output / 'cellstore.cpp').read_text())
            self.assertNotIn('void Player::update()', (output / 'player_data.cpp').read_text())
            self.assertIn('ESMStore::getSpellList', (output / 'spellstore.cpp').read_text())

    def test_original_source_mismatch_fails_before_projection(self):
        lock = json.loads((prepare.ROOT / 'engine-lock.json').read_text())
        lock['sources'][next(iter(lock['sources']))] = '0' * 64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'engine-lock.json').write_text(json.dumps(lock))
            with patch.object(prepare, 'ROOT', root), self.assertRaisesRegex(ValueError, 'original source mismatch'):
                prepare.prepare(root / 'output')

    def test_source_output_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Generated source must be'):
            prepare.prepare(prepare.ROOT / 'src')

    def test_mygui_view_preserves_originals_and_caches_unchanged_headers(self):
        source = prepare.REPO / 'experiments/ios-openmw-world-smoke/artifacts/deps/mygui/MyGUIEngine/include'
        if not source.is_dir():
            # Portable CI supplies the exact verified tree through this variable.
            source = Path(os.environ['G6_MYGUI_HEADERS'])
        original = dependencies.inventory(source)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            expected = dependencies.mygui_view(source, output)
            before = {name: (output / name).stat().st_mtime_ns for name in expected}
            self.assertEqual(expected, dependencies.mygui_view(source, output))
            self.assertEqual(before, {name: (output / name).stat().st_mtime_ns for name in expected})
            self.assertEqual(original, dependencies.inventory(source))
            text = (output / 'MyGUI_UString.h').read_text(encoding='utf-8-sig')
            self.assertIn('using unicode_char = char32_t;', text)
            self.assertIn('using code_point = char16_t;', text)

    def test_mygui_source_and_view_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'must be separate'):
                dependencies.mygui_view(root, root)


class Dependencies(unittest.TestCase):
    def archive(self, name='source/header.h'):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as stream:
            stream.writestr(name, b'authored archive-integrity fixture')
        return buffer.getvalue()

    def fixture(self, root, raw):
        (root / 'fixture.zip').write_bytes(raw)
        lock = {'fixture': {'archive': 'fixture.zip', 'directory': 'verified', 'prefix': 'source',
            'url': 'https://invalid.example/unused-offline-fixture', 'bytes': len(raw),
            'algorithm': 'sha256', 'hash': hashlib.sha256(raw).hexdigest()}}
        (root / 'dependencies.json').write_text(json.dumps(lock))

    def test_archive_hash_is_required_before_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root, self.archive())
            (root / 'fixture.zip').write_bytes(b'changed')
            with patch.object(dependencies, 'ROOT', root), self.assertRaisesRegex(ValueError, 'archive size/hash mismatch'):
                dependencies.acquire(root, True)
            self.assertFalse((root / 'verified').exists())

    def test_extra_extracted_file_fails_exact_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root, self.archive())
            with patch.object(dependencies, 'ROOT', root):
                dependencies.acquire(root)
                (root / 'verified/unexpected').write_bytes(b'extra')
                with self.assertRaisesRegex(ValueError, 'inventory/hash mismatch'):
                    dependencies.acquire(root, True)

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root, self.archive('source/../escape'))
            with patch.object(dependencies, 'ROOT', root), self.assertRaisesRegex(ValueError, 'Unsafe dependency'):
                dependencies.acquire(root)
            self.assertFalse((root / 'escape').exists())

    def test_undeclared_tar_symlink_is_rejected(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as stream:
            entry = tarfile.TarInfo('source/link'); entry.type = tarfile.SYMTYPE; entry.linkname = '../outside'
            stream.addfile(entry)
        with self.assertRaisesRegex(ValueError, 'special member'):
            list(dependencies.entries(buffer.getvalue(), 'fixture.tar.gz'))


class ResultValidation(unittest.TestCase):
    def row(self, **overrides):
        return dict({'exit': 0, 'exit_hex': '0x0', 'stdout': '{"status":"PASS","checks":9}',
            'stderr': '', 'timeout': False, 'spawn_error': None}, **overrides)

    def test_exact_success_is_accepted(self):
        cases.validate_result('ownership', self.row())

    def test_wrong_assertion_inventory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'assertion inventory'):
            cases.validate_result('ownership', self.row(stdout='{"status":"PASS","checks":1}'))

    def test_native_access_violation_cannot_be_success(self):
        with self.assertRaisesRegex(ValueError, '0xc0000005'):
            cases.validate_result('ownership', self.row(exit=0xc0000005, exit_hex='0xc0000005', stdout=''))

    def test_expected_rejection_requires_the_exact_diagnostic(self):
        with self.assertRaisesRegex(ValueError, 'Wrong native rejection'):
            cases.validate_result('runtime-delete', self.row(exit=1, stderr='some unrelated error'))
        cases.validate_result('runtime-delete', self.row(exit=1, stderr=cases.NEGATIVE['runtime-delete']))

    def test_signal_cannot_satisfy_an_expected_rejection(self):
        with self.assertRaisesRegex(ValueError, 'Wrong native rejection'):
            cases.validate_result('runtime-delete', self.row(exit=-11, stderr=cases.NEGATIVE['runtime-delete']))

    def test_timeout_and_spawn_failure_are_not_rejections(self):
        for value in ({'timeout': True}, {'spawn_error': 'unavailable'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cases.validate_result('runtime-delete', self.row(exit=1, stderr=cases.NEGATIVE['runtime-delete'], **value))

    def test_empty_expected_diagnostic_cannot_accept_arbitrary_failure(self):
        with patch.dict(cases.NEGATIVE, {'runtime-delete': ''}), self.assertRaisesRegex(ValueError, 'Wrong native rejection'):
            cases.validate_result('runtime-delete', self.row(exit=1, stderr='ordinary failure'))

    def test_process_error_mode_is_restored(self):
        if os.name == 'nt':
            kernel = ctypes.WinDLL('kernel32'); kernel.GetErrorMode.restype = ctypes.c_uint32
            before = kernel.GetErrorMode()
            with cases.child_fault_capture():
                self.assertTrue(kernel.GetErrorMode() & 0x2)
            self.assertEqual(before, kernel.GetErrorMode())
        else:
            with cases.child_fault_capture():
                self.assertNotEqual(os.name, 'nt')


class BuildContracts(unittest.TestCase):
    def consumer(self, root, extra=()):
        return {'arguments': ['clang++', '-std=c++20', '-DBT_USE_DOUBLE_PRECISION',
            '-DMYGUI_STATIC', '-DMYGUI_USE_FREETYPE', '-DU_STATIC_IMPLEMENTATION',
            '-I' + str(root / 'mygui'), '-I' + str(root / 'osg'), *extra]}

    def test_real_standard_tokens_and_dependency_abi_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            entry = self.consumer(root)
            audit.consumer(entry, root, root / 'osg')
            for bad in ('-std=c++17', '-std=gnu++20', '-std=c++23', '-Dunrelated=c++20'):
                candidate = {'arguments': [bad if a == '-std=c++20' else a for a in entry['arguments']]}
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    audit.consumer(candidate, root, root / 'osg')
            for flag in ('-DBT_USE_DOUBLE_PRECISION', '-DMYGUI_STATIC', '-DMYGUI_USE_FREETYPE', '-DU_STATIC_IMPLEMENTATION'):
                with self.subTest(flag=flag), self.assertRaises(ValueError):
                    audit.consumer({'arguments': [a for a in entry['arguments'] if a != flag]}, root, root / 'osg')

    def test_original_mygui_abi_cannot_precede_compatible_core(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); entry = self.consumer(root)
            entry['arguments'].insert(0, '-I' + str(root / 'MyGUIEngine/include'))
            with self.assertRaisesRegex(ValueError, 'Original MyGUI ABI'):
                audit.consumer(entry, root, root / 'osg')

    def test_host_or_simulator_cannot_satisfy_iphoneos_consumer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); sdk = root / 'iPhoneOS.sdk'
            extra = ['-arch', 'arm64', '-isysroot', str(sdk), '-miphoneos-version-min=18.0']
            audit.consumer(self.consumer(root, extra), root, root / 'osg', sdk)
            for option, value in (('-arch', 'x86_64'), ('-isysroot', str(root / 'iPhoneSimulator.sdk'))):
                bad = extra.copy(); bad[bad.index(option) + 1] = value
                with self.subTest(option=option), self.assertRaises(ValueError):
                    audit.consumer(self.consumer(root, bad), root, root / 'osg', sdk)
            for bad in (['-target', 'arm64-apple-ios18.0-simulator'], ['-mmacosx-version-min=18.0']):
                with self.subTest(conflict=bad), self.assertRaises(ValueError):
                    audit.consumer(self.consumer(root, extra + bad), root, root / 'osg', sdk)

    def test_apple_preflight_cannot_be_claimed_on_windows(self):
        with patch.object(native.sys, 'platform', 'win32'), self.assertRaisesRegex(ValueError, 'Real macOS'):
            native.run(Path('unused'), Path('iPhoneOS.sdk'), Path('unused'))

    def test_configuration_requires_one_actual_target_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
                audit.configuration(root)
            (root / 'g6-config-Release.json').write_text('{"generated":"C:/safe/path"}')
            self.assertEqual(audit.configuration(root)['generated'], 'C:/safe/path')
            (root / 'nested').mkdir()
            (root / 'nested/g6-config-Release.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
                audit.configuration(root)


class Packaging(unittest.TestCase):
    def symbols(self, undefined=False, omit=None):
        names = ['_osgdb_' + name for name in ('dds', 'tga', 'bmp', 'png', 'jpeg', 'osg', 'osg2')]
        names += ['_wrapper_serializer_library_osg', '_wrapper_serializer_BufferIndexBinding']
        names += ['__ZN7MWWorld8ESMStore4load', '__ZN7MWWorld8ESMStore5setUp',
            '__ZN7MWWorld10WorldModel11registerPtr', '__ZN7MWWorld9CellStore4load',
            '__ZN7MWWorld15LiveCellRefBaseD1Ev']
        names = [n for n in names if n != omit]
        strings = bytearray(b'\0'); records = bytearray()
        for name in names:
            records += struct.pack('<IBBHQ', len(strings), 1 if undefined else 0x0f,
                0 if undefined else 1, 0, 0)
            strings += name.encode() + b'\0'
        header = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 2, 1, 24, 0, 0)
        command = struct.pack('<6I', 2, 24, 56, len(names), 56 + len(records), len(strings))
        return header + command + records + strings

    def test_defined_engine_ownership_and_all_static_registrations_are_required(self):
        # Authored symbol-table contract fixture, never a substitute Apple product.
        self.assertEqual(len(package.registrations(self.symbols())['registrations']), 9)
        for missing in ('_osgdb_dds', '_wrapper_serializer_BufferIndexBinding',
                '__ZN7MWWorld10WorldModel11registerPtr', '__ZN7MWWorld9CellStore4load'):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                package.registrations(self.symbols(omit=missing))

    def test_undefined_references_cannot_count_as_retained_implementations(self):
        with self.assertRaisesRegex(ValueError, 'registrations absent'):
            package.registrations(self.symbols(undefined=True))

    def test_truncated_symbol_table_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Invalid G6 symbol table'):
            package.registrations(self.symbols()[:-10])

    def test_no_sdk_cannot_accept_package(self):
        with self.assertRaisesRegex(ValueError, 'genuine Apple SDK'):
            package.validate({}, Path('unused'), None)

    def test_proprietary_files_or_extra_bundle_members_are_rejected(self):
        manifest = {'baseline_g5_build': {'public_resources_sha256': {}}, 'public_resources_sha256': {}}
        entries = {'g6-build.json': package.p.Entry(json.dumps(manifest).encode(), 0o100644),
            'Morrowind.esm': package.p.Entry(b'authored forbidden-name fixture', 0o100644)}
        with patch.object(package.p, 'prepared_resources', return_value=({}, {})), \
                patch.object(package.provenance, 'baseline_contract'), \
                patch.object(package.provenance, 'new_resources', return_value=set()), \
                self.assertRaisesRegex(ValueError, 'Exact G6 public bundle inventory'):
            package.validate(entries, Path('unused'), Path('iPhoneOS.sdk'))


if __name__ == '__main__':
    unittest.main()
