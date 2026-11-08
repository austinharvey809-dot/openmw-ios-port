# First OpenMW data-core compilation milestone

Status: source/build and dedicated manual CI preparation only. Offline contracts
pass; the real C++ runtime check is skipped on Windows. No CMake configuration,
C++ compilation, iPhone build, CI run or engine execution has been performed here.

This is milestone A: compile a small, dependency-free subset of actual OpenMW
component code for iPhoneOS ARM64. It is not the complete `components` library,
`openmw-lib`, an `OMW::Engine` instance, a game scene or an installable application.
See [the readiness audit](../../docs/ios-port/engine-readiness-audit.md).

The static target `openmw-ios-data-core` compiles these repository files directly:

- `components/files/conversion.cpp`
- `components/files/openfile.cpp`
- `components/files/constrainedfilestreambuf.cpp`
- `components/platform/fileposix.cpp`
- `components/vfs/manager.cpp`

Their inspected project-header closure requires standard C++20 and POSIX file
APIs, with no SDL, OSG, ANGLE, Boost, Lua, UI, audio or game assets. Sources are
neither copied nor patched. The standalone CMake project avoids root OpenMW's
desktop dependency discovery and FetchContent entirely. Default configuration
rejects anything other than iPhoneOS ARM64 with deployment target 18.0. Host
execution requires the explicit `OPENMW_IOS_CORE_HOST_TESTS=ON` option and a native
POSIX host. No dependencies are downloaded by configuration or the tests.

The optional host executable links these actual implementations and checks:

- Complete binary file reading and constrained-range reads/seeks.
- UTF-8 filesystem-path conversion and VFS case/slash normalization.
- `VFS::Manager` indexing, file dispatch, last-added archive precedence,
  recursive index iteration, missing-resource failure and reset.

The archive adapter in `tests/core_check.cpp` is a test-only bridge to the real
bounded file reader. It does not claim BSA decoding or the full engine's loose-file
archive implementation. The fixture writes ten original ASCII bytes to the named
file in its owned build/test directory; it does not load Morrowind data. VFS path
normalization is not an iOS filesystem sandbox or a document-import policy.

## Local Windows checks

Using an existing Python 3.10+ installation, without installing anything:

```powershell
python -m unittest discover -s experiments/ios-openmw-core/tools -p 'test_*.py' -v
```

In this workspace the Windows `python` aliases are not a usable installation;
validation used the already installed MO2 embedded Python 3.12, with bytecode
writes disabled. Do not install dependencies merely to run this milestone.
The runtime test explicitly skips on Windows; source contracts do not prove that
libc++/Clang or iOS can compile these files.

## Future macOS host execution

These are instructions for a later manual/CI run, not commands executed during
implementation. Use existing CMake and a C++20 compiler:

```sh
cmake -S experiments/ios-openmw-core -B experiments/ios-openmw-core/build-host \
  -DOPENMW_IOS_CORE_HOST_TESTS=ON
cmake --build experiments/ios-openmw-core/build-host --parallel 3
ctest --test-dir experiments/ios-openmw-core/build-host --output-on-failure
```

Passing this executes actual OpenMW data-component code on the host. It establishes
neither iPhone execution nor an engine launch. A compile error is evidence to
investigate; do not add forced includes, substitute file backends or copy functions
to make the check pass without explaining the source issue.

## Future iPhoneOS compilation

Full Xcode with an iPhoneOS SDK, CMake >=3.24 and the repository checkout are
required. ANGLE/OSG rebuilding is unnecessary for this first target.

```sh
git rev-parse HEAD
git diff -- components/files components/platform components/vfs components/misc/strings
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
cmake -S experiments/ios-openmw-core -B experiments/ios-openmw-core/build-device -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0
cmake --build experiments/ios-openmw-core/build-device --config Release \
  --target openmw-ios-data-core -- -jobs 3 CODE_SIGNING_ALLOWED=NO
xcrun lipo experiments/ios-openmw-core/build-device/Release-iphoneos/libopenmw-ios-data-core.a -info
xcrun lipo experiments/ios-openmw-core/build-device/Release-iphoneos/libopenmw-ios-data-core.a -verify_arch arm64
xcrun ar -t experiments/ios-openmw-core/build-device/Release-iphoneos/libopenmw-ios-data-core.a
xcrun otool -l experiments/ios-openmw-core/build-device/Release-iphoneos/libopenmw-ios-data-core.a
```

Review every object's platform load command for iOS device compatibility and
deployment target, not architecture alone. ARM64 macOS/simulator objects are not
acceptable device evidence. Record configuration/build logs, SDK/Xcode versions,
source revision/differences, archive member list and Mach-O inspection alongside
the library. Preserve repository license notices with future distributed artifacts.
The Xcode output path above is expected, not verified on this host.

## Dedicated manual GitHub Actions workflow

[ios-openmw-core.yml](../../.github/workflows/ios-openmw-core.yml) has only
`workflow_dispatch`: no push, pull-request, scheduled or commit-message trigger.
Ordinary pushes and `[run-openmw-core]` do not activate it. GitHub normally must
register the workflow from the repository's default branch before offering its
manual dispatch UI/API. Adding it only to ios-port may therefore be insufficient.
After manual review and registration through your normal Git process, select
**ios-port** in Actions -> iOS OpenMW data-core native validation -> Run workflow.
Both jobs verify that branch and the checked-out commit; dispatching another
branch fails with evidence rather than validating an unintended revision.
No default-branch changes, commits, pushes or dispatch requests were performed.

Two independent jobs use **macos-26**, matching the established graphics workflows,
with the runner's installed full Xcode, CMake, Python and Apple C++20 compiler.
No package installation or ANGLE/OSG/other engine dependency fetch is configured.
The active Xcode/SDK/image versions are recorded, not presumed fixed across runner
updates. Missing tools or compilation errors fail normally; no substitutions,
forced include files or continue-on-error flags are used.

- **host-validation:** isolated Python contracts, Xcode CMake configuration with
  OPENMW_IOS_CORE_HOST_TESTS=ON, build of openmw-data-core-check, then CTest with
  Release configuration, output-on-failure and no-tests=error. Its success proves
  this data fixture executed on macOS, not on iPhone or in OMW::Engine.
- **iphoneos-compilation:** separate Xcode CMake configuration with host tests OFF,
  the resolved iPhoneOS SDK, ARM64 and deployment 18.0, then compilation of
  openmw-ios-data-core only. Each of the five actual repository translation units
  must appear exactly once in the resulting archive.

Both jobs must pass acceptance. They have no dependency on each other, so a host
failure does not hide device compilation diagnostics. Neither invokes the unfinished
Build #15 OSG experiment, its tests, its overlay builder or its package validator.

### Strict archive acceptance

`tools/validate_archive.py` uses existing Xcode lipo/ar/otool tools for raw evidence
and a separate stdlib parser for every embedded object. It requires:

- A regular BSD/GNU ar archive with exactly the five expected source objects,
  accepting Xcode's `source.o` or CMake's `source.cpp.o` names. Duplicate, missing,
  extra or unsafe names fail; symbol/name-table members are handled separately.
- Exactly ordinary ARM64, both through lipo verification and each Mach-O header.
  Fat archives, bitcode-only inputs, x86_64, arm64e and non-object members fail.
- LC_BUILD_VERSION with **iOS device platform 2** and minimum OS **18.0.0** in every
  object. macOS, iOS Simulator, Catalyst/other platforms, legacy ambiguous metadata,
  duplicate/missing build commands and a different minimum OS fail.

SDK version is recorded from each object, but may legitimately be zero for
relocatable objects; it is not substituted for mandatory platform/deployment
metadata. The selected SDK version/path is also recorded from xcrun. Architecture
alone can never make a macOS/simulator archive pass. This validates compile output,
not final application linkage, SDK dependency closure or device execution.

### Evidence and failure artifacts

Each job initializes its evidence directory in RUNNER_TEMP before checkout and
uploads it with `always()`, missing-files=error and 14-day retention:

- `ios-openmw-core-host-<run-id>-<attempt>`: commit/ref, runner/Xcode/SDK/compiler/
  CMake/Python versions, source checksums, traced configure/build/CTest commands
  and output, Python test log, CMake/CTest diagnostics and the host static library
  when available (explicitly named `host-libopenmw-ios-data-core.a`).
- `ios-openmw-core-device-<run-id>-<attempt>`: equivalent source/toolchain/build
  evidence; `libopenmw-ios-data-core.a` when produced; ar member listing and lipo
  results; individual extracted objects and otool headers/load commands; and
  `archive-inspection/archive-validation.json` with per-object source identity,
  platform, minimum OS, SDK and SHA-256.

Both include the OpenMW license and SHA256SUMS over the evidence files. The source
manifest covers the experiment/workflow and relevant repository data-component
directories, including the five selected source files and their project headers.
Pipefail preserves compiler/test failure exit codes while tee keeps output. CMake
configuration logs/caches and CTest failure logs are copied when available. A raw
archive may be uploaded after failed validation; its presence is not acceptance:
require both jobs successful and `archive-validation.json` valid=true. Early
failures may lack later-stage files, but retain the evidence produced so far.

Offline workflow tests inspect trigger/job/command/artifact contracts and syntax-
check every Bash block without running it. Synthetic archive regressions exercise
platform/architecture/deployment/inventory rejection and retained failure evidence.
These checks use no new dependencies and do not replace the first real macOS run.

Local workflow implementation checks: **19 passed, one skipped** (the original
POSIX C++ runtime fixture on Windows). All 12 workflow Bash blocks passed `bash -n`
without execution; four Python files passed AST parsing. Trigger/job/artifact,
strict archive/Mach-O, retained-failure-evidence, whitespace and documentation-link
checks passed. Existing observer files were checked against their starting hashes;
the five source files and reviewed CMake target were unchanged. No local native
build, dependency download, GitHub run, commit or push occurred. The YAML contracts
are structural checks, not a claim that GitHub has parsed or executed the workflow.

## Boundary and next integration

The next native acceptance is a successful device archive plus successful macOS
runtime checks. A subsequent separate UIKit app can call the bounded data-code
check once against a bundled fixture and export the result while preserving the
Build #14 graphics/context design. That requires reviewing bundle-path plumbing,
app packaging and actual phone execution; none is implemented here.

Do not link this subset alongside the complete OpenMW `components` library:
they define the same symbols. It is a temporary source-isolation target, to be
replaced by a deliberately partitioned component build or the real target later.
Expanding into `FileSystemArchive`, BSA/NIF/resource loading or ShaderManager needs
a separately audited dependency closure. The engine-readiness report lists the
next gates; this probe does not resolve them.

The nine pre-existing unfinished Build #15 files, all working graphics experiments,
dependency pins, remotes and engine sources are preserved. No commit, push, CI,
dependency fetch or native build was performed.
