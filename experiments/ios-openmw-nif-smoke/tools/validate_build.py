"""Audit configured G0B host build and Bullet precision before compilation."""

import argparse
import json
from pathlib import Path
import re


def audit(build, bullet_source):
    bullet_source = bullet_source.resolve()
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    required = ("USE_DOUBLE_PRECISION:BOOL=ON", "BUILD_SHARED_LIBS:BOOL=OFF",
                "BUILD_BULLET3:BOOL=OFF", "BUILD_BULLET2_DEMOS:BOOL=OFF",
                "BUILD_OPENGL3_DEMOS:BOOL=OFF", "BUILD_PYBULLET:BOOL=OFF",
                "DYNAMIC_OPENSCENEGRAPH:BOOL=OFF", "DYNAMIC_OPENTHREADS:BOOL=OFF",
                "OSG_USE_FLOAT_BOUNDINGSPHERE:BOOL=ON", "OSG_USE_FLOAT_BOUNDINGBOX:BOOL=ON",
                "OSG_USE_FLOAT_MATRIX:BOOL=OFF", "OSG_USE_FLOAT_QUAT:BOOL=OFF")
    for setting in required:
        if setting not in cache:
            raise ValueError("Bullet build setting missing: " + setting)
    commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
    selected = {"openmw_nif": 0, "bullet_collision": 0, "bullet_linear_math": 0}
    for entry in commands:
        file = Path(entry["file"]).resolve()
        command = entry.get("command", " ".join(entry.get("arguments", [])))
        if file.name == "node.cpp" and "components/nif" in file.as_posix():
            key = "openmw_nif"
        elif file.is_relative_to(bullet_source / "src/BulletCollision"):
            key = "bullet_collision"
        elif file.is_relative_to(bullet_source / "src/LinearMath"):
            key = "bullet_linear_math"
        else:
            continue
        if not re.search(r'(?:^|\s)-DBT_USE_DOUBLE_PRECISION(?:=1)?(?:\s|$)', command):
            raise ValueError("Double-precision macro missing from " + str(file))
        selected[key] += 1
    if any(not count for count in selected.values()):
        raise ValueError("OpenMW NIF/Bullet compile commands missing: " + repr(selected))
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--bullet-source", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"double_precision_compile_commands": audit(args.build.resolve(),
                                                               args.bullet_source.resolve()),
                      "status": "configured source audit; no compile/runtime claim"}))
