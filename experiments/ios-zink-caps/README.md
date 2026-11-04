# iOS Mesa/Zink 25.1.9 capability audit

This standalone ARM64 iPhone application queries Vulkan through the same public **MoltenVK 1.4.2** release used by the successful native rendering experiment. It does not include, download, build or execute Mesa, Zink, OpenSceneGraph or OpenMW. It creates an instance and, where supported, a Metal surface for physical-device surface queries. It creates no logical device, submits no GPU work, presents no frames and runs no rendering timer. Surface queries do not prove a swapchain can present.

The existing `../ios-render-smoke/` application, its controller bindings, workflow and engine files are preserved. This app has a separate bundle identifier, so installation need not replace the working renderer. Its results do not supersede that experiment's proven physical-device rendering; they investigate a different compatibility boundary. Requested refresh rate and actual display FPS are not measured by this query app.

**Status:** source and host tests are prepared on Windows. Native Objective-C++ compilation and actual iPhone queries require the next macOS CI/device run. No real iPhone capability report is checked in or invented. Read [requirements-audit.md](requirements-audit.md) for the exact revision's source findings, formal Vulkan Profiles versus startup conditions, and remaining limitations.

**What is exported**

- `caps-latest.json`: instance/device extension names and specification versions, device/driver identity, API versions, feature booleans, limits/properties, format support, memory/queue/surface information and query/debug diagnostics. Unqueried values are omitted with diagnostic context; they are not manufactured as supported.
- `requirements-latest.json`: the exact manifest used for the comparison, also bundled in the app as `mesa-25.1.9-requirements.json`.
- `comparison-latest.json`: supported/unsupported/unknown checks for each device and each audited profile, with independent runtime checks and source references. `supported` means **reported by Vulkan**, not enabled, rendered, validated or safe in every feature combination. Overall Zink viability deliberately remains unknown.
- `summary-latest.txt` and `audit-latest.log`: readable results and application/export diagnostics.

The comparison preserves complete AND branches inside profile alternatives; it must not accept one feature from an otherwise failing alternative. Boolean false is different from an absent field. Numeric minimum/maximum checks and required format-bit masks are compared separately. An advertised extension does not satisfy its required feature booleans. Formal profile extension requirements remain literal; core promotion is accepted only where an independently documented runtime requirement explicitly permits it. Advisory/optional failures are visible and do not become mandatory profile failures. Raw data and comparison carry the same audit ID/date; when new raw data replaces an earlier run, its old comparison/summary are removed before recomparison so a failure cannot leave mismatched evidence.

Counts describe requirement rows/groups, not unique Vulkan features. Shared requirements recur across GL profiles. JSON contains the full nested alternative results. Unknown fields, missing header support and unsupported comparison semantics remain unknown. This is an auditable comparison of the pinned definitions, not the Khronos Vulkan Profiles library or a conformance certificate.

**Using the iPhone**

The audit runs automatically on activation and then remains idle. With a PS4 DualShock 4, **Triangle / GameController Y / SDL Y position** repeats the query, and **Square / X** opens the system share sheet. No SDL dependency or touchscreen gameplay interface is added. A diagnostic Share button and Files export also work without a controller. System share-sheet navigation with a controller is not independently verified.

Use **Files → On My iPhone → iOS Zink Caps** to copy the five exported files, or use the Share button. Xcode's device-container download is another option. Each successful repeat replaces the latest results, so copy evidence before another query. Raw capabilities are written before comparison so a comparison failure cannot conceal a completed query. Keep the raw/requirements/comparison files together and record device model, iOS version, source SHA and signing method. UIKit's generic `model` field is not proof of the precise iPhone model.

Scene deactivation prevents new controller-triggered queries or export actions. There is no background render loop or pending GPU submission to drain. Orientation changes resize the query layer and diagnostics; repeat the query afterward if comparing surface extents. Returning Home and foregrounding is still a physical-device acceptance check for this new app.

**Windows comparison and tests**

With Python 3.10+ installed, run from the repository root:

```powershell
python -m unittest discover -s experiments/ios-zink-caps/tools -p 'test_*.py' -v
python experiments/ios-zink-caps/tools/compare_caps.py C:/audit/caps-latest.json --requirements C:/audit/requirements-latest.json --output C:/audit/comparison-windows.json
```

The regression fixtures are synthetic, clearly named, and not hardware evidence. They cover missing versus false fields, unsupported requirements, extension/feature separation, explicit promotion, minimum/maximum limits, format masks and grouped alternatives. Existing dependency resolution and unsigned-IPA validation are reused/read independently without editing the original experiment. Local Windows checks use the already available bundled CPython runtime where normal Python commands are unavailable; nothing is installed.

On macOS, CI also compiles the **actual Foundation evaluator used by the app** and compares it against the same host regression fixtures. This checks native/host comparison parity without pretending to execute iPhone Vulkan. A native parity pass is separate from the ARM64 iOS app compilation.

**Dependencies and macOS/Xcode steps**

Required: Xcode with the iphoneos SDK, CMake 3.24+, Python 3.10+ and the existing public static MoltenVK 1.4.2 iOS distribution with matching headers. No full Vulkan SDK, shader compiler or Mesa toolchain is required. The archive pin is shared with the successful renderer:

```text
MoltenVK-ios.tar v1.4.2
SHA-256 b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1
```

The new app reads the existing [MoltenVK resolver](../ios-render-smoke/tools/resolve_moltenvk.py); it does not configure OpenMW's root project. CMake performs no downloads. Point at an already extracted dependency:

```sh
cmake -S experiments/ios-zink-caps -B experiments/ios-zink-caps/build -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DMOLTENVK_ROOT=/absolute/path/to/extracted/MoltenVK \
  -DCAPS_UNSIGNED=ON
cmake --build experiments/ios-zink-caps/build --config Release --target IOSZinkCaps -- CODE_SIGNING_ALLOWED=NO
```

For Xcode installation instead, configure a fresh build with `CAPS_UNSIGNED=OFF`, your `CAPS_DEVELOPMENT_TEAM` and `CAPS_BUNDLE_ID`, select the IOSZinkCaps scheme/physical iPhone and sign locally. No signing identities, accounts, certificates, profiles or secrets belong in the repository. These commands have not been executed on the Windows host.

**GitHub Actions and Sideloadly**

The separate [workflow](../../.github/workflows/ios-zink-caps.yml) builds Release for iphoneos ARM64, records its actual source/Xcode/SDK, runs host/native comparison and packaging tests, and downloads only the hash-pinned public iOS MoltenVK asset. It never downloads or builds Mesa. It preserves architecture, platform and `otool -L` evidence; checks iOS SDK and bundled dependencies; packages and reopens a standard `Payload/IOSZinkCaps.app` IPA; and always uploads logs and available artifacts.

A qualifying push on `ios-port` can bootstrap the workflow. Manual dispatch generally requires it to exist on the repository's default branch first; selecting `ios-port` alone does not register it. No push or dispatch has been performed here. Once a run succeeds, extract its outer artifact ZIP and select **`IOSZinkCaps-unsigned.ipa`** in Sideloadly on Windows. Sign/authenticate locally using the existing installation method. Do not select the diagnostic `.app.zip`. This app's installation/launch remains unverified until that run and device test.

The new [packager](tools/package_ios.py) retains the original experiment's strict ARM64/device, SDK-stub, transitive dependency and archive checks, adapted to this app and its required manifest. Offline `--validate-only` requires the **matching source checkout** because it verifies exact bundled manifest bytes; SDK availability remains explicitly unchecked without `--sdk`:

```powershell
python experiments/ios-zink-caps/tools/package_ios.py --validate-only C:/audit/IOSZinkCaps-unsigned.ipa --report C:/audit/ipa-check.json
```

**Interpreting the first device report**

1. Confirm the intended Apple GPU/MoltenVK driver, device API and complete extension enumeration; inspect query/debug errors before interpreting absent data.
2. Start with `VP_ZINK_gl21_baseline` for the present OSG GL2 contract, then inspect the independent runtime checks. A formal profile failure and a startup blocker are different findings; neither should be hidden by the other.
3. Review unsupported/unknown feature bits, limits, format masks and alternative branches individually. Missing extension functionality, false feature booleans or unavailable required formats are evidence to investigate, not permission to override capabilities.
4. Even a fully reported profile match leaves feature enablement, actual Zink initialization, shaders, OpenMW-specific rendering correctness and direct UIKit/Kopper WSI untested. This app neither implements that missing frontend nor certifies full desktop GL.
5. No query-only result can establish gameplay FPS, power or sustained thermal behavior. Preserve the reports and decide the next bounded test before compiling Mesa.

New experiment code uses the repository's GPLv3 terms. The audit manifest contains attributed factual requirement data and source references. MoltenVK and any later dependency/code reuse retain their own applicable licenses and notices; this compile-only experiment does not certify redistribution compliance.
