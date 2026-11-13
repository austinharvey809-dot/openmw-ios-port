"""G1B preservation, prepared resources and actual single-provider configuration audits."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
G1A = ROOT.parent
REPO = G1A.parents[1]
sys.path.insert(0, str(G1A / 'tools'))
import contracts as host
from run_geometry import expected_geometry_hash

require, sha = host.require, host.sha
ORIGINS = json.loads((ROOT / 'data/source-origins.json').read_text())
PIN = 'fa3451ab825750f241b37ef6021c6b7ff48724f5'


def files(root):
    require(root.is_dir() and not root.is_symlink(), 'Missing/linked resource tree')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked resource: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
        else:
            require(path.is_dir(), 'Nonregular resource')
    return result


def audit(osg, local=False):
    report = host.audit(osg, check_local=local)
    host.git('merge-base', '--is-ancestor', PIN, 'HEAD')
    require(ORIGINS['g1a_validated_commit'] == PIN and
            ORIGINS['graphics_baseline_commit'] == host.LOCK['graphics_baseline_commit'], 'Wrong source origins')
    preserved = json.loads((ROOT / 'data/preserved-source-sha256.json').read_text())
    require(len(preserved) == 204, 'G1B preservation inventory changed')
    for name, entry in preserved.items():
        path = REPO / name
        require(path.is_file() and not path.is_symlink(), 'Missing preserved source: ' + name)
        data = path.read_bytes()
        require(sha(data.replace(b'\r\n', b'\n') if entry['text'] else data) == entry['sha256'],
                'Completed source changed: ' + name)
    baseline = host.LOCK['graphics_baseline_commit']
    for name, entry in ORIGINS['source_origins'].items():
        original = host.git('show', baseline + ':' + entry['source'])
        actual = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
        if entry['kind'] == 'exact Git blob copy':
            require(actual == original, 'Copied v2 baseline changed: ' + name)
        elif name == 'src/AngleRenderer.hpp':
            text = original.decode()
            expected = '#pragma once\n' + text[text.index('class Renderer {'):text.index('@interface MetalView')].rstrip('\n') + '\n'
            require(actual.decode() == expected, 'External EGL ownership implementation changed')
    for path in (ROOT / 'tools').glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    return {'g1a_validated_commit': PIN, 'preserved_sources': len(preserved), 'host_source_contracts': report,
            'scope': 'G1B source audit; no native or physical rendering claim'}


def checked_headers(generated):
    result = {}
    for name in host.GENERATED:
        path = generated / name
        require(path.is_file() and not path.is_symlink(), 'Missing genuine generated header: ' + name)
        result[name] = path.read_bytes()
    expected = json.loads((REPO / 'experiments/ios-openmw-esm/data/source-audit.json').read_text())['osg_config_defines']
    text = result['osg/Config'].decode()
    for name, enabled in expected.items():
        require(bool(re.search(r'^#define\s+' + name + r'(?:\s|$)', text, re.M)) == enabled,
                'OSG math/configuration mismatch: ' + name)
    gl = result['osg/GL'].decode()
    require('#include <GLES3/gl3.h>' in gl and '#include <GLES2/gl2ext.h>' in gl,
            'Generated GL header is not the selected ANGLE GLES3 configuration')
    require('#include <OpenGLES/' not in gl and '#include <OpenGL/' not in gl, 'Apple GL fallback in generated header')
    return result


def prepare(args):
    source_audit = audit(args.osg_reference)
    subprocess.run([sys.executable, str(ROOT / 'baseline/tools/check_osg_source.py'),
                    '--source', str(args.osg_renderer)], check=True)
    # Resolve uses the existing exact package inventory, roles and provenance checks.
    with __import__('tempfile').TemporaryDirectory() as temp:
        subprocess.run([sys.executable, str(REPO / 'experiments/ios-angle-smoke/tools/validate_dependency.py'),
                        '--root', str(args.angle), '--resolve', str(Path(temp) / 'resolved.cmake')], check=True)
    output = args.output.resolve()
    require(not output.is_relative_to(REPO) or output.is_relative_to(ROOT / 'artifacts')
            or output.is_relative_to(ROOT / 'build'), 'Prepared files must remain in build/artifact storage')
    for source in (args.osg_reference, args.osg_renderer, args.angle, args.bullet, host.DATA):
        require(not output.is_relative_to(source.resolve()), 'Output cannot alter dependencies or fixtures')
    resources = {'Fixtures/' + name: data for name, data in files(host.DATA).items()}
    angle_files = files(args.angle)
    for name, data in angle_files.items():
        if name.startswith('Frameworks/'):
            resources[name] = data
        elif name.startswith('Licenses/'):
            resources['Licenses/ANGLE/' + name.removeprefix('Licenses/')] = data
    for name in ('angle-lock.json', 'angle-build.json', 'package-hashes.json', 'dependency-validation.json', 'args.gn'):
        resources['Provenance/ANGLE/' + name] = angle_files[name]
    angle_build = json.loads(angle_files['angle-build.json'])
    require(angle_build['angle_revision'] == host.LOCK['angle_revision'] and
            angle_build['validation'] == 'device-binary-and-sdk-passed', 'Unverified ANGLE package')
    resources['Licenses/OpenMW-LICENSE.txt'] = (REPO / 'LICENSE').read_bytes()
    resources['Licenses/OSG-LICENSE.txt'] = (args.osg_renderer / 'LICENSE.txt').read_bytes()
    for name, data in files(args.osg_renderer / 'include/OpenThreads').items():
        resources['Licenses/OpenThreads/' + name] = data
    bullet = json.loads((args.bullet.parent / 'bullet-provenance.json').read_text())
    require(bullet['archive_sha512'] == host.LOCK['bullet_sha512']
            and bullet['source_url'] == host.LOCK['bullet_url']
            and Path(bullet['source_directory']).resolve() == args.bullet.resolve(), 'Bullet provenance mismatch')
    resources['Provenance/bullet-provenance.json'] = (args.bullet.parent / 'bullet-provenance.json').read_bytes()
    notices = sorted(p for p in args.bullet.rglob('*') if p.is_file() and p.name.lower() in ('license', 'license.txt', 'copying'))
    require(notices and all(not p.is_symlink() for p in notices), 'Missing/linked Bullet notices')
    for index, path in enumerate(notices):
        resources['Licenses/Bullet-%d.txt' % index] = path.read_bytes()
    resources['Provenance/osg-lock.json'] = (ROOT / 'baseline/data/osg-lock.json').read_bytes()
    resources['Provenance/ios-osg-overlay.json'] = (args.osg_renderer / 'ios-osg-overlay.json').read_bytes()
    for name, data in checked_headers(args.generated).items():
        resources['Provenance/generated/' + name] = data
    metadata = {'schema_version': 1, 'source_commit': host.git('rev-parse', 'HEAD').decode().strip(),
                'g1a_validated_commit': PIN, 'graphics_baseline_commit': host.LOCK['graphics_baseline_commit'],
                'osg_revision': host.LOCK['osg_revision'], 'overlay_version': 2, 'profile': 'GLES3',
                'platform_target': 'iPhoneOS-arm64', 'minimum_os': '18.0',
                'dependency_pins': {name: host.LOCK[name] for name in ('angle_revision', 'depot_tools_revision',
                    'bullet_url', 'bullet_sha512')},
                'angle_libraries': angle_build['libraries'], 'geometry_sha256': expected_geometry_hash(),
                'fixture_snapshot': host.fixture_snapshot(), 'source_audit': source_audit,
                'source_sha256_lf': {p.relative_to(REPO).as_posix(): sha(p.read_bytes().replace(b'\r\n', b'\n'))
                    for p in ROOT.rglob('*') if p.is_file() and not {'artifacts', 'build', '__pycache__'} & set(p.relative_to(ROOT).parts)},
                'adapter_sha256_lf': sha((G1A / 'src/GeometryAdapter.cpp').read_bytes().replace(b'\r\n', b'\n')),
                'resources_sha256': {name: sha(data) for name, data in sorted(resources.items())},
                'scope': 'Prepared G1B build provenance; physical rendering unverified'}
    workflow = REPO / '.github/workflows/ios-openmw-nif-render-device-smoke.yml'
    metadata['source_sha256_lf'][workflow.relative_to(REPO).as_posix()] = sha(workflow.read_bytes().replace(b'\r\n', b'\n'))
    resources['g1b-build.json'] = (json.dumps(metadata, sort_keys=True, indent=2) + '\n').encode()
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / 'resources').exists() or set(files(output / 'resources')) <= set(resources),
            'Unexpected stale prepared resource inventory')
    for name, data in resources.items():
        path = output / 'resources' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if name in angle_build['libraries'].values():
            path.chmod(0o755)
    include = output / 'include'
    include.mkdir(exist_ok=True)
    (include / 'G1AExpectations.hpp').write_text('#pragma once\nnamespace G1A { inline constexpr char ExpectedNifSHA256[] = "'
        + host.LOCK['fixtures']['triangle-candidate.nif']['sha256'] + '"; }\n')
    constants = {'BuildSHA256': sha(resources['g1b-build.json']), 'SourceCommit': metadata['source_commit'],
                 'GeometrySHA256': metadata['geometry_sha256']}
    (include / 'G1BExpectations.hpp').write_text('#pragma once\nnamespace G1BExpected {\n' + ''.join(
        'inline constexpr char ' + name + '[] = "' + value + '";\n' for name, value in constants.items()) + '}\n')
    return {'prepared_resource_files': len(resources), 'metadata_sha256': sha(resources['g1b-build.json'])}


def require_cxx20(tokens):
    standards = [token for token in tokens if token.startswith(('-std=', '--std='))
                 or token in ('-std', '--std')]
    require(len(standards) == 1 and standards[0] in ('-std=c++20', '-std=c++2a'),
            'Consumer requires exactly one strict C++20 standard option (-std=c++20 or -std=c++2a)')


def configured(build, bullet):
    original = host.load('_g1b_precision_audit', REPO / 'experiments/ios-openmw-nif-smoke/tools/validate_build.py')
    precision = original.audit(build, bullet)
    headers = checked_headers(build / 'osg/include')
    cache = (build / 'CMakeCache.txt').read_text()
    for name, value in (('CMAKE_SYSTEM_NAME', 'iOS'), ('CMAKE_OSX_ARCHITECTURES', 'arm64'),
                        ('CMAKE_OSX_DEPLOYMENT_TARGET', '18.0'), ('OPENGL_PROFILE', 'GLES3'),
                        ('OSG_WINDOWING_SYSTEM', 'None'), ('OPENTHREADS_ATOMIC_USE_MUTEX', 'ON')):
        require(any(line.startswith(name + ':') and line.endswith('=' + value) for line in cache.splitlines()),
                'Configured device setting missing: ' + name)
    commands = json.loads((build / 'compile_commands.json').read_text())
    # Exactly one provider compiles each OSG/OpenThreads translation unit.
    from collections import Counter
    counts = Counter(str(Path(entry['file']).resolve()) for entry in commands)
    require(all(count == 1 for name, count in counts.items() if '/src/osg/' in name or '/src/OpenThreads/' in name),
            'Duplicate OSG/OpenThreads provider translation units')
    selected = []
    for entry in commands:
        name = Path(entry['file']).as_posix()
        if any(part in name for part in ('/components/nif/', '/components/esm', '/components/vfs/',
                                        '/components/bsa/', '/GeometryAdapter.cpp', '/NifProbe.cpp',
                                        '/geometry_check.cpp', '/device/src/main.mm')):
            command = entry.get('command', ' '.join(entry.get('arguments', [])))
            canonical = str(build / 'osg/include')
            tokens = shlex.split(command)
            includes = [token[2:] if token != '-I' else tokens[index + 1]
                        for index, token in enumerate(tokens) if token.startswith('-I')]
            require(canonical in includes and all(includes.index(canonical) < index
                    for index, path in enumerate(includes) if '/osg-math/include' in path),
                    'Math-only configuration shadows renderer')
            require_cxx20(tokens)
            require('OpenGLES.framework' not in command and '-framework OpenGL' not in command, 'Alternate GL provider')
            selected.append(name)
    require(any(n.endswith('GeometryAdapter.cpp') for n in selected) and any(n.endswith('/device/src/main.mm') for n in selected),
            'Missing actual adapter/app compile commands')
    return {'precision': precision, 'canonical_consumers': selected,
            'generated_sha256': {name: sha(data) for name, data in headers.items()},
            'scope': 'Configured iPhoneOS build only; no native or device execution claim'}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('audit', 'prepare', 'configured'))
    cli.add_argument('--osg-reference', type=Path, required=True)
    cli.add_argument('--local-build15', action='store_true')
    for name in ('osg-renderer', 'angle', 'bullet', 'generated', 'output', 'build'):
        cli.add_argument('--' + name, type=Path)
    args = cli.parse_args()
    report = audit(args.osg_reference, args.local_build15) if args.phase == 'audit' else (
        prepare(args) if args.phase == 'prepare' else configured(args.build.resolve(), args.bullet.resolve()))
    print(json.dumps(report, indent=2))
