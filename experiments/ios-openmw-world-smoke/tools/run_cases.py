"""Strict native gates with atomic, incremental evidence even for silent crashes."""
import argparse,base64,hashlib,json,signal,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures

def reject(mode,code,stderr):
    expected=fixtures.NEGATIVE[mode]
    if not expected.strip() or code!=1 or expected not in stderr:
        raise ValueError('Wrong native rejection '+mode+' exit='+str(code)+': '+stderr)

def save(output,results):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=output.parent,prefix=output.name+'.',suffix='.tmp',delete=False,encoding='utf-8') as stream:
        temporary=Path(stream.name)
        json.dump(results,stream,indent=2);stream.write('\n')
    try:temporary.replace(output)
    finally:temporary.unlink(missing_ok=True)

def text(value):
    return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''

def streams(row,stdout,stderr):
    for name,value in (('stdout',stdout),('stderr',stderr)):
        raw=value if isinstance(value,bytes) else text(value).encode('utf-8')
        row[name]=text(raw);row[name+'_base64']=base64.b64encode(raw).decode('ascii')

def capture(command,timeout):
    """Do not classify a crash/timeout/spawn error as an expected rejection."""
    started=time.monotonic()
    row={'command':[str(a) for a in command],'exit':None,'exit_hex':None,'signal':None,'signal_name':None,
        'stdout':'','stderr':'','stdout_base64':'','stderr_base64':'','timeout':False,'spawn_error':None,'platform':sys.platform}
    try:
        result=subprocess.run(row['command'],capture_output=True,timeout=timeout)
        row['exit']=result.returncode;streams(row,result.stdout,result.stderr)
        if result.returncode<0 and sys.platform!='win32':
            row['signal']=-result.returncode
            try:row['signal_name']=signal.Signals(-result.returncode).name
            except ValueError:row['signal_name']='signal-'+str(-result.returncode)
        else:row['exit_hex']=hex(result.returncode&0xffffffff)
    except subprocess.TimeoutExpired as error:
        row['timeout']=True;streams(row,error.stdout,error.stderr)
    except OSError as error:row['spawn_error']=str(error)
    row['elapsed_seconds']=time.monotonic()-started
    return row

def failure(row,output,reason):
    row.update(status='FAIL',failure=reason)
    return ValueError(row['case']+': '+reason+'; exit='+str(row['exit'])+' signal='+str(row['signal'])+
        ' ('+str(row['signal_name'])+'); stdout='+repr(row['stdout'][:2000])+'; stderr='+repr(row['stderr'][:2000])+
        '; retained evidence='+str(output))

def process_ok(row):
    if row['timeout']:raise ValueError('native subprocess timed out')
    if row['spawn_error']:raise ValueError('native subprocess could not start: '+row['spawn_error'])

def snapshot(root):
    result={}
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):raise ValueError('Unsafe authored input after subprocess')
        if path.is_file():result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def run(binary,shaders,output=None):
    output=Path(output) if output else fixtures.ROOT/'artifacts/native-cases.json'
    results=[];save(output,results)
    for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixtures.write(root,mode);before=snapshot(root)
            row={'case':mode,'status':'RUNNING','exit':None,'stdout':'','stderr':'','inputs_before_sha256':before,
                'expected_exit':0 if mode in fixtures.POSITIVE else 1,'expected_diagnostic':fixtures.NEGATIVE.get(mode)}
            results.append(row);save(output,results)
            row.update(capture([binary,root,shaders,mode],120))
            row['status']='CAPTURED';save(output,results)
            try:
                row['inputs_after_sha256']=snapshot(root)
                row['inputs_unchanged']=before==row['inputs_after_sha256']
                process_ok(row)
                if mode in fixtures.POSITIVE:
                    if row['exit']!=0:raise ValueError('positive native case returned nonzero')
                    report=json.loads(row['stdout'])
                    if not isinstance(report,dict) or report.get('status')!='PASS' or report['cells']!=9 or report['programs']<2:
                        raise ValueError('False genuine world PASS')
                else:reject(mode,row['exit'],row['stderr'])
                if not row['inputs_unchanged']:raise ValueError('Native case modified authored inputs')
            except (ValueError,KeyError,TypeError,OSError) as error:
                exception=failure(row,output,str(error));save(output,results);raise exception from error
            row['status']='PASS';save(output,results)
    return results

def run_startup(binary,output):
    row={'case':'startup-capabilities','status':'RUNNING','exit':None,'stdout':'','stderr':''};results=[row]
    save(output,results);row.update(capture([binary],30));row['status']='CAPTURED';save(output,results)
    try:
        process_ok(row)
        if row['exit']!=0:raise ValueError('startup native gate returned nonzero')
        result=json.loads(row['stdout'])
        if not isinstance(result,dict) or result.get('status')!='PASS' or type(result.get('checks')) is not int or result['checks']<1 or result.get('scope')!='genuine pinned OSG headless startup guards':
            raise ValueError('False native startup PASS')
    except (ValueError,KeyError,TypeError) as error:
        exception=failure(row,output,str(error));save(output,results);raise exception from error
    row['status']='PASS';save(output,results);return results

if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--binary',type=Path);group.add_argument('--startup-binary',type=Path)
    p.add_argument('--shaders',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.startup_binary:
        if a.shaders:p.error('--startup-binary does not consume world shaders')
        output=a.output or fixtures.ROOT/'artifacts/startup-case.json'
        result=run_startup(a.startup_binary.resolve(),output)
    else:
        if a.shaders is None:p.error('--binary requires --shaders')
        result=run(a.binary.resolve(),a.shaders.resolve(),a.output)
    print(json.dumps(result,indent=2))
