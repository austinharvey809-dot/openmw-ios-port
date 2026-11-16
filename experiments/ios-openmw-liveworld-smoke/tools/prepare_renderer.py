"""Reuse G5's renderer; replace its snapshot merger with genuine live ownership."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import ROOT, REPO, digest, replace_once, write_if_changed


def prepare(source, output):
    lock = json.loads((REPO / 'experiments/ios-openmw-engine-smoke/engine-lock.json').read_text())
    for name, expected in lock['sources'].items():
        if digest((REPO / name).read_bytes()) != expected:
            raise ValueError('Preserved G5 renderer input changed: ' + name)
    generated = json.loads((source / 'frontend-view.json').read_text())
    products = {}
    for name in lock['frontend']:
        target = Path(name).name
        raw = (source / target).read_bytes()
        if hashlib.sha256(raw).hexdigest() != generated[target]:
            raise ValueError('G5 generated frontend hash mismatch: ' + target)
        text = raw.decode().replace('G5', 'G6').replace('g5-', 'g6-')
        if target == 'WorldIndex.hpp':
            text = '#pragma once\n#include "LiveWorld.hpp"\n'
        if target == 'Session.hpp':
            anchor = '    const Area& area()const{return *current;}'
            text = replace_once(text, anchor, anchor + '\n    Statistics liveDiagnostics()const{return index->diagnostics();}')
        if target == 'main.mm':
            anchor = '        auto index=std::make_unique<G6::WorldIndex>(profile.contentPaths(path));'
            text = replace_once(text, anchor,
                '        NSString* defaults=[[NSBundle mainBundle] pathForResource:@"settings-default" ofType:@"cfg"];\n'
                '        if(!defaults)throw std::runtime_error("G6 missing upstream settings resource");\n'
                '        auto index=std::make_unique<G6::WorldIndex>(profile.contentPaths(path),std::filesystem::path(defaults.UTF8String));')
            anchor = '        Evidence[@"world_loads"]=@(world.loads);Evidence[@"door_transitions"]=@(world.transitions);'
            text = replace_once(text, anchor, anchor
                + '\n        const auto live=world.liveDiagnostics();'
                + '\n        Evidence[@"live_world_store"]=@"MWWorld::WorldModel / CellStore / LiveCellRef";'
                + '\n        Evidence[@"live_loaded_cells"]=@(live.loadedCells);'
                + '\n        Evidence[@"live_registered_objects"]=@(live.registeredObjects);'
                + '\n        Evidence[@"live_raw_reference_reservations"]=@(live.rawReferences);'
                + '\n        Evidence[@"live_successful_loads"]=@(live.successfulLoads);'
                + '\n        Evidence[@"live_failed_loads"]=@(live.failedLoads);'
                + '\n        Evidence[@"live_maximum_cell_preparation_ms"]=@(live.maximumPreparationMs);')
        write_if_changed(output / target, text.encode())
        products[target] = hashlib.sha256(text.encode()).hexdigest()
    original_defaults = (source / 'G5Defaults.hpp').read_bytes()
    expected_defaults = (source.parent / 'g4-generated/G4Defaults.hpp').read_bytes().replace(b'G4Defaults', b'G5Defaults')
    if original_defaults != expected_defaults:
        raise ValueError('G5 clear-day defaults differ from preserved provider')
    defaults = original_defaults.replace(b'G5Defaults', b'G6Defaults')
    write_if_changed(output / 'G6Defaults.hpp', defaults)
    products['G6Defaults.hpp'] = hashlib.sha256(defaults).hexdigest()
    labels = REPO / 'experiments/ios-openmw-engine-smoke/src/LabelDispatch.hpp'
    text = labels.read_text().replace('G5', 'G6')
    write_if_changed(output / 'LabelDispatch.hpp', text.encode())
    products['LabelDispatch.hpp'] = hashlib.sha256(text.encode()).hexdigest()
    write_if_changed(output / 'renderer-view.json', (json.dumps({
        'schema': 1, 'g5_base': 'cb089f4141782f6c136d68d7e71b03f4f30b73a9',
        'g5_apple_acceptance': 'PENDING; two runner allocation failures, no source execution',
        'source_inputs': lock['sources'], 'products': products,
    }, indent=2) + '\n').encode('utf-8'))
    return products


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--g5', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.g5, args.output), indent=2))
