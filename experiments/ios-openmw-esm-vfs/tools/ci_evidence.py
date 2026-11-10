"""Milestone E source, runtime and failure evidence; no dependency fetching or compilation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import audit_sources as auditor
import fixtures
import validate_esm_vfs_archive as validator

ROOT, REPO = auditor.ROOT, auditor.REPO
previous = auditor.load_module('unchanged_milestone_d_archive_validator',
    REPO / 'experiments/ios-openmw-esm/tools/validate_esm_archive.py')
ARCHIVES = {
    'milestone-d': ('libopenmw-ios-esm-reader.a', previous.SOURCES),
    'milestone-e': ('libopenmw-ios-esm-vfs.a', validator.SOURCES),
}
CONFIG = Path('esm-reader/osg-math/include/osg/Config')


class EvidenceError(ValueError):
    pass


def require(value, message):
    if not value:
        raise EvidenceError(message)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot(osg, evidence):
    result = auditor.audit(osg_source=osg)
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True).stdout.strip()
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == commit, 'Requested OpenMW SHA mismatch')
    manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
    inherited = json.loads(auditor.esm_audit.MANIFEST.read_text(encoding='utf-8'))
    raw, canonical = [], []
    for prefix, base, hashes in (('openmw', REPO, manifest['project_sha256_lf']),
                                 ('osg-pinned', Path(osg), inherited['osg_sha256_lf'])):
        for name in sorted(hashes):
            data = (base / name).read_bytes()
            relative = prefix + '/' + name
            raw.append(hashlib.sha256(data).hexdigest() + '  ' + relative)
            canonical.append(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest() + '  ' + relative)
    (evidence / 'source-sha256.txt').write_text('\n'.join(raw) + '\n', encoding='utf-8')
    (evidence / 'source-sha256-lf.txt').write_text('\n'.join(canonical) + '\n', encoding='utf-8')
    write_json(evidence / 'source-provenance.json', {'openmw_commit': commit,
        'osg_revision': auditor.esm_audit.OSG_REVISION, 'project_files': 79, 'osg_files': 7,
        'audit': result, 'scope': 'Source/header verification, not native build evidence'})
    shutil.copy2(auditor.MANIFEST, evidence / 'milestone-e-source-audit.json')
    shutil.copy2(auditor.esm_audit.MANIFEST, evidence / 'milestone-d-source-audit.json')
    shutil.copy2(REPO / 'LICENSE', evidence / 'OpenMW-LICENSE.txt')
    shutil.copy2(Path(osg) / 'LICENSE.txt', evidence / 'OSG-LICENSE.txt')
    files = [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and not any(part.startswith('build') for part in p.relative_to(ROOT).parts[:-1])]
    files += [REPO / name for name in manifest['reused_build_sha256_lf']]
    files += [REPO / name for name in (
        '.github/workflows/ios-openmw-esm-vfs.yml',
        'experiments/ios-openmw-core/tools/validate_archive.py',
        'experiments/ios-openmw-esm/tools/validate_esm_archive.py',
        'experiments/ios-openmw-esm/tools/ci_evidence.py',
        'experiments/ios-osg-smoke/data/osg-lock.json')]
    (evidence / 'validation-input-sha256.txt').write_text('\n'.join(
        sha(path) + '  openmw/' + path.relative_to(REPO).as_posix() for path in sorted(set(files))) + '\n', encoding='utf-8')


def locate_archives(build, evidence, required):
    reports = {}
    for label, (name, sources) in ARCHIVES.items():
        paths = sorted(Path(build).rglob(name))
        valid = len(paths) == 1 and paths[0].is_file() and paths[0].stat().st_size > 0
        reports[label] = {'valid': valid, 'archive': name, 'expected_objects': len(sources),
                          'matches': [str(path) for path in paths]}
        if valid:
            shutil.copy2(paths[0], evidence / name)
        elif len(paths) > 1:
            # Preserve ambiguous outputs for diagnosis; never select one as authoritative.
            for path in paths:
                if path.is_file():
                    dest = evidence / 'ambiguous-archives' / label / path.relative_to(build)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
    write_json(evidence / 'archive-locations.json', reports)
    if required:
        require(all(report['valid'] for report in reports.values()),
                'Require one nonempty D archive and one nonempty E archive; missing/empty/ambiguous output rejected')
    return reports


def host_results(build, evidence):
    report = evidence / 'host-validation.json'
    try:
        locate_archives(build, evidence, required=True)
        inventories = {}
        for label, (name, sources) in ARCHIVES.items():
            objects = validator.core.archive_objects((evidence / name).read_bytes())
            require(len(objects) == len(sources), 'Incorrect host archive object count: ' + label)
            found, members = set(), []
            for member, payload in objects:
                candidates = [s for s in sources if member in {Path(s).stem + '.o', Path(s).name + '.o'}]
                require(len(candidates) == 1 and candidates[0] not in found and payload,
                        'Unexpected/duplicate/empty host object: ' + member)
                found.add(candidates[0])
                members.append({'member': member, 'source': candidates[0], 'sha256': hashlib.sha256(payload).hexdigest()})
            require(found == set(sources), 'Host source inventory mismatch: ' + label)
            completed = subprocess.run(['xcrun', 'ar', '-t', str(evidence / name)], capture_output=True, text=True)
            (evidence / (label + '-host-members.log')).write_text(
                '$ xcrun ar -t ' + name + '\n' + completed.stdout + completed.stderr, encoding='utf-8')
            require(completed.returncode == 0, 'Host ar inventory failed: ' + label)
            inventories[label] = {'archive': name, 'sha256': sha(evidence / name), 'objects': members}
        junit = ET.parse(evidence / 'ctest-results.xml').getroot()
        require(junit.tag in {'testsuite', 'testsuites'}, 'Unrecognized CTest JUnit report')
        tests = list(junit.iter('testcase'))
        require(len(tests) == 1 and tests[0].get('name') == 'openmw-esm-vfs-runtime', 'Missing/incorrect CTest selection')
        require(not any(node.tag in {'failure', 'error', 'skipped'} for node in junit.iter())
                and tests[0].get('status', 'run') == 'run', 'CTest runtime did not pass')
        for node in junit.iter():
            if node.tag in {'testsuite', 'testsuites'}:
                require(all(int(node.get(key, '0')) == 0 for key in ('failures', 'errors', 'disabled', 'skipped')),
                        'CTest report declares failed or unexecuted tests')
        text = (Path(build) / 'Testing/Temporary/LastTest.log').read_text(encoding='utf-8')
        for label, _, _, _, marker in fixtures.CASES:
            lines = [line for line in text.splitlines() if line.startswith(label + ': ')]
            require(len(lines) == 1 and marker in lines[0], 'Missing/duplicate/failed runtime case: ' + label)
        require(text.count('Sixteen synthetic ESM/VFS cases passed with unchanged input tree.') == 1,
                'Missing/ambiguous sixteen-case completion marker')
        expected = {name: hashlib.sha256(data).hexdigest() for name, data in fixtures.inputs().items()}
        actual = fixtures.snapshot(Path(build) / 'synthetic-esm-vfs')
        require(actual == expected, 'Runtime input tree differs from deterministic fixture manifest')
        (evidence / 'synthetic-input-sha256.txt').write_text('\n'.join(
            value + '  ' + name for name, value in sorted(actual.items())) + '\n', encoding='utf-8')
        write_json(report, {'valid': True, 'runtime_cases': 16, 'unchanged_input_files': len(actual),
            'archives': inventories, 'scope': 'macOS host link/runtime only; no combined iPhoneOS executable proof'})
    except (OSError, ValueError, RuntimeError, ET.ParseError) as error:
        write_json(report, {'valid': False, 'error': str(error)})
        raise


def checksums(evidence):
    (evidence / 'SHA256SUMS').write_text('\n'.join(
        sha(p) + '  ' + p.relative_to(evidence).as_posix() for p in sorted(evidence.rglob('*'))
        if p.is_file() and p.name != 'SHA256SUMS') + '\n', encoding='utf-8')


def collect(build, evidence, kind, status):
    build = Path(build)
    try:
        for path in sorted(build.rglob('*')):
            if path.is_file() and path.name in {'CMakeCache.txt', 'CMakeConfigureLog.yaml', 'LastTest.log', 'LastTestsFailed.log',
                                                'source-audit.log', 'osg-math-resolved.cmake'}:
                destination = evidence / 'build-diagnostics' / path.relative_to(build)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        config = build / CONFIG
        if config.is_file():
            dest = evidence / 'generated/osg/Config'
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config, dest)
        inputs = build / 'synthetic-esm-vfs'
        if inputs.is_dir():
            shutil.copytree(inputs, evidence / 'synthetic-esm-vfs', dirs_exist_ok=True)
        locate_archives(build, evidence, required=status == 'success')
        if status == 'success':
            config_report = json.loads((evidence / 'config-validation.json').read_text())
            require(config_report['valid'] and config_report['sha256'] == sha(evidence / 'generated/osg/Config'),
                    'Collected Config differs from verified configuration')
            require((evidence / 'source-provenance.json').is_file(), 'Missing source provenance')
            if kind == 'device':
                for label, (name, sources) in ARCHIVES.items():
                    result = json.loads((evidence / 'archive-inspection' / label / 'archive-validation.json').read_text())
                    require(result['valid'] and len(result['objects']) == len(sources)
                            and {obj['source'] for obj in result['objects']} == set(sources),
                            'Missing strict object validation: ' + label)
                    require(result['sha256'] == sha(evidence / name), 'Collected archive differs from validated archive: ' + label)
            else:
                result = json.loads((evidence / 'host-validation.json').read_text())
                require(result['valid'] and result['runtime_cases'] == 16, 'Missing successful sixteen-case host evidence')
                actual = fixtures.snapshot(evidence / 'synthetic-esm-vfs')
                require(actual == {name: hashlib.sha256(data).hexdigest() for name, data in fixtures.inputs().items()},
                        'Collected host input tree mismatch')
                for label, (name, _) in ARCHIVES.items():
                    require(result['archives'][label]['sha256'] == sha(evidence / name), 'Collected host archive mismatch')
        write_json(evidence / 'job-status.json', {'job_kind': kind, 'validation_steps_status': status,
            'evidence_collection': 'success', 'timing': 'Before artifact upload; GitHub final job conclusion is authoritative'})
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        write_json(evidence / 'job-status.json', {'job_kind': kind, 'validation_steps_status': status,
            'evidence_collection': 'failure', 'error': str(error), 'reported_pre_upload_status': 'failure'})
        raise
    finally:
        checksums(evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('sources', 'archives', 'host-results', 'collect'))
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--osg-source', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--kind', choices=('host', 'device'))
    parser.add_argument('--status', choices=('success', 'failure', 'cancelled', 'skipped'))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    try:
        if args.phase == 'sources':
            require(args.osg_source is not None, 'Supply genuine pinned OSG checkout')
            source_snapshot(args.osg_source, args.evidence)
        else:
            require(args.build is not None, 'Supply isolated build directory')
            if args.phase == 'archives': locate_archives(args.build, args.evidence, required=True)
            elif args.phase == 'host-results': host_results(args.build, args.evidence)
            else:
                require(args.kind is not None and args.status is not None, 'Supply job kind and status')
                collect(args.build, args.evidence, args.kind, args.status)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError, ET.ParseError) as error:
        print('ESM/VFS evidence validation failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
