"""Original, deterministic 4.0.0.2 *candidate* NIF and ESM/BSA inputs.

Binary layout follows the current OpenMW Nif::Reader, NiNode, NiGeometry and
NiTriShapeData read methods. Only that genuine reader can establish validity.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ESM_VFS = ROOT.parent / "ios-openmw-esm-vfs" / "tools" / "fixtures.py"


def le(fmt, *values):
    return struct.pack("<" + fmt, *values)


def string(value):
    value = value.encode("ascii")
    return le("I", len(value)) + value


def mw_bool(value):
    # NIFStream::read<bool> uses int32_t before version 4.1.0.0.
    return le("i", int(value))


def object_net(name):
    # NiObjectNET::read: name, extra-data ref, controller ref (4.0.0.2).
    return string(name) + le("ii", -1, -1)


def av_object(name):
    # NiAVObject::read: flags, T, Matrix3 (contiguous mValues[3][3]), scale, velocity,
    # property list, has-bounds. Newer-version collision ref is absent.
    return (object_net(name) + le("H", 0) + le("3f", 0, 0, 0)
            + le("9f", 1, 0, 0, 0, 1, 0, 0, 0, 1) + le("f", 1)
            + le("3f", 0, 0, 0) + le("I", 0) + mw_bool(False))


def record(kind, body):
    return string(kind) + body


def triangle_candidate():
    node = av_object("G0Root") + le("IiI", 1, 1, 0)  # child=record 1; no effects
    shape = av_object("G0Triangle") + le("ii", 2, -1)  # data=record 2; no skin
    data = (le("H", 3) + mw_bool(True)
            + le("9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
            + mw_bool(False) + le("4f", 0, 0, 0, 1)
            + mw_bool(False) + le("H", 0) + mw_bool(False)
            # uint16 triangle count, uint32 index count, uint16 indices/match count.
            # 4.0.0.2 has no additional triangle-presence Boolean.
            + le("HI3HH", 1, 3, 0, 1, 2, 0))
    return (b"NetImmerse File Format, Version 4.0.0.2\n"
            + le("II", 0x04000002, 3)
            + record("NiNode", node)
            + record("NiTriShape", shape)
            + record("NiTriShapeData", data)
            + le("Ii", 1, 0))  # exactly one root, record 0


def load_existing_fixture_module():
    spec = importlib.util.spec_from_file_location("g0_existing_esm_vfs_fixtures", ESM_VFS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_bytes():
    existing = load_existing_fixture_module()
    candidate = triangle_candidate()
    invalid = b"X" + candidate[1:]  # deliberately invalid header, same size
    truncated = candidate[:-17]  # missing root-list tail and final record data
    shape = record("NiTriShape", av_object("G0Triangle") + le("ii", 2, -1))
    bad_shape = record("NiTriShape", av_object("G0Triangle") + le("ii", 99, -1))
    if candidate.count(shape) != 1:
        raise ValueError("Original triangle record layout changed")
    invalid_reference = candidate.replace(shape, bad_shape, 1)
    archive = existing.bsa.archive(((existing.RESOURCE, candidate),))
    invalid_archive = existing.bsa.archive(((existing.RESOURCE, invalid),))
    truncated_archive = existing.bsa.archive(((existing.RESOURCE, truncated),))
    reference_archive = existing.bsa.archive(((existing.RESOURCE, invalid_reference),))
    missing_archive = existing.bsa.archive(((b"Docs\\Only.txt", b"No mesh here"),))
    return {
        "triangle-candidate.nif": candidate,
        "invalid-header.nif": invalid,
        "truncated.nif": truncated,
        "invalid-reference.nif": invalid_reference,
        "valid.esm": existing.stat_file(),
        "triangle-candidate.bsa": archive,
        "invalid-header.bsa": invalid_archive,
        "truncated.bsa": truncated_archive,
        "invalid-reference.bsa": reference_archive,
        "missing-resource.bsa": missing_archive,
    }


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generate():
    files = fixture_bytes()
    manifest = {
        "schema_version": 1,
        "status": "candidate-unvalidated-by-openmw-parser",
        "origin": "self-authored from OpenMW 4.0.0.2 reader contracts; no game assets",
        "nif_version": "4.0.0.2",
        "resource_path": "meshes/test.nif",
        "files": {name: {"size": len(data), "sha256": sha(data)} for name, data in sorted(files.items())},
    }
    files["fixture-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    DATA.mkdir(exist_ok=True)
    present = {p.name for p in DATA.iterdir()}
    if present - files.keys() - {"nif-source-sha256.json"}:
        raise ValueError("Unexpected file in G0 data directory")
    for name, data in files.items():
        path = DATA / name
        if path.is_symlink():
            raise ValueError("Refusing linked fixture: " + name)
        if path.exists() and path.read_bytes() != data:
            if name != "fixture-manifest.json":
                raise ValueError("Refusing to replace changed fixture: " + name)
            old = json.loads(path.read_text(encoding="utf-8"))
            if (old.get("schema_version") != 1 or old.get("status") != manifest["status"]
                    or not set(old.get("files", {})).issubset(manifest["files"])):
                raise ValueError("Refusing unexpected manifest change")
            for old_name, entry in old["files"].items():
                if entry != manifest["files"][old_name]:
                    raise ValueError("Refusing changed existing fixture metadata")
            path.write_bytes(data)
        elif not path.exists():
            path.write_bytes(data)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    generate()
