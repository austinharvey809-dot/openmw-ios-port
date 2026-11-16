# G4 proposed Build #5: native host startup test correction

Review base: `226a51d4f199abe4886f7d8b304de7a4da8ae154`, `ios-port`.
Prepared 2026-11-15, America/Chicago. All changes remain uncommitted; no push,
workflow dispatch or G5 work. G4 physical acceptance remains unverified.

## Conclusions and evidence limits

The newly introduced headless case invokes a context-dependent GL function while
no real GL context exists. That is an invalid portability assumption in the test
and in the helper's context-absence detection. A dummy embedded OSG window does
not create or bind a native context. A Windows null return from glGetString is
not a portable native-context query.

The correction explicitly queries the backend's current context handle first.
It retains the genuine OSG-before-OpenMW initialization order, null guards and
durable startup diagnostics. The headless case is strengthened and still runs;
it is not skipped or replaced with fabricated capabilities.

**The exact macOS terminating instruction and signal cannot be recovered from the
available evidence.** The old Python wrapper discarded the child status and
printed only stderr, which was empty. There is no uploaded crash report or failed
G4 executable. The contextless GL query is an identified unsafe boundary consistent
with the failure, not an asserted Apple crash stack. The new phase markers and
lossless subprocess records localize any remaining platform-specific problem.

## Independently inspected Build #4 evidence

[Completed run](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43777593217),
host job `133007320781`, artifact `14187324706`:

```text
openmw-g4-host-43777593217-1.zip
SHA-256 4850aa6056ca52d8d1ff6c5bbb29fb53759c5b46e24d380bdc597f00aaf09b80
4,000,462 bytes
```

The downloaded ZIP digest matches GitHub's artifact metadata and source commit.
ZIP CRCs, exact SHA256SUMS inventory and all 223 inner payload hashes pass.
The complete job log and uploaded CTest evidence agree:

- Host compilation/linking and G1D/G2/G3 native tests passed.
- G4 static reader/serializer registration passed.
- All 42 Python tests passed in that macOS run without skips.
- `g4-genuine-world-regressions` failed in `startup-capabilities` after about
  1.87 seconds. The old runner reported `ValueError: startup-capabilities:`.
- CTest exit 8 denotes test failure; it is not the native child's exit code.
- Completed-job metadata confirms ANGLE and iPhoneOS jobs were skipped.

The original runner checked cases sequentially. Reaching startup implies earlier
cases passed its checks, but their individual records were lost because results
were written only after the entire suite succeeded. Later cases were not reached.
No unknown child status is relabeled as SIGSEGV, SIGABRT or an ordinary exit 1.

## Pinned lifecycle and platform assumptions

The genuine pinned `GraphicsWindowEmbedded` constructor creates a State, assigns
an OSG context ID and event machinery. Its `valid`, `isRealizedImplementation` and
`makeCurrentImplementation` methods assume an external owner supplies a valid
native context. They are not proof of one and must not be used to manufacture it
in a headless test.

OSG State starts with a null extension pointer. State initialization creates real
capabilities; OpenMW's operation registers an observer on that genuine pointer.
The Build #4 order fix remains necessary. It is not reverted to address a host test.

The old test exercised creation, uninitialized-pointer rejection, a raw version
query without a context, then destruction. It lacked phase logging, so the
available CI output does not identify which operation terminated the child.

The pinned GraphicsContext base destructor calls `close(false)`. That path releases
CPU State/cache ownership and context-ID bookkeeping without the `makeCurrent`
and GL initialization branch used by `close(true)` on an allegedly realized window.
The new test explicitly exercises this same contextless close path, checks State
retirement, destroys the actual wrapper, recreates it and checks context-ID reuse.
It does not suppress destruction, leak the test object or allocate dummy extensions.

Source references, all at OSG revision `9b384d5439977784e5cd250ff8ff7966928ddd27`:

- [Embedded-window contract](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/include/osgViewer/GraphicsWindow)
- [GraphicsContext current/close/destructor behavior](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/GraphicsContext.cpp)
- [State initialization/destruction](https://raw.githubusercontent.com/openscenegraph/OpenSceneGraph/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/State.cpp)

The original OpenMW implementation is unchanged at
`components/sceneutil/glextensions.cpp`; preservation checks cover its exact bytes.

## Safe context checks and production boundary

`initializeGLCapabilities` now requires an explicit native-context predicate.
It validates graphics State, checks that predicate, then queries the genuine GL
version, initializes actual OSG procedures and registers OpenMW capabilities.
An empty/false predicate fails before GL dispatch or registration. The callback
does not inject capability values; every successful capability object still
comes from the real current driver through pinned OSG.

The device frontend implements the predicate with ANGLE's
`eglGetCurrentContext` and `eglGetCurrentDisplay`. OSGScene checks it before
resolver/window creation and again before initialization. Shared Renderer still
owns/binds the EGL context and validates ANGLE/Metal identity. No desktop GL or
EAGL provider is introduced into the iPhone application.

The host test uses `wglGetCurrentContext` on Windows and `CGLGetCurrentContext`
on macOS, checking the calling thread's native handle without issuing a GL
command. A GLX adapter preserves desktop Linux source support; it was not tested
locally. The iPhone renderer does not compile these host-only adapters.

Primary API references:

- [Microsoft WGL current-context query](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-wglgetcurrentcontext)
- [Apple capability-query sequence](https://developer.apple.com/library/archive/documentation/GraphicsImaging/Conceptual/OpenGL-MacProgGuide/opengl_general/opengl_gen_tasks.html)
- [EGL context-query contract, section 3.7.4](https://registry.khronos.org/EGL/specs/eglspec.1.4.pdf)

The Windows experiment confirms that the old raw no-context GL_VERSION call
returns null on this machine. It also confirms that the original Build #4 Windows
startup case still passes. Neither observation establishes macOS or iPhoneOS
safety. No current-context GL call is used to discover context absence now.

## Native gate and assertion coverage

`StartupChecks.hpp` contains the same genuine checks used by both the full
`startup-capabilities` world case and `openmw-g4-startup-check`:

- A real native context is absent, and no OpenMW capabilities are pre-published.
- Fresh real embedded State exists with an uninitialized extension pointer.
- Registration rejects that null pointer and rejects missing graphics State.
- Native-context probing occurs exactly once; false and empty predicates fail
  before any initialization trace, state mutation or observer registration.
- Missing graphics input still fails specifically.
- Explicit contextless close retires State; destruction publishes no capabilities.
- A second full creation/rejection/destruction cycle reuses the retired context ID.

There are 29 native assertions, with flushed stderr checkpoints before/after
native query, construction, rejection, close and destruction. The full world case
continues through genuine authored CELL/LAND/NIF/BSA processing afterwards.
Its fixture bytes and the 42-case inventory are unchanged.

The small CMake executable compiles only the test plus the unchanged genuine
OpenMW capability-registration translation unit. It links the existing seven-library
OSG viewer closure, not the full G4 world/Bullet/image closure. The workflow builds
and executes it immediately after configuring/auditing the existing G4 shared
provider, before the full G4 application regression build. Its OSG objects are
reused by that build. It does not add another OSG provider.

This is earlier than the full G4 world build, not before all existing baseline
OSG prerequisites. No large CI redesign or acceptance-gate removal was attempted.
The accepted suites, static registration, real dependencies, Apple SDK preflight,
single-provider/double-precision checks, linking and IPA validation remain intact.

## Subprocess evidence correction

The runner now atomically persists a RUNNING row before launching each child,
then its captured outcome before parsing success or asserting rejection. On
failure it saves the failed row together with every completed prior case.

Records include command, platform, elapsed time, raw exit code, hexadecimal status,
POSIX signal number/name where appropriate, timeout/spawn errors, full text streams
and base64 copies of original output bytes. Windows NTSTATUS values are not
misclassified as POSIX signals. Timeout evidence leaves unavailable exit/signal
values null instead of inventing a kill code. Error messages include the status,
stream excerpts and retained evidence location even when stderr is empty.

World cases retain before/after exact input SHA-256 inventories and expected
exit/diagnostic contracts. Crashes, timeouts, unrelated failures, malformed PASS
JSON, mutations and unexpected files cannot satisfy a negative rejection gate.
Ordinary negative cases still require exit 1 and their exact expected message.

CTest writes `g4-startup-case.json` and incremental `g4-world-cases.json` into the
actual build directory. The always-run upload retains them on failure, along with
phase/build logs, LastTest.log and link/compile evidence. It now also retains the
two G4 host executables for future symbol/UUID inspection. These are public
authored-test products; no proprietary game data is present in CI.
Separate configure/startup gate outcomes distinguish an early failure from a
skipped full build. Packaging gates are unchanged.

## Executed local validation and limitations

| Validation | Result and actual scope |
| --- | --- |
| Windows early native gate | PASS, 29 assertions; CTest about 0.29 seconds |
| Windows full native world cases | All 42 pass, including the strengthened startup case and all 15 strict negatives |
| Windows static registration/runtime | PASS |
| G4 Python | All 52 pass with zero skips using explicit portable CMake 4.2.1 |
| Device C++ header target | Compiles against genuine supplemental desktop provider |
| Genuine current-context capability initialization | PASS on desktop NVIDIA OpenGL 4.6, including repeated initialization |
| Actual corrected G4 constructor with real desktop GL | Completes; no world/shader/frame success falsely reported |
| Actual G4 constructor without native context | Explicit stage-specific rejection before GL dispatch |
| Original null-registration fault | Still reproduces 0xC0000005 in isolated Windows child; new capture retains status/streams |
| Runner unit coverage | Partial persistence, simulated POSIX signal, signed/unsigned NTSTATUS, non-UTF8 bytes, timeout, spawn failure, malformed success, mutation and strict rejection |
| Actual silent child | Exit 23, empty stdout/stderr correctly retained |
| Workflow shell/embedded Python and Python AST | PASS |
| Preservation | All 4,139 protected snapshot files and 560 accepted/upstream entries unchanged, including nine Build #15 files |
| A-E/F/G0B, original fixtures and pins | PASS; 206 accepted-suite results retained without changing their sources |
| Git whitespace and exact source inventory | PASS |
| Corrected macOS ARM64 execution | UNVERIFIED locally; needs reviewed native CI |
| Corrected iPhoneOS Objective-C++, linking and packaging | UNVERIFIED; Build #4 skipped these jobs |
| Physical G4 launch/world rendering | UNVERIFIED; no new IPA/device acceptance |

The new current-context experiment is genuine Windows desktop execution using
the pinned provider and actual G4 constructor. It is not ANGLE/Metal execution or
a substitute for Apple testing. CGL source selection and linkage have been
reviewed, but no macOS runtime, Linux runtime or Apple SDK is available here.
Mocked subprocess outcomes test reporting only and do not claim native signal
reproduction on macOS. The deliberate fault executable is an isolated local
evidence probe, not an application path or a CI positive test.

## Exact proposed source inventory

| Repository path | Purpose |
| --- | --- |
| .github/workflows/ios-openmw-world-device.yml | Early shared-provider native gate and retained failure evidence/products |
| experiments/ios-openmw-world-smoke/CMakeLists.txt | Small startup target/CTest and explicit incremental report paths |
| experiments/ios-openmw-world-smoke/src/GLCapabilities.hpp | Mandatory native-context precondition before GL dispatch |
| experiments/ios-openmw-world-smoke/device/src/OSGScene.hpp | Use/check device context predicate; preserve initialization order |
| experiments/ios-openmw-world-smoke/device/src/main.mm | Real ANGLE EGL current-handle predicate; durable diagnostics unchanged |
| experiments/ios-openmw-world-smoke/tests/StartupChecks.hpp | New shared genuine headless assertions and lifecycle markers |
| experiments/ios-openmw-world-smoke/tests/startup_check.cpp | New lightweight executable entry point |
| experiments/ios-openmw-world-smoke/tests/world_check.cpp | Invoke the same assertions in the retained world case |
| experiments/ios-openmw-world-smoke/tools/run_cases.py | Incremental, lossless failure records and strict startup runner |
| experiments/ios-openmw-world-smoke/tools/test_g4.py | Runner failure regressions and native-context/gate contracts |
| experiments/ios-openmw-world-smoke/README.md | Current status and report link |
| experiments/ios-openmw-world-smoke/STARTUP-REGRESSION.md | Historical-status pointer; original startup diagnosis retained |
| experiments/ios-openmw-world-smoke/BUILD5-HOST-REGRESSION.md | This report |

No dependency revision/checksum, upstream implementation, completed milestone,
Build #15 edit, application identifier, original game file or validated fixture
changes. Documents/Model import compatibility and controller-first UI remain.
Review evidence, dependency sources and temporary executables remain ignored.
The source ZIP contains selected text/JSON evidence and reproducer source, not
game assets, dependency archives, temporary binaries or an IPA.

## Handoff

Stop for independent source review. After approval, a later authorized task can
commit/push the reviewed inventory and dispatch the existing manual workflow,
returning its run link immediately without waiting or polling.

Build #5 must demonstrate the early headless gate on actual macOS ARM64, all
retained regressions, then ANGLE and the real iPhoneOS compile/link/package gates.
If a child still fails, the new exact status, phase markers and partial reports
must drive the next investigation. Do not infer success from Windows-only results.
Only after native review should the unchanged app identity be used to install
over the current phone app and retest launches, startup JSON and the actual world.
