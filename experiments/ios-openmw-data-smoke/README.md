# Milestone F — first iPhone OpenMW data execution (prepared, not yet native-tested)

This separate UIKit experiment prepares genuine `ESMReader` → `ESM::Static::load` → original BSA → `VFS::Manager` resource execution on an iPhone. It runs one deterministic positive case, verifies its exact bytes and SHA-256, displays PASS/FAIL and exports diagnostic files. The payload is original synthetic binary data named `.nif`; it is not NIF geometry, Morrowind content, world loading or full OpenMW startup.

**Status:** the user verified Milestone E run `42746322511`, including macOS link/runtime and all 21 ARM64 iPhoneOS archive objects. Those results do not prove a combined iPhoneOS executable link. F passed manual source review and is approved for native CI preparation. No Apple compiler/linker or physical-device test has run for F. The manual workflow is now prepared for review; it has not been dispatched. Stop for manual review before committing or running GitHub Actions.

## Audit and architecture

The known-good graphics apps demonstrate UIKit `UIApplicationMain`, a single `UIWindowScene` delegate/window, inline launch-screen metadata, iOS 18.0 ARM64 unsigned CMake/Xcode builds and a validated `Payload/<app>.app` IPA for Windows Sideloadly. This app reuses that pattern without changing any graphics application. It needs **UIKit and Foundation only** as explicitly linked Apple frameworks. CommonCrypto's `CC_SHA256` comes from the system libraries; no Swift/CryptoKit package or handwritten hash substitute is added.

There is no CAMetalLayer, EGL context, display link, render loop, SDL, controller subsystem, audio, ANGLE/MoltenVK, or OSG renderer in F. The pinned OSG math headers/config remain compile-time requirements inherited from D. Existing graphics context/swap/controller behavior is untouched. The Share button is a diagnostic utility, not a touchscreen gameplay interface.

The original [E CMake target](../ios-openmw-esm-vfs/CMakeLists.txt) remains the sole engine-library dependency:

```text
openmw-data-link-check (exact unchanged E fixture main)
    → openmw-ios-esm-vfs (6 objects)
        → openmw-ios-esm-reader (15 objects)
            → system threads / C++ runtime

IOSOpenMWDataSmoke (new UIKit + Objective-C++ bridge + C++ probe)
    → same unchanged E → D libraries
    → UIKit + Foundation + system CommonCrypto
```

The [E source inventory](../ios-openmw-esm-vfs/data/source-audit.json) covers 20 genuine engine translation units plus C's real existing registration helper, with 58 project headers (79 files total). Neither A/B/C archives nor duplicate copies of their overlapping sources are added. No force-load, multiple-definition allowance, substitute OpenMW class or engine patch is used. The separate OSG checkout must remain at `9b384d5439977784e5cd250ff8ff7966928ddd27`; the existing audit checks its revision and all seven inventoried original files. Source/config checks run before target preparation.

The **link gate** compiles E's unchanged `tests/esm_vfs_check.cpp` as an ordinary iPhoneOS `MH_EXECUTE`, with all normal undefined-symbol checks. It is not an application, is not launched as a subprocess on a stock iPhone, and is not packaged in the app. It proves executable linking only when the Apple linker actually completes. The app has an explicit dependency on this gate so a failed gate prevents app construction. UIKit application linking is a separate subsequent result.

No undefined or duplicate symbols have been observed in F because no native linker has run. The source closure was already independently linked on macOS/Linux, but Apple SDK availability, iOS libc++/`std::format`, CommonCrypto resolution, Objective-C++ compilation and final application linking remain native acceptance gates. Let normal compiler/linker errors fail; inspect the logs rather than adding replacement symbols or suppressing errors.

## Files and runtime operation

| File | Purpose |
| --- | --- |
| `CMakeLists.txt` | Strict iPhoneOS ARM64/18.0 configuration, unchanged E/D subprojects, separate link gate and app target |
| `Info.plist.in` | iPhone app identity, inline launch screen, `DataSceneDelegate`, document sharing and supported orientations |
| `src/DataProbe.hpp`, `src/DataProbe.cpp` | Small adapter invoking real OpenMW parsing, path and archive APIs; no new parser |
| `src/DataCheck.hpp`, `src/DataCheck.mm` | CommonCrypto hashes, input snapshots, provenance verification, error/result dictionary |
| `src/main.mm` | One-shot UIKit app, PASS/FAIL, detailed findings, atomic JSON/log export and share sheet |
| `data/fixtures.json` | Reviewed hashes/sizes and exact synthetic resource expectations |
| `tools/prepare_inputs.py` | Read-only E/OSG audit, genuine Config check, deterministic bundle resources and compiled expectation header |
| `tools/package_ios.py` | Strict link/app/IPA validation using unchanged ANGLE SDK/Mach-O primitives; no global mutation |
| `tools/test_data_app.py`, `tools/test_package_ios.py` | Offline application, provenance, fixture, packaging and failure contracts |
| `tools/ci_checks.py`, `tools/test_ci_workflow.py` | Strict 28-test runner, workflow/evidence contracts, product discovery, provenance handoffs and failure collection |
| `data/prior-milestones.json` | Canonical LF SHA-256 preservation inventory of all 53 tracked A–E files and workflows |
| `.github/workflows/ios-openmw-data-smoke.yml` | Manual-only independent host/offline and iPhoneOS native jobs |
| `.gitignore` | Generated build/artifact exclusions |

`prepare_inputs.py` generates resources only in the specified owned build output. It does not download, build or modify OSG. Its generated `FixtureExpectations.hpp` binds the executable to the input manifest, original payload, current source commit and exact build-metadata hash. `data-build.json` includes all 79 project and seven OSG hashes, generated Config hash, and hashes of the app/link-gate sources. The actual genuine Config and original OpenMW/OSG license texts are bundled too. These are build provenance, not device-runtime proof. Use a fresh build/configuration after source changes; do not reuse stale prepared resources.

On first view presentation, the app writes RUNNING diagnostics, then performs one short check on a utility queue. The UI and exports are updated on the main queue. Closing the share sheet or returning from the Home Screen does not restart the test. The OS may suspend a backgrounded process; no background-completion claim or background mode is added. An interrupted run remains RUNNING, not PASS. Relaunch to run a fresh session.

The fixture directory is the app's read-only bundle `Fixtures/`, not a hardcoded Windows path, current working directory, user-selected archive or game install directory. The app requires exactly the three known files (two inputs and their manifest), rejects symbolic/unexpected entries and verifies all input bytes before calling OpenMW. Both borrowed UTF-8 encoders outlive their real readers. The resource stream is checked after VFS manager destruction, with a bounded oversized read and end-relative seek/EOF check. No archive-entry pointer outlives its owner.

The real `STAT` loader extracts ID `eIOSStatic` and MODL `TeSt.NIF`. An explicit mesh-category prefix uses the public VFS path API, yielding `meshes/test.nif`, matching E's tested policy. C's existing helper requires an existing original-format BSA before constructing `BsaArchive<BSAFile>`; it prevents the reader's missing-archive creation path. The app does not parse a BSA or ESM using a new implementation.

## Exact deterministic inputs

The build reuses E's byte generator and checks it against [data/fixtures.json](data/fixtures.json):

| Data | Size | SHA-256 |
| --- | ---: | --- |
| `Fixtures/valid.esm` | 376 | `48fdfa9d1aed2bb3d82169cd16574088373c4deaff3a39e9b40ea809157fcd9f` |
| `Fixtures/base.bsa` | 134 | `3bb579dc79ac3aabbf12159298625d33e0a7a929a80a9550452fae7a47f632be` |
| Retrieved `meshes/test.nif` payload | 24 | `3f164502d39021fecd17102c940caad8e7916ede6863daca51200c44ff65a288` |

The payload is `b'\x00OMW-E\xff\n\x00synthetic-model'`. Both byte-for-byte equality and a hash of the **actual returned stream bytes** are required. The manifest hash and metadata hash must match compiled expectations. The whole fixture tree is compared before/after; failure paths retain post-failure integrity findings where possible, or UNKNOWN if unavailable. This first device app runs the positive ESM/BSA integration, not E's sixteen-subprocess suite; those regressions remain in E's independent host workflow.

PASS is displayed only if all real calls/checks finish and both exports save successfully. `Documents/data-smoke.json` and `Documents/data-smoke.log` contain identical structured findings, including a unique session ID, UTC timestamps, source/OSG provenance, actual ID/model/key/size/hash, input snapshots, completion flags, elapsed wall time and error text. Elapsed time is a one-shot duration, not FPS. The device model/system/thermal-state sample is recorded without claiming sustained thermal performance. Each launch replaces F's latest files; export a session before relaunching if it must be retained. No earlier experiment logs are touched.

## Offline validation on Windows

With an existing Python 3.10+ installation:

```powershell
python -B -m unittest discover -s experiments/ios-openmw-data-smoke/tools -v
python -B experiments/ios-openmw-esm-vfs/tools/audit_sources.py --osg-source C:/Users/austi/Projects/OpenSceneGraph-pinned --require-complete
git diff --check
```

Tests verify exact fixture hashes, provenance/config failure handling, genuine API/source selection, link-target ordering, scene/export metadata, runtime PASS gates, ARM64/iOS18 executable metadata, SDK platform rejection and standard unsigned IPA round trips. Synthetic Mach-O/stub files and mocked tool calls test validators only; no mock is used as evidence of engine execution. Temporary Config-template renders in unit tests test the verifier and are not native CMake output. Windows has no available Xcode/iPhoneOS SDK/compatible native toolchain here, so C++/Objective-C++ compilation, executable linking, SDK checks, signing and device execution are unexecuted.

## Manual Apple link and application gates (future, not executed)

Use a macOS machine with full Xcode, its iPhoneOS SDK, CMake 3.24+, Python and the same verified separate OSG checkout. No ANGLE/OSG renderer dependency build is needed. The prepared [manual workflow](../../.github/workflows/ios-openmw-data-smoke.yml) implements the gates below, plus strict archive inspection and independent provenance checks. It uses `workflow_dispatch` only, on `ios-port`, with no push trigger. The examples below are reference commands, not evidence that they ran.

Record the exact source commit, OSG revision, `xcodebuild -version`, SDK/compiler/CMake versions, commands and complete logs. The examples use standard Xcode `Release-iphoneos` product paths: inspect the actual unique products, and stop rather than selecting a macOS/simulator or ambiguous output.

```bash
set -euo pipefail
SRC="$PWD/experiments/ios-openmw-data-smoke"
BUILD="$SRC/build-device"
OSG_SOURCE="/absolute/path/to/OpenSceneGraph-pinned"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
mkdir -p "$BUILD/evidence"
python3 experiments/ios-openmw-esm-vfs/tools/audit_sources.py --osg-source "$OSG_SOURCE" --require-complete
cmake -S "$SRC" -B "$BUILD" -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$SDK" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DOPENMW_ESM_OSG_SOURCE="$OSG_SOURCE" 2>&1 | tee "$BUILD/evidence/configure.log"

# Gate F0: actual Apple executable link of the exact reviewed E fixture.
cmake --build "$BUILD" --config Release --verbose --target openmw-data-link-check -- \
  -jobs 3 CODE_SIGNING_ALLOWED=NO 2>&1 | tee "$BUILD/evidence/link-build.log"
python3 "$SRC/tools/package_ios.py" \
  --link-executable "$BUILD/Release-iphoneos/openmw-data-link-check" \
  --sdk "$SDK" --evidence "$BUILD/evidence/link"
```

Stop if this link or metadata/dependency check fails. Before proceeding, also reuse E's existing archive locator and unchanged D/E validators to inspect the 15 + 6 objects individually; successful static and executable results must be reported separately. For F, D's generated Config is under `build-device/esm-vfs/esm-reader/osg-math/include/osg/Config`. The link checker executable is retained as compile evidence, never copied into the app.

```bash
# Gate F1: distinct UIKit application link, then strict unsigned package validation.
cmake --build "$BUILD" --config Release --verbose --target IOSOpenMWDataSmoke -- \
  -jobs 3 CODE_SIGNING_ALLOWED=NO 2>&1 | tee "$BUILD/evidence/app-build.log"
python3 "$SRC/tools/package_ios.py" \
  --app "$BUILD/Release-iphoneos/IOSOpenMWDataSmoke.app" --sdk "$SDK" \
  --output "$BUILD/IOSOpenMWDataSmoke-unsigned.ipa" --evidence "$BUILD/evidence/package"
python3 "$SRC/tools/package_ios.py" --validate-only "$BUILD/IOSOpenMWDataSmoke-unsigned.ipa" \
  --evidence "$BUILD/evidence/ipa-archive"
```

The packager requires a sole thin unsigned ARM64 `MH_EXECUTE`, iOS-device platform/minimum 18.0, valid app/scene metadata, UIKit/Foundation imports and exact resources/hashes/licenses. It rejects signatures, provisioning/credential files, host paths, alternate graphics libraries, bundled static/dynamic libraries and unexpected native binaries. With no custom dynamic libraries, no `LC_RPATH` is needed or accepted. `otool -L` is checked against parsed imports, and system dependencies must pass the existing strict iPhoneOS SDK/TAPI validation. The unsigned IPA must round-trip through exactly `Payload/IOSOpenMWDataSmoke.app/` with preserved executable permissions, resources and checksums. Portable `--validate-only` without an SDK cannot establish SDK availability; its report says so.

Native link/package evidence contains `validation.json`, `otool-L.txt` where applicable and `SHA256SUMS`, including failure reports. Retain the linker outputs, both archives and member reports, generated Config/metadata, all logs, IPA and their hashes for later independent review. An archive existing on disk, host tests passing, or metadata parsing alone must never be reported as an actual Apple link or iPhone execution.

## Installation and first physical acceptance

Transfer the validated unsigned IPA to Windows. Sign/install it with the user's existing Sideloadly process and trusted local Apple-account/provisioning setup. An unsigned IPA cannot launch until signed appropriately. Credentials, certificates, profiles and entitlements are not supplied or stored by this project. Signing/installation and any account restrictions remain external steps. There are no app capabilities beyond a normal UIKit sandbox/file export requirement.

On the iPhone 16 Plus:

1. Launch F separately from the working graphics app. Observe RUNNING then PASS or a clear failure.
2. Require ID `eIOSStatic`, model `TeSt.NIF`, key `meshes/test.nif`, size 24 and the exact payload hash above.
3. Export both diagnostic files using Share or the app's document-sharing location. Require matching session/result data, `genuine_openmw_call_completed=true`, `inputs_unchanged=true`, matching before/after input hashes and correct source/OSG provenance.
4. Check that returning from the Home Screen keeps the completed result and does not start another test. If interrupted before completion, relaunch and review the new session; do not count RUNNING as success.

Only an actual reviewed device result establishes Milestone F physical success. It proves these selected data APIs executed, not all sixteen host cases, NIF loading, rendering, game startup or sustained performance.

## Preserved limits and next boundary

The malformed-BSA undersized-directory allocation risk and ESM short-read/bounds limitations documented in A–E are unchanged. Existing-file/magic checks and preverified small bundle fixtures are an input policy, not a parser security repair. No untrusted or real game content should be introduced in this milestone.

After manual review of the prepared CI changes, run the native workflow, resolve any concrete Apple link/compiler issue without substitutes, then perform and independently inspect the physical test. Genuine NIF parsing, renderer/resource integration, game-data import/sandbox paths, asset licenses, world/cell loading and full engine startup remain later milestones. Existing graphics experiments, controller behavior, dependency pins and all nine unfinished Build #15 files are preserved.

## Prepared CI gates and evidence

Both jobs use `macos-26`, check out exactly `${{ github.sha }}` and the sibling `OpenMW/osg` revision `9b384d5439977784e5cd250ff8ff7966928ddd27`, and independently verify those revisions, the existing D/E manifests and `data/prior-milestones.json`. The latter freezes all tracked A–E files/workflows without modifying them. No dependency downloads or OSG renderer builds are added. Runner image/Xcode availability is checked at execution time; it has not been established offline.

The host job requires all **28** reviewed F regressions to pass, with no skips or expected failures. It also runs the new workflow/evidence tests and the complete E Python suite, checks Python/Bash/embedded-Python syntax, documentation and whitespace, configures the existing E host CMake project to generate the genuine OSG Config, then validates generated Config, synthetic fixture bytes and prepared provenance. E's optional native-runtime Python test is expected to skip without a compiled checker. This job does not claim host C++ execution; E's existing host runtime workflow remains unchanged.

The independent native job proceeds in this order:

1. Configure the existing F project with Xcode, real iPhoneOS SDK, ARM64 and exactly minimum iOS 18.0. Verify nested Config and all prepared inputs.
2. Build D and E archives, locate unique nonempty outputs and apply the unchanged strict per-object validators to exactly **15 + 6** objects.
3. **F0:** build `openmw-data-link-check` through the normal Apple executable linker, then inspect the actual product with `lipo`, `otool`, `vtool` and the existing strict executable/SDK dependency validator. Any failure blocks the app gate.
4. **F1:** compile/link `IOSOpenMWDataSmoke`, independently inspect its device executable, and validate the single scene, bundle identity, UIKit/Foundation imports, system dependencies, fixtures and all prepared provenance/license/Config bytes. Successful normal linking must resolve CommonCrypto `CC_SHA256` through the SDK system libraries, plus inherited libc++/thread dependencies; a separate CommonCrypto framework is not added.
5. **Packaging:** only after F1 succeeds, run the unchanged strict packager, create `IOSOpenMWDataSmoke-unsigned.ipa`, reopen the completed IPA with `--validate-only --sdk`, then independently compare all packaged prepared resources against the current checkout. No signing occurs in CI.

Build/link commands use `--verbose`, and every pipeline uses `set -euo pipefail`. Normal compiler/linker errors fail the job without symbol substitutes or suppressed errors. Product discovery rejects missing or ambiguous output. Partial diagnostics are collected with `always()`; a separate finalizer records gate outcomes and computes the full evidence `SHA256SUMS`, even if collection failed. Upload also uses `always()`. A cancellation or runner loss can still prevent artifact delivery; the final GitHub job conclusion is authoritative.

| Artifact | Contents |
| --- | --- |
| `ios-openmw-data-host-<run_id>-<attempt>` | Requested/source/OSG revisions, source hash inventories, frozen A–E inventory, toolchain, 28-test report, complete Python logs, syntax/workflow/E results, Config, prepared fixtures/provenance, status and SHA-256 manifest |
| `ios-openmw-data-native-<run_id>-<attempt>` | Toolchain/source inventories, CMake diagnostics, full archive/F0/F1 build and link logs, both static archives, per-object Mach-O reports, link executable, available app/dSYM products, generated Config/header/resources/provenance, separate F0/F1/package/reopened-IPA reports, gate status, full SHA-256 manifest and unsigned IPA if produced |

`job-status.json` separates F0, F1 and packaging, and always records physical device execution as `not-performed`. An IPA left by a later failed verification is diagnostic evidence only: require successful packaging/reopened-IPA status and the final job conclusion before accepting it. Offline synthetic Mach-O tests validate rejection logic only. Native compatibility, unresolved/duplicate symbols, SDK/libc++/CommonCrypto availability and Objective-C++ compilation remain unproven until this workflow actually passes. Signing, installation and iPhone execution remain separate manual acceptance steps.
