"""Offline full-file and transitive-include audit of the real Milestone E closure."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
MANIFEST = ROOT / 'data/source-audit.json'
ADDITIONAL = (
    'components/esm3/loadstat.cpp',
    'components/bsa/bsafile.cpp',
    'components/files/constrainedfilestreambuf.cpp',
    'components/platform/fileposix.cpp',
    'components/vfs/manager.cpp',
    'experiments/ios-openmw-bsa-vfs/src/register_bsa.cpp',
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


esm_audit = load_module('milestone_d_source_audit', REPO / 'experiments/ios-openmw-esm/tools/audit_sources.py')
AuditError = esm_audit.AuditError
require = esm_audit.require


def safe_path(name):
    require(isinstance(name, str) and '\\' not in name
            and (name.startswith('components/') or name.startswith('experiments/ios-openmw-bsa-vfs/')),
            'Unexpected project path')
    path = (REPO / name).resolve()
    require(path.is_relative_to(REPO) and path.is_file(), 'Missing/unsafe source: ' + name)
    return path


def closure(sources):
    pending, visited, external = list(sources), set(), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        path = safe_path(name)
        visited.add(name)
        for delimiter, include in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]',
                                            path.read_text(encoding='utf-8'), re.M):
            if include.startswith('components/'):
                pending.append(include)
            elif delimiter == '"':
                target = (path.parent / include).resolve()
                require(target.is_relative_to(REPO), 'Quoted dependency escapes repository')
                pending.append(target.relative_to(REPO).as_posix())
            else:
                external.add(include)
    return visited, external


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def audit(manifest=None, osg_source=None):
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    require(manifest['schema_version'] == 1, 'Unknown audit schema')
    # Retain D's exact source/header/OSG revision and Config-template checks.
    previous = esm_audit.audit(osg_source=osg_source)
    old = json.loads(esm_audit.MANIFEST.read_text(encoding='utf-8'))
    require(manifest['osg_revision'] == esm_audit.OSG_REVISION, 'OSG pin mismatch')
    require(manifest['inherited_sources'] == old['sources'], 'Inherited fifteen-source contract changed')
    require(manifest['additional_sources'] == list(ADDITIONAL), 'Additional six-source contract changed')
    sources = manifest['inherited_sources'] + manifest['additional_sources']
    require(len(sources) == len(set(sources)) == 21, 'Overlapping/incorrect translation units')
    visited, external = closure(sources)
    require(set(manifest['project_sha256_lf']) == visited, 'Transitive source/header inventory mismatch')
    require(manifest['headers'] == sorted(visited - set(sources)), 'Header inventory mismatch')
    require(manifest['external_includes'] == sorted(external), 'External dependency inventory mismatch')
    for name in sorted(visited):
        require(digest(safe_path(name)) == manifest['project_sha256_lf'][name], 'Source integrity mismatch: ' + name)
    for name, expected in manifest['reused_build_sha256_lf'].items():
        path = (REPO / name).resolve()
        require(path.is_relative_to(REPO) and path.is_file() and digest(path) == expected,
                'Reused build/fixture integrity mismatch: ' + name)
    require(set(manifest['reused_build_sha256_lf']) == {
        'experiments/ios-openmw-esm/CMakeLists.txt',
        'experiments/ios-openmw-esm/data/source-audit.json',
        'experiments/ios-openmw-esm/tools/audit_sources.py',
        'experiments/ios-openmw-esm/tools/fixtures.py',
        'experiments/ios-openmw-bsa-vfs/tools/fixtures.py',
    }, 'Reused build/fixture inventory mismatch')
    return {'source_hashes_verified': len(visited), 'translation_units': len(sources),
            'genuine_engine_translation_units': 20, 'registration_policy_translation_units': 1,
            'headers': len(manifest['headers']), 'external_includes': sorted(external),
            'osg_revision': esm_audit.OSG_REVISION, 'osg_checkout_verified': previous['osg_checkout_verified'],
            'native_compilation_performed': False, 'scope': 'Source audit only; not compilation or runtime evidence'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osg-source', type=Path)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    try:
        result = audit(osg_source=args.osg_source)
        require(not args.require_complete or args.osg_source is not None, 'Pinned OSG checkout required')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, KeyError, TypeError, ValueError) as error:
        print('ESM/VFS audit failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
