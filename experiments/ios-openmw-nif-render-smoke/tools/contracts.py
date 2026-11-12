"""Read-only G1A provenance; reuse completed audits without modifying their sources."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
G0B = ROOT.parent / 'ios-openmw-nif-smoke'
DATA = G0B / 'data'
LOCK = json.loads((ROOT / 'data/source-lock.json').read_text(encoding='utf-8'))
GENERATED = ('OpenThreads/Config', 'OpenThreads/Version', 'osg/Config', 'osg/GL', 'osg/Version')
NEGATIVES = ('vertex-count', 'vertex-metadata', 'triangle-grouping', 'triangle-metadata',
             'nonfinite-nan', 'nonfinite-infinity', 'index-range', 'repeated-index', 'collinear',
             'root-translation', 'shape-scale', 'root-offdiagonal', 'shape-rotation', 'nan-transform',
             'wrong-version', 'missing-root', 'wrong-root-type', 'missing-child',
             'missing-data-reference', 'missing-record')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], check=True, capture_output=True).stdout


def fixture_snapshot(directory=DATA):
    require(directory.is_dir() and not directory.is_symlink(), 'Unsafe fixture directory')
    result, canonical = {}, {}
    for path in directory.iterdir():
        require(path.is_file() and not path.is_symlink(), 'Unsafe fixture entry: ' + path.name)
        data = path.read_bytes()
        result[path.name] = {'size': len(data), 'sha256': sha(data)}
        checked = data.replace(b'\r\n', b'\n') if path.name in LOCK['fixture_text_lf'] else data
        canonical[path.name] = {'size': len(checked), 'sha256': sha(checked)}
    require(canonical == LOCK['fixtures'], 'Fixture inventory/hash/size mismatch')
    return result


def preservation():
    entries = json.loads((ROOT / 'data/preserved-source-sha256.json').read_text())
    require(len(entries) == 191, 'Preservation inventory changed')
    for name, record in entries.items():
        path = REPO / name
        require(path.is_file() and not path.is_symlink(), 'Missing/linked preserved file: ' + name)
        data = path.read_bytes()
        require(sha(data.replace(b'\r\n', b'\n') if record['text'] else data) == record['sha256'],
                'Preserved source changed: ' + name)
    return len(entries)


def local_build15():
    entries = json.loads((ROOT / 'data/build15-local-sha256.json').read_text())
    require(len(entries) == 9, 'Wrong local Build #15 preservation inventory')
    for name, digest in entries.items():
        path = REPO / name
        require(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest,
                'Local Build #15 source changed: ' + name)
    return len(entries)


def graphics_baseline():
    commit = LOCK['graphics_baseline_commit']
    require(commit == '8799e90148c3ea1985b2547fa8e9b31be19b45c2', 'Wrong graphics baseline commit')
    names = git('ls-tree', '-r', '--name-only', commit, '--', 'experiments/ios-osg-smoke').decode().splitlines()
    require(set(names) == set(LOCK['graphics_baseline_files']), 'Graphics baseline inventory changed')
    blobs = {}
    for name, record in LOCK['graphics_baseline_files'].items():
        blob = git('show', commit + ':' + name)
        require(sha(blob) == record['sha256'] and
                git('rev-parse', commit + ':' + name).decode().strip() == record['git_blob'],
                'Committed graphics blob changed: ' + name)
        blobs[name] = blob
    osg = json.loads(blobs['experiments/ios-osg-smoke/data/osg-lock.json'])
    angle = json.loads(blobs['experiments/ios-osg-smoke/data/angle-lock.json'])
    require(osg['overlay_version'] == LOCK['graphics_overlay_version'] == 2, 'Not version-2 graphics')
    require(osg['revision'] == LOCK['osg_revision'] and angle['angle_revision'] == LOCK['angle_revision']
            and angle['depot_tools_revision'] == LOCK['depot_tools_revision'], 'Graphics dependency pin changed')
    require(not LOCK['graphics_sources_copied'], 'G1A does not import graphics or observer sources')
    return len(blobs)


def audit(osg, check_local=False):
    # G0C's reusable audit verifies A-E(53), F/G0B(47), NIF(59), E/VFS and clean pinned OSG.
    sys.path.insert(0, str(ROOT.parent / 'ios-openmw-nif-device-smoke/tools'))
    diagnostics = io.StringIO()
    try:
        completed = load('_g1a_completed_audit', ROOT.parent / 'ios-openmw-nif-device-smoke/tools/prepare.py')
        with contextlib.redirect_stdout(diagnostics):
            upstream = completed.audit(osg)
    finally:
        sys.path.pop(0)
    require(LOCK['osg_revision'] == completed.OSG_REVISION and
            LOCK['bullet_url'] == completed.bullet.URL and LOCK['bullet_sha512'] == completed.bullet.SHA512,
            'Dependency lock differs from completed source contracts')
    require(re.fullmatch('[0-9a-f]{40}', LOCK['preparation_source_commit']), 'Invalid preparation commit')
    git('cat-file', '-e', LOCK['preparation_source_commit'] + '^{commit}')
    git('merge-base', '--is-ancestor', LOCK['preparation_source_commit'], 'HEAD')
    return {'scope': 'G1A source/provenance only; native geometry unverified',
            'source_commit': git('rev-parse', 'HEAD').decode().strip(),
            'preparation_source_commit': LOCK['preparation_source_commit'],
            'graphics_baseline_commit': LOCK['graphics_baseline_commit'],
            'graphics_v2_blobs': graphics_baseline(), 'preserved_sources': preservation(),
            'fixtures': fixture_snapshot(), 'completed_audits': upstream,
            'completed_audit_diagnostics': diagnostics.getvalue(),
            'dependency_pins': {key: LOCK[key] for key in ('osg_revision', 'angle_revision',
                'depot_tools_revision', 'bullet_url', 'bullet_sha512')},
            'build15_local': local_build15() if check_local else 'not checked on CI; local snapshot retained'}


def build_audit(build, bullet_source):
    completed = load('_g1a_g0b_build_audit', G0B / 'tools/validate_build.py')
    precision = completed.audit(build, bullet_source)
    headers = {}
    for name in GENERATED:
        path = build / 'g0b/osg/include' / name
        require(path.is_file() and not path.is_symlink(), 'Missing genuine generated header: ' + name)
        headers[name] = sha(path.read_bytes())
    commands = json.loads((build / 'compile_commands.json').read_text())
    for name in ('GeometryAdapter.cpp', 'geometry_check.cpp'):
        selected = [entry for entry in commands if Path(entry['file']).name == name]
        require(len(selected) == 1, 'Missing/duplicate G1A compile unit: ' + name)
        command = selected[0].get('command', ' '.join(selected[0].get('arguments', [])))
        require('c++20' in command and 'BT_USE_DOUBLE_PRECISION' in command, 'Wrong G1A language/precision')
        require(str(build / 'g0b/osg/include') in command, 'G1A lacks actual generated OSG headers')
    return {'precision_compile_commands': precision, 'generated_headers_sha256': headers,
            'scope': 'Configured host build only; no native execution claim'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osg-source', type=Path, required=True)
    parser.add_argument('--check-local-build15', action='store_true')
    parser.add_argument('--build', type=Path)
    parser.add_argument('--bullet-source', type=Path)
    args = parser.parse_args()
    report = audit(args.osg_source, args.check_local_build15)
    if args.build:
        require(args.bullet_source is not None, 'Build audit requires Bullet source')
        report['build'] = build_audit(args.build.resolve(), args.bullet_source.resolve())
    print(json.dumps(report, indent=2))
