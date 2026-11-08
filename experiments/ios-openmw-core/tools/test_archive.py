"""Synthetic archive/Mach-O regressions; no SDK, downloads or compiler needed."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import validate_archive as validator


def object_file(cpu=0x0100000C, subtype=0, target=2, minimum=18 << 16, kind=1, commands=None):
    if commands is None:
        commands = [struct.pack('<6I', 0x32, 24, target, minimum, 26 << 16, 0)]
    payload = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, subtype, kind, len(commands), len(payload), 0, 0) + payload


def member(name, data, bsd=False):
    if bsd:
        encoded = name.encode() + b'\0\0'
        label = '#1/' + str(len(encoded))
        data = encoded + data
    else:
        label = name
    header = (f'{label:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n').encode()
    if len(header) != 60:
        raise AssertionError('Use a BSD name fixture for long names')
    return header + data + (b'\n' if len(data) % 2 else b'')


def archive(replace=None, names=None):
    names = names or [Path(source).stem + '.o' for source in validator.SOURCES]
    contents = b'!<arch>\n' + member('__.SYMDEF SORTED', b'symbol-index', bsd=True)
    for index, name in enumerate(names):
        contents += member(name, (replace or {}).get(index, object_file()), bsd=True)
    return contents


class ArchiveTests(unittest.TestCase):
    def test_device_metadata_and_exact_five_source_inventory(self):
        data = archive()
        report = validator.validate(data)
        self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual({item['source'] for item in report['objects']}, set(validator.SOURCES))
        for item in report['objects']:
            self.assertEqual((item['architecture'], item['platform'], item['minimum_os']), ('arm64', 'IOS', '18.0'))
            self.assertEqual(item['sha256'], hashlib.sha256(object_file()).hexdigest())
        # SDK=0 is permitted for relocatable objects; device platform/minimum are mandatory.
        zero_sdk = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 0)
        self.assertEqual(validator.inspect_object(object_file(commands=[zero_sdk]))['sdk'], '0.0.0')

    def test_arm64_macos_simulator_catalyst_and_other_platforms_are_rejected(self):
        for target in (1, 3, 4, 6, 7, 8, 11, 12):
            with self.subTest(target=target), self.assertRaisesRegex(validator.ValidationError, 'not iOS device'):
                validator.validate(archive({3: object_file(target=target)}))

    def test_wrong_architecture_arm64e_file_type_and_deployment_rejected(self):
        for data in (object_file(cpu=0x01000007), object_file(subtype=2), object_file(kind=6),
                     object_file(minimum=17 << 16), object_file(minimum=(18 << 16) | (1 << 8)),
                     object_file(minimum=19 << 16)):
            with self.subTest(data=data), self.assertRaises(validator.ValidationError):
                validator.validate(archive({0: data}))

    def test_missing_duplicate_legacy_or_malformed_load_commands_rejected(self):
        build = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 26 << 16, 0)
        bad = [object_file(commands=[]), object_file(commands=[build, build]),
               object_file(commands=[struct.pack('<4I', 0x25, 16, 18 << 16, 26 << 16)]),
               object_file(commands=[struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 1)]),
               object_file()[:-1], b'BC\xc0\xde' + b'\0' * 60]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(validator.ValidationError):
                validator.inspect_object(data)

    def test_missing_extra_duplicate_and_aliased_source_objects_rejected(self):
        names = [Path(source).stem + '.o' for source in validator.SOURCES]
        for variant in (names[:-1], names + ['unrelated.o'], names + [names[0]],
                        names + ['conversion.cpp.o']):
            with self.subTest(names=variant), self.assertRaises(validator.ValidationError):
                validator.validate(archive(names=variant))
        cpp_names = [Path(source).name + '.o' for source in validator.SOURCES]
        self.assertTrue(validator.validate(archive(names=cpp_names))['valid'])

    def test_archive_names_bounds_and_fat_input_fail_closed(self):
        for data in (b'\xca\xfe\xba\xbe' + b'\0' * 60, archive()[:-1], b'!<arch>\n' + b'x' * 59,
                     b'!<arch>\n' + member('../escape.o', object_file(), bsd=True),
                     b'!<arch>\n' + member('a\\escape.o', object_file(), bsd=True),
                     b'!<arch>\n' + member('/999', object_file()),
                     b'!<arch>\n' + member('#1/999', b'x')):
            with self.subTest(data=data[:32]), self.assertRaises(validator.ValidationError):
                validator.archive_objects(data)

    def test_gnu_names_and_symbol_table_are_decoded_without_extraction(self):
        table, bodies = b'', b''
        for source in validator.SOURCES:
            name = Path(source).name + '.o'
            offset = len(table)
            table += name.encode() + b'/\n'
            bodies += member('/' + str(offset), object_file())
        data = b'!<arch>\n' + member('/', b'index') + member('//', table) + bodies
        self.assertTrue(validator.validate(data)['valid'])

    def test_cli_keeps_per_object_tool_evidence_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'device.a'
            source.write_bytes(archive())
            output = root / 'inspection'
            def run(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'tool evidence\n', '')
            with patch('sys.argv', ['validate_archive', '--archive', str(source), '--evidence', str(output)]), \
                    patch.object(validator.platform, 'system', return_value='Darwin'), \
                    patch.object(validator.subprocess, 'run', side_effect=run) as mocked:
                self.assertEqual(validator.main(), 0)
            self.assertTrue(json.loads((output / 'archive-validation.json').read_text())['valid'])
            self.assertEqual(len(list((output / 'objects').glob('*.otool.txt'))), 5)
            commands = [call.args[0] for call in mocked.call_args_list]
            self.assertEqual(sum('otool' in command and '-l' in command for command in commands), 5)
            self.assertIn(['xcrun', 'lipo', str(source), '-verify_arch', 'arm64'], commands)

    def test_cli_records_failure_and_never_substitutes_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('sys.argv', ['validate_archive', '--archive', str(root / 'missing'), '--evidence', str(root)]), \
                    patch.object(validator.platform, 'system', return_value='Windows'), \
                    patch.object(validator.subprocess, 'run', side_effect=AssertionError('Unexpected tool/download')):
                self.assertEqual(validator.main(), 1)
            report = json.loads((root / 'archive-validation.json').read_text())
            self.assertFalse(report['valid'])

    def test_cli_retains_raw_object_evidence_when_platform_validation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'bad-platform.a'
            source.write_bytes(archive({4: object_file(target=7)}))
            output = root / 'inspection'
            def run(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, 'arm64\n' if '-archs' in command else 'raw inspection\n', '')
            with patch('sys.argv', ['validate_archive', '--archive', str(source), '--evidence', str(output)]), \
                    patch.object(validator.platform, 'system', return_value='Darwin'), \
                    patch.object(validator.subprocess, 'run', side_effect=run):
                self.assertEqual(validator.main(), 1)
            report = json.loads((output / 'archive-validation.json').read_text())
            self.assertFalse(report['valid'])
            self.assertIn('not iOS device', report['error'])
            self.assertEqual(len(list((output / 'objects').glob('*.otool.txt'))), 5)
            self.assertTrue((output / 'archive-tools.log').is_file())


if __name__ == '__main__':
    unittest.main()
