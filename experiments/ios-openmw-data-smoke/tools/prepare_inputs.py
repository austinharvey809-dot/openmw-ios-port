"""Verify unchanged E/OSG sources and stage two original synthetic bundle inputs, offline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
MANIFEST = ROOT / 'data/fixtures.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


auditor = module('f_genuine_e_auditor', ROOT.parent / 'ios-openmw-esm-vfs/tools/audit_sources.py')
fixtures = module('f_original_e_fixtures', ROOT.parent / 'ios-openmw-esm-vfs/tools/fixtures.py')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture_bytes(manifest=None):
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    require(manifest['schema_version'] == 1, 'Unknown fixture schema')
    require(set(manifest['inputs']) == {'valid.esm', 'base.bsa'}, 'Exactly two E fixture inputs required')
    generated = fixtures.inputs()
    selected = {name: generated[name] for name in manifest['inputs']}
    for name, data in selected.items():
        require(manifest['inputs'][name] == {'size': len(data), 'sha256': digest(data)}, 'Fixture hash/size mismatch: ' + name)
    resource = manifest['resource']
    require(resource == {'id': 'eIOSStatic', 'model': 'TeSt.NIF', 'key': 'meshes/test.nif',
            'size': len(fixtures.BASE_PAYLOAD), 'hex': fixtures.BASE_PAYLOAD.hex(),
            'sha256': digest(fixtures.BASE_PAYLOAD)}, 'Synthetic resource expectations differ from E')
    return selected


def prepare(output, osg_source, config):
    output, osg_source = Path(output).resolve(), Path(osg_source).resolve()
    require(output != REPO and output != ROOT and not output.is_relative_to(osg_source), 'Unsafe output directory')
    require(not output.is_relative_to(REPO) or output.is_relative_to(ROOT), 'Output cannot alter earlier milestones')
    require(not output.is_relative_to(ROOT / 'src') and not output.is_relative_to(ROOT / 'data')
            and not output.is_relative_to(ROOT / 'tools'), 'Output cannot overwrite implementation inputs')
    audit = auditor.audit(osg_source=osg_source)
    data = fixture_bytes()
    esm_manifest = json.loads(auditor.esm_audit.MANIFEST.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    template = (osg_source / 'src/osg/Config.in').read_text(encoding='utf-8')
    expected_config = re.sub(r'^#cmakedefine (\w+)$', lambda m:
        '#define ' + m[1] if esm_manifest['osg_config_defines'][m[1]] else '/* #undef ' + m[1] + ' */', template, flags=re.M)
    config_data = Path(config).read_bytes()
    require(config_data.replace(b'\r\n', b'\n').decode('utf-8') == expected_config, 'Generated OSG Config mismatch')
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Cannot verify current OpenMW commit')
    source_manifest = json.loads(auditor.MANIFEST.read_text(encoding='utf-8'))
    validation_files = [ROOT / 'CMakeLists.txt', ROOT / 'Info.plist.in', MANIFEST, Path(__file__)]
    validation_files += sorted((ROOT / 'src').glob('*'))
    validation_files += [ROOT.parent / 'ios-openmw-esm-vfs/tests/esm_vfs_check.cpp',
                         ROOT.parent / 'ios-openmw-esm-vfs/CMakeLists.txt']
    metadata = {'schema_version': 1, 'source_commit': commit, 'osg_revision': auditor.esm_audit.OSG_REVISION,
        'genuine_engine_units': 20, 'registration_helper_units': 1,
        'scope': 'prepared source provenance; not device runtime proof',
        'project_source_sha256_lf': source_manifest['project_sha256_lf'],
        'osg_source_sha256_lf': esm_manifest['osg_sha256_lf'],
        'osg_config_sha256': digest(config_data), 'fixture_manifest_sha256': digest(MANIFEST.read_bytes()),
        'validation_source_sha256': {p.relative_to(REPO).as_posix(): digest(p.read_bytes()) for p in validation_files},
        'source_audit': audit}
    metadata_bytes = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode('utf-8')
    resources = output / 'resources'
    inputs = resources / 'Fixtures'
    inputs.mkdir(parents=True, exist_ok=True)
    for name, contents in data.items():
        (inputs / name).write_bytes(contents)
    shutil.copy2(MANIFEST, inputs / 'fixtures.json')
    (resources / 'data-build.json').write_bytes(metadata_bytes)
    licenses = resources / 'Licenses'; licenses.mkdir(exist_ok=True)
    shutil.copy2(REPO / 'LICENSE', licenses / 'OpenMW-LICENSE.txt')
    shutil.copy2(osg_source / 'LICENSE.txt', licenses / 'OSG-LICENSE.txt')
    provenance = resources / 'Provenance/osg'; provenance.mkdir(parents=True, exist_ok=True)
    (provenance / 'Config').write_bytes(config_data)
    header = output / 'include/FixtureExpectations.hpp'; header.parent.mkdir(exist_ok=True)
    constants = {'SourceCommit': commit, 'OSGRevision': metadata['osg_revision'],
        'BuildMetadataSHA256': digest(metadata_bytes), 'FixtureManifestSHA256': digest(MANIFEST.read_bytes()),
        'ObjectId': manifest['resource']['id'], 'Model': manifest['resource']['model'],
        'ResourceKey': manifest['resource']['key'], 'PayloadSHA256': manifest['resource']['sha256']}
    text = '#pragma once\n#include <array>\n#include <cstdint>\nnamespace OpenMWIOSDataSmoke::Expected {\n'
    text += ''.join('inline constexpr char ' + name + '[] = ' + json.dumps(value) + ';\n' for name, value in constants.items())
    text += 'inline constexpr std::array<std::uint8_t, 24> Payload = {'
    text += ', '.join('0x%02x' % b for b in fixtures.BASE_PAYLOAD) + '};\n}\n'
    header.write_text(text, encoding='utf-8')
    print(json.dumps({'prepared': True, 'fixtures': manifest['inputs'], 'resource_sha256': manifest['resource']['sha256'],
                      'source_commit': commit, 'scope': metadata['scope']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--osg-source', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.output, args.osg_source, args.config)
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('Data-smoke preparation failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
