"""Mechanical, hash-guarded reuse of the accepted G4 platform coordinator.

No scene, physics or streaming algorithms are forked here. Only the content-index
dependency, milestone identity and GL label dispatch hook change. Generated views
are build products, never edits to the accepted milestone or upstream checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_engine import ROOT, REPO, function_span

G4 = REPO / 'experiments/ios-openmw-world-smoke'


def prepare(output, defaults):
    lock = json.loads((ROOT / 'engine-lock.json').read_text())
    for name, expected in lock['sources'].items():
        if hashlib.sha256((REPO/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Frontend source provenance mismatch: '+name)
    output.mkdir(parents=True,exist_ok=True)
    result={}
    for name in lock['frontend']:
        text=(G4/name).read_text(encoding='utf-8').replace('G4','G5').replace('g4-','g5-')
        if name=='tests/world_check.cpp':
            # These are authored fixture payload bytes, not milestone identity.
            text=text.replace('G5-loose-priority','G4-loose-priority').replace('G5-last-archive','G4-last-archive')
        if name=='src/WorldIndex.hpp':
            text='#pragma once\n#include "EngineIndex.hpp"\n'
        if name=='device/src/OSGScene.hpp':
            text='#include "LabelDispatch.hpp"\n'+text
            anchor='        G5::initializeGLCapabilities(window,G5::deviceContextCurrent,checkpoint);'
            if text.count(anchor)!=1: raise ValueError('Startup hook anchor changed')
            text=text.replace(anchor,anchor+'\n        checkpoint("osg.object-label-api="+G5::configureLabels(*state));')
        if name=='device/src/main.mm':
            anchor='        auto index=std::make_unique<G5::WorldIndex>(profile.contentPaths(path));'
            if text.count(anchor)!=1:raise ValueError('Engine diagnostic anchor changed')
            text=text.replace(anchor,anchor+'\n        report[@"content_store"]=@"MWWorld::ESMStore";\n'
                +'        report[@"engine_cells"]=@(index->cells.getSize());\n'
                +'        report[@"engine_books"]=@(index->store().get<ESM::Book>().getSize());\n'
                +'        report[@"engine_npcs"]=@(index->store().get<ESM::NPC>().getSize());')
        target=output/Path(name).name
        if target.name in result: raise ValueError('Generated basename collision')
        target.write_bytes(text.encode());result[target.name]=hashlib.sha256(text.encode()).hexdigest()
    text=(G4/'src/WorldIndex.cpp').read_text()
    start,end=function_span(text,'std::vector<ESM::CellRef> WorldIndex::references(')
    text='#include "EngineIndex.hpp"\n#include <map>\n#include <algorithm>\nnamespace G5 {\n'+text[start:end].replace('WorldIndex::','EngineIndex::').replace('G4','G5')+'\n}\n'
    (output/'References.cpp').write_bytes(text.encode())
    (output/'G5Defaults.hpp').write_bytes(defaults.read_bytes().replace(b'G4Defaults',b'G5Defaults'))
    (output/'frontend-view.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--defaults',type=Path,required=True)
    a=p.parse_args();prepare(a.output,a.defaults)
