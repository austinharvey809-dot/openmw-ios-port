"""Offline real-source/header provenance audit; successful checks are not compilation/link evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
MANIFEST = ROOT / 'data/source-audit.json'
OSG_REVISION = '9b384d5439977784e5cd250ff8ff7966928ddd27'
STANDARD = set('algorithm array cassert charconv concepts condition_variable cstddef cstdint cstring filesystem '
               'fstream functional ios iosfwd iostream istream iterator limits list locale map memory mutex '
               'optional ostream span sstream stdexcept stdint.h string string_view system_error tuple '
               'type_traits unordered_set utility variant vector'.split())


class AuditError(ValueError):
    pass


def require(value, message):
    if not value:
        raise AuditError(message)


def project_path(name):
    require(isinstance(name, str) and name.startswith('components/') and '\\' not in name,
            'Invalid project source path')
    path = (REPO / name).resolve()
    require(path.is_relative_to(REPO) and path.is_file(), 'Missing/unsafe project source: ' + name)
    return path


def audit_osg(source, manifest):
    source = Path(source).resolve()
    require(source.is_dir(), 'Missing pinned OSG checkout: ' + str(source))
    try:
        command = ['git', '-c', 'safe.directory=' + source.as_posix(), '-C', str(source), 'rev-parse', 'HEAD']
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuditError('Cannot verify local OSG Git revision: ' + str(error)) from error
    require(result.stdout.strip() == OSG_REVISION, 'OSG checkout revision mismatch')
    expected = manifest['osg_sha256_lf']
    require(set(expected) == {'include/osg/Vec3f', 'include/osg/Vec2f', 'include/osg/Math', 'include/osg/Export',
                              'src/osg/Config.in', 'CMakeLists.txt', 'LICENSE.txt'}, 'Unexpected OSG inventory')
    for name, digest in expected.items():
        path = source / name
        require(path.is_file() and path.resolve().is_relative_to(source), 'Missing/unsafe OSG file: ' + name)
        require(hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest,
                'OSG source integrity mismatch: ' + name)
    pending, visited, external = ['include/osg/Vec3f'], set(), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        require(name in expected, 'Unexpected OSG math dependency: ' + name)
        visited.add(name)
        for _, include in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]',
                                    (source / name).read_text(encoding='utf-8'), re.M):
            if include == 'osg/Config':
                pending.append('src/osg/Config.in')
            elif include.startswith('osg/'):
                pending.append('include/' + include)
            else:
                external.add(include)
    require(visited == set(expected) - {'CMakeLists.txt', 'LICENSE.txt'} and external == {'cmath', 'cfloat'},
            'OSG math header closure changed')
    switches = re.findall(r'^#cmakedefine (\w+)', (source / 'src/osg/Config.in').read_text(encoding='utf-8'), re.M)
    require(set(switches) == set(manifest['osg_config_defines']), 'OSG Config template switches changed')
    require(all(type(value) is bool for value in manifest['osg_config_defines'].values()), 'Invalid Config switch value')
    return source


def audit(manifest=None, osg_source=None):
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    require(manifest['schema_version'] == 1, 'Unsupported source-audit schema')
    require(manifest['osg_revision'] == OSG_REVISION, 'Pinned OSG revision mismatch')
    lock = json.loads((REPO / 'experiments/ios-osg-smoke/data/osg-lock.json').read_text(encoding='utf-8'))
    require(lock['revision'] == OSG_REVISION, 'Existing OSG experiment uses an unexpected revision')
    require(manifest['link_closure_verified'] is False and manifest['osg_transitive_headers_verified'] is True,
            'Source/header provenance is known; native linking remains unverified')
    sources, headers = manifest['sources'], manifest['headers']
    require(len(sources) == len(set(sources)) == 15, 'Expected fifteen candidate translation units')
    require(len(headers) == len(set(headers)) == 38, 'Expected thirty-eight project headers')
    expected = set(sources) | set(headers)
    require(len(expected) == 53 and set(manifest['project_sha256_lf']) == expected, 'Inconsistent project inventory')
    require(set(manifest['standard_includes']) == STANDARD, 'Standard-header inventory changed')
    require(manifest['external_include_roots'] == ['osg/Vec3f'], 'Unexpected external dependency inventory')
    pending = list(sources)
    visited, external = set(), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        path = project_path(name)
        data = path.read_bytes().replace(b'\r\n', b'\n')
        require(name in expected, 'Unrecorded project dependency: ' + name)
        require(hashlib.sha256(data).hexdigest() == manifest['project_sha256_lf'][name],
                'Source integrity mismatch: ' + name)
        visited.add(name)
        for delimiter, include in re.findall(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', data.decode('utf-8'), re.M):
            if include.startswith('components/'):
                pending.append(include)
            elif delimiter == '"':
                target = (path.parent / include).resolve()
                require(target.is_relative_to(REPO), 'Quoted include escapes repository')
                pending.append(target.relative_to(REPO).as_posix())
            else:
                external.add(include)
    require(visited == expected, 'Recorded project header closure does not match current sources')
    require(external == STANDARD | {'osg/Vec3f'}, 'External dependency closure changed')
    if osg_source is not None:
        audit_osg(osg_source, manifest)
    return {
        'project_source_audit_valid': True,
        'audit_baseline_commit': manifest['openmw_audit_commit'],
        'candidate_translation_units': len(sources),
        'project_headers': len(headers),
        'source_hashes_verified': len(visited),
        'hash_normalization': manifest['hash_normalization'],
        'osg_revision': OSG_REVISION,
        'external_include_roots': ['osg/Vec3f'],
        'osg_header_closure_audited': True,
        'osg_checkout_verified': osg_source is not None,
        'generated_config': 'CMake configure_file from verified upstream src/osg/Config.in; generated output not compiled here',
        'link_closure_verified': False,
        'native_ready': False,
        'scope': 'Real project/OSG source audit; no native compilation/link/runtime proof',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osg-source', type=Path, help='Existing separate checkout of the exact pinned OSG revision')
    parser.add_argument('--resolve', type=Path, help='Write verified OSG include/template paths for CMake')
    parser.add_argument('--require-complete', action='store_true',
                        help='Require the genuine pinned source/header checkout; success is not a native link claim')
    args = parser.parse_args()
    try:
        result = audit(osg_source=args.osg_source)
        print(json.dumps(result, indent=2))
        if (args.require_complete or args.resolve) and args.osg_source is None:
            print('BLOCKED: provide the genuine pinned OSG checkout with --osg-source.')
            return 1
        if args.resolve:
            source = args.osg_source.resolve().as_posix()
            require(not any(c in source for c in '\n\r;"$'), 'OSG path contains unsupported CMake metacharacters')
            args.resolve.parent.mkdir(parents=True, exist_ok=True)
            args.resolve.write_text('set(OSG_MATH_SOURCE_INCLUDE "' + source + '/include")\n'
                                   'set(OSG_MATH_CONFIG_TEMPLATE "' + source + '/src/osg/Config.in")\n', encoding='utf-8')
        return 0
    except (OSError, KeyError, TypeError, AuditError, json.JSONDecodeError) as error:
        print('ESM source audit failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
