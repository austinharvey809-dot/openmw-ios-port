#!/usr/bin/env python3
"""Validate this device app and produce an unsigned IPA. Python stdlib only.

Packaging requires macOS for otool; --validate-only also works on Windows.
No signing, provisioning, network access or dependency modification occurs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import struct
import subprocess
import tempfile
import zipfile

from generate_checkerboard import HEIGHT, WIDTH, checkerboard_rgba


APP_NAME = "IOSRenderSmoke.app"
PREFIX = f"Payload/{APP_NAME}/"
MACHO_MAGIC = b"\xcf\xfa\xed\xfe"
FORBIDDEN_SUFFIXES = {".p12", ".pfx", ".pem", ".key", ".cer", ".crt", ".mobileprovision", ".provisionprofile"}
LOAD_DYLIB = {0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023}


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    data: bytes
    mode: int


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def safe_name(name: str):
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and "\\" not in name
            and all(part not in ("", ".", "..") for part in name.split("/"))
            and ":" not in name and "\x00" not in name, f"Unsafe bundle/archive path: {name!r}")


def version_tuple(value: str):
    require(isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+){0,2}", value), f"Invalid OS version: {value!r}")
    parts = tuple(map(int, value.split(".")))
    return parts + (0,) * (3 - len(parts))


def macho(data: bytes):
    """Read only the ARM64 Mach-O header and load commands needed for packaging."""
    require(len(data) >= 32 and data[:4] == MACHO_MAGIC, "Expected a thin, little-endian ARM64 Mach-O")
    _, cpu, _, filetype, count, size, _, _ = struct.unpack_from("<IiiIIIII", data)
    require(cpu == 0x0100000C, "Mach-O architecture is not ARM64")
    require(filetype in (2, 6), "Expected an executable or dynamic library, not a static archive/plugin")
    require(32 + size <= len(data), "Truncated Mach-O load commands")
    result = {"filetype": filetype, "dependencies": [], "rpaths": [], "platform": None,
              "minimum_os": None, "install_name": None}
    offset = 32
    for _ in range(count):
        require(offset + 8 <= 32 + size, "Truncated Mach-O command header")
        command, length = struct.unpack_from("<II", data, offset)
        require(length >= 8 and offset + length <= 32 + size, "Invalid Mach-O command length")
        payload = data[offset:offset + length]
        if command in LOAD_DYLIB | {0xD, 0x8000001C}:
            minimum = 12 if command == 0x8000001C else 24
            require(length >= minimum, "Truncated Mach-O path command")
            start = struct.unpack_from("<I", payload, 8)[0]
            require(minimum <= start < length, "Invalid Mach-O path offset")
            end = payload.find(b"\x00", start)
            require(end >= start, "Unterminated Mach-O path")
            try:
                value = payload[start:end].decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValidationError("Invalid Mach-O path encoding") from error
            require(bool(value), "Empty Mach-O path")
            if command in LOAD_DYLIB:
                result["dependencies"].append(value)
            elif command == 0xD:
                result["install_name"] = value
            else:
                result["rpaths"].append(value)
        elif command == 0x32:  # LC_BUILD_VERSION
            require(length >= 24 and result["platform"] is None, "Invalid/duplicate LC_BUILD_VERSION")
            platform, minimum = struct.unpack_from("<II", payload, 8)
            require(platform == 2, "Mach-O platform is not iOS device (simulator/macOS rejected)")
            result["platform"] = "IOS"
            result["minimum_os"] = (minimum >> 16, (minimum >> 8) & 255, minimum & 255)
        elif command == 0x1D:  # LC_CODE_SIGNATURE
            raise ValidationError("Unsigned IPA input contains a Mach-O code signature; no signatures are stripped")
        elif command == 0x2C:  # LC_ENCRYPTION_INFO_64
            require(length >= 24 and struct.unpack_from("<I", payload, 16)[0] == 0, "Encrypted Mach-O is not supported")
        offset += length
    require(offset == 32 + size and result["platform"] == "IOS", "Missing/invalid iOS load-command metadata")
    return result


def check_sdk(sdk: Path):
    try:
        settings = plistlib.loads((sdk / "SDKSettings.plist").read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        raise ValidationError(f"Cannot inspect iphoneos SDK settings: {sdk}") from error
    require(str(settings.get("CanonicalName", "")).startswith("iphoneos"), "Dependency SDK is not iphoneos")


def _yaml_scalar(value: str):
    value = value.strip()
    require(bool(value), "Empty TAPI YAML metadata value")
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except ValueError as error:
            raise ValidationError("Unsupported quoted TAPI YAML metadata") from error
        require(isinstance(decoded, str), "Expected TAPI YAML string")
        return decoded
    if value.startswith("'"):
        require(value.endswith("'") and re.fullmatch(r"'(?:[^']|'')*'", value), "Invalid TAPI YAML quoted string")
        return value[1:-1].replace("''", "'")
    require(re.fullmatch(r"[A-Za-z0-9_./@+:-]+", value), "Unsupported TAPI YAML metadata scalar")
    return value


def _yaml_metadata_fields(text: str):
    """Read first-document root metadata, not nested exports/inlined libraries.

    This deliberately handles SDK metadata scalars and string sequences only;
    it is not a general YAML parser and rejects unsupported metadata syntax.
    """
    lines = []
    tag = None
    for line in text.splitlines():
        # Preserve '#' inside quoted scalars; ignore actual YAML comments.
        clean, quote, index = [], None, 0
        while index < len(line):
            char = line[index]
            if quote == '"' and char == "\\" and index + 1 < len(line):
                clean.extend(line[index:index + 2])
                index += 2
                continue
            if char in ("'", '"'):
                if quote is None:
                    quote = char
                elif quote == char:
                    if char == "'" and index + 1 < len(line) and line[index + 1] == "'":
                        clean.extend("''")
                        index += 2
                        continue
                    quote = None
            if char == "#" and quote is None:
                break
            clean.append(char)
            index += 1
        line = "".join(clean).rstrip()
        if not line.strip():
            continue
        if line.startswith("---"):
            if tag is not None:
                break
            tag = line[3:].strip()
            continue
        if line.strip() == "...":
            break
        lines.append(line)
    require(tag in ("!tapi-tbd", "!tapi-tbd-v3"), "Unsupported TAPI YAML document tag")
    mappings = [(index, match) for index, line in enumerate(lines)
                if (match := re.match(r"^( *)([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", line))]
    require(bool(mappings), "Missing TAPI YAML root metadata")
    root_indent = min(len(match[1]) for _, match in mappings)
    roots = [(index, match) for index, match in mappings if len(match[1]) == root_indent]
    fields = {}
    selected = {"tbd-version", "targets", "install-name", "archs", "platform"}
    for position, (index, match) in enumerate(roots):
        key = match[2]
        if key not in selected:
            continue
        require(key not in fields, f"Duplicate TAPI YAML metadata key: {key}")
        end = roots[position + 1][0] if position + 1 < len(roots) else len(lines)
        tail = lines[index + 1:end]
        value = match[3].strip()
        if key in ("targets", "archs"):
            if value.startswith("["):
                sequence = " ".join([value] + [line.strip() for line in tail])
                require(sequence.endswith("]"), f"Unterminated TAPI YAML {key}")
                values = sequence[1:-1].strip().split(",")
                if values and not values[-1].strip():
                    values.pop()
                fields[key] = [_yaml_scalar(item) for item in values]
            else:
                require(not value and bool(tail), f"Invalid TAPI YAML {key} sequence")
                values = []
                for line in tail:
                    item = re.fullmatch(r" +-\s+(.+)", line)
                    require(item is not None, f"Unsupported TAPI YAML {key} sequence")
                    values.append(_yaml_scalar(item[1]))
                fields[key] = values
        else:
            require(not tail, f"Unsupported multiline TAPI YAML {key}")
            fields[key] = _yaml_scalar(value)
    return tag, fields


def _string_targets(value, label):
    require(isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value),
            f"Invalid TAPI {label} targets")
    return set(value)


def read_tbd_metadata(text: str):
    """Return supported targets and install names from the *main* stub library."""
    text = text.lstrip("\ufeff \t\r\n")
    if text.startswith("{"):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, f"Duplicate TAPI JSON key: {key}")
                result[key] = value
            return result
        try:
            document = json.loads(text, object_pairs_hook=unique_object)
        except ValueError as error:
            raise ValidationError(f"Invalid TAPI JSON: {error}") from error
        require(document.get("tapi_tbd_version") == 5, "Unsupported TAPI JSON version (expected v5)")
        library = document.get("main_library")
        require(isinstance(library, dict), "Missing TAPI v5 main_library")
        target_info = library.get("target_info")
        require(isinstance(target_info, list) and all(isinstance(item, dict) for item in target_info), "Invalid TAPI v5 target_info")
        targets = _string_targets([item.get("target") for item in target_info], "v5 main_library")
        entries = library.get("install_names")
        require(isinstance(entries, list) and bool(entries), "Missing TAPI v5 install_names")
        names = {}
        for entry in entries:
            require(isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"], "Invalid TAPI v5 install name")
            scope = _string_targets(entry["targets"], "v5 install-name") if "targets" in entry else targets
            require(scope <= targets, "TAPI v5 install-name targets are outside main_library")
            names.setdefault(entry["name"], set()).update(scope)
        return {"format": "TAPI v5 JSON", "targets": targets, "install_names": names}
    tag, fields = _yaml_metadata_fields(text)
    name = fields.get("install-name")
    require(isinstance(name, str) and name, "Missing TAPI YAML install-name")
    if tag == "!tapi-tbd" and fields.get("tbd-version") == "4":
        targets = _string_targets(fields.get("targets"), "v4 main-library")
        format_name = "TAPI v4 YAML"
    elif tag == "!tapi-tbd-v3":
        arches = _string_targets(fields.get("archs"), "v3 architecture")
        platform = fields.get("platform")
        require(isinstance(platform, str) and platform, "Missing TAPI v3 platform")
        targets = {arch + "-" + platform for arch in arches}
        format_name = "TAPI v3 YAML"
    else:
        raise ValidationError("Unsupported TAPI YAML version")
    return {"format": format_name, "targets": targets, "install_names": {name: targets}}


def probe_arm64_system_stub(stub: Path, sdk: Path, name: str, minimum_os: str):
    """Require Apple's selected linker to confirm ARM64e system-stub compatibility.

    This is confined to public SDK stubs with exact iOS device targets. It does
    not relax architecture/platform checks for the app or any bundled binary.
    """
    version_tuple(minimum_os)
    with tempfile.TemporaryDirectory(prefix="ios-sdk-abi-") as directory:
        output = Path(directory) / "probe.dylib"
        command = ["xcrun", "--sdk", "iphoneos", "clang", "-target", f"arm64-apple-ios{minimum_os}",
                   "-isysroot", str(sdk), "-dynamiclib", "-x", "c", "-", "-Xlinker", "-needed_library",
                   "-Xlinker", str(stub), "-Wl,-fatal_warnings", "-Wl,-no_adhoc_codesign", "-o", str(output)]
        try:
            result = subprocess.run(command, input="void ios_sdk_abi_probe(void) {}\n", capture_output=True, text=True)
        except OSError as error:
            raise ValidationError(f"Cannot check ARM64 compatibility of {stub} with Apple's linker: {error}") from error
        require(result.returncode == 0, f"Apple linker rejected ARM64 iOS use of {stub}: {result.stderr.strip()}")
        try:
            details = macho(output.read_bytes())
        except OSError as error:
            raise ValidationError(f"Apple linker did not produce an ARM64 iOS probe for {stub}") from error
        require(name in details["dependencies"], f"ARM64 linker probe did not load the required SDK dependency: {name}")


def system_dependency(name: str, sdk: Path, minimum_os="18.0"):
    require(name.startswith(("/usr/lib/", "/System/Library/Frameworks/")), f"Non-public/non-iOS absolute dependency: {name}")
    relative = name.removeprefix("/")
    safe_name(relative)
    binary = sdk / relative
    stub = binary.with_suffix(".tbd") if binary.suffix == ".dylib" else Path(str(binary) + ".tbd")
    # Device libraries often exist only in the dyld cache. Inspect SDK text stubs,
    # never the build Mac's /usr/lib or /System/Library copies.
    require(stub.is_file(), f"No matching public iphoneos SDK stub for {name}: {stub}")
    text = stub.read_text(encoding="utf-8")
    metadata = read_tbd_metadata(text)
    # Explicit CPU_TYPE_ARM64 system-stub candidates, never arbitrary arm64* or
    # platform prefixes. Exact arm64 needs no ABI fallback; ARM64e needs proof.
    supported = metadata["targets"] & {"arm64-ios", "arm64e-ios", "arm64e.x1-ios"}
    require(supported, f"SDK stub does not advertise ARM64 iOS device support: {stub}; "
            f"{metadata['format']} declared targets={sorted(metadata['targets'])}")
    supported &= metadata["install_names"].get(name, set())
    require(supported, f"SDK stub install name does not match dependency for a supported iOS target: {name}")
    if "arm64-ios" not in supported:
        probe_arm64_system_stub(stub, sdk, name, minimum_os)
    return {"kind": "iphoneos-sdk", "stub": str(stub)}


def normalize_bundle_path(value: str, allow_root=False):
    require(not value.startswith("/") and "\\" not in value, f"Dependency escapes application: {value}")
    parts = []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            require(bool(parts), f"Dependency escapes application: {value}")
            parts.pop()
        else:
            parts.append(part)
    result = "/".join(parts)
    if not result and allow_root:
        return "."
    safe_name(result)
    return result


def expand_path(value: str, loader: str, allow_root=False):
    for token, base in (("@loader_path", str(PurePosixPath(loader).parent)), ("@executable_path", ".")):
        if value == token or value.startswith(token + "/"):
            return normalize_bundle_path(base + value[len(token):], allow_root)
    raise ValidationError(f"Unsupported/non-bundled runpath: {value}")


def spirv_metadata(data: bytes, stage: int, name: str):
    """Check resource identity/structure, not full SPIR-V semantic validity."""
    require(20 <= len(data) <= 1024 * 1024 and len(data) % 4 == 0,
            f"Invalid SPIR-V size/alignment: {name}")
    words = struct.unpack(f"<{len(data) // 4}I", data)
    require(words[0] == 0x07230203 and words[1] == 0x00010000 and words[3] > 0 and words[4] == 0,
            f"Expected little-endian SPIR-V 1.0 header: {name}")
    entries, shader, memory_model = [], False, False
    index = 5
    while index < len(words):
        count, opcode = words[index] >> 16, words[index] & 0xFFFF
        require(count > 0 and index + count <= len(words), f"Malformed SPIR-V instruction: {name}")
        instruction = words[index:index + count]
        if opcode == 17:  # OpCapability Shader
            require(count == 2, f"Malformed SPIR-V capability: {name}")
            shader |= instruction[1] == 1
        elif opcode == 14:  # OpMemoryModel Logical GLSL450
            require(count == 3, f"Malformed SPIR-V memory model: {name}")
            memory_model |= instruction[1:] == (0, 1)
        elif opcode == 15:  # OpEntryPoint execution model, id, null-terminated name
            require(count >= 4, f"Malformed SPIR-V entry point: {name}")
            encoded = struct.pack(f"<{count - 3}I", *instruction[3:])
            require(b"\0" in encoded, f"Unterminated SPIR-V entry point: {name}")
            entries.append((instruction[1], encoded.split(b"\0", 1)[0]))
        index += count
    require(shader and memory_model and entries == [(stage, b"main")],
            f"Expected Shader capability, Logical GLSL450 and stage {stage} main entry point: {name}")
    return {"stage": "vertex" if stage == 0 else "fragment", "entry_point": "main",
            "spirv_version": "1.0", "sha256": hashlib.sha256(data).hexdigest()}


def validate_bundle(files: dict[str, Entry], sdk: Path | None = None):
    require("Info.plist" in files, "Missing application Info.plist")
    for name, entry in files.items():
        safe_name(name)
        require(not stat.S_ISLNK(entry.mode), f"Symlinks are not supported in this iOS application: {name}")
        require("_CodeSignature" not in PurePosixPath(name).parts and PurePosixPath(name).suffix.lower() not in FORBIDDEN_SUFFIXES,
                f"Signing/provisioning/credential file is forbidden in unsigned input: {name}")
        require(PurePosixPath(name).suffix.lower() != ".a", f"Static library must be linked, not bundled: {name}")
    try:
        info = plistlib.loads(files["Info.plist"].data)
    except (ValueError, plistlib.InvalidFileException) as error:
        raise ValidationError("Invalid Info.plist") from error
    require(isinstance(info, dict), "Info.plist must be a dictionary")
    executable = info.get("CFBundleExecutable")
    require(isinstance(executable, str) and executable == "IOSRenderSmoke" and executable in files,
            "Missing/mismatched CFBundleExecutable (expected IOSRenderSmoke)")
    require(files[executable].mode & 0o111, "Application executable lacks Unix executable permissions")
    require(info.get("CFBundlePackageType") == "APPL", "CFBundlePackageType must be APPL")
    require(isinstance(info.get("CFBundleIdentifier"), str) and re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", info["CFBundleIdentifier"]),
            "Missing/invalid bundle identifier")
    family = info.get("UIDeviceFamily")
    require(info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"] and isinstance(family, list) and 1 in family,
            "Bundle is not an iPhoneOS/iPhone application")
    minimum_os = version_tuple(info.get("MinimumOSVersion"))
    require(isinstance(info.get("UILaunchScreen"), dict), "Missing inline launch-screen resource configuration")
    require(not any(key in info for key in ("UIMainStoryboardFile", "UILaunchStoryboardName")), "External storyboard resources are not part of this experiment")
    mode = info.get("IOSRenderSmokeMode")
    require(mode in ("cube", "triangle", "clear"), "Missing/invalid IOSRenderSmokeMode (expected cube, triangle or clear)")
    cube_available = info.get("IOSRenderSmokeCubeAvailable", False)
    require(type(cube_available) is bool, "IOSRenderSmokeCubeAvailable must be a boolean")
    require(mode != "cube" or cube_available, "Cube start mode requires IOSRenderSmokeCubeAvailable=true")
    require(not cube_available or mode in ("cube", "triangle"), "Clear-only build cannot advertise cube resources")
    required_resources, shaders, textures = ["Info.plist", executable], {}, {}
    if mode != "clear":
        for name, stage in (("triangle.vert.spv", 0), ("triangle.frag.spv", 4)):
            require(name in files, f"Missing required triangle shader resource: {name}")
            shaders[name] = spirv_metadata(files[name].data, stage, name)
            required_resources.append(name)
    if cube_available:
        for name, stage in (("cube.vert.spv", 0), ("cube.frag.spv", 4)):
            require(name in files, f"Missing required cube shader resource: {name}")
            shaders[name] = spirv_metadata(files[name].data, stage, name)
            required_resources.append(name)
        name = "checkerboard.rgba"
        require(name in files, "Missing required original checkerboard texture: checkerboard.rgba")
        require(files[name].data == checkerboard_rgba(), "Checkerboard texture does not match original 32x32 RGBA8 asset")
        required_resources.append(name)
        textures[name] = {"width": WIDTH, "height": HEIGHT, "format": "RGBA8_UNORM",
                          "sha256": hashlib.sha256(files[name].data).hexdigest(), "original_generated_asset": True}
    manifest = info.get("UIApplicationSceneManifest", {})
    require(isinstance(manifest, dict), "Invalid scene manifest")
    configurations = manifest.get("UISceneConfigurations", {})
    require(isinstance(configurations, dict), "Invalid scene configurations")
    scenes = configurations.get("UIWindowSceneSessionRoleApplication", [])
    require(isinstance(scenes, list) and all(isinstance(scene, dict) for scene in scenes)
            and any(scene.get("UISceneDelegateClassName") == "SmokeSceneDelegate" for scene in scenes),
            "Missing inline SmokeSceneDelegate configuration")
    binaries = {name: macho(entry.data) for name, entry in files.items() if entry.data.startswith(MACHO_MAGIC)}
    require(executable in binaries and binaries[executable]["filetype"] == 2, "Application executable is not an ARM64 iOS Mach-O executable")
    require(binaries[executable]["minimum_os"] == minimum_os, "Info.plist and Mach-O deployment versions differ")
    for name, details in binaries.items():
        require(files[name].mode & 0o111, f"Native binary lacks executable permissions: {name}")
        require(details["minimum_os"] <= minimum_os, f"Bundled binary requires newer iOS than application: {name}")
        require(name == executable or (name.startswith("Frameworks/") and details["filetype"] == 6), f"Unexpected native binary outside Frameworks: {name}")
    for name in files:
        require(not name.endswith(".dylib") or name in binaries, f"Bundled dylib is not an ARM64 iOS Mach-O: {name}")
    if sdk is not None:
        check_sdk(sdk)
    resolved, visited = [], set()

    def walk(loader, inherited=()):
        details = binaries[loader]
        rpaths = tuple(expand_path(value, loader, allow_root=True) for value in details["rpaths"]) + inherited
        key = (loader, rpaths)
        if key in visited:
            return
        visited.add(key)
        for dependency in details["dependencies"]:
            record = {"loader": loader, "dependency": dependency}
            if dependency.startswith("/"):
                # Without an SDK, validate only the dependency's namespace and
                # make the unverified system availability explicit in the report.
                require(dependency.startswith(("/usr/lib/", "/System/Library/Frameworks/")), f"Unexpected host dependency: {dependency}")
                record.update(system_dependency(dependency, sdk, info["MinimumOSVersion"]) if sdk else {"kind": "system-availability-not-checked"})
            else:
                if dependency.startswith("@rpath/"):
                    candidates = [normalize_bundle_path(path + "/" + dependency[len("@rpath/"):]) for path in rpaths]
                else:
                    candidates = [expand_path(dependency, loader)]
                target = next((name for name in candidates if name in binaries), None)
                require(target is not None, f"Unresolved bundled dependency {dependency} loaded by {loader}")
                record.update(kind="bundled", target=target)
                # A dependency graph may contain cycles; do not recursively grow
                # inherited runpaths after a loader has already been visited.
                if not any(item[0] == target for item in visited):
                    walk(target, rpaths)
            resolved.append(record)

    walk(executable)
    reachable = {item[0] for item in visited}
    require(reachable == set(binaries), "Unreferenced native libraries in bundle are not permitted")
    return {"bundle_identifier": info["CFBundleIdentifier"], "executable": executable,
            "minimum_os": info["MinimumOSVersion"], "architecture": "arm64", "platform": "IOS",
            "render_mode": mode, "cube_available": cube_available, "required_resources": required_resources,
            "shaders": shaders, "textures": textures,
            "resource_note": "Inline launch/scene configuration; geometry modes require their declared shader/texture resources. Structural checks do not replace SPIR-V semantic validation or a device draw.",
            "binaries": binaries, "dependencies": resolved, "sdk_availability_checked": sdk is not None}


def collect_bundle(app: Path):
    require(app.is_dir() and not app.is_symlink() and app.name == APP_NAME, f"Expected {APP_NAME} directory")
    files = {}
    for path in sorted(app.rglob("*")):
        require(not path.is_symlink(), f"Symlink in application: {path}")
        if path.is_file():
            files[path.relative_to(app).as_posix()] = Entry(path.read_bytes(), path.stat().st_mode)
    return files


def inspect_dependencies(app: Path, report: dict):
    """Keep actual otool output for the executable and all bundled libraries."""
    outputs = {}
    for name, details in report["binaries"].items():
        result = subprocess.run(["xcrun", "otool", "-L", str(app / name)], check=True, capture_output=True, text=True)
        listed = []
        for line in result.stdout.splitlines()[1:]:
            if " (compatibility version " in line:
                listed.append(line.strip().split(" (compatibility version ", 1)[0])
        expected = set(details["dependencies"])
        if details["install_name"]:
            expected.add(details["install_name"])
        require(set(listed) == expected, f"otool -L and Mach-O dependency metadata disagree: {name}")
        outputs[name] = result.stdout
    return outputs


def write_ipa(files: dict[str, Entry], destination: Path):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ("Payload/", PREFIX):
            entry = zipfile.ZipInfo(directory)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(entry, b"")
        for name, source in sorted(files.items()):
            safe_name(name)
            entry = zipfile.ZipInfo(PREFIX + name)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | stat.S_IMODE(source.mode)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, source.data)


def validate_ipa(path: Path, sdk: Path | None = None, expected: dict[str, Entry] | None = None):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len({entry.filename for entry in entries}) == len(entries), "Duplicate IPA archive entries")
        require(archive.testzip() is None, "IPA CRC check failed")
        files = {}
        for entry in entries:
            name = entry.filename.rstrip("/")
            safe_name(name)
            require(name == "Payload" or name == PREFIX.rstrip("/") or name.startswith(PREFIX), f"Unexpected IPA archive root/application: {name}")
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not entry.flag_bits & 1, f"Symlink/encrypted IPA entry: {name}")
            if not entry.is_dir():
                require(entry.filename.startswith(PREFIX), f"File outside IPA application: {name}")
                files[name[len(PREFIX):]] = Entry(archive.read(entry), mode)
        report = validate_bundle(files, sdk)
        if expected is not None:
            require(files == expected, "IPA contents or permissions differ from validated application bundle")
        report.update(archive_root=PREFIX, files=len(files), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      archive_bytes=path.stat().st_size, unsigned=True)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--app", type=Path)
    source.add_argument("--validate-only", type=Path, metavar="IPA")
    parser.add_argument("--sdk", type=Path, help="Selected iphoneos SDK; mandatory for packaging")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    temporary = None
    try:
        if args.app:
            require(args.sdk is not None and args.output is not None, "Packaging requires --sdk and --output")
            files = collect_bundle(args.app)
            bundle_report = validate_bundle(files, args.sdk)
            outputs = inspect_dependencies(args.app, bundle_report)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix=".ipa.tmp", delete=False) as handle:
                temporary = Path(handle.name)
            write_ipa(files, temporary)
            report = validate_ipa(temporary, args.sdk, files)
            report["otool_L"] = outputs
            os.replace(temporary, args.output)
            temporary = None
            report["ipa"] = str(args.output)
        else:
            report = validate_ipa(args.validate_only, args.sdk)
            report["ipa"] = str(args.validate_only)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in ("ipa", "sha256", "files", "unsigned", "sdk_availability_checked")}, indent=2))
        return 0
    except (ValidationError, OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f"IPA validation failed: {error}")
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
