# iOS Vulkan triangle and presentation smoke test

This is an independent device application, not an OpenMW build target. It preserves the working **Vulkan -> MoltenVK -> CAMetalLayer swapchain presentation** path and adds a three-vertex graphics-pipeline draw over the changing clear color. GLSL vertex and fragment shaders are compiled to SPIR-V before packaging. Vertex positions and colors come from `gl_VertexIndex`; no vertex buffer, descriptors, textures, depth attachment or optional Vulkan device feature is needed. There is no SDL, Mesa, Zink, OpenGL, framebuffer readback or CPU pixel transfer. A UIKit diagnostics label remains above the Metal layer.

**Status: the existing clear-color app has run on a physical iPhone 16 Plus.** The developer reports visible changing colors, an increasing presentation counter throughout the recording, and no visible errors. This is evidence of the baseline's visible presentation, not a measured FPS result or a thermal qualification. The new triangle, shader compilation, controller toggle and timing diagnostics still require the next macOS build and physical-device run. They have not been validated by the earlier recording.

Local Python tests run on Windows using an existing bundled CPython 3.12.3 runtime and standard library, invoked through its C API without installing Python. The `python`/`python3` commands on PATH are Microsoft Store shortcuts. The Apple SDK and Xcode are unavailable locally. A full GitHub Actions schema/actionlint check is not available locally.

The investigation in [direct-presentation.md](direct-presentation.md) explains why raw Vulkan presentation is a reasonable first gate, while direct **Zink** presentation remains blocked on missing UIKit/Metal native-window integration. Do not interpret a successful clear test as a working Zink/OpenMW port.

**Files and dependencies**

- `src/main.mm`: UIKit scene lifecycle, CAMetalLayer-backed view, Vulkan capability/error logging, FIFO swapchain, clear/triangle commands, submit/present, controller mode selection, and display callbacks requesting 30 Hz.
- `src/FrameTiming.hpp` and `tests/frame_timing.cpp`: portable timing accumulation and host regression tests, without Apple or Vulkan dependencies.
- `shaders/triangle.vert` and `shaders/triangle.frag`: vertex positions/colors and interpolated fragment color, compiled offline to the two bundled `.spv` files.
- `CMakeLists.txt` and `Info.plist.in`: standalone ARM64 iOS device application, deployment target 18.0, explicit triangle/clear build mode, normal signing or explicitly unsigned compilation.
- `tools/resolve_moltenvk.py`: selects a unique static ARM64 iOS **device** archive and matching headers by XCFramework metadata; fails on missing/ambiguous inputs. It reads metadata, not dependency code. Python 3.10+ standard library only.
- `tools/test_resolve_moltenvk.py`: synthetic host tests for device/simulator distinction, ambiguous inputs, missing files and metadata paths. No SDK or real binary required.
- `tools/package_ios.py` and `tools/test_package_ios.py`: unsigned app/dependency/IPA validation and standard-library ZIP packaging, with synthetic Mach-O/SDK/archive tests. No signing or networking.
- [Build and packaging workflow](../../.github/workflows/ios-render-smoke.yml): a path-filtered `ios-port` push or eligible manual dispatch can trigger it. No PR trigger, signing, installation or device run.

Required for a device build: macOS with Xcode and its iOS SDK, CMake 3.24+, Python 3.10+, and a **previously obtained public MoltenVK 1.4.2 iOS distribution** with static `MoltenVK.xcframework` and corresponding Vulkan headers. Triangle builds also require a host glslang shader compiler. Do not use the macOS MoltenVK archive, private-API build, a simulator slice, or unrelated Vulkan headers. Static linking requires no Vulkan loader/ICD installation. The app links UIKit, Foundation, QuartzCore, Metal, CoreGraphics, IOSurface and GameController; it does not link AppKit, IOKit or OpenGLES.

The pinned public asset is [MoltenVK-ios.tar](https://github.com/KhronosGroup/MoltenVK/releases/expanded_assets/v1.4.2), about 32.9 MB, for source revision `db66022459ffb663aa2b50f6b018bc2e124f5edf`. Its published archive SHA-256 is:

```text
b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1
```

No dependency fetch occurs in the experiment's CMake configuration. The baseline CI/device result establishes that its selected MoltenVK library linked and launched for that build. The resolver still inspects `Info.plist` instead of assuming archive paths; missing or ambiguous inputs remain blockers. Its metadata check is not a Mach-O architecture verifier; the Apple linker and CI `lipo` check remain necessary.

CI builds its host shader compiler from [glslang 15.1.0, revision `1062752a891c95b2bfeed9e356562d88f9df84ac`](https://github.com/KhronosGroup/glslang/commit/1062752a891c95b2bfeed9e356562d88f9df84ac). Building this compiler from source requires CMake 3.27+, while the experiment itself requires 3.24+. It builds only `glslang-standalone`, with external projects, optimizer, HLSL, tests and installation disabled. This avoids a full Vulkan SDK or SPIRV-Tools download. The compiler runs on the Mac during the build and is not linked or bundled into the iOS app. Use the same pinned source for reproducible local shader generation; the exact host-build commands are in the [workflow](../../.github/workflows/ios-render-smoke.yml).

**macOS/Xcode build steps**

These commands are instructions for later execution, not commands run in this investigation. Have the matching dependency distribution and a native macOS `glslangValidator`/`glslang` executable available first; point `MOLTENVK_ROOT` at the extraction directory or the specific static `MoltenVK.xcframework` if there are multiple copies. `SMOKE_GLSLANG_VALIDATOR` identifies a **host** compiler, not a program to execute on iOS. CMake can also find it on PATH. Replace the paths, team and bundle ID with your own. Run from the OpenMW repository root, without invoking its root CMake configuration:

```sh
python3 -m unittest discover -s experiments/ios-render-smoke/tools -p 'test_*.py' -v
c++ -std=c++17 -Wall -Wextra -Werror experiments/ios-render-smoke/tests/frame_timing.cpp -o /tmp/ios-smoke-timing-tests
/tmp/ios-smoke-timing-tests

cmake -S experiments/ios-render-smoke -B experiments/ios-render-smoke/build -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DMOLTENVK_ROOT=/absolute/path/to/extracted/MoltenVK \
  -DSMOKE_GLSLANG_VALIDATOR=/absolute/path/to/host/glslangValidator \
  -DSMOKE_DEVELOPMENT_TEAM=YOUR_TEAM_ID \
  -DSMOKE_BUNDLE_ID=com.example.ios-render-smoke

open experiments/ios-render-smoke/build/IOSRenderSmoke.xcodeproj
```

In Xcode, select the **IOSRenderSmoke** scheme and connected iPhone 16 Plus, verify your signing team/bundle ID, enable Developer Mode on the phone if needed, and build/run. A signed standalone installation is the acceptance target. Do not substitute LiveContainer or a simulator result for this test.

For compile-only work, use a separate build directory with `-DSMOKE_UNSIGNED=ON` and no team:

```sh
cmake -S experiments/ios-render-smoke -B experiments/ios-render-smoke/build/unsigned -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DMOLTENVK_ROOT=/absolute/path/to/extracted/MoltenVK \
  -DSMOKE_GLSLANG_VALIDATOR=/absolute/path/to/host/glslangValidator -DSMOKE_UNSIGNED=ON
cmake --build experiments/ios-render-smoke/build/unsigned --config Release --target IOSRenderSmoke -- CODE_SIGNING_ALLOWED=NO
```

The build compiles both GLSL stages using `-V --target-env vulkan1.0`, then copies `triangle.vert.spv` and `triangle.frag.spv` to the application bundle. No runtime shader compiler is bundled. A missing host compiler or failed shader compilation stops the build. To build the baseline independently, use the same device configuration in a fresh directory, add `-DSMOKE_CLEAR_ONLY=ON`, and omit `SMOKE_GLSLANG_VALIDATOR`. Keep this directory separate from the triangle build so its app and artifacts cannot be confused.

The resulting unsigned `.app` needs signing before installation. To package it into the same unsigned IPA produced by CI:

```sh
EXPERIMENT=experiments/ios-render-smoke
app=$(find "$EXPERIMENT/build/unsigned" -type d -name IOSRenderSmoke.app -print -quit)
python3 "$EXPERIMENT/tools/package_ios.py" --app "$app" \
  --sdk "$(xcrun --sdk iphoneos --show-sdk-path)" \
  --output "$EXPERIMENT/artifacts/IOSRenderSmoke-unsigned.ipa" \
  --report "$EXPERIMENT/artifacts/ipa-validation.json"
```

This is ZIP packaging, not Xcode signing or export. It refuses signed/profile-bearing input instead of stripping or replacing signatures.

**Expected behavior and deliberate limits**

The default build should show an interpolated-color triangle over the existing slowly cycling background. The pipeline uses a triangle list, one color attachment, one sample, no culling, no blending and dynamic viewport/scissor. Each frame binds that pipeline and records `vkCmdDraw(3, 1, 0, 0)` inside the existing render pass. The graphics pipeline is rebuilt with the render pass when the swapchain is recreated; temporary shader modules are destroyed after pipeline creation. The existing submission and presentation synchronization remains in place.

An extended gamepad's **Y/top face button** toggles triangle and clear-only modes. The smoke test renders without a connected controller; it has no touch buttons or touchscreen gameplay interface. Controller support here selects a diagnostic mode and does not implement OpenMW input handling. On a triangle build, Xcode's launch argument **`--clear-only`** starts with the baseline clear path and skips triangle-pipeline creation. For a baseline that needs neither shader resources nor a shader compiler, configure a separate directory with **`-DSMOKE_CLEAR_ONLY=ON`**. Its `IOSRenderSmokeMode=clear` bundle marker prevents a controller toggle from enabling unavailable geometry.

The overlay and `Documents/smoke.log` report the selected mode, cumulative successful presentation-call and debug warning/error counts, timing statistics and the thermal-state enum (0 nominal, 1 fair, 2 serious, 3 critical). Approximately two-second windows measure CPU callback frequency, mean/max callback interval and intervals over 50 ms, CPU render mean/max, fence/acquire/present-call per-callback averages (including skipped callbacks), and callbacks without an accepted present. The log also records the maximum accepted-present return interval. They do not measure GPU execution time, compositor scanout, end-to-end latency or displayed FPS. A present-return rate counts successful API calls over elapsed time; the requested 30 Hz callback rate is shown separately. Lifecycle pauses reset timing accumulation so background time is excluded. Swapchain/pipeline setup time is logged separately and excluded from the subsequent steady-state timing window.

The app enables surface/swapchain and applicable portability extensions; optional Vulkan device features are queried, not enabled. It logs device/driver information, advertised extensions, selected surface format/extent, and relevant capability booleans, including `nullDescriptor` where available. If `VK_EXT_debug_utils` is advertised, a messenger records warning/error messages; this does not install or imply an active Vulkan validation layer. Checked Vulkan failures produce a visible **BLOCKED** message and stop callbacks. Surface loss/device loss stops the experiment; out-of-date/suboptimal swapchains are recreated. Preserve the exact error before using the explicit clear-only mode to isolate a geometry failure. Neither mode uses readback or another presentation backend.

One submission is in flight. The acquire semaphore and command buffer are reused after the submission fence, while presentation semaphores are allocated per swapchain image. The latter avoids incorrectly treating a submission fence as proof that presentation has consumed its semaphore. See the [Vulkan semaphore guidance](https://docs.vulkan.org/guide/latest/swapchain_semaphore_reuse.html).

CADisplayLink requests 30 Hz. That request, FIFO mode and the thermal display are **not** measured FPS or a thermal guarantee. Scene deactivation stops callbacks and waits for submitted GPU work; activation invalidates swapchain size and resets animation/timing accumulation. `vkDeviceWaitIdle` on lifecycle/recreation is a correctness-first simplification and may stall; it is not an engine lifecycle solution. No validation-layer binary is bundled. Use Xcode Metal API validation and GPU capture for device diagnostics; Vulkan validation needs a separately provisioned iOS-compatible layer in a later step.

`Documents/smoke.log` is flushed during execution and replaced on a new renderer initialization. Retrieve it with Xcode's Devices and Simulators container download or Files sharing. Copy it before another launch. Missing file output still leaves Xcode console diagnostics.

**Real-iPhone acceptance checklist**

1. Record source SHA, dependency archive hash, actual Xcode/SDK, iOS version, device model, signing method and build configuration. Confirm the logged driver is MoltenVK on the intended Apple GPU.
2. Observe the triangle, interpolated vertex colors, background animation and increasing present count. Capture a frame with Xcode's Metal GPU capture. Confirm a three-vertex graphics draw targets the swapchain/drawable texture, with no application framebuffer readback. Save the shader/pipeline evidence; the earlier clear-color recording does not establish geometry rendering.
3. Connect an extended gamepad and press Y to compare triangle and clear modes. Check the overlay mode and counters. Separately launch with `--clear-only`; if triangle initialization is blocked, preserve the error and verify the explicit fallback independently. A `SMOKE_CLEAR_ONLY=ON` build should remain clear when Y is pressed.
4. Run for several minutes, rotate between landscape orientations, lock/unlock and repeatedly background/foreground. Check pipeline/swapchain recreation, no continuing submission while inactive, reset timing windows, no errors and no stale permanently displayed frame.
5. Run an optimized build for 20-30 minutes with recorded brightness, ambient temperature, power mode and charging state. Save logs and Metal System Trace/energy observations. Inspect measured callback/render/present-call timing and stalls; use display/GPU tools for displayed pacing. This tiny workload cannot qualify whole-game performance or low heat.
6. Treat shader compilation, pipeline creation, missing extensions, missing present support, swapchain failures, validation errors or lifecycle failures as blockers. Preserve logs and stop before adding OpenSceneGraph or Mesa. Do not patch reported capabilities to pass the test.

**Hosted macOS compilation**

The workflow uses `macos-26`, records the selected developer directory/Xcode/SDK/Clang, runs Python resolver/packaging tests and the portable C++ timing tests, downloads the pinned iOS MoltenVK asset, verifies its SHA-256, and builds the pinned host glslang compiler for triangle mode. It then compiles shaders and an unsigned Release device app. Existing ARM64-only `lipo` and device-platform `vtool` checks remain. It packages the app/dSYM plus toolchain/configure/build/linkage/platform logs, `timing-tests.log`, `shader-toolchain.log`, the glslang source license and dependency provenance, and `IOSRenderSmoke-unsigned.ipa` with `ipa-validation.log` and `ipa-validation.json`. The existing always-upload artifact step includes them. A clear-only run skips the host shader-compiler step. Hosted images and actions can change; logs preserve the actual toolchain used. The workflow never runs or signs the app, installs the full Vulkan SDK or builds OpenMW/Mesa. The new host-tool and shader resource build steps still need macOS CI validation.

The packager runs `otool -L` on the executable and any bundled dynamic libraries/frameworks, checks its output against Mach-O load commands, and records that output in the JSON report. Absolute runtime loads must resolve to public ARM64 iOS `.tbd` stubs in the selected **iphoneos** SDK; a library existing on the build Mac is not sufficient. `@rpath`, `@loader_path` and `@executable_path` dependencies must resolve to included ARM64 iOS binaries, with transitive loads validated too. Static MoltenVK is inside the executable and does not need a separate framework in the app. Missing/host-only/unresolved dependencies stop packaging; nothing is automatically copied or rewritten. See [Apple framework guidance](https://developer.apple.com/library/archive/technotes/tn2435/_index.html) and [Apple's library primer](https://developer.apple.com/forums/thread/715385).

SDK target validation reads metadata rather than searching the entire stub for an `arm64-ios` substring:

- **TAPI v4 YAML:** reads the first library document's root `targets` and `install-name`, including quoted or multiline target lists. The bounded metadata reader also retains v3 `archs`/`platform` support. Unsupported metadata syntax fails rather than guessing; no third-party YAML parser is installed.
- **TAPI v5 JSON:** decodes JSON and reads `main_library.target_info[].target` and target-scoped `main_library.install_names`. Comments, symbol groups, re-exports and other inlined libraries cannot supply evidence for the main library. Unknown versions and malformed metadata fail.
- **Exact device platform:** `arm64-ios` is supported directly. `arm64e-ios` and `arm64e.x1-ios` are recognized as candidates for Apple system SDK libraries only; the selected Apple linker must additionally produce an ARM64 iOS probe that actually loads the named stub. The probe uses the same SDK and application's minimum iOS version, treats linker warnings as errors, disables ad-hoc signing, and leaves no published probe binary. Failure or unavailable Apple tools stops validation. Application and bundled-binary architecture/platform checks remain unchanged. macOS, Mac Catalyst, Simulator, `arm64_32`, x86 and unknown ARM64 suffixes are rejected.

This addresses the literal-target check that can reject newer UIKit SDK stubs: an iPhoneOS 27.0 UIKit example is **v4 YAML** listing only `arm64e-ios` and `arm64e.x1-ios`. Standard v5 JSON still uses names such as `arm64-ios`, so changing from YAML to JSON alone is not a proven explanation of the earlier CI failure. The exact failing runner's UIKit bytes were not available here. Parsed format and declared targets are included in unsupported-target errors. The ARM64e compatibility path has local mocked-linker tests; the CI report establishes which checks actually ran for a particular SDK. It never bypasses the linker or platform check. Format and ABI references: [LLVM v4 metadata](https://github.com/llvm/llvm-project/blob/main/llvm/lib/TextAPI/TextStub.cpp), [LLVM v5 schema](https://github.com/llvm/llvm-project/blob/main/llvm/lib/TextAPI/TextStubV5.cpp#L19-L65), [LLVM same-platform ABI matching](https://github.com/llvm/llvm-project/blob/main/lld/MachO/InputFiles.cpp), and [architecture definitions](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/TextAPI/Architecture.def).

Bundle validation requires the executable named by `CFBundleExecutable`, Unix execute permissions, device ARM64 Mach-O metadata, consistent minimum iOS versions, valid iPhone bundle metadata and inline launch-screen/scene configuration. Triangle mode additionally requires **`triangle.vert.spv` and `triangle.frag.spv`** in the app bundle, with matching shader-stage/entry-point metadata. The packaging checks are bounded structural checks, not full SPIR-V semantic validation or proof that MoltenVK compiles the shaders. An explicitly marked clear-only bundle needs no shaders; missing triangle resources cannot silently become a clear-only package. No external metallib, texture or game-data resource is required. The packager rejects signing/provisioning files, credential file types, symlinks and embedded static archives. It writes `Payload/IOSRenderSmoke.app/` into a standard IPA ZIP, then reopens it to verify CRCs, unique safe paths, one app root, required files, executable permissions, native metadata and byte/permission equality with the validated bundle. The JSON report includes the IPA SHA-256 and dependency resolutions. SDK stub checks establish availability in that SDK, not runtime success on every supported iOS version.

To bootstrap **without merging to the default branch**, a future authorized push to a GitHub-hosted `ios-port` branch can trigger this workflow when it changes `experiments/ios-render-smoke/**` or `.github/workflows/ios-render-smoke.yml`. Unlike manual dispatch, this push event reads the workflow from the pushed branch. Both event types have an `ios-port` job guard. A push touching only unrelated files will not run the experiment.

Retained `workflow_dispatch` has a separate limitation: GitHub requires the workflow to exist on the repository's default branch before it can be dispatched; select `ios-port` as the run ref after registration. Its **`clear_only`** input defaults to false; true produces the shader-free fallback. A qualifying branch push builds triangle mode. Adding `--ref ios-port` alone does not remove the default-branch registration requirement. See [GitHub event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

A qualifying push or dispatch downloads the pinned build dependencies and compiles the experiment. Nothing downloads merely from editing these files locally.

**Using the IPA with Sideloadly on Windows**

Download the workflow's `ios-render-smoke-compile-<source SHA>` artifact and extract the outer GitHub artifact ZIP. Select **`IOSRenderSmoke-unsigned.ipa`** for Sideloadly; the `.app.zip` and dSYM ZIP are diagnostic artifacts. The IPA must contain `Payload/IOSRenderSmoke.app`, without an extra enclosing folder. Compare its hash with `ipa-validation.json` after download.

With a normal Python 3.10+ installation, the archive can also be rechecked offline on Windows:

```powershell
python experiments/ios-render-smoke/tools/package_ios.py --validate-only C:/path/IOSRenderSmoke-unsigned.ipa --report C:/path/ipa-local-validation.json
```

Without `--sdk`, this independently checks archive structure, native metadata, resources, signatures and bundled dependency resolution, but explicitly reports **system SDK availability not checked**. CI's original report performs that SDK check on macOS.

Follow the [official Sideloadly Windows setup](https://sideloadly.io/) for its Apple device software requirements and connect/trust the iPhone. Drag the IPA into Sideloadly and perform account authentication/signing locally. The repository and workflow contain no signing certificates, Apple credentials, provisioning profiles or signing secrets. The output IPA is deliberately unsigned. The previously observed clear-color launch does not validate signing/installation or geometry rendering of this new IPA; repeat the physical-iPhone acceptance checks.

**Extending to Zink**

First satisfy the raw Vulkan triangle checklist before integrating OpenSceneGraph, then follow the staged frontend/WSI work in [direct-presentation.md](direct-presentation.md) for Zink. Existing Mesa surfaceless EGL renders offscreen and cannot simply accept this app's `VkDevice`/swapchain. A successful pbuffer or readback demo does not satisfy direct presentation. OpenSceneGraph, OpenMW shaders, gameplay controller mappings and moderate graphics improvements remain later gates.

**License**

New experiment sources are offered under this repository's GPLv3 terms; no reference-port implementation was transplanted. MoltenVK is an external Apache-2.0 dependency with its own bundled-component notices. glslang is an external host build tool with [its own license notices](https://github.com/KhronosGroup/glslang/blob/1062752a891c95b2bfeed9e356562d88f9df84ac/LICENSE.txt), retained in CI evidence; its binary is not distributed inside the IPA. Retain the exact MoltenVK release source/license notices before distributing an app. The workflow's unsigned artifact is not a claim that binary redistribution obligations have been completed.
