# G0C: genuine NIF parsing on iPhoneOS — preparation

Prepared 2026-11-11, branch `ios-port`. This isolated experiment is ready for
manual source review. **No G0C iPhoneOS compilation, linking, bundle/IPA
validation, installation or physical-device parsing has been performed.**
Milestone F's physical iPhone data result is user-confirmed; G0B's host parsing
result is independently confirmed below. Neither establishes G0C device parsing.

## Completed G0B host evidence

[Build #6](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/42954098459)
at `64cad82d891438c5d07ed4904321e4d04901aa0b` succeeded on `macos-26-arm64`.
Read-only GitHub job/API inspection confirmed 46 passing Python tests, exact
Bullet acquisition, configuration, compilation/linking and actual parser runtime:

```text
PASS genuine OpenMW NIF parse version=4.0.0.2 records=3 roots=1 geometry=1 vertices=3 triangles=1
invalid: PASS genuine parser rejected invalid
truncated: PASS genuine parser rejected truncated
invalid-reference: PASS genuine parser rejected invalid-reference
missing: PASS missing resource rejected
wrong-resource-bytes: PASS rejected before parser
```

The positive NIF is 392 bytes, SHA-256
`0b77632dd08be22a3df33be66939065e4d467fa1231b9a12459f844224f846ff`;
its BSA is 440 bytes, SHA-256
`72adc5667e62f146d4bfa770b568b29b3f519def6cce1784a49f67c632058ec3`.
All ten input hashes, revisions and observations are recorded in
[`data/g0b-completion.json`](data/g0b-completion.json). The unchanged G0B data
directory remains the fixture authority; it is not copied into this source tree.

The API lists artifact `13825894163`, `ios-openmw-nif-host-42954098459-1`,
317,618 bytes, reported archive SHA-256
`6a35d315cd516df813332a15a91edb66f017a2ffd66fa2e7a5565cfea17e7760`.
Its ZIP contents/checksum could not be independently checked locally: the
available download client hit the sandbox TLS limitation. This is an artifact
verification limit, not uncertainty about the observed job/runtime logs.
Retrieved job logs remain in ignored `artifacts/g0b-build6-job.log`; bulky
logs, build outputs, IPAs and exported phone diagnostics belong in that directory.

## Supported device library closure and reuse

| Component | Exact reuse / device requirement |
| --- | --- |
| ESM/BSA/VFS | Add unchanged E, which adds D once: 21 units including one registration helper; avoid duplicate A/B/C archives |
| NIF | Compile the 14 units from G0B's audited source manifest: twelve NIF units plus files/hash and smhasher |
| Native test | G0C0 compiles G0B's unchanged `nif_parse_check.cpp`; UIKit includes the same implementation with its main renamed and calls it in-process |
| OSG | Exact `OpenMW/osg` revision `9b384d5439977784e5cd250ff8ff7966928ddd27`; static `osg` core and OpenThreads; no osgDB, viewer, plugins or ANGLE targets |
| Bullet | Exact 3.25 URL/SHA-512 and existing G0B acquisition/provenance recipe; static BulletCollision then LinearMath, with `BT_USE_DOUBLE_PRECISION` on libraries and consumer |
| Language/platform | AppleClang, real iPhoneOS SDK, ARM64, C++20, minimum iOS exactly 18.0; macOS/simulator binaries rejected |
| Apple system linkage | libc++/libSystem and any emitted libobjc dependency; UIKit/Foundation for app; SDK OpenGLES for original OSG core linkage |
| Generated configuration | Real OSG/OpenThreads templates; Config/Version for both, osg/GL; generated include directory precedes D's math-only Config and reaches parser consumers |
| Packaging | Reuse F's read-only ARM64/iOS Mach-O, SDK TAPI availability, otool agreement, file collector and ZIP writer helpers through a separate module instance; F files stay unchanged |

The supported library-level closure intentionally retains the proven full OSG
core target. It is not a claim that every compiled OSG translation unit is
necessary for this single triangle. Shrinking the core archive is deferred;
there is no replacement math implementation or dependency on dead stripping to
hide undefined symbols.

The pinned root OSG CMake script assumes a hardcoded Xcode/iPhone SDK path and
macOS OpenGL discovery. `cmake/osg/CMakeLists.txt` adapts configuration only:
it invokes the original OpenThreads/core subdirectory recipes, points their
project-source lookup at the clean pinned checkout, generates the complete
upstream templates, imports D's audited math switches, and selects upstream's
Apple GLES2 header profile. The original core recipe's `LINK_CORELIB_DEFAULT`
links `OPENGL_gl_LIBRARY`; here `find_library` resolves that to SDK OpenGLES.
This explicit native system dependency is inspected at G0C0, not substituted by
ANGLE. The application creates no GL context, submits no geometry and implements
no rendering integration. See the pinned
[OSG recipe](https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/CMakeLists.txt)
and [link macro](https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/CMakeModules/OsgMacroUtils.cmake).

OpenThreads uses its supported mutex-atomic configuration, avoiding cross-target
`try_run` and deprecated OSAtomic selection. Both consumers and libraries see
the same generated configuration. OSG matrix, plane and quaternion precision
remain double; bounding spheres/boxes remain float as in D/G0B. No upstream file
or pinned checkout is modified. The generated files exist before compilation,
and all five are required at configure time and preserved in bundle provenance.

## Actual runtime and exported evidence

The single background worker calls all six unchanged G0B cases in-process.
The positive path loads ESM, reads STAT/MODL, resolves BSA/VFS bytes, obtains a
fresh stream, invokes `Nif::Reader`, checks typed decoded relationships and
indices, and emits counts from the actual decoded objects. G0C reads those
counts from the genuine diagnostic output; it does not assign expected counts
as observed results. It also retrieves actual VFS bytes for CommonCrypto
SHA-256 verification against the approved NIF hash.

Every input is a regular, nonlinked bundled file. The exact twelve-entry
fixture inventory and SHA-256/size manifest are checked before parsing; the
source manifest and build provenance are bound to compiled hash constants.
Snapshots after **each** case must match the initial snapshot. All five
negative cases, their exit codes and expected diagnostics are mandatory. A
missing/failed case, changed input or incomplete evidence prevents overall PASS.
On exceptions, available case outputs and post-failure integrity findings remain
in the FAIL result.

The UIKit screen displays RUNNING, then PASS/FAIL, decoded vertices/triangles/
geometry, resource identifier and SHA-256, plus full provenance/results. It
enables sharing only after both `nif-smoke.json` and `nif-smoke.log` are saved.
The LOG is the same complete pretty-printed JSON for readable and comparable
evidence. The screen's PASS requires the genuine suite and successful export;
installation/launch alone is insufficient. Device identity, hardware identifier,
session ID, timestamps and elapsed time accompany the case logs.

## Manual-only CI and native gates

`.github/workflows/ios-openmw-nif-device-smoke.yml` has only `workflow_dispatch`
and read-only contents permission. It first reruns the unchanged G0B host
configuration/build/runtime as `host-validation`. The dependent device job
audits sources, fixtures, all 53 A–E entries and the 47 preserved F/G0B files,
runs the new offline contracts and Python syntax checks, and provisions the
same verified Bullet archive in runner temporary storage.

The native build uses Unix Makefiles to retain the real compiler-command
database required by G0B's precision audit. CMake supports non-Xcode iOS cross
builds and flat resource placement; nevertheless, this new UIKit bundle path
must be validated on the actual runner. See
[CMake toolchains](https://cmake.org/cmake/help/latest/manual/cmake-toolchains.7.html#cross-compiling-for-ios-tvos-or-watchos)
and [bundle resource placement](https://cmake.org/cmake/help/latest/prop_sf/MACOSX_PACKAGE_LOCATION.html).

- **G0C0:** Compile/link the genuine iPhoneOS executable; require ARM64, iOS
  LC_BUILD_VERSION, deployment 18.0, no signature/RPATH/host library, permitted
  system dependencies available in the selected SDK, and agreement with otool.
- **G0C1:** Compile/link the UIKit app. Signing is disabled; the linker is told
  not to add an ad-hoc signature. Any unexpected signature is rejected.
- **G0C2:** Require exact bundle inventory, iPhone plist identity/settings,
  identical prepared/source fixture bytes, complete generated-header/license/
  Bullet provenance, and the matching metadata contract embedded in the app.
- **G0C3:** Write an unsigned IPA, reopen it independently, reject duplicate,
  encrypted, linked, misplaced or changed files, validate SDK/Mach-O/resources
  again, and compare all archive bytes/modes against the validated bundle.

All gates are fail-fast and required. Separate outcomes, logs, compiler commands,
available CMake diagnostics, link executable and prepared resource provenance
are retained, including failures. The job status explicitly reports signing and
physical-device execution as not performed. No CI command signs, installs,
dispatches another workflow, stages, commits or pushes.

## Local validation and risks

Python's WindowsApps alias still fails to launch; no local CMake, Apple SDK,
C++/Objective-C++ compiler or compatible native parser is available. Therefore
the new 13-test Python suite, Python syntax, configure/link, bundle and IPA
validators are **unverified as executions**. The 46-test G0B pass is historical
host evidence, not a new local or device result. New regression fixtures use
synthetic Mach-O and JSON metadata only and cannot establish native acceptance.

Available local PowerShell/Git Bash checks verify preserved hashes, exact G0B
fixture sizes/hashes and inventory, source/configuration contracts, original
Bullet recipe/pin equality, workflow gate order/manual trigger, all sixteen
shell blocks, and new-file/Git whitespace. The original Morrowind installation
is not accessed. All 56 starting protected raw file hashes (G0B, F and nine
graphics files) match; A–E hashes and the clean pinned OSG revision match.
No private assets, upstream changes, new source dependencies, signing material,
rendering implementation or system tools are introduced.

Remaining risks require native evidence: compatibility of the original full
OSG core/GLES2 build with the current iPhoneOS SDK, its Apple symbol-lookup
branches, mutex-atomic configuration, any additional system dependency exposed
by native linking, UIKit/Objective-C++ compilation, non-Xcode bundle placement,
and SDK/TAPI/unsigned packaging behavior. No unknown dependency is allowed to
silently pass. A confirmed blocker requiring upstream changes must be reported
and reviewed rather than patched around with dummy headers or replacement code.

## Created files and gate status

The only new tracked-source candidates are this experiment's nineteen files
and `.github/workflows/ios-openmw-nif-device-smoke.yml`. Existing files are
unchanged. The experiment contains:

```text
.gitignore
CMakeLists.txt
Info.plist.in
README.md
cmake/bullet.cmake
cmake/osg/CMakeLists.txt
data/g0b-completion.json
data/preserved-source-sha256.json
src/NifProbe.cpp
src/NifProbe.hpp
src/NifCheck.mm
src/NifCheck.hpp
src/main.mm
tools/common.py
tools/prepare.py
tools/ci.py
tools/package_ios.py
tools/verify_result.py
tools/test_g0c.py
```

| Gate | Observed status |
| --- | --- |
| G0B macOS ARM64 parsing | PASS, independently verified Build #6 logs |
| G0C offline Python regressions/syntax | Unverified locally: Python cannot launch |
| iPhoneOS compilation | Unverified: Apple toolchain unavailable locally |
| G0C0 iPhoneOS linking/dependencies | Unverified |
| G0C1 UIKit compilation/linking | Unverified |
| G0C2 bundle verification | Unverified |
| G0C3 IPA packaging/reopening | Unverified |
| Signing/install/device execution | Not performed |

## Next manual steps

1. Review all new files and dependency/configuration decisions. Separately
   authorize any commit/push and manual workflow run; none was performed here.
2. Require host validation and G0C0–G0C3 to succeed for that exact commit. Inspect
   gate-status JSON, logs, SDK dependencies, provenance and unsigned IPA hash.
   A compile/link/bundle failure is not device acceptance.
3. Only after all gates pass, download the unsigned IPA on Windows. Use the
   existing Sideloadly workflow with your own Apple account to sign/install it
   on the iPhone 16 Plus; enable Developer Mode/trust as previously established.
   No credentials are handled by these tools or committed to this repository.
4. Launch once. Capture the final screen and full provenance/session. Require
   genuine PASS, 3 records, 1 root, 1 geometry, 3 vertices, 1 triangle, correct
   resource ID/hash, all six cases and unchanged inputs. Export both files
   through Share/Files and store them in ignored `artifacts/device/`.
5. With a functioning Python 3.10+ interpreter, independently review the exports:

   ```text
   python -B experiments/ios-openmw-nif-device-smoke/tools/verify_result.py --json experiments/ios-openmw-nif-device-smoke/artifacts/device/nif-smoke.json --log experiments/ios-openmw-nif-device-smoke/artifacts/device/nif-smoke.log --expected-source-commit <the-exact-successful-G0C-CI-commit>
   ```

   Paths above are examples; use the actual exported files under this
   experiment's ignored artifact directory. The validator requires matching
   JSON/LOG, provenance, decoded/stdout agreement, all negatives and immutable
   inputs. Review the screenshot/device identity alongside it. Only then can
   G0C physical parsing be accepted. G1/G2 rendering remains out of scope.
