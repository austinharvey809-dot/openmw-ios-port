import argparse,json,subprocess,tempfile,hashlib
from pathlib import Path
import fixtures
def run(binary):
    results=[]
    for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixtures.write(root,mode);before={n:hashlib.sha256(b).hexdigest() for n,b in fixtures.inputs(mode).items()}
            r=subprocess.run([str(binary),str(root),'furn_de_rug_02',mode],capture_output=True,text=True,timeout=90)
            if mode in fixtures.POSITIVE:
                if r.returncode:raise ValueError(r.stderr)
                result=json.loads(r.stdout)
                if not(result['status']=='PASS' and result['vertices']==4 and result['triangles']==2 and result['shapes']==1):raise ValueError('Decoded status/counts differ')
            elif r.returncode!=1:raise ValueError('Invalid fixture accepted/crashed: '+mode)
            elif fixtures.NEGATIVE[mode] not in r.stderr:raise ValueError('Wrong rejection: '+mode+' '+r.stderr)
            if mode in fixtures.NEGATIVE and mode not in ('cycle','missing'):
                if not all(x in r.stderr for x in ('G1D stage=','node=','property=')):raise ValueError('Missing processing context: '+mode)
            if mode=='unknown-property' and not all(x in r.stderr for x in ('stage=properties','NiTriShape#2[Quad]','NiDitherProperty#7')):
                raise ValueError('Unsupported property diagnostic lacks exact record identity')
            if before!={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}:raise ValueError('Inputs modified')
            results.append({'case':mode,'exit':r.returncode,'stderr':r.stderr,'stdout':r.stdout})
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.binary.resolve()),indent=2))
