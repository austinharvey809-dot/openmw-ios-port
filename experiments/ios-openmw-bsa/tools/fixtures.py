"""Original synthetic Morrowind-format BSA bytes; never reads/downloads game data."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

ENTRIES = (
    (b'Meshes\\IOSProbe.BIN', b'\x00OMW\xff\nARCH'),
    (b'Textures\\IOSProbe.TXT', b'Original synthetic archive payload.\n'),
)
MASK = (1 << 32) - 1


def name_hash(name):
    """Independent fixture encoder for the archive's two 32-bit hash words."""
    split = len(name) // 2
    low = 0
    for index, value in enumerate(name[:split]):
        low ^= value << ((8 * index) & 31)
    high = 0
    for index, value in enumerate(name[split:]):
        word = value << ((8 * index) & 31)
        high ^= word
        rotation = word & 31
        if rotation:
            high = ((high >> rotation) | (high << (32 - rotation))) & MASK
    return low & MASK, high & MASK


def synthetic_archive():
    names, payloads, rows = bytearray(), bytearray(), []
    for name, payload in ENTRIES:
        rows.append((name_hash(name), len(payload), len(payloads), len(names)))
        names.extend(name + b'\0')
        payloads.extend(payload)
    # The on-disk directory/hash order differs from payload order. OpenMW's reader
    # must use offsets, then sort its FileStruct list by absolute payload offset.
    rows.sort(key=lambda row: row[0])
    directory_size = len(rows) * 12 + len(names)
    header = struct.pack('<III', 0x100, directory_size, len(rows))
    sizes_offsets = b''.join(struct.pack('<II', size, offset) for _, size, offset, _ in rows)
    name_offsets = b''.join(struct.pack('<I', offset) for _, _, _, offset in rows)
    hashes = b''.join(struct.pack('<II', *value) for value, _, _, _ in rows)
    return header + sizes_offsets + name_offsets + names + hashes + payloads


def replace_u32(data, offset, value):
    changed = bytearray(data)
    struct.pack_into('<I', changed, offset, value)
    return bytes(changed)


def cases():
    good = synthetic_archive()
    _, directory_size, count = struct.unpack_from('<III', good)
    names_start = 12 + 12 * count
    names_size = directory_size - 12 * count
    unterminated = bytearray(good)
    unterminated[names_start:12 + directory_size] = good[names_start:12 + directory_size].replace(b'\0', b'x')
    return {
        'valid.bsa': (good, False),
        'short-header.bsa': (good[:11], True),
        'wrong-magic.bsa': (replace_u32(good, 0, 0xDEADBEEF), True),
        'compressed-magic.bsa': (replace_u32(good, 0, 0x415342), True),
        'oversized-directory.bsa': (replace_u32(good, 4, len(good) * 2), True),
        'payload-outside.bsa': (replace_u32(good, 12, len(good) * 2), True),
        'name-outside.bsa': (replace_u32(good, 12 + 8 * count, names_size), True),
        'unterminated-name.bsa': (bytes(unterminated), True),
    }


def run_cases(reader, directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (data, reject) in cases().items():
        path = directory / name
        path.write_bytes(data)
        before = hashlib.sha256(data).hexdigest()
        command = [str(reader.resolve()), str(path.resolve()), 'reject' if reject else 'read']
        completed = subprocess.run(command, capture_output=True, text=True)
        print(name + ': ' + completed.stdout.strip(), flush=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise RuntimeError('Reader changed an input fixture: ' + name)
        if completed.returncode != 0:
            raise RuntimeError(f'Real reader fixture failed ({completed.returncode}): {name}\n{completed.stderr}')
        expected = 'REJECTED by OpenMW BSA reader' if reject else 'OpenMW BSA payload checks passed'
        if expected not in completed.stdout:
            raise RuntimeError('Missing reader completion evidence: ' + name)
    print('Eight synthetic BSA cases passed with unchanged input bytes.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True,
                        help='Owned build/test directory; known fixture filenames are overwritten here')
    args = parser.parse_args()
    run_cases(args.reader, args.directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
