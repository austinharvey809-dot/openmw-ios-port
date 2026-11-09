"""Collect bounded Milestone D provenance and failure evidence; never fetch/build dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import audit_sources as auditor

ROOT, REPO = auditor.ROOT, auditor.REPO
ARCHIVE = 'libopenmw-ios-esm-reader.a'
CONFIG = Path('osg-math/include/osg/Config')


class EvidenceError(ValueError):
    pass


def require(value, message):
    if not value:
        raise EvidenceError(message)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def source_snapshot(osg, evidence):
    result = auditor.audit(osg_source=osg)  # Required genuine revision and all 60 full-file hashes.
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True).stdout.strip()
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == commit, 'Requested source SHA mismatch')
    manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
    raw, canonical = [], []
    for prefix, base, hashes in (('openmw', REPO, manifest['project_sha256_lf']),
                                  ('osg-pinned', Path(osg), manifest['osg_sha256_lf'])):
        for name in sorted(hashes):
            data = (base / name).read_bytes()
            relative = prefix + '/' + name
            raw.append(hashlib.sha256(data).hexdigest() + '  ' + relative)
            canonical.append(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest() + '  ' + relative)
    (evidence / 'source-sha256.txt').write_text('\n'.join(raw) + '\n', encoding='utf-8')
    (evidence / 'source-sha256-lf.txt').write_text('\n'.join(canonical) + '\n', encoding='utf-8')
    write_json(evidence / 'source-provenance.json', {'openmw_commit': commit, 'osg_revision': auditor.OSG_REVISION,
        'openmw_files': 53, 'osg_files': 7, 'audit': result, 'scope': 'Source/header provenance, not native build proof'})
    shutil.copy2(auditor.MANIFEST, evidence / 'source-audit-manifest.json')
    shutil.copy2(REPO / 'LICENSE', evidence / 'OpenMW-LICENSE.txt')
    shutil.copy2(Path(osg) / 'LICENSE.txt', evidence / 'OSG-LICENSE.txt')
    files = [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and not any(part.startswith('build') for part in p.relative_to(ROOT).parts[:-1])]
    files += [REPO / '.github/workflows/ios-openmw-esm.yml',
              REPO / 'experiments/ios-openmw-core/tools/validate_archive.py',
              REPO / 'experiments/ios-osg-smoke/data/osg-lock.json']
    rows = [hashlib.sha256(p.read_bytes()).hexdigest() + '  openmw/' + p.relative_to(REPO).as_posix()
            for p in sorted(set(files))]
    (evidence / 'validation-input-sha256.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')


def verify_config(osg, build, evidence):
    report = evidence / 'config-validation.json'
    try:
        auditor.audit(osg_source=osg)
        manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
        template = (Path(osg) / 'src/osg/Config.in').read_text(encoding='utf-8')
        # Independently compare the generated file to CMake's #cmakedefine
        # expansion of the genuine audited template. No header is generated here.
        expected = re.sub(r'^#cmakedefine (\w+)$', lambda match:
            '#define ' + match[1] if manifest['osg_config_defines'][match[1]] else '/* #undef ' + match[1] + ' */',
            template, flags=re.M)
        path = Path(build) / CONFIG
        require(path.is_file() and path.stat().st_size > 0, 'Missing/empty genuine generated osg/Config')
        destination = evidence / 'generated/osg/Config'
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        data = path.read_bytes()
        require(data.replace(b'\r\n', b'\n').decode('utf-8') == expected, 'Generated osg/Config differs from audited template/settings')
        write_json(report, {'valid': True, 'sha256': hashlib.sha256(data).hexdigest(),
            'sha256_lf': hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest(),
            'template_sha256_lf': manifest['osg_sha256_lf']['src/osg/Config.in'],
            'switches': manifest['osg_config_defines'], 'scope': 'Configuration content only; no native compile claim'})
    except (OSError, EvidenceError, auditor.AuditError) as error:
        write_json(report, {'valid': False, 'error': str(error)})
        raise


def locate_archive(build, evidence, required):
    paths = sorted(Path(build).rglob(ARCHIVE))
    valid = len(paths) == 1 and paths[0].is_file() and paths[0].stat().st_size > 0
    write_json(evidence / 'archive-location.json', {'valid': valid, 'archive': ARCHIVE,
        'matches': [str(path) for path in paths], 'scope': 'Location only; object validation is separate'})
    if valid:
        shutil.copy2(paths[0], evidence / ARCHIVE)
    if required:
        require(valid, 'Expected exactly one nonempty ESM archive; missing/empty/ambiguous outputs rejected')
    return valid


def collect(build, evidence, kind, status):
    build = Path(build)
    write_json(evidence / 'job-status.json', {'job_kind': kind, 'validation_steps_status': status,
        'evidence_collection': 'running', 'timing': 'After validation, before artifact upload; GitHub final job conclusion is authoritative'})
    try:
        for path in sorted(build.rglob('*')):
            if path.is_file() and path.name in {'CMakeCache.txt', 'CMakeConfigureLog.yaml', 'LastTest.log', 'LastTestsFailed.log',
                                                'source-audit.log', 'osg-math-resolved.cmake'}:
                destination = evidence / 'build-diagnostics' / path.relative_to(build)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        config = build / CONFIG
        if config.is_file():
            destination = evidence / 'generated/osg/Config'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config, destination)
        inputs = build / 'synthetic-esm'
        if inputs.is_dir():
            shutil.copytree(inputs, evidence / 'synthetic-esm', dirs_exist_ok=True)
        locate_archive(build, evidence, required=status == 'success')
        if status == 'success':
            config_report = json.loads((evidence / 'config-validation.json').read_text())
            require(config_report['valid'], 'Missing/invalid Config verification')
            require(config_report['sha256'] == hashlib.sha256((evidence / 'generated/osg/Config').read_bytes()).hexdigest(),
                    'Collected Config differs from the verified configuration')
            require((evidence / 'source-provenance.json').is_file(), 'Missing source verification evidence')
            if kind == 'device':
                result = json.loads((evidence / 'archive-inspection/archive-validation.json').read_text())
                require(result['valid'] and len(result['objects']) == 15, 'Missing strict fifteen-object validation evidence')
                require(result['sha256'] == hashlib.sha256((evidence / ARCHIVE).read_bytes()).hexdigest(),
                        'Collected archive differs from the verified archive')
            else:
                require(inputs.is_dir(), 'Missing host synthetic input evidence')
        write_json(evidence / 'job-status.json', {'job_kind': kind, 'validation_steps_status': status,
            'evidence_collection': 'success', 'timing': 'Immediately before artifact upload; GitHub final job conclusion is authoritative'})
    except (OSError, ValueError, KeyError) as error:
        write_json(evidence / 'job-status.json', {'job_kind': kind, 'validation_steps_status': status,
            'evidence_collection': 'failure', 'error': str(error), 'reported_pre_upload_status': 'failure'})
        raise
    finally:
        rows = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(evidence).as_posix()
                for p in sorted(evidence.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS']
        (evidence / 'SHA256SUMS').write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('sources', 'config', 'archive', 'collect'))
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--osg-source', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--kind', choices=('host', 'device'))
    parser.add_argument('--status', choices=('success', 'failure', 'cancelled', 'skipped'))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    try:
        if args.phase in ('sources', 'config'):
            require(args.osg_source is not None, 'Provide the verified OSG source checkout')
        if args.phase != 'sources':
            require(args.build is not None, 'Provide the isolated build directory')
        if args.phase == 'sources': source_snapshot(args.osg_source, args.evidence)
        elif args.phase == 'config': verify_config(args.osg_source, args.build, args.evidence)
        elif args.phase == 'archive': locate_archive(args.build, args.evidence, required=True)
        else:
            require(args.kind is not None and args.status is not None, 'Provide job kind/status for evidence collection')
            collect(args.build, args.evidence, args.kind, args.status)
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('ESM evidence collection failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
