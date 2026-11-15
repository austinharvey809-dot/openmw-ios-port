# Local validation and acceptance boundaries

Prepared on 2026-11-15 against `ios-port` base
`d60ca603e82935a9ccce9ae5ec8dc9ec22013580`. Independent review conditionally
approved the original archive and authorized publication/Build #1 after focused
corrections. The original source-review archive
contains the new source/workflow and selected text/JSON validation evidence;
it contains no original assets, dependencies, executables or IPA.

## Executed locally

| Check | Result and scope |
| --- | --- |
| G4 Python | 26 tests pass; profiles, archive integrity/escapes, shader generation, compiler tokens, rejection gates, packaging contracts, preservation and controller-first contracts |
| Accepted Python suites | 206 tests across G0B/G0C/G1A/G1B/G1C/G1D/G2/G3; no failures. One CMake test initially skipped because CMake was absent from PATH; that exact test was rerun with portable CMake and passed |
| G4 native authored cases | 41 pass: 26 positive and 15 specifically diagnosed negative cases; unexpected failures/crashes do not count as rejection |
| Genuine Windows CPU build | Entire 202-unit g4-upstream target, real image plugins/serializers/dependencies and openmw-world-check compile/link successfully |
| Device C++ headers | g4-device-headers builds against the genuine desktop provider; no UIKit/Apple compile claim |
| Private original-content inspection | Exterior plus six interiors prepare successfully; original input hashes identical before/after |
| Actual generated shader pairs | 21 ESSL vertex/fragment pairs pass glslang linking; no driver/GPU execution claim |
| Workflow shell/Python syntax | 30 Bash blocks and two embedded Python blocks pass; GitHub schema execution remains a native CI gate |
| Dependency archives/sources | All six SHA-512 values and exact extracted inventories reverified after building |
| Provider/provenance | New configured source/generated-header audit passes; imported desktop provider's original single-provider/double Bullet audit passes |
| Preservation | All 4,139 preexisting snapshot files unchanged, including nine Build #15 files; 53 A–E entries, 47 F/G0B entries, original fixtures and pinned dependency contracts pass |
| Whitespace/Python syntax | Git diff check, all new source whitespace and Python AST checks pass |

G4's authored native cases cover genuine master order and missing-master rejection,
duplicate content, plugin overrides/deletes/new RefNums, moved-reference leases,
per-plugin LAND/LTEX palettes, original transforms, distinct loose/BSA precedence,
shared instance ownership and expiry, reload, real multipass terrain, root
material/depth/culling defaults, GLES3 normals-attachment adaptation, input profile
hash/inventory/path rejection, async streaming, rollback without retry churn,
door scene commits, suspend timing and grounded movement. Every case verifies
exact authored input inventories and SHA-256 values remain unchanged.

All 15 native negatives require exit 1 and their specific expected diagnostic:
missing/out-of-order masters, duplicate content, deleted CELL/LAND, bad scale,
nonfinite destination, missing mesh, broken NIF, missing image, nonfinite height,
locked/trapped door, corrupt terrain image and missing/deleted bases. Python
tests additionally ensure unrelated errors and process crashes cannot pass.

## Genuine original content, privately inspected

The genuine lower-level loader now constructs scene roots that the former
static mesh bridge deliberately filtered. These counts describe instantiated
roots, including hidden/empty editor/effect branches; they are **not verified
visible instance counts**, and need not equal accepted G3's bridge inventory.

| Original area | References | Instantiated model roots | Collision objects | Shader pairs |
| --- | ---: | ---: | ---: | ---: |
| Initial nine Seyda Neen exterior cells | 1,849 | 1,715 | 950 | 6 |
| Fargoth's House | 46 | 43 | 41 | 2 |
| Lighthouse | 54 | 46 | 30 | 2 |
| Census and Excise Office | 268 | 234 | 182 | 3 |
| Arrille's Tradehouse | 207 | 176 | 148 | 2 |
| Imperial Prison Ship | 262 | 249 | 187 | 2 |
| Addamasartus | 285 | 267 | 184 | 4 |

The initial exterior has 418 genuine terrain passes. The explicit single-color
GLES3 adapter omits 385 unused normals-attachment state operations while keeping
color blending/depth and refusing other unsupported indexed capabilities.

The original-content CPU test grounds at the real Fargoth return-door arrival
and advances a short movement probe. It commits an adjacent neighborhood and
returns, then follows an unlocked Lighthouse door into the original interior
and returns outside: five total world loads, two committed door transitions,
zero failed loads. The test deliberately repositions the camera for cell/door
transactions; it does not establish physical controller traversal or device
activation acceptance. Fargoth's original locked entry is not bypassed.

Private input SHA-256 before and after all seven inspections:

```text
Morrowind.esm  5c3c8c2cbd20e25901b59b3ece33d36b7ef0e3d60ad8d11828bcc61a5ead1647
Morrowind.bsa  3dcd5e6bfa08245521a53374bf733ee5c920df49103898a15aa31144ad64cf48
```

Only aggregate metadata and diagnostics are recorded. No original mesh, texture,
record payload or placement array is included in source or review evidence.
The input installation is opened read-only. Private inspected shader strings
are temporary GPL shader-source evidence; they are not archived as game data.

## Toolchain and reproducibility

Supplemental build: portable Zig 0.14.1 targeting Windows x86-64, CMake 4.2.1,
Ninja, portable Python and existing verified G3 desktop OSG/Bullet artifacts.
No system tools were installed. Genuine image/source dependencies were compiled
locally; the successful binary's SHA-256 and aggregate case reports are included
in review evidence. The imported provider is a CPU validation aid, never an
iPhoneOS compatibility substitute. Upstream OSG warnings are retained in logs.

The accepted suite logs are retained rather than repeatedly rerunning them.
`tools/validate.py` imports their outcomes, runs final G4 Python/source/shell/
preservation checks and binds the retained CPU evidence to the built binary.
`tools/inspect_private.py` is an opt-in reproducible private probe.

The older G3 validator's summary contains a generic `physical-g3: UNVERIFIED`
field because that tool cannot operate a phone. This does not supersede the
independent G3 physical acceptance recorded in G3-COMPLETION.md. The final G4
summary explicitly separates accepted G3 from unverified G4.

## Required next validation

Conditional independent source review is approved. This task is authorized to
stage the reviewed inventory plus focused corrections, commit, push and dispatch
`ios-openmw-world-device.yml`. Return the commit/run URL immediately after
dispatch; do not watch or poll the build.

Native CI must pass the Apple framework probe, accepted regression suites,
single-provider ARM64/double configuration audit, real configured-consumer
preflight, genuine compilation/linking, Mach-O platform/deployment/dependency
inspection, exact public bundle inventory, unsigned IPA creation and independent
reopening. All these **G4 native gates remain UNVERIFIED locally**.

After CI and installation over the current app, independent iPhone review must
confirm unobstructed genuine scenes, original textures/materials/terrain,
controller movement/collision, crossing neighborhood boundaries and an unlocked
interior/return transition. Export g4-render.json/log, screenshot/recording and
source provenance; inspect failures, GL errors, frame timing, memory, thermal
state, pause/resume and private input hashes. No swap/compile/package result
alone proves rendering, GPU completion or physical acceptance.

Water rendering/swimming, dynamic sky/weather, full engine ESMStore/CellStore
lifecycle, genuine engine character physics, actor/gameplay systems, exact
desktop lighting parity, Tamriel Rebuilt compatibility, peak memory and sustained
thermal behavior remain unsupported or unverified as detailed in ARCHITECTURE.md.

## Focused pre-Build #1 review validation

The corrected Windows targets and C++ device-header probe build successfully.
All 41 authored native cases pass, including concurrent notification counts and
closure, constructor unwinding, device-acceptance rejection with scene rollback
and successful retry, cache timestamp/ownership rules, maintenance-error isolation
and pending-worker shutdown. All seven private original-content inspections and
21 shader pairs pass again with unchanged original hashes. These are CPU tests;
the rejection callback models a device failure and does not execute an Apple GPU.

Twenty-six Python regressions cover the retained boundaries plus source contracts
for pre-publication shader acceptance, the OSG reference clock, serialized file
logging and revision-guarded footprint fields. The 206 accepted suite results
remain valid and their source files remain byte-for-byte unchanged.

The Apple footprint field follows the public
[XNU task_info header](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/task_info.h).
The OS-reported lifetime footprint peak and sampled maximum are separately named;
unsupported/failed kernel results stay null rather than becoming invented peaks.
The 418 terrain passes remain genuine prepared inventory, not measured draw calls.
