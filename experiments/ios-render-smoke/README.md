# iOS direct Vulkan presentation smoke test

This is an independent device application, not an OpenMW build target. It uses **Vulkan -> MoltenVK -> CAMetalLayer swapchain presentation**, with a changing render-pass clear color. There are no shaders, vertex buffers, SDL, Mesa, Zink, OpenGL calls, framebuffer readback, or CPU pixel transfers in the application. A UIKit status label is composited over the Metal layer.

**Status: previous CI build succeeded; unsigned IPA packaging added for the next run.** Public [run 41747796821](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/41747796821) successfully configured, compiled and packaged source `57aa900a459f5ec93160597683130158d0dc65d5`. Artifact metadata is public, but downloading its bytes requires authentication, so the prior app's actual dependency list and contents were not independently inspected here. New bundle/dependency/IPA checks must pass on the next macOS run. No iPhone installation or rendering result is established.

Local tests run on Windows using an existing bundled CPython 3.12.3 runtime and standard library, invoked through its C API without installing Python. The `python`/`python3` commands on PATH are Microsoft Store shortcuts. No Apple SDK or local C++ compiler is available. A full GitHub Actions schema/actionlint check is not available locally.

The investigation in [direct-presentation.md](direct-presentation.md) explains why raw Vulkan presentation is a reasonable first gate, while direct **Zink** presentation remains blocked on missing UIKit/Metal native-window integration. Do not interpret a successful clear test as a working Zink/OpenMW port.

**Files and dependencies**

- `src/main.mm`: UIKit scene lifecycle, CAMetalLayer-backed view, Vulkan instance/device/capability logging, FIFO swapchain, render-pass clear, submit/present, and 30 Hz display callback.
- `CMakeLists.txt` and `Info.plist.in`: standalone ARM64 iOS device application, deployment target 18.0, normal signing or explicitly unsigned compilation.
- `tools/resolve_moltenvk.py`: selects a unique static ARM64 iOS **device** archive and matching headers by XCFramework metadata; fails on missing/ambiguous inputs. It reads metadata, not dependency code. Python 3.10+ standard library only.
- `tools/test_resolve_moltenvk.py`: synthetic host tests for device/simulator distinction, ambiguous inputs, missing files and metadata paths. No SDK or real binary required.
- `tools/package_ios.py` and `tools/test_package_ios.py`: unsigned app/dependency/IPA validation and standard-library ZIP packaging, with synthetic Mach-O/SDK/archive tests. No signing or networking.
- [Build and packaging workflow](../../.github/workflows/ios-render-smoke.yml): a path-filtered `ios-port` push or eligible manual dispatch can trigger it. No PR trigger, signing, installation or device run.

Required later: macOS with Xcode and its iOS SDK, CMake 3.24+, Python 3.10+, and a **previously obtained public MoltenVK 1.4.2 iOS distribution** with static `MoltenVK.xcframework` and corresponding Vulkan headers. Do not use the macOS archive, private-API build, a simulator slice, an installed desktop Vulkan SDK, or an unrelated Vulkan header version. Static linking requires no Vulkan loader/ICD installation. The app links UIKit, Foundation, QuartzCore, Metal, CoreGraphics and IOSurface; it does not link AppKit, IOKit or OpenGLES.

The pinned public asset is [MoltenVK-ios.tar](https://github.com/KhronosGroup/MoltenVK/releases/expanded_assets/v1.4.2), about 32.9 MB, for source revision `db66022459ffb663aa2b50f6b018bc2e124f5edf`. Its published archive SHA-256 is:

```text
b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1
```

No dependency fetch occurs in CMake. The release archive's internal layout and actual static link have **not** been tested here. The resolver inspects `Info.plist` instead of assuming archive paths; a different layout produces an explicit blocker. Its metadata check is not a Mach-O architecture verifier; the Apple linker and CI `lipo` check remain necessary.

**macOS/Xcode build steps**

These commands are instructions for later execution, not commands run in this investigation. Have the matching dependency distribution available first; point `MOLTENVK_ROOT` at its extraction directory or the specific static `MoltenVK.xcframework` if there are multiple copies. Replace the team and bundle ID with your own. Run from the OpenMW repository root, without invoking its root CMake configuration:

```sh
python3 -m unittest discover -s experiments/ios-render-smoke/tools -p 'test_*.py' -v

cmake -S experiments/ios-render-smoke -B experiments/ios-render-smoke/build -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DMOLTENVK_ROOT=/absolute/path/to/extracted/MoltenVK \
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
  -DMOLTENVK_ROOT=/absolute/path/to/extracted/MoltenVK -DSMOKE_UNSIGNED=ON
cmake --build experiments/ios-render-smoke/build/unsigned --config Release --target IOSRenderSmoke -- CODE_SIGNING_ALLOWED=NO
```

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

The view should continuously cycle colors beneath a label showing presentation-call count and the thermal-state enum (0 nominal, 1 fair, 2 serious, 3 critical). Color changes come from a render pass clearing the acquired swapchain image; MoltenVK owns the Metal drawable presentation. A counter and successful `vkQueuePresentKHR` return alone do not prove the image appeared on the display.

The app enables only surface/swapchain and applicable portability extensions; optional Vulkan features are queried, not enabled. It logs device/driver information, advertised extensions, selected surface format/extent, and relevant capability booleans, including `nullDescriptor` where available. It does not falsify feature limits, enable private Metal APIs, switch to another renderer, or fall back to readback. Vulkan errors produce a visible **BLOCKED** message and stop callbacks. Surface loss/device loss stops the experiment; out-of-date/suboptimal swapchains are recreated.

One submission is in flight. The acquire semaphore and command buffer are reused after the submission fence, while presentation semaphores are allocated per swapchain image. The latter avoids incorrectly treating a submission fence as proof that presentation has consumed its semaphore. See the [Vulkan semaphore guidance](https://docs.vulkan.org/guide/latest/swapchain_semaphore_reuse.html).

CADisplayLink requests 30 Hz. That request, FIFO mode and the thermal display are **not** measured FPS or a thermal guarantee. Scene deactivation stops callbacks and waits for submitted GPU work; activation invalidates swapchain size and resets animation timing. `vkDeviceWaitIdle` on lifecycle/recreation is a correctness-first simplification and may stall; it is not an engine lifecycle solution. There is no validation-layer binary bundled: Metal API validation/GPU capture are available through Xcode, but Vulkan validation needs a separately provisioned iOS-compatible layer in a later diagnostic step.

`Documents/smoke.log` is flushed during execution and replaced on a new renderer initialization. Retrieve it with Xcode's Devices and Simulators container download or Files sharing. Copy it before another launch. Missing file output still leaves Xcode console diagnostics.

**Real-iPhone acceptance checklist**

1. Record source SHA, dependency archive hash, actual Xcode/SDK, iOS version, device model, signing method and build configuration. Confirm the logged driver is MoltenVK on the intended Apple GPU.
2. Observe color animation and increasing present count. Capture a frame with Xcode's Metal GPU capture. Verify work targets swapchain/drawable textures; there must be no application staging-buffer copy, readback or hidden alternate rendering path. API support alone cannot prove capture behavior.
3. Run for several minutes, rotate between landscape orientations, lock/unlock and repeatedly background/foreground. Check resize recreation, no continuing submission while inactive, no errors and no stale permanently displayed frame.
4. Run an optimized build for 20-30 minutes with recorded brightness, ambient temperature, power mode and charging state. Save log and Metal System Trace/energy observations. Measure actual pacing/stalls rather than inferring 30 FPS from the callback request. This tiny clear workload cannot qualify whole-game performance or low heat.
5. Treat missing extensions, missing present support, swapchain failures, validation errors or lifecycle failures as blockers. Preserve logs and stop before adding Mesa. Do not patch reported capabilities to pass the test.

**Hosted macOS compilation**

The workflow uses `macos-26`, records the selected developer directory/Xcode/SDK/Clang, runs all resolver/packaging tests, downloads **only the pinned iOS MoltenVK asset**, verifies its SHA-256 and compiles an unsigned Release device app. Existing ARM64-only `lipo` and device-platform `vtool` checks remain. It packages the app/dSYM plus toolchain/configure/build/linkage/platform logs, and adds `IOSRenderSmoke-unsigned.ipa`, `ipa-validation.log` and `ipa-validation.json`. The existing always-upload artifact step includes all of them. Hosted images and actions can change; logs preserve the actual toolchain used. The workflow never runs or signs the app, installs the full Vulkan SDK or builds OpenMW/Mesa.

The packager runs `otool -L` on the executable and any bundled dynamic libraries/frameworks, checks its output against Mach-O load commands, and records that output in the JSON report. Absolute runtime loads must resolve to public ARM64 iOS `.tbd` stubs in the selected **iphoneos** SDK; a library existing on the build Mac is not sufficient. `@rpath`, `@loader_path` and `@executable_path` dependencies must resolve to included ARM64 iOS binaries, with transitive loads validated too. Static MoltenVK is inside the executable and does not need a separate framework in the app. Missing/host-only/unresolved dependencies stop packaging; nothing is automatically copied or rewritten. See [Apple framework guidance](https://developer.apple.com/library/archive/technotes/tn2435/_index.html) and [Apple's library primer](https://developer.apple.com/forums/thread/715385).

Bundle validation requires the executable named by `CFBundleExecutable`, Unix execute permissions, device ARM64 Mach-O metadata, consistent minimum iOS versions, valid iPhone bundle metadata and inline launch-screen/scene configuration. This clear-only application requires **no external shader, metallib, texture or game-data resources**. The packager rejects signing/provisioning files, credential file types, symlinks and embedded static archives. It writes `Payload/IOSRenderSmoke.app/` into a standard IPA ZIP, then reopens it to verify CRCs, unique safe paths, one app root, required files, executable permissions, native metadata and byte/permission equality with the validated bundle. The JSON report includes the IPA SHA-256 and dependency resolutions. SDK stub checks establish availability in that SDK, not runtime success on every supported iOS version.

To bootstrap **without merging to the default branch**, a future authorized push to a GitHub-hosted `ios-port` branch can trigger this workflow when it changes `experiments/ios-render-smoke/**` or `.github/workflows/ios-render-smoke.yml`. Unlike manual dispatch, this push event reads the workflow from the pushed branch. Both event types have an `ios-port` job guard. A push touching only unrelated files will not run the experiment.

Retained `workflow_dispatch` has a separate limitation: GitHub requires the workflow to exist on the repository's default branch before it can be dispatched; select `ios-port` as the run ref after registration. Adding `--ref ios-port` alone does not remove that requirement. See [GitHub event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

The checkout now has a `github` remote at `https://github.com/austinharvey809-dot/openmw-ios-port.git`, alongside the GitLab upstream. No commit, push, remote change or dispatch was performed during this packaging update. A future qualifying push or dispatch will download the dependency and compile; nothing downloads merely from editing these files locally.

**Using the IPA with Sideloadly on Windows**

Download the workflow's `ios-render-smoke-compile-<source SHA>` artifact and extract the outer GitHub artifact ZIP. Select **`IOSRenderSmoke-unsigned.ipa`** for Sideloadly; the `.app.zip` and dSYM ZIP are diagnostic artifacts. The IPA must contain `Payload/IOSRenderSmoke.app`, without an extra enclosing folder. Compare its hash with `ipa-validation.json` after download.

With a normal Python 3.10+ installation, the archive can also be rechecked offline on Windows:

```powershell
python experiments/ios-render-smoke/tools/package_ios.py --validate-only C:/path/IOSRenderSmoke-unsigned.ipa --report C:/path/ipa-local-validation.json
```

Without `--sdk`, this independently checks archive structure, native metadata, resources, signatures and bundled dependency resolution, but explicitly reports **system SDK availability not checked**. CI's original report performs that SDK check on macOS.

Follow the [official Sideloadly Windows setup](https://sideloadly.io/) for its Apple device software requirements and connect/trust the iPhone. Drag the IPA into Sideloadly and perform account authentication/signing locally. The repository and workflow contain no signing certificates, Apple credentials, provisioning profiles or signing secrets. The output IPA is deliberately unsigned; successful Sideloadly signing, installation, launch, Vulkan presentation and thermal behavior still require the actual iPhone 16 Plus. No installation was attempted here.

**Extending to Zink**

First satisfy the raw Vulkan checklist, then follow the staged frontend/WSI work in [direct-presentation.md](direct-presentation.md). Existing Mesa surfaceless EGL renders offscreen and cannot simply accept this app's `VkDevice`/swapchain. A successful pbuffer or readback demo does not satisfy direct presentation. OSG, current OpenMW shaders, controllers and moderate graphics improvements remain later gates; this first experiment deliberately contains none of them.

**License**

New experiment sources are offered under this repository's GPLv3 terms; no reference-port implementation was transplanted. MoltenVK is an external Apache-2.0 dependency with its own bundled-component notices. Retain the exact release source/license notices before distributing an app. The workflow's unsigned artifact is not a claim that binary redistribution obligations have been completed.
