"""Synthetic format/contracts plus an optional genuine OpenMW reader runtime test."""
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
CORE_CMAKE = (ROOT.parent / 'ios-openmw-core/CMakeLists.txt').read_text(encoding='utf-8')
CORE_SOURCES = re.search(r'set\(OPENMW_CORE_SOURCES\s+(.*?)\n\)', CORE_CMAKE, re.S)[1].split()
SOURCES = [*CORE_SOURCES, 'components/bsa/bsafile.cpp']


class BSATests(unittest.TestCase):
    def test_real_source_and_milestone_a_reuse_without_dependency_fetches(self):
        self.assertIn('add_library(openmw-ios-bsa-reader STATIC "${OPENMW_ROOT}/components/bsa/bsafile.cpp")', CMAKE)
        self.assertIn('target_link_libraries(openmw-ios-bsa-reader PUBLIC openmw-ios-data-core)', CMAKE)
        self.assertIn('set(OPENMW_IOS_CORE_HOST_TESTS "${OPENMW_IOS_BSA_HOST_TESTS}")', CMAKE)
        self.assertIn('../ios-openmw-core', CMAKE)
        self.assertIn('EXCLUDE_FROM_ALL', CMAKE)
        self.assertIn('cxx_std_20', CMAKE)
        self.assertIn('if(NOT OPENMW_IOS_BSA_HOST_TESTS)\n    set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0"', CMAKE)
        self.assertIn('--reader "$<TARGET_FILE:openmw-bsa-check>"', CMAKE)
        for forbidden in ('FetchContent', 'ExternalProject', 'ios-osg-smoke', 'ios-angle-smoke',
                          'compressedbsafile.cpp', 'file(COPY', 'file(WRITE', '-include', 'try_run'):
            self.assertNotIn(forbidden, CMAKE)
        self.assertEqual(len(SOURCES), 6)

    def test_full_project_header_closure_requires_only_standard_and_posix_headers(self):
        pending = [REPO / source for source in SOURCES] + [ROOT / 'tests/bsa_check.cpp']
        visited, external = set(), set()
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            for delimiter, name in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', source.read_text(encoding='utf-8'), re.M):
                if name.startswith('components/'):
                    target = REPO / name
                    self.assertTrue(target.is_file(), str(target))
                    pending.append(target)
                elif delimiter == '"':
                    target = source.parent / name
                    self.assertTrue(target.is_file(), str(target))
                    pending.append(target)
                else:
                    external.add(name)
        standard = {'algorithm', 'array', 'bit', 'cassert', 'cerrno', 'charconv', 'cstddef',
                    'cstdint', 'cstdlib', 'cstring', 'filesystem', 'format', 'fstream', 'functional',
                    'ios', 'iosfwd', 'iostream', 'istream', 'iterator', 'limits', 'locale', 'map',
                    'memory', 'optional', 'ostream', 'sstream', 'stdexcept', 'streambuf', 'string',
                    'string_view', 'system_error', 'type_traits', 'utility', 'vector',
                    'errno.h', 'fcntl.h', 'string.h', 'sys/types.h', 'unistd.h'}
        self.assertEqual(external - standard, set())
        self.assertTrue({'format', 'bit', 'filesystem', 'unistd.h'} <= external)
        self.assertIn(REPO / 'components/esm/fourcc.hpp', visited)
        self.assertNotIn(REPO / 'components/vfs/bsaarchive.hpp', visited)

    def test_synthetic_archive_has_independent_expected_layout_and_payloads(self):
        raw = fixtures.synthetic_archive()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '96a0d6067f84e12b60c7822cd5bef5d8c9926ce091d78194d2af98a959ba2824')
        self.assertEqual(struct.unpack_from('<III', raw), (0x100, 66, 2))
        self.assertEqual(len(raw), 140)
        payload_base = 12 + 66 + 2 * 8
        rows = [struct.unpack_from('<II', raw, 12 + index * 8) for index in range(2)]
        self.assertEqual(rows, [(36, 10), (10, 0)])  # directory order != data order
        names_start = 12 + 2 * 12
        for index, (size, offset) in enumerate(rows):
            name_offset = struct.unpack_from('<I', raw, 12 + 2 * 8 + index * 4)[0]
            name = raw[names_start + name_offset:12 + 66].split(b'\0', 1)[0]
            expected = dict(fixtures.ENTRIES)[name]
            self.assertEqual(raw[payload_base + offset:payload_base + offset + size], expected)
        self.assertEqual(fixtures.name_hash(b'a'), (0, 0x80000030))
        self.assertEqual(fixtures.name_hash(b'ab'), (ord('a'), 0x80000018))

    def test_malformed_fixtures_are_bounded_and_cover_reader_rejections(self):
        cases = fixtures.cases()
        self.assertEqual(len(cases), 8)
        good = cases['valid.bsa'][0]
        self.assertFalse(cases['valid.bsa'][1])
        self.assertTrue(all(reject for name, (_, reject) in cases.items() if name != 'valid.bsa'))
        self.assertEqual(len(cases['short-header.bsa'][0]), 11)
        self.assertGreater(struct.unpack_from('<I', cases['oversized-directory.bsa'][0], 4)[0], len(good))
        self.assertGreater(struct.unpack_from('<I', cases['payload-outside.bsa'][0], 12)[0], len(good))
        self.assertNotIn(b'\0', cases['unterminated-name.bsa'][0][36:78])
        self.assertEqual(struct.unpack_from('<I', cases['name-outside.bsa'][0], 28)[0], 42)
        self.assertTrue(all(len(data) <= 140 for data, _ in cases.values()))

    def test_reader_fixture_uses_real_api_and_never_calls_archive_writer(self):
        code = (ROOT / 'tests/bsa_check.cpp').read_text(encoding='utf-8')
        for value in ('Bsa::BSAFile reader;', 'reader.open(path);', 'reader.getList()',
                      'reader.getFile(&entry)', 'reader.close();', 'std::filesystem::is_regular_file(path)',
                      'std::endian::native == std::endian::little'):
            self.assertIn(value, code)
        self.assertNotIn('addFile(', code)
        self.assertNotIn('writeHeader(', code)
        self.assertNotIn('std::ofstream', code)
        self.assertIn('no ESM/NIF/world loaded', code)

    def test_case_runner_checks_process_result_and_input_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(command, **kwargs):
                return subprocess.CompletedProcess(command, 0,
                    'REJECTED by OpenMW BSA reader' if command[-1] == 'reject' else 'OpenMW BSA payload checks passed', '')
            with patch.object(fixtures.subprocess, 'run', side_effect=run) as mocked, contextlib.redirect_stdout(io.StringIO()):
                fixtures.run_cases(root / 'reader', root / 'cases')
            self.assertEqual(mocked.call_count, 8)
            for name, (expected, _) in fixtures.cases().items():
                self.assertEqual((root / 'cases' / name).read_bytes(), expected)
            with patch.object(fixtures.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'compile/runtime blocker')), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'Real reader fixture failed'):
                fixtures.run_cases(root / 'reader', root / 'bad-status')
            def mutate(command, **kwargs):
                Path(command[1]).write_bytes(b'changed')
                return subprocess.CompletedProcess(command, 0, 'OpenMW BSA payload checks passed', '')
            with patch.object(fixtures.subprocess, 'run', side_effect=mutate), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'changed an input fixture'):
                fixtures.run_cases(root / 'reader', root / 'changed')

    def test_actual_openmw_bsa_reader_on_available_posix_compiler(self):
        if os.name == 'nt':
            self.skipTest('Real BSA C++ compile/runtime fixture requires an existing POSIX host compiler')
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('No C++20 host compiler; no downloads or fake reader substitute')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'bsa-check'
            subprocess.run([compiler, '-std=c++20', '-I', str(REPO),
                            *(str(REPO / source) for source in SOURCES), str(ROOT / 'tests/bsa_check.cpp'),
                            '-o', str(binary)], check=True)
            fixtures.run_cases(binary, root / 'fixtures')


if __name__ == '__main__':
    unittest.main()
