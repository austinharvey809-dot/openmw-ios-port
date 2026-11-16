"""Reuse an existing verified Windows provider/toolchain; install nothing."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def configure(cmake, existing, build):
    cache = {}
    for line in (existing / 'CMakeCache.txt').read_text().splitlines():
        if '=' in line and ':' in line and not line.startswith('//'):
            key, value = line.split('=', 1)
            cache[key.split(':')[0]] = value
    names = ('CMAKE_C_COMPILER', 'CMAKE_CXX_COMPILER', 'CMAKE_MAKE_PROGRAM', 'CMAKE_BUILD_TYPE',
        'CMAKE_POLICY_VERSION_MINIMUM', 'G0_BULLET_SOURCE', 'G4_CPU_AR', 'G4_CPU_PROVIDER',
        'G4_CPU_RANLIB', 'G4_DEPENDENCIES_SOURCE', 'G4_OSG_SOURCE', 'G5_LUA_SOURCE', 'Python3_EXECUTABLE')
    if not all(cache.get(name) for name in names):
        raise ValueError('Existing verified Windows provider configuration incomplete')
    if build.resolve().is_relative_to(REPO) and not build.resolve().is_relative_to(
            REPO / 'experiments/ios-openmw-world-smoke/artifacts'):
        raise ValueError('Honor the accepted G4 generated-shader output restriction')
    command = [str(cmake), '-S', str(ROOT), '-B', str(build), '-G', 'Ninja']
    command += ['-D' + name + '=' + cache[name] for name in names]
    command += ['-DCMAKE_AR=' + cache['G4_CPU_AR'], '-DCMAKE_RANLIB=' + cache['G4_CPU_RANLIB'],
        '-DG6_DEPENDENCIES_SOURCE=' + str(ROOT / 'artifacts/runtime-deps'),
        '-DCMAKE_NINJA_FORCE_RESPONSE_FILE=ON', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
    result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL)
    (ROOT / 'artifacts/configure.log').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode(errors='replace')[-6000:])
    return command


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cmake', type=Path, required=True)
    parser.add_argument('--existing-build', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    configure(args.cmake, args.existing_build, args.build)
    print('G6 Windows configuration passed; no source or existing build was modified.')
