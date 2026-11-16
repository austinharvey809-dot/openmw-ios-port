# G4 Build #3 startup regression and proposed Build #4

Historical Build #4 investigation. Its genuine initialization-order correction
is retained. Build #4 subsequently exposed a host-test contextless GL assumption;
see [the proposed Build #5 correction](BUILD5-HOST-REGRESSION.md) for the current
findings and validation boundaries. G4 physical acceptance is still pending.

Investigated against `ios-port` commit
`e8ee8bfe740c09681004c91494826f4dc8d07610`. Changes remain uncommitted and
unpublished. G4 physical acceptance failed; accepted G1D/G2/G3 milestones remain
unchanged. No G5 work, dependency changes or new native workflow dispatch.

## Finding and confidence

A confirmed G4 initialization-order defect passes an uninitialized OSG extension
pointer into genuine OpenMW capability registration. The original G4 constructor
reproduces an access violation locally with a genuine current desktop GL context.
The corrected constructor completes. This is a strong evidence-supported cause
of the observed iPhone startup regression, not a claim to possess its crash stack
or OS termination reason. No iOS crash report has been supplied so far.

The last KHR_debug line is a successful checkpoint before the failing operation;
it does not establish a debug-callback failure.

## Actual device evidence inspected

The complete private local `C:/Users/austi/Downloads/g4-render.log` is 48,230 bytes,
SHA-256 recorded in the accompanying `device-and-binary-evidence.json`. It contains
**seven** sessions, extending the initial five-session report with attempts at
23:14:46 and 23:14:48 UTC. All seven identify the accepted source and end at
`KHR_debug registered: synchronous capture; existing driver message filters retained`.
No later scene completion or recorded exception appears. The source reports ANGLE
2.1.1 / revision 6ea96bcca6d7, ES 3.0 and the Apple A18 renderer.

The earlier `g4 launch log.txt` is a separate 5,054-byte truncated copy, ending
midway through the first extension list. It was superseded by the complete log.
No G4 JSON or crash report was available. The three rapid failures visible in the
screen recording are user/independent-review evidence; the recording was not
independently opened during this investigation because its local path was not supplied.

## Exact startup path and null pointer

1. UIKit creates the scene/view. `viewDidLoad` creates Evidence in memory and logs
   the new session; the original implementation writes no JSON here.
2. `sceneDidBecomeActive` calls `activate`, which allocates `Renderer` and calls
   its shared, accepted `start` implementation on the main thread.
3. ANGLE creates/makes current the ES3 context, validates identity and configures
   KHR_debug. The supplied log reaches this successful registration.
4. `flushDebug` drains copied records outside the GL callback; `setPhase` changes
   a mutex-protected enum. `Renderer::start` then constructs G4's `OSGScene`.
5. Its notification scope installs the synchronized handler. It resolves three
   GL functions and constructs `GraphicsWindowEmbedded`, which allocates an OSG
   State and assigns its context ID. It does **not** initialize extension procedures.
6. G4 sets state/attribute aliases and its DDS-decompression environment option.
   It then calls `SceneUtil::GetGLExtensionsOperation` before viewer construction.
7. In the exact pinned OSG, `State::get<GLExtensions>()` returns the stored
   `_glExtensions` pointer. It does not lazily allocate it. The pointer remains
   null until `State::initializeExtensionProcs()` sets it.
8. OpenMW `components/sceneutil/glextensions.cpp:57-58` inserts that null pointer
   into its observer set and calls `addObserver` through it. This is undefined
   behavior and produces an access violation in the release-library reproduction.

The original G4 constructor never reaches viewer allocation on this path. Its
asset-preparation dispatch occurs only after Renderer::start returns, so the
failure precedes ESM/BSA hashing, world indexing, model loading and genuine shader
program compilation. Replacing assets or changing lighting cannot fix this defect.

Pinned OSG sources were fetched read-only over verified HTTPS from the official
repository and compared byte-for-byte after LF normalization with the pinned
checkout. All three match:

- [State accessors](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/include/osg/State)
- [State initialization](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/State.cpp)
- [Embedded window initialization](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/include/osgViewer/GraphicsWindow)

Desktop OpenMW normally registers the capability operation as a viewer realize
operation in `apps/openmw/engine.cpp`. OSG's graphics-context current/realization
path initializes State first. G3 also calls `viewer->realize()` and never invokes
this new G4 capability operation before that initialization. The shared Renderer
and KHR_debug implementation are unchanged from the physically accepted G3 base.

## Native executable and linking evidence

The original unsigned IPA remains unchanged; SHA-256 is
`dd9ccdf27d92029c65b86ac44995e7fcd2bfdf06dc60bd236578d2e2af3530ec`.
Its application Mach-O UUID is **E3876A35-C11A-39AC-A24F-A0F28F857976**,
preferred text base `0x100000000`. Symbol-table inspection and limited ARM64 direct
BL decoding establish these actual original-binary addresses:

| Symbol / call | Preferred address |
| --- | --- |
| Renderer::start | 0x100008d40 |
| G4 OSGScene constructor | 0x100012438 |
| Constructor call to OpenMW capability operation | 0x100012730 |
| GetGLExtensionsOperation::operator() | 0x1001ff1d4 |
| Its call to osg::Referenced::addObserver | 0x1001ff20c |
| osg::State::initializeExtensionProcs | 0x100511ca0 |

The constructor's retained direct calls include the capability operation but no
State initialization. This agrees with source inspection. The parser does not
pretend to be a complete disassembler or infer indirect calls. Addresses require
the actual crash image slide before use against a device PC; a matching UUID,
crashed thread and exception/termination fields are still needed.

The completed artifact review verified the single OSG GLES3 provider, actual
ARM64/iPhoneOS binaries, exact dependency pins, all 1,377 public resource files,
ANGLE framework bytes and native dependency graph. DDS/TGA/BMP/PNG/JPEG/OSG/osg2
and 206 serializer registration symbols are retained. There is no observed
missing-symbol or platform/linking defect explaining these launches. Static
registration before main already completes far enough to permit ANGLE identity
logging. This does not establish runtime support for every registered type.

## Correction

New G4-only `src/GLCapabilities.hpp`:

- Rejects absent graphics state and absent genuine current GL context.
- Explicitly calls public OSG `State::initializeExtensionProcs()` while the
  application's real ANGLE context is current and the capability mutex is held.
- Checks the actual State extension pointer before passing it to the unchanged
  genuine OpenMW operation; failures identify their stage and cannot publish
  dummy capabilities or begin image loading.
- Retains genuine OpenMW registration and checks it completed. No upstream
  file, resolver, extension string, image decoder, provider or pin is replaced.

G4 OSGScene uses this helper before viewer construction. Shader acceptance,
resource validation, scene rollback, genuine terrain and world streaming are
unchanged. The recursive capability mutex already permits nested acquisition;
the investigation found no evidence that its existing nesting caused a deadlock.

## Startup diagnostics and missing JSON

Previously the first JSON write occurred in `beginPreparation` or at the end of
`activate`, both after Renderer::start. A native access violation in OSG construction
bypasses C++ exception handlers and prevents those calls. This path explains the
missing export; absence of a supplied JSON alone cannot prove no file ever existed.

The correction now writes an initial truthful `g4-render.json` from viewDidLoad,
before any Renderer allocation/GL bootstrap. Parser/geometry and shader success
remain false until their real gates pass. Source commit and bound-metadata hash
are included even if full preparation never starts.

An independent `Documents/g4-startup.json` journal records sequence, session,
stage, monotonic uptime, main/background thread and sampled physical footprint
where available. It uses atomic JSON replacement and at most 128 events; truncation
is explicit. Existing text logs remain append-only. The journal is independent of
the worker's preparation report, avoiding concurrent access to the main Evidence
dictionary. All file writes and journal mutation use the existing diagnostic mutex.
Worker checkpoints carry an immutable session token captured before dispatch;
retired workers can append tagged text but cannot overwrite a newer session's journal.
JSON errors are counted/reported instead of silently ignored. These are completed
atomic file writes, not an assertion of power-loss-safe storage.

Checkpoint groups cover initial export; Renderer allocation/start; identity and
KHR registration; notification setup; resolver/window creation; extension-procedure
initialization and OpenMW registration; viewer creation; dispatch/worker entry;
provenance, private hashes, world index/resources/session; main completion/attach;
display-link setup; actual initial shader acceptance and first OSG frame.
The shared accepted Renderer/debug source is not edited to add these checkpoints.

Recoverable Objective-C exceptions at activation/preparation boundaries now record
their name/reason as failures. Existing C++ failures remain failures. No signal
handler attempts unsafe recovery from access violations, assertions or termination.
The diagnostic path does not invoke GL/OSG or recursively call Log while holding
the file mutex. Actual Foundation/Objective-C++ execution remains an Apple gate.

## Other mechanisms investigated

- **KHR_debug reentrancy/lifetime:** the unchanged callback copies bounded bytes
  under its own mutex. It does not log, allocate record storage or invoke GL/EGL.
  Drain formatting/file I/O occurs after releasing that mutex and after GL returns.
  Phase updates hold no lock across GL calls. Renderer detaches while current and
  keeps callback storage alive through context destruction. No defect was found
  that justifies disabling synchronous capture or changing driver filters.
- **Notifications/threading:** startup is main-thread code; the resource worker
  has not been dispatched at the identified fault. Notification closure and cache
  maintenance concurrency regressions still pass. No evidence supports a resource
  loading race as the primary cause of this specific failure path.
- **Memory/watchdog/assertions:** no device termination report was available.
  Early sampled footprints/checkpoints improve the next investigation, but do not
  establish Jetsam, watchdog or assertion as the current cause. The local release
  access violation is actual evidence; its Windows code is not an iOS signal claim.
- **OSG lifetime:** a retired embedded window can leave genuine extension objects
  alive in OSG's shared context caches. The local probe observed this. The weak
  OpenMW observer is not itself an owning reference; an immediate empty global
  registry after dropping a window is not a valid test requirement. No unproven
  global-cache teardown change was introduced.

## Executed regressions and limits

| Check | Outcome |
| --- | --- |
| Original capability operation, genuine release G4 library | Child exits 0xC0000005 with a null initial extension pointer |
| Original full G4 constructor with real current GL | Child exits 0xC0000005 |
| Corrected headless registration guard | Explicit stage-specific rejection, exit 0 in test |
| Corrected capability initialization with real current GL | Successful registration and repeated initialization |
| Corrected actual G4 OSGScene constructor | Completes; world/shader/frame success remains false/zero |
| G4 native authored harness | All 42 pass: 27 positive, 15 specifically diagnosed negative cases |
| G4 Python | All 42 pass, no skips |
| Native registration runtime and device C++ header target | Pass on supplemental Windows provider |
| Workflow shell/Python syntax, source whitespace, Python AST | Pass |
| Accepted/upstream source lock | All 560 unchanged |
| Original snapshot and Build #15 | All 4,139 unchanged, including nine Build #15 files |
| A-E/F/G0B/fixtures/OSG preservation audits | Pass; retained 206 accepted-suite results remain source-preserved |
| Corrected Apple Objective-C++ compile/link/package | UNVERIFIED; no Apple SDK on this Windows machine |
| Corrected iPhone launch/rendering/streaming | UNVERIFIED; requires a separately approved native build and physical test |

The local current-context probe uses a hidden window with desktop NVIDIA OpenGL
4.6 and the actual pinned shared OSG/G4 release provider. It is genuine execution
of the relevant constructor/helper, not ANGLE/iPhoneOS or original-world rendering
acceptance. An initial debug-compiled reproducer also reported the null member
call directly at OpenMW glextensions.cpp:58. Deliberate crash probes are isolated
child processes stored only as review evidence, never application code or CI
positive tests. The formal new headless regression rejects unsafe inputs cleanly.

### Final pre-publication validation reconciliation

Independent review found seven CMake-related skips in the packaged Python log,
despite the no-skips result stated above. That log came from a later direct
`validate.py` invocation in the same Windows workspace, without the temporary
`OPENMW_TEST_CMAKE` and PATH settings used by the earlier complete run. It
overwrote the earlier log. The seven skipped checks were five conflicting-target
subtests plus the host-processor and explicit-iOS-processor checks. An exit-zero
unittest result alone did not establish full coverage.

The final pre-commit suite was rerun with the existing portable CMake 4.2.1
explicitly selected by absolute path and available on PATH. All 42 Python tests
completed with **zero skips**; all seven CMake checks executed. The final evidence
is retained separately in `artifacts/build4-final/validation/g4-python.log`, with
the reviewed skipped log preserved in `artifacts/build4-final/`. Publication is
gated on both exit zero and an explicit zero-skips check. The reviewed ZIP remains
unchanged. No application, dependency, workflow or test implementation changed
to reconcile this discrepancy.

The new native case proves the real embedded State starts uninitialized, missing
state/current-context inputs fail specifically, and rejected paths publish no
fake capabilities. Python contracts guard initialization order, early truthful
JSON and unchanged deferred GL-debug logging. They do not pretend to execute UIKit.

CI previously missed this because header/consumer checks only compile, native
packaging only inspects products, and CPU world tests never constructed the
device bootstrap. The new headless case is automatically included in the existing
strict G4 native suite; no workflow change or duplicate provider build is needed.

## Exact proposed source changes

All paths are under `experiments/ios-openmw-world-smoke/`:

| File | Change |
| --- | --- |
| src/GLCapabilities.hpp | New genuine initialization/registration helper and guards |
| device/src/OSGScene.hpp | Use helper; scoped startup/first-frame checkpoints |
| device/src/main.mm | Early render JSON, bounded startup journal, stage/memory diagnostics and Objective-C failure reporting |
| tests/world_check.cpp | Real pinned-OSG headless precondition regression |
| tools/fixtures.py | Register the additional authored native case; existing fixture bytes unchanged |
| tools/test_g4.py | Three focused startup/debug diagnostic contracts |
| README.md | Current failure/correction status and report link |
| STARTUP-REGRESSION.md | This report |

No upstream/completed milestone, Build #15 file, dependency pin, workflow,
application identifier or private game file changes. Documents/Model compatibility
and controller-first gameplay remain. Review evidence, crash probes and temporary
binaries stay ignored and must not be staged. No new dependencies are required.

## Proposed Build #4 and physical follow-up

Stop for source review first. After explicit approval, retain all current native
preflight/provenance/packaging gates; publish only the reviewed G4 changes, dispatch
the existing manual workflow and return its run URL immediately without polling.
No build has been dispatched during this investigation.

After a successful reviewed native run, install over the existing application
with the same effective signing identity; preserve Documents/Model. First test
three cold launches, collecting **g4-startup.json, g4-render.json and g4-render.log**
from each before the next launch overwrites snapshots. Confirm capability
initialization completes before preparation, followed by genuine shader acceptance,
an advancing OSG frame count and a visibly rendered original exterior. Only then
continue the existing streaming/door/lifecycle/controller/performance checklist.

If any launch still terminates, preserve the journal's last stage, log, source
commit/session and original recording. Obtain the iOS crash .ips or JetsamEvent
if available, including termination reason, crashed thread and binary image UUID;
match the UUID to the actual installed build, not automatically to Build #3.
[Apple's crash/device-log guidance](https://developer.apple.com/documentation/xcode/diagnosing-issues-using-crash-reports-and-device-logs)
explains why these reports are needed to distinguish exception and termination
mechanisms. Do not infer one solely from a missing report.

This correction is ready for independent source review. Apple compilation and
physical G4 acceptance of the corrected implementation remain pending.
