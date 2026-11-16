"""Bind the isolated live-world component to genuine baseline resources."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import ROOT, REPO, digest as normalized_digest
from dependencies import acquire

WORKFLOW = REPO / '.github/workflows/ios-openmw-liveworld-device.yml'
G5 = REPO / 'experiments/ios-openmw-engine-smoke'
sys.path.insert(0, str(G5 / 'tools'))
spec = importlib.util.spec_from_file_location('g6_baseline_g5_provenance', G5 / 'tools/provenance.py')
baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    return {path.relative_to(ROOT).as_posix(): normalized_digest(path.read_bytes())
        for path in ROOT.rglob('*') if path.is_file()
        and not {'artifacts', 'build', 'private', '__pycache__'} & set(path.relative_to(ROOT).parts)}


def new_resources():
    return {'settings-default.cfg', 'g6-engine.json', 'g6-renderer.json', 'g6-mygui-view.json',
        'Licenses/G6-SDL.txt', 'Licenses/G6-Recast.txt', 'Licenses/G6-ICU.txt',
        'Licenses/G6-ICU-data.txt', 'Licenses/G6-FreeType-LICENSE.txt',
        'Licenses/G6-FreeType-FTL.txt', 'Licenses/G6-FreeType-GPLv2.txt'}


def baseline_contract(manifest):
    baseline.accepted_contract(manifest['accepted_g4_build'])
    if manifest['source_sha256_lf'] != baseline.sources():
        raise ValueError('Published G5 source identity differs')
    if manifest['workflow_sha256_lf'] != normalized_digest(baseline.WORKFLOW.read_bytes()):
        raise ValueError('Published G5 workflow differs')
    if manifest['engine_lock'] != json.loads((G5 / 'engine-lock.json').read_text()):
        raise ValueError('Published G5 engine lock differs')
    if manifest['new_dependencies'] != json.loads((G5 / 'dependencies.json').read_text()):
        raise ValueError('Published G5 dependency pins differ')
    expected = set(manifest['accepted_g4_build']['public_resources_sha256']) | {
        'Licenses/G5-Lua-readme.html', 'g5-engine.json'}
    if set(manifest['public_resources_sha256']) != expected:
        raise ValueError('G5 baseline resource inventory differs')


def prepare(output, g5_public, dependencies, lua):
    baseline.verify_lua(lua)
    manifest = json.loads((g5_public / 'g5-build.json').read_text())
    baseline_contract(manifest)
    verified = acquire(dependencies, offline=True)
    public = output / 'public'; public.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest['public_resources_sha256'].items():
        raw = (g5_public / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError('G5 baseline resource changed: ' + name)
        target = public / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    (public / 'settings-default.cfg').write_bytes((REPO / 'files/settings-default.cfg').read_bytes())
    (public / 'g6-engine.json').write_bytes((output / 'projection.json').read_bytes())
    (public / 'g6-renderer.json').write_bytes((output / 'renderer-view.json').read_bytes())
    view = {'original_header_sha256': '58bab3e34ea4c0041e7c87ec14362ae3ba29f2899766e733202641d6de695296',
        'projected_header_sha256': digest((output / 'mygui/MyGUI_UString.h').read_bytes()),
        'unicode_char': 'char32_t', 'code_point': 'char16_t',
        'abi': 'All genuine MyGUI core sources and consumers compile with this view; no prebuilt MyGUI'}
    (public / 'g6-mygui-view.json').write_text(json.dumps(view, indent=2) + '\n', encoding='utf-8')
    source = {name: Path(item['source']) for name, item in verified.items()}
    sdl_license = next((source['sdl'] / name for name in ('LICENSE.txt', 'COPYING.txt')
        if (source['sdl'] / name).is_file()), None)
    if not sdl_license:
        raise ValueError('Genuine SDL license unavailable')
    licenses = {'SDL': sdl_license, 'Recast': source['recast'] / 'License.txt',
        'ICU': source['icu'] / 'icu4c/LICENSE', 'ICU-data': source['icu_data'] / 'LICENSE',
        'FreeType-LICENSE': source['freetype'] / 'LICENSE.TXT',
        'FreeType-FTL': source['freetype'] / 'docs/FTL.TXT',
        'FreeType-GPLv2': source['freetype'] / 'docs/GPLv2.TXT'}
    for name, path in licenses.items():
        (public / ('Licenses/G6-' + name + '.txt')).write_bytes(path.read_bytes())
    inventory = {path.relative_to(public).as_posix(): digest(path.read_bytes())
        for path in public.rglob('*') if path.is_file() and path.name != 'g6-build.json'}
    if set(inventory) != set(manifest['public_resources_sha256']) | new_resources():
        raise ValueError('Unexpected G6 public resource inventory')
    result = {'schema': 1, 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'g5_checkpoint': 'cb089f4141782f6c136d68d7e71b03f4f30b73a9',
        'g5_apple_acceptance': 'PENDING; runner allocation failures did not execute source',
        'baseline_g5_build': manifest, 'source_sha256_lf': sources(),
        'workflow_sha256_lf': normalized_digest(WORKFLOW.read_bytes()),
        'engine_lock': json.loads((ROOT / 'engine-lock.json').read_text()),
        'new_dependencies': json.loads((ROOT / 'dependencies.json').read_text()),
        'public_resources_sha256': inventory,
        'capabilities': {'genuine_cellstore_worldmodel': True, 'full_world_scene_activation': False,
            'actors_simulated': False, 'runtime_deletion': False, 'physical_acceptance': 'UNVERIFIED'}}
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    (public / 'g6-build.json').write_bytes(raw)
    (output / 'G6Expected.hpp').write_text('#pragma once\nnamespace G6Expected {inline constexpr char SHA[]="'
        + digest(raw) + '";inline constexpr char Commit[]="' + result['commit'] + '";}\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('output', 'g5-public', 'dependencies', 'lua'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, args.g5_public, args.dependencies, args.lua), indent=2))
