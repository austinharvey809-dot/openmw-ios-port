#!/usr/bin/env python3
"""Compare exported Vulkan queries with the pinned audit manifest. Python stdlib only.

Supported means reported by Vulkan, not enabled/tested or a Zink compatibility certificate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def is_number(value):
    return type(value) in (int, float)


def is_version(value):
    return isinstance(value, list) and len(value) == 3 and all(is_number(v) and v >= 0 for v in value)


def evaluate(row, device, instance):
    if not isinstance(row, dict):
        return {"status": "unknown", "actual": None, "reason": "Malformed requirement row"}

    def result(status, actual=None, reason=""):
        return dict(row, status=status, actual=actual, reason=reason)

    kind, key = row.get("kind"), row.get("key")
    if kind in ("any", "all"):
        alternatives = row.get("all_of" if kind == "all" else "any_of")
        if not isinstance(alternatives, list) or not alternatives:
            return result("unknown", reason="Missing alternatives")
        children = [evaluate(child, device, instance) for child in alternatives]
        statuses = [child["status"] for child in children]
        if kind == "all":
            status = "unsupported" if "unsupported" in statuses else "unknown" if "unknown" in statuses else "supported"
        else:
            status = "supported" if "supported" in statuses else "unknown" if "unknown" in statuses else "unsupported"
        return dict(result(status, reason="Alternative requirements"), alternatives=children)
    if kind == "manual":
        return result("unknown", reason="Requires build/execution/presentation validation")
    actual = None
    if kind == "api":
        actual = device.get("identity", {}).get("api_version")
    elif kind in ("extension", "instance_extension"):
        extensions = (instance if kind == "instance_extension" else device).get("extensions")
        if not isinstance(extensions, dict) or not isinstance(key, str):
            return result("unknown", reason="Extension enumeration unavailable")
        api = instance.get("api_version") if kind == "instance_extension" else device.get("identity", {}).get("api_version")
        promoted = row.get("core_since")
        if is_version(promoted) and is_version(api) and api >= promoted:
            return result("supported", api, "Explicit requirement permits core promotion; feature bits checked separately")
        if key not in extensions:
            return result("unsupported", False, "Extension absent from completed enumeration")
        actual = extensions[key]
        if "value" not in row:
            return result("supported", actual, "Extension advertised; execution correctness untested")
    elif kind == "format":
        actual = device.get("formats", {}).get(row.get("format"), {}).get(key)
    else:
        group = {"feature": "features", "limit": "limits", "property": "properties", "surface": "surface"}.get(kind)
        if group is None:
            return result("unknown", reason="Unsupported requirement kind")
        actual = device.get(group, {}).get(key)
    if actual is None:
        return result("unknown", reason="Field not queried/query failed; missing is not false")
    expected, op = row.get("value"), row.get("op", "eq")
    if kind == "api" and is_version(actual) and is_version(expected):
        predicates = {"eq": lambda: actual == expected, "ge": lambda: actual >= expected, "le": lambda: actual <= expected}
    elif op == "eq" and type(actual) is bool and type(expected) is bool:
        predicates = {"eq": lambda: actual == expected}
    elif is_number(actual) and is_number(expected):
        predicates = {"eq": lambda: actual == expected, "ge": lambda: actual >= expected, "le": lambda: actual <= expected}
        if type(actual) is int and type(expected) is int and actual >= 0 and expected >= 0:
            predicates["bits_all"] = lambda: actual & expected == expected
    else:
        return result("unknown", actual, "Mismatched comparison data type")
    if op not in predicates:
        return result("unknown", actual, "Unsupported comparison")
    return result("supported" if predicates[op]() else "unsupported", actual, "Comparison of reported data; execution correctness untested")


def evaluate_group(rows, device, instance):
    counts = {"supported": 0, "unsupported": 0, "unknown": 0}
    if not isinstance(rows, list) or not rows:
        return {"status": "unknown", "checks": [], "counts": counts, "reason": "Empty/missing requirement group"}
    checks = [evaluate(row, device, instance) for row in rows]
    required = []
    for item in checks:
        counts[item["status"]] += 1
        if item.get("severity") != "advisory":
            required.append(item["status"])
    status = "unsupported" if "unsupported" in required else "unknown" if "unknown" in required else "supported"
    return {"status": status, "checks": checks, "counts": counts}


def compare(capabilities, requirements):
    devices = []
    for device in capabilities.get("devices", []):
        groups = {name: evaluate_group(profile.get("requirements"), device, capabilities.get("instance", {}))
                  for name, profile in requirements.get("profiles", {}).items()}
        groups["runtime_checks"] = evaluate_group(requirements.get("runtime_checks"), device, capabilities.get("instance", {}))
        devices.append({"identity": device.get("identity", {}), "groups": groups,
                        "query_status": device.get("query_status", "unknown"), "query_diagnostics": device.get("unknown", [])})
    return {"schema_version": 1, "mesa_version": requirements.get("mesa_version", "unknown"),
            "audit_id": capabilities.get("audit_id"), "recorded_at": capabilities.get("recorded_at"),
            "query_diagnostics": capabilities.get("unknown", []),
            "requirements_sources": requirements.get("sources", []), "devices": devices,
            "scope": "Reported capabilities only; no Mesa/Zink correctness, presentation, performance or thermal validation.",
            "zink_viability": "unknown_until_actual_zink_and_presentation_tests"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capabilities", type=Path)
    parser.add_argument("--requirements", type=Path, default=Path(__file__).resolve().parents[1] / "data/mesa-25.1.9-requirements.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare(json.loads(args.capabilities.read_text(encoding="utf-8")),
                     json.loads(args.requirements.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}; {len(report['devices'])} device(s). Query results do not certify Zink.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
