"""Read-only metadata inventory of a private Morrowind installation.

This is a bounded TES3/BSA directory inspector, not a NIF parser. It never
extracts or writes game bytes. Only paths, IDs, sizes and SHA-256 are reported.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def normalize_model(data):
    name = data.split(b"\0", 1)[0].decode("cp1252", errors="replace")
    name = name.replace("\\", "/").strip("/").lower()
    return name if name.startswith("meshes/") else "meshes/" + name


def stat_models(esm):
    models = {}
    with esm.open("rb") as source:
        size = esm.stat().st_size
        while source.tell() < size:
            head = source.read(16)
            if len(head) != 16:
                raise ValueError("Short ESM record header")
            tag, length, _, _ = struct.unpack("<4sIII", head)
            end = source.tell() + length
            if end > size:
                raise ValueError("ESM record exceeds file")
            if tag != b"STAT":
                source.seek(end)
                continue
            record_id = model = None
            while source.tell() < end:
                sub = source.read(8)
                if len(sub) != 8:
                    raise ValueError("Short STAT subrecord")
                kind, count = struct.unpack("<4sI", sub)
                if source.tell() + count > end:
                    raise ValueError("STAT subrecord exceeds record")
                if kind == b"NAME":
                    record_id = source.read(count).split(b"\0", 1)[0].decode("cp1252", errors="replace")
                elif kind == b"MODL":
                    model = normalize_model(source.read(count))
                else:
                    source.seek(count, 1)
            if record_id and model:
                models.setdefault(model, []).append(record_id)
    return models


def bsa_entries(archive):
    with archive.open("rb") as source:
        archive_size = archive.stat().st_size
        header = source.read(12)
        if len(header) != 12:
            raise ValueError("Short BSA header")
        magic, directory_size, count = struct.unpack("<III", header)
        if magic != 0x100 or directory_size + 8 * count + 12 > archive_size:
            raise ValueError("Unsupported or malformed Morrowind BSA")
        if count > 1_000_000 or directory_size < 12 * count:
            raise ValueError("Unsafe BSA directory count")
        directory = source.read(directory_size)
        if len(directory) != directory_size:
            raise ValueError("Short BSA directory")
        name_buffer = directory[12 * count:]
        data_start = 12 + directory_size + 8 * count
        for index in range(count):
            length, relative = struct.unpack_from("<II", directory, index * 8)
            name_offset = struct.unpack_from("<I", directory, 8 * count + index * 4)[0]
            if name_offset >= len(name_buffer):
                raise ValueError("BSA name offset out of bounds")
            end = name_buffer.find(b"\0", name_offset)
            if end < 0 or data_start + relative + length > archive_size:
                raise ValueError("BSA entry out of bounds")
            name = normalize_model(name_buffer[name_offset:end])
            yield name, data_start + relative, length


def digest_range(path, offset, length):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        source.seek(offset)
        remaining = length
        while remaining:
            chunk = source.read(min(1 << 20, remaining))
            if not chunk:
                raise ValueError("Short asset read")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def inspect(root):
    data = root / "Data Files"
    if not root.is_dir() or not data.is_dir():
        raise ValueError("Morrowind/Data Files directory missing")
    names = ("Morrowind.esm", "Morrowind.bsa", "Tribunal.esm", "Tribunal.bsa",
             "Bloodmoon.esm", "Bloodmoon.bsa")
    inventory = {}
    for name in names:
        path = data / name
        inventory[name] = {"present": path.is_file()}
        if path.is_file():
            stat = path.stat()
            inventory[name].update(size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    model_refs = stat_models(data / "Morrowind.esm")
    candidates = []
    archives = []
    for name in ("Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa"):
        path = data / name
        if not path.is_file():
            continue
        entries = list(bsa_entries(path))
        archives.append({"name": name, "entries": len(entries),
                         "nif_entries": sum(key.endswith(".nif") for key, _, _ in entries)})
        for key, offset, length in entries:
            if key.endswith(".nif") and key in model_refs and 0 < length <= 200_000:
                candidates.append((length, key, name, offset, model_refs[key][:3]))
    selected = []
    for length, key, archive_name, offset, ids in sorted(candidates)[:8]:
        selected.append({"origin": archive_name, "resource_path": key, "stat_ids": ids,
                         "size": length, "sha256": digest_range(data / archive_name, offset, length),
                         "external_textures": "unverified without genuine NIF parser"})
    mesh_root = data / "Meshes"
    loose_dirs = sorted(p.name for p in mesh_root.iterdir() if p.is_dir()) if mesh_root.is_dir() else []
    return {"scope": "private read-only metadata inventory; no NIF parse or extraction",
            "inventory": inventory, "loose_meshes_present": mesh_root.is_dir(),
            "loose_meshes_subdirectory_count": len(loose_dirs),
            "archives": archives, "morrowind_stat_model_paths": len(model_refs),
            "candidates": selected}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.installation), indent=2))
