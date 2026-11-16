"""Keep accepted source immutable; optionally verify the local raw-byte snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
BASE='cd5e74396fc75a502d441925adc77efcac4af1ec'
ALLOWED=('experiments/ios-openmw-engine-smoke/', '.github/workflows/ios-openmw-engine-device.yml')


def allowed_source(name):
    if name==ALLOWED[1]:return True
    if not name.startswith(ALLOWED[0]):return False
    path=Path(name.removeprefix(ALLOWED[0]))
    return not {'artifacts','build','private','__pycache__'}&set(path.parts) and (
        path.suffix in ('.md','.json','.py','.cpp','.hpp','.cmake') or path.name=='.gitignore')


def verify(snapshot=None):
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=REPO,check=True,capture_output=True)
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'HEAD'],cwd=REPO,text=True).splitlines()
    if any(not allowed_source(n) for n in changed):raise ValueError('Published change outside isolated G5 source scope')
    count=0
    if snapshot:
        lock=json.loads(snapshot.read_text())
        for name,want in lock['sha256_raw'].items():
            path=(REPO/name).resolve()
            if not path.is_relative_to(REPO) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=want:
                raise ValueError('Protected working-tree file changed: '+name)
            count+=1
    return {'status':'PASS','base':BASE,'protected_raw_files_verified':count,'published_changed_files':changed}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path);a=p.parse_args();print(json.dumps(verify(a.snapshot),indent=2))
