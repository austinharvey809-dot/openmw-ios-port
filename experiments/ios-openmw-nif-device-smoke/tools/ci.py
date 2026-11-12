"""G0C source, syntax and observed native-configuration gates; no device claims."""
import argparse
import ast
import json
from pathlib import Path
import subprocess

from common import ROOT, REPO, G0B, load, require, sha


def sources(osg):
    from prepare import audit
    result = audit(osg)
    for path in (ROOT / 'tools').glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return {**result, 'scope': 'Source/syntax checks only; native/device gates separate'}


def configured(build, bullet_source):
    validator = load('_g0c_bullet_precision_audit', G0B / 'tools/validate_build.py')
    counts = validator.audit(build, bullet_source)
    cache = (build / 'CMakeCache.txt').read_text()
    for setting in ('CMAKE_SYSTEM_NAME:UNINITIALIZED=iOS', 'CMAKE_OSX_ARCHITECTURES:STRING=arm64',
                    'CMAKE_OSX_DEPLOYMENT_TARGET:STRING=18.0', 'OPENTHREADS_ATOMIC_USE_MUTEX:BOOL=ON'):
        # CMake may record command-line selections as UNINITIALIZED until the platform consumes them.
        name, value = setting.split('=', 1)
        key = name.split(':')[0]
        require(any(line.startswith(key + ':') and line.endswith('=' + value) for line in cache.splitlines()),
                'Device setting missing: ' + setting)
    headers = build / 'cmake/osg/include'
    from prepare import GENERATED
    for header in GENERATED:
        require((headers / header).is_file(), 'Generated header missing: ' + header)
    commands = json.loads((build / 'compile_commands.json').read_text())
    for entry in commands:
        name = Path(entry['file']).as_posix()
        if '/components/nif/' in name or name.endswith('/nif_parse_check.cpp') or name.endswith('/NifProbe.cpp'):
            command = entry.get('command', ' '.join(entry.get('arguments', [])))
            require(str(headers) in command and 'iphoneos' in command.lower(), 'Missing device/generated include flags: ' + name)
    return {'valid': True, 'precision_commands': counts, 'scope': 'Configured iPhoneOS sources; compilation not implied'}


def collect(build, evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    for path in build.rglob('*'):
        if path.is_file() and (path.name in {'CMakeCache.txt', 'CMakeConfigureLog.yaml', 'compile_commands.json',
                                          'openmw-nif-device-link-check'} or 'prepared' in path.relative_to(build).parts):
            target = evidence / path.relative_to(build)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    return {'scope': 'Available diagnostics only'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('sources', 'configured', 'collect'))
    parser.add_argument('--osg-source', type=Path)
    parser.add_argument('--bullet-source', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    try:
        result = sources(args.osg_source) if args.phase == 'sources' else (
            configured(args.build, args.bullet_source) if args.phase == 'configured' else collect(args.build, args.evidence))
        (args.evidence / (args.phase + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    except Exception as error:
        (args.evidence / (args.phase + '.json')).write_text(json.dumps({'valid': False, 'error': str(error)}) + '\n')
        raise
