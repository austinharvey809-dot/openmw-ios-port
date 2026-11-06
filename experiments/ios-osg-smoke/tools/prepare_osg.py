#!/usr/bin/env python3
"""Explicit opt-in pinned OSG checkout and bounded, hash-checked source overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "data/osg-lock.json").read_text(encoding="utf-8"))


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one overlay anchor: {old!r}")
    return text.replace(old, new, 1)


def overlay(name, text):
    if name == "CMakeLists.txt":
        text = replace_once(text,
            'SET (IPHONE_SDKROOT "${IPHONE_DEVROOT}/SDKs/iPhoneOS${IPHONE_SDKVER}.sdk")',
            'SET (IPHONE_SDKROOT "${CMAKE_OSX_SYSROOT}") # isolated ANGLE device build')
        text = replace_once(text,
            'SET(OPENGL_gl_LIBRARY "${IPHONE_SDKROOT}/System/Library/Frameworks/OpenGLES.framework")',
            'SET(OPENGL_gl_LIBRARY "${OSG_ANGLE_GLES_LIBRARY}") # validated ANGLE provider')
        text = replace_once(text,
            'SET(OSG_WINDOWING_SYSTEM "IOS" CACHE STRING "Windowing system type for graphics window creation, options only IOS." FORCE)',
            'SET(OSG_WINDOWING_SYSTEM "None" CACHE STRING "UIKit and ANGLE own the context" FORCE)')
    elif name == "src/osg/GLExtensions.cpp":
        text = '#include <EGL/egl.h> // isolated ANGLE provider\n' + text
        text = replace_once(text, '#if defined(__ANDROID__)',
            '#if defined(OSG_IOS_ANGLE)\n'
            '        return reinterpret_cast<void*>(eglGetProcAddress(funcName));\n'
            '    #elif defined(__ANDROID__)')
    else:
        raise ValueError("Unaudited overlay file")
    return text


def apply(source):
    output = {}
    # Validate every input before writing any file. No fuzzy patch or fallback.
    for name, expected in LOCK["source_sha256"].items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Pinned source checksum mismatch: {name}")
        output[name] = overlay(name, data.decode("utf-8"))
    for name, text in output.items():
        (source / name).write_bytes(text.encode("utf-8"))
    manifest = {"revision": LOCK["revision"], "overlay_version": LOCK["overlay_version"],
                "files": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in output.items()}}
    (source / "ios-osg-overlay.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="New/empty checkout directory")
    parser.add_argument("--allow-downloads", action="store_true")
    args = parser.parse_args()
    print(json.dumps(LOCK, indent=2), flush=True)
    if not args.allow_downloads:
        return 0
    if platform.system() != "Darwin":
        parser.error("OSG device checkout/build preparation is restricted to macOS; no Windows downloads")
    source = args.source.resolve()
    if source.exists() and any(source.iterdir()):
        parser.error("Refusing to modify a nonempty source directory")
    source.mkdir(parents=True, exist_ok=True)

    def run(args, capture=False):
        return subprocess.run(args, cwd=source, check=True, text=True,
                              stdout=subprocess.PIPE if capture else None).stdout

    run(["git", "init"])
    run(["git", "config", "core.autocrlf", "false"])
    run(["git", "remote", "add", "origin", LOCK["repository"]])
    run(["git", "fetch", "--depth=1", "origin", LOCK["revision"]])
    run(["git", "checkout", "--detach", "FETCH_HEAD"])
    if run(["git", "rev-parse", "HEAD"], True).strip() != LOCK["revision"]:
        raise ValueError("OSG revision mismatch")
    apply(source)
    print("Pinned OSG source prepared; no native compilation or runtime success claimed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
