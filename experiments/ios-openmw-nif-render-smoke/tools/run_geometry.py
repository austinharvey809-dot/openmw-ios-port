"""Execute actual host binaries; preserve inputs and diagnostics even on failure."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from contracts import ROOT, REPO, DATA, LOCK, NEGATIVES, audit, fixture_snapshot, sha, require


def expected_geometry_hash():
    # Independent fixture expectation, confined to testing, never production mesh output.
    payload = b'G1A-geometry-v1' + struct.pack('<II9f3H', 3, 3, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    return sha(payload)


def validate(result):
    require(result.get('status') == 'PASS' and result.get('scope') == 'structural OSG geometry; no GPU rendering',
            'No structural native PASS')
    require({key: result.get(key) for key in ('records', 'roots', 'geometry', 'vertices', 'triangles')}
            == dict(records=3, roots=1, geometry=1, vertices=3, triangles=1), 'Wrong decoded geometry counts')
    require(all(type(result[key]) is int for key in ('records', 'roots', 'geometry', 'vertices', 'triangles')),
            'Malformed geometry counts')
    require(result.get('source_equivalence') is True and result.get('parser_released') is True,
            'Missing equivalence/lifetime evidence')
    require(result.get('negative_cases') == list(NEGATIVES), 'Missing/reordered geometry negative cases')
    require(result.get('object_id') == 'eIOSStatic' and result.get('model') == 'TeSt.NIF'
            and result.get('resource_key') == 'meshes/test.nif', 'Wrong ESM-selected resource')
    require(result.get('resource_sha256') == LOCK['fixtures']['triangle-candidate.nif']['sha256']
            and result.get('geometry_sha256') == expected_geometry_hash(), 'Wrong resource/geometry SHA-256')


def run(geometry, parser, osg, evidence):
    evidence = evidence.resolve()
    require(not evidence.is_relative_to(REPO) or evidence.is_relative_to(ROOT / 'artifacts')
            or evidence.is_relative_to(ROOT / 'build'),
            'Evidence must be external build storage or ignored G1A artifacts')
    require(not evidence.is_relative_to(DATA) and not evidence.is_relative_to(osg.resolve()),
            'Evidence cannot alter fixtures/dependencies')
    evidence.mkdir(parents=True, exist_ok=True)
    before = fixture_snapshot()
    report = {'status': 'FAIL', 'scope': 'G1A host geometry; no GPU/device execution'}
    try:
        report['provenance'] = audit(osg)
        for label, binary in (('geometry', geometry), ('parser', parser)):
            require(binary.is_file() and not binary.is_symlink(), 'Missing native executable: ' + label)
            report[label + '_executable_sha256'] = sha(binary.read_bytes())
        result = subprocess.run([str(geometry.resolve()), str(DATA)], capture_output=True, text=True, timeout=120)
        (evidence / 'geometry-stdout.log').write_text(result.stdout, encoding='utf-8')
        (evidence / 'geometry-stderr.log').write_text(result.stderr, encoding='utf-8')
        require(result.returncode == 0, 'Native geometry tests failed')
        report['geometry'] = json.loads(result.stdout)
        validate(report['geometry'])
        # Run all six unchanged genuine G0B cases against the same linked parser provider.
        import sys
        result = subprocess.run([sys.executable, str(ROOT.parent / 'ios-openmw-nif-smoke/tools/run_host_cases.py'),
                                 '--reader', str(parser.resolve())], capture_output=True, text=True, timeout=420)
        (evidence / 'six-parser-cases.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        require(result.returncode == 0, 'Preserved genuine parser cases failed')
        report['parser_cases'] = 'all six passed'
        report['g1a_source_sha256_lf'] = {
            path.relative_to(REPO).as_posix(): sha(path.read_bytes().replace(b'\r\n', b'\n'))
            for path in sorted(ROOT.rglob('*')) if path.is_file()
            and not {'artifacts', 'build', '__pycache__'} & set(path.relative_to(ROOT).parts)}
        workflow = REPO / '.github/workflows/ios-openmw-nif-geometry-host-smoke.yml'
        report['g1a_source_sha256_lf'][workflow.relative_to(REPO).as_posix()] = sha(
            workflow.read_bytes().replace(b'\r\n', b'\n'))
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        try:
            after = fixture_snapshot()
            require(after == before, 'Native tests modified input snapshots')
            report['inputs_before'], report['inputs_after'] = before, after
            report['inputs_unchanged'] = True
        except Exception as error:
            report.update(status='FAIL', inputs_unchanged=False, error=str(error))
            raise
        finally:
            (evidence / 'g1a-result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--geometry', type=Path, required=True)
    cli.add_argument('--parser', type=Path, required=True)
    cli.add_argument('--osg-source', type=Path, required=True)
    cli.add_argument('--evidence', type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(run(args.geometry, args.parser, args.osg_source, args.evidence), indent=2))
