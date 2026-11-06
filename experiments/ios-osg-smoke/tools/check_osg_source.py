"""Read-only verification of the source pin and bounded overlay before CMake."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_osg import LOCK


def check(source):
    actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, check=True,
                            capture_output=True, text=True).stdout.strip()
    if actual != LOCK["revision"]:
        raise ValueError("OSG checkout revision mismatch")
    overlay = json.loads((source / "ios-osg-overlay.json").read_text(encoding="utf-8"))
    if overlay.get("revision") != actual or overlay.get("overlay_version") != LOCK["overlay_version"]:
        raise ValueError("OSG source overlay provenance mismatch")
    if set(overlay.get("files", {})) != set(LOCK["source_sha256"]):
        raise ValueError("OSG overlay inventory mismatch")
    # All tracked differences must be exactly the two audited overlay files.
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=source, check=True,
                             capture_output=True, text=True).stdout.splitlines()
    if set(changed) != set(LOCK["source_sha256"]):
        raise ValueError("Unexpected OSG tracked modifications")
    from prepare_osg import overlay as transform
    for name in LOCK["source_sha256"]:
        original = subprocess.run(["git", "show", "HEAD:" + name], cwd=source, check=True, capture_output=True).stdout
        expected = transform(name, original.decode("utf-8")).encode("utf-8")
        current = (source / name).read_bytes()
        if hashlib.sha256(original).hexdigest() != LOCK["source_sha256"][name] or current != expected:
            raise ValueError(f"OSG overlay differs from audited transformation: {name}")
        if hashlib.sha256(current).hexdigest() != overlay["files"][name]:
            raise ValueError(f"OSG overlay digest mismatch: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    check(parser.parse_args().source.resolve())
