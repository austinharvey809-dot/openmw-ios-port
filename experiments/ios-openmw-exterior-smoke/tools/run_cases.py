import argparse,hashlib,json,subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures
def reject(mode,code,stderr):
    expected=fixtures.NEGATIVE[mode]
    if not expected.strip() or code!=1 or expected not in stderr:raise ValueError('Wrong G3 native rejection '+mode+' exit='+str(code)+': '+stderr)
def run(binary):
    results=[]
    for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixtures.write(root,mode)
            before={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in fixtures.inputs(mode)}
            result=subprocess.run([str(binary),str(root),mode],capture_output=True,text=True,timeout=120)
            if mode in fixtures.POSITIVE:
                if result.returncode:raise ValueError(mode+': '+result.stderr)
                report=json.loads(result.stdout)
                if report['status']!='PASS' or report['cells']!=9 or report['terrain_triangles']!=73728:raise ValueError('False native PASS')
            else:reject(mode,result.returncode,result.stderr)
            if before!={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}:raise ValueError('Native test modified inputs')
            results.append({'case':mode,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);args=p.parse_args();print(json.dumps(run(args.binary.resolve()),indent=2))
