"""Acquire the repository-pinned Bullet archive for a future manual CI run.

The local audit/test path uses --archive and never accesses the network.
--download is reserved for the manually dispatched G0B workflow.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
UPSTREAM = REPO / "extern/CMakeLists.txt"
URL = "https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz"
SHA512 = ("7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674"
          "e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4")
ARCHIVE_ROOT = "bullet3-3.25"
# The reported Bullet 3.25 tarball is about 133 MiB; allow bounded headroom.
MAX_ARCHIVE = 192 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


def verify_upstream_pin():
    text = UPSTREAM.read_text(encoding="utf-8")
    if text.count("URL " + URL) != 1 or text.count("URL_HASH SHA512=" + SHA512) != 1:
        raise ValueError("Repository Bullet 3.25 source pin changed")


def digest(path):
    hash_ = hashlib.sha512()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hash_.update(block)
    return hash_.hexdigest()


def verify_archive(path, diagnostics=None):
    verify_upstream_pin()
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Bullet archive missing, linked or too large")
    if diagnostics is not None:
        diagnostics["sha512_verification_attempted"] = True
    actual = digest(path)
    if diagnostics is not None and diagnostics["transfer_completed"]:
        diagnostics["actual_sha512"] = actual
    if actual != SHA512:
        raise ValueError("Bullet SHA-512 mismatch: " + actual)
    return actual


def member_path(member):
    name = member.name
    path = PurePosixPath(name)
    raw_parts = name.rstrip("/").split("/")
    if (not name or "\\" in name or "\x00" in name or path.is_absolute()
            or any(part in ("", ".", "..") for part in raw_parts)
            or not path.parts or path.parts[0] != ARCHIVE_ROOT
            or not (member.isfile() or member.isdir())
            or (len(path.parts) < 2 and not member.isdir())):
        raise ValueError("Unsafe Bullet archive member: " + repr(name))
    return path.parts[1:]


def inspect_members(members):
    seen = set()
    total = 0
    for member in members:
        parts = member_path(member)
        if not parts:  # GitHub tarballs may include the archive root directory.
            continue
        folded = "/".join(parts).casefold()
        if folded in seen:
            raise ValueError("Duplicate Bullet archive member: " + member.name)
        seen.add(folded)
        if member.isfile():
            if member.size < 0:
                raise ValueError("Negative Bullet archive member size")
            total += member.size
            if total > MAX_EXPANDED:
                raise ValueError("Bullet archive expansion exceeds limit")
    if not any(parts == ("CMakeLists.txt",) for parts in
               (member_path(member) for member in members if member.isfile())):
        raise ValueError("Bullet source CMakeLists.txt missing")
    licenses = [member.name for member in members if member.isfile()
                and PurePosixPath(member.name).name.lower() in ("license", "license.txt", "copying")]
    if not licenses:
        raise ValueError("Bullet source license file missing")
    return licenses


def extract_verified(archive, destination):
    verify_archive(archive)  # Before inspecting or extracting any archive member.
    if destination.exists() or destination.is_symlink():
        raise ValueError("Bullet extraction destination must be new")
    with tarfile.open(archive, mode="r:gz") as tar:
        members = tar.getmembers()
        licenses = inspect_members(members)
        destination.mkdir(parents=True)
        for member in members:
            parts = member_path(member)
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise ValueError("Bullet member cannot be read")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    return licenses


def acquire(output, evidence, archive=None, download=False):
    output = output.resolve()
    evidence = evidence.resolve()
    if output.is_relative_to(REPO) or evidence.is_relative_to(REPO):
        raise ValueError("Bullet source/evidence must remain outside the repository")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Bullet output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    local_archive = output / "bullet-3.25.tar.gz"
    diagnostics = {"compressed_archive_limit_bytes": MAX_ARCHIVE,
                   "http_content_length_provided": False, "http_content_length_bytes": None,
                   "bytes_downloaded": 0,
                   "transfer_completed": False, "sha512_verification_attempted": False,
                   "archive_verified": False}
    try:
        verify_upstream_pin()
        if download:
            request = urllib.request.Request(URL, headers={"User-Agent": "OpenMW-G0B-pinned-source"})
            with urllib.request.urlopen(request, timeout=60) as response:
                length = response.headers.get("Content-Length")
                if length is not None:
                    diagnostics["http_content_length_provided"] = True
                    if not length.isascii() or not length.isdecimal():
                        raise ValueError("Invalid Bullet Content-Length")
                    diagnostics["http_content_length_bytes"] = int(length)
                    if diagnostics["http_content_length_bytes"] > MAX_ARCHIVE:
                        raise ValueError("Bullet Content-Length exceeds limit")
                with local_archive.open("xb") as target:
                    while True:
                        remaining = MAX_ARCHIVE - diagnostics["bytes_downloaded"]
                        block = response.read(min(1024 * 1024, max(1, remaining)))
                        if not block:
                            if (diagnostics["http_content_length_provided"]
                                    and diagnostics["bytes_downloaded"] != diagnostics["http_content_length_bytes"]):
                                raise ValueError("Bullet download length differs from Content-Length")
                            diagnostics["transfer_completed"] = True
                            break
                        diagnostics["bytes_downloaded"] += len(block)
                        if diagnostics["bytes_downloaded"] > MAX_ARCHIVE:
                            raise ValueError("Bullet download exceeds limit")
                        target.write(block)
        elif archive is not None:
            verify_archive(archive, diagnostics)
            shutil.copyfile(archive, local_archive)
        else:
            raise ValueError("Provide a verified local archive or explicitly request CI download")
        actual = verify_archive(local_archive, diagnostics)
        licenses = extract_verified(local_archive, output / "source")
        license_paths = []
        for index, name in enumerate(licenses):
            license_source = output / "source" / PurePosixPath(name).relative_to(ARCHIVE_ROOT)
            destination = evidence / ("bullet-license-%d.txt" % index)
            shutil.copyfile(license_source, destination)
            license_paths.append(destination.name)
        license_hashes = {name: hashlib.sha256((evidence / name).read_bytes()).hexdigest()
                          for name in license_paths}
        report = {"version": "3.25", "source_url": URL, "archive_sha512": actual,
                  "source_directory": str((output / "source").resolve()),
                  "license_evidence_sha256": license_hashes,
                  "status": "verified source archive; no parser build or runtime claim"}
        (output / "bullet-provenance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (evidence / "bullet-provenance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    except Exception as error:
        if download and not diagnostics["transfer_completed"]:
            try:
                local_archive.unlink(missing_ok=True)
            except OSError as cleanup_error:
                diagnostics["partial_archive_cleanup_error"] = str(cleanup_error)
        diagnostics["failure_reason"] = str(error)
        (evidence / "bullet-acquisition-error.json").write_text(
            json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
        (evidence / "bullet-acquisition-error.txt").write_text(str(error) + "\n", encoding="utf-8")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archive", type=Path)
    mode.add_argument("--download", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output, args.evidence, args.archive, args.download), indent=2))


if __name__ == "__main__":
    main()
