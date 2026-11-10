"""Deterministic TES3/STAT + original BSA fixtures; runtime uses the genuine C++ readers."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


esm = load_module('milestone_d_fixture_bytes', ROOT.parent / 'ios-openmw-esm/tools/fixtures.py')
bsa = load_module('milestone_c_fixture_bytes', ROOT.parent / 'ios-openmw-bsa-vfs/tools/fixtures.py')
BASE_PAYLOAD = b'\x00OMW-E\xff\n\x00synthetic-model'
OVERLAY_PAYLOAD = b'Override-E\x00\xfe'
IDENTIFIER = b'eIOSStatic\0'
MODEL = b'TeSt.NIF\0'
RESOURCE = b'Meshes\\Test.NIF'


def stat_file(kind=1, model=MODEL, name=IDENTIFIER, extra=b''):
    body = (esm.subrecord(b'NAME', name) if name is not None else b'')
    body += esm.subrecord(b'MODL', model) if model is not None else b''
    return esm.tes3_header(kind) + esm.record(b'STAT', body + extra)


def inputs():
    good = stat_file()
    unsupported = bytearray(bsa.archive(((RESOURCE, BASE_PAYLOAD),)))
    struct.pack_into('<I', unsupported, 0, 0xDEADBEEF)
    return {
        'valid.esm': good,
        'valid.esp': stat_file(kind=0),
        'normalized.esm': stat_file(model=b'\\\\TeSt.NIF\0'),
        'no-stat.esm': esm.tes3_header(), # Deliberately inconsistent declared count, checked by caller.
        'no-name.esm': stat_file(name=None),
        'no-model.esm': stat_file(model=None), # Accepted by Static::load; rejected by fixture policy.
        'deleted.esm': stat_file(extra=esm.subrecord(b'DELE', b'\0\0\0')),
        'unknown-sub.esm': stat_file(extra=esm.subrecord(b'NOPE', b'original')),
        'wrong-tag.esm': b'NOPE' + good[4:],
        'oversized.esm': esm.patch_u32(good, 324 + 4, len(good)),
        'base.bsa': bsa.archive(((RESOURCE, BASE_PAYLOAD), (b'Docs\\Adjacent.bin', b'Adjacent entry sentinel.'))),
        'overlay.bsa': bsa.archive(((b'mEsHeS//TEST.NIF', OVERLAY_PAYLOAD),)),
        'missing-resource.bsa': bsa.archive(((b'Docs\\Only.txt', b'No model in this archive.'),)),
        'unsupported.bsa': bytes(unsupported),
    }


# Every tuple runs a fresh process. Completion markers prevent accidental success.
CASES = (
    ('esm', 'read', 'valid.esm', 'base.bsa', 'PASS resource:'),
    ('esp', 'esp', 'valid.esp', 'base.bsa', 'PASS resource:'),
    ('ascii-normalization', 'normalized', 'normalized.esm', 'base.bsa', 'PASS resource:'),
    ('base-then-overlay', 'base-first', 'valid.esm', 'base.bsa', 'PASS resource:'),
    ('overlay-then-base', 'overlay-first', 'valid.esm', 'base.bsa', 'PASS resource:'),
    ('missing-resource', 'missing-resource', 'valid.esm', 'missing-resource.bsa', 'PASS missing-resource'),
    ('missing-record', 'missing-record', 'no-stat.esm', 'base.bsa', 'PASS missing-record'),
    ('missing-name', 'reject-esm', 'no-name.esm', 'base.bsa', 'PASS reject-esm'),
    ('unknown-subrecord', 'reject-esm', 'unknown-sub.esm', 'base.bsa', 'PASS reject-esm'),
    ('wrong-header', 'reject-esm', 'wrong-tag.esm', 'base.bsa', 'PASS reject-esm'),
    ('truncated-record', 'reject-esm', 'oversized.esm', 'base.bsa', 'PASS reject-esm'),
    ('absent-model', 'reject-policy', 'no-model.esm', 'base.bsa', 'PASS reject-policy'),
    ('deleted-object', 'reject-policy', 'deleted.esm', 'base.bsa', 'PASS reject-policy'),
    ('missing-esm', 'missing-esm', 'must-not-be-created.esm', 'base.bsa', 'PASS missing-esm'),
    ('missing-archive', 'reject-archive', 'valid.esm', 'must-not-be-created.bsa', 'PASS reject-archive'),
    ('unsupported-archive', 'reject-archive', 'valid.esm', 'unsupported.bsa', 'PASS reject-archive'),
)


def snapshot(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Unexpected directory/symlink in synthetic input tree')
        result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def prepare(directory):
    if directory.is_symlink():
        raise RuntimeError('Synthetic input root must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True)
    expected = inputs()
    # Never overwrite unknown or modified existing inputs. Reruns accept exact bytes only.
    before = snapshot(directory)
    if set(before) - set(expected):
        raise RuntimeError('Unexpected existing input tree entries')
    for name in before:
        if before[name] != hashlib.sha256(expected[name]).hexdigest():
            raise RuntimeError('Existing synthetic input bytes differ: ' + name)
    for name, data in expected.items():
        if name not in before:
            (directory / name).write_bytes(data)
    return snapshot(directory)


def run_cases(reader, directory):
    before = prepare(directory)
    for label, mode, esm_name, bsa_name, marker in CASES:
        command = [str(reader.resolve()), mode, str((directory / esm_name).resolve()),
                   str((directory / bsa_name).resolve()), str((directory / 'overlay.bsa').resolve())]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        finally:
            if snapshot(directory) != before:
                raise RuntimeError('Reader changed input tree or created a file: ' + label)
        print(label + ': ' + result.stdout.strip(), flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
        if result.returncode != 0 or marker not in result.stdout:
            raise RuntimeError(f'Genuine ESM/VFS fixture failed ({result.returncode}): {label}')
    for name, digest in before.items():
        print(digest + '  ' + name, flush=True)
    print('Sixteen synthetic ESM/VFS cases passed with unchanged input tree.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True, help='Owned synthetic input directory; exact-byte reruns only')
    args = parser.parse_args()
    run_cases(args.reader, args.directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
