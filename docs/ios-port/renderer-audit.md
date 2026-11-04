# iOS renderer reference audit

Audit date: 2026-11-03. Target: an offline native iPhone 16 Plus application, stable 30 FPS, moderate visual improvements, controllers, and low sustained thermal load.

**Recommendation:** first evaluate **desktop OpenGL 2.1 / OSG -> Mesa Zink -> MoltenVK -> Metal**, using the GitHub reference's development-branch integration as a narrowly scoped donor. It preserves the rendering model of our current source and has stronger implementation and development evidence than either reference's GLES path. This is a recommendation for an isolated proof of concept, not acceptance of its performance or a decision to import the port wholesale.

Keep **desktop GL -> gl4es -> GLES -> ANGLE/Metal** as a fallback experiment. ANGLE alone does not implement our desktop GL compatibility API. A direct GLES3/ANGLE port remains a possible longer-term approach, but requires substantial renderer and shader changes. The GitLab reference's Vulkan renderer belongs to another engine lineage and is not present in our source.

**Scope and evidence rules**

Only this report was added to our repository. No engine files, Git branch, dependency installations, or build configurations were changed; no configuration, compilation, packaging, or device execution was performed. Public sources were browsed and shallow reference clones were made outside the repository, without recursive submodule checkout, under `%TEMP%/openmw-ios-renderer-audit-20261103/`:

- `OpenMWiOS`: GitHub default branch.
- `OpenMWiOS-wo40`: GitHub `codex/wo40-zink-touch` development branch.
- `openmw_ios`: GitLab default branch.

Evidence labels used below:

- **Verified source:** observed directly in the cloned tree at the stated commit.
- **Verified public metadata:** observed on the hosting service, such as a successful CI status. This does not verify the artifact's contents or runtime behavior.
- **Reported:** a maintainer's documentation, evidence record, or device feedback; not independently reproduced here.
- **Untested:** no build or device verification in this investigation. Source inspection cannot establish stability, frame rate, energy use, or licensing compliance of a finished binary.

| Snapshot | Revision inspected | Significance |
| --- | --- | --- |
| Our `ios-port` | `9666b295d1a4bd46e7a8aed5e305bffc0366734c` | CMake declares **0.53.0**, despite the initial 0.52 description. Desktop OSG/OpenGL source. |
| GitHub `main` | `ed23e9c9be44893fead05c6b65f8915a6a7b53b2` | README-only tree; describes a 0.51/gl4es bootstrap whose claimed scripts are absent from this snapshot. |
| GitHub `codex/wo40-zink-touch` | `568323258e0a17f294b91797b68cd29222c374ab`, 2026-11-01 | Substantial OpenMW 0.52 tree, Zink iOS port and touch integration; inherited foundation `joedemo42/OpenMW` commit `2931be63bd2147e437a2b077ed6c97f563648a0a`. |
| GitLab `main` | `9f706aaef2b7a909a2cfdc69333bebad6929cd55`, 2026-10-06 | Launcher/build repository that fetches a Vulkan-capable OpenMW fork. GitLab UI marks the project archived/read-only. |

The GitHub default README is not an accurate account of the inspected development branch. Likewise, a branch-tip source snapshot is not automatically the source of an earlier successful binary. References below pin source files to commits; live release/CI pages can change.

**Reference comparison**

| Area | GitHub development branch | GitLab default branch |
| --- | --- | --- |
| Rendering | OSG GL2 / desktop GLSL -> Mesa Zink -> Vulkan -> MoltenVK -> Metal | Separate OpenMW Vulkan renderer -> MoltenVK -> Metal |
| ANGLE/gl4es | Neither is the active renderer in WO40; default-branch README describes older gl4es work | Older EAGL/GLES/gl4es scaffolding remains, but README explicitly says GL/GLES is unsupported |
| Application | SDL2 UIKit application, SDL2main, XcodeGen project, static XCFramework dependencies | SwiftUI/Compose Multiplatform launcher; loads an engine framework and calls its C `main`; mixed static/dynamic dependencies |
| Content | Documents `Config`, `Data`, `Saves`, `Logs`; bundle `engine` resources; one-time INI import | Documents `Data Files`; generated configuration; staged `OpenMWAssets` and Application Support resources |
| Input | Existing SDL controller support plus native device detection and touch overlay; incomplete device validation documented | Custom overlay using SDL internal symbols; controller correctness not demonstrated |
| Build instructions | Shell recipes, CMake engine build, XcodeGen/Xcode; ARM64 device and simulator slices | Gradle orchestrates CMake/vcpkg, then Xcode; ARM64 device and simulator frameworks |
| Runtime evidence | CI build success independently visible; repository records positive device feedback and an unresolved touch issue | Author reports startup and Vulkan initialization; explicitly no verified physical-device rendering |
| Performance evidence | No iPhone 16 Plus 30 FPS/thermal qualification; presentation copy and latency documented | No qualifying gameplay/performance/thermal evidence |
| Reuse basis | GPLv3 engine/port declaration; dependency-specific licenses and patch notices | Root GPLv3 text; provenance/compliance notes require further file-level confirmation; some dependency notices stale |

**GitHub: implementation, build and actual progress**

The [default README][gh-main] claims SDL2, gl4es, static dependencies, bootstrap scripts, and GitHub Actions. At its inspected `main` commit only `README.md` exists: there is no application source, bootstrap script, workflow, or license file in that tree. Its promises must not be counted as delivered code. The development branch is materially different.

The [development iOS guide][gh-ios] describes desktop OpenGL through Zink/MoltenVK. The [Mesa recipe][gh-mesa] enables desktop OpenGL and disables GLES1/GLES2, builds surfaceless EGL and Zink, and assembles a static Mesa archive. The [OSG recipe][gh-osg] retains GL2, disables OSG's native window system, uses Mesa's desktop GL headers, and combines selected OSG libraries/plugins into an archive. This directly matches our legacy rendering model.

Important source pins are:

| Dependency | GitHub recipe pin | Difference or constraint |
| --- | --- | --- |
| Mesa | **25.1.9**, archive SHA-256 recorded in recipe | Ten local patches; recipe attributes the 25.1 pin to newer Zink's `robustness2/nullDescriptor` requirement. This compatibility diagnosis was not reproduced. |
| MoltenVK | **1.4.2**, `db66022459ffb663aa2b50f6b018bc2e124f5edf` | Static iOS slices; own dependencies fetched from its recorded revisions. |
| SDL2 | **2.32.10** | Three local UIKit/EGL/scene/orientation patches. |
| OpenMW OSG | `01cc2b585c8456a4ff843066b7e1a8715558289f` | Different from our `9b384d5439977784e5cd250ff8ff7966928ddd27`; rebase and verify rather than silently downgrade. |

See [MoltenVK recipe][gh-mvk], [SDL recipe][gh-sdl], and [patch inventory][gh-patches]. Other recipes cover Boost, ICU, Bullet, MyGUI, Recast, interpreter-only LuaJIT, FFmpeg, OpenAL Soft, FreeType, image libraries, LZ4 and YAML. A proof does not need this entire game dependency stack.

Two patches solve concrete integration problems:

- [OSG extension lookup patch][gh-osg-proc], patch lines 22-36: resolve desktop GL functions through `eglGetProcAddress` on iOS instead of relying on Apple's symbol lookup and whatever static symbols the app exports.
- [SDL UIKit EGL patch][gh-sdl-egl], patch lines 39-55, 404 and 521-592: preserve the application's `SDL_GL_*` interface while creating a surfaceless EGL desktop-GL pbuffer and presenting it through a Metal view. Its `SDL_VIDEO_STATIC_ANGLE` macro is reused for static EGL plumbing; **it does not mean ANGLE is linked or rendering**.

Presentation is a significant caveat for our goals. `glReadPixels` transfers the rendered frame into a buffer, followed by a Metal buffer-to-texture blit and drawable presentation. Async PBO/fence operation presents the preceding frame; persistent mappings can avoid a CPU copy, but do not eliminate the transfer or extra frame of latency. The patch contains author-reported M1 iPad throughput numbers; these are not an independently reproduced benchmark and do not establish our target's thermal behavior. [Mesa patch 0010][gh-interop] exports Metal objects for [MetalFX processing][gh-metalfx]; it does **not** replace SDL's presentation path with direct drawable rendering.

The [application project][gh-project] defines an ARM64 iOS 18+ application, static dependency XCFrameworks, Apple frameworks, bundled engine resources and license staging, and linker retention for static registration. The [toolchain][gh-toolchain] isolates target dependency roots/pkg-config and provides Mesa headers. [Paths][gh-paths] and [first launch][gh-firstlaunch] supply sandbox layout and INI import. The [FFmpeg recipe][gh-ffmpeg] disables network support, consistent with local offline playback; initial source/dependency downloads still require network access. The guide's example clone command still names the upstream donor, so reproduce from a pinned audited revision rather than following that command blindly. Its Xcode 27.1/macOS 27 setup is a documented reference environment, not a toolchain tested by this audit.

There is useful platform code, but no complete lifecycle qualification: [engine.cpp][gh-engine] has iOS lifecycle persistence handling, while the SDL input wrapper still ignores mobile lifecycle events and [platform.mm][gh-platform] adds memory/thermal logging and device policy. The increased-memory-limit entitlement is requested by the app; whether a later signing method grants it is not established. Do not assume this port's iPad-oriented UI, 60 FPS default, or entitlement dependence suits our phone/thermal budget.

Development evidence must be separated by revision:

- **Verified public metadata:** [CI run 41200954123][gh-run] succeeded on 2026-10-31 for `f4d9f9d8d6bcba1b3bc59201724aab62627aaa4e`, with an uploaded WO40 artifact. Authenticated logs and artifact bytes were not downloaded/verified in this audit.
- **Reported in source:** [WO40 report][gh-report] and [validation record][gh-validation] describe integrated compilation/linking, unsigned IPA/dSYM packaging, artifact hashes and input contract tests. Those tests do not run UIKit or the GPU.
- **Reported device feedback:** the same report records installation through LiveContainer and positive feedback on 2026-11-01, alongside inability to aim with the same finger holding Attack. Device model, native standalone signed-install behavior, detailed suspend/resume/controller checks and sustained performance were not established here. LiveContainer feedback does not by itself qualify our intended application lifecycle.
- **Separate older lineage:** [Development Build 67][gh-release67] advertises an unsigned iOS 16.3+ IPA from `457ab881442302a9bd59435c1878ed4e72f6e52b`. It is not evidence that WO40's iOS 18+ Zink source is that binary, nor a current performance baseline.

**GitLab: implementation, build and actual progress**

The [README][gl-readme] reports OpenMW 0.52 builds, content discovery and Vulkan initialization, but explicitly says rendering has not been verified on a physical device. Simulator startup is blocked by the Vulkan renderer's bindless descriptor/update-after-bind limits, inter-stage component requirements and optional features. Touch, movies and background behavior are unfinished. No checked-in IPA, device capture, result bundle or build log was found in the inspected tracked tree; the build/startup statements remain author reports.

The [engine build recipe][gl-engine], lines 123-125, fetches `OursCodeur/openmw` branch **`clockwork-alpha`**, not a fixed engine commit. Our tree contains no corresponding Vulkan renderer. Its glslang/MoltenVK approach would require adopting/rebasing that renderer and its feature requirements, rather than linking a graphics library to our current source.

The [top-level native CMake][gl-cmake] uses vcpkg plus OpenMW and local overlays, with `master` defaults for vcpkg and the OpenMW dependency overlay. It pins MoltenVK 1.4.2 but builds/downloads it during configuration; merely configuring this reference would perform work outside this audit's scope. The OSG port selects another commit, `638f0a1e73687633fd99bf110d04226e78ff69c6`, with GLES3/iPhone/static settings. Device/simulator target selection and framework staging are useful examples; the moving refs prevent a fully frozen dependency graph as supplied.

Specific blockers and misleading remnants:

- [MoltenVK sampler patch][gl-sampler] changes the reported Tier2 sampler limit to 1024. The CMake comment contrasts stock 16 with the renderer's required 47. Changing reported capability is not evidence the complete renderer works on the iPhone; validate actual binding and shader behavior before considering this patch.
- [Swift launcher][gl-launcher], lines 235-246 and 285-301, still creates an EAGL bootstrap context and sets legacy GLES/gl4es environment options despite selecting Vulkan. Older GLES/MyGUI/framebuffer patches remain. This mixed scaffolding does not demonstrate a supported GLES renderer.
- The launcher loads the bundled engine with `dlopen`, finds C `main` and takes over the main thread. It also bypasses intro movies to avoid playback stalls. This is startup scaffolding, not a completed lifecycle/video design.
- The [overlay][gl-overlay] uses SDL internal input functions resolved with `dlsym`; the SDL port exposes internal symbols. That creates version coupling and does not demonstrate external-controller correctness.
- The [LuaJIT port][gl-luajit], lines 69-76, forces JIT-related configuration and assumes failed executable-memory allocation will leave an interpreter. Do not inherit that unvalidated strategy; use an intentionally interpreter-only iOS build.

Build instructions require macOS/Xcode, CMake 3.22.1+, Git/download utilities and a JDK. Gradle tasks build native device/simulator libraries; Xcode embeds framework wrappers for the engine, SDL2, OpenAL and COLLADA with staged assets. Signing defaults must be replaced with one's own settings. The launcher uses Foundation sandbox paths and Files sharing; no security-scoped external-directory workflow was verified. These are useful design references, not a drop-in build for our revision.

**License and reuse assessment**

This is a source-license/provenance check, not certification of a distributed application. No reference code was copied into the engine. Preserve authorship, modification notices, applicable source obligations and dependency notices for any later selective reuse.

| Material | Checked basis | Reuse position |
| --- | --- | --- |
| Our engine | [README](../../README.md), [LICENSE](../../LICENSE): GPLv3 | Keep the existing license and notices. |
| GitHub default branch | No license/source files in the inspected README-only tree | Do not infer a reusable implementation or license grant from its description. |
| GitHub development engine/port | [GPLv3 LICENSE][gh-license], README declaration and [notice index][gh-notices] | Candidate for selective reuse within our GPLv3 engine; preserve donor lineage and check copied-file notices. Root licensing is not proof of every asset's provenance. |
| GitLab launcher/patches | [GPLv3 LICENSE][gl-license]; [release checklist][gl-compliance] specifically calls for confirming coverage of original Swift/Kotlin/patches | Candidate subject to file-level scope/provenance confirmation. Avoid wholesale import of assets or code with unclear origin. |
| SDL modifications | Added SDL files carry zlib-style notices in the GitHub patch | Preserve notice, origin and alteration marking; retain patch attribution. |
| Mesa/Zink | [Mesa licensing][mesa-license]: mainly MIT with per-file terms; donor recipe stages MIT, Apache-2.0, BSL-1.0 and individual notices | Audit the actual selected source/archive contents, not just the library name. |
| MoltenVK | [1.4.2 LICENSE][mvk-license]: Apache-2.0; recipe lists embedded dependency license files | Preserve applicable notices and inspect bundled components at the selected revisions. |
| OSG | [Upstream OSG license][osg-license]: OSGPL/LGPL-based with exceptions and separate file notices | Existing dependency, but donor/current fork revisions differ. Exact fetched fork contents and relevant file licenses still need checking before redistribution. |
| ANGLE / gl4es alternative | [ANGLE LICENSE][angle-license]: BSD-style three-clause; [gl4es LICENSE][gl4es-license]: MIT | Suitable license families to evaluate with GPLv3; retain notices and audit bundled subcomponents at pinned revisions. |

The [GitLab third-party notice file][gl-notices] still mentions gl4es and an absent `buildscripts/build_ios.sh`, while its current README describes Vulkan. It is not an exact current dependency/binary manifest. GitHub has more explicit license staging, but the resulting IPA was not inspected here. Static LGPL components such as FFmpeg/OpenAL and OSG file exceptions require checking the actual linkage and source/relink obligations. Do not adopt either project's distribution-compliance claims as already satisfied for our app; assets/fonts have separate notices.

**Compatibility with our source and renderer choice**

The following are verified in our current checkout:

| Local source reference | Finding and consequence |
| --- | --- |
| [Root CMake](../../CMakeLists.txt), lines 290-298; [components CMake](../../components/CMakeLists.txt), line 620 | Desktop OpenGL discovery/linking on Apple must be separated from macOS and supplied by the selected compatibility library. |
| [Dependency CMake](../../extern/CMakeLists.txt), lines 97 and 132 | GL2 OSG, pinned to `9b384d5...`; the donor OSG patches need inspection/reapplication to this revision. |
| [Shader manager](../../components/shader/shadermanager.cpp), lines 520-523 | Defaults to `compatibility/`; core shader selection remains TODO. Merely finding `core/` shader files is not a GLES implementation. |
| [GUI shaders](../../files/shaders/compatibility/gui.vert), [fragment shader](../../files/shaders/compatibility/gui.frag); [GUI renderer](../../components/myguiplatform/myguirendermanager.cpp), lines 96-154 | GLSL 1.20 builtins and direct legacy client arrays need desktop compatibility, conversion, or rewriting. |
| [SDL graphics window](../../components/sdlutil/sdlgraphicswindow.cpp), lines 103-177 and 214-247 | SDL owns context/current/swap operations. Donor SDL EGL integration fits this interface; normal UIKit GL context creation does not select ANGLE/Metal. |
| [gl4es initialization](../../components/sdlutil/gl4esinit.cpp), lines 17-32 | Existing manual hooks make a fallback plausible, but use window points for framebuffer size and SDL's resolver for underlying GLES. ANGLE routing is not implemented. |
| [Canvas](../../apps/openmw/mwrender/pingpongcanvas.cpp), lines 220 and 362 | Hardcoded default FBO zero matters especially for native Apple EAGL's nonzero framebuffer. Verify EGL/pbuffer behavior rather than assuming all paths are correct. |
| [Lighting](../../components/sceneutil/lightmanager.cpp), lines 363-389; [depth](../../components/sceneutil/depth.cpp), lines 118-131 | Existing lighting/depth fallbacks can exclude desktop compute/clip-control requirements initially. |
| [Ripples](../../apps/openmw/mwrender/ripples.cpp), lines 42-83 | Apple already avoids compute ripples; fragment fallback still needs render-target validation. Leave ripples disabled in the first proof. |

| Candidate | Current-source change burden | Decision |
| --- | --- | --- |
| Desktop GL -> patched Mesa/Zink -> MoltenVK -> Metal | Keep GL2/GLSL120/MyGUI; rebase OSG lookup and SDL EGL/presentation patches, isolate CMake and platform glue | **First proof candidate.** Most concrete reusable iOS integration, but custom patch maintenance and readback power cost are unresolved. |
| Desktop GL -> gl4es -> GLES -> ANGLE/Metal | Keep much legacy code, but route all desktop symbols to gl4es and all GLES symbols to ANGLE; validate converted shaders and missing features | **Fallback experiment.** Existing hooks help, but neither audited current branch proves this exact stack. |
| Native GLES3 -> ANGLE/Metal | Rework shaders, vertex input and legacy state throughout OSG/OpenMW/GUI; add EGL Metal surface integration | Potential longer-term path; not the smallest first proof. |
| GitLab Vulkan fork -> MoltenVK | Import another renderer and satisfy its bindless/device requirements | Defer; no verified physical-device rendering and substantial engine divergence. |
| Direct Metal backend | Replace or abstract substantial OSG rendering/shader/resource behavior | Defer; largest scope. |
| Native Apple OpenGL ES | Still needs gl4es or GLES renderer changes and EAGL framebuffer/lifecycle handling | Diagnostic fallback only; [deprecated API][apple-gles], not the preferred foundation. |

[ANGLE's support matrix][angle-readme] confirms GLES2/3 on Metal/iOS; it does not offer desktop compatibility GL or promise Metal GLES3.1/compute. Its [Metal EGL extension][angle-metal] and [surface implementation][angle-surface] provide a real Metal-backed presentation route. [gl4es documentation][gl4es-readme] lists OpenMW/iOS uses, but also limited GLSL conversion, multiple-render-target and texture/readback limitations. None establishes compatibility with our current shaders. OSG desktop extension resolution would additionally have to reach gl4es wrappers, rather than bypassing conversion into raw ANGLE entry points.

[Upstream Zink documentation][zink-docs] describes desktop GL on Vulkan and experimental macOS support; that is not an upstream guarantee for this custom iOS stack. [MoltenVK][mvk-readme] provides Vulkan on Metal, not GL by itself. The recommendation favors the reference's concrete integration evidence over speculation about API translation overhead. No measurement currently establishes which candidate is fastest or coolest on the iPhone 16 Plus.

**Smallest rendering proof of concept proposed for the next phase**

Create an independent test application in a separate workspace. Do not initially build `openmw`, the launcher, the full `components` library, navigation, audio, Lua, game content or MetalFX. Start with pinned Mesa 25.1.9, MoltenVK 1.4.2 and SDL2 2.32.10; record hashes and patch attribution. Retain Mesa patches 0001-0009 and SDL patches 0001-0003 as the reference baseline before attempting to reduce that patch set. Mesa 0010 is for MetalFX and can stay outside the proof if no selected build glue references its added interop API. Rebase OSG patch 0001 onto our pinned OSG revision; add the image-discovery patch 0002 only if image plugins enter the fixture. A donor-OSG-only success is useful diagnosis but not acceptance for our revision.

1. **Surface and presentation gate.** Minimal SDL UIKit app using the donor EGL backend; render a rotating, textured desktop-GL object into the pbuffer and present through Metal. Log GL/EGL/Vulkan renderer/version/extension information and the chosen transfer path. Capture Metal GPU work to exclude software or unintended Apple GLES rendering. Verify dimensions, orientation and resize. Keep one window/context and a bounded number of frames in flight.
2. **Current rendering contract gate.** Add minimal OSG libraries and the rebased `eglGetProcAddress` patch. Render legacy vertex arrays/matrix state with a depth buffer, then the current GUI shader pair with MyGUI-format vertices, alpha blending and scissoring. Instantiate actual current shader templates/imports with recorded definitions rather than replacing them with hand-written GLES shaders. Render to a small color/depth FBO and sample/blit back to the drawable; check completeness and visual output. This is the smallest meaningful compatibility proof; a GLES triangle alone would not test our blockers.
3. **Lifecycle and pacing gate.** Schedule at 30 Hz without busy-waiting; do not assume the donor's stored swap interval enforces 30 FPS. Stop submission before backgrounding, reset timing/input on resume, and repeat lock/unlock/background cycles. Keep a simple controller-driven rotation or input indicator to validate event delivery/reconnection without importing the full controls overlay.
4. **Bounded device measurement.** On the actual iPhone 16 Plus, run an optimized standalone signed build at a modest render size, for example 1280x720, and at drawable size. Record frame-time percentiles, CPU/GPU time, presentation/readback stalls, memory, thermal-state changes and energy observations for 20-30 minutes with stated brightness, power mode, charging state and ambient conditions. The lower-resolution RGBA transfer alone represents about 111 MB/s at 30 FPS per full-frame transfer, before other copies; this is an arithmetic estimate, not measured bandwidth or power.

Acceptance: correct OSG/current-GUI/FBO output on Metal, repeatable 30 Hz delivery without recurring missed 33.3 ms deadlines after warm-up, bounded memory, successful suspend/resume, controller reconnect, and documented presentation cost. Log thermal state and throttling trends; this synthetic workload cannot establish whole-game 30 FPS or low heat. If readback dominates, evaluate a direct Metal-texture presentation experiment or the ANGLE/gl4es fallback **before** committing to a full port. Mesa's MetalFX export is useful reference material, not an already implemented direct-presentation solution.

Only after these gates pass add one user-supplied vanilla NIF/DDS and actual MyGUI integration, followed by an interior/exterior engine scene. Validate S3TC/DDS fallback memory, terrain, water, maps and modest shadows individually. Texture filtering and conservative resolution are more appropriate first enhancements than compute lighting, extensive reflections or heavy post-processing.

**Windows versus macOS work**

| Work | Windows | macOS/Xcode/device |
| --- | --- | --- |
| Source/license audit, patch rebase planning, isolated harness source, dependency manifests and shader fixtures | Can prepare and review | Review remains useful |
| Generic desktop GL/OSG fixture checks | Possible later with an existing Windows environment; not performed here | Does not substitute for iOS |
| iOS dependency binaries, Objective-C/UIKit linkage, XCFrameworks, signing and archive | Cannot validate locally with the supported Apple toolchain | Required; a remote Mac/CI can compile |
| Metal capture, readback cost, lifecycle/audio integration and thermal behavior | Can analyze exported evidence | Actual iPhone required; simulator is not an acceptance substitute |

**Remaining blockers and confidence**

- **Verified:** our GL2/GLSL120/GUI contract; GitHub's implemented Zink/SDL/OSG bridge and pins; GitLab's divergent Vulkan recipe and unverified-device status; repository-level licenses and notice mechanisms.
- **Verified metadata, limited scope:** GitHub CI success and artifact listing; not a fresh reproduction or artifact audit.
- **Reported only:** GitHub positive device use, donor iPad performance, GitLab builds/startup, and the diagnosis behind Mesa/MoltenVK capability pins.
- **Untested:** patches applying to our newer OSG/0.53 source, actual shader/FBO/texture coverage, static symbol retention, standalone signed installation, offline game completeness, reliable controllers/lifecycle, stable game 30 FPS, battery and thermal impact.
- **Before code reuse:** confirm copied-file provenance and exact dependency license contents. Before engine changes: complete the isolated renderer proof. Before a full port commitment: measure representative game scenes on the intended phone.

**Reference sources: repository snapshots pinned; upstream documentation retrieved 2026-11-03**

[gh-main]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/ed23e9c9be44893fead05c6b65f8915a6a7b53b2/README.md
[gh-ios]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios/README.md
[gh-mesa]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/mesa.sh
[gh-mvk]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/moltenvk.sh
[gh-sdl]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/sdl2.sh
[gh-osg]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/osg.sh
[gh-patches]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/patches/README.md
[gh-osg-proc]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/patches/osg/0001-glextensions-egl-proc-address-on-ios.patch
[gh-sdl-egl]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/patches/sdl2/0002-uikit-desktop-opengl-via-egl.patch
[gh-interop]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/patches/mesa/0010-gl-interop-metal-objects-and-ordered-callback.patch
[gh-metalfx]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/apps/openmw/ios/metalfx.mm
[gh-project]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios/project.yml
[gh-toolchain]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios/openmw-toolchain.cmake
[gh-paths]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/components/files/iospath.cpp
[gh-firstlaunch]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/apps/openmw/ios/firstlaunch.cpp
[gh-ffmpeg]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/ffmpeg.sh
[gh-engine]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/apps/openmw/engine.cpp#L94
[gh-platform]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/apps/openmw/ios/platform.mm
[gh-report]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/Evidence/WO-040/report.md
[gh-validation]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/Evidence/WO-040/validation.md
[gh-license]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/LICENSE
[gh-notices]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios/licenses/README.txt
[gh-run]: https://github.com/arjunyerevan95-dot/OpenMWiOS/actions/runs/41200954123
[gh-release67]: https://github.com/arjunyerevan95-dot/OpenMWiOS/releases/tag/ios-fast-67
[gl-readme]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/README.md
[gl-engine]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/composeApp/src/commonMain/cpp/openmw/CMakeLists.txt
[gl-cmake]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/composeApp/src/commonMain/cpp/CMakeLists.txt
[gl-sampler]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/composeApp/src/commonMain/cpp/patches/moltenvk-tier2-sampler-limit.patch
[gl-launcher]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/iosApp/iosApp/OpenMWLauncher.swift
[gl-overlay]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/iosApp/iosApp/ComposeHost.swift
[gl-luajit]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/composeApp/src/commonMain/cpp/vcpkg-extras/ports/luajit/portfile.cmake
[gl-license]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/LICENSE
[gl-compliance]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/RELEASE_COMPLIANCE.md
[gl-notices]: https://gitlab.com/duron27/openmw_ios/-/blob/9f706aaef2b7a909a2cfdc69333bebad6929cd55/THIRD_PARTY_NOTICES.md
[angle-readme]: https://github.com/google/angle/blob/main/README.md#level-of-opengl-es-support-via-backing-renderers
[angle-metal]: https://github.com/google/angle/blob/main/extensions/EGL_ANGLE_platform_angle_metal.txt
[angle-surface]: https://github.com/google/angle/blob/main/src/libANGLE/renderer/metal/SurfaceMtl.mm
[angle-license]: https://github.com/google/angle/blob/main/LICENSE
[gl4es-readme]: https://github.com/ptitSeb/gl4es/blob/master/README.md
[gl4es-license]: https://github.com/ptitSeb/gl4es/blob/master/LICENSE
[zink-docs]: https://docs.mesa3d.org/drivers/zink.html
[mesa-license]: https://docs.mesa3d.org/license.html
[mvk-readme]: https://github.com/KhronosGroup/MoltenVK
[mvk-license]: https://github.com/KhronosGroup/MoltenVK/blob/v1.4.2/LICENSE
[osg-license]: https://github.com/openscenegraph/OpenSceneGraph/blob/master/LICENSE.txt
[apple-gles]: https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/OpenGLES_ProgrammingGuide/
