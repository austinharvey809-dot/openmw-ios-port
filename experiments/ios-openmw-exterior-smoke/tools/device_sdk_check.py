"""Retain accepted G2 framework preflight and add G3's new diagnostics SDK API."""
import argparse,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(output):
    spec=importlib.util.spec_from_file_location('_g3_accepted_framework_gate',ROOT.parent/'ios-openmw-interior-smoke/tools/device_sdk_check.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    report=old.run(output/'frameworks');command=json.loads((output/'frameworks/command.json').read_text())
    command=[str(ROOT/'tests/diagnostics_probe.mm') if v.endswith('/tests/device_framework_probe.mm') else v for v in command]
    binary=output/'g3-diagnostics-link-check';command[command.index('-o')+1]=str(binary)
    (output/'diagnostics-command.json').write_text(json.dumps(command,indent=2)+'\n')
    result=subprocess.run(command,capture_output=True,text=True);(output/'diagnostics-compile-link.log').write_text(result.stdout+result.stderr);result.check_returncode()
    details=old.core.macho(binary.read_bytes());sdk=Path(report['sdk'])
    if details['filetype']!=2 or details['minimum_os']!=(18,0,0):raise ValueError('Wrong diagnostics product platform/type/deployment')
    report['diagnostics_api_dependencies']=[old.core.system_dependency(n,sdk,'18.0') for n in details['dependencies']]
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();print(json.dumps(run(args.output),indent=2))
