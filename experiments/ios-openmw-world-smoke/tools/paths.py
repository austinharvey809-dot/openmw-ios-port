import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
def verify():
    lock=json.loads((ROOT/'accepted-source-lock.json').read_text())
    for name,expected in lock['source_sha256_lf'].items():
        path=(REPO/name).resolve()
        if not path.is_relative_to(REPO) or not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Accepted/upstream source changed: '+name)
    return {'accepted_g3_commit':lock['accepted_g3_commit'],'unchanged_sources':len(lock['source_sha256_lf'])}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
