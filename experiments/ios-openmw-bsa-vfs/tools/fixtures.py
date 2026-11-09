"""Original deterministic BSA/VFS inputs and read-only runtime protocol; no game data."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

BASE = (
    (b'Meshes\\IOSProbe.BIN', b'\x00OMW\xff\nVFS\0'),
    (b'Textures\\Caf\xe9X.TXT', b'Encoded archive filename; original synthetic bytes.\n'),
    (b'Docs\\OnlyBase.TXT', b'Base-only original payload.\n'),
)
OVERLAY = (
    (b'mEsHeS//IOSProbe.bin', b'Override original payload.\x00\xfe'),
    (b'Docs\\OnlyOverride.TXT', b'Override-only original payload.\n'),
)
MASK = (1 << 32) - 1


def name_hash(name):
    """Two-word table for the synthetic original-format directory."""
    low, high = 0, 0
    half = len(name) // 2
    for index, value in enumerate(name[:half]):
        low ^= value << ((8 * index) & 31)
    for index, value in enumerate(name[half:]):
        word = value << ((8 * index) & 31)
        high ^= word
        rotate = word & 31
        if rotate:
            high = ((high >> rotate) | (high << (32 - rotate))) & MASK
    return low & MASK, high & MASK


def archive(entries):
    names, payloads, rows = bytearray(), bytearray(), []
    for name, payload in entries:
        if not name or b'\0' in name or not payload:
            raise ValueError('Synthetic entries require a filename and nonempty payload')
        rows.append((name_hash(name), len(payload), len(payloads), len(names)))
        names.extend(name + b'\0')
        payloads.extend(payload)
    rows.sort(key=lambda row: row[0])
    directory = (b''.join(struct.pack('<II', size, offset) for _, size, offset, _ in rows)
                 + b''.join(struct.pack('<I', offset) for _, _, _, offset in rows) + names)
    hashes = b''.join(struct.pack('<II', *value) for value, _, _, _ in rows)
    return struct.pack('<III', 0x100, len(directory), len(rows)) + directory + hashes + payloads


def archives():
    good = archive(BASE)
    wrong_magic = bytearray(good)
    struct.pack_into('<I', wrong_magic, 0, 0xDEADBEEF)
    return {
        'base.bsa': good,
        'overlay.bsa': archive(OVERLAY),
        'unsupported.bsa': bytes(wrong_magic),
        'unexpected.bsa': archive((*BASE, (b'Unexpected\\Extra.TXT', b'Not in the expected synthetic manifest.\n'))),
        'incomplete.bsa': archive(BASE[:-1]),
    }


def snapshot(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Fixture tree must not contain symlinks')
        key = path.relative_to(directory).as_posix()
        result[key] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else '<directory>'
    return result


def run_cases(reader, directory):
    directory.mkdir(parents=True, exist_ok=True)
    inputs = archives()
    missing = directory / 'must-not-be-created.bsa'
    if missing.exists() or missing.is_symlink():
        raise RuntimeError('Missing-file fixture path must not already exist')
    for name, data in inputs.items():
        path = directory / name
        if path.is_symlink():
            raise RuntimeError('Fixture output must not be a symlink')
        path.write_bytes(data)
    (directory / 'not-a-file').mkdir(exist_ok=True)
    before = snapshot(directory)
    if set(before) != {*inputs, 'not-a-file'}:
        raise RuntimeError('Unexpected existing entries in owned synthetic-input directory')
    cases = (
        ('integration', ('verify', 'base.bsa', 'overlay.bsa'), 'OpenMW BSA/VFS integration passed;'),
        ('missing-archive', ('reject-archive', missing.name), 'REJECTED by existing-file/original-format input policy'),
        ('directory', ('reject-archive', 'not-a-file'), 'REJECTED by existing-file/original-format input policy'),
        ('wrong-format', ('reject-archive', 'unsupported.bsa'), 'REJECTED by existing-file/original-format input policy'),
        ('unexpected-index', ('reject-index', 'unexpected.bsa'), 'REJECTED unexpected/missing synthetic VFS index entry'),
        ('incomplete-index', ('reject-index', 'incomplete.bsa'), 'REJECTED unexpected/missing synthetic VFS index entry'),
    )
    for label, (mode, *names), marker in cases:
        command = [str(reader.resolve()), mode, *(str((directory / name).resolve()) for name in names)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        print(label + ': ' + completed.stdout.strip(), flush=True)
        if completed.stderr:
            print(completed.stderr, flush=True)
        if snapshot(directory) != before or missing.exists():
            raise RuntimeError('Reader modified the input tree or created an archive: ' + label)
        if completed.returncode != 0 or marker not in completed.stdout:
            raise RuntimeError(f'Real BSA/VFS fixture failed ({completed.returncode}): {label}')
    for name, digest in before.items():
        print(digest + '  ' + name, flush=True)
    print('Six synthetic BSA/VFS cases passed with unchanged input tree.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True,
                        help='Owned build/test directory; the five known synthetic archive files are overwritten here')
    args = parser.parse_args()
    run_cases(args.reader, args.directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
