# OSG over ANGLE/Metal: isolated iPhone scene proof

Status: **compiled, packaged, installed and physically tested on iPhone 16 Plus**
(user-confirmed). The rotating, depth-tested colored cube rendered with OSG 3.6.5,
ANGLE Metal on Apple A18, OpenGL ES 3.0 and GLSL ES 3.00. The captured results
reported 1,632 OSG frames, 1,846 successful EGL swaps and approximately 30.87 swaps
per active second, with nominal thermal state and no application or shader-link
failure. Controller operation and foreground recovery were demonstrated.
Successful swaps are not measured display FPS or a sustained game-performance
result. Build #7 subsequently confirmed the five-frame State diagnostics on the
device, with 1,450 OSG frames/swaps, nominal thermal state and no app/link failure.
Build #8 then confirmed native compilation, callback registration, useful API-error
messages and five-frame deregistration on the device. Two independent launches
reported unsupported `GL_TEXTURE_LOD_BIAS` in `glTexParameterf`. This observed
operation is identified. Original pinned source is now verified locally and the
GLES3-only LOD-bias overlay below is implemented and physically validated in Build #9.
That run rendered 759 OSG frames with 854 successful EGL swaps (approximately
30.53 swaps per active second), nominal thermal state and no application/link
failure. The prior first-frame LOD-bias error was absent in the new session.
Five-frame diagnostic registration/restoration and foreground recovery worked;
the expected missing-windowing-interface warning remains.

**Build #10 status: implemented locally; native compilation and device testing
pending.** It adds the explicit checkerboard Texture2D scene described next.

The separate `ios-angle-smoke` app remains the user-confirmed physical-device
baseline (workflow #12); its code and workflow are unchanged. The build #3-#5
failure/fix sections below are historical records, superseded by the successful
OSG device milestone where they describe compilation as pending.

## Build #10: explicit checkerboard Texture2D

The default scene is now a textured version of the same rotating, depth-tested
24-vertex/36-index cube. The original colored shaders and six-face palette remain
available as a regression baseline. No engine integration or asset loading is added.

`src/Checkerboard.hpp` generates an original 32x32 RGBA fixture (4096 bytes):
4x4 alternating dark `(32,32,32,255)` and light `(240,240,240,255)` cells, with
the entire 4x4 cell at `(u,v)=(0,0)` replaced by red `(255,32,32,255)`.
Row zero is the v=0 edge. Each face maps `(0,0),(1,0),(1,1),(0,1)` to its four
existing vertices, so the marker identifies the first UV corner on every face.
Face winding/orientation follows the existing cube's face order; do not expect
the red corner to occupy the same screen position on differently oriented faces.

`OSGScene` allocates an `osg::Image` once with `allocateImage(..., GL_RGBA,
GL_UNSIGNED_BYTE)` and writes directly into its OSG-owned storage. A ref-counted
Texture2D retains that Image (`setUnRefImageDataAfterApply(false)`); a retained
textured StateSet owns the texture.
There are no pointers into temporary pixel arrays or image-file plugins. OSG's
first textured draw performs upload through its Texture2D traversal; no manual
GL upload, readback or per-frame image/resource reconstruction is added. The
colored and textured StateSets share the existing geometry and model transform.

Texture unit 0 uses explicit NEAREST minification/magnification, CLAMP_TO_EDGE
S/T, zero LOD bias and disabled hardware mip generation. The image supplies only
level zero, and the non-mipmapped min filter does not request a mip chain or OSG's
CPU mip-generation fallback. No osg::Sampler objects, filtering variants, sRGB,
anisotropy or border settings are introduced. The separate GLES3 sampler-object
CLAMP conversion concern remains deliberately unexercised and unmodified.

The new ESSL 3.00 program binds position to attribute 0 and UVs to explicit generic
attribute 6, supplied with `setVertexAttribArray(6, ..., BIND_PER_VERTEX)`.
This public API also has existing repository usage in `groundcover.cpp`; the
complete pinned Geometry/State headers are not cached locally, so the actual
pinned implementation and its interaction with noncompact aliases must still
pass the native build/device test. Conventional `osg_MultiTexCoord0` aliases are
not guessed. UV varying precision matches explicitly between the two shaders.
An integer `checkerTexture` uniform selects unit 0; the fragment shader outputs
only `texture(checkerTexture, uv)`, without the cube's face-color tint.
Attribute-only texture attachment avoids requesting a legacy GL_TEXTURE_2D enable.

Each program has its own first-use link-check flag. After that mode's first OSG
traversal, its actual per-context program link status and info log are checked and
logged with `textured` or `colored` identification. Checking the startup textured
program cannot mark the colored program checked. A failed link still stops with
the existing failure diagnostics.

Controls are edge-triggered as before:

- Square/X toggles the selected cube between textured and colored. In clear-only
  mode it changes the stored cube selection while leaving clear-only active.
- Triangle/Y toggles clear-only; leaving it returns to the selected cube.
- Controller priming/reconnection and pause/foreground behavior are unchanged.

The overlay names the displayed cube mode, and `selected_cube` in the existing
JSON export records the selection independently of `clear_only`. Mode transitions
and startup configuration are written to the existing log. No touchscreen controls
are added. The first active traversal starts textured so its initial upload occurs
inside the unchanged five-frame State and KHR_debug diagnostic window. Switching
modes does not restart that window; later colored linking remains independently
checked. No EGL context changes, extra swaps or synchronization calls are added.

### Build #10 validation and device procedure

Run the existing host command below. `test_texture_scene.py` adds source-contract
checks for storage/lifetime, UV count/bindings, shaders, texture configuration,
independent linking and controller/startup behavior. An optional C++11 fixture
executes the actual checkerboard generator, validates all 1024 pixels/alpha,
checks the 16-pixel red marker and checks guard bytes. It skips explicitly when
no compiler is installed; source checks alone do not execute C++ or validate GL.

After manual review/commit, use the unchanged `[run-osg]` opt-in workflow and
strict IPA validator. No workflow, packaging, overlay or dependency-pin change
is needed. Install the new unsigned IPA using the existing Sideloadly procedure.
For a fresh launch (not merely foregrounding an old scene), verify:

1. Textured startup, visible alternating cells and red marker on each face,
   undistorted face coverage, rotation and correct depth occlusion.
2. A successful `textured` link check and no first-upload/sampling API errors in
   raw OSG/KHR messages. Confirm both five-frame diagnostic transitions and no
   callback loss. The known windowing-interface warning is expected; warning
   counters alone are insufficient evidence of GL correctness.
3. Square selects the original colored baseline and produces its independent
   successful `colored` link check. Repeated switching retains texture content.
4. Triangle enters/exits clear-only and restores the selected cube. Test Square
   while clear-only, held buttons and controller disconnect/reconnect.
5. Repeated Home Screen return and landscape resizing preserve the pattern,
   selection, depth and external-context ownership without application failure.
6. Export the new-session log/JSON, record traversal/swap counts, active swap rate,
   CPU timing and thermal state. Compare a sustained nominal-thermal run with the
   previous approximately 30 successful swaps/active second; actual display FPS
   and GPU duration remain unmeasured.

Mipmap generation, linear/repeat filtering and sampler objects require separate
controlled follow-up builds. This fixture does not validate those paths, broader
OpenMW material compatibility or long-duration battery/performance behavior.

Local Build #10 validation: 89 OSG tests ran (85 passed, four compiler-dependent
fixtures skipped), including 11 new texture regressions. ANGLE: 76 passed/one
skip; Vulkan: 76 passed; Zink: 43 passed. Total: **280 passed, five skipped**.
The pixel-execution fixture is among the skips on this Windows host. Native
Apple compilation, shader linking, texture upload and visual behavior are untested
for Build #10. No downloads, CI runs, commits or pushes were performed.

## Temporary first-five-frame GL diagnostics

The first physical OSG test logged:

```text
Warning: detected OpenGL error 'invalid enumerant' at after RenderBin::draw(..)
```

This identifies where OSG noticed the error, not the originating GL call. The
read-only investigation did not establish a root cause. The missing
WindowingSystemInterface warning is consistent with intentional windowing None
and externally managed UIKit/EGL; it is not evidence that the external context
failed. Neither warning is suppressed.

Immediately after constructing `GraphicsWindowEmbedded`, before State setup,
viewer realization and first traversal, `OSGScene` uses the public State API to
select `osg::State::ONCE_PER_ATTRIBUTE`. After the fifth completed
`viewer->frame()` traversal it restores `osg::State::ONCE_PER_FRAME`. Both
transitions append to the existing `osg-smoke.log`:

```text
OSG GL checking: ONCE_PER_ATTRIBUTE for initialization and the first 5 OSG-rendered frames
OSG GL checking: ONCE_PER_FRAME restored after 5 OSG-rendered frames
```

Frames 1-5 receive fine-grained checks; frame 6 onward retains normal per-frame
checks. Clear-only swaps do not consume this window. Suspension/foreground return
does not reset the existing OSG scene or count, so it neither spends nor restarts
the five-frame budget. If fewer than five OSG frames run, fine-grained checking
remains selected for that scene until its fifth traversal or destruction. A
throwing traversal is not counted; existing error handling still stops the app.

The State diagnostic added no `glGetError` calls, source overlays or rendering
changes. The first frames can incur additional CPU diagnostic overhead;
their timing is not a baseline performance measurement. This mode can narrow an
error to an OSG state/attribute boundary but may not identify an individual call.

Existing logs and JSON fields are preserved. `osg_warnings` counts only delivered
notifications with severity `<= osg::WARN`; a literal "Warning:" prefix does not
guarantee that severity. Other GL diagnostic notifications may be logged without
incrementing this counter. `gl_errors` counts only application-side checks: OSG
can consume and report an error before the application's later check sees it.
Neither counter is a complete count of all GL errors. Continue inspecting the
raw OSG messages and their numeric severity, not just the counters.

Build #7 confirmed both State-check transitions and localized the warning to
`after applying attribute Texture2D`. The app creates no texture explicitly:
exact compiled-binary evidence shows `StateSet::setGlobalDefaults()` creates an
image-backed default Texture2D on unit 0. The error does not justify removing it.

## Temporary GL_KHR_debug capture

Capture/cleanup lives in `src/GLDebugCapture.hpp` and the existing Renderer in
`src/main.mm`; focused regressions are in `tools/test_gl_debug.py`.

Before build #8, the leading hypothesis was the desktop aggregate
`glTexParameteriv(..., GL_TEXTURE_SWIZZLE_RGBA, ...)` found in this exact packaged
OSG binary's `Texture::applyTexParameters`. GLES3 uses the individual R/G/B/A
swizzle parameters. Execution of the aggregate call is **not confirmed**. A guarded
border-color call is another candidate because the device advertises no border-clamp
extension. Build #8 instead captured `glTexParameterf` with `GL_TEXTURE_LOD_BIAS`;
the aggregate swizzle hypothesis does not explain that observed error. No
swizzle/texture correction is implemented by this diagnostic.

`Renderer::start()` uses the already enumerated runtime extension list to require
the exact `GL_KHR_debug` token. With the owning ANGLE context current, it resolves
`glDebugMessageCallbackKHR` through `eglGetProcAddress`, checks the driver message
size and allocates bounded storage **before constructing OSG**. A missing extension,
entry point, valid size or allocation produces an explicit skip reason; the
working experiment continues. No core-function fallback, debug-context request or
EGL attribute change is made. The existing native C++11 declaration probe now
checks `GLDEBUGPROCKHR`, `PFNGLDEBUGMESSAGECALLBACKKHRPROC`, `GL_APIENTRY`, and the
KHR output/synchronous/message-limit constants against the actual restored headers.
The exact headers are not cached locally; build #8 passed this native declaration
probe against the restored artifact, and device callback operation is confirmed.

The callback is registered with synchronous debug output enabled for initialization
and the first five completed OSG frames. The callback only copies into a fixed
buffer: no GL/EGL calls, file I/O, Foundation formatting or dynamic allocation.
Published messages are drained through the existing application logger after GL
returns. Records are JSON-prefixed `KHR_debug` lines with numeric `source`, `type`,
`id`, `severity`, exact `message` text, `phase` and `osg_frame`. JSON escapes preserve
multiline/embedded-NUL text. Valid UTF-8 is retained; a Latin-1 fallback preserves
otherwise undecodable driver bytes as characters. `message_encoding` and
`message_bytes` record the decoding and original length.

Phases distinguish `before OSG construction`, `OSG initialization`, `OSG rendered
frame` (1-based) and clear-only callbacks (completed OSG frame count). The record
limit is 64 messages for the whole window, not per frame or resume; each message
must fit the driver's reported maximum, capped at 16 KiB. Missing/oversized messages
and overflow are counted and explicitly reported as capture loss, without changing
OSG checking. Accepted records are not silently truncated. Excessive advertised
message lengths skip capture altogether. These limits bound both memory and log
volume; loss is reported initially and totals are updated on detach, rather than
logging every subsequent dropped message. Message delivery is not guaranteed
under overflow.

After the fifth OSG frame returns (and OSG restores ONCE_PER_FRAME), the callback
is deregistered and the prior debug-output/synchronous enable states are restored.
Remaining records are flushed. Clear-only swaps do not advance this budget. Pause
detaches before context unbinding; foreground reattaches only if fewer than five
OSG frames completed, preserving captured records and the remaining budget.
Initialization/traversal failures detach while current. Shutdown attempts to bind
the owning context before cleanup. If rebinding fails, no callback-cleanup GL
call is issued against another context, and userdata stays alive through EGL
context/display destruction. No callback calls are made by the capture destructor.

Existing driver message filters are retained; no `glDebugMessageControl` filtering
or suppression is introduced. `GL_KHR_debug` and pointer availability do not guarantee
that a non-debug context emits a useful message or names the offending API/pname.
The context attributes intentionally remain unchanged. Keep the existing State
checks and raw logs as independent evidence; absence of callback messages does
not prove absence of GL errors. If messages are insufficient, obtain the exact
pinned texture source before planning narrower call instrumentation or an
integrity-verified compatibility overlay. The next device run should inspect
registration/skip reasons, phase-tagged error messages, capture-loss notices and
the five-frame deregistration line. Build #8 confirmed useful error delivery and
correct deregistration. Display FPS remains unmeasured.

## Build #8: confirmed texture LOD-bias incompatibility

The user reported the same KHR callback error in two independent iPhone launches:

```text
glTexParameterf: Enum 0x8501 is currently not supported.
```

`0x8501` is `GL_TEXTURE_LOD_BIAS`. The record identifies OpenGL API source, Error
type, High severity, ID 1280 (`GL_INVALID_ENUM`) and the first OSG-rendered frame.
OSG's independent State check identifies Texture2D application. Rendering continues
and both five-frame diagnostic mechanisms remain enabled and unchanged.

GLES3 does not accept `GL_TEXTURE_LOD_BIAS` as a texture parameter. The earlier
exact packaged-binary audit placed texture-parameter operations in
`osg::Texture::applyTexParameters(unsigned, osg::State&) const`; combined with
the callback, that identifies the texture operation now verified in source below.
The callback message alone does not reveal the bias value passed. The source
establishes the default as zero. `GL_TEXTURE_MIN_LOD` and `GL_TEXTURE_MAX_LOD`
clamp the LOD range and are **not substitutes** for bias.

### Verified original source and narrow correction

The user supplied original files from the pinned
`9b384d5439977784e5cd250ff8ff7966928ddd27` commit under
`%USERPROFILE%/Downloads/OpenMW-OSG-pinned-source/src/osg/`. They were read only.
GLExtensions.cpp independently matches the existing source lock; the other two
whole-file hashes are now recorded for fail-closed verification of the fetched
Git originals. No revision or ANGLE/depot_tools pin changes.

| Original file | Confirmed source | Original SHA-256 |
| --- | --- | --- |
| `GLExtensions.cpp:917-923` | Non-Emscripten uses `glVersion >= 1.2f` for bias support, which wrongly passes for GLES3. The Emscripten branch uses `>= 3.0f`. | `bd2cb7bc27918acc902848fcde5e1ecc03f6530acfe614e38d3d4740f304a7cc` |
| `Texture.cpp:1338,2256-2257` | Default `_lodbias(0.0f)`; the capability guards the device-observed `glTexParameterf(target, GL_TEXTURE_LOD_BIAS, _lodbias)`. | `294ea04733def9aa072d0f3563dc965dbb3aac9f6dd4afc3853db5a17d86a2f3` |
| `Sampler.cpp:45,223` | Default `_lodbias(0.0f)`; dirty sampler setup unconditionally submits `glSamplerParameterf(..., GL_TEXTURE_LOD_BIAS, _lodbias)` once sampler entry points exist. | `a3ac93cd091ff2f91a90ffa39c15defc02dbf4d2a59616e7e0f7460efe7721a9` |

`prepare_osg.py` now overrides bias capability to false only when
`OSG_GLES3_AVAILABLE` is defined. Existing texture-max-level detection and every
original desktop version/extension expression remain unchanged. It also surrounds
only the two texture/sampler bias operations with that profile guard: GLES3 emits
no unsupported bias call, while the desktop branches retain their exact original
operations and guards. The separate sampler path is compiled into `osg` (confirmed
by the existing build log), so it needs its own guard; it has not been exercised
by the colored-cube device test.

**Zero bias:** no warning or unsupported call, preserving the intended zero-bias
sampling behavior. **Nonzero bias:** an explicit `OSG_WARN` includes the requested
value and states `unsupported on GLES3; bias is not applied`. The requested member
value is not rewritten, but no equivalent GPU bias is implemented. Applications
requiring nonzero bias must treat it as unsupported. Future shader-level handling
may be necessary, with sampling-operation/stage-specific semantics; it is outside
this patch. MIN_LOD/MAX_LOD clamping is unchanged and is not used as a replacement.

All surrounding parameters, swizzle operations, texture initialization, shaders,
geometry, EGL ownership and controller/lifecycle code are unchanged. No GL errors
are cleared or hidden; both five-frame diagnostic mechanisms remain intact for
post-fix verification. One separate source limitation is recorded without a fix:
Sampler.cpp:183 omits GLES3 from its CLAMP-to-CLAMP_TO_EDGE conversion guard despite
default CLAMP wraps. That is another potential sampler-path issue if exercised;
this bias correction does not establish general sampler compatibility.

Overlay version **2** now identifies exactly four changed fetched files: the
existing CMakeLists.txt/GLExtensions.cpp adaptations plus Texture.cpp/Sampler.cpp.
Seven exact-once replacement anchors and all four original SHA-256s are checked
before any write. Missing/duplicate anchors or wrong source fail preparation.
`check_osg_source.py` still verifies HEAD, original Git blobs, exact transformed
bytes, tracked-file inventory and output manifest hashes. Bundled build metadata
and the strict IPA validator require overlay version 2; stale version 1 metadata
is rejected. Source revision pins remain unchanged.

Build #9 must validate the fetched original hashes, native compilation and strict
IPA packaging. On the iPhone, retain both diagnostics and verify that the first
five frames no longer report the 0x8501 error while the cube, depth, controls and
foreground recovery still work. Report any different error rather than suppressing
it. Nonzero warning behavior and the unexercised sampler path need their own
native validation before any broader compatibility claim.

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
| `src/osg/GL.in` and root header settings | Apple defaults to `<OpenGLES/ES3/gl.h>`. Set the CMake cache header strings to ANGLE `<GLES3/gl3.h>` / `<GLES2/gl2ext.h>`; pass its include path to compile checks. No GL.in patch is needed. |
| `src/osg/GLExtensions.cpp` | Apple branch uses global `dlopen`/`dlsym`; replace provider selection only for this experiment with `eglGetProcAddress`, including core-function availability probes at runtime. No global resolver fallback. |
| `include/osgViewer/GraphicsWindow` | Embedded window creates State/context bookkeeping and has no-op current/swap implementations. Use only with the already-current external EGL context. |
| `src/osg/State.cpp`, `include/osg/Program` | Default aliases can be compact; select the explicit noncompact mapping. Enable supplied matrix uniforms and inspect the actual per-context program link status. |
| `src/osgViewer/CMakeLists.txt` | Viewer links osgGA, osgText, osgDB, osgUtil, osg, OpenThreads. osgText remains a transitive dependency even with no text drawn. |

Exactly **four fetched OSG files** are adapted: three CMake replacements,
GLExtensions resolver/capability changes, and the Texture/Sampler bias guards.
`prepare_osg.py` verifies original SHA-256s
before any write, and `check_osg_source.py` recomputes expected overlays from
pinned Git blobs, verifies HEAD and rejects unrelated tracked differences.
`data/osg-lock.json` records all pins, source hashes and overlay version. These
are explicit source adaptations, not claims of stock fork compatibility. They
are never applied to the engine's `extern` checkout or any working experiment.

### Run #3 shader debug-label identifier fix

The first reported compiler error was `src/osg/Shader.cpp:757`: the existing
`_extensions->debugObjectLabel(GL_SHADER, _glShaderHandle, _shader->getName())`
call uses a core GL identifier absent from the selected GLES3 headers. The
reported pinned ANGLE `GLES2/gl2ext.h` instead declares `GL_SHADER_KHR` as
`0x82E1`, the same shader-object identifier. This is a declaration spelling
mismatch, not a shader-language, context-creation or shader-compilation change.

CMake now adds **`GL_SHADER=GL_SHADER_KHR` only to `src/osg/Shader.cpp` in the
`osg` target directory**. It does not define a project-wide token or change any
fetched source. The original call, object handle, name and runtime debug-support
checks remain intact; no debug feature is forced on or disabled. Header presence
does not establish runtime KHR_debug support. The existing header-only native
C++11 probe tests this alias and asserts the KHR identifier equals `0x82E1`.
A missing/wrong declaration still fails configuration without GL linking.

At the shader-label stage, no new source overlay, hash or overlay-version bump
was needed: the original two
audited files and their transformations are unchanged. `check_osg_source.py`
still rejects any tracked modification to `Shader.cpp`. Existing lock/build
metadata described overlay version 1. The later LOD adaptation above uses version
2; dependency revisions remain unchanged.
This source-specific compile definition is recorded here and in CMake rather
than claiming it is a third transformed source file.

This follow-up was performed offline using the reported native error/header
evidence and local configuration. The full pinned `Shader.cpp` and ANGLE headers
are not cached locally; no new upstream source checksum has been invented. Tests
check definition scope, strict source inventory and the native probe. An optional
C++11 synthetic reproducer checks the original failure, alias success, missing
KHR token and wrong value when a host compiler is available. It is skipped on
this Windows host. Full compilation and runtime labeling remain unverified.

### Run #4 program debug-label identifier fix

`Program.cpp:830` uses the analogous
`_extensions->debugObjectLabel(GL_PROGRAM, _glProgramHandle, _program->getName())`.
The selected GLES3 headers do not declare that core spelling. The intended KHR
program-object identifier is `GL_PROGRAM_KHR` (`0x82E2`). CMake adds
**`GL_PROGRAM=GL_PROGRAM_KHR` only to `src/osg/Program.cpp`, with
`TARGET_DIRECTORY osg`**, after the OSG target exists. Shader.cpp retains its
own alias; neither alias is global or added to other rendering/application sources.
The original program-linking code, debug label call and runtime guards remain
untouched. No additional OSG source overlay or integrity exception is introduced.

Exact-artifact verification is mandatory before either source alias is applied:
`check_angle_headers.py` reads the already hash-validated artifact's actual
`include/GLES2/gl2ext.h` and requires exactly one literal definition each of
`GL_SHADER_KHR == 0x82E1` and `GL_PROGRAM_KHR == 0x82E2`. It reports the verified
values alongside header hashes. The subsequent fresh C++11 probe includes the
selected headers, tests both aliases and statically asserts both values after
preprocessing. Missing, wrong, duplicate or indirect token definitions fail the
preflight; a preprocessor/declaration mismatch fails the native probe. No local
replacement header is exported or used for a real build.

Offline evidence: `ios-osg-angle-gate-1-42155332093.zip` in the local Downloads
directory confirms the Program.cpp error and successful old probe. Its configure
log records `GLES2/gl2ext.h` SHA-256
`53c564985d35b7ca4b744a0a8b81f120aa0c114c319b3b98d3223bf599bc815b`.
The ZIP contains logs, not the header text or the full OSG source. At this fix's
implementation, the exact pinned artifact's GL_PROGRAM_KHR declaration was not
independently verified locally. Run #5 subsequently passed the mandatory actual
artifact preflight and native probe: its configure log reports shader/program
values 33505/33506 (`0x82E1`/`0x82E2`). Synthetic test headers are not artifact
verification.

Locally available debugObjectLabel references are the reported shader/program
error excerpts, configuration and regression fixtures, not a full fork checkout.
No additional alias was justified at that stage. Run #5 now supplies concrete
buffer-label evidence, as documented below.

### Run #5 buffer debug-label fix and bounded call-site audit

The sole build-log error is `src/osg/BufferObject.cpp:207`, at
`_extensions->debugObjectLabel(GL_BUFFER, _glObjectID, _bufferObject->getName())`.
This is the same core/KHR identifier spelling mismatch, not a buffer allocation
or GPU data-upload failure. CMake now defines **`GL_BUFFER=GL_BUFFER_KHR` only for
`BufferObject.cpp`, using `TARGET_DIRECTORY osg`** after the OSG target exists.
The original fetched source, object/name arguments, runtime debug-support checks,
shader compilation, program linking and buffer operations are unchanged.

The already hash-validated ANGLE artifact's actual `GLES2/gl2ext.h` must now also
define `GL_BUFFER_KHR` exactly once as `0x82E0`. The native C++11 probe separately
asserts that value and the alias equality after preprocessing. Both checks run
before CMake permits the BufferObject.cpp compile definition. The exact buffer
declaration is **not yet verified against an available pinned header locally**;
the diagnostic ZIP does not contain header text. Missing or wrong declarations
must stop configuration, never cause a fabricated header or backend fallback.

The offline bounded audit searched this repository (including ignored experiment
directories), the existing cached reference tree under
`%TEMP%/openmw-ios-renderer-audit-20261103`, and the three available OSG Gate 1
diagnostic ZIPs in Downloads. No full pinned OSG source files or ANGLE headers
were found in these locations. Compiler excerpts provide these exact usages:

| Available pinned-source excerpt | Identifier | Evidence/status |
| --- | --- | --- |
| `Shader.cpp:757` | `GL_SHADER` | Earlier error excerpt; source alias and actual KHR declaration/probe passed build #5. |
| `Program.cpp:830` | `GL_PROGRAM` | Earlier error excerpt; source alias and actual KHR declaration/probe passed build #5. |
| `BufferObject.cpp:207` | `GL_BUFFER` | Sole build #5 error; new source alias gated by pending artifact/native verification. |

No other demonstrably incompatible debugObjectLabel identifier was found in the
available source excerpts. **This is not a complete audit of the unavailable
pinned checkout**, and a single compiler error cannot prove other translation
units are compatible. Further call sites must be inspected from that exact
checkout or exported source evidence before adding more aliases. No speculative
mapping is added for other GL object types.

Source-integrity tests explicitly reject modifications to Shader.cpp, Program.cpp
and BufferObject.cpp. At the buffer-label stage the two original overlay files,
SHA-256 checks and overlay version 1 were unchanged. The later LOD overlay is
version 2. Dependency revisions and the UIKit/EGL owner, Metal
presentation and single-threaded OSG traversal are untouched.

Seven OSG libraries are built statically: OpenThreads, osg, osgUtil, osgDB, osgGA,
osgText and osgViewer. The top-level OSG project is configured with `EXCLUDE_FROM_ALL`;
only the app and its real target closure are built. Plugins, examples, applications,
deprecated serializers and shared OSG libraries are disabled. Optional image/font/
compression dependencies are disabled; native Cocoa/Carbon/IOS/X11 window modules
are excluded by windowing None. No broad OSG install target is invoked.

### GLES header preflight

OSG-over-ANGLE run #2 reached native compilation but failed on our configured
`GLES3/gl3ext.h`. This was an experiment configuration error, not a missing `-I`
flag, incomplete Gate 0 export or a mandatory OSG filename. The pinned ANGLE
[`include/GLES3`](https://github.com/google/angle/tree/6ea96bcca6d7f05199f5565c6d5c4722af7269da/include/GLES3)
inventory contains `gl3.h`, `gl31.h`, `gl32.h` and `gl3platform.h`, but no
`gl3ext.h`. The unchanged builder copies the entire include tree. The pinned OSG
template simply inserts `OPENGL_HEADER1` and `OPENGL_HEADER2`; its non-Apple GLES3
default uses `GLES3/gl3.h` with an empty second header.

The intended pair is now **`GLES3/gl3.h` then `GLES2/gl2ext.h`**. The first supplies
ES3 core types/functions and platform macros. ANGLE's shared Khronos GLES extension
declarations live in the second, including OES vertex-array function pointer types
and extended 64-bit types; it consumes the preceding core declarations. Including
this file does not select a GLES2 context or establish runtime extension support.
No empty shim, GLES3.1/3.2 header upgrade, Apple OpenGLES include or source-overlay
change is used. `OPENGL_PROFILE` remains exactly GLES3.

Before adding OSG's CMake subdirectory, `check_angle_headers.py` checks the actual
restored artifact, not the host SDK: both selected headers, `GLES3/gl3platform.h`,
`KHR/khrplatform.h`, `EGL/egl.h`, `EGL/eglext.h` and `EGL/eglplatform.h` must exist,
be nonempty and resolve inside the artifact include root. Wrong profiles, header
orders, alternate providers or invalid selections fail explicitly. This follows
the existing full artifact hash verification; it does not replace it. Header
hashes are printed to the configure log. `gl2ext.h` does not require importing
the GLES2 core header (`gl2.h`) or an additional extension platform header.

A fresh, scoped CMake static-library compile probe then includes the exact selected
pair and tests ES3 64-bit and core/OES VAO declarations. It requires neither GL
linking nor signing and aborts configuration on a declaration mismatch. No cached
positive result is trusted. The actual generated `osg/GL`, complete OSG compilation,
further extension API compatibility and runtime rendering still require native
compilation and a device run. Run #3 confirmed the selected-header/type probe
before the shader-label fix; the extended probe and full compilation require the
next opted-in macOS build. Host file-inventory fixtures do not prove native
header compatibility.

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
the distinct bundle ID `org.openmw.experiments.ios-osg-smoke`; installation and
launch are now user-confirmed for the initial app. Each changed diagnostic build
still needs its own validation. No credentials, profiles or certificates belong here.

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

The first real run proved a visible rotating depth-tested object and the
ANGLE Metal/A18/GLES3 identity, OSG version, program linking and increasing counts.
The next run should capture the new error-check transitions and any narrower GL
diagnostics. Continue testing DS4 reconnect, both landscape orientations and
repeated Home Screen return beyond the demonstrated controller/foreground cases.
Check that the external context remains current and that one EGL swap occurs per
rendered callback. Measure sustained thermal/memory/frame behavior afterward;
OSG/GLSL compatibility, performance and battery impact cannot be inferred from
the earlier bare triangle or these host tests.

Basic native compilation, static linking, shader linking, VAO geometry, matrix
upload, depth drawing and IPA installation are now established for this scene.
Remaining uncertainties include native validation of Build #10's explicit texture,
broader extension paths, repeated lifecycle/resize behavior and sustained thermal
performance. The initial four exact source anchors plus three verified LOD anchors
are the bounded adaptations; any further source adaptation requires compiler/runtime evidence
and bounded integrity verification. Do not port the full game,
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
validate native rendering. Compiling and physically testing the new temporary
diagnostics is the next gate; prior device success does not validate this change.

Pinned-source LOD correction: 78 OSG tests ran (75 passed, three compiler-dependent
fixtures skipped). The eight new LOD tests include real reference checksum/default/
roundtrip checks, GLES3/desktop behavior, exact-anchor rejection, atomic wrong-source
failure and overlay-version/pin checks. The optional C++11 fixture executes the
actual anchor snippets across desktop/GLES3 and Emscripten variants; it could not
run on this host. Other suites passed: ANGLE 76/one skip, Vulkan 76, Zink 43:
**270 passes, four skips** overall. All 34 Python tool files passed AST parsing;
JSON/plist, whitespace, unchanged revision pins/original hashes, application-source
preservation, read-only references and experiment-only scope checks passed.
The application and both diagnostics are unchanged. Native OSG/Apple compilation
and Build #9 device behavior are untested; no downloads, CI, commits or pushes ran.

Previous Build #8 LOD-bias investigation: only the README changed. Existing suites passed:
OSG 68 passed/two skips, ANGLE 76 passed/one skip, Vulkan 76 passed, Zink 43 passed
(**263 passes, three compiler-dependent skips**). All 33 Python tool files passed
AST parsing; JSON/plist, unchanged pins, README-only scope and whitespace checks
passed. The source-evidence recipe passed Bash syntax checking without execution.
No bias-exclusion behavior test was added or claimed: no verified overlay can be
implemented until the original pinned source is available. Native callback/error
reporting remains intact. No downloads, builds, CI, commits or pushes occurred.

Previous KHR callback follow-up: 70 OSG tests ran (68 passed, two C++ compiler-dependent
fixtures skipped). Seven focused callback tests cover runtime/entry-point checks,
registration order, bounded full-message recording, phases, scope, cleanup,
unchanged rendering/error polls and the pinned-header native probe. The optional
C++17 fixture exercises the actual helper with synthetic EGL/GLES declarations;
it is not proof of ANGLE ABI or device behavior. Unchanged ANGLE/Vulkan/Zink suites
passed 76/76/43 tests with one ANGLE compiler-fixture skip: **263 passes, three
skips** overall. All 33 Python tool files passed AST parsing; JSON/plist, whitespace,
unchanged pins/OSGScene and six-file experiment-only scope checks passed. No local
CMake/native compiler was available. Native probe/Apple compilation and callback
delivery remain untested; no downloads, CI, commits or pushes were performed.

Previous State-diagnostic follow-up: 63 OSG tests ran (62 passed, one optional C++
compiler fixture skipped), including three new initialization/scope/restoration
and reporting regressions. Unchanged ANGLE/Vulkan/Zink suites passed 76/76/43
tests respectively, with one existing ANGLE compiler-fixture skip: **257 passes,
two skips** overall. All 32 tool Python files passed AST parsing; OSG JSON/plist,
unchanged-lock, exact three-file change scope and whitespace checks passed.
No native compiler/CMake was available locally. No downloads, native build, CI,
commit or push was performed; the diagnostic mode still needs iPhone validation.

Previous buffer-label follow-up: the OSG suite ran 60 tests (59 passed, one optional C++
compiler fixture skipped). Regressions now cover all three source-specific aliases,
native-probe values, rejection of fetched-source edits and invalid/missing buffer
definitions. A dedicated CLI regression checks the explicit missing-buffer error.
The synthetic compiler fixture includes buffer alias success and missing/wrong
KHR declarations, but cannot run without a local compiler. Native OSG compilation
and runtime debug-label behavior remain unverified for this change.
The unchanged suites also passed: ANGLE 76 passed/one compiler-fixture skip,
Vulkan 76 passed and Zink 43 passed: **254 passes, two skips** overall.
All 32 tool Python files passed AST parsing; OSG JSON/plist, unchanged locks,
changed-file whitespace and experiment-only change-scope checks passed. No local
native compilation, download, CI run, commit or push was performed.

Previous program-label follow-up: the OSG suite ran 59 tests (58 passed, one optional C++
compiler fixture skipped). The fixture now covers both shader and program tokens.
The extra header regression rejects missing, wrong, commented-out, duplicate and
indirect definitions for each identifier. Native artifact checks remain pending.
Unchanged suites also passed: ANGLE 76 passed/one compiler-fixture skip, Vulkan
76 passed and Zink 43 passed, giving **253 passes and two skips** overall.
Python AST parsing (32 files), OSG JSON/plist parsing, unchanged-lock checks and
changed-file whitespace checks passed. All five changed files are confined to
this experiment; workflows, engine, other experiments and pins are unchanged.

Previous shader-label follow-up: the OSG suite ran 58 tests (57 passed, one optional C++
compiler fixture skipped). ANGLE ran 77 (76 passed, its existing compiler fixture
skipped), Vulkan 76 passed and Zink 43 passed: **252 passes, two skips** overall.
All 32 experiment-tool Python files passed AST parsing; OSG JSON/plist parsing,
changed-file whitespace and unchanged-lock checks passed. No local CMake,
Xcode/iPhoneOS compiler or actual ANGLE-header compile was available. The next
manual `[run-osg]` build must validate the extended declaration probe, generated
Shader.cpp compile definition and remaining native compilation. No CI was started.

Previous header-fix local results: 54 OSG-experiment tests passed, including seven header-selection
regressions and seven artifact-handoff regressions. Existing ANGLE/Vulkan/Zink suites
also passed (76/76/43 tests respectively), with the existing ANGLE C++ compiler
fixture skipped on this Windows host: **249 passes, one skip** overall. Python
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
| `tools/` | `prepare_osg.py`, `check_osg_source.py`, `check_angle_headers.py`, `package_ios.py`, `workflow_opt_in.py`, `test_integration.py`, `test_package_ios.py`, `test_artifact_handoff.py`, `test_angle_headers.py` |
