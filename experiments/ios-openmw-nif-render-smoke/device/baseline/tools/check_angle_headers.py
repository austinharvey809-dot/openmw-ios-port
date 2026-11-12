#!/usr/bin/env python3
"""Read-only OSG GLES3 header preflight against an already verified ANGLE artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import re

SELECTED = ("GLES3/gl3.h", "GLES2/gl2ext.h")
# Dependencies of the selected GL core header and the app/OSG EGL entry points.
# gl2ext.h consumes the types/macros from the preceding gl3.h; it is not gl2.h.
DEPENDENCIES = ("GLES3/gl3platform.h", "KHR/khrplatform.h", "EGL/egl.h", "EGL/eglext.h", "EGL/eglplatform.h")
LABEL_IDENTIFIERS = {"GL_SHADER_KHR": 0x82E1, "GL_PROGRAM_KHR": 0x82E2, "GL_BUFFER_KHR": 0x82E0}


def check(root, profile, headers):
    if profile != "GLES3":
        raise ValueError(f"Expected GLES3 profile, got {profile!r}")
    selected = []
    for declaration in headers:
        match = re.fullmatch(r"#include\s+<([^>]+)>", declaration)
        if not match:
            raise ValueError(f"Invalid GL include selection: {declaration!r}")
        selected.append(match.group(1))
    if tuple(selected) != SELECTED:
        raise ValueError(f"Invalid ANGLE GLES3 include selection/order: {selected!r}; expected {SELECTED!r}")
    include = (root / "include").resolve()
    if not include.is_dir():
        raise ValueError(f"Missing ANGLE artifact include directory: {include}")
    hashes = {}
    for name in (*SELECTED, *DEPENDENCIES):
        path = (include / name).resolve()
        if not path.is_relative_to(include) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing, empty or non-artifact ANGLE header: {name} (under {include})")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Inspect the actual artifact, not a standard header or synthetic replacement.
    # Fail closed on missing/ambiguous/nonliteral definitions; the subsequent
    # C++11 probe also verifies these values after real preprocessing.
    extensions = (include / "GLES2/gl2ext.h").read_text(encoding="utf-8")
    for token, expected in LABEL_IDENTIFIERS.items():
        values = re.findall(r"^[ \t]*#[ \t]*define[ \t]+" + token
                            + r"[ \t]+(0[xX][0-9a-fA-F]+|[0-9]+)[ \t]*\r?$", extensions, re.MULTILINE)
        if len(values) != 1 or int(values[0], 16 if values[0].lower().startswith("0x") else 10) != expected:
            raise ValueError(f"ANGLE artifact GLES2/gl2ext.h must define {token} as {expected:#x} exactly once")
    return {"profile": profile, "selected_headers": selected, "header_sha256": hashes,
            "label_identifiers": LABEL_IDENTIFIERS.copy()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--header", required=True, action="append")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(args.root, args.profile, args.header), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"ANGLE GL header preflight failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
