# G1B: unified iPhoneOS decoded-geometry renderer

Prepared for manual source review. **This new device build, packaging and runtime
are unverified.** No shader execution, visible triangle, GPU completion,
lifecycle recovery or physical-device acceptance is claimed.

## Prerequisites and preserved scope

[G1A Build #1](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43144248999)
at `fa3451ab825750f241b37ef6021c6b7ff48724f5` succeeded. Read-only GitHub job/log
inspection confirmed 14 G1A Python tests, 46 G0B tests, 25 G0C tests and the
native macOS ARM64 geometry test, including source equivalence, parser release,
20 geometry negatives and all six genuine parser cases. This is host structural
evidence, not this new device build's result. G0C physical-phone parsing and its
independent screenshot/export review remain recorded in the unchanged
[completion/graphics plan](../../../docs/ios-port/g0c-completion-and-g1-plan.md).

All completed A-F/G0B/G0C/G1A files remain unchanged. G1B lives in this new
`device/` directory. The sole addition outside it is the required separate
manual workflow. No original Morrowind installation or private assets are used.
All resources are the existing, validated synthetic fixtures. This milestone
does not implement game rendering, materials, textures, animation or gameplay.

## One provider and genuine geometry

The device CMake entry includes `cmake/provider.cmake`, adapted from the committed
version-2 graphics baseline at
`8799e90148c3ea1985b2547fa8e9b31be19b45c2`. It adds the OSG source exactly once.
The static viewer closure remains osgViewer, osgGA, osgText, osgDB, osgUtil, osg
and OpenThreads; windowing is None and plugins are disabled. EGL/GLES symbols
come from the verified dynamic ANGLE Metal frameworks. The original resolver,
header checks, native type probe and three source-scoped KHR label aliases are
retained. No version-3 observer is copied, compiled or imported.

The clean pinned OSG audit checkout remains separate from a future scratch
renderer checkout. Only the recorded original version-2 four-file overlay is
applied to that scratch copy by the copied baseline tool. No upstream source or
existing dependency checkout was edited during this preparation.

The genuine NIF source list comes from the unchanged G0B manifest: twelve NIF
translation units plus hash.cpp/MurmurHash3.cpp. D/E ESM/BSA/VFS targets are added
once; overlapping A/B/C archives are not added. The unchanged verified Bullet
recipe supplies BulletCollision/LinearMath with double precision. G1A's actual
`GeometryAdapter.cpp` is compiled directly, without modifying or replacing it.
G0C's unchanged in-process six-case NIF probe is also compiled; its OSG provider
and application are not imported.

The full D configuration-switch set is applied before OSG configuration. The
genuine upstream pthread-mutex atomic fallback avoids a device try_run/OSAtomic
assumption. The single actual generated include tree is prepended to all seven
OSG targets, D/E, parser, adapter and app consumers, ahead of D's math-only tree.
All five genuine generated headers are required. The configured audit checks
their hashes, precision switches, GLES3 headers, C++20 consumers, Bullet macros,
include ordering, device settings and duplicate OSG source compilation.

Pins are unchanged and recorded through G1A's lock and new source-origin ledger:

| Dependency | Identity |
| --- | --- |
| OSG | `9b384d5439977784e5cd250ff8ff7966928ddd27` |
| ANGLE | `6ea96bcca6d7f05199f5565c6d5c4722af7269da` |
| depot_tools | `816da11f80777dcf8c10bdaa84df18450dcba12a` |
| Bullet | 3.25, existing `https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz` |
| Bullet SHA-512 | `7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4` |
| Platform | AppleClang, iPhoneOS ARM64 only, minimum iOS 18.0; C++20/Objective-C++20 consumers |

## Runtime path and ownership

`LoadGeometry()` checks compiled build metadata and all twelve fixture snapshots,
executes all six genuine parser cases, then calls the unchanged G1A
`readResource()`/`copyGeometry()` adapter. Thus the ESM STAT/MODL selects the
BSA/VFS resource, its SHA-256 is checked before genuine NIF parsing, and actual
decoded arrays populate the owned OSG geometry. It checks the canonical geometry
digest against G1A's independent fixture expectation and releases parser records
before returning the owned scene data. It rechecks all input snapshots afterward.
No parser work runs in the display callback.

The new `OSGScene` attaches that exact owned Geode. It creates only diagnostic
colors, not positions or indices. A fixed, front-facing camera fits the decoded
bounds and actual EGL pixel aspect; culling is explicitly off for two-sided
unlit visibility. The two colored ESSL300 shader strings and attribute/uniform
ABI are unchanged from the committed version-2 scene: osg_Vertex 0, osg_Color 3,
osg_ModelViewProjectionMatrix, OSG matrix uniforms and vertex aliases. It checks
the real per-context program link result after traversal and retains the log.

`AngleRenderer.hpp` is the exact Renderer class extracted from the committed
version-2 main, with a header guard added. It retains explicit Metal EGL display
selection, application-owned ES3 currentness, GraphicsWindowEmbedded /
SingleThreaded viewer, exactly one external swap, bounded raw KHR/OSG diagnostics,
pause/drain/unbind and context-aware teardown. The new UIKit controller adapts
the original activation, suspension, resize and controller-button handling; only
the diagnostic clear toggle remains. A clear fallback or exception is recorded
as a failure/unavailable scene, never a rendering PASS.

Future device exports are `g1b-render.json` and the diagnostic `g1b-render.log`.
They record a session, machine/OS, combined source/dependency/fixture provenance,
six parser results, actual geometry identity/digest/counts, parser release,
unchanged inputs, runtime GL identity, shader-link status, errors, frames and
swaps. The overlay includes the session prefix. Physical rendering acceptance
always remains explicitly UNVERIFIED pending independent screenshot/export
review; frame/swap counters cannot establish visible rendering or display FPS.
GPU-completion and lifecycle-acceptance fields remain unverified.

## Binary, bundle and IPA gates

CMake exports actual link-check executable, app executable and bundle paths via
target generator expressions. The workflow checks regular executable files,
not just an app directory or assumed product path. The device link-check reuses
the genuine G1A native test source as a compilation/link target; CI never tries
to execute that iPhoneOS binary on the Mac.

Preparation verifies clean reference sources, the scratch v2 overlay and the
exact validated ANGLE package. It prepares resources only in build/artifact
storage: twelve fixtures, ANGLE frameworks and complete notices, OpenMW/OSG/
OpenThreads/Bullet notices, dependency manifests and all five generated headers.
Combined metadata includes the actual source commit, G1A proof commit, baseline
origins, source/adapter/shader hashes, dependency pins, raw fixture snapshots and
resource hashes. Its digest is compiled into the application and required in
the packaged executable. No source fixture or dependency is changed.

The new packager reuses an isolated instance of the preserved ANGLE Mach-O,
SDK TAPI/linker, path, collection, otool and ZIP-writing primitives. It adds:

- Exact G1B identity, inline scene/platform/deployment settings and file inventory
  equal to prepared resources plus Info.plist and the executable.
- Exact prepared bytes, original fixtures, provenance/notice hashes and executable
  metadata contract; rejection of signing/provisioning files, symlinks, static
  archives and executable resources.
- ARM64 device Mach-O, exact app minimum 18.0, compatible framework minimums,
  command alignment/extent, unambiguous platform metadata and unsigned state.
- Exactly the two recorded ANGLE framework roles, matching install names,
  permitted runpaths, resolved/reachable dependency graph and no alternate
  OpenGLES/OpenGL/Vulkan/GL4ES provider. Real selected-iPhoneOS-SDK checks remain
  mandatory through every CLI phase; policy tests alone may omit an SDK and
  then explicitly report availability as unchecked.
- Actual otool dependency comparison for the full bundle; strict ZIP CRC,
  duplicate/root/type/mode checks and no empty/unexpected directories.
- IPA validation before atomic publication, then a separate reopening command
  that re-runs full native, resource and SDK validation.

These checks are prepared source, not successful G1B packaging evidence.

## Separate manual workflow and tests

[ios-openmw-nif-render-device-smoke.yml](../../../.github/workflows/ios-openmw-nif-render-device-smoke.yml)
has no push/PR trigger and has not been dispatched. Its jobs are sequential:

1. `host-regressions`: preservation and new policy tests, unchanged G1A/G0B/G0C
   tests, verified Bullet acquisition, native ARM64 G1A build and its real
   ownership/20-negative/six-parser-case execution.
2. `angle-device`: only after host success, build the exact locked ANGLE Metal
   graph, validate its actual iPhoneOS framework products/SDK dependencies and
   preserve a dependency artifact.
3. `iphoneos-geometry`: only after both jobs succeed, independently revalidate
   that artifact; prepare a separate pinned v2 OSG renderer and Bullet; configure
   a single provider; build/inspect the native geometry executable; build UIKit;
   validate the complete bundle; package; independently reopen.

Every gate is fail-fast. Failure diagnostics retain toolchain/configuration,
compiler/linker/package logs, actual binaries when available, compile commands,
prepared provenance/resources, separate gate outcomes and evidence checksums.
No job signs, installs or launches the application or declares physical success.

Sixteen new offline tests use synthetic Mach-O/SDK data for policy checks:
selected-SDK helper invocation, architecture/platform/deployment/signatures,
runpaths, forbidden/unresolved providers, exact inventory/resource types, app
identity, reachable ANGLE roles, compiled metadata and independent IPA reopening.
Source contracts check preserved origins, a single provider, exact colored
shader ABI, external lifecycle and mandatory manual gates. Synthetic test data
is never native execution or device evidence.

## Validation performed and remaining risks

Local Python cannot launch (`The file cannot be accessed by the system` from
the WindowsApps alias); CMake/C++/Apple tools are unavailable. New Python tests
and syntax, configured build audits, iPhoneOS compilation/linking, SDK inspection,
bundle validation and IPA packaging/reopening remain **unverified**. There is no
observed G1B compiler/linker result to report. No dependency download, native
build, IPA creation or device installation was performed locally.

Available PowerShell checks verify the 204 frozen completed-source files,
including every original G1A file; 53 A-E entries; 18 F files; G0B/G0C and source
closures; all fixture inventories/hashes; unchanged Bullet/ANGLE pins; clean
pinned OSG; historical v2 copies; all nine Build #15 hashes; and the session's
228 pre-existing protected files. Workflow shell syntax, new-file/documentation
and Git whitespace checks pass. HEAD/index remain unchanged.

The outstanding technical risk is the first native combination of the real
parser and viewer under this single generated GLES3 configuration. Generated
includes, archive linkage, framework closure, Unix Makefiles bundle resource
placement and actual shader/runtime behavior must pass their real gates; no
speculative dependency updates or relaxed checks substitute for that evidence.
After native source/build review, physical triangle visibility, diagnostics,
background/foreground recovery and matching session screenshots/exports require
separate user-authorized device validation. Real Morrowind models and full
gameplay remain outside this milestone.

Stop for manual review before staging, publication or workflow execution.
