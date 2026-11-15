import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures
def reject(mode,code,stderr):
    expected=fixtures.NEGATIVE[mode]
    if not expected.strip() or code!=1 or expected not in stderr:
        raise ValueError('Wrong native rejection '+mode+' exit='+str(code)+': '+stderr)
def run(binary,shaders,output=None):
    results=[]
    for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixtures.write(root,mode)
            before={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            result=subprocess.run([str(binary),str(root),str(shaders),mode],capture_output=True,text=True,timeout=120)
            if mode in fixtures.POSITIVE:
                if result.returncode:raise ValueError(mode+': '+result.stderr)
                report=json.loads(result.stdout)
                if report.get('status')!='PASS' or report['cells']!=9 or report['programs']<2:
                    raise ValueError('False genuine world PASS '+mode)
            else:reject(mode,result.returncode,result.stderr)
            after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            if before!=after:raise ValueError('Native case modified authored inputs: '+mode)
            results.append({'case':mode,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if output:output.write_text(json.dumps(results,indent=2)+'\n')
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--shaders',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    print(json.dumps(run(a.binary.resolve(),a.shaders.resolve(),a.output),indent=2))
