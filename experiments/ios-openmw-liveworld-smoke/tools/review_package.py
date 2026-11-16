"""Create and reopen an exact public source-review ZIP; never mutate Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BASE = 'cb089f4141782f6c136d68d7e71b03f4f30b73a9'
WORKFLOW = REPO / '.github/workflows/ios-openmw-liveworld-device.yml'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    paths = [WORKFLOW]
    for directory, children, names in os.walk(ROOT):
        children[:] = [name for name in children if name not in ('artifacts', 'build', 'private', '__pycache__')]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or (path.suffix not in ('.md', '.json', '.py', '.cpp', '.hpp', '.cmake', '.in')
                    and name not in ('.gitignore', 'CMakeLists.txt')):
                raise ValueError('Unexpected source-review member: ' + str(path))
            paths.append(path)
    return sorted(paths)


def package(output):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    if head != BASE:
        raise ValueError('Source review must use the documented unchanged G5 checkpoint')
    files = {p.relative_to(REPO).as_posix(): p.read_bytes() for p in sources()}
    source_names = set(files)
    validation = json.loads((ROOT / 'artifacts/validation/validation.json').read_text())
    if validation['source_sha256_lf'] != {n: digest(raw.replace(b'\r\n', b'\n')) for n, raw in files.items()}:
        raise ValueError('Final validation does not bind current exact source inventory/bytes')
    if any(row['status'] not in ('PASS', 'UNVERIFIED') for row in validation['results'].values()):
        raise ValueError('Failed validation cannot enter the review ZIP')
    # This directory contains only selected authored-test outputs and sanitized
    # private-content/fault summaries. Never recursively include artifacts/.
    for path in sorted((ROOT / 'artifacts/validation').iterdir()):
        if path.is_file() and path.suffix in ('.json', '.log'):
            files['evidence/validation/' + path.name] = path.read_bytes()
    for name in ('build-review.log', 'attached-host-configure-final.log'):
        files['evidence/' + name] = (ROOT / 'artifacts' / name).read_bytes()
    inventory = {'schema': 1, 'base_commit': BASE, 'source_count': len(source_names),
        'source_additions': sorted(source_names), 'evidence_files': sorted(set(files) - source_names),
        'source_sha256_raw': {n: digest(files[n]) for n in sorted(source_names)},
        'source_sha256_lf': {n: digest(files[n].replace(b'\r\n', b'\n')) for n in sorted(source_names)},
        'publication': 'UNPUBLISHED; no staging, commit, push or dispatch',
        'excluded': 'Game assets, private profiles/recordings, full private logs, archives, executables, libraries, PDBs'}
    files['REVIEW-INVENTORY.json'] = (json.dumps(inventory, indent=2) + '\n').encode()
    files['SHA256SUMS'] = ''.join(digest(raw) + '  ' + name + '\n' for name, raw in sorted(files.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 16, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Review ZIP corruption/duplicate entries')
        if set(archive.namelist()) != set(files): raise ValueError('Review ZIP exact inventory differs')
        for name, raw in files.items():
            if archive.read(name) != raw: raise ValueError('Review ZIP payload differs: ' + name)
    result = {'status': 'PASS', 'path': str(output.resolve()), 'sha256': digest(output.read_bytes()),
        'bytes': output.stat().st_size, 'source_additions': len(source_names),
        'evidence_files': len(inventory['evidence_files']), 'zip_entries': len(files)}
    output.with_suffix('.zip.sha256').write_text(result['sha256'] + '  ' + output.name + '\n', encoding='utf-8')
    output.with_suffix('.review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(package(parser.parse_args().output.resolve()), indent=2))
