"""Audit preserved sources and stage only proven G0B synthetic resources."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from common import ROOT, REPO, G0B, OSG_REVISION, HOST_COMMIT, load, sha, require, tree

g0 = load('_g0c_source_audit', G0B / 'tools/audit_g0.py')
e = load('_g0c_e_audit', ROOT.parent / 'ios-openmw-esm-vfs/tools/audit_sources.py')
bullet = load('_g0c_bullet', G0B / 'tools/prepare_bullet.py')
GENERATED = ('OpenThreads/Config', 'OpenThreads/Version', 'osg/Config', 'osg/GL', 'osg/Version')


def audit(osg):
    g0.verify()
    e.audit(osg_source=osg)
    prior = json.loads((ROOT.parent / 'ios-openmw-data-smoke/data/prior-milestones.json').read_text())
    require(len(prior['sha256_lf']) == 53, 'A-E preservation inventory changed')
    for name, digest in prior['sha256_lf'].items():
        require(sha((REPO / name).read_bytes().replace(b'\r\n', b'\n')) == digest, 'A-E source changed: ' + name)
    preserved = json.loads((ROOT / 'data/preserved-source-sha256.json').read_text())
    require(len(preserved) == 47, 'F/G0B preservation inventory changed')
    for name, entry in preserved.items():
        data = (REPO / name).read_bytes()
        require(sha(data.replace(b'\r\n', b'\n') if entry['text'] else data) == entry['sha256'],
                'Preserved F/G0B file changed: ' + name)
    bullet.verify_upstream_pin()
    command = ['git', '-c', 'safe.directory=' + Path(osg).resolve().as_posix(), '-C', str(osg)]
    require(subprocess.run(command + ['rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
            == OSG_REVISION, 'Wrong OSG revision')
    require(not subprocess.run(command + ['status', '--porcelain', '--untracked-files=all'],
                               check=True, capture_output=True, text=True).stdout.strip(), 'Dirty OSG source')
    return {'g0b_sources': 14, 'g0b_source_headers': 59, 'esm_vfs_units': 21,
            'prior_milestone_files': 53, 'preserved_f_g0b_files': len(preserved)}


def prepare(output, osg, generated, bullet_source):
    audited = audit(osg)
    output = output.resolve()
    require(not output.is_relative_to(REPO) or output.is_relative_to(ROOT / 'artifacts'),
            'Prepared files must stay in runner storage or ignored G0C artifacts')
    require(not output.is_relative_to(Path(osg).resolve()) and not output.is_relative_to(bullet_source.resolve()),
            'Prepared output cannot alter dependencies')
    fixture_names = sorted(p.name for p in (G0B / 'data').iterdir())
    require(len(fixture_names) == 12, 'Expected exact G0B data inventory')
    resources = {'Fixtures/' + name: (G0B / 'data' / name).read_bytes() for name in fixture_names}
    for name in GENERATED:
        path = generated / name
        require(path.is_file() and not path.is_symlink(), 'Missing generated header: ' + name)
        resources['Provenance/generated/' + name] = path.read_bytes()
    provenance = json.loads((bullet_source.parent / 'bullet-provenance.json').read_text())
    require(provenance['archive_sha512'] == bullet.SHA512 and provenance['source_url'] == bullet.URL
            and Path(provenance['source_directory']).resolve() == bullet_source.resolve(), 'Wrong Bullet provenance')
    resources['Provenance/bullet-provenance.json'] = (bullet_source.parent / 'bullet-provenance.json').read_bytes()
    resources['Licenses/OpenMW-LICENSE.txt'] = (REPO / 'LICENSE').read_bytes()
    resources['Licenses/OSG-LICENSE.txt'] = (Path(osg) / 'LICENSE.txt').read_bytes()
    license_paths = sorted(p for p in bullet_source.rglob('*') if p.is_file()
                           and p.name.lower() in ('license', 'license.txt', 'copying'))
    require(license_paths, 'Missing Bullet notices')
    for index, path in enumerate(license_paths):
        require(not path.is_symlink(), 'Linked Bullet license')
        resources['Licenses/Bullet-%d.txt' % index] = path.read_bytes()
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'],
                            check=True, capture_output=True, text=True).stdout.strip()
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Invalid source commit')
    metadata = {'schema_version': 1, 'source_commit': commit, 'g0b_validated_commit': HOST_COMMIT,
                'osg_revision': OSG_REVISION, 'bullet_url': bullet.URL, 'bullet_sha512': bullet.SHA512,
                'platform_target': 'iPhoneOS-arm64', 'minimum_os': '18.0', 'source_audit': audited,
                'resources_sha256': {name: sha(data) for name, data in sorted(resources.items())},
                'scope': 'Prepared source provenance; no device execution claim'}
    metadata['g0c_source_sha256_lf'] = {
        p.relative_to(REPO).as_posix(): sha(p.read_bytes().replace(b'\r\n', b'\n'))
        for p in sorted(ROOT.rglob('*')) if p.is_file() and 'artifacts' not in p.relative_to(ROOT).parts
        and '__pycache__' not in p.parts}
    metadata_bytes = (json.dumps(metadata, sort_keys=True, indent=2) + '\n').encode()
    resources['nif-build.json'] = metadata_bytes
    header = '#pragma once\nnamespace G0CExpected {\n'
    constants = {'BuildSHA256': sha(metadata_bytes), 'SourceCommit': commit,
                 'ManifestSHA256': sha(resources['Fixtures/fixture-manifest.json']),
                 'PayloadSHA256': sha(resources['Fixtures/triangle-candidate.nif']), 'OSGRevision': OSG_REVISION}
    header += ''.join('inline constexpr char ' + name + '[] = ' + json.dumps(value) + ';\n'
                      for name, value in constants.items()) + '}\n'
    planned = {'resources/' + name: data for name, data in resources.items()}
    planned['include/G0CExpectations.hpp'] = header.encode('utf-8')
    require(not output.exists() or tree(output) == planned or not tree(output), 'Prepared output differs from exact plan')
    for name, data in planned.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('audit', 'prepare'))
    parser.add_argument('--osg-source', type=Path, required=True)
    parser.add_argument('--generated', type=Path)
    parser.add_argument('--bullet-source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.osg_source) if args.phase == 'audit' else prepare(
        args.output, args.osg_source, args.generated, args.bullet_source)
    print(json.dumps(result, sort_keys=True, indent=2))
