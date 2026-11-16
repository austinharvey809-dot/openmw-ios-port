"""Inspect actual G6 build commands, projections and platform boundaries."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import ROOT, REPO, digest

G4 = REPO / 'experiments/ios-openmw-world-smoke'
sys.path.insert(0, str(G4 / 'tools'))
spec = importlib.util.spec_from_file_location('_g6_accepted_command_audit', G4 / 'tools/provenance.py')
accepted = importlib.util.module_from_spec(spec); spec.loader.exec_module(accepted)


def configuration(build):
    matches = list(build.rglob('g6-config-Release.json'))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous actual G6 target configuration')
    return json.loads(matches[0].read_text())


def include_paths(arguments):
    paths = []
    for index, value in enumerate(arguments):
        if value.startswith('-I') and value != '-I': paths.append(Path(value[2:]).resolve())
        elif value in ('-I', '-isystem') and index + 1 < len(arguments): paths.append(Path(arguments[index + 1]).resolve())
    return paths


def consumer(entry, generated, osg, sdk=None):
    args = accepted.arguments(entry)
    accepted.standard(args)
    if not accepted.double(args): raise ValueError('G6 Bullet precision mismatch')
    includes = include_paths(args)
    if osg not in includes: raise ValueError('Actual generated OSG headers missing')
    if any('osg-math' in str(path) for path in includes[:includes.index(osg)]):
        raise ValueError('Math-only OSG provider precedes real provider')
    if (generated / 'mygui').resolve() not in includes: raise ValueError('G6 MyGUI ABI view absent')
    view = includes.index((generated / 'mygui').resolve())
    if any(path.name == 'include' and path.parent.name == 'MyGUIEngine' for path in includes[:view]):
        raise ValueError('Original MyGUI ABI precedes compatibility view')
    for name in ('MYGUI_STATIC', 'MYGUI_USE_FREETYPE', 'U_STATIC_IMPLEMENTATION'):
        if '-D' + name not in args: raise ValueError('G6 dependency ABI definition absent: ' + name)
    if sdk:
        selected = accepted.platform(args)
        if selected['-arch'] != ['arm64'] or [Path(p).resolve() for p in selected['-isysroot']] != [sdk.resolve()]:
            raise ValueError('G6 consumer architecture/SDK mismatch')
        if [x for x in args if x.startswith('-miphoneos-version-min=')] != ['-miphoneos-version-min=18.0']:
            raise ValueError('G6 deployment target missing/conflicting')
        if not sdk.name.lower().startswith('iphoneos'): raise ValueError('Genuine iPhoneOS SDK required')
        if any('mmacosx-version-min' in a or 'mios-simulator-version-min' in a for a in args):
            raise ValueError('G6 conflicting host/simulator platform flag')
        if selected['-target'] and (len(selected['-target']) != 1 or not re.fullmatch(
                r'arm64-apple-ios18\.0(?:\.0)?', selected['-target'][0])):
            raise ValueError('G6 conflicting target triple')
    return accepted.platform(args)


def audit(build, sdk=None):
    accepted.paths.verify()
    config = configuration(build); generated = Path(config['generated']).resolve()
    lock = json.loads((ROOT / 'engine-lock.json').read_text())
    for name, want in lock['sources'].items():
        if digest((REPO / name).read_bytes()) != want: raise ValueError('Original engine/G5 source drift: ' + name)
    projection = json.loads((generated / 'projection.json').read_text())
    if projection['originals'] != lock['sources'] or projection['rules'] != lock['projections']:
        raise ValueError('G6 projection provenance differs')
    for name, want in projection['products'].items():
        if hashlib.sha256((generated / name).read_bytes()).hexdigest() != want:
            raise ValueError('Generated engine source drift: ' + name)
    renderer = json.loads((generated / 'renderer-view.json').read_text())
    renderer_lock = json.loads((REPO / 'experiments/ios-openmw-engine-smoke/engine-lock.json').read_text())
    if renderer['source_inputs'] != renderer_lock['sources']:
        raise ValueError('G6 renderer no longer binds the preserved G5 inputs')
    frontend = {Path(name).name for name in renderer_lock['frontend']} | {'G6Defaults.hpp', 'LabelDispatch.hpp'}
    if set(renderer['products']) != frontend:
        raise ValueError('G6 renderer view inventory mismatch')
    for name, want in renderer['products'].items():
        if hashlib.sha256((generated / name).read_bytes()).hexdigest() != want:
            raise ValueError('Generated renderer source drift: ' + name)
    expected = {REPO / name for name in lock['units']}
    expected |= {generated / name for name in lock['projections'] if name.endswith('.cpp')}
    expected |= {ROOT / 'src/LiveWorld.cpp'}
    expected |= {REPO / name for name in ('components/esm/luascripts.cpp', 'components/lua/serialization.cpp',
        'components/lua/configuration.cpp', 'components/misc/color.cpp')}
    entries = json.loads((build / 'compile_commands.json').read_text())
    def target(name):
        return [e for e in entries if '/' + name + '.dir/' in e.get('output', e.get('command', '')).replace('\\', '/')]
    core = target('g6-live-world')
    if len(core) != len(expected) or {Path(e['file']).resolve() for e in core} != {p.resolve() for p in expected}:
        raise ValueError('G6 exact genuine engine compilation inventory mismatch')
    selected = core + target('g6-world') + target('IOSOpenMWLiveWorld')
    platforms = [consumer(e, generated, Path(config['osg_include']).resolve(), sdk) for e in selected]
    if not platforms or any(value != platforms[0] for value in platforms):
        raise ValueError('G6 core/render consumers disagree on target platform')
    if sdk and len(target('IOSOpenMWLiveWorld')) != 1: raise ValueError('Actual G6 UIKit consumer absent/duplicated')
    for name in ('osg/Config', 'osg/GL', 'osg/Version', 'OpenThreads/Config', 'OpenThreads/Version'):
        if not (Path(config['osg_include']) / name).is_file(): raise ValueError('Generated provider header missing: ' + name)
    states = [e for e in entries if Path(e['file']).as_posix().endswith('/src/osg/State.cpp')]
    if (sdk or states) and len(states) != 1: raise ValueError('G6 must use exactly one genuine OSG provider')
    dependencies = {}
    for name in ('g6-mygui', 'g6-icu-common', 'g6-icu-i18n', 'g6-detour', 'freetype', 'g5-lua'):
        units = target(name)
        if not units: raise ValueError('G6 genuine dependency source inventory absent: ' + name)
        for unit in units:
            if accepted.platform(accepted.arguments(unit)) != platforms[0]:
                raise ValueError('G6 dependency platform differs: ' + name)
        dependencies[name] = len(units)
    mygui = target('g6-mygui')
    if len(mygui) != 97: raise ValueError('Pinned genuine MyGUI core inventory differs')
    if dependencies['g6-icu-common'] + dependencies['g6-icu-i18n'] != 438:
        raise ValueError('Pinned genuine ICU implementation inventory differs')
    return {'status': 'PASS', 'core_units': len(core), 'core_render_consumers': len(selected),
        'genuine_dependencies': dependencies, 'osg_provider_units': len(states),
        'imported_windows_desktop_provider': os.name == 'nt' and not states,
        'scope': 'Configured source/provenance/platform only; no Apple execution or device acceptance'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--sdk', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.build.resolve(), args.sdk), indent=2))
