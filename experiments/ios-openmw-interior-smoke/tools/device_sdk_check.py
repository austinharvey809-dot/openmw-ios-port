"""Early SDK-only iPhoneOS compile/link gate; never executes the device product."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'ios-openmw-nif-render-smoke/textured/tools'))
import support
core=support.package.core
def frameworks():
    names=json.loads((ROOT/'device/frameworks.json').read_text())
    if not names or len(set(names))!=len(names) or any(not n.isascii() or not n.isalnum() for n in names):
        raise ValueError('Invalid/duplicate framework inventory')
    return names
def run(output):
    output.mkdir(parents=True,exist_ok=True)
    sdk=Path(subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip())
    core.check_sdk(sdk)
    compiler=subprocess.check_output(['xcrun','--sdk','iphoneos','--find','clang++'],text=True).strip()
    binary=output/'g2-sdk-link-check'
    command=[compiler,'-std=c++20','-fobjc-arc','-target','arm64-apple-ios18.0','-isysroot',str(sdk),
        str(ROOT/'tests/device_framework_probe.mm'),'-Wl,-no_adhoc_codesign','-o',str(binary)]
    for name in frameworks():command+=['-framework',name]
    (output/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    result=subprocess.run(command,capture_output=True,text=True)
    (output/'compile-link.log').write_text(result.stdout+result.stderr)
    result.check_returncode()
    details=core.macho(binary.read_bytes())
    if details['filetype']!=2 or details['minimum_os']!=(18,0,0):raise ValueError('Wrong probe executable/deployment')
    dependencies=[{'dependency':name,**core.system_dependency(name,sdk,'18.0')} for name in details['dependencies']]
    if '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics' not in details['dependencies']:
        raise ValueError('Probe lost its CoreGraphics dependency')
    return {'sdk':str(sdk),'frameworks':frameworks(),'dependencies':dependencies,'platform':details['platform'],
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'scope':'SDK compile/link and Mach-O inspection only; full app and physical rendering unverified'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.output),indent=2))
