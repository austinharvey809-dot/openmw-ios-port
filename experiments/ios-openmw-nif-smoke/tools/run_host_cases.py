"""Run the actual OpenMW reader against generated candidate fixtures.

No PASS is possible without an existing compiled C++ binary. The manifest and
input snapshot are checked independently with Python's SHA-256 implementation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    result = {}
    for path in DATA.iterdir():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Unsafe fixture entry: " + path.name)
        result[path.name] = sha(path)
    return result


def run(reader):
    if not reader.is_file():
        raise RuntimeError("Genuine C++ parser binary is unavailable")
    manifest = json.loads((DATA / "fixture-manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "candidate-unvalidated-by-openmw-parser":
        raise RuntimeError("Unexpected fixture status")
    before = snapshot()
    if set(before) != set(manifest["files"]) | {"fixture-manifest.json", "nif-source-sha256.json"}:
        raise RuntimeError("Fixture inventory mismatch")
    for name, entry in manifest["files"].items():
        if entry != {"size": (DATA / name).stat().st_size, "sha256": before[name]}:
            raise RuntimeError("Fixture SHA-256/size mismatch: " + name)
    cases = (
        ("positive", "triangle-candidate.bsa", "triangle-candidate.nif", "PASS genuine OpenMW NIF parse"),
        ("invalid", "invalid-header.bsa", "invalid-header.nif", "PASS genuine parser rejected invalid"),
        ("truncated", "truncated.bsa", "truncated.nif", "PASS genuine parser rejected truncated"),
        ("invalid-reference", "invalid-reference.bsa", "invalid-reference.nif",
         "PASS genuine parser rejected invalid-reference"),
        ("missing", "missing-resource.bsa", "triangle-candidate.nif", "PASS missing resource rejected"),
    )
    for mode, archive, nif, marker in cases:
        command = [str(reader.resolve()), mode, str(DATA / "valid.esm"), str(DATA / archive), str(DATA / nif)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        finally:
            if snapshot() != before:
                raise RuntimeError("G0A parser changed input files: " + mode)
        print(mode + ": " + result.stdout.strip(), flush=True)
        if result.stderr:
            print(result.stderr.strip(), flush=True)
        if result.returncode != 0 or marker not in result.stdout:
            raise RuntimeError("Genuine parser case failed: " + mode)
    # The positive archive paired with a different expected NIF must stop before
    # parsing. A successful VFS lookup is insufficient for PASS.
    mismatch = subprocess.run([str(reader.resolve()), "positive", str(DATA / "valid.esm"),
                               str(DATA / "triangle-candidate.bsa"), str(DATA / "invalid-header.nif")],
                              capture_output=True, text=True, timeout=60, check=False)
    if (mismatch.returncode == 0 or "VFS NIF bytes differ" not in mismatch.stderr
            or snapshot() != before):
        raise RuntimeError("Incorrect resource hash/bytes were not rejected")
    print("wrong-resource-bytes: PASS rejected before parser", flush=True)
    print("G0A genuine parser candidate cases passed; exact fixture SHA-256 values:")
    for name in sorted(manifest["files"]):
        print(before[name] + "  " + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", type=Path, required=True)
    args = parser.parse_args()
    run(args.reader)
