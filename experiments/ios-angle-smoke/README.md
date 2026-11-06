# iOS ANGLE Metal smoke: independent Gates 0 and 1

This isolated implementation targets the iPhone 16 Plus, iOS 18+, ARM64
device SDK. It does not modify or consume the Vulkan cube, Zink experiment,
OpenMW, SDL, OpenSceneGraph or GL4ES. No game assets or signing material belong
here. A CI pass will establish compilation/package evidence, not rendering or FPS.

## Resource budget and current blockers

**Read before opting in to an expensive build.** Standalone ANGLE still needs its
Chromium build/toolchain dependency graph, not a small binary download. Some test
dependencies remain unconditional upstream even though only EGL/GLES targets
are built. Expect multi-GB network/disk use; the actual bytes, duration and peak
memory have not been measured. Gate 0 requires 20 GiB free space before fetching,
uses three build jobs and a 90 minute timeout. A standard hosted runner may have
insufficient free disk or time. In that case inspect logs and choose an adequately
sized macOS host; no automatic deletion of runner software or paid runner upgrade
is performed. There is no automatic retry, prebuilt mirror or simulator substitute.

Nothing in these scripts downloads on Windows. `build_angle.py` is a plan-only
command unless `--allow-downloads` is supplied, and rejects a non-macOS build host
even with that option. No CI is launched by these scripts outside an opted-in
GitHub workflow or an explicit local invocation.

Reported run #8 passed Gate 0's dependency build and validation. Run #10 also
compiled the native app, then failed IPA validation on an absolute build-machine
rpath as described below. Still unverified: successful unsigned IPA packaging, Sideloadly
framework signing/installation, and physical ES3/Metal behavior. A hook, missing
resource, unsigned-framework requirement or upstream build assertion failure is
a Gate 0 blocker to investigate, not permission to change platforms/backends.

## Gate 0: pinned dependency

The exact revision is in [data/angle-lock.json](data/angle-lock.json): ANGLE
`6ea96bcca6d7f05199f5565c6d5c4722af7269da`, plus pinned depot_tools and the
SHA-256 of ANGLE's DEPS. The checked DEPS and its pinned recursive dependencies
own Git revisions, CIPD versions and GCS compiler object hashes. Important build,
Clang, GN, Ninja and CPython identities are also listed in the manifest; the saved
`gclient-revinfo.txt` records the resolved graph. This is source/dependency locking,
not a claim of byte-identical artifacts across different Xcode/runner versions.

Source basis (all at the pinned revision):

- [ANGLE standalone setup](https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/doc/DevSetup.md)
  documents depot_tools/gclient. Its simulator example is not device evidence.
- [gni/angle.gni](https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/gni/angle.gni)
  wraps `angle_shared_library` with `ios_framework_bundle` on iOS. Build only
  `libEGL` and `libGLESv2`, retaining original bundles and all their resources.
- [DEPS](https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/DEPS)
  provisions pinned GN/Clang/Ninja/CPython. Sync with `--nohooks`; explicitly run
  LASTCHANGE metadata generation only. Do not fetch hermetic Xcode, Rust, trace
  corpora or Dawn/OpenCL dependencies. Some remaining dependencies are upstream
  unconditional. Missing required tooling fails the gate; audit the relevant hook
  rather than running every hook without review.
- [metal_backend.gni](https://github.com/google/angle/blob/6ea96bcca6d7f05199f5565c6d5c4722af7269da/src/libANGLE/renderer/metal/metal_backend.gni)
  defaults iOS internal shaders to the runtime compilation path unless a Metal
  toolchain is supplied. This experiment follows that path, without downloading
  Xcode's optional Metal compiler component or promising precompiled shaders.
- Chromium build at `5987c5fc2c176d5c1329de0832c6b3c28b3638f8`:
  `config/ios/ios_sdk.gni` selects iphoneos for `target_environment="device"`;
  `config/apple/mobile_config.gni` declares `ios_enable_code_signing`.

[args.gn](args.gn) explicitly selects iOS/device/ARM64, system Xcode, deployment
18.0, unsigned Release and Metal only. GL, Vulkan, SwiftShader, WebGPU, null and
OpenCL backends are disabled. Unused GN arguments are fatal. This is a minimal
official pair of dynamic framework targets, not a manually assembled set of
incomplete static archives. Build-system downloads are confined to the explicitly
authorized Gate 0 invocation.

On a Mac with full Xcode selected, Python 3.10+, Git and CMake 3.24+:

```sh
EXPERIMENT=experiments/ios-angle-smoke
# First print/review the plan; no fetch or build:
python3 "$EXPERIMENT/tools/build_angle.py" \
  --workspace /path/to/empty/angle-work --output /path/to/empty/angle-ios-arm64
# Expensive opt-in, ONLY after reviewing the budget above:
set -o pipefail
python3 -u "$EXPERIMENT/tools/build_angle.py" \
  --workspace /path/to/empty/angle-work --output /path/to/empty/angle-ios-arm64 \
  --allow-downloads --jobs 3 2>&1 | tee angle-build.log
```

Use new/empty, separate workspace and package directories. No destructive retry
or automatic checkout reset is implemented. Inspect and retain failed workspaces.
`depot_tools` self-update is disabled. The build records exact system Xcode/SDK
and downloaded Clang versions. It checks the pinned ANGLE/DEPS/build revisions.

### depot_tools bootstrap and the first CI failure

Reported GitHub run #2 (`908e96f8f3`) passed lightweight checks and reached the
`gn gen` invocation after sync, then failed because `python3_bin_reldir.txt` was
missing. Gate 1 correctly stayed skipped. The pinned depot_tools source explains
why successful `gclient sync --nohooks` does not prove Python bootstrap:

- [`gclient`](https://chromium.googlesource.com/chromium/tools/depot_tools/+/816da11f80777dcf8c10bdaa84df18450dcba12a/gclient)
  skips `update_depot_tools` when `DEPOT_TOOLS_UPDATE=0`, and runs through
  `vpython3`. That wrapper independently provisions its CIPD tools/interpreter.
- [`gn`](https://chromium.googlesource.com/chromium/tools/depot_tools/+/816da11f80777dcf8c10bdaa84df18450dcba12a/gn)
  and `ninja` instead invoke `python-bin/python3`. Its metadata is generated by
  [`bootstrap_python3`](https://chromium.googlesource.com/chromium/tools/depot_tools/+/816da11f80777dcf8c10bdaa84df18450dcba12a/bootstrap_python3)
  and `bootstrap/bootstrap.py`, not by ANGLE's DEPS hooks. Disabling self-update
  skipped that initialization path as well as repository updates. PATH already
  selected our pinned wrapper; repeating the same sync cannot repair this split.
  `GCLIENT_PY3=1` is not a bootstrap request for these wrappers.

The build now explicitly sources the pinned `bootstrap_python3` file and calls
its function in a fail-fast Bash subprocess **before sync**. This is the Python
portion used by `ensure_bootstrap`; it avoids that broader script's unrelated
gsutil/pylint provisioning. No `update_depot_tools`, unpinned GN replacement,
system-Python bypass, hand-written metadata or change to ANGLE hooks is used.
The subprocess is equivalent to the following, with `DEPOT_TOOLS_DIR` pointing
to the pinned checkout (the build script runs it automatically on macOS):

```sh
bash -e -o pipefail -c 'source "$1/bootstrap_python3"; bootstrap_python3' \
  angle-depot-bootstrap "$DEPOT_TOOLS_DIR"
```

`DEPOT_TOOLS_UPDATE=0` remains set. The function uses
[`bootstrap/manifest.txt`](https://chromium.googlesource.com/chromium/tools/depot_tools/+/816da11f80777dcf8c10bdaa84df18450dcba12a/bootstrap/manifest.txt)
and its checked-in `manifest.versions` instance pins. Its CPython is
`version:2@3.11.8.chromium.35`; this is separate from ANGLE's existing DEPS-pinned
CPython `version:3@3.11.9.chromium.38`. Neither dependency pin changes.

Before proceeding, the script verifies depot_tools HEAD before/after bootstrap,
requires generated metadata pointing to an installed interpreter inside that
checkout, and probes `python-bin/python3 --version`. Child environment settings
force that pinned checkout/interpreter and remove inherited `VPYTHON_BYPASS`,
`CUSTOM_CIPD_CLIENT` and `CHROMIUM_BUILDTOOLS_PATH` overrides. These overrides were
not established as the cause of the reported run. No global environment changes
are made, and `python-bin` is not prepended to PATH.

After sync, preflight requires the exact DEPS paths for mac-host GN, Ninja,
ANGLE's host Python and Clang. GN/Ninja share the repaired depot_tools Python
wrapper; ANGLE's `.gn` separately needs `third_party/cpython3/host/bin/python3`.
Version probes run before `gn gen`, and bootstrap/tool identities are printed in
the existing captured Gate 0 log and saved in successful build provenance.
Missing tools fail rather than selecting a runner-installed Ninja or GN. The
existing explicit LASTCHANGE generation remains; no other missing initialization
has been confirmed from this error. GN generation, compilation, any later hook
requirements and physical rendering still need the next opted-in macOS/device
build. This bootstrap has not been executed or downloaded on Windows.

`validate_dependency.py` requires two flat unsigned ARM64 iOS Mach-O frameworks,
their matching iPhoneOS plists, exported EGL/GLES3 entry points, `@rpath` install
names, a bounded runtime search path, and closure against the actual iphoneos SDK
TAPI stubs (v4 YAML/v5 JSON). It rejects simulator/macOS binaries even if ARM64,
alternate GL/Vulkan providers, signatures, symlinks and unresolved libraries. It
records `lipo`, `vtool`, `nm`, `otool -L`, dependency metadata and package hashes.
The app resolver checks that inventory and rejects modified/incomplete packages.
Unsigned is intentional: sign the complete bundle locally for installation.

Gate 0's framework rpath allowlist is exact: `@loader_path`, `@loader_path/..`,
`@executable_path/Frameworks`, and `@loader_path/Frameworks`. The last entry was
missing when reported run #6 (`f210d32`) finished 560 compilation tasks and then
failed our validator. Both `/Frameworks` entries are emitted by
[`ios_shared_library_flags` in the pinned Chromium build revision](https://chromium.googlesource.com/chromium/src/build/+/5987c5fc2c176d5c1329de0832c6b3c28b3638f8/config/ios/BUILD.gn).
Accepting that entry corrects our validator; no framework binary or install name
is rewritten, and no dependency or revision check is bypassed.

For `Payload/IOSANGLESmoke.app/Frameworks/libEGL.framework/libEGL`,
`@executable_path/Frameworks` means the app's shared `Frameworks` directory.
`@loader_path/Frameworks` means `Frameworks/libEGL.framework/Frameworks` inside the
app; it does **not** mean the sibling framework directory. It is legal to retain
this upstream search entry even when that nested directory does not exist. Its
presence alone neither requires nested frameworks nor proves dependency resolution.
Gate 0 still requires exact `@rpath/<framework>.framework/<executable>` install
names, exact known peer-framework dependency IDs or checked public SDK libraries,
and the existing iOS/ARM64/deployment/unsigned framework properties. Host absolute
rpaths, unknown tokens, bare relative paths, added suffixes and traversal variants
remain rejected. Gate 1's packager separately resolves the actual app load graph
through its real rpaths and requires every bundled dependency to resolve; the app
links with `@executable_path/Frameworks`. Missing dependencies still fail rather
than treating a loader-relative path as the app root. Synthetic host regression
tests cover these cases; actual app loading remains pending the eventual device
run.

The app must also avoid CMake's automatically generated **build-tree** rpath.
Gate 1 links absolute validated framework binaries from
`$RUNNER_TEMP/angle-ios-arm64/Frameworks`. Those paths legitimately supply
link-time framework search information (`FRAMEWORK_SEARCH_PATHS`/`-F`). Because
the framework install names begin with `@rpath`, CMake also normally adds their
directory to the build-tree runtime search path, emitted by its Xcode generator
as `LD_RUNPATH_SEARCH_PATHS` and ultimately Mach-O `LC_RPATH`. That is the source
of run #10's `/Users/runner/work/_temp/angle-ios-arm64/Frameworks` failure; our
explicit relative linker option did not suppress the automatic entry.

CI packages the build-tree `.app` without running `cmake --install`. The app target
therefore now sets `BUILD_WITH_INSTALL_RPATH=TRUE`,
`INSTALL_RPATH=@executable_path/Frameworks`, and
`INSTALL_RPATH_USE_LINK_PATH=FALSE`, using CMake's runtime-path model instead of
an additional raw `-rpath` flag. See CMake's
[build-with-install-rpath](https://cmake.org/cmake/help/latest/prop_tgt/BUILD_WITH_INSTALL_RPATH.html)
and [build-rpath](https://cmake.org/cmake/help/latest/prop_tgt/BUILD_RPATH.html)
documentation. This changes the application's runtime search path, while keeping
the absolute build-time link inputs. It does not rename or rewrite framework
install names, dependency references, resources or upstream framework rpaths.
Frameworks are still copied intact into `.app/Frameworks`, and Gate 0 checks and
hashes their dependency identities before the app resolver accepts them.

The IPA validator is unchanged: it examines the executable **and every reachable
embedded library**, rejects host absolute rpaths/dependency references, resolves
actual bundled dependencies and rejects unreferenced native libraries. Regression
fixtures inject the runner path into each binary separately and verify rejection,
as well as checking missing/misplaced frameworks and a valid IPA round trip. Host
configuration tests check the CMake target policy; actual generated Xcode settings,
the real bundle's Mach-O load commands and IPA success still require an opted-in
macOS run. No `install_name_tool` patching, path whitelist exception or validator
relaxation is used.

All fetched `LICENSE*`, `COPYING*`, `NOTICE*` and `README.chromium` files are retained
under original paths in `Licenses/`; ANGLE's BSD-style license is mandatory. This
is an overinclusive notice inventory, not a completed legal review of every linked
third-party object. Review the actual resolved closure/notices before redistribution.

## Gate 1: app build using a Gate 0 artifact

The dependency gate can run alone (`build_dependencies=true` and
`build_application=false` in manual dispatch).
The app gate accepts its previously validated artifact; app configuration neither
fetches nor rebuilds ANGLE:

```sh
cmake -S experiments/ios-angle-smoke -B experiments/ios-angle-smoke/build -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DANGLE_ROOT=/path/to/angle-ios-arm64
cmake --build experiments/ios-angle-smoke/build --config Release \
  --target IOSANGLESmoke -- CODE_SIGNING_ALLOWED=NO
```

The UIKit view owns a CAMetalLayer. EGL client extensions and
`eglGetPlatformDisplayEXT(EGL_PLATFORM_ANGLE_ANGLE, ..., METAL_ANGLE)` are required.
There is no `eglGetDisplay` fallback. The app binds the ES API, chooses an ES3
window config, creates an ES3 context and layer-backed EGL surface, then verifies
GL major version >=3 and renderer identity containing ANGLE and Metal. It logs
actual EGL/GL/vendor/GLSL strings, extensions and config attributes.

The original tiny ESSL 3.00 shaders generate a colored triangle from `gl_VertexID`
with a VAO. They need no shader compiler download or resource files. Changing
clear color remains independent of shader compilation. Full compile/link logs
are exported; shader failure leaves explicit clear-only fallback diagnostics.
Other EGL/GL failures stop callbacks visibly with a BLOCKED message; lost contexts
require a relaunch rather than an untested recovery workaround.

PS4 **Triangle / Y** toggles clear-only. **Square / X** selects triangle when its
program is available. Reconnection/resume primes held buttons without synthetic
presses. No touchscreen gameplay controls are present. A controller is optional
to observe the initial automatic triangle.

Callbacks request 30 Hz. The overlay and JSON distinguish requested rate,
successful `eglSwapBuffers` returns/active second, CPU callback time including swap
wait, and callback interval. **Actual display FPS is unmeasured**, and EGL success
does not prove scanout. GL error counts exclude EGL failures, which are separately
reported as fatal diagnostic strings. Thermal state is Apple's categorical value,
not a power measurement. Logging/JSON run at roughly 1 Hz; CPU timing covers the
draw/controller callback before diagnostics export, not total process CPU time.

Before inactivity, stop callbacks, perform a single lifecycle `glFinish`, and
unbind the context before suspension. Foregrounding rebinds it and resets timing
windows. There is no per-frame finish, fence wait, texture upload or framebuffer
readback. Layout updates the layer's pixel size; each frame queries actual EGL
surface size for `glViewport`. Orientation and Home Screen recovery need device
validation, including checking whether this ANGLE revision resizes existing
surfaces correctly without recreation.

## IPA, CI and Windows installation

[ios-angle-smoke.yml](../../.github/workflows/ios-angle-smoke.yml) has path-filtered
`ios-port` push triggers. Ordinary matching pushes run only the Ubuntu lightweight
host-test job (10 minute limit); they skip both macOS build jobs. Unrelated paths
do not start this workflow at all. There are no schedule, PR or repository-dispatch
triggers. Dependency downloads/compilation require one of these deliberate opt-ins:

1. **Commit-message opt-in on `ios-port`:** include the exact, case-sensitive token
   `[run-angle]` anywhere in the **HEAD commit message** of a push. For example,
   `Test ANGLE device build [run-angle]`. The push must also change a file under
   `experiments/ios-angle-smoke/` or `.github/workflows/ios-angle-smoke.yml` to pass
   the existing path filter. A small intentional README change is sufficient;
   an empty commit or a token only in an earlier commit does not activate the
   workflow. This path works with the workflow on `ios-port` and does not depend
   on manual dispatch being registered on the default branch. It requests both
   dependency and app builds. Once that commit is no longer HEAD, later ordinary
   pushes do not inherit its opt-in. Pushing the same opted-in HEAD again, or
   rerunning that workflow, still represents an opted-in build.
2. **Manual dispatch, where registered:** choose the `ios-port` branch and check
   `build_dependencies` (default **false**). Leave `build_application` checked
   (default **true**) for both gates; uncheck it for dependency-only validation.
   Dispatch without `build_dependencies` runs lightweight checks only, even if
   `build_application` is checked or the selected commit contains `[run-angle]`.
   Manual dispatch generally requires default-branch registration, as described
   in [GitHub's event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

The opt-in helper reads GitHub's event JSON, never interpolating commit messages
into shell commands. Its only outputs are literal `true`/`false`. Gate 0 requires
successful lightweight validation and `run_expensive == 'true'`; Gate 1 requires
successful Gate 0 and `build_application == 'true'`. Skipped/failed validation or
dependency jobs cannot start the app job. Gate 1 downloads the verified Gate 0
artifact from the same run, then the existing resolver checks its package hashes.

The 90 minute dependency and 25 minute application limits remain unchanged.
Ordinary pushes do not cancel already-running opted-in builds: workflow-wide
`cancel-in-progress` was removed. Multiple deliberate opt-ins can therefore start
separate builds. Gate 0 still uploads failure logs/GN diagnostics with `always()`;
successful dependency artifacts remain independent of Gate 1. No workflow has
been triggered here, and no default branch registration, commit or push is done
by these scripts.

After compiling, CI validates the executable and all linked frameworks, system
dependencies against selected SDK stubs, deployment/architecture/rpaths/resources
and absence of signing credentials/profiles. It packages and reopens:

```text
Payload/IOSANGLESmoke.app/
  IOSANGLESmoke
  Info.plist
  Frameworks/<upstream EGL and GLES frameworks, including resources>
  Licenses/...
  angle-lock.json
  angle-build.json
```

The ZIP validator checks one application root, safe/unique paths, permissions,
CRC and byte equality with the validated bundle. Gate 1 uploads
`IOSANGLESmoke-unsigned.ipa`, JSON reports, logs and an app evidence tarball.
For a local package (substitute the generated app path):

```sh
python3 experiments/ios-angle-smoke/tools/package_ios.py \
  --app experiments/ios-angle-smoke/build/Release-iphoneos/IOSANGLESmoke.app \
  --sdk "$(xcrun --sdk iphoneos --show-sdk-path)" \
  --output IOSANGLESmoke-unsigned.ipa --report ipa-validation.json
```

Download the unsigned IPA on Windows and have Sideloadly sign/install the app
and both embedded frameworks locally. Credentials/certificates remain outside
this repository. Do not treat successful ZIP validation as installation proof.
Retrieve `angle-smoke.json` and `angle-smoke.log` from the app's Documents folder
using Files/Apple file sharing; Files exposes “On My iPhone” after files exist.
Store exports only in the ignored `device-results/` directory. Logs append across
launches; JSON is the latest snapshot. Inspect Xcode/device console if the app
fails before Documents logging starts (for example a dyld error).

## Checks and device acceptance

Host checks require Python stdlib, no ANGLE checkout. An optional C++ argument-type
test uses an existing host compiler and is skipped when none is available:

```sh
python3 -m unittest discover -s experiments/ios-angle-smoke/tools -p 'test_*.py' -v
```

Tests cover plan-only/no-download behavior, Windows build rejection, locked
framework inventory, unsupported CPUs/platforms/deployment, SDK TAPI metadata,
dependency/rpath rejection, signatures, unsigned IPA round trips and tampering.
Synthetic Mach-O fixtures are validator tests, never evidence of an Apple build.

Latest Windows validation: **76 ANGLE host tests passed**, with one C++ compilation
test skipped because no host compiler is available. This includes configuration
checks for the CMake runtime-path policy and regressions for each bundled binary.
The unchanged Vulkan smoke suite (76) and Zink capability suite (43) also passed,
for **195 passing tests and one skip**. Python AST, plist parsing, changed-file
whitespace and all ten workflow Bash scripts (`bash -n`) passed. Initial
implementation checks also passed the unchanged Vulkan smoke suite (76), Zink
capability suite (43), JSON/plist parsing, local documentation links and whitespace
checks. No YAML parser/actionlint, native C++ compiler,
Xcode or iphoneos SDK was available locally. Workflow structure was reviewed;
The changed Xcode generation and native binary output still need the macOS runner. The
Windows test runner used an existing embedded Python 3.12 runtime without
installing anything. Temporary synthetic IPA fixtures were removed by the tests;
there is no compiled application or installable IPA from this local validation.

Physical acceptance: install on iPhone 16 Plus, export actual ANGLE/Metal/ES3
identity, observe changing clear and triangle, operate both DS4 buttons, reconnect
while held, rotate both landscape orientations, and background/foreground several
times. Check errors, updated pixel dimensions, swap counters, CPU intervals and
thermal trend during a longer run. Use Instruments/Metal capture for actual
display/GPU timing and unexpected passes; no battery/30 FPS guarantee is made.
Stop on unsupported identity, missing symbols/resources, framework signing failure,
context loss or presentation errors. Resolve the specific blocker before adding
textures, OSG or engine integration.
