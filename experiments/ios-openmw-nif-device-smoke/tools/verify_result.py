"""Require matching phone JSON/LOG and complete genuine-parser evidence."""
import argparse
import json
from pathlib import Path
import re

from common import G0B, OSG_REVISION, HOST_COMMIT, sha, require

MODES = ('positive', 'invalid', 'truncated', 'invalid-reference', 'missing', 'wrong-resource-bytes')
COUNTS = {'records': 3, 'roots': 1, 'geometry': 1, 'vertices': 3, 'triangles': 1}
MARKERS = ('PASS genuine OpenMW NIF parse', 'PASS genuine parser rejected invalid',
           'PASS genuine parser rejected truncated', 'PASS genuine parser rejected invalid-reference',
           'PASS missing resource rejected', 'VFS NIF bytes differ')


def validate(result, expected_commit):
    require(result.get('status') == 'PASS' and result.get('genuine_parser_suite_completed') is True,
            'No complete genuine device parser PASS')
    require(result.get('inputs_unchanged') is True, 'Inputs not verified unchanged')
    require(result.get('inputs_before') == result.get('inputs_after'), 'Input snapshots disagree')
    require(result.get('decoded') == COUNTS and all(type(v) is int for v in result['decoded'].values()),
            'Decoded geometry evidence differs')
    build = result.get('build', {})
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and build.get('source_commit') == expected_commit,
            'Wrong source commit')
    require(build.get('osg_revision') == OSG_REVISION and build.get('g0b_validated_commit') == HOST_COMMIT
            and build.get('platform_target') == 'iPhoneOS-arm64', 'Wrong build provenance')
    from prepare import bullet
    require(build.get('bullet_sha512') == bullet.SHA512, 'Wrong Bullet precision/source provenance')
    manifest = json.loads((G0B / 'data/fixture-manifest.json').read_text())
    before = result['inputs_before']
    require(set(before) == set(manifest['files']) | {'fixture-manifest.json', 'nif-source-sha256.json'},
            'Phone fixture inventory mismatch')
    require(all(before[name] == entry for name, entry in manifest['files'].items()), 'Phone fixture hashes differ')
    require(all(before[name]['sha256'] == build['resources_sha256']['Fixtures/' + name] for name in before),
            'Phone source/fixture provenance mismatch')
    require(result.get('resource_sha256') == manifest['files']['triangle-candidate.nif']['sha256']
            and result.get('resource_key') == 'meshes/test.nif' and result.get('object_id') == 'eIOSStatic',
            'Wrong actual resource identity/hash')
    cases = result.get('cases', [])
    require(len(cases) == 6 and [c.get('mode') for c in cases] == list(MODES), 'Missing/skipped/reordered negative case')
    for index, case in enumerate(cases):
        require(case.get('passed') is True and type(case.get('exit_code')) is int, 'Failed/malformed case')
        require((case['exit_code'] != 0 if index == 5 else case['exit_code'] == 0), 'Wrong case exit code')
        require(MARKERS[index] in case.get('stderr' if index == 5 else 'stdout', ''), 'Missing genuine case marker')
    for name, count in COUNTS.items():
        require(re.search(r'\b' + name + '=' + str(count) + r'(?:\s|$)', cases[0]['stdout']),
                'Decoded JSON and genuine stdout disagree')
    require(isinstance(result.get('device'), dict) and result['device'].get('system'), 'Missing phone identity')
    return {'valid': True, 'source_commit': expected_commit, 'scope': 'Consistent exported device evidence; review phone screenshot too'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--expected-source-commit', required=True)
    args = parser.parse_args()
    result = json.loads(args.json.read_text(encoding='utf-8'))
    require(result == json.loads(args.log.read_text(encoding='utf-8')), 'JSON/LOG exports disagree')
    print(json.dumps(validate(result, args.expected_source_commit), indent=2))
