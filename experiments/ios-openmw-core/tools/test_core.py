"""No-download contracts and optional execution of the actual OpenMW source subset."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CMAKE = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
SOURCES = re.search(r'set\(OPENMW_CORE_SOURCES\s+(.*?)\n\)', CMAKE, re.S)[1].split()


class CoreTests(unittest.TestCase):
    def test_source_scope_is_actual_data_code(self):
        self.assertEqual(SOURCES, ['components/files/conversion.cpp', 'components/files/openfile.cpp',
                                  'components/files/constrainedfilestreambuf.cpp',
                                  'components/platform/fileposix.cpp', 'components/vfs/manager.cpp'])
        for source in SOURCES:
            self.assertTrue((REPO / source).is_file(), source)

    def test_transitive_project_headers_require_no_external_dependency(self):
        pending = [REPO / source for source in SOURCES] + [ROOT / 'tests/core_check.cpp']
        visited = set()
        standard = set()
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            for delimiter, name in re.findall(r'^\s*#include\s*([<"])([^>"]+)[>"]', source.read_text(encoding='utf-8'), re.M):
                if name.startswith('components/'):
                    target = REPO / name
                    self.assertTrue(target.is_file(), target)
                    pending.append(target)
                elif delimiter == '"':
                    target = source.parent / name
                    self.assertTrue(target.is_file(), target)
                    pending.append(target)
                else:
                    standard.add(name)
        self.assertTrue({'unistd.h', 'sys/types.h', 'filesystem', 'charconv'} <= standard)
        self.assertFalse(any(name.startswith(('boost/', 'osg/', 'SDL', 'MyGUI', 'lua', 'unicode/', 'libav')) for name in standard))
        self.assertGreater(len(visited), len(SOURCES))

    def test_device_default_fails_closed_and_host_execution_is_explicit(self):
        for value in ('CMAKE_SYSTEM_NAME STREQUAL "iOS"', 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"',
                      'CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0"', '_sdk MATCHES "iphoneos"',
                      'if(NOT UNIX OR CMAKE_CROSSCOMPILING)', 'cxx_std_20'):
            self.assertIn(value, CMAKE)
        self.assertIn('option(OPENMW_IOS_CORE_HOST_TESTS "Explicit POSIX host build and runtime check; not iPhone evidence" OFF)', CMAKE)
        self.assertIn('add_library(openmw-ios-data-core STATIC', CMAKE)
        self.assertIn('if(OPENMW_IOS_CORE_HOST_TESTS)\n    enable_testing()', CMAKE)
        self.assertIn('if(NOT OPENMW_IOS_CORE_HOST_TESTS)\n    set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0"', CMAKE)
        for forbidden in ('FetchContent', 'ExternalProject', 'find_package(', 'add_subdirectory(', 'execute_process(', 'eglSwapBuffers'):
            self.assertNotIn(forbidden, CMAKE)

    def test_real_source_runtime_on_available_posix_host(self):
        if os.name == 'nt':
            self.skipTest('POSIX runtime fixture requires macOS/Linux; no Windows dependency installation')
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            self.skipTest('No host C++20 compiler; source contracts do not prove compilation')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'core-check'
            subprocess.run([compiler, '-std=c++20', '-I', str(REPO),
                            *(str(REPO / name) for name in SOURCES), str(ROOT / 'tests/core_check.cpp'),
                            '-o', str(binary)], check=True)
            result = subprocess.run([str(binary), str(Path(directory) / 'probe.bin')],
                                    check=True, text=True, capture_output=True)
            self.assertIn('OpenMW data-core host checks passed', result.stdout)
            self.assertEqual((Path(directory) / 'probe.bin').read_bytes(), b'0123456789')


if __name__ == '__main__':
    unittest.main()
