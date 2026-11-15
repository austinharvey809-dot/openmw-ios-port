"""Bind the explicit clear-day comparison profile to upstream OpenMW defaults."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'files/openmw.cfg'
def generate(output):
    values={}
    for line in SOURCE.read_text().splitlines():
        if line.startswith('fallback='):
            key,value=line.removeprefix('fallback=').split(',',1)
            if key in values:raise ValueError('Duplicate upstream fallback '+key)
            values[key]=value
    output.mkdir(parents=True,exist_ok=True)
    body='#pragma once\n#include <map>\n#include <string>\nnamespace G4Defaults {inline const std::map<std::string,std::string> Values={\n'
    body+=',\n'.join('{'+json.dumps(k)+','+json.dumps(v)+'}' for k,v in sorted(values.items()))+'\n};}\n'
    (output/'G4Defaults.hpp').write_text(body,newline='\n')
    (output/'g4-environment.json').write_text(json.dumps({'scope':'Fixed upstream clear-day defaults, not dynamic weather/sky acceptance',
        'upstream_cfg_sha256_lf':hashlib.sha256(SOURCE.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        'fallbacks':values},sort_keys=True,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();generate(a.output)
