# ANGLE/Metal investigation for the iPhone 16 Plus

Audit date: 2026-11-04. OpenMW source: `495bdc58421a21fec9e7086fc4b48634389a0e1e`, branch `ios-port`, declaring **0.53.0**. This report is the only new implementation artifact from this investigation. No renderer, workflow, dependency, engine or working experiment was changed. The already pending `experiments/ios-zink-caps/.gitignore` change is preserved.

**Recommendation:** first establish a small, explicitly selected **GLES3 -> ANGLE/Metal -> CAMetalLayer** application. This is a shared foundation for both candidate architectures. Then test two isolated OSG configurations: GL2 through GL4ES for compatibility, and GLES3 with explicit ESSL300 shaders for a cleaner long-term renderer. Do not select GL4ES for the full port until current OpenMW shader/GUI/framebuffer fixtures pass. Do not interpret the GLES OSG fixture as an already ported OpenMW renderer.

The preferred long-term candidate is direct GLES3 if its engine adaptation remains manageable: it removes GL4ES's desktop-state emulation and its documented graphics limitations. GL4ES remains a potentially shorter compatibility bridge, particularly because our source already has initialization hooks. Neither approach has been compiled or timed on our phone. There is no measured evidence yet that either is faster or cooler than the Vulkan baseline.

## Evidence and source snapshots

Verified means source inspection or analysis of the supplied local results, not a new native build. Reported project features remain author claims unless the implementation was inspected. Proposed configuration and acceptance steps below are untested.

| Source inspected | Revision / role |
| --- | --- |
| [ANGLE][angle-root] | `6ea96bcca6d7f05199f5565c6d5c4722af7269da`, main, 2026-11-04 |
| [Upstream GL4ES][gl4es-root] | `bc4314d8369f169d3fa81c5ed1b46b3dba4e74a5`, master, 2026-10-30 |
| [xyzz Android][xyzz-build] | `bfd613230ebe57170cbe4966aa8938d54afa6efa`; repository metadata marks it archived; inspected as historical evidence |
| [Sisah2 Android][sisah-build] | `921215447566e8a8b879c88c2c7e442cf7414d2c`, 2026-10-12; current recipe uses a native GLES3 OSG fork and shader-conversion patches |
| [Andiweli Android][andi-build] | `14c354602522423500d31ed657c0bf50bf23d4a0`, 2026-10-28; current recipe selects OpenMW 0.51 and GL4ES adaptations |
| Our OSG fork | `9b384d5439977784e5cd250ff8ff7966928ddd27`, from [extern/CMakeLists.txt](../../extern/CMakeLists.txt); pinned GL configuration and extension lookup were also inspected remotely |

Only repository metadata and selected individual source/patch texts were retrieved. No ANGLE/Chromium, Android, GL4ES, Mesa or OSG checkout/archive or binary dependency was downloaded. Current pinned source was checked directly where cached browser results showed older Android recipes. This distinction matters: Sisah2's present recipe differs materially from its historical GL4ES build.

Raw iPhone exports remain local under the ignored `device-results/` directory; this report contains no copied device UUIDs, signing identifiers or raw diagnostic files.

## What the physical Vulkan results establish

The supplied exports identify Apple A18 GPU / MoltenVK 1.4.2, report complete device queries and zero debug warning/error messages. Validation layers were **not enabled**. The exported audit IDs agree, its requirements are semantically identical to our manifest, and the host comparator reproduces the native nested results. The successful Vulkan cube separately demonstrates textured geometry, depth, controllers and foreground recovery. Neither establishes displayed FPS or sustained whole-game thermal behavior.

The GL2.1 Zink profile fails on absent custom-border-color/border-color-swizzle extensions, `logicOp=false` and `rectangularLines=false`. Their absent extension feature fields remain unknown. Known startup prerequisites, timeline/imageless features and surface usage/queue queries pass. `nullDescriptor=false` affects an optional descriptor-buffer path in Mesa 25.1.9. `drawIndirectCount=false` alone is not an additional GL2.1 blocker because the complete extension-based alternative passes. See the [pinned requirements audit](../../experiments/ios-zink-caps/requirements-audit.md).

These results justify prioritizing a different translation path. They do not prove that every Zink scene is impossible, or that ANGLE implements missing desktop GL behavior. ANGLE/Metal avoids the Zink Vulkan feature contract; OpenMW's compatibility contract must still be implemented above it.

## ANGLE's actual iOS backend

ANGLE's [support matrix][angle-readme] lists iOS Metal and GLES 3.0 on Metal as complete. The Metal column does not establish GLES 3.1/3.2 support. Start with **ES 3.0 / ESSL 3.00**, query the actual device limits/extensions, and reject an incompatible context. Vulkan-backend conformance results in the README are not evidence for the iOS Metal backend.

The pinned [Metal display][angle-display] creates its own Metal device/queue. The [window surface][angle-surface] accepts a supplied `CAMetalLayer` (or adds one to a generic layer), obtains drawables, tracks bounds/content scale and presents through Metal. This is real iOS-capable source, not an inference from macOS. It is a different backend from our MoltenVK renderer: retain the proven UIKit/lifecycle design, but do not pass its Vulkan device/swapchain to ANGLE or run two presenters on one layer.

Select the backend explicitly using `EGL_PLATFORM_ANGLE_ANGLE` with `EGL_PLATFORM_ANGLE_TYPE_ANGLE = EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE`. The [Metal platform extension][angle-metal-ext] documents that selection. Never accept default-backend selection as proof of Metal; log `GL_RENDERER`, vendor, GL/ESSL versions and EGL identity. Do not link Apple's OpenGLES/OpenGL implementation into the first ANGLE app.

ANGLE sets the Metal layer's `framebufferOnly` to false to support operations such as blitting/readback. That does **not** imply mandatory CPU framebuffer readback; the ordinary window path presents its drawable. Our application should perform no readback, but GPU capture must establish actual passes/copies and costs. Do not force the layer back to framebuffer-only behind ANGLE's back, or claim an identical fast path to the native cube.

### Build and packaging uncertainty

The [development guide][angle-setup] describes depot_tools, gclient, GN/Ninja and fetched build dependencies; its explicit iOS example is a Chromium-based **simulator** test build. It is not a validated recipe for our unsigned ARM64 standalone app. A reproducible device dependency artifact is the first build gate, before scene debugging.

The pinned [GN configuration][angle-gni] enables Metal on Apple platforms and has an iOS framework-bundle path. [BUILD.gn][angle-build] also defines `libEGL_static` and `libGLESv2_static`. Important choices:

- Prefer evaluating upstream-generated iOS EGL/GLES framework products for the first app, with their actual names/install names, transitive dependencies and runtime loader verified. Embed them unsigned under the app's Frameworks directory; signing happens locally through the installation workflow.
- Static products are an alternative, but two named `.a` files are not necessarily self-contained: GN public dependencies include the implementation and supporting libraries. Export the complete link closure or build a deliberate aggregate target. `is_component_build=false` alone is not proof of a complete static archive.
- Pin ANGLE and its DEPS/build tools. Select Metal only; disable unneeded Vulkan/SwiftShader/desktop backends and tests where supported by that pin. Verify candidate GN arguments using its declared arguments rather than copying a desktop recipe.
- The [Metal shader build policy][angle-metal-build] does not precompile iOS internal shaders by default; it supports an explicit Metal-toolchain opt-in. If opting in, current source notes Xcode 26's separately installed Metal toolchain. Record which path is used and whether startup compiles internal shaders. Neither configuration has been built here.
- No verified small official iOS binary release asset was identified. Do not silently substitute an arbitrary third-party binary or promise the previous MoltenVK workflow's build time. A future dependency job may need substantially more download space/time; measure that before setting CI budgets.

The runtime implementation exists, but dependency assembly, ARM64 SDK metadata, install names, unsigned framework handling and Sideloadly signing/launch remain untested blockers. No dependency fetch, Metal-toolchain installation or build was executed now.

## Current OpenMW rendering contract

| Area and source | Verified requirement | Consequence |
| --- | --- | --- |
| [Root CMake](../../CMakeLists.txt), lines 15, 60, 290-298 | Legacy desktop OpenGL selection; Apple branch finds the desktop framework; explicit manual GL4ES option | iOS must select the intended provider. Reuse hooks, not the macOS framework discovery. |
| [OSG dependency](../../extern/CMakeLists.txt), lines 93-97, 132 | Our exact fork, GL2; existing double-precision CPU math defaults | GL4ES proof retains this contract. GLES proof rebuilds the same fork/profile consistently rather than mixing generated GL2/GLES headers. |
| [Shader manager](../../components/shader/shadermanager.cpp), lines 520-523; [GUI shaders](../../files/shaders/compatibility/gui.vert), [fragment](../../files/shaders/compatibility/gui.frag) | Defaults to compatibility shaders, GLSL120 builtins and varying/texture2D/gl_FragData usage | ANGLE accepts ESSL, not these desktop shaders unchanged. Existing core shader files are not a completed GLES renderer. |
| [MyGUI renderer](../../components/myguiplatform/myguirendermanager.cpp), lines 96-154 | Legacy client arrays, packed normalized colors, VBO and CPU-pointer paths | GL4ES must translate state faithfully. GLES3 needs generic attributes, matching shader locations, VAO/VBO ownership and removal of the client-memory fallback. |
| [Postprocessor](../../apps/openmw/mwrender/postprocessor.cpp), lines 518-544; [ping-pong canvas](../../apps/openmw/mwrender/pingpongcanvas.cpp), lines 185-220, 362 | Multiple color targets in some configurations, depth/stencil, sampling/render-to-texture and default FBO-zero binds | Test actual format/attachment combinations, not only a screen triangle. Native GLES3 MRT support does not remove GL4ES's own wrapper limitations. |
| [Depth](../../components/sceneutil/depth.cpp), lines 118-131; [lighting](../../components/sceneutil/lightmanager.cpp), lines 363-389 | Reverse-Z requires clip control; clustered lighting requires GLSL430 | Start with existing standard-depth/per-object-lighting fallbacks. GLES3.0 does not provide the compute/SSBO desktop path. |
| [SDL graphics window](../../components/sdlutil/sdlgraphicswindow.cpp), lines 103-177, 214-247 | SDL context creation/current/release/swap; Android/manual path requests an ES context | Requesting ES does not select ANGLE on UIKit. Context ownership and function resolution need deliberate routing. |
| [Input wrapper](../../components/sdlutil/sdlinputwrapper.cpp), lines 220-225, 261-273 | Mobile lifecycle events currently discarded; drawable-size resize propagation exists | Later engine integration must handle lifecycle explicitly and retain pixel-size propagation. Do not inherit Android context-loss assumptions as iOS behavior. |

The pinned OSG [GL configuration][our-osg-gl] contains GLES3 configuration support. Its [Apple extension lookup][our-osg-ext] normally searches process symbols; the static-GL mode uses a separate lookup table. Neither guarantees ANGLE or GL4ES entry points are selected. OSG GLES3 compilation is a dependency test, not evidence that the direct GL calls in OpenMW/MyGUI have been ported.

## Android references: two different strategies

### Historical xyzz: compatibility-layer techniques

The pinned [build recipe][xyzz-build] selects GL4ES v1.1.4, OSG 3.6.5 and an older engine commit. Its OSG configuration retains legacy matrices/vertex arrays/fixed-function support and disables display lists. [GameActivity][xyzz-activity] selects underlying GLES behavior and loads the compatibility library before the engine.

Useful techniques: separate desktop-facing GL from the native context provider, initialize in a controlled order, disable unnecessary display lists, and make graphics settings explicit. Its Android shared-library loader, old dependency versions, touch UI and GLES environment settings are not iOS/ANGLE integration. An Android GLES driver is not equivalent to ANGLE/Metal.

### Current Sisah2: native GLES and conversion work

Fresh inspection of the pinned [recipe][sisah-build] shows `OPENGL_PROFILE=GLES3`, GLAD loading, OSG fork `638f0a1e73687633fd99bf110d04226e78ff69c6`, and engine fork `cdfe3df4e264869804f7fa0d8d4e51ead1a12462`. This is materially different from the older cached GL4ES recipe.

The [GUI patch][sisah-gui] replaces client-state calls with generic attributes and normalized byte colors. The [loader patch][sisah-glad] resolves GLES through SDL. The [shader patch][sisah-spirv] introduces glslang/SPIRV-Cross conversion to ESSL and additional shader/postprocessing changes. These are concrete examples of the scope of a GLES adaptation, not just a CMake switch.

Reuse ideas, not entire patches: audit attribute locations against shader bindings; one patch's attribute comment and actual indices differ. Its remaining CPU-pointer fallback must not be copied into a strict GLES3 VBO/VAO path. The converter can request ESSL320, exceeding the ES3.0 baseline established for ANGLE Metal. Removing unsupported extension declarations or bypassing version checks does not implement their semantics. Additional runtime compiler libraries add startup/cache/battery work. The recipe also contains an unpinned SPIRV-Cross clone, which is unsuitable for our reproducible dependency manifest.

### Current Andiweli: a newer GL4ES branch

The pinned [recipe][andi-build] selects OpenMW 0.51 commit `f4bec41444214a7903bebd178389ca22ca13f646`, a separate GL4ES fork revision `5ac069d82ad8ca2cc3c574484e4c5bad880db83e`, and OSG revision `69cfecebfb6dc703b42e8de39eed750a84a87489`. Its OSG configuration remains legacy GL1-style with display lists disabled. The README's improved graphics claims are author reports, not our iPhone results.

Its [0.51 helper-inlining adaptation][andi-inline] addresses helper-only shader-object linking in that stack. An older [shadow adaptation][andi-shadow] replaces unavailable depth-clamp behavior in the shadow vertex shader. Useful lessons are whole-program shader assembly, explicit GLES precision and workload-specific fallbacks. These changes require testing against our 0.53 shader assembly, depth conventions and actual ANGLE compiler; blanket text replacement or stripped capability guards are not safe reusable techniques.

None of these projects verifies our exact OSG pin + current OpenMW + ANGLE/Metal combination. No Android patch or artwork was copied.

## Architecture comparison

| Issue | OpenMW -> GL4ES -> ANGLE/Metal | OpenMW adapted to GLES3 -> ANGLE/Metal |
| --- | --- | --- |
| Existing behavior | Preserves more legacy interfaces initially; conversion coverage unproven | Explicitly ports shaders, vertex state and unsupported desktop operations |
| Initial work | Smaller engine-facing changes, but nontrivial symbol/loader integration | Larger renderer/GUI/shader changes; smallest OSG GLES demo is still simple |
| CPU overhead expectation | Extra state emulation, possible repacking and shader conversion | Avoids GL4ES layer; still pays OSG traversal, ANGLE validation and Metal translation |
| Shader startup | GL4ES conversion plus ANGLE ESSL-to-MSL/pipeline creation | ANGLE compilation; optional conversion system would add another compiler/cache layer |
| Graphics envelope | Upstream GL4ES documents limited shader conversion, no multiple color FBO attachments and depth/stencil read restrictions | GLES3 supports a broader native modern baseline, but not desktop GL or guaranteed GLES3.1/compute/geometry shaders |
| Maintenance | Smaller early engine diff; long-term compatibility/fork patches and extension routing | Larger initial diff; potentially clearer capability policy and fewer emulation-specific workarounds |
| Enhanced vanilla graphics | Must prove shadows/water/postprocessing against wrapper restrictions | Better candidate for intentional GLES feature budgets, still requiring substantial validation |
| Performance/heat verdict | Unknown | Unknown; fewer layers is a hypothesis, not a benchmark |

GL4ES's [upstream documentation][gl4es-readme] is a limitation checklist, not proof that every downstream fork has identical behavior. Compare each selected fork's implementation before claiming it fixes MRT or shader coverage. Merely asking GL4ES to use a GLES3 context does not automatically add GLES3 features to its desktop-facing emulation.

### The GL4ES symbol-routing gate

ANGLE exports GLES `gl*` entry points; GL4ES exports desktop-compatible `gl*` wrappers. A naive static link can fail with duplicate symbols or bind calls to the wrong implementation. Library filename suffixes and link order are not sufficient symbol isolation.

The required routing is:

1. OpenMW/OSG direct desktop GL calls and extension lookup reach GL4ES.
2. GL4ES's underlying GLES resolver reaches ANGLE, never its own wrappers or Apple's GLES.
3. EGL context/window/swap operations go to ANGLE.

The existing [manual initializer](../../components/sdlutil/gl4esinit.cpp) and GL4ES's [initialization API][gl4es-init] expose callbacks and `gl4es_GetProcAddress`. Configure a context-provider-owned ANGLE resolver before initialization, after its context is current. Desktop extension lookup must use GL4ES's resolver. The existing framebuffer callback uses logical window points; an iOS adapter must supply actual drawable pixels.

Possible implementations are explicit framework-scoped resolution with verified Mach-O bindings, or a controlled symbol-namespaced static build and function table. Neither is verified here. Check core as well as extension entry points; do not assume every provider's `eglGetProcAddress` covers every core symbol. Make symbol-origin checks a pass/fail fixture before adding OSG. Preserve a separate bare-ANGLE target to detect accidental compatibility-layer interception.

## Smallest proposed isolated experiment

Proposed future files: `experiments/ios-angle-smoke/` and `.github/workflows/ios-angle-smoke.yml`. **They are not created by this report.** Use a distinct bundle identifier and retain both working applications unchanged.

The first target needs UIKit/QuartzCore/Metal/GameController, an audited ARM64 ANGLE EGL/GLES artifact and matching headers, a minimal app/Info.plist and two tiny ESSL300 shaders. No OpenMW, SDL, OSG, GL4ES, Mesa, MoltenVK, external shader compiler, game data or texture decoder is required.

Proposed sequence:

1. Create one UIKit-owned `CAMetalLayer`; choose the ANGLE Metal EGL display explicitly and check all extension/API prerequisites.
2. Bind the GLES API; choose an ES3/window configuration; create the layer-backed window surface and ES3 context; make it current. Log actual selected config and renderer identity.
3. Draw a colored triangle using `gl_VertexID` initially, with a changing clear background. Then add a VBO/VAO fixture. Report full shader compilation/link logs and EGL/GL errors. A clear-only fallback must remain explicit.
4. Request 30 Hz callbacks and let the selected EGL implementation manage its presentation. Count successful `eglSwapBuffers` returns separately from CPU callback timing. Label actual display FPS unavailable; EGL success is not a Vulkan-present or scanout counter.
5. Keep PS4 Triangle/Y as clear toggle and Square/X for scene selection as fixtures grow; no touch gameplay controls. Preserve controller reconnect/held-button handling, diagnostics overlay and local Files exports. Ignore new device-result directories when that future experiment is created.
6. Pause callbacks before inactivity, finish outstanding provider-owned work while the context is valid, then unbind/release as appropriate. A one-time lifecycle drain is acceptable; per-frame `glFinish` or CPU readback is not. Rebind/recreate after foregrounding as required. Query surface dimensions in pixels and update viewport/projection after resize.

CI should separate the dependency-artifact gate from app compilation: record immutable ANGLE/DEPS/toolchain identities, build only the required device products, validate actual binaries with `lipo`/`vtool`/`otool`, preserve licenses and build logs, package `Payload/IOSANGLESmoke.app`, reopen/validate the unsigned IPA, and upload it with diagnostics. Retain the `ios-port` push trigger and document default-branch registration for manual dispatch. No signing secrets belong in CI. Frameworks must be unsigned at packaging and their actual rpaths/dependencies verified; adapt packaging checks inside the new experiment without modifying the existing apps.

Use Sideloadly to sign/install the resulting IPA locally only after CI succeeds. Availability of native source paths does not establish that this app or framework package installs successfully; a macOS-only or simulator artifact is not acceptable evidence.

## Roadmap and acceptance gates

| Gate | Deliverable | Required evidence / stop condition |
| --- | --- | --- |
| 0. Dependency | Reproducible iOS ARM64 ANGLE Metal artifact | Correct SDK/platform, complete closure/resources, no unwanted backend or loader fallback. Stop on unresolved standalone build/signing requirements. |
| 1. Bare ANGLE | Triangle + clear; then textured rotating cube/depth | Visible Metal rendering on iPhone; config/identity/errors logged; no readback; controller and Home Screen/orientation recovery. |
| 2. GLES OSG | Same current OSG fork rebuilt for GLES3, procedural scene and ESSL300 | Single-threaded Viewer and an EGL GraphicsWindow adapter; VBO/VAO/indexed cube, in-memory checker and standard OSG camera matrices. One swap owner, not an extra app swap after Viewer. |
| 3. GL4ES routing | Separate desktop-call fixture over the same ANGLE dependency | Verify both resolver directions and direct symbol binding; exercise legacy arrays/matrices, GLSL120 and blend/scissor. Stop on recursion or wrong-provider calls. |
| 4. GL2 OSG | Original GL2 profile + GL4ES, same procedural scene | Match camera/texture/depth/orientation output to GLES OSG, preserving original API conventions rather than hiding conversion errors. |
| 5. Current engine fixtures | Actual current GUI shaders/layout and representative shader-template/FBO workloads | Test packed colors, shader helper assembly, MRT, depth sampling, render-to-texture/blit, shadows/water prerequisites. No full game dependency graph yet. |
| 6. Select architecture | Measured compatibility/overhead matrix and scoped engine proposal | No silent capability overrides. Choose GLES adaptation or bounded GL4ES bridge based on evidence; report exact engine changes before implementing them. |

For the OSG gates, initially use OpenThreads/osg/osgUtil/osgDB/osgGA/osgText/osgViewer with plugins/examples disabled and a procedural texture. Verify the exact fork's transitive dependency closure during its build; no image plugins/game content are needed. Preserve double-precision CPU transforms initially. Use normal OpenGL/OSG projection conventions, not the Vulkan cube's [0,1]-depth/Y-inverted matrix unchanged. Adapt the pinned Apple function resolver explicitly. A custom GraphicsWindow should own EGL current/swap operations; SDL integration belongs after the isolated OSG proof.

A GLES OSG pass demonstrates a possible scenegraph path; the current shader manager, MyGUI and desktop calls still require adaptation. A GL4ES OSG pass demonstrates a narrower compatibility workload; it does not certify postprocessing or the game. Start with standard depth and per-object lighting; add modest graphics improvements only after their actual texture/attachment/shader prerequisites are tested.

Compare both paths in optimized builds at the same drawable size, brightness, power/charging conditions and requested rate. Record warm versus cold compilation, CPU update/cull/draw/swap timing, skipped callbacks, memory and thermal trend over 20-30 minutes. Use Xcode Metal capture/System Trace for drawables, extra passes/copies and GPU/display pacing. Keep GPU/display FPS unavailable when not measured. The native cube's nominal thermal state is a baseline observation, not a battery guarantee for OSG or Morrowind.

## Reuse, remaining uncertainty and next action

ANGLE is BSD-style licensed; upstream GL4ES is MIT; Android engine/launcher patches inherit GPLv3 notices where applicable; OSG carries its OSGPL/file-specific terms. Preserve file attribution and review the exact selected fork and ANGLE DEPS notices before code/binary reuse. No third-party implementation or Android shader pack was imported by this report.

Verified: native iOS Metal source paths, the ES3.0 support claim, relevant current OpenMW interfaces, both Android adaptation strategies, existing iPhone Zink gaps and the need for explicit provider routing. Unknown: standalone ARM64 build details/closure, runtime GL/format limits, current shader conversion accuracy, framework installation, sustained performance and thermal cost. A direct GLES3 port's engine diff and long-term maintenance cost cannot be measured from a triangle alone.

**Recommended next implementation:** limit the next change to Gate 0 plus Gate 1 in a new ANGLE-only experiment: resolve a pinned Metal-only iOS dependency build, compile/package an unsigned app, then validate the bare triangle/clear and lifecycle/controller behavior on the iPhone. Defer GL4ES and OSG until the backend/package is proven. This keeps a failing library build, a symbol-routing issue and a renderer-compatibility failure from becoming one inseparable test.

## Sources

[angle-root]: https://github.com/google/angle/tree/6ea96bcca6d7f05199f5565c6d5c4722af7269da
[angle-readme]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/README.md
[angle-setup]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/doc/DevSetup.md
[angle-gni]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/gni/angle.gni
[angle-build]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/BUILD.gn
[angle-metal-build]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/src/libANGLE/renderer/metal/metal_backend.gni
[angle-display]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/src/libANGLE/renderer/metal/DisplayMtl.mm
[angle-surface]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/src/libANGLE/renderer/metal/SurfaceMtl.mm
[angle-metal-ext]: https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/extensions/EGL_ANGLE_platform_angle_metal.txt
[gl4es-root]: https://github.com/ptitSeb/gl4es/tree/bc4314d8369f169d3fa81c5ed1b46b3dba4e74a5
[gl4es-readme]: https://github.com/ptitSeb/gl4es/blob/bc4314d8369f169d3fa81c5ed1b46b3dba4e74a5/README.md
[gl4es-init]: https://github.com/ptitSeb/gl4es/blob/bc4314d8369f169d3fa81c5ed1b46b3dba4e74a5/include/gl4esinit.h
[our-osg-gl]: https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/GL.in
[our-osg-ext]: https://github.com/OpenMW/osg/blob/9b384d5439977784e5cd250ff8ff7966928ddd27/src/osg/GLExtensions.cpp
[xyzz-build]: https://github.com/xyzz/openmw-android/blob/bfd613230ebe57170cbe4966aa8938d54afa6efa/buildscripts/CMakeLists.txt
[xyzz-activity]: https://github.com/xyzz/openmw-android/blob/bfd613230ebe57170cbe4966aa8938d54afa6efa/app/src/main/java/ui/activity/GameActivity.kt
[sisah-build]: https://github.com/Sisah2/openmw-android/blob/921215447566e8a8b879c88c2c7e442cf7414d2c/buildscripts/CMakeLists.txt
[sisah-gui]: https://github.com/Sisah2/openmw-android/blob/921215447566e8a8b879c88c2c7e442cf7414d2c/buildscripts/patches/openmw/gui.patch
[sisah-glad]: https://github.com/Sisah2/openmw-android/blob/921215447566e8a8b879c88c2c7e442cf7414d2c/buildscripts/patches/openmw/glad.patch
[sisah-spirv]: https://github.com/Sisah2/openmw-android/blob/921215447566e8a8b879c88c2c7e442cf7414d2c/buildscripts/patches/openmw/spirv.patch
[andi-build]: https://github.com/Andiweli/OpenMW-Android/blob/14c354602522423500d31ed657c0bf50bf23d4a0/source/buildscripts/CMakeLists.txt
[andi-inline]: https://github.com/Andiweli/OpenMW-Android/blob/14c354602522423500d31ed657c0bf50bf23d4a0/source/buildscripts/patches/openmw051-final/apply-android-gl4es-core-inline.py
[andi-shadow]: https://github.com/Andiweli/OpenMW-Android/blob/14c354602522423500d31ed657c0bf50bf23d4a0/source/buildscripts/patches/openmw050-final/0007-android-shadow-depth-clamp-fallback.patch
