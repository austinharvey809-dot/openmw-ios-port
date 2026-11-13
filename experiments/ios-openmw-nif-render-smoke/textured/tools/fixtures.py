"""Self-authored six-record MW NIF, RGBA TGA and genuine ESM/BSA fixture encoders.

These encoders create test inputs, never replace the actual native NIF/image readers.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
DATA = ROOT / 'data'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g0 = load('_g1c_original_encoders', REPO / 'experiments/ios-openmw-nif-smoke/tools/generate_fixtures.py')
le, string, boolean, record, net = g0.le, g0.string, g0.mw_bool, g0.record, g0.object_net
existing = g0.load_existing_fixture_module()
MODEL = b'Meshes\\TeXtUrEd.NIF'
IMAGE = b'Textures\\Patterns\\NifTest.TGA'
TEXTURE_REFERENCE = 'Patterns\\NifTest.tga'


def av(name, properties=()):
    # Exact original NiAVObject transform/framing, with a genuine property list.
    original = g0.av_object(name)
    return original[:-8] + le('I', len(properties)) + b''.join(le('i', p) for p in properties) + boolean(False)


def nif(*, uv=((0., 0.), (1., 0.), (0., 1.)), texture=TEXTURE_REFERENCE, reference=4):
    node = av('G1CRoot') + le('IiI', 1, 1, 0)
    shape = av('G1CTextured', (3, 5)) + le('ii', 2, -1)
    geometry = (le('H', 3) + boolean(True) + le('9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
                + boolean(False) + le('4f', 0, 0, 0, 1) + boolean(False)
                + le('H', 1) + boolean(True) + b''.join(le('2f', *v) for v in uv)
                + le('HI3HH', 1, 3, 0, 1, 2, 0))
    # NiProperty -> NiObjectNET; flags, Modulate, 1 texture; bool is int32 in MW.
    texture_property = (net('BaseTexture') + le('HII', 0, 2, 1) + boolean(True)
                        + le('iIII', reference, 0, 0, 0) + bytes(6))
    # External texture byte, filename, TrueColor / No mipmaps / Smooth alpha, static byte.
    source = net('ExternalTGA') + le('B', 1) + string(texture) + le('IIIB', 2, 0, 2, 1)
    material = net('UnlitDiffuse') + le('H14f', 0, 1, 1, 1, .75, 1, .5, 0, 0, 0, 0, 0, 0, 0, 1)
    return (b'NetImmerse File Format, Version 4.0.0.2\n' + le('II', 0x04000002, 6)
            + record('NiNode', node) + record('NiTriShape', shape) + record('NiTriShapeData', geometry)
            + record('NiTexturingProperty', texture_property) + record('NiSourceTexture', source)
            + record('NiMaterialProperty', material) + le('Ii', 1, 0))


def pixels():
    # Bottom-left row first, alternating cyan/yellow with a red UV-origin corner.
    return bytes(channel for y in range(8) for x in range(8)
                 for channel in ((255, 32, 32, 255) if x < 2 and y < 2 else
                                 ((32, 224, 255, 255) if (x // 2 + y // 2) % 2 else (255, 224, 32, 255))))


def tga():
    rgba = pixels()
    bgra = b''.join(bytes((rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3])) for i in range(0, len(rgba), 4))
    return le('BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, 8, 8, 32, 8) + bgra


def fixture_bytes():
    model, image = nif(), tga()
    archive = lambda n, t: existing.bsa.archive(((MODEL, n), (IMAGE, t)))
    invalid = b'X' + model[1:]
    return {'textured.esm': existing.stat_file(model=b'TeXtUrEd.NIF\0'),
            'textured.nif': model, 'pattern.tga': image,
            'textured.bsa': archive(model, image),
            'invalid-header.bsa': archive(invalid, image),
            'invalid-reference.bsa': archive(nif(reference=99), image),
            'invalid-uv.bsa': archive(nif(uv=((float('nan'), 0), (1, 0), (0, 1))), image),
            'unsafe-texture.bsa': archive(nif(texture='../private.tga'), image),
            'missing-texture.bsa': existing.bsa.archive(((MODEL, model),)),
            'bad-image.bsa': archive(model, image[:12])}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cases():
    model, image = nif(), tga()
    variants = [('textured.bsa', model, image, ''),
                ('invalid-header.bsa', b'X' + model[1:], image, 'Invalid NIF header'),
                ('invalid-reference.bsa', nif(reference=99), image, 'Genuine NIF parse rejected'),
                ('invalid-uv.bsa', nif(uv=((float('nan'), 0), (1, 0), (0, 1))), image, 'Invalid UV'),
                ('unsafe-texture.bsa', nif(texture='../private.tga'), image, 'Unsafe texture'),
                ('missing-texture.bsa', model, image, 'Missing/unexpected texture'),
                ('bad-image.bsa', model, image[:12], 'TGA decode rejected')]
    return [{'archive': archive, 'nif_sha256': digest(n), 'texture_sha256': digest(t),
             'diagnostic': diagnostic} for archive, n, t, diagnostic in variants]


def manifest():
    return {'schema_version': 1, 'origin': 'Self-authored synthetic assets, no Bethesda content',
            'nif_records': 6, 'resource_key': 'meshes/textured.nif', 'texture_key': 'textures/patterns/niftest.tga',
            'uv': [[0., 0.], [1., 0.], [0., 1.]], 'diffuse': [.75, 1., .5, 1.],
            'rgba_sha256': digest(pixels()), 'sampler': 'NEAREST/CLAMP_TO_EDGE; no mipmaps', 'cases': cases(),
            'files': {name: {'size': len(data), 'sha256': digest(data)} for name, data in sorted(fixture_bytes().items())}}


def audit(directory=DATA):
    expected = fixture_bytes()
    def require(condition):
        if not condition:
            raise ValueError('G1C fixture inventory/bytes mismatch')
    require(directory.is_dir() and not directory.is_symlink())
    require({p.name for p in directory.iterdir()} == set(expected) | {'fixture-manifest.json'})
    for name, data in expected.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == data)
    path = directory / 'fixture-manifest.json'
    require(not path.is_symlink() and json.loads(path.read_text()) == manifest())
    return manifest()


def generate():
    DATA.mkdir(parents=True, exist_ok=True)
    values = fixture_bytes()
    values['fixture-manifest.json'] = (json.dumps(manifest(), sort_keys=True, indent=2) + '\n').encode()
    for name, data in values.items():
        path = DATA / name
        if path.exists():
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError('Refusing to replace changed fixture: ' + name)
        else:
            path.write_bytes(data)
    audit()


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--generate', action='store_true')
    args = cli.parse_args()
    if args.generate:
        generate()
    print(json.dumps(audit(), indent=2))
