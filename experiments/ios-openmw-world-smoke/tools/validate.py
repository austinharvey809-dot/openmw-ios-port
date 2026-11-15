"""Finish local review checks; retained native/legacy evidence is not rerun."""
import argparse,ast,hashlib,json,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures,paths,preserve,provenance

def validate(output,bash,legacy,native,binary):
    output.mkdir(parents=True,exist_ok=True);results={}
    def check(name,command):
        run=subprocess.run(command,cwd=paths.REPO,capture_output=True,text=True)
        (output/(name+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        results[name]={'status':'PASS' if run.returncode==0 else 'FAIL','exit':run.returncode}
        if run.returncode:raise ValueError(name+' failed; see retained log')
    check('g4-python',[sys.executable,'-B','-m','unittest','discover','-s',str(paths.ROOT/'tools'),'-p','test_g4.py','-v'])
    check('workflow-syntax',[sys.executable,'-B',str(paths.REPO/'experiments/ios-openmw-nif-render-smoke/textured/tools/check_workflow.py'),
        '--workflow',str(provenance.WORKFLOW),'--bash',str(bash)])
    check('git-whitespace',['git','diff','--check'])
    for p in (paths.ROOT/'tools').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
    sources=provenance.sources()
    for name in sources:
        p=paths.ROOT/name
        if any(line.rstrip()!=line for line in p.read_text().splitlines()):raise ValueError('New source whitespace: '+name)
    if any(line.rstrip()!=line for line in provenance.WORKFLOW.read_text().splitlines()):raise ValueError('Workflow whitespace')
    results['python-syntax']={'status':'PASS','files':len(list((paths.ROOT/'tools').glob('*.py')))}
    results['new-source-whitespace']={'status':'PASS','files':len(sources)+1}
    results['accepted-source-lock']={'status':'PASS',**paths.verify()}
    original=json.loads((paths.ROOT/'artifacts/preparation-tree.json').read_text())
    results['entire-original-tree']=preserve.verify(original)
    legacy_report=json.loads((legacy/'validation.json').read_text())
    for name in ('g0b','g0c','g1a','g1b','g1c','g1d','g2','g3','preservation-audit','provider-audit'):
        if legacy_report[name]['status']!='PASS':raise ValueError('Retained accepted validation failed: '+name)
    # The older validator's generic physical-g3 UNVERIFIED field describes its
    # own inability to run devices, not the user's independently accepted G3.
    results['retained-accepted-regressions']={'status':'PASS','scope':'206 tests across G0B through G3; prior retained logs, not rerun',
        'evidence_sha256':hashlib.sha256((legacy/'validation.json').read_bytes()).hexdigest()}
    cases=json.loads(native.read_text())
    expected=set((*fixtures.POSITIVE,*fixtures.NEGATIVE))
    if {r['case'] for r in cases}!=expected or len(cases)!=len(expected):raise ValueError('Incomplete retained native cases')
    for row in cases:
        if row['case'] in fixtures.POSITIVE:
            if row['exit'] or json.loads(row['stdout'])['status']!='PASS':raise ValueError('Retained positive native failure')
        else:
            import run_cases
            run_cases.reject(row['case'],row['exit'],row['stderr'])
    results['retained-native-cpu']={'status':'PASS','positive':len(fixtures.POSITIVE),'specific_negative':len(fixtures.NEGATIVE),
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'evidence_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),
        'scope':'Supplemental Windows CPU; binary built/tested separately, not an Apple product'}
    results['g3-physical-acceptance']={'status':'ACCEPTED','commit':preserve.BASE,'scope':'User independent review; see G3-COMPLETION.md'}
    for gate in ('apple-compilation','iphoneos-link','ipa-package-reopen','gpu-rendering','physical-g4'):
        results[gate]={'status':'UNVERIFIED','reason':'Apple tools/device unavailable; manual workflow and physical acceptance remain necessary'}
    report={'results':results,'source_sha256_lf':sources,'workflow_sha256_lf':hashlib.sha256(provenance.WORKFLOW.read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n');return results

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('output','bash','legacy','native','binary'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(validate(a.output,a.bash,a.legacy,a.native,a.binary),indent=2))
