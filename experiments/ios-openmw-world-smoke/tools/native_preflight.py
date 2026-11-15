"""Compile the actual configured new iPhoneOS consumers before library builds."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import provenance
import dependency_preflight
def syntax_arguments(args):
    result=[];skip=False
    for arg in args:
        if skip:skip=False;continue
        if arg in ('-o','-MF','-MT','-MQ'):skip=True;continue
        if arg in ('-c','-MD','-MMD','-MP'):continue
        result.append(arg)
    return result+['-fsyntax-only']
def run(build,sdk,output):
    if sys.platform!='darwin':raise ValueError('iPhoneOS preflight requires the genuine Apple SDK/toolchain')
    provenance.configured(build,sdk);output.mkdir(parents=True,exist_ok=True)
    dependencies=dependency_preflight.run(build,sdk,output/'dependencies')
    commands=json.loads((build/'compile_commands.json').read_text());results=[]
    selected=[e for e in commands if 'IOSOpenMWWorld.dir' in e.get('output',e.get('command','')) or
        ('g4-upstream.dir' in e.get('output',e.get('command','')) and
         (Path(e['file']).is_relative_to(provenance.ROOT/'src') or Path(e['file']).name in
          ('nifloader.cpp','scenemanager.cpp','imagemanager.cpp','shadervisitor.cpp','statesetupdater.cpp','terraindrawable.cpp','material.cpp','mwshadowtechnique.cpp','bulletshapemanager.cpp')))]
    if len(selected)<15:raise ValueError('Incomplete new device consumer preflight')
    for index,entry in enumerate(selected):
        command=syntax_arguments(provenance.arguments(entry))
        result=subprocess.run(command,cwd=entry['directory'],capture_output=True,text=True)
        (output/(str(index)+'-'+Path(entry['file']).name+'.log')).write_text(result.stdout+result.stderr)
        results.append({'source':entry['file'],'command':command,'exit':result.returncode})
        (output/'commands-and-results.json').write_text(json.dumps(results,indent=2)+'\n')
        if result.returncode:raise ValueError('Early iPhoneOS compile failed: '+entry['file'])
    return {'status':'PASS','compiled_consumers':len(results),'dependencies':dependencies,
        'scope':'Apple dependency archive/consumer syntax checks; final app linking, GPU and device rendering remain separate gates'}
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('build','sdk','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.build.resolve(),a.sdk.resolve(),a.output.resolve()),indent=2))
