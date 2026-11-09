"""Original synthetic TES3/GMST bytes and genuine-reader subprocess protocol; no game data."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

AUTHOR = b'Original Caf\xe9 fixture'
DESCRIPTION = b'Original synthetic TES3 fixture; no game data.'
IDENTIFIER = b'iIOSProbe\0'
VALUE = -1234567


def subrecord(tag, data):
    if len(tag) != 4:
        raise ValueError('Subrecord tag must be four bytes')
    return tag + struct.pack('<I', len(data)) + data


def record(tag, data):
    if len(tag) != 4:
        raise ValueError('Record tag must be four bytes')
    return tag + struct.pack('<III', len(data), 0, 0) + data


def tes3_header(kind=1):
    if kind not in (0, 1):
        raise ValueError('Fixture kind must be ESP=0 or ESM=1')
    hedr = struct.pack('<Ii', 0x3FA66666, kind) + AUTHOR.ljust(32, b'\0') + DESCRIPTION.ljust(256, b'\0') + struct.pack('<i', 1)
    return record(b'TES3', subrecord(b'HEDR', hedr))


def synthetic_esm(kind=1):
    return tes3_header(kind) + record(b'GMST', subrecord(b'NAME', IDENTIFIER) + subrecord(b'INTV', struct.pack('<i', VALUE)))


def patch_u32(data, offset, value):
    changed = bytearray(data)
    struct.pack_into('<I', changed, offset, value)
    return bytes(changed)


def inputs():
    good = synthetic_esm()
    gmst = len(tes3_header())
    intv = gmst + 16 + len(subrecord(b'NAME', IDENTIFIER))
    short_sub = good[:intv + 6]  # Name plus only two of the four size bytes.
    return {
        'valid.esm': good,
        'valid.esp': synthetic_esm(0),
        'wrong-tag.esm': b'NOPE' + good[4:],
        'short-header.esm': good[:10],
        'oversized-record.esm': patch_u32(good, gmst + 4, 40),
        'wrong-value-size.esm': patch_u32(good, intv + 4, 3),
        'short-sub-header.esm': patch_u32(short_sub, gmst + 4, len(short_sub) - gmst - 16),
        # Keep record/file lengths consistent so the actual strict stream read,
        # rather than getRecHeader's size guard, demonstrates the EOF policy.
        'short-read.esm': patch_u32(good[:-1], gmst + 4, 29),
    }


CASES = (
    ('esm', ('read', 'valid.esm', '1'), 'OpenMW ESM fixture passed;'),
    ('esp', ('read', 'valid.esp', '0'), 'OpenMW ESM fixture passed;'),
    ('strict-valid', ('strict-read', 'valid.esm', '1'), 'OpenMW ESM fixture passed;'),
    ('wrong-tag', ('reject', 'wrong-tag.esm'), 'REJECTED by genuine ESM reader check'),
    ('short-header', ('reject', 'short-header.esm'), 'REJECTED by genuine ESM reader check'),
    ('record-size', ('reject', 'oversized-record.esm'), 'REJECTED by genuine ESM reader check'),
    ('value-size', ('reject', 'wrong-value-size.esm'), 'REJECTED by genuine ESM reader check'),
    ('sub-header', ('reject', 'short-sub-header.esm'), 'REJECTED by genuine ESM reader check'),
    ('strict-short-read', ('strict-reject', 'short-read.esm'), 'REJECTED short read by explicit caller stream policy'),
    ('missing', ('reject-missing', 'must-not-be-created.esm'), 'REJECTED missing file by genuine OpenMW file helper'),
)


def snapshot(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Unexpected non-file/symlink in synthetic input tree')
        result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run_cases(reader, directory):
    directory.mkdir(parents=True, exist_ok=True)
    missing = directory / 'must-not-be-created.esm'
    if missing.exists() or missing.is_symlink():
        raise RuntimeError('Missing-input sentinel must not already exist')
    for name, data in inputs().items():
        path = directory / name
        if path.is_symlink():
            raise RuntimeError('Fixture output must not be a symlink')
        path.write_bytes(data)
    before = snapshot(directory)
    if set(before) != set(inputs()):
        raise RuntimeError('Unexpected preexisting synthetic input')
    for label, (mode, name, *extra), marker in CASES:
        command = [str(reader.resolve()), mode, str((directory / name).resolve()), *extra]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        print(label + ': ' + result.stdout.strip(), flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
        if snapshot(directory) != before or missing.exists():
            raise RuntimeError('Reader changed the input tree or created a file: ' + label)
        if result.returncode != 0 or marker not in result.stdout:
            raise RuntimeError(f'Real ESM fixture failed ({result.returncode}): {label}')
    for name, digest in before.items():
        print(digest + '  ' + name, flush=True)
    print('Ten synthetic ESM cases passed with unchanged input tree.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True, help='Owned build/test directory; eight known original inputs are overwritten')
    args = parser.parse_args()
    run_cases(args.reader, args.directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
