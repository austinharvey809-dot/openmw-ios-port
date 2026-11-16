"""Keep G5/accepted source immutable; verify local raw snapshots when supplied."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BASE = 'cb089f4141782f6c136d68d7e71b03f4f30b73a9'
WORKFLOW = '.github/workflows/ios-openmw-liveworld-device.yml'


def allowed(name):
    if name == WORKFLOW: return True
    prefix = 'experiments/ios-openmw-liveworld-smoke/'
    if not name.startswith(prefix): return False
    path = Path(name[len(prefix):])
    return not {'artifacts', 'build', 'private', '__pycache__'} & set(path.parts) and (
        path.suffix in ('.md', '.json', '.py', '.cpp', '.hpp', '.cmake', '.in')
        or path.name in ('.gitignore', 'CMakeLists.txt'))


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=REPO, text=True).strip()


def verify(snapshots=()):
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=REPO, check=True, capture_output=True)
    published = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    for line in published:
        status, name = line.split('\t', 1)
        if status != 'A' or not allowed(name):
            raise ValueError('Published change outside independent G6 additions: ' + line)
    checked = []
    covered = set()
    for snapshot in snapshots:
        lock = json.loads(snapshot.read_text())
        for name, want in lock['sha256_raw'].items():
            path = (REPO / name).resolve()
            if not path.is_relative_to(REPO) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != want:
                raise ValueError('Protected raw file changed: ' + name)
        covered.update(lock['sha256_raw'])
        checked.append({'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            'base': lock['base'], 'protected_raw_files': len(lock['sha256_raw'])})
    working = git('diff', '--name-only', 'HEAD').splitlines()
    untracked = git('ls-files', '--others', '--exclude-standard').splitlines()
    for name in (*working, *untracked):
        if not allowed(name) and name not in covered:
            raise ValueError('Unrelated local work requires its original preservation snapshot: ' + name)
    lock = json.loads((ROOT / 'engine-lock.json').read_text())
    for name, want in lock['sources'].items():
        if hashlib.sha256((REPO / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != want:
            raise ValueError('Genuine upstream/published G5 source changed: ' + name)
    return {'status': 'PASS', 'g5_checkpoint': BASE, 'head': git('rev-parse', 'HEAD'),
        'branch': git('branch', '--show-current'), 'published_additions': published,
        'snapshots': checked, 'locked_upstream_and_g5_files': len(lock['sources'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot), indent=2))
