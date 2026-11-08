"""Validate exactly one real BSA translation unit; reuse unchanged Milestone A Mach-O checks."""
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
SOURCE = 'components/bsa/bsafile.cpp'


def validate(data):
    objects = core.archive_objects(data)
    core.require(len(objects) == 1, 'BSA archive must contain exactly one translation unit')
    name, payload = objects[0]
    core.require(name in {'bsafile.o', 'bsafile.cpp.o'}, 'Unexpected BSA archive object: ' + name)
    return {
        'valid': True,
        'sha256': hashlib.sha256(data).hexdigest(),
        'objects': [{'member': name, 'source': SOURCE, 'sha256': hashlib.sha256(payload).hexdigest(),
                     **core.inspect_object(payload)}],
        'scope': 'BSA static compilation only; separate five-object data-core validation required; no iPhone execution',
    }


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
        objects = core.archive_objects(data)  # Validates names before writing any object.
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
        print('BSA archive validation failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
