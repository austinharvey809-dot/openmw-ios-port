"""Verify the unchanged OpenMW parser source closure and original G0 fixtures."""

import hashlib
import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE_MANIFEST = ROOT / "data/nif-source-sha256.json"
NIF_UNITS = tuple("base controller data effect extra niffile nifstream node particle physics property texture".split())
SOURCES = tuple("components/nif/" + name + ".cpp" for name in NIF_UNITS) + (
    "components/files/hash.cpp", "extern/smhasher/MurmurHash3.cpp")
INCLUDE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', re.M)


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def closure():
    pending, visited, external = list(SOURCES), set(), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        path = (REPO / name).resolve()
        if not path.is_relative_to(REPO) or not path.is_file():
            raise ValueError("Missing/unsafe parser source: " + name)
        visited.add(name)
        for delimiter, include in INCLUDE.findall(path.read_text(encoding="utf-8")):
            if include.startswith(("components/", "extern/")):
                target = REPO / include
            elif delimiter == '"':
                target = path.parent / include
                if not target.is_file() and include == "MurmurHash3.h":
                    target = REPO / "extern/smhasher/include/smhasher/MurmurHash3.h"
            else:
                external.add(include)
                continue
            target = target.resolve()
            if not target.is_relative_to(REPO) or not target.is_file():
                raise ValueError("Unresolved local parser include: " + include + " in " + name)
            pending.append(target.relative_to(REPO).as_posix())
    return sorted(visited), sorted(external)


def current_manifest():
    paths, external = closure()
    return {"schema_version": 1, "sources": list(SOURCES),
            "sha256_lf": {name: digest(REPO / name) for name in paths},
            "external_includes": external}


def load_fixture_generator():
    path = ROOT / "tools/generate_fixtures.py"
    spec = importlib.util.spec_from_file_location("g0_pinned_fixture_generator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify():
    expected = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    actual = current_manifest()
    if actual != expected:
        raise ValueError("OpenMW parser source/header inventory or hash changed")
    generator = load_fixture_generator()
    files = generator.fixture_bytes()
    manifest = json.loads((ROOT / "data/fixture-manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "candidate-unvalidated-by-openmw-parser" or set(files) != set(manifest["files"]):
        raise ValueError("G0 candidate fixture inventory/status changed")
    if {p.name for p in (ROOT / "data").iterdir()} != set(files) | {
            "fixture-manifest.json", "nif-source-sha256.json"}:
        raise ValueError("Unexpected G0 fixture data entry")
    for name, data in files.items():
        path = ROOT / "data" / name
        if path.is_symlink() or path.read_bytes() != data or manifest["files"][name] != {
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}:
            raise ValueError("G0 fixture differs from original generator: " + name)
    print(json.dumps({"parser_sources": len(SOURCES), "source_and_header_hashes": len(actual["sha256_lf"]),
                      "original_fixture_files": len(files), "status": "source/fixture audit only; parser not run"}))


if __name__ == "__main__":
    verify()
