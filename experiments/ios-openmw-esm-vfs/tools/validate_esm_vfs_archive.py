"""Strict six-object Milestone E validation using unchanged Milestone A Mach-O inspection."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess

CORE_PATH = Path(__file__).resolve().parents[2] / 'ios-openmw-core/tools/validate_archive.py'
SPEC = importlib.util.spec_from_file_location('openmw_core_archive_validation', CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)
SOURCES = (
    'components/esm3/loadstat.cpp',
    'components/bsa/bsafile.cpp',
    'components/files/constrainedfilestreambuf.cpp',
    'components/platform/fileposix.cpp',
    'components/vfs/manager.cpp',
    'experiments/ios-openmw-bsa-vfs/src/register_bsa.cpp',
)


def validate(data):
    objects = core.archive_objects(data)
    core.require(len(objects) == 6, 'Milestone E archive must contain exactly six translation units')
    found, result = set(), []
    for name, payload in objects:
        candidates = [source for source in SOURCES
                      if name in {Path(source).name + '.o', Path(source).stem + '.o'}]
        core.require(len(candidates) == 1, 'Unexpected Milestone E archive object: ' + name)
        source = candidates[0]
        core.require(source not in found, 'Multiple objects for the same translation unit: ' + source)
        found.add(source)
        result.append({'member': name, 'source': source, 'sha256': hashlib.sha256(payload).hexdigest(),
                       **core.inspect_object(payload)})
    core.require(found == set(SOURCES), 'Milestone E archive source inventory mismatch')
    return {'valid': True, 'sha256': hashlib.sha256(data).hexdigest(), 'objects': result,
            'scope': 'ESM-to-VFS static compilation only; no combined iPhoneOS executable link or runtime proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = args.evidence / 'archive-validation.json'

    def tool(arguments, log):
        completed = subprocess.run(['xcrun', *arguments], capture_output=True, text=True)
        with log.open('a', encoding='utf-8') as stream:
            stream.write('$ xcrun ' + ' '.join(map(str, arguments)) + '\n')
            stream.write(completed.stdout + completed.stderr)
        core.require(completed.returncode == 0, f'xcrun {arguments[0]} failed; see {log.name}')
        return completed.stdout.strip()

    try:
        core.require(platform.system() == 'Darwin', 'Native archive inspection requires existing macOS Xcode tools')
        data = args.archive.read_bytes()
        objects = core.archive_objects(data)  # Validate names before writing any extracted object.
        log = args.evidence / 'archive-tools.log'
        tool(['lipo', str(args.archive), '-info'], log)
        core.require(tool(['lipo', str(args.archive), '-archs'], log) == 'arm64',
                     'Archive contains architectures other than ARM64')
        tool(['lipo', str(args.archive), '-verify_arch', 'arm64'], log)
        tool(['ar', '-t', str(args.archive)], log)
        output = args.evidence / 'objects'
        output.mkdir(exist_ok=True)
        for index, (name, payload) in enumerate(objects):
            path = output / f'{index:02d}-{name}'
            path.write_bytes(payload)
            tool(['otool', '-hv', str(path)], output / f'{path.name}.otool.txt')
            tool(['otool', '-l', str(path)], output / f'{path.name}.otool.txt')
        result = validate(data)
        report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, core.ValidationError) as error:
        report.write_text(json.dumps({'valid': False, 'error': str(error)}, indent=2) + '\n', encoding='utf-8')
        print('ESM/VFS archive validation failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
