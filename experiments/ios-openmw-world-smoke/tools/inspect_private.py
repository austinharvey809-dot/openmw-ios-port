"""Opt-in CPU inspection of privately owned content; exports aggregates only.

Never copies models, textures, ESM/BSA payloads or reference/placement arrays.
Generated GLSL evidence comes from GPL OpenMW sources, not game asset bytes.
"""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path


def inspect(binary,shaders,data,glslang,output):
    data=data.resolve(strict=True);output=output.resolve()
    if output.is_relative_to(data):raise ValueError('Do not write results into the original installation')
    output.mkdir(parents=True,exist_ok=True)
    def hashes():
        result={}
        for name in ('Morrowind.esm','Morrowind.bsa'):
            with (data/name).open('rb') as stream:result[name]=hashlib.file_digest(stream,'sha256').hexdigest()
        return result
    before=hashes();results=[]
    modes=['inspect-stream']+['inspect-interior:'+name for name in (
        "Seyda Neen, Fargoth's House",'Seyda Neen, Lighthouse','Seyda Neen, Census and Excise Office',
        "Seyda Neen, Arrille's Tradehouse",'Imperial Prison Ship','Addamasartus')]
    for index,mode in enumerate(modes):
        # Shader strings are scratch GPL source evidence and never archived here.
        with tempfile.TemporaryDirectory() as temp:
            command=[str(binary.resolve()),str(data),str(shaders.resolve()),mode,temp]
            run=subprocess.run(command,capture_output=True,text=True,timeout=180)
            (output/(str(index)+'-diagnostic.log')).write_text(run.stderr,encoding='utf-8')
            result={'case':mode,'exit':run.returncode,'scope':'Windows CPU only; iPhoneOS/GPU/physical G4 UNVERIFIED'}
            if run.returncode==0:
                result['report']=json.loads(run.stdout);result['shader_links']=[]
                for vert in sorted(Path(temp).glob('*.vert')):
                    linked=subprocess.run([str(glslang.resolve()),'-l',str(vert),str(vert.with_suffix('.frag'))],capture_output=True,text=True)
                    result['shader_links'].append({'program':vert.stem,'exit':linked.returncode})
                    if linked.returncode:result['shader_failure']=linked.stdout+linked.stderr
            else:result['error']=run.stderr[-4000:]
            results.append(result)
    after=hashes()
    report={'scope':'Private read-only CPU/source-shader inspection; no physical acceptance',
        'input_sha256_before':before,'input_sha256_after':after,'inputs_unchanged':before==after,
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'results':results}
    (output/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
    if before!=after:raise ValueError('Private inputs changed')
    if any(r['exit'] or any(link['exit'] for link in r.get('shader_links',[])) for r in results):
        raise ValueError('Private inspection failed; inspect retained aggregate results')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('binary','shaders','data','glslang','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(inspect(a.binary,a.shaders,a.data,a.glslang,a.output),indent=2))
