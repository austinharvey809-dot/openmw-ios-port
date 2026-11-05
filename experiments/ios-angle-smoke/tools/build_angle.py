#!/usr/bin/env python3
"""Gate 0: explicit opt-in, pinned standalone device dependency build (macOS only)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def lock():
    return json.loads((ROOT / "data/angle-lock.json").read_text(encoding="utf-8"))


def client_config(pin):
    # Do not run arbitrary DEPS hooks (Rust, hermetic Xcode, test utilities).
    # gclient still resolves all active pinned Git/CIPD/GCS dependencies.
    return "solutions = " + repr([{
        "name": "angle", "url": pin["angle_repository"],
        "managed": False, "custom_deps": {}, "custom_vars": {
            "checkout_angle_cl_deps": False, "checkout_angle_dawn_deps": False,
            "checkout_angle_internal": False, "checkout_angle_mesa": False,
            "checkout_angle_restricted_traces": False, "checkout_extra_traces": False,
            "download_remoteexec_cfg": False,
        },
    }]) + "\ntarget_os = ['ios']\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="New/empty external build directory")
    parser.add_argument("--output", type=Path, required=True, help="New dependency package directory")
    parser.add_argument("--allow-downloads", action="store_true", help="Authorize multi-GB downloads/build; otherwise print plan only")
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args(argv)
    pin = lock()
    print(json.dumps({"gate": 0, "lock": pin, "gn_args": (ROOT / "args.gn").read_text(),
                      "targets": ["libEGL", "libGLESv2"], "downloads_enabled": args.allow_downloads}, indent=2), flush=True)
    if not args.allow_downloads:
        return 0
    if platform.system() != "Darwin":
        parser.error("A macOS host with full Xcode and iphoneos SDK is required; Windows downloads are disabled")
    if args.jobs < 1 or args.jobs > 8:
        parser.error("--jobs must be between 1 and 8")
    workspace, output = args.workspace.resolve(), args.output.resolve()
    for path in (workspace, output):
        if path.exists() and any(path.iterdir()):
            parser.error(f"Refusing to overwrite nonempty directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
    if workspace == output or workspace in output.parents or output in workspace.parents:
        parser.error("Workspace and output must be separate directories")
    if shutil.disk_usage(workspace).free < 20 * 1024**3:
        parser.error("Reserve at least 20 GiB free disk; actual checkout requirements are not measured")
    env = dict(os.environ, DEPOT_TOOLS_UPDATE="0", DEPOT_TOOLS_METRICS="0", GCLIENT_PY3="1")
    depot = workspace / "depot_tools"

    def run(command, cwd=workspace, capture=False):
        print("RUN", repr([str(item) for item in command]), flush=True)
        return subprocess.run([str(item) for item in command], cwd=cwd, env=env,
                              check=True, text=True, stdout=subprocess.PIPE if capture else None).stdout

    run(["git", "init", depot])
    run(["git", "remote", "add", "origin", pin["depot_tools_repository"]], depot)
    run(["git", "fetch", "--depth=1", "origin", pin["depot_tools_revision"]], depot)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], depot)
    env["PATH"] = str(depot) + os.pathsep + env["PATH"]
    (workspace / ".gclient").write_text(client_config(pin), encoding="utf-8")
    run([depot / "gclient", "sync", "--revision", "angle@" + pin["angle_revision"],
         "--nohooks", "--no-history", "--shallow", "--jobs", str(args.jobs)])
    source = workspace / "angle"
    actual = run(["git", "rev-parse", "HEAD"], source, True).strip()
    if actual != pin["angle_revision"]:
        raise RuntimeError("ANGLE checkout revision mismatch")
    if hashlib.sha256((source / "DEPS").read_bytes()).hexdigest() != pin["deps_sha256"]:
        raise RuntimeError("ANGLE DEPS checksum mismatch; refusing an unlocked graph")
    for name, revision in pin["required_deps"].items():
        if run(["git", "rev-parse", "HEAD"], source / name, True).strip() != revision:
            raise RuntimeError(f"Dependency revision mismatch: {name}")
    (output / "gclient-revinfo.txt").write_text(run([depot / "gclient", "revinfo", "-a"], capture=True), encoding="utf-8")
    # Required metadata hook only. Compiler/GN/Ninja/CPython are pinned sync deps;
    # fail visibly if the selected graph no longer supplies them.
    run([sys.executable, "build/util/lastchange.py", "-o", "build/util/LASTCHANGE"], source)
    if not (source / "third_party/llvm-build/Release+Asserts/bin/clang").is_file():
        raise RuntimeError("Pinned sync did not provision Clang; audit required toolchain hook before proceeding")
    build = source / "out/ios-angle-arm64"
    build.mkdir(parents=True)
    shutil.copy2(ROOT / "args.gn", build / "args.gn")
    run([depot / "gn", "gen", build, "--fail-on-unused-args"], source)
    run([depot / "ninja", "-C", build, "-j", str(args.jobs), "libEGL", "libGLESv2"], source)
    toolchain = {"xcode": run(["xcodebuild", "-version"], capture=True),
                 "sdk": run(["xcrun", "--sdk", "iphoneos", "--show-sdk-version"], capture=True),
                 "clang": run([source / "third_party/llvm-build/Release+Asserts/bin/clang", "--version"], capture=True),
                 "host": platform.platform()}
    # No renamed dylibs, install_name_tool patches, simulator substitution or signing.
    frameworks = output / "Frameworks"
    frameworks.mkdir()
    products = list(build.glob("*.framework"))
    if len(products) != 2:
        raise RuntimeError(f"Expected exactly two top-level framework products, found {products}; inspect GN outputs")
    for product in products:
        shutil.copytree(product, frameworks / product.name, symlinks=True)
    shutil.copytree(source / "include", output / "include")
    shutil.copy2(ROOT / "data/angle-lock.json", output / "angle-lock.json")
    shutil.copy2(ROOT / "args.gn", output / "args.gn")
    # Overinclusive source notices: retain original paths and license metadata for
    # all fetched dependencies, not just the top-level BSD notice.
    notices = output / "Licenses"
    count = 0
    for folder, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name not in (".git", "out", "node_modules")]
        for name in files:
            if name.upper().startswith(("LICENSE", "COPYING", "NOTICE")) or name == "README.chromium":
                path = Path(folder) / name
                if path.is_file() and not path.is_symlink():
                    target = notices / path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    count += 1
    if not (notices / "LICENSE").is_file():
        raise RuntimeError("Missing upstream ANGLE license")
    (output / "angle-build.json").write_text(json.dumps({
        "angle_revision": actual, "target": "arm64-apple-ios18.0", "metal_only": True,
        "toolchain": toolchain, "notice_files": count, "validation": "pending",
    }, indent=2) + "\n", encoding="utf-8")
    run([sys.executable, ROOT / "tools/validate_dependency.py", "--root", output,
         "--sdk", run(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], capture=True).strip()])
    print("GATE 0 PASS: validated ARM64 iPhoneOS dependency package; runtime remains untested", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
