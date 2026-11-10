"""Milestone F CI handoffs. Offline checks never imply native link or device execution."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

import prepare_inputs as inputs
import package_ios as package

ROOT, REPO = inputs.ROOT, inputs.REPO
CONTRACT = ROOT / 'data/prior-milestones.json'
CONFIG = Path('esm-vfs/esm-reader/osg-math/include/osg/Config')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def contracts():
    inventory = json.loads(CONTRACT.read_text(encoding='utf-8'))
    require(inventory['schema_version'] == 1, 'Unknown preservation contract')
    for name, expected in inventory['sha256_lf'].items():
        path = (REPO / name).resolve()
        require(path.is_relative_to(REPO), 'Invalid preservation path')
        actual = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        require(actual == expected, 'Prior milestone changed: ' + name)
    inputs.fixture_bytes()  # Exact original E inputs AND ID/model/key/payload bytes.
    return {'valid': True, 'preserved_files': len(inventory['sha256_lf']),
            'fixtures': json.loads(inputs.MANIFEST.read_text(encoding='utf-8')),
            'scope': 'Offline source/fixture contracts only'}


def regressions(evidence):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in
                               ('test_data_app', 'test_package_ios'))
    require(suite.countTestCases() == 28, 'Expected exactly the 28 reviewed F regressions')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
              'valid': result.wasSuccessful() and result.testsRun == 28 and not result.skipped
                       and not result.expectedFailures,
              'scope': 'Offline regressions; synthetic metadata is not native evidence'}
    write_json(evidence / 'python-regressions.json', report)
    require(report['valid'], 'All 28 F regressions must pass, without skips/expected failures')
    return report


def syntax():
    paths = sorted((ROOT / 'tools').glob('*.py'))
    for path in paths:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return {'valid': True, 'python_files': len(paths)}


def tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Symlink in prepared tree: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def prepared(directory, osg, config):
    # Recompute from the audited checkout, not from possibly stale bundled JSON.
    with tempfile.TemporaryDirectory() as temporary:
        expected = Path(temporary) / 'prepared'
        inputs.prepare(expected, osg, config)
        require(tree(directory) == tree(expected), 'Prepared resources/header/provenance mismatch')
    return {'valid': True, 'files': {name: hashlib.sha256(data).hexdigest()
                                   for name, data in tree(directory).items()}}


def verify_resources(files, directory):
    expected = tree(directory / 'resources')
    require(expected, 'Missing prepared resources')
    for name, data in expected.items():
        require(name in files and files[name].data == data, 'Built resource/provenance mismatch: ' + name)
    metadata = json.loads(expected['data-build.json'])
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True).stdout.strip()
    require(metadata['source_commit'] == commit, 'Prepared source commit differs from checkout')
    require(not os.environ.get('GITHUB_SHA') or commit == os.environ['GITHUB_SHA'], 'Requested source commit mismatch')
    return {name: hashlib.sha256(data).hexdigest() for name, data in expected.items()}


def locate(build, kind, evidence):
    name = package.APP_NAME if kind == 'app' else 'openmw-data-link-check'
    matches = [p for p in build.rglob(name) if p.is_dir() == (kind == 'app')]
    write_json(evidence / (kind + '-locations.json'), {'matches': [str(p) for p in matches]})
    require(len(matches) == 1 and not matches[0].is_symlink(), 'Expected unique ' + name)
    require(kind == 'app' or matches[0].stat().st_size > 0, 'Empty link executable')
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
            stream.write(('APP_PATH' if kind == 'app' else 'LINK_PATH') + '=' + str(matches[0]) + '\n')
    return {'valid': True, 'path': str(matches[0])}


def app_report(app, directory, sdk, evidence):
    files = package.collect_bundle(app)
    resources = verify_resources(files, directory)
    report = package.validate_bundle(files, sdk)
    outputs = package.core.inspect_dependencies(app, report)
    (evidence / 'otool-L.txt').write_text('\n'.join(outputs.values()), encoding='utf-8')
    report.update(valid=True, prepared_resource_sha256=resources)
    return report


def ipa_report(ipa, directory, sdk):
    report = package.validate_ipa(ipa, sdk)
    with zipfile.ZipFile(ipa) as archive:
        files = {entry.filename[len(package.PREFIX):]: package.Entry(archive.read(entry), entry.external_attr >> 16)
                 for entry in archive.infolist() if not entry.is_dir()}
    report.update(valid=True, prepared_resource_sha256=verify_resources(files, directory))
    return report


def inventory(evidence):
    paths = [CONTRACT, REPO / '.github/workflows/ios-openmw-data-smoke.yml', ROOT / 'README.md',
             ROOT / 'CMakeLists.txt', ROOT / 'Info.plist.in', inputs.MANIFEST]
    paths += sorted((ROOT / 'tools').glob('*.py')) + sorted((ROOT / 'src').glob('*'))
    write_json(evidence / 'f-source-sha256.json', {p.relative_to(REPO).as_posix(): sha(p) for p in paths})
    shutil.copy2(CONTRACT, evidence / CONTRACT.name)
    return contracts()


def collect(build, evidence):
    # Preserve partial outputs too; collection never grants a gate success.
    names = {'CMakeCache.txt', 'CMakeConfigureLog.yaml', 'CMakeError.log', 'CMakeOutput.log',
             'source-audit.log', 'osg-math-resolved.cmake', 'prepare-inputs.log',
             'libopenmw-ios-esm-reader.a', 'libopenmw-ios-esm-vfs.a', 'openmw-data-link-check', 'Config'}
    for path in sorted(build.rglob('*')):
        relative = path.relative_to(build)
        if path.is_file() and (path.name in names or path.suffix == '.log'
                or any(p == 'prepared' or p.endswith(('.app', '.dSYM', '.xcactivitylog')) for p in relative.parts)):
            destination = evidence / 'build-products' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    return {'valid': True, 'scope': 'Available diagnostics/products only; gate status is recorded separately'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('contracts', 'regressions', 'syntax', 'prepared', 'inventory',
                                         'locate-link', 'locate-app', 'app', 'ipa', 'collect'))
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--osg-source', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--product', type=Path)
    parser.add_argument('--sdk', type=Path)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    try:
        if args.phase in ('contracts', 'syntax'):
            report = globals()[args.phase]()
        elif args.phase in ('regressions', 'inventory'):
            report = globals()[args.phase](args.evidence)
        elif args.phase == 'prepared':
            report = prepared(args.prepared, args.osg_source, args.config)
        elif args.phase.startswith('locate-'):
            report = locate(args.build, args.phase.removeprefix('locate-'), args.evidence)
        elif args.phase == 'app':
            require(args.sdk is not None, 'App gate requires real iPhoneOS SDK')
            report = app_report(args.product, args.prepared, args.sdk, args.evidence)
        elif args.phase == 'ipa':
            require(args.sdk is not None, 'IPA gate requires real iPhoneOS SDK')
            report = ipa_report(args.product, args.prepared, args.sdk)
        else:
            report = collect(args.build, args.evidence)
        write_json(args.evidence / (args.phase + '-validation.json'), report)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, KeyError, package.ValidationError, subprocess.CalledProcessError) as error:
        write_json(args.evidence / (args.phase + '-validation.json'), {'valid': False, 'error': str(error)})
        print('Milestone F CI check failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
