"""Offline encoding/source contracts and optional real native POSIX CMake/CTest execution."""
import contextlib
import hashlib
import io
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

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CMAKE = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
REGISTER = (ROOT / 'src/register_bsa.cpp').read_text(encoding='utf-8')
CHECKER = (ROOT / 'tests/vfs_check.cpp').read_text(encoding='utf-8')
CORE_CMAKE = (ROOT.parent / 'ios-openmw-core/CMakeLists.txt').read_text(encoding='utf-8')
CORE_SOURCES = re.search(r'set\(OPENMW_CORE_SOURCES\s+(.*?)\n\)', CORE_CMAKE, re.S)[1].split()
ENGINE_SOURCES = [*CORE_SOURCES, 'components/bsa/bsafile.cpp',
                  'components/toutf8/toutf8.cpp', 'components/debug/debuglog.cpp']


class VFSChecks(unittest.TestCase):
    def test_target_reuses_real_sources_and_existing_platform_guards(self):
        self.assertEqual(len(ENGINE_SOURCES), 8)
        for name in ('components/toutf8/toutf8.cpp', 'components/debug/debuglog.cpp',
                     'src/register_bsa.cpp', 'PUBLIC openmw-ios-bsa-reader Threads::Threads',
                     'find_package(Threads REQUIRED)', 'cxx_std_20', 'EXCLUDE_FROM_ALL',
                     'set(OPENMW_IOS_BSA_HOST_TESTS "${OPENMW_IOS_BSA_VFS_HOST_TESTS}")',
                     'set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0"', 'NAME openmw-bsa-vfs-runtime',
                     '--reader "$<TARGET_FILE:openmw-bsa-vfs-check>"'):
            self.assertIn(name, CMAKE)
        for forbidden in ('FetchContent', 'ExternalProject', 'registerarchives.cpp', 'filesystemarchive.cpp',
                          'compressedbsafile.cpp', 'ba2gnrlfile.cpp', 'ba2dx10file.cpp', 'debugging.cpp',
                          'file(WRITE', 'FORCE', '-Wno-', '-include '):
            self.assertNotIn(forbidden, CMAKE)

    def test_complete_selected_include_closure_is_standard_posix_only(self):
        pending = [REPO / name for name in ENGINE_SOURCES] + [ROOT / 'src/register_bsa.cpp', ROOT / 'tests/vfs_check.cpp']
        visited, external = set(), set()
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            for delim, name in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', source.read_text(encoding='utf-8'), re.M):
                if name.startswith('components/'):
                    target = REPO / name
                elif delim == '"':
                    target = source.parent / name
                    if not target.is_file():
                        target = ROOT / 'src' / name
                else:
                    external.add(name)
                    continue
                self.assertTrue(target.is_file(), str(target))
                pending.append(target)
        allowed = set('algorithm bit cassert cerrno charconv cstdint cstdlib cstring errno.h fcntl.h filesystem '
                      'format fstream ios iosfwd iostream istream iterator limits list locale map memory mutex '
                      'optional ostream set span sstream stdexcept streambuf string string.h string_view '
                      'sys/types.h system_error unistd.h utility vector'.split())
        self.assertEqual(external - allowed, set())
        self.assertTrue({'mutex', 'span', 'format', 'unistd.h'} <= external)
        self.assertEqual(len(visited), 36)
        for name in ('components/vfs/bsaarchive.hpp', 'components/toutf8/tablesgen.hpp',
                     'components/debug/debuglog.hpp', 'components/bsa/compressedbsafile.hpp',
                     'components/bsa/ba2gnrlfile.hpp', 'components/bsa/ba2dx10file.hpp'):
            self.assertIn(REPO / name, visited)  # Interface inclusion is not a linked decoder.

    def test_registration_is_typed_and_preflight_precedes_archive_construction(self):
        self.assertIn('std::make_unique<VFS::BsaArchive<Bsa::BSAFile>>(path, &encoder)', REGISTER)
        self.assertLess(REGISTER.index('is_regular_file(path)'), REGISTER.index('detectVersion(path)'))
        self.assertLess(REGISTER.index('detectVersion(path)'), REGISTER.index('manager.addArchive'))
        self.assertIn('Bsa::BsaVersion::Uncompressed', REGISTER)
        self.assertNotIn('makeBsaArchive(', REGISTER)
        self.assertNotIn('registerArchives(', REGISTER)
        for forbidden in ('addFile(', 'std::ofstream', 'writeHeader(', 'create_directories', 'remove('):
            self.assertNotIn(forbidden, REGISTER + CHECKER)

    def test_real_checked_in_encoding_table_and_logging_reference(self):
        text = (REPO / 'components/toutf8/tablesgen.hpp').read_text(encoding='utf-8')
        table = re.search(r'windows_1252\[\]\s*=\s*\{([^}]+)\}', text, re.S)[1]
        values = [int(value) for value in re.findall(r'-?\d+', table)]
        self.assertEqual(len(values), 256 * 6)
        row = values[0xE9 * 6:(0xE9 + 1) * 6]
        self.assertEqual(row[0], 2)
        self.assertEqual(bytes(value & 255 for value in row[1:3]), b'\xc3\xa9')
        encoder = (REPO / 'components/toutf8/toutf8.cpp').read_text(encoding='utf-8')
        self.assertIn('#include "tablesgen.hpp"', encoder)
        self.assertIn('Log(Debug::Info)', encoder)
        self.assertIn('static std::mutex sLock;', (REPO / 'components/debug/debuglog.cpp').read_text(encoding='utf-8'))

    def test_deterministic_archives_and_encoded_filename_payload_layout(self):
        expected = {
            'base.bsa': (219, '73f8038e732f3414e1ccacd0f85801fcd7deff77f54ba23c0ebae67e2604d63e'),
            'overlay.bsa': (155, '4467e9d9bb78c329de2a3dea8a486e4729094ad5ac20d8e15c1590f5c442c740'),
            'unsupported.bsa': (219, '732d9bc541aef1d5ac08be4741563dbb49b036212940528c97fd9d6999b1daf9'),
            'unexpected.bsa': (300, '0022ac5e119ee6bd032a8248aacff7d972cb3bbb58b613c3f0b4ba2f4081c0c4'),
            'incomplete.bsa': (153, '391e026dcbc7f07d0adcad777858629f7bc40382b60f69db3ea95b251f513d46'),
        }
        for name, data in fixtures.archives().items():
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), expected[name])
        for entries in (fixtures.BASE, fixtures.OVERLAY):
            data = fixtures.archive(entries)
            magic, directory, count = struct.unpack_from('<III', data)
            self.assertEqual((magic, count), (0x100, len(entries)))
            self.assertGreaterEqual(directory, 12 * count)  # No undersized-directory allocation test.
            names_start, payload_start = 12 + 12 * count, 12 + directory + 8 * count
            seen = {}
            for index in range(count):
                size, offset = struct.unpack_from('<II', data, 12 + index * 8)
                name_offset, = struct.unpack_from('<I', data, 12 + 8 * count + index * 4)
                name = data[names_start + name_offset:12 + directory].split(b'\0', 1)[0]
                seen[name] = data[payload_start + offset:payload_start + offset + size]
            self.assertEqual(seen, dict(entries))
        self.assertEqual(fixtures.BASE[1][0].decode('cp1252'), 'Textures\\Caf\u00e9X.TXT')
        self.assertNotEqual(fixtures.BASE[0][1], fixtures.OVERLAY[0][1])
        self.assertEqual((len(fixtures.BASE[0][1]), len(fixtures.OVERLAY[0][1])), (10, 28))

    def test_fixture_covers_genuine_manager_lookup_normalization_and_encoding(self):
        for value in ('ToUTF8::StatelessUtf8Encoder encoder(ToUTF8::WINDOWS_1252)',
                      'manager.buildIndex()', 'manager.exists(key)', 'manager.find(', 'manager.get(key)',
                      'manager.getStem(', 'manager.getLastModified(', 'manager.getArchive(',
                      'getRecursiveDirectoryIterator()', 'checkIndex(manager, basePayloads)',
                      'ASCII case/slash/leading-separator normalization differs',
                      'Dot components unexpectedly resolved', 'No Unicode case folding',
                      'NormalizedView must not accept an unnormalized path'):
            self.assertIn(value, CHECKER)
        self.assertLess(CHECKER.index('const ToUTF8::StatelessUtf8Encoder encoder'), CHECKER.index('integration(argv'))
        header = (ROOT / 'src/register_bsa.hpp').read_text(encoding='utf-8')
        self.assertIn('encoder is borrowed', header)
        self.assertIn('alive until the manager resets/destroys this archive', header)

    def test_fixture_bounds_stream_lifetimes_and_reversed_duplicate_precedence(self):
        for value in ('expected.size() + 8', 'stream->gcount()', 'buffer.substr(expected.size())',
                      'expected.size() + 1', 'stream->seekg(-1, std::ios::end)',
                      'Entry EOF leaked adjacent bytes', 'Old index remains until rebuild',
                      'manager.reset()', 'contents(*retained) == baseMesh',
                      'contents(*afterDestruction) == baseMesh', 'Last-added duplicate archive should win',
                      'Reversed registration order should reverse duplicate precedence'):
            self.assertIn(value, CHECKER)

    def test_runner_requires_six_successful_processes_and_full_input_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(command, **kwargs):
                marker = {'verify': 'OpenMW BSA/VFS integration passed;',
                          'reject-archive': 'REJECTED by existing-file/original-format input policy',
                          'reject-index': 'REJECTED unexpected/missing synthetic VFS index entry'}[command[1]]
                return subprocess.CompletedProcess(command, 0, marker, '')
            with patch.object(fixtures.subprocess, 'run', side_effect=run) as mocked, contextlib.redirect_stdout(io.StringIO()):
                fixtures.run_cases(root / 'reader', root / 'inputs')
            self.assertEqual(mocked.call_count, 6)
            self.assertFalse((root / 'inputs/must-not-be-created.bsa').exists())
            for name, data in fixtures.archives().items():
                self.assertEqual((root / 'inputs' / name).read_bytes(), data)

    def test_runner_rejects_nonzero_missing_evidence_mutation_and_created_archive(self):
        for variant in ('failed-process', 'no-marker', 'mutated', 'created'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def run(command, **kwargs):
                    if variant == 'mutated':
                        (root / 'inputs/base.bsa').write_bytes(b'changed')
                    elif variant == 'created':
                        (root / 'inputs/must-not-be-created.bsa').write_bytes(b'new')
                    return subprocess.CompletedProcess(command, 1 if variant == 'failed-process' else 0,
                        '' if variant == 'no-marker' else 'OpenMW BSA/VFS integration passed;', '')
                with patch.object(fixtures.subprocess, 'run', side_effect=run), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    fixtures.run_cases(root / 'reader', root / 'inputs')

    def test_actual_native_posix_cmake_link_and_runtime_when_tools_exist(self):
        if os.name == 'nt':
            self.skipTest('C++ fixture unexecuted: a native POSIX compiler/CMake is required')
        compiler = shutil.which('clang++') or shutil.which('g++')
        cmake, ctest = shutil.which('cmake'), shutil.which('ctest')
        if not all((compiler, cmake, ctest)):
            self.skipTest('Existing POSIX C++20/CMake/CTest toolchain unavailable; no downloads')
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([cmake, '-S', str(ROOT), '-B', directory,
                            '-DOPENMW_IOS_BSA_VFS_HOST_TESTS=ON', '-DCMAKE_BUILD_TYPE=Release',
                            '-DCMAKE_CXX_COMPILER=' + compiler], check=True)
            subprocess.run([cmake, '--build', directory, '--config', 'Release',
                            '--target', 'openmw-bsa-vfs-check', '--parallel', '3'], check=True)
            subprocess.run([ctest, '--test-dir', directory, '-C', 'Release', '--verbose',
                            '--output-on-failure', '--no-tests=error', '-R', '^openmw-bsa-vfs-runtime$'], check=True)


if __name__ == '__main__':
    unittest.main()
