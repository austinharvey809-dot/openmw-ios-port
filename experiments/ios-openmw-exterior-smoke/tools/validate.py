"""Local review checks. Private inspection is opt-in; no game bytes are exported."""
import argparse,ast,hashlib,json,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import paths,mesh_bridge

def run(output,osg,bash,glslang=None):
    output.mkdir(parents=True,exist_ok=True);results={}
    def check(name,command):
        proc=subprocess.run(command,capture_output=True,text=True,cwd=paths.REPO)
        (output/(name+'.log')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
        results[name]={'status':'PASS' if proc.returncode==0 else 'FAIL','exit':proc.returncode}
        print(name,results[name]['status'],flush=True)
    for name,where,pattern in (
        ('g3','ios-openmw-exterior-smoke/tools','test_g3.py'),('g2','ios-openmw-interior-smoke/tools','test_g2.py'),
        ('g1d','ios-openmw-nif-render-smoke/real-model/tools','test_g1d.py'),('g1c','ios-openmw-nif-render-smoke/textured/tools','test_*.py'),
        ('g1b','ios-openmw-nif-render-smoke/device/tools','test_g1b.py'),('g1a','ios-openmw-nif-render-smoke/tools','test_*.py'),
        ('g0c','ios-openmw-nif-device-smoke/tools','test_g0c.py'),('g0b','ios-openmw-nif-smoke/tools','test_*.py')):
        check(name,[sys.executable,'-B','-m','unittest','discover','-s',str(paths.REPO/'experiments'/where),'-p',pattern,'-v'])
    workflow=paths.REPO/'.github/workflows/ios-openmw-exterior-device.yml'
    check('workflow-syntax',[sys.executable,'-B',str(paths.REPO/'experiments/ios-openmw-nif-render-smoke/textured/tools/check_workflow.py'),'--workflow',str(workflow),'--bash',str(bash)])
    check('preservation-audit',[sys.executable,'-B',str(paths.REPO/'experiments/ios-openmw-nif-render-smoke/tools/contracts.py'),'--osg-source',str(osg),'--check-local-build15'])
    check('provider-audit',[sys.executable,'-B',str(paths.REPO/'experiments/ios-openmw-nif-render-smoke/textured/tools/resources.py'),'audit','--osg-reference',str(osg),'--local-build15'])
    mesh_bridge.generate(output/'generated');code=(paths.ROOT/'device/src/OSGScene.hpp').read_text()
    vertex=re.search(r'VERTEX, R"\((.*?)\)"',code,re.S).group(1)
    fragment=re.search(r'G3Shader::Material\+R"\((.*?)\)"',code,re.S).group(1)
    material=(output/'generated/MaterialShader.hpp').read_text().split('R"G3(',1)[1].rsplit(')G3"',1)[0]
    vert=output/'exterior.vert';frag=output/'exterior.frag';vert.write_text(vertex);frag.write_text('#version 300 es\nprecision highp float;\n'+material+'\n'+fragment)
    if glslang and glslang.is_file():check('essl-link',[str(glslang),'-l',str(vert),str(frag)])
    else:results['essl-link']={'status':'UNVERIFIED','reason':'glslang unavailable'}
    for p in paths.ROOT.rglob('*.py'):
        if not {'artifacts','build','__pycache__'}&set(p.relative_to(paths.ROOT).parts):ast.parse(p.read_text(),filename=str(p))
    results['python-syntax']={'status':'PASS'}
    check('git-whitespace',['git','diff','--check'])
    sources=[p for p in paths.ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(paths.ROOT).parts)]
    for p in sources+[workflow]:
        if any(line.rstrip()!=line for line in p.read_text().splitlines()):raise ValueError('New source whitespace '+str(p))
    results['new-file-whitespace']={'status':'PASS','files':len(sources)+1}
    results['accepted-source-lock']={'status':'PASS',**paths.verify()}
    results['macos-and-iphoneos']={'status':'UNVERIFIED','reason':'Apple SDK/toolchain unavailable locally; supplemental Windows CPU results are recorded separately'}
    results['physical-g3']={'status':'UNVERIFIED','reason':'Requires independent iPhone evidence after native build'}
    (output/'validation.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(item['status']=='FAIL' for item in results.values()):raise ValueError('Local validation failed; inspect retained logs')
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--osg-source',type=Path,required=True);p.add_argument('--bash',type=Path,required=True);p.add_argument('--glslang',type=Path);a=p.parse_args()
    run(a.output.resolve(),a.osg_source.resolve(),a.bash.resolve(),a.glslang.resolve() if a.glslang else None)
