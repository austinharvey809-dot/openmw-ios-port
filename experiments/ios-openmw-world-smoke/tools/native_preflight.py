"""Compile the actual configured new iPhoneOS consumers before library builds."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import provenance
import dependency_preflight
import osg_compat
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
    new_osg=osg_compat.configured(build)
    # Compile actual targets once. The final app build reuses these outputs;
    # every serializer/plugin/added-library TU is covered with its exact flags.
    with (output/'new-osg-build.log').open('w') as log:
        early=subprocess.run(['cmake','--build',str(build),'--target',*osg_compat.TARGETS,
            'openmw-g4-osg-registration-check','--parallel','3'],stdout=log,stderr=subprocess.STDOUT,text=True)
    if early.returncode:raise ValueError('Early new OSG target compilation failed; see new-osg-build.log')
    objects=osg_compat.compiled(build,new_osg)
    (output/'new-osg-objects.json').write_text(json.dumps(objects,indent=2)+'\n')
    import package
    product=Path((build/'g4-registration-Release.txt').read_text().strip())
    link=package.p.core.macho(product.read_bytes())
    if link['filetype']!=2 or link['minimum_os']!=(18,0,0):raise ValueError('Registration link probe is not an iPhoneOS 18 executable')
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
    return {'status':'PASS','compiled_consumers':len(results),'new_osg_objects':len(objects),
        'registration_link_probe':link,'dependencies':dependencies,
        'scope':'Apple dependency archive/consumer syntax checks; final app linking, GPU and device rendering remain separate gates'}
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('build','sdk','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.build.resolve(),a.sdk.resolve(),a.output.resolve()),indent=2))
