"""Early genuine Apple consumers and strict per-object dependency inspection."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import audit, configuration, accepted, ROOT, REPO

G4 = REPO / 'experiments/ios-openmw-world-smoke'
sys.path.insert(0, str(G4 / 'tools'))
spec = importlib.util.spec_from_file_location('_g6_archive_preflight', G4 / 'tools/dependency_preflight.py')
archives = importlib.util.module_from_spec(spec); spec.loader.exec_module(archives)
spec = importlib.util.spec_from_file_location('_g6_genuine_syntax_preflight', G4 / 'tools/native_preflight.py')
syntax = importlib.util.module_from_spec(spec); spec.loader.exec_module(syntax)

EARLY = ('mygui', 'freetype', 'icu_common', 'icu_i18n', 'icu_data', 'detour', 'lua')


def consumers(build):
    config = configuration(build); generated = Path(config['generated']).resolve()
    entries = json.loads((build / 'compile_commands.json').read_text())
    names = {ROOT / 'src/LiveWorld.cpp', generated / 'cellstore.cpp',
        REPO / 'apps/openmw/mwclass/classes.cpp', REPO / 'apps/openmw/mwclass/npc.cpp',
        REPO / 'apps/openmw/mwrender/animation.cpp', REPO / 'apps/openmw/mwphysics/physicssystem.cpp',
        REPO / 'apps/openmw/mwworld/scene.cpp', REPO / 'components/settings/values.cpp'}
    selected = []
    for entry in entries:
        target = entry.get('output', entry.get('command', '')).replace('\\', '/')
        path = Path(entry['file']).resolve()
        is_g6 = any('/' + name + '.dir/' in target for name in ('g6-live-world', 'g6-scene-compile'))
        if is_g6 and path in names: selected.append(entry)
        elif '/IOSOpenMWLiveWorld.dir/' in target: selected.append(entry)
        elif '/g6-mygui.dir/' in target and path.name == 'MyGUI_UString.cpp': selected.append(entry)
        elif '/freetype.dir/' in target and path.name == 'ftsystem.c': selected.append(entry)
        elif '/g6-icu-common.dir/' in target and path.name == 'putil.cpp': selected.append(entry)
        elif '/g6-icu-i18n.dir/' in target and path.name == 'msgfmt.cpp': selected.append(entry)
    if not names <= {Path(entry['file']).resolve() for entry in selected}:
        raise ValueError('Focused genuine engine/Scene consumer inventory missing')
    return selected


def inspect(build, final=False):
    config = configuration(build)
    names = ('core', *EARLY) if final else EARLY
    return {name: archives.inspect_archive(Path(config['archives'][name])) for name in names}


def run(build, sdk, output):
    if sys.platform != 'darwin' or not sdk.is_dir() or not sdk.name.lower().startswith('iphoneos'):
        raise ValueError('Real macOS/iPhoneOS SDK required; Windows cannot satisfy Apple preflight')
    output.mkdir(parents=True, exist_ok=True)
    result = {'configured': audit(build, sdk), 'commands': [], 'status': 'RUNNING'}
    accepted.configured(build, sdk)
    selected = consumers(build)
    if sum(Path(entry['file']).name == 'main.mm' for entry in selected) != 1:
        raise ValueError('Actual UIKit G6 consumer missing')
    def save():
        (output / 'preflight.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    save()
    for index, entry in enumerate(selected):
        command = syntax.syntax_arguments(accepted.arguments(entry))
        completed = subprocess.run(command, cwd=entry['directory'], capture_output=True)
        (output / (str(index) + '-' + Path(entry['file']).name + '.log')).write_bytes(completed.stdout + completed.stderr)
        result['commands'].append({'file': entry['file'], 'command': command, 'exit': completed.returncode})
        save()
        if completed.returncode:
            raise ValueError('Focused Apple compilation failed: ' + entry['file'])
    with (output / 'genuine-dependency-build.log').open('wb') as log:
        completed = subprocess.run(['cmake', '--build', str(build), '--target',
            'g6-mygui', 'g6-icu-i18n', 'g6-detour', 'g5-lua', '--parallel', '3'],
            stdout=log, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise ValueError('Genuine G6 dependency build failed; retained log identifies the error')
    result['archives'] = inspect(build)
    result.update(status='PASS', scope='Apple consumer syntax and actual ARM64/iOS dependency objects; final app/IPA/device gates remain mandatory')
    save(); return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--final-archives', action='store_true')
    args = parser.parse_args()
    if args.audit:
        result = audit(args.build.resolve(), args.sdk)
    elif args.final_archives:
        if sys.platform != 'darwin': raise ValueError('Final Apple archives require actual macOS build products')
        result = {'status': 'PASS', 'archives': inspect(args.build.resolve(), True)}
    else:
        if not args.sdk or not args.output: parser.error('Apple preflight requires sdk/output')
        result = run(args.build.resolve(), args.sdk.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2))
