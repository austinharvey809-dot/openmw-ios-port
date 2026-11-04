#!/usr/bin/env python3
"""Compare the actual Foundation evaluator with host regression fixtures on macOS."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from compare_caps import compare
from test_compare_caps import comparison_cases


def projection(report):
    return [{name: {"status": group["status"], "counts": group["counts"],
                   "checks": [{"status": row["status"], "actual": row["actual"]} for row in group["checks"]]}
             for name, group in device["groups"].items()} for device in report["devices"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    args = parser.parse_args(argv)
    cases = comparison_cases()
    with tempfile.TemporaryDirectory(prefix="caps-native-audit-") as directory:
        directory = Path(directory)
        for row, device, expected in cases:
            capabilities = {"devices": [device], "instance": {"extensions": {}}}
            requirements = {"mesa_version": "25.1.9", "profiles": {"fixture": {"requirements": [row]}}, "runtime_checks": [{"kind": "manual"}]}
            caps_path, req_path = directory / "caps.json", directory / "requirements.json"
            caps_path.write_text(json.dumps(capabilities), encoding="utf-8")
            req_path.write_text(json.dumps(requirements), encoding="utf-8")
            result = subprocess.run([str(args.native.resolve()), str(caps_path), str(req_path)], capture_output=True, text=True, check=True)
            native = json.loads(result.stdout)
            python = compare(capabilities, requirements)
            if native["devices"][0]["groups"]["fixture"]["status"] != expected or projection(native) != projection(python):
                raise RuntimeError(f"Native/Python comparison differs: {row['id']}")
        # Also exercise every real profile's nesting and optional branches. This device is
        # intentionally synthetic/incomplete; it is not a measured iPhone profile.
        requirements = json.loads((Path(__file__).resolve().parents[1] / "data/mesa-25.1.9-requirements.json").read_text())
        capabilities = {"devices": [{"identity": {"device_name": "SYNTHETIC MANIFEST REGRESSION", "api_version": [1, 2, 0]},
                                      "extensions": {}, "features": {}, "limits": {}, "formats": {}, "properties": {}}],
                        "instance": {"extensions": {}}}
        caps_path.write_text(json.dumps(capabilities), encoding="utf-8")
        req_path.write_text(json.dumps(requirements), encoding="utf-8")
        native = json.loads(subprocess.run([str(args.native.resolve()), str(caps_path), str(req_path)],
                                          capture_output=True, text=True, check=True).stdout)
        if projection(native) != projection(compare(capabilities, requirements)):
            raise RuntimeError("Native/Python comparison differs on the pinned complete manifest")
    print(f"Native Foundation/Python comparison parity: {len(cases)} fixtures and all pinned profiles passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
