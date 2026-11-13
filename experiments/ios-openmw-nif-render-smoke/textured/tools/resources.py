"""G1C source closure, exact extra fixture inventory and configured-consumer audits."""
import argparse
import ast
import copy
import json
from pathlib import Path
import shlex
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures
from support import ROOT, REPO, DEVICE, base, package, require, sha, host

WORKFLOW = REPO / '.github/workflows/ios-openmw-textured-nif-device-smoke.yml'
EXTRA = ('components/misc/resourcehelpers.cpp', 'components/misc/resourcehelpers.hpp',
         'components/resource/objectcache.hpp', 'components/resource/cachestats.hpp')


def sources():
    paths = [p for p in ROOT.rglob('*') if p.is_file() and not
             {'build', 'artifacts', '__pycache__'} & set(p.relative_to(ROOT).parts)] + [WORKFLOW]
    return {p.relative_to(REPO).as_posix(): sha(p.read_bytes().replace(b'\r\n', b'\n')) for p in paths}


def checked_decoder(osg):
    pinned = json.loads((ROOT / 'source-closure.json').read_text())
    decoder = osg / 'src/osgPlugins/tga/ReaderWriterTGA.cpp'
    require(decoder.is_file() and not decoder.is_symlink()
            and sha(decoder.read_bytes().replace(b'\r\n', b'\n')) == pinned['tga_sha256_lf'],
            'TGA decoder differs from pinned source')


def audit(osg, local=False):
    report = base.audit(osg, local)
    fixtures.audit()
    pinned = json.loads((ROOT / 'source-closure.json').read_text())
    require(pinned['osg_revision'] == host.LOCK['osg_revision'], 'G1C OSG pin changed')
    for name, digest in pinned['openmw_sha256_lf'].items():
        require(sha((REPO / name).read_bytes().replace(b'\r\n', b'\n')) == digest, 'G1C resource source changed: ' + name)
    require(set(pinned['openmw_sha256_lf']) == set(EXTRA), 'Resource source inventory changed')
    checked_decoder(osg)
    preserved = json.loads((ROOT / 'g1b-source-sha256.json').read_text())
    require(bool(preserved), 'Missing G1B source preservation')
    for name, digest in preserved.items():
        require(sha((REPO / name).read_bytes().replace(b'\r\n', b'\n')) == digest, 'Completed G1B changed: ' + name)
    for path in (ROOT / 'tools').glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    return {'g1b': report, 'g1b_preserved_files': len(preserved), 'fixture_files': len(fixtures.fixture_bytes()),
            'additional_sources': pinned, 'scope': 'G1C source only; no native/physical texture claim'}


def extend(output):
    resources = base.files(output / 'resources')
    metadata = json.loads(resources.pop('g1b-build.json'))
    resources['Licenses/G1C-TGA-NOTICES.txt'] = (ROOT / 'NOTICES.txt').read_bytes()
    for path in fixtures.DATA.iterdir():
        resources['TexturedFixtures/' + path.name] = path.read_bytes()
    metadata['g1c'] = {'schema_version': 1, 'fixture_manifest': fixtures.audit(),
                       'source_sha256_lf': sources(),
                       'source_closure': json.loads((ROOT / 'source-closure.json').read_text()),
                       'scope': 'Synthetic textured resource; physical visibility unverified'}
    metadata['resources_sha256'] = {name: sha(data) for name, data in sorted(resources.items())}
    resources['g1b-build.json'] = (json.dumps(metadata, sort_keys=True, indent=2) + '\n').encode()
    for name, data in resources.items():
        path = output / 'resources' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    constants = {'BuildSHA256': sha(resources['g1b-build.json']), 'SourceCommit': metadata['source_commit'],
                 'GeometrySHA256': metadata['geometry_sha256']}
    (output / 'include/G1BExpectations.hpp').write_text('#pragma once\nnamespace G1BExpected {\n' + ''.join(
        'inline constexpr char ' + name + '[] = "' + value + '";\n' for name, value in constants.items()) + '}\n')
    manifest = metadata['g1c']['fixture_manifest']
    constants = {'NifSHA256': manifest['files']['textured.nif']['sha256'],
                 'TextureSHA256': manifest['files']['pattern.tga']['sha256'], 'PixelsSHA256': manifest['rgba_sha256']}
    (output / 'include/G1CExpectations.hpp').write_text('#pragma once\nnamespace G1CExpected {\n' + ''.join(
        'inline constexpr char ' + name + '[] = "' + value + '";\n' for name, value in constants.items()) + '}\n')
    return {'resource_files': len(resources), 'metadata_sha256': sha(resources['g1b-build.json'])}


def prepared_resources(prepared):
    # Original gate still verifies all original fixtures, SDK/pins/source provenance and every resource hash.
    resources, metadata = original_prepared(prepared)
    require(metadata['g1c']['fixture_manifest'] == fixtures.audit(), 'G1C fixture metadata mismatch')
    require(metadata['g1c']['source_sha256_lf'] == sources(), 'G1C source changed after preparation')
    require(metadata['g1c']['source_closure'] == json.loads((ROOT / 'source-closure.json').read_text()),
            'G1C source closure mismatch')
    require(resources.get('Licenses/G1C-TGA-NOTICES.txt') == (ROOT / 'NOTICES.txt').read_bytes(), 'Missing G1C/TGA notices')
    require({name.removeprefix('TexturedFixtures/'): data for name, data in resources.items()
             if name.startswith('TexturedFixtures/')} == base.files(fixtures.DATA), 'G1C fixture inventory/bytes mismatch')
    return resources, metadata


original_prepared = package.prepared_resources
package.prepared_resources = prepared_resources


def configured(build, bullet):
    report = base.configured(build, bullet)
    entries = json.loads((build / 'compile_commands.json').read_text())
    required = ('/TextureAdapter.cpp', '/components/misc/resourcehelpers.cpp', '/texture_check.cpp',
                '/osgPlugins/tga/ReaderWriterTGA.cpp')
    selected = []
    canonical = (build / 'osg/include').as_posix()
    for suffix in required:
        values = [entry for entry in entries if Path(entry['file']).as_posix().endswith(suffix)]
        require(len(values) == 1, 'Missing/duplicate texture source: ' + suffix)
        entry = values[0]
        tokens = entry.get('arguments') or shlex.split(entry['command'])
        includes = [token[2:] if token != '-I' else tokens[i + 1] for i, token in enumerate(tokens) if token.startswith('-I')]
        require(canonical in includes and all(includes.index(canonical) < i for i, value in enumerate(includes)
                if '/osg-math/include' in value), 'Texture consumer lacks canonical generated headers')
        if not suffix.endswith('ReaderWriterTGA.cpp'):
            base.require_cxx20(tokens)
        else:
            checked_decoder(Path(entry['file']).resolve().parents[3])
        require(not any('OpenGLES.framework' in token or 'OpenGL.framework' in token for token in tokens),
                'Alternate texture GL provider')
        selected.append(entry['file'])
    require(not any('/osgPlugins/' in Path(e['file']).as_posix() and
            not Path(e['file']).as_posix().endswith(required[-1]) for e in entries), 'Unexpected image plugin closure')
    report['textured_consumers'] = selected
    return report


def host_configured(build, bullet):
    precision = host.load('_g1c_host_precision', REPO / 'experiments/ios-openmw-nif-smoke/tools/validate_build.py')
    result = precision.audit(build, bullet)
    generated = build / 'g1a/g0b/osg/include'
    for name in host.GENERATED:
        path = generated / name
        require(path.is_file() and not path.is_symlink(), 'Missing host generated header: ' + name)
    commands = json.loads((build / 'compile_commands.json').read_text())
    for suffix in ('/GeometryAdapter.cpp', '/TextureAdapter.cpp', '/texture_check.cpp',
                   '/components/misc/resourcehelpers.cpp', '/osgPlugins/tga/ReaderWriterTGA.cpp'):
        found = [e for e in commands if Path(e['file']).as_posix().endswith(suffix)]
        require(len(found) == 1, 'Missing/duplicate host texture source: ' + suffix)
        tokens = found[0].get('arguments') or shlex.split(found[0]['command'])
        require('-I' + str(generated) in tokens or any(token == '-I' and tokens[i + 1] == str(generated)
                for i, token in enumerate(tokens)), 'Host consumer lacks real generated headers')
        if not suffix.endswith('ReaderWriterTGA.cpp'):
            base.require_cxx20(tokens)
    return {'precision': result, 'scope': 'Host configured only; native execution separate'}


def prepare(args):
    audit(args.osg_reference)
    checked_decoder(args.osg_renderer)  # The actual overlaid compiler input must match too.
    # Stage through a temporary tree, then copy only to approved build/artifact storage.
    output = args.output.resolve()
    require(not output.is_relative_to(REPO) or any(output.is_relative_to(ROOT / name) for name in ('build', 'artifacts')),
            'G1C output must be isolated build/artifact storage')
    for source in (args.osg_reference, args.osg_renderer, args.angle, args.bullet, fixtures.DATA):
        require(not output.is_relative_to(source.resolve()), 'Output overlaps an input')
    import shutil
    with tempfile.TemporaryDirectory() as directory:
        staged = copy.copy(args)
        staged.output = Path(directory) / 'prepared'
        base.prepare(staged)
        result = extend(staged.output)
        if output.exists():
            require(set(base.files(output)) <= set(base.files(staged.output)), 'Unexpected stale prepared inventory')
        shutil.copytree(staged.output, output, dirs_exist_ok=True)
    prepared_resources(output)
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('audit', 'prepare', 'configured', 'host-configured'))
    cli.add_argument('--osg-reference', type=Path, required=True)
    cli.add_argument('--local-build15', action='store_true')
    for name in ('osg-renderer', 'angle', 'bullet', 'generated', 'output', 'build'):
        cli.add_argument('--' + name, type=Path)
    args = cli.parse_args()
    result = audit(args.osg_reference, args.local_build15) if args.phase == 'audit' else (
        prepare(args) if args.phase == 'prepare' else
        (host_configured if args.phase == 'host-configured' else configured)(args.build.resolve(), args.bullet.resolve()))
    print(json.dumps(result, indent=2))
