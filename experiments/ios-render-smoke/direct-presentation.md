# Zink and direct iOS presentation investigation

Date: 2026-11-03. Baseline: our [renderer audit](../../docs/ios-port/renderer-audit.md), OpenMW commit `9666b295d1a4bd46e7a8aed5e305bffc0366734c`, and the reference's Mesa **25.1.9** / MoltenVK **1.4.2** combination. No Mesa/MoltenVK source archive or binary was downloaded during the original investigation; existing reference recipes/patches and individual upstream source files were inspected. Subsequent CI/device progress is recorded below and in the [current smoke instructions](README.md).

**Finding**

Direct Vulkan presentation through MoltenVK to an iOS `CAMetalLayer` is a supported API architecture that does not require CPU framebuffer readback. The `VK_EXT_metal_surface` API accepts the layer, and a `VK_KHR_swapchain` can acquire/present its images. The developer has now observed the clear-only baseline visibly changing colors on a physical iPhone 16 Plus, with an increasing presentation counter and no visible errors. The isolated app now adds a Vulkan triangle pipeline while preserving that clear path. The triangle and its new build steps still need macOS compilation and device confirmation; GPU-capture and timing/thermal qualifications remain separate checks.

**The audited Zink stack cannot use that path unchanged.** Its EGL native-window frontend, Kopper surface dispatch, and generated Vulkan instance extensions lack UIKit/Metal surface support. The donor works around the absence with a surfaceless pbuffer and readback/presentation bridge. Reusing that bridge would not meet this task's direct-presentation requirement. A native UIKit/Metal WSI integration is a real porting task, not a CMake flag or a guarantee inherited from macOS support.

This revises the earlier audit's proposed order: prove raw MoltenVK swapchain presentation first, then decide whether the missing Zink frontend is viable before importing the readback-based reference into our engine.

**MoltenVK mechanism and limitations**

The [Vulkan Metal surface definition][metal-surface] supplies `CAMetalLayer*` to `vkCreateMetalSurfaceEXT`. At the exact MoltenVK revision `db66022459ffb663aa2b50f6b018bc2e124f5edf`, [MVKSurface.mm][mvk-surface] retains the supplied layer and [MVKSwapchain.mm][mvk-swapchain] manages its presentable images/drawables. These are iOS-capable paths, not just AppKit window APIs. The [runtime guide][mvk-guide] documents iOS XCFramework linkage and swapchains.

The original clear-only test needs only instance surface extensions, graphics/present queue support, a supported color-attachment surface format, swapchain creation, synchronization and presentation. The explicit `SMOKE_CLEAR_ONLY=ON` fallback still needs no shader compiler or resources. The new default triangle test adds offline glslang/SPIR-V vertex and fragment shaders and a three-vertex graphics draw before any OpenSceneGraph integration. Neither test needs descriptor indexing, dynamic rendering, timeline semaphores, Zink or an OpenMW Vulkan fork.

The application calls no `vkMapMemory`, image-to-buffer copy, GL readback, staging-buffer upload or CPU pixel conversion. This establishes its source-level intent; it does not certify every internal driver operation as zero-copy. MoltenVK/Metal may perform internal synchronization or GPU work. A real-device Metal capture must confirm the selected swapchain/drawable path and costs. A successful present API return means queued presentation, not proof of visible scanout.

The public MoltenVK build is a Vulkan portability implementation. Extension names, Vulkan version numbers and macOS behavior cannot replace iPhone feature queries. Do not use the private-API release or change capability reports to conceal missing features. The pinned source's `logicOp` depends on private-API configuration, and its robustness2 `nullDescriptor` is false; these are source observations, not fresh measurements of a release binary on our phone. [MVKDevice.mm][mvk-device] is the specific capability source.

**Mesa/Zink iOS build and frontend blockers**

Mesa source inspection is pinned to tag `mesa-25.1.9`. Canonical upstream links below identify the exact files. Direct upstream GitLab raw access was unavailable during this investigation; the tagged files were read through the [Mesa source mirror][mesa-mirror]. This is an access limitation, not a claim that mirror code constitutes a separate supported port. A later dependency build must pin/verify the upstream archive and patch hashes.

| Layer and source | Observed implementation | Consequence on iOS |
| --- | --- | --- |
| [Mesa Meson configuration][mesa-meson] and [build documentation][mesa-build] | Darwin/macOS build cases exist; the documented tested OS list does not establish an iOS UIKit target. | SDK/architecture flags alone do not supply a native window platform, static driver loader or iOS runtime behavior. |
| [EGL platform enum][mesa-egl-enum], approximately lines 48-57 | X11/XCB, Wayland, DRM, Android, Haiku, surfaceless, device and Windows; no UIKit/Metal native window platform. | There is no audited `eglCreateWindowSurface` path that accepts our layer. Even the macOS platform build flag is not an EGL UIKit implementation. |
| [EGL DRI2 initialization][mesa-egl-init], approximately lines 883-910 | Existing native-platform dispatch; no Apple window surface initialization. | A new or extended native-window frontend must carry layer ownership, dimensions and lifecycle into the driver. |
| [Zink Kopper][mesa-kopper], `init_dt_type` and `kopper_CreateSurface`, approximately lines 50-107 | XCB, Wayland and Win32 surface cases; no Metal/iOS case; unsupported types reach an unreachable branch. | Adding a Vulkan loader or passing a layer pointer to an existing case is insufficient. |
| [Zink generated instance support][mesa-instance], approximately lines 45-49 | Surface/headless/XCB/Wayland/Win32 extensions; no `VK_EXT_metal_surface` negotiation. | Extension generation/dispatch and build platform guards also need changes. |
| Reference [Mesa recipe][donor-mesa] and [patch inventory][donor-patches] | Static MoltenVK binding, Darwin DRI plumbing, surfaceless EGL, shader/interop fixes. GLES disabled, desktop GL retained. | An existing downstream iOS build recipe is evidence of porting effort; it does not add a native UIKit Vulkan swapchain frontend. |

The recipe assembles a static Mesa archive from internal build objects, rather than relying on desktop runtime-loaded DRI drivers. That mechanism, Mesa's host code generators, its target/host separation, and iOS filesystem/cache assumptions also need a reproducible build on macOS. LLVM is disabled in the reference; enabling software fallback would not satisfy our Metal presentation gate.

An inspection of live mirror `main` also found no Metal/UIKit cases in the EGL enum or Kopper surface switch. That observation is unpinned and is not used as a guarantee about every later Mesa release. We have not identified an upstream-supported turnkey iOS Zink window-surface recipe.

**Required Vulkan features must be evaluated by Mesa revision**

| Requirement | Mesa/MoltenVK evidence | How to treat it |
| --- | --- | --- |
| `VK_KHR_surface`, Metal surface, swapchain, present queue | Required by this raw Vulkan experiment; MoltenVK implements the relevant APIs. | Missing support is a smoke-test blocker. No alternate backend is substituted. |
| Maintenance1, create_renderpass2, imageless_framebuffer, descriptor_update_template | Marked required in Mesa 25.1.9's [device capability generator][mesa-device]. Core promotions must also be considered. | Evaluate the actual enabled core features/extension equivalents before a Zink build. |
| Timeline semaphores | Hard initialization check in [25.1.9 screen code][mesa-screen]. Pinned MoltenVK source reports support. | Device query and later Zink initialization must agree. Not required or enabled by the clear test. |
| `logicOp`, `fillModeNonSolid`, `shaderClipDistance`, scalar layout, custom border color and line rasterization | [Zink requirements][zink-docs] and pinned screen/device source distinguish base-contract checks, warnings and higher-GL requirements. | Some missing features warn about correctness instead of universally failing startup; do not claim full GL2 correctness from a successful screen creation. |
| Dynamic rendering | Probed by 25.1.9; not an unconditional required extension in its device table. Pinned MoltenVK reports it. | Log/query it; do not needlessly require it for this first smoke. |
| `robustness2.nullDescriptor` | [Mesa 25.2.0][mesa-252] has an explicit initialization failure when absent. 25.1.9 uses it for optional descriptor-buffer paths. Pinned MoltenVK [source][mvk-device] reports false. | Newer Mesa is not automatically a drop-in upgrade. Listing KHR/EXT robustness2 is insufficient: query the individual boolean. No fake limit or private-API workaround. |

The app records advertised extension names, core feature booleans and relevant portability/robustness/border/line features when queryable. This is input to a later revision-specific capability audit, not a full Zink conformance checker. Missing a Zink-only capability must not prevent testing the simpler Vulkan presentation mechanism. Conversely, passing this simpler test must not hide a missing Zink feature.

**A realistic route to direct Zink presentation**

The following is a proposal, not implemented or tested support:

1. **Raw WSI gate (this experiment).** Build against public pinned MoltenVK, run on the standalone signed iPhone app, prove visible clear/present and inspect Metal capture, resize and suspension. Stop on any failure.
2. **Offscreen Zink capability gate.** In a separate target/workspace, build pinned Mesa with the necessary reference iOS build patches and host generators, keep software drivers excluded, initialize desktop GL over a surfaceless pbuffer and log Zink/device/shader results. This can establish Zink compilation and basic feature/shader behavior, but is explicitly **not** direct-presentation acceptance. Do not add CPU readback to make it look like the requested result.
3. **Design a native-window frontend before coding around it.** Decide how a UIKit-owned layer is represented and retained through EGL/Gallium/Kopper, how pixel extent/format and scene lifecycle are conveyed, and who creates/owns the Vulkan instance/device/swapchain. Keep all rendering/presentation on Zink's own synchronized queues. Existing EGL cannot simply adopt the raw smoke app's device and swapchain.
4. **Implement the missing Metal WSI integration in an isolated Mesa fork.** Extend frontend dispatch, Kopper surface types, instance extension generation, platform headers/build guards and native-window lifecycle to call `vkCreateMetalSurfaceEXT`. Add appropriate format/extent/acquire/present handling rather than wrapping a headless pbuffer. This is currently a blocker, not provided by this patch set.
5. **Direct GL window-surface gate.** A minimal desktop-GL clear and then a textured triangle must present through the newly implemented swapchain without `glReadPixels` or CPU staging. Verify queue synchronization, present semaphores, swapchain recreation, background/foreground and memory stability using GPU capture/validation. A GPU texture copy may be a deliberate later design, but must be measured and named; it cannot be called existing native swapchain support.
6. **Current OpenMW contract gate.** Only then add the current pinned GL2 OSG revision, GUI shaders/client arrays and a color/depth FBO. Our OSG pin differs from the donor. Full engine integration and graphics enhancements remain later work.

Exporting a pbuffer's Metal texture to a separate Metal presenter is another possible research direction, but requires explicit cross-API ownership/synchronization and still does not implement the requested Zink Vulkan swapchain frontend. The reference's MetalFX export API is not a ready-made solution. No such workaround is substituted in this experiment.

**What is and is not established now**

- **Verified by source/document inspection:** MoltenVK's Metal surface/swapchain mechanism; missing audited Mesa UIKit/Kopper/extension plumbing; the pinned feature checks; the reference's readback-based presentation design.
- **Baseline progress:** CI compiled the ARM64 iOS application, and the developer reports a successful visible clear-color run on the physical iPhone 16 Plus. That observation does not establish measured FPS, GPU capture, controller support or game performance.
- **Prepared next:** a standalone triangle graphics pipeline, offline shader generation, controller diagnostic-mode toggle, explicit clear fallback, CPU timing/error diagnostics, strict shader/IPA packaging and compile-only GitHub workflow. See [README.md](README.md) for build and acceptance steps.
- **Local validation update:** 69 Python resolver/packaging/TAPI tests pass with the existing bundled CPython 3.12.3 runtime. Python AST, workflow Bash syntax, plist parsing and documentation-link checks pass. Portable C++ timing tests are prepared for macOS CI; no local C++ compiler is available.
- **Not validated for the new triangle:** host glslang build, shader compilation/resource copying, Apple compilation, MoltenVK pipeline/shader execution, controller toggling, synchronization validation, resize/resume, display pacing, energy or thermal impact. Synthetic packaging tests do not establish a device draw.
- **Blocked for direct Zink today:** the native-window/Metal WSI frontend is absent in the audited stack. A raw Vulkan success is necessary evidence for further work, not a resolution of that blocker.

**Sources**

[metal-surface]: https://docs.vulkan.org/refpages/latest/refpages/source/VkMetalSurfaceCreateInfoEXT.html
[mvk-guide]: https://github.com/KhronosGroup/MoltenVK/blob/v1.4.2/Docs/MoltenVK_Runtime_UserGuide.md
[mvk-device]: https://github.com/KhronosGroup/MoltenVK/blob/db66022459ffb663aa2b50f6b018bc2e124f5edf/MoltenVK/MoltenVK/GPUObjects/MVKDevice.mm
[mvk-surface]: https://github.com/KhronosGroup/MoltenVK/blob/db66022459ffb663aa2b50f6b018bc2e124f5edf/MoltenVK/MoltenVK/GPUObjects/MVKSurface.mm
[mvk-swapchain]: https://github.com/KhronosGroup/MoltenVK/blob/db66022459ffb663aa2b50f6b018bc2e124f5edf/MoltenVK/MoltenVK/GPUObjects/MVKSwapchain.mm
[mesa-mirror]: https://github.com/chaotic-cx/mesa-mirror/tree/mesa-25.1.9
[mesa-meson]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/meson.build
[mesa-build]: https://docs.mesa3d.org/meson.html
[mesa-egl-enum]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/egl/main/egldisplay.h
[mesa-egl-init]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/egl/drivers/dri2/egl_dri2.c
[mesa-kopper]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_kopper.c
[mesa-instance]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_instance.py
[mesa-device]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_device_info.py
[mesa-screen]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_screen.c
[mesa-252]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.2.0/src/gallium/drivers/zink/zink_screen.c
[zink-docs]: https://docs.mesa3d.org/drivers/zink.html
[donor-mesa]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/recipes/mesa.sh
[donor-patches]: https://github.com/arjunyerevan95-dot/OpenMWiOS/blob/568323258e0a17f294b91797b68cd29222c374ab/ios-deps/patches/README.md
