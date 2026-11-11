# G0B Build #5 generated-header preparation

Reviewed on 2026-11-10 (America/Chicago), branch `ios-port`, starting HEAD
`aa1a026602`. Ready for manual review; the corrected native build and genuine
parser execution remain unverified. Nothing was staged, committed, pushed or
dispatched during this task.

## Confirmed failure

[Build #4](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/42950318076)
passed source validation, verified Bullet acquisition, and configuration. Its
source gate ran all 34 then-current G0B tests successfully. Compilation failed
in the genuine parser target; the parser runtime step was skipped.

Read-only job-log inspection confirmed this include chain:

```text
components/nif/effect.hpp -> components/nif/node.hpp -> osg/Plane
-> osg/Matrix -> osg/Matrixd -> osg/Object -> osg/Referenced
-> OpenThreads/Mutex -> OpenThreads/Exports
fatal error: 'OpenThreads/Config' file not found
```

The same failure occurred in base, controller and data translation units. The
logs show `osg` had already built before these failures. This is a missing
consumer include path, not missing OSG acquisition or a header-generation race.

## Generated locations and correction

The unchanged pinned checkout is clean at
`9b384d5439977784e5cd250ff8ff7966928ddd27`.
Its [OpenThreads CMake file](https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/src/OpenThreads/CMakeLists.txt)
uses `configure_file` to generate `OpenThreads/Config` and `OpenThreads/Version`
under `${PROJECT_BINARY_DIR}/include`. Its
[top-level CMake file](https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/CMakeLists.txt)
generates `osg/Config`, `osg/GL` and `osg/Version` in the same include tree.

Here OSG's project binary directory is the `osg` subdirectory of the isolated
G0 build. All five headers therefore live below `<G0 build>/osg/include`.
The pinned OSG build uses directory-scoped include settings, which do not
propagate from the child project to our parent parser target. D/E's inherited
include tree provides a math-only `osg/Config`, but no `OpenThreads/Config`.

The isolated CMake file now names `_osg_binary_dir` once, passes it as the actual
`add_subdirectory` binary directory, and derives `_osg_generated_include` from
that same path. After the upstream subdirectory returns, it requires all five
generated headers to exist as files, with a fatal error on any missing header.
Upstream generates them during configuration; no extra build-time dependency
or copied/generated substitute is needed. Existing linkage to `osg` and
`OpenThreads` remains intact.

The parser target receives:

```cmake
target_include_directories(openmw-ios-nif-parser BEFORE PUBLIC
    "$<BUILD_INTERFACE:${_osg_generated_include}>")
```

`BEFORE` gives the real OSG build configuration priority over the inherited
math-only configuration. `PUBLIC` also supplies the generated headers to the
genuine parser test executable. The build-interface expression avoids exporting
this build path as an installed interface. These scopes follow the
[official CMake include-directory contract](https://cmake.org/cmake/help/latest/command/target_include_directories.html).

No upstream source, generated header, dependency pin, workflow gate or fixture
was changed. The twelve NIF units, two support units, ESM/BSA/VFS linkage,
C++20, static double-precision Bullet, OSG math switches and genuine parser
positive/negative requirements remain intact.

## Regression coverage and validation

Four new `GeneratedOSGHeaderContracts` tests cover the shared build-directory
derivation, target/public include propagation and precedence, all five fatal
header checks after upstream configuration, absence of local header substitutes,
and retained parser/Bullet/source-provenance contracts. All 34 existing tests
are retained, for 38 total.

Python still resolves to a WindowsApps alias that fails to launch with
`The file cannot be accessed by the system`. CMake and a suitable native POSIX
C++ toolchain are unavailable locally. **No current Python test, Python syntax
check, CMake configure, host compilation/link, or genuine parser case was
executed.** Build #4's historical 34-test pass does not validate the new diff.

Available checks passed through PowerShell/.NET and Git Bash:

| Check | Result |
| --- | --- |
| A–E preservation | All 53 canonical-LF hashes match |
| G0 source hashes/include closure | 14 units, 59 local files, 48 external includes match |
| E source hashes/include closure | 21 units, 79 local files, 48 external includes match |
| D source hashes / E reused build hashes | 53/53 and 5/5 match |
| Pinned OSG source/header hashes | 7/7 match; checkout clean at the exact pin |
| Fixtures | All ten sizes/SHA-256 values and exact twelve-entry data inventory match |
| Generated-header source contracts | Build path, PUBLIC scope, precedence, five fatal guards and ordering match |
| Bullet provenance | Exact 3.25 URL/SHA-512 match upstream, helper and isolated CMake |
| Workflow shell syntax | All seven run blocks pass `bash --noprofile --norc -n` |
| Git whitespace | `git diff --check` passes; only LF/CRLF conversion warnings |
| Protected raw file hashes | All 39 match the start of this task: nine graphics, eighteen F and twelve G0 data files |
| Git index / HEAD | Unchanged |

The nine graphics hashes also match the earlier Build #4 preparation baseline.
The original Morrowind installation was not accessed or modified; no private
assets or new dependencies were added. Python audits and deterministic fixture
regeneration remain unverified as executions; the independent hash and closure
checks above passed. No global Git configuration or sandbox permissions changed.

## Files and handoff

Only these files were changed or added during this task:

- `experiments/ios-openmw-nif-smoke/CMakeLists.txt`
- `experiments/ios-openmw-nif-smoke/tools/test_g0_ci.py`
- `experiments/ios-openmw-nif-smoke/G0B-build5-review.md`

Build #5 preparation is ready for manual review. A later separately authorized
run must pass the current 38-test suite, configuration/header/precision checks,
native compilation/link and genuine parser cases. Further compiler or linker
errors and candidate-NIF rejection remain possible. No host parsing, iPhoneOS
linking, device execution or rendering result is claimed.
