#!/usr/bin/env python3
"""Validate the real Gate 0 framework closure, SDK stubs, symbols and provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess

from package_ios import MACHO_MAGIC, check_sdk, macho, require, system_dependency, version_tuple

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("OpenGLES.framework", "OpenGL.framework", "MoltenVK", "libvulkan", "GL4ES")


def frameworks(root):
    require((root / "angle-lock.json").read_bytes() == (ROOT / "data/angle-lock.json").read_bytes(), "Dependency lock mismatch")
    require((root / "args.gn").read_bytes() == (ROOT / "args.gn").read_bytes(), "Dependency GN configuration mismatch")
    build = json.loads((root / "angle-build.json").read_text(encoding="utf-8"))
    pin = json.loads((root / "angle-lock.json").read_text(encoding="utf-8"))
    require(build.get("angle_revision") == pin["angle_revision"] and build.get("target") == "arm64-apple-ios18.0"
            and build.get("metal_only") is True, "Wrong dependency provenance")
    require((root / "Licenses/LICENSE").is_file(), "Missing ANGLE license")
    result = {}
    for path in root.rglob("*"):
        require(not path.is_symlink(), f"Symlink in device package: {path}")
        require(path.name != "_CodeSignature" and path.suffix not in (".mobileprovision", ".p12", ".pem", ".key"), "Signing input forbidden")
    for framework in sorted((root / "Frameworks").glob("*.framework")):
        info = plistlib.loads((framework / "Info.plist").read_bytes())
        name = info.get("CFBundleExecutable")
        require(isinstance(name, str) and name == Path(name).name, "Invalid framework executable")
        binary = framework / name
        details = macho(binary.read_bytes())
        require(details["filetype"] == 6 and details["minimum_os"] <= version_tuple("18.0"), "Wrong device library deployment/type")
        expected = "@rpath/" + framework.name + "/" + name
        require(details["install_name"] == expected, f"Unexpected install name: {details['install_name']}; expected {expected}")
        require(info.get("CFBundlePackageType") == "FMWK", "Not a framework bundle")
        require(info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"], "Framework plist is not iPhoneOS")
        result[expected] = (binary, details)
    require(len(result) == 2, "Expected only EGL and GLES framework products")
    for binary, details in result.values():
        for dependency in details["dependencies"]:
            require(not any(name in dependency for name in FORBIDDEN), f"Alternate graphics provider: {dependency}")
            require(dependency in result or dependency.startswith(("/usr/lib/", "/System/Library/Frameworks/")), f"Unbundled dependency: {dependency}")
        require(all(path in ("@loader_path", "@loader_path/..", "@executable_path/Frameworks") for path in details["rpaths"]),
                f"Unexpected framework runtime search paths: {details['rpaths']}")
    known = {binary.resolve() for binary, _ in result.values()}
    for path in (root / "Frameworks").rglob("*"):
        if path.is_file() and path.read_bytes()[:4] == MACHO_MAGIC:
            require(path.resolve() in known, f"Unexpected native resource: {path}")
    return result


def validate(root, sdk):
    check_sdk(sdk)
    products = frameworks(root)
    reports, roles = {}, {}
    for install_name, (binary, details) in products.items():
        subprocess.run(["xcrun", "lipo", str(binary), "-verify_arch", "arm64"], check=True)
        tools = {}
        for tool, flags in (("otool", ["-L"]), ("vtool", ["-show-build"]), ("nm", ["-gU"])):
            tools[tool] = subprocess.run(["xcrun", tool, *flags, str(binary)], check=True, capture_output=True, text=True).stdout
        for dependency in details["dependencies"]:
            if dependency.startswith("/"):
                system_dependency(dependency, sdk, "18.0")
        symbols = {line.split()[-1] for line in tools["nm"].splitlines() if line.split()}
        for role, required in (("egl", {"_eglInitialize", "_eglCreateContext", "_eglGetPlatformDisplayEXT", "_eglSwapBuffers"}),
                               ("gles", {"_glCreateShader", "_glDrawArrays", "_glGenVertexArrays"})):
            if required <= symbols:
                require(role not in roles, f"Duplicate {role} provider")
                roles[role] = binary.relative_to(root).as_posix()
        reports[install_name] = dict(details, tools=tools)
    require(set(roles) == {"egl", "gles"}, "Missing required exported EGL/GLES3 entry points")
    require(roles["egl"] != roles["gles"], "Expected distinct upstream EGL/GLES frameworks")
    for header in ("EGL/egl.h", "EGL/eglext.h", "GLES3/gl3.h", "KHR/khrplatform.h"):
        require((root / "include" / header).is_file(), f"Missing header {header}")
    (root / "dependency-validation.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    build_path = root / "angle-build.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    build.update(validation="device-binary-and-sdk-passed", libraries=roles)
    build_path.write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(root.rglob("*")) if path.is_file() and path.name != "package-hashes.json"}
    (root / "package-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")


def resolve(root, destination):
    frameworks(root)
    hashes = json.loads((root / "package-hashes.json").read_text(encoding="utf-8"))
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != "package-hashes.json"}
    require(set(hashes) == actual, "Dependency package file inventory mismatch")
    for name, digest in hashes.items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, f"Dependency package digest mismatch: {name}")
    build = json.loads((root / "angle-build.json").read_text(encoding="utf-8"))
    require(build.get("validation") == "device-binary-and-sdk-passed", "Gate 0 did not pass")
    lines = []
    for role in ("egl", "gles"):
        library = (root / build["libraries"][role]).resolve()
        require(library.is_relative_to((root / "Frameworks").resolve()) and library.is_file(), "Invalid library path")
        lines.append(f'set(ANGLE_{role.upper()}_LIBRARY "{library.as_posix()}")')
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--sdk", type=Path)
    operation.add_argument("--resolve", type=Path)
    args = parser.parse_args()
    try:
        if args.sdk:
            validate(args.root.resolve(), args.sdk.resolve())
        else:
            resolve(args.root.resolve(), args.resolve)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ANGLE dependency validation failed: {error}\n")


if __name__ == "__main__":
    main()
