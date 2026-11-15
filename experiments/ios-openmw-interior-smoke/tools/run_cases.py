import argparse,hashlib,json,subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures
def check_rejection(mode,returncode,stderr):
    expected=fixtures.NEGATIVE[mode]
    if not expected.strip():raise ValueError('Empty native rejection contract: '+mode)
    if returncode!=1 or expected not in stderr:raise ValueError('Wrong native rejection '+mode+': '+stderr)
def run(binary):
    if any(not text.strip() for text in fixtures.NEGATIVE.values()):raise ValueError('Empty native rejection contract')
    results=[]
    for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixtures.write(root,mode)
            before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in fixtures.inputs(mode)}
            r=subprocess.run([str(binary),str(root),fixtures.CELL,mode],capture_output=True,text=True,timeout=90)
            if mode in fixtures.POSITIVE:
                if r.returncode:raise ValueError(mode+': '+r.stderr)
                data=json.loads(r.stdout)
                if data['status']!='PASS' or data['instances']!=6 or data['triangles']!=12:raise ValueError('Native gate failed: '+mode)
            else:check_rejection(mode,r.returncode,r.stderr)
            if before!={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}:raise ValueError('Inputs changed')
            results.append({'case':mode,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.binary.resolve()),indent=2))
