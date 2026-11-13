"""Execute genuine host texture reader, equivalence/ownership and negative gates."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures
from support import ROOT, REPO, base


def validate(report, manifest):
    if not (report.get('status') == 'PASS' and report.get('source_equivalence') is True
            and report.get('parser_vfs_cache_released') is True
            and report.get('scope') == 'CPU parsing/resource/owned OSG data; no GPU claim'
            and {key: report.get(key) for key in ('negative_cases', 'cache_hits', 'vertices', 'triangles', 'uv_sets')}
                == dict(negative_cases=11, cache_hits=1, vertices=3, triangles=1, uv_sets=1)
            and all(type(report[key]) is int for key in ('negative_cases', 'cache_hits', 'vertices', 'triangles', 'uv_sets'))
            and report.get('texture_key') == manifest['texture_key']
            and report.get('pixels_sha256') == manifest['rgba_sha256']
            and report.get('geometry_sha256') == base.expected_geometry_hash()):
        raise ValueError('Genuine textured data report mismatch')


def run(product, evidence):
    if not product.is_file() or product.is_symlink():
        raise ValueError('Missing/nonregular genuine texture executable')
    if evidence.is_relative_to(REPO) and not any(evidence.is_relative_to(ROOT / name) for name in ('artifacts', 'build')):
        raise ValueError('Texture evidence must be external build or ignored artifact storage')
    manifest = fixtures.audit()
    before = {p.name: fixtures.digest(p.read_bytes()) for p in fixtures.DATA.iterdir()}
    evidence.mkdir(parents=True, exist_ok=True)
    reports = []
    for case in manifest['cases']:
        command = [str(product), str(fixtures.DATA), case['archive'], case['nif_sha256'], case['texture_sha256']]
        value = subprocess.run(command, capture_output=True, text=True, timeout=120)
        name = case['archive'].removesuffix('.bsa')
        (evidence / (name + '.stdout')).write_text(value.stdout)
        (evidence / (name + '.stderr')).write_text(value.stderr)
        (evidence / (name + '.command.json')).write_text(json.dumps(command))
        if case['diagnostic']:
            if value.returncode != 1 or case['diagnostic'] not in value.stderr:
                raise ValueError('Negative did not fail at expected gate: ' + name)
        else:
            if value.returncode != 0:
                raise ValueError('Genuine textured reader failed: ' + value.stderr)
            report = json.loads(value.stdout)
            validate(report, manifest)
        reports.append({'case': name, 'passed': True, 'returncode': value.returncode})
    fixtures.audit()
    if before != {p.name: fixtures.digest(p.read_bytes()) for p in fixtures.DATA.iterdir()}:
        raise ValueError('Native texture run modified inputs')
    result = {'cases': reports, 'inputs_unchanged': True, 'scope': 'Native CPU tests only; rendering unverified'}
    (evidence / 'texture-suite.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--product', type=Path, required=True)
    cli.add_argument('--evidence', type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(run(args.product.resolve(), args.evidence.resolve()), indent=2))
