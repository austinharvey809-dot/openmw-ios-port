"""Read-only verification of the accepted tree and unrelated working changes."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
BASE='d60ca603e82935a9ccce9ae5ec8dc9ec22013580'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capture():
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()!=BASE:
        raise ValueError('Unexpected review base')
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
    names=[n for n in names if n and (REPO/n).is_file()]
    names+=['experiments/ios-osg-smoke/src/MipmapObservation.hpp']
    return {'base':BASE,'sha256_raw':{n:digest(REPO/n) for n in names}}

def verify(lock):
    for name,expected in lock['sha256_raw'].items():
        path=(REPO/name).resolve()
        if not path.is_relative_to(REPO) or not path.is_file() or digest(path)!=expected:
            raise ValueError('Pre-existing file changed: '+name)
    return {'status':'PASS','base':lock['base'],'unchanged_files':len(lock['sha256_raw'])}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--capture',type=Path);p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.capture:
        a.capture.parent.mkdir(parents=True,exist_ok=True)
        a.capture.write_text(json.dumps(capture(),indent=2)+'\n')
    elif a.verify:print(json.dumps(verify(json.loads(a.verify.read_text())),indent=2))
    else:p.error('Choose --capture or --verify')
