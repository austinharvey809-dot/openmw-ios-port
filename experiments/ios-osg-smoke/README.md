# OSG over ANGLE/Metal: isolated iPhone scene proof

Status: implementation prepared, **not compiled or run on iOS**. The separate
`ios-angle-smoke` app is the user-confirmed physical-device baseline (workflow
#12). Its source, controller code, packaging scripts and workflow are unchanged.
This experiment needs its own successful CI build, IPA validation and iPhone run.

## Architecture and scene

```text
UIKit + CADisplayLink + GameController
  -> ANGLE EGL ES3 context / CAMetalLayer, explicitly Metal
  -> osgViewer::Viewer::frame(), SingleThreaded
     -> osg::MatrixTransform -> osg::Geode -> osg::Geometry
     -> OSG update, cull and draw traversal -> ANGLE GLES3 -> Metal
  -> one application-owned eglSwapBuffers
```

The scene is a rotating colored cube (24 vertices, 36 indices), a perspective
camera and depth testing. There are no game assets, file-loaded scenes, fonts,
image decoders or manually drawn GL cube calls. OSG owns VBO/VAO geometry and
shader application; the application owns the native window, EGL context and swap.
`GraphicsWindowEmbedded` supplies OSG's State/context ID and deliberately performs
no native currentness, window creation or swap. That is safe here only because
the UIKit thread binds EGL before setup/frame, all OSG traversal is single-threaded,
and callbacks stop before suspension. Do not reuse this assumption with a threaded
viewer or multiple contexts without a real context-provider adapter.

ESSL 3.00 shaders explicitly consume `osg_Vertex`, `osg_Color` and
`osg_ModelViewProjectionMatrix`. The State enables aliasing and matrix uniforms,
and explicitly selects noncompact alias locations (vertex 0, color 3), matched
by Program attribute bindings. No default/fixed-function shader conversion is
assumed. The first traversed program must actually link; its info log is exported.
Geometry uses triangles/VBOs/VAOs, not display lists or immediate mode. No GL4ES,
desktop GL, Apple OpenGLES, Vulkan or software backend is introduced.

## Exact fork audit and bounded adaptations

The engine pins [OpenMW/osg at 9b384d5439977784e5cd250ff8ff7966928ddd27](https://github.com/OpenMW/osg/tree/9b384d5439977784e5cd250ff8ff7966928ddd27)
in `extern/CMakeLists.txt`. This experiment keeps that revision, GLES3 and the
existing ANGLE/depot_tools pins. The fork's current branch README is background,
not evidence that the pinned iOS configuration works unchanged.

Verified source at that revision:

| Source | Finding and action |
| --- | --- |
| `CMakeLists.txt`, `OPENGL_PROFILE` | `GLES3` enables `OSG_GLES3_AVAILABLE`, removes fixed-function features. Configure only this profile, never GL2/GLCORE. |
| `CMakeLists.txt`, iPhone branches | `OSG_BUILD_PLATFORM_IPHONE=ON` assumes Xcode.app, SDK 10.2, minimum 7.0, mixed device/simulator defaults, Apple's OpenGLES and forced IOS windowing. Set device-only SDK/ARM64/minimum 18.0 explicitly, and overlay the three hard-coded provider/window/SDK assignments. |
| `src/osg/GL.in` and root header settings | Apple defaults to `<OpenGLES/ES3/gl.h>`. Set the documented CMake cache header strings to ANGLE `<GLES3/gl3.h>` / `<GLES3/gl3ext.h>`; pass its include path to compile checks. No GL.in patch is needed. |
| `src/osg/GLExtensions.cpp` | Apple branch uses global `dlopen`/`dlsym`; replace provider selection only for this experiment with `eglGetProcAddress`, including core-function availability probes at runtime. No global resolver fallback. |
| `include/osgViewer/GraphicsWindow` | Embedded window creates State/context bookkeeping and has no-op current/swap implementations. Use only with the already-current external EGL context. |
| `src/osg/State.cpp`, `include/osg/Program` | Default aliases can be compact; select the explicit noncompact mapping. Enable supplied matrix uniforms and inspect the actual per-context program link status. |
| `src/osgViewer/CMakeLists.txt` | Viewer links osgGA, osgText, osgDB, osgUtil, osg, OpenThreads. osgText remains a transitive dependency even with no text drawn. |

Only **two fetched OSG files** are changed: three exact CMake replacements and
one extension-resolver branch/include. `prepare_osg.py` verifies original SHA-256s
before any write, and `check_osg_source.py` recomputes expected overlays from
pinned Git blobs, verifies HEAD and rejects unrelated tracked differences.
`data/osg-lock.json` records all pins, source hashes and overlay version. These
are explicit source adaptations, not claims of stock fork compatibility. They
are never applied to the engine's `extern` checkout or any working experiment.

Seven OSG libraries are built statically: OpenThreads, osg, osgUtil, osgDB, osgGA,
osgText and osgViewer. The top-level OSG project is configured with `EXCLUDE_FROM_ALL`;
only the app and its real target closure are built. Plugins, examples, applications,
deprecated serializers and shared OSG libraries are disabled. Optional image/font/
compression dependencies are disabled; native Cocoa/Carbon/IOS/X11 window modules
are excluded by windowing None. No broad OSG install target is invoked.

The app uses the same iPhoneOS/ARM64/minimum-18.0 and final-rpath CMake policies as
the working app. Only ANGLE's two untouched frameworks are embedded. OSG archives
are linked into the executable, never copied into the IPA. The inherited validator
rejects host paths, wrong architecture/platform/deployment, unbundled dependencies,
signatures, provisioning files and malformed archive layouts. It additionally
requires the OSG lock, build provenance and notices. Package hashes and the actual
SDK stub checks remain mandatory for the reused ANGLE artifact.

## Build activation and resource budget

Nothing is downloaded or built by host tests. `prepare_osg.py` is plan-only unless
`--allow-downloads` is supplied and refuses non-macOS preparation. CI is explicit
opt-in: a matching push to `ios-port` runs only lightweight tests unless the HEAD
commit message contains **`[run-osg]`** (case-sensitive). `[run-angle]` does not opt
in to this new workflow. Push paths include this experiment/workflow and reused
ANGLE tools/lock/args. An empty commit does not satisfy path filtering. No commit
or push is performed by these scripts.

Where manual dispatch is registered on the default branch, select `ios-port` and
check `build_dependencies` (default false). `build_application=true` requests the
OSG/app stage after ANGLE; false builds only the ANGLE artifact. An ordinary push
or unchecked dispatch cannot run expensive jobs. Existing workflow behavior is
preserved in `.github/workflows/ios-angle-smoke.yml`.

`.github/workflows/ios-osg-smoke.yml` uses three jobs:

1. Ubuntu host checks and explicit event opt-in evaluation.
2. macOS ANGLE dependency gate, calling the original pinned builder/validator
   unchanged; uploads the verified tar and failure logs (90 minute budget).
3. macOS OSG source preparation, app+static OSG compilation and unsigned IPA
   validation (45 minute budget, three Xcode build jobs). It consumes the verified
   ANGLE artifact from the same run and preserves preparation/configuration/build/
   packaging logs even if native compilation fails.

The ANGLE builder's `--output` is **`$RUNNER_TEMP/angle-ios-arm64`**, a directory;
the builder does not choose the workflow's artifact upload directory. The workflow
creates `experiments/ios-osg-smoke/artifacts/angle-ios-arm64.tar.gz` with exactly
one package root, `angle-ios-arm64/`. All three uploads use the job's
`${{ env.EXPERIMENT }}/artifacts/` and fail if no files exist. The first OSG run
incorrectly retained `experiments/ios-angle-smoke/artifacts/` in all three copied
upload steps; that also threatened lightweight logs and the eventual Gate 1 IPA.

The Gate 0 artifact name remains `ios-osg-angle-gate-0-${{ github.run_id }}`.
Gate 1 downloads that same artifact into `dependency-artifact/`, checks its
`angle-ios-arm64.tar.gz` is nonempty, and extracts it into `$RUNNER_TEMP`. This
restores exactly the `-DANGLE_ROOT="$RUNNER_TEMP/angle-ios-arm64"` consumed by CMake.
The package retains `Frameworks/` (EGL/GLES bundles and resources), `include/`,
`Licenses/`, `angle-lock.json`, `angle-build.json`, `args.gn`, `gclient-revinfo.txt`,
`dependency-validation.json` and `package-hashes.json`. The unchanged ANGLE resolver
verifies the producer package before archiving and the restored package **before
OSG source download**, checking device frameworks, pins, inventory and every hash.
Archive listings and both validation logs are uploaded with diagnostics. Synthetic
host tar round trips exercise this layout; actual Actions transport still needs
the next opted-in run. The download name/path and extraction root were already
correct; no changes to the working ANGLE workflow or builder were needed.

ANGLE's multi-GB download, 20 GiB disk preflight and runner requirements still
apply. This workflow currently rebuilds it for a deliberate run, rather than
silently trusting an unrelated old artifact. The OSG shallow checkout/build adds
unmeasured disk, memory and compile time; source preparation fetches the pinned
tree, not just the seven component directories. No CI run, large dependency fetch,
macOS build, provisioning or signing has been launched during implementation.

On macOS with an existing verified ANGLE package, the stages are independently
testable (full Xcode, Python >=3.10, Git and CMake >=3.24 required):

```sh
python3 experiments/ios-osg-smoke/tools/prepare_osg.py --source /path/to/new/osg-source
# After reviewing resource cost, explicitly authorize source fetch/preparation:
python3 experiments/ios-osg-smoke/tools/prepare_osg.py \
  --source /path/to/new/osg-source --allow-downloads
cmake -S experiments/ios-osg-smoke -B experiments/ios-osg-smoke/build -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DANGLE_ROOT=/path/to/verified/angle-ios-arm64 -DOSG_SOURCE=/path/to/new/osg-source \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build experiments/ios-osg-smoke/build --config Release --target IOSOSGSmoke -- \
  -jobs 3 CODE_SIGNING_ALLOWED=NO
```

The policy argument permits this older fork's minimum-CMake declaration on CMake
4; it is not proof of successful native configuration. Configuration downloads
nothing. It rejects missing/altered source/artifacts, a desktop profile, native
window selection or wrong device target. A compile/link failure is a blocker to
inspect, not permission to change the pinned revision or add desktop libraries.

The workflow produces `IOSOSGSmoke-unsigned.ipa` with
`Payload/IOSOSGSmoke.app/`, copied ANGLE frameworks/notices and build provenance.
The copied/adapted stdlib packager reopens the ZIP and verifies contents, CRC,
permissions, resources, SDK dependencies and Mach-O closure before publication.
Download the IPA on Windows and sign/install it locally through Sideloadly. Use
the distinct bundle ID `org.openmw.experiments.ios-osg-smoke`; signing/installing
and framework re-signing still need validation for this new app. No credentials,
profiles or certificates belong here.

## Diagnostics, controls and acceptance

The copied UIKit harness preserves DS4 Triangle/Y clear-only toggle, Square/X
scene selection, held-button/reconnect handling, landscape resize, foreground
rebinding and the one lifecycle drain before context unbinding. No touchscreen
gameplay interface is added. The original working app is not used as a build-time
source dependency; its copied harness is now independent.

Diagnostics include actual EGL/GL/Metal renderer identity, OSG runtime version and
context ID, OSG notify/shader/link output, traversal count/wall time, successful
EGL swaps, callback mean wall time and interval, GL errors and thermal category.
Requested 30 Hz and successful swap rate are clearly separated from **unmeasured
display FPS**. Traversal time includes CPU/driver submission and can block; it is
not GPU timing. There is no framebuffer readback or per-frame glFinish. OSG scene
initialization failure stays visibly in clear fallback; traversal/link/EGL errors
stop with BLOCKED diagnostics. A lost context still requires relaunch.

Retrieve Documents `osg-smoke.json` and `osg-smoke.log` through Files/file sharing;
keep exports only under ignored `device-results/`. OSG logs append across launches,
JSON is the latest snapshot. Use device console for failures before app logging.

First real run must prove a visible rotating depth-tested colored object, not just
an OSG link/version string. Export the ANGLE Metal/A18/GLES3 identity, OSG version,
program link result, increasing traversal/swap counts and errors. Test DS4 mode
switching/reconnect, both landscape orientations and repeated Home Screen return.
Check that the external context remains current and that one EGL swap occurs per
rendered callback. Measure sustained thermal/memory/frame behavior afterward;
OSG/GLSL compatibility, performance and battery impact cannot be inferred from
the earlier bare triangle or these host tests.

Remaining native uncertainties: old fork/modern SDK C++ compatibility, transitive
static link closure and optional detection behavior, GLES3 extension dispatch,
VAO state, matrix upload, actual shader generation/link behavior, first-frame draw,
resize/background teardown and the complete IPA. Only four exact source anchors
were needed in the audit; any further change should be justified by a concrete
compiler/runtime failure and kept in the new overlay. Do not port the full game,
add plugins, GL4ES, file loading or multithreaded rendering to hide a failing gate.

OSG's pinned `LICENSE.txt` is OSGPL (heading version 1.0, granting version 0.0 or
later), based on LGPL-2.1 with the documented wxWindows exceptions. OpenThreads
headers retain their own notices. Both are copied into the app alongside ANGLE's
existing notice inventory. Review exact exceptions and redistribution/source
obligations for the static build before broader binary distribution; this is not
a completed legal-compliance certification.

Host validation command:

```sh
python3 -m unittest discover -s experiments/ios-osg-smoke/tools -p 'test_*.py' -v
```

Tests cover bounded overlays, no-download preparation, source pins, opt-in policy,
scene/context ownership contracts, required OSG provenance and the inherited
unsigned IPA/SDK/Mach-O regressions. These synthetic checks do not compile OSG or
validate native rendering. The first real macOS build is the next required gate.

Local results: 47 OSG-experiment tests passed, including seven artifact-handoff
regressions. Existing ANGLE/Vulkan/Zink suites
also passed (76/76/43 tests respectively), with the existing ANGLE C++ compiler
fixture skipped on this Windows host: **242 passes, one skip** overall. Python
syntax, JSON/plist parsing, all 11 new workflow Bash scripts, documentation links,
new-file whitespace and baseline-preservation checks passed. No local Xcode,
iphoneos SDK, CMake/native compiler or actionlint/YAML parser was available. The
workflow was structurally reviewed, not executed. All four overlay anchors and
both original source checksums were inspected against the pinned upstream files.

Files added (no existing files changed):

| Location | Files |
| --- | --- |
| `.github/workflows/` | `ios-osg-smoke.yml` |
| `experiments/ios-osg-smoke/` | `.gitignore`, `CMakeLists.txt`, `Info.plist.in`, `README.md` |
| `data/` | `angle-lock.json` (unchanged copy), `osg-lock.json` |
| `src/` | `main.mm` (independent adapted UIKit harness), `OSGScene.hpp` |
| `tools/` | `prepare_osg.py`, `check_osg_source.py`, `package_ios.py`, `workflow_opt_in.py`, `test_integration.py`, `test_package_ios.py`, `test_artifact_handoff.py` |
