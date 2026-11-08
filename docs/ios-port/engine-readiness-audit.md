# Native OpenMW iOS readiness and first component milestone

Audit: 2026-11-08, offline, branch `ios-port`. Repository HEAD at inspection:
`8ff9d1704e` (Build #14). Root CMake declares OpenMW **0.53.0**, C++20; earlier
conversation descriptions of 0.52 do not override the current source. This report
distinguishes inspected source, user-confirmed phone results and unbuilt proposals.

## 1. Recovery of unfinished Build #15

The working tree was already dirty when this task started. No changes were staged.
Eight tracked files and one untracked header implement part of the previous
observation-only task:

| Existing file | Work already present |
| --- | --- |
| `experiments/ios-osg-smoke/tools/prepare_osg.py` | Exact-anchor post-call events at both glGenerateMipmap dispatches, an image-helper completion event and an observation ABI marker in hash-locked Texture.cpp. |
| `src/MipmapObservation.hpp` (untracked) | Texture/context-filtered, thread-local observer, counters, tri-state result and RAII detach. |
| `src/OSGScene.hpp` | Registers the mipmapped texture, logs observation transitions and unregisters on teardown. |
| `src/main.mm` | Event receiver, JSON observation fields and dynamic call status in the existing overlay. |
| `data/osg-lock.json`, `CMakeLists.txt` | Overlay version raised from 2 to 3 and build metadata/header registration updated. |
| `tools/package_ios.py`, `tools/test_package_ios.py`, `tools/test_integration.py` | Version-3 validation/fixtures and stale-version rejection partially updated. |

Paths in the table after the first row are relative to `experiments/ios-osg-smoke/`.
This work does not change the pinned OSG/ANGLE revisions or the four original
source hashes. It is nevertheless **unfinished and unvalidated**. Its README and
LOD/source-roundtrip fixtures were not updated and no focused observer tests exist.

The initial local OSG suite ran **105 tests: 96 passed, four failure records,
five compiler-dependent skips**. The failures are:

1. Original Texture.cpp roundtrip does not reverse the new observation adaptation.
2. The manifest regression still expects overlay version 2.
3. The synthetic atomicity fixture lacks the new anchor, causing an earlier error
   before the intended bad Sampler.cpp checksum is reached.
4. The overlay presentation test still expects the old capability/call text.

The four failures predate this audit's edits. They are not resolved by suppressing
tests or reverting the observer. The existing nine file contents were hashed at
the start and checked for exact preservation at the end. The unfinished observer
is a separate pending work item; actual device glGenerateMipmap invocation remains
unobserved. Its completion is not a prerequisite for compiling data components.

There is no engine-source conflict, but future engine work must not silently use
the dirty version-3 smoke tree as if it were the physically validated baseline.
For a new graphics integration gate, explicitly use the reviewed Build #14
version-2 source/artifact contract or first finish and validate Build #15. Do not
mix v2 libraries/metadata with a v3 validator. No checkout, stash, reset, commit,
push, remote edit or CI run was performed. `github` remains the personal repository;
`origin` remains upstream OpenMW on GitLab.

## 2. What is established

The user confirmed Build #14 compiling, packaging, installing and running on an
iPhone 16 Plus: OSG 3.6.5 -> GLES3 -> pinned ANGLE Metal -> Apple A18, textured
geometry, four profiles, six comparison cubes, controllers and foreground recovery.
Reported results include about 30 successful swaps per active second, zero
application-polled GL errors and nominal thermal state. These results establish
the graphics harness, not a running OpenMW engine or measured display FPS.

Pinned dependency identities remain:

- OSG `9b384d5439977784e5cd250ff8ff7966928ddd27`.
- ANGLE `6ea96bcca6d7f05199f5565c6d5c4722af7269da`.
- depot_tools `816da11f80777dcf8c10bdaa84df18450dcba12a`.
- iPhoneOS ARM64, minimum deployment 18.0; original strict unsigned IPA workflow.

Build #14 uses UIKit/CAMetalLayer, explicit ANGLE EGL Metal selection, a current
application-owned GLES3 context, GraphicsWindowEmbedded, SingleThreaded OSG and
one application-owned eglSwapBuffers per rendered callback. The new data target
does not touch that contract. Earlier Vulkan/MoltenVK and Zink experiments remain
independent evidence and are not engine dependencies or new backend candidates.

## 3. Full engine dependency inventory

"Available" here means checked into the repository or supported by existing
device build evidence. A Windows installation is not evidence of an iPhoneOS
library. No package-manager/system dependency inventory or native link test was
performed. External library APIs, versions and build requirements below come from
the current source/configuration, not a new upstream compatibility survey.

| Dependency | Actual requirement / pinned fallback | Local/device evidence and remaining work |
| --- | --- | --- |
| C++ toolchain | [Root CMake](../../CMakeLists.txt#L11): C++20; code uses char8_t, ranges, std::format. | Current graphics app is C++17 with older OSG compilation. Xcode/libc++ must compile the engine's actual C++20 use. No local CMake/C++ compiler was available. |
| ANGLE EGL/GLES | Pins above; UIKit/Metal/Foundation/QuartzCore/GameController frameworks. | Native framework build and phone rendering established. No general desktop OpenGL implementation is supplied. |
| OSG/OpenThreads | [Root component list](../../CMakeLists.txt#L309) includes Animation, DB, GA, FX, Particle, Text, Util, Shadow, Sim, Viewer, in addition to osg/OpenThreads. | Smoke builds seven libraries: osg, osgDB, osgUtil, osgViewer, osgGA, osgText, OpenThreads. Engine closure needs more components; IPA-linked static code is not a reusable set of headers/static archives. Rebuild/export a matched device package. |
| OSG plugins | BMP, DAE, DDS, FreeType, JPEG, OSG, PNG, serializers, TGA requested; extern also enables KTX. | Smoke avoids plugins. Full engine expects plugin registration and checks presence. Static plugin retention, image/font libraries and Collada DOM need explicit scope/provenance. Not all are needed for the first synthetic scene. |
| SDL2 | [Root](../../CMakeLists.txt#L554): >=2.26; video, controllers, joystick, sensor and engine input integration. | No iOS SDL package/ANGLE context bridge established. GameController in the smoke app does not provide SDL events or SDL_Window. |
| Boost | >=1.70 CONFIG, iostreams and program_options. | Not vendored; no iPhoneOS package verified. Used beyond launchers, including engine/components configuration/debug paths. |
| Bullet | Collision + LinearMath; version >=287 and double precision; fallback 3.25 with archive hash. | Not downloaded/present under extern. Full physics/resource-shape path needs matched double-precision device build. |
| MyGUI | >=3.4.3; fallback MyGUI3.4.3 archive with hash, renderer interface 4. | Library not vendored; OpenMW's custom OSG renderer is present. No device MyGUI/GUI shader/font validation. |
| Lua / LuaJIT | Default USE_LUAJIT=TRUE; USE_LUAJIT=FALSE already selects FindLua and NO_LUAJIT. sol3 3.5.0/config headers are vendored. | No runtime source/package pin or device recipe verified. Evaluate the existing plain-Lua route first; do not assume a desktop JIT recipe works on the phone. No new runtime version selected here. |
| ICU | uc, i18n, data; fallback 70.1. | No device build. Bundled recipe uses configure/make; special host-tool cross-build handling exists for Android only. iOS host/data cross-generation needs a real recipe. |
| FFmpeg | >=4.0: avcodec, avformat, avutil, swscale, swresample. | Wrapper source exists under extern; FFmpeg itself is absent. iPhone codecs, static closure, configured features and notices need validation. |
| OpenAL | Required by engine; OpenAL output/EFX calls in mwsound. | No current device package verified. Do not assume Apple framework availability or an arbitrary desktop OpenAL build. Audio session/interruption/route handling remains unimplemented. |
| Recast/Detour | OpenMW fork `03259f3287ff8330f0d66fcd98d022edddffaa97`, hash-checked archive fallback. | Source not fetched. Required by broad components/physics/navigation closure. |
| SQLite | System or fallback 3.41.1 amalgamation/hash. | No iOS build established for this project. Stock Apple SQLite availability would still need an explicit find/link/feature check, not an assumed package. |
| LZ4 / zlib | Required discovery/linking in root/components. | No device package validation. iOS SDK zlib availability may be usable later but has not been checked here. LZ4 is not vendored. |
| yaml-cpp | System or pinned `c2680200486572baf8221ba052ef50b58ecd816e` (0.8.0 plus CMake compatibility commit). | No source/device package in current checkout. |
| TinyXML / OICS / Base64 / smhasher | Internal TinyXML option; OICS input, Base64 and MurmurHash sources under extern. | Sources present. Their inclusion/ABI and full engine link are untested on iOS. They are not all independent downloaded packages. |
| Qt6 / unshield / test libs | Qt for launcher/editor/wizard, unshield for non-Windows wizard; GTest/benchmark optional. | Exclude those applications/tests from the engine target. Qt is not intrinsically required for the game, but broad root discovery still requires other engine dependencies. |

See [extern/CMakeLists.txt](../../extern/CMakeLists.txt) for the existing archive
hashes/versions. No pin was changed and no absent dependency was downloaded.
Recipe presence does not establish iOS compatibility. The selected first milestone
below avoids all external libraries while retaining real OpenMW source execution
as its next host-test acceptance condition.

## 4. Verified platform/build blockers

### Build graph and Apple assumptions

[Root CMake](../../CMakeLists.txt#L290) unconditionally searches desktop OpenGL,
including a framework-only APPLE branch. Disabling desktop apps does not bypass
all global dependency checks or FetchContent recipes. `BUILD_OPENMW=OFF` also does
not turn the broad common component graph into an iOS data-only library.
[components](../../components/CMakeLists.txt#L589) is a single large static target;
[openmw-lib](../../apps/openmw/CMakeLists.txt#L121) includes nearly all game subsystems.
Linking just Engine therefore brings substantial compile/link dependencies even
if runtime options would later disable features.

Broad APPLE branches configure `Contents/MacOS`, `Contents/Resources`, macOS plist/
icons and Cocoa/IOKit/VideoDecodeAcceleration linkage. These are macOS recipes,
not UIKit/iPhone bundle recipes. The root also enables install-rpath propagation
from link paths, contrary to the verified app's strict bundled-framework policy.
An eventual iOS branch must distinguish the target OS, use the validated packaging
rules and keep desktop behavior intact. No global APPLE macro hack is justified.

`CheckLuaCustomAllocator.cmake` runs a try_run for non-Windows/non-Android builds;
iOS cannot execute that target binary on the build host. The ICU fallback likewise
needs host-generated data/tools during cross-compilation. These are explicit
cross-build tasks, not grounds to fake results or install unpinned substitutes.

### Context/window ownership and lifecycle

[Engine constructor](../../apps/openmw/engine.cpp#L397) calls SDL initialization
with video/controller/joystick/sensor flags. It is not a platform-free object.
[createWindow](../../apps/openmw/engine.cpp#L524) creates an SDL_OPENGL window and
GraphicsWindowSDL2, attaches it to the camera and realizes the viewer.
[GraphicsWindowSDL2](../../components/sdlutil/sdlgraphicswindow.cpp#L86) creates,
makes current, deletes and swaps an SDL GL context. Its ES profile selection is
conditional on Android/GL4ES, not a native iOS/ANGLE implementation.

That conflicts directly with UIKit's existing ANGLE context and swap ownership.
Do not wrap the current SDL context class around a dummy window or let it create
a second context/layer. A future platform adapter must accept the application's
existing viewer/window/context and separate controller/input events from rendering
ownership. Keep SDL as a possible input integration dependency; using it does not
require granting SDL presentation ownership. Such separation is not implemented.

[Engine::frame](../../apps/openmw/engine.hpp#L203) and prepareEngine are private.
[go](../../apps/openmw/engine.cpp#L974) owns a blocking loop, advances the viewer,
updates systems and invokes traversal. CADisplayLink integration needs an explicit
initialization/step/suspend interface rather than nesting this loop inside UIKit.
Pause/resume must eventually coordinate physics/Lua workers, UI/audio and queued
resource compilation. Smoke foreground recovery proves only its own simple path.

### Rendering and OSG integration

`prepareEngine` constructs VFS/ResourceSystem, SceneManager, GUI and ultimately
MWWorld/MWRender. [ResourceSystem](../../components/resource/resourcesystem.cpp)
constructs several file/image/scene/keyframe managers. [SceneManager](../../components/resource/scenemanager.cpp)
pulls in NifOsg, ShaderManager/ShaderVisitor, osgAnimation and osgParticle. The
minimal seven-library smoke closure is insufficient for that path.

The working ESSL300 cube does not establish OpenMW shader compatibility:

- [ShaderManager](../../components/shader/shadermanager.cpp#L520) defaults unprefixed
  templates to compatibility/, with core-profile switching explicitly unfinished.
- [Object shaders](../../files/shaders/compatibility/objects.vert) use GLSL 1.20,
  compatibility inputs and extension-dependent variants. [GUI shaders](../../files/shaders/compatibility/gui.vert)
  also use gl_Vertex/gl_Color/gl_MultiTexCoord0.
- A core/ directory exists, but [its GUI shader](../../files/shaders/core/gui.vert)
  declares desktop GLSL 4.30, and its compute paths do not establish ES3.0 support.
- [MyGUI rendering](../../components/myguiplatform/myguirendermanager.cpp) already
  submits OSG-backed buffers/GL_TRIANGLES and obtains its program from the engine
  ShaderManager. It needs an explicit GLES attribute/uniform/shader test; a generic
  "replace #version" patch is insufficient.
- RenderingManager still manipulates alpha-test state; water/shadows include
  depth-clamp and more advanced paths. Postprocessing/FBO/render-to-texture and
  depth formats need separate device fixtures. Some paths have guards, so token
  presence alone does not prove every path will fail; current ES3 compatibility
  of the real renderer is untested.

The validated LOD-bias OSG adaptation is one bounded fix, not blanket certification
of every OpenMW state/extension path. Do not enable GL4ES, Zink, Apple OpenGLES or
a software renderer as a hidden substitute.

### Files, game data, resources and input/audio

[FixedPath](../../components/files/fixedpath.hpp) selects MacOsPath for Apple targets.
[MacOsPath](../../components/files/macospath.cpp) assumes Library/Preferences,
global /Library directories, a Contents/Resources-style bundle layout and desktop
installation discovery. Global paths/layout are wrong for the intended app;
the existing POSIX low-level file API is a different, reusable layer.

Plan explicit paths from UIKit/Foundation: bundled read-only OpenMW resources,
app-owned imported game data, writable configuration/saves/logs and Library/Caches.
Paths from a document picker may require copying or security-scoped access and
lifetime handling. Do not treat picker URLs as unconditional POSIX access, or
normalization as a security sandbox. No user import/path policy is implemented.

[main parseOptions](../../apps/openmw/main.cpp#L107) rejects empty content lists;
Engine::go asserts nonempty content and prepareEngine creates/loads the world.
Skipping the menu does not create a no-world mode. Real Morrowind rendering later
needs user-provided content/BSA or loose data, OpenMW's own shader/UI/font/Lua/
localization resources, settings defaults and writable paths. A synthetic fixture
can avoid game assets but cannot prove the full world pipeline.

The engine's SDL polling, InputWrapper, bindings manager and OICS differ from the
smoke app's GameController buttons. Preserve DS4 behavior while mapping actions
and neutralizing held inputs on suspend/disconnect. Touchscreen gameplay remains
out of scope. Audio requires OpenAL output plus FFmpeg decoding in current build
targets even with --no-sound; that option changes runtime behavior, not the link
closure. Future audio work needs interruption/background/route testing on iPhone.

## 5. Milestone selection

| Candidate | Assessment |
| --- | --- |
| A: compile selected real OpenMW component code | Earliest achievable. A standard/POSIX-only data subset is available without acquiring dependencies or altering engine sources. Prepare it now; native success remains a separate gate. |
| B: instantiate/start Engine without a world | Not yet small: constructor initializes SDL, go requires content and setup pulls in most subsystems. Needs dependencies plus a deliberate initialization/lifecycle contract. |
| C: minimal scene through actual OpenMW rendering | Desired later graphics milestone, but ResourceSystem/NifOsg/ShaderManager/MWRender bring a much wider closure and shader incompatibilities. Do not relabel the existing manually assembled OSG cube as this milestone. |

**Selected: A, an isolated data-core compilation slice.**
[experiments/ios-openmw-core](../../experiments/ios-openmw-core/README.md) builds
five existing translation units directly: file conversion/opening, constrained
file streams, POSIX file backend and VFS::Manager. Its header closure was inspected
and tested for external includes. It uses C++20, matches device deployment 18.0
and fails closed for non-device default configurations. It does not invoke root
CMake, discover packages, fetch dependencies, create a window/context or start
an engine. This is a temporary source-isolation target, not a supported new engine
architecture or a substitute for the full components target.

The host runtime fixture links those real implementations and exercises file
range/seek behavior, normalized VFS lookup, archive precedence, iteration, error
handling and reset using an original ten-byte fixture. Only its archive adapter
is test scaffolding. Do not link this library together with the broad components
library later: overlapping definitions must be partitioned or the probe retired.

No C++ compilation or runtime execution was possible on the current Windows host.
There is therefore **no claim that any OpenMW code or Engine instance has run on
iPhone, or that this target compiles on Apple**. Three Python contracts passed;
the real-source POSIX C++20 compile/runtime test skipped explicitly.

## 6. Concrete progression toward an OpenMW scene

1. **Review the new target independently of Build #15.** The first concrete build
   change is already present: a standalone static target with the five source
   files. Review its source list and tests. Preserve the nine existing pending
   observer files, and stage only the new core directory/report if choosing to
   advance this milestone separately.
2. **Native compile and host execution gate.** On a hosted macOS runner with
   existing Xcode/CMake, execute the host runtime fixture, build the iPhoneOS
   ARM64 static target, inspect every archive member's device platform/deployment
   metadata and preserve logs/source identity. This needs no ANGLE download. A
   future dedicated opt-in workflow must be independent of the currently failing
   OSG host suite. No workflow was created or triggered in this task.
3. **Execute the same data probe inside a separate UIKit application.** Reuse the
   reviewed Build #14 platform structure and strict IPA validation, bind a bundled
   original fixture path, call data code once and export results. Keep one context
   and swap. Do not copy the dirty Build #15 tree into it implicitly. This step
   needs app packaging/native execution and is not implemented now.
4. **Expand the source closure deliberately.** Add real loose-file archive and
   debug logging, then BSA/ESM/NIF parsing and encoders. Select and pin missing
   dependencies with complete device recipes before acquisition/builds. Verify
   source, binary platform/ABI and licenses; do not substitute SDK/private/host
   libraries by name or weaken validators. Preserve double Bullet/OSG matrix ABI.
5. **Compile the real resource/render slice.** Extend the existing pinned OSG build
   for required components and selected static plugins; export matched headers,
   generated profile configuration and archives. Port the smallest actual
   ShaderManager/ShaderVisitor/SceneManager fixture to ESSL300 with explicit
   attributes/uniforms, one simple material and no advanced FBO/shadow/compute
   paths. Add an original synthetic mesh/image through those actual managers.
   Treat any shader rewrite as an explicit engine change for separate review.
6. **Separate platform ownership from Engine setup.** Propose a host/platform
   interface accepting viewer/embedded context, drawable dimensions, paths,
   controller events and lifecycle callbacks, plus initialize/step/shutdown.
   Keep SDL input decisions separate from GL context ownership. No dummy SDL
   window/context or broad preprocessor alias should conceal missing integration.
7. **Bring up Engine subsystems in stages.** Once a real OpenMW render slice runs,
   build/validate MyGUI, plain Lua or a verified runtime, physics/navigation and
   audio packages. Then initialize Engine through the reviewed platform seam,
   first with controlled content, later imported user game data. Test suspension,
   saves, controller bindings, thermal/memory behavior and sustained performance.

This order does not require proving hardware mip generation before compiling
engine components. Finishing the optional Build #15 observation remains useful
independent diagnostics work, requiring its own test/provenance completion and
native run before it is called validated.

## 7. Validation and files from this task

New files only:

- This report, `docs/ios-port/engine-readiness-audit.md`.
- `experiments/ios-openmw-core/.gitignore`.
- `experiments/ios-openmw-core/CMakeLists.txt`.
- `experiments/ios-openmw-core/README.md`.
- `experiments/ios-openmw-core/tests/core_check.cpp`.
- `experiments/ios-openmw-core/tools/test_core.py`.

No existing engine, experiment, workflow, pin or remote was modified. Existing
Build #15 contents were preserved. Source checks are not CMake configuration,
compiler/linker tests, an unsigned IPA or device execution.

| Local suite | Passed | Failed | Skipped |
| --- | --- | --- | --- |
| New data-core | 3 | 0 | 1 (POSIX C++ runtime check on Windows) |
| Existing unfinished OSG | 96 | 4 | 5 |
| Unchanged ANGLE | 76 | 0 | 1 |
| Unchanged Vulkan | 76 | 0 | 0 |
| Unchanged Zink | 43 | 0 | 0 |

All 36 Python tool files passed AST parsing. JSON, plist-template structure
(with Vulkan's boolean placeholder rendered in memory), new-file whitespace and
documentation-link checks passed. The nine starting file hashes match exactly;
only the six new files above were added. Branch/remotes and the unstaged index
state are unchanged. No failing check is presented as a passing native gate.
