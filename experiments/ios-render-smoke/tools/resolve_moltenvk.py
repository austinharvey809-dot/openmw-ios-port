#!/usr/bin/env python3
"""Resolve a supplied MoltenVK distribution; never download or execute its files.

Only static arm64 iOS *device* slices are accepted. Info.plist describes the
slice; the eventual Apple linker still has to validate the actual archive.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import plistlib
import sys


class ResolutionError(ValueError):
    """The supplied distribution cannot identify one usable dependency."""


@dataclass(frozen=True)
class ResolvedMoltenVK:
    library: Path
    include_dir: Path
    xcframework: Path


def _relative_child(parent: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ResolutionError(f"{field} must be a nonempty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolutionError(f"{field} escapes its XCFramework directory")
    try:
        result = (parent / relative).resolve()
    except (OSError, ValueError) as error:
        raise ResolutionError(f"{field} contains an invalid filesystem path") from error
    try:
        result.relative_to(parent.resolve())
    except ValueError as error:
        raise ResolutionError(f"{field} escapes its XCFramework directory") from error
    return result


def _frameworks(root: Path) -> list[Path]:
    if root.name == "MoltenVK.xcframework":
        return [root]
    return sorted({path.resolve() for path in root.rglob("MoltenVK.xcframework") if path.is_dir()})


def _headers(framework: Path, slice_dir: Path, entry: dict) -> Path:
    # Prefer the headers shipped with this exact slice. Metadata paths must not
    # escape the slice, even when the supplied Info.plist contains symlinks.
    headers_path = entry.get("HeadersPath", "Headers")
    headers = _relative_child(slice_dir, headers_path, "HeadersPath")
    if (headers / "vulkan" / "vulkan.h").is_file():
        return headers

    # Official distributions also have MoltenVK/include next to static/.
    # Inspect only these two nearby layouts, never an arbitrary system SDK.
    candidates = {
        (parent / "include").resolve()
        for parent in (framework.parent, framework.parent.parent)
        if (parent / "include" / "vulkan" / "vulkan.h").is_file()
    }
    if len(candidates) == 1:
        return candidates.pop()
    if len(candidates) > 1:
        raise ResolutionError(f"Ambiguous Vulkan include directories near {framework}")
    raise ResolutionError(
        f"No Vulkan headers for {framework}: expected {headers / 'vulkan' / 'vulkan.h'} "
        "or the adjacent distribution include/vulkan/vulkan.h"
    )


def resolve_moltenvk(root: Path | str) -> ResolvedMoltenVK:
    """Select one static device archive using XCFramework metadata.

    A complete distribution may contain dynamic and simulator variants; they
    are ignored. Multiple static arm64 device matches are an error, even when
    their filenames or archive contents appear identical.
    """
    try:
        root = Path(root).expanduser().resolve(strict=True)
    except (OSError, ValueError) as error:
        raise ResolutionError(f"MoltenVK root does not exist: {root}") from error
    if not root.is_dir():
        raise ResolutionError(f"MoltenVK root must be a directory: {root}")
    frameworks = _frameworks(root)
    if not frameworks:
        raise ResolutionError(f"No MoltenVK.xcframework found under {root}")

    matches: list[tuple[Path, Path, Path, dict]] = []
    for framework in frameworks:
        metadata_path = framework / "Info.plist"
        try:
            with metadata_path.open("rb") as metadata_file:
                metadata = plistlib.load(metadata_file)
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            raise ResolutionError(f"Cannot read XCFramework metadata: {metadata_path}") from error
        if not isinstance(metadata, dict) or not isinstance(metadata.get("AvailableLibraries"), list):
            raise ResolutionError(f"Invalid AvailableLibraries in {metadata_path}")

        for entry in metadata["AvailableLibraries"]:
            if not isinstance(entry, dict):
                raise ResolutionError(f"Invalid library entry in {metadata_path}")
            architectures = entry.get("SupportedArchitectures", [])
            if (
                entry.get("SupportedPlatform") != "ios"
                or entry.get("SupportedPlatformVariant") is not None
                or not isinstance(architectures, list)
                or "arm64" not in architectures
            ):
                continue
            library_path = entry.get("LibraryPath")
            if not isinstance(library_path, str) or Path(library_path).suffix != ".a":
                continue
            slice_dir = _relative_child(framework, entry.get("LibraryIdentifier"), "LibraryIdentifier")
            library = _relative_child(slice_dir, library_path, "LibraryPath")
            if not library.is_file():
                raise ResolutionError(f"Static device archive is missing: {library}")
            matches.append((framework, slice_dir, library, entry))

    if not matches:
        raise ResolutionError(
            f"No static arm64 iOS device slice in {root}; simulator, macOS, "
            "Mac Catalyst and dynamic frameworks are not accepted"
        )
    if len(matches) != 1:
        locations = "\n".join(str(match[2]) for match in matches)
        raise ResolutionError(
            "Ambiguous static arm64 iOS device slices; narrow --root to one "
            f"static MoltenVK.xcframework:\n{locations}"
        )

    framework, slice_dir, library, entry = matches[0]
    return ResolvedMoltenVK(library, _headers(framework, slice_dir, entry), framework)


def _cmake_literal(path: Path) -> str:
    # Bracket arguments prevent CMake variable expansion, list splitting and
    # command injection from paths containing $, semicolons, quotes or brackets.
    value = path.as_posix()
    equals = "="
    while f"]{equals}]" in value:
        equals += "="
    return f"[{equals}[{value}]{equals}]"


def render_cmake(resolved: ResolvedMoltenVK) -> str:
    """Return an include file with three literal absolute-path variables."""
    return (
        "# Generated by resolve_moltenvk.py; no dependency code was executed.\n"
        f"set(SMOKE_MOLTENVK_LIBRARY {_cmake_literal(resolved.library)})\n"
        f"set(SMOKE_VULKAN_INCLUDE_DIR {_cmake_literal(resolved.include_dir)})\n"
        f"set(SMOKE_MOLTENVK_XCFRAMEWORK {_cmake_literal(resolved.xcframework)})\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Extracted distribution or static XCFramework")
    parser.add_argument("--output", required=True, type=Path, help="Generated CMake include file")
    arguments = parser.parse_args(argv)
    try:
        resolved = resolve_moltenvk(arguments.root)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(render_cmake(resolved), encoding="utf-8")
    except (OSError, ResolutionError) as error:
        print(f"resolve_moltenvk: {error}", file=sys.stderr)
        return 2
    print(f"MoltenVK static iOS device archive: {resolved.library}")
    print(f"Vulkan headers: {resolved.include_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
