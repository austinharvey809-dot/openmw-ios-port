# Milestone D: genuine ESM/ESP reader and synthetic TES3 fixture

**Status: source-reviewed, with independent Linux GCC 14.2/C++20 compile, link
and ten-case runtime success reported by the user. macOS execution and iPhoneOS
compilation remain unverified.** This Windows workflow-preparation session did
not repeat that Linux build or run an Apple compiler. The genuine separate pinned
OSG checkout after the initial audit found no headers in Downloads/`extern`.
The actual math header closure is now verified. The target compiles real OpenMW
sources, generates `osg/Config` from the original upstream template, and links
no renderer or GUI. The Linux result establishes that selection on GCC, without
OSG rendering libraries; a real macOS link/run must still establish it on Xcode.

Baseline: `ios-port`, commit
`1b4f9a3e65be07a4f32f11450bed384d32a9c214`. The user reports independent native
success for A/B/C, including C run `42543465325`. Those results establish the
existing file/BSA/VFS foundation, not this reader's compilation or execution.
The nine unfinished Build #15 graphics files, A/B/C, engine sources, pins and
graphics applications are preserved.

## Selected next target

The implemented test targets **genuine `ESM::ESMReader` parsing a TES3/HEDR
header followed by one GMST record**, traversing its NAME and INTV subrecords.
Use two original synthetic variants (ESM type 1 and ESP type 0), a real
`ToUTF8::Utf8Encoder(WINDOWS_1252)` and genuine `ESM::RefId` string handling.
Do not compile a world/store, full cell loader, gameplay, physics or rendering.

Only the generic reader is selected; reading GMST tags/fields directly through
its public APIs does not claim to execute a high-level game-setting loader or
resolve the game store. A four-byte TES3 detector alone would be a smaller but
less meaningful step and would not satisfy record parsing.

## Exact available project source inventory

[`data/source-audit.json`](data/source-audit.json) records the source-inspected
candidate link closure, complete textual project-header closure, external
include roots and complete-file SHA-256 hashes. **The user independently
verified this link closure on Linux GCC 14.2.** The manifest's source-audit
booleans are not runtime/build attestations; they stay conservative during
preflight and do not supersede separate native evidence. macOS and device
toolchain compatibility still requires their actual builds.

| Group | Genuine translation units |
| --- | --- |
| Reader/header/cache and coupled writer/cell-ID definitions | `components/esm3/esmreader.cpp`, `readerscache.cpp`, `loadtes3.cpp`, `esmwriter.cpp`, `cellid.cpp` |
| Identifier implementations | `components/esm/refid.cpp`, `stringrefid.cpp`, `formid.cpp`, `generatedrefid.cpp`, `indexrefid.cpp`, `esm3exteriorcellrefid.cpp` |
| Encoding and logging | `components/toutf8/toutf8.cpp`, `components/debug/debuglog.cpp` |
| File opening/path conversion | `components/files/openfile.cpp`, `components/files/conversion.cpp` |

That is **15 translation units plus 38 project headers**:

```text
components/debug/debuglog.hpp
components/esm/common.hpp
components/esm/decompose.hpp
components/esm/defs.hpp
components/esm/esm3exteriorcellrefid.hpp
components/esm/esmcommon.hpp
components/esm/formid.hpp
components/esm/fourcc.hpp
components/esm/generatedrefid.hpp
components/esm/indexrefid.hpp
components/esm/position.hpp
components/esm/refid.hpp
components/esm/serializerefid.hpp
components/esm/stringrefid.hpp
components/esm3/cellid.hpp
components/esm3/cellref.hpp
components/esm3/esmreader.hpp
components/esm3/esmwriter.hpp
components/esm3/formatversion.hpp
components/esm3/loadcell.hpp
components/esm3/loadtes3.hpp
components/esm3/readerscache.hpp
components/esm3/refnum.hpp
components/esm4/common.hpp
components/files/conversion.hpp
components/files/openfile.hpp
components/misc/algorithm.hpp
components/misc/concepts.hpp
components/misc/constants.hpp
components/misc/guarded.hpp
components/misc/hash.hpp
components/misc/notnullptr.hpp
components/misc/strings/algorithm.hpp
components/misc/strings/conversion.hpp
components/misc/strings/lower.hpp
components/misc/utf8stream.hpp
components/toutf8/tablesgen.hpp
components/toutf8/toutf8.hpp
```

This is a recursive textual include audit, not preprocessor/dead-strip analysis.
Hashes cover all 53 complete project files, normalizing **only CRLF to LF** so
Windows and macOS checkouts compare consistently. The initial normalized bytes
were independently compared with their Git blobs at the recorded commit. The
separate preservation check for unfinished graphics files uses raw-byte hashes.

Why the apparently unused definitions remain in the candidate:

* `ESMReader::resolveParentFileIndices()` references `ReadersCache` methods.
* `Header::blank/load()` are needed by reader open/close. `Header::save()` shares
  `loadtes3.cpp` and references writer definitions. `CellId` load/save definitions
  likewise couple the reader and writer. Do not strip these source methods or
  rely on linker dead stripping to hide unresolved symbols.
* `ESMReader::getCellId()` references `CellId` and exterior/string RefIds. The
  generic RefId implementation dispatches across all six listed identifier
  implementations; they are not all implemented in `refid.cpp` alone.
* Encoder calls are compiled even if a fixture leaves its pointer null. Use the
  genuine implementation and checked-in tables. Its logging references require
  real `debuglog.cpp`, not a no-op replacement.
* `loadcell.hpp`/`cellref.hpp` declarations are reached, but this does not alone
  require `loadcell.cpp`/`cellref.cpp` or loading a cell. Lua-related pointers in
  the reader are forward declarations, not evidence of a Lua runtime dependency.

The observed external includes are standard C/C++ headers plus `osg/Vec3f`.
System threading is relevant to the real logger and guarded identifier pool.
No Boost, Bullet, SDL, MyGUI, compression, ICU/iconv runtime or external
serialization headers were found in this closure. Existing encoding tables are
sufficient; no generator or dependency download is needed for them.

## Genuine pinned OSG dependency closure

Verified checkout: `C:/Users/austi/Projects/OpenSceneGraph-pinned`, Git HEAD
`9b384d5439977784e5cd250ff8ff7966928ddd27`, clean at inspection. No files were
changed there. Earlier Downloads/`extern` searches found only source fragments
and adapters; this newly supplied checkout resolves the source/header blocker.

The complete used route is:

```text
components/esm3/esmreader.cpp -> loadcell.hpp -> cellref.hpp
  -> components/esm/position.hpp -> osg/Vec3f
       -> osg/Vec2f -> osg/Math -> osg/Export -> osg/Config
       -> osg/Math (same dependency)
```

The four original headers are `include/osg/{Vec3f,Vec2f,Math,Export}`. Math adds
only standard `<cmath>` and `<cfloat>`. Export requires the generated
`osg/Config`, whose genuine template is `src/osg/Config.in`. No `osg/GL`, ANGLE,
OpenThreads, viewer or window-system header is in this chain.

The manifest locks the complete LF-normalized contents of those four headers,
the Config template, OSG `CMakeLists.txt` and `LICENSE.txt` (seven files). Their
contents were compared with the exact commit's Git blobs. The preflight checks
Git HEAD and every locked file on each supplied checkout. Its per-command
`safe.directory` setting handles this explicitly user-supplied read-only
checkout under the Windows sandbox account; no global Git setting is changed.

The isolated CMake project uses `configure_file()` on the verified, complete
upstream Config template in its **own build directory**. It supplies all 15
real template switches: usual fork defaults for math/ref-pointer/features,
window-system NONE, Carbon off, UTF-8 filename option off, and MSVC warning
suppression off. The math headers do not use matrix/bounds/ref-pointer feature
switches; Export's MSVC warning pragma remains disabled. This is configuration
generation, not an empty substitute header or a made-up OSG class. It neither
runs the OSG renderer CMake project nor writes into the OSG checkout. This
math-only configuration must not be substituted for an ABI-matched renderer
configuration in a later integration.

`Vec3f`/`Vec2f` constructors, arithmetic and ordering used by `ESM::Position` are
inline. **Math also declares non-inline `asciiToDouble` and `findAsciiToDouble`**
(and inline wrappers that call them). Header presence alone therefore proves
nothing about arbitrary OSG code linking. The selected reader/fixture does not
call these conversion functions. The actual host fixture exercises Position,
Vec3f and tuple ordering and must link the complete reader without any OSG
library. That link passed independently on Linux; the macOS link remains
unexecuted. If undefined symbols appear on a new toolchain, report the exact
evidence before broadening dependencies. No linker dead-strip trick,
undefined-symbol allowance or substitute implementation is used.

## Reader behavior and malformed-input findings

Verified from current sources:

* `open(path)` uses `Files::openBinaryInputFileStream()`. A missing input throws
  `std::system_error`; an input-only `ifstream` does not create a missing file.
  This differs from the existing BSA API's create-if-missing behavior.
* `open(std::unique_ptr<std::istream>&&, name)` transfers stream ownership.
  `openRaw()` seeks to the end to determine size, then back to the beginning;
  inputs must be valid seekable streams. A null/nonseekable stream is outside
  this fixture and is not validated here.
* `open()` requires the first tag to be TES3, reads its record header and calls
  `Header::load()`. Legacy input without FORM uses format version 0.
* `Header::load()` reads HEDR with **`if (isNextSub("HEDR"))`**: HEDR is optional
  in this implementation. It reads its fields but does not explicitly require
  the subrecord's declared size to equal 300. This fixture requires the expected
  HEDR field values as its own data contract; it does not attribute that
  restriction to the engine. Header record-count metadata is not a whole-file
  count validator.
* A TES3 record header is a four-byte tag, payload size, unused word and flags
  (16 bytes). `getRecHeader()` checks remaining bytes against the header and
  declared record payload. `getRecName()` rejects unread previous-record bytes.
* Subrecord names and sizes are four bytes each. `isNextSub()`/`peekNextSub()`
  cache names; callers must respect whether a name has already been consumed.
  `getHNT()` checks the exact expected typed payload size before reading.
* `getSubHeader()` subtracts the declared payload size from `leftRec` and may
  leave it negative. `getRecName()` can backtrack a negative remainder. This is
  observable compatibility behavior, not a strict subrecord-range clamp.
* `getExact()` calls `mEsm->read()` without testing `gcount()` or stream status.
  The default file opener sets exceptions to **`badbit` only**. Short reads that
  set EOF/failbit are therefore not universally guaranteed to throw. Do not
  advertise blanket truncated-file rejection or treat it as a bounded stream.
* `skip()` reads small ranges and seeks for ranges over 4096 bytes without an
  explicit source-level EOF bound. `getStringView()` sizes a buffer from the
  requested size before reading. These are further reasons to keep malformed
  fixtures tiny and avoid malicious huge allocations in this milestone.
* `fail()` throws `std::runtime_error` with file, record, subrecord and attempted
  offset context. After stream failure, a reported offset need not be valid.

The strict truncation test uses the **existing public stream API**:
open a real file using the real file helper, enable `failbit | badbit` exceptions
on that standard stream, then transfer it into `ESMReader`. This is an explicit
caller I/O policy, not a fake decoder or an upstream hardening fix. Test and
report it separately from the unchanged default path-opening behavior.

The previously documented malformed-BSA undersized-directory allocation issue
also remains unchanged; nothing in an ESM fixture would repair or supersede it.

## Implemented deterministic fixture and coverage

`tools/fixtures.py` generates original bytes independently with Python `struct`,
never an engine writer or copied game file:

1. A 300-byte legacy HEDR payload: 1.3 version bits (`0x3fa66666`), type 1/0,
   32-byte padded author containing Windows-1252 `Caf\xe9`, a 256-byte original
   description and record count 1. With subrecord/header framing, TES3 is 324
   bytes. No masters, FORM, screenshot or savegame content.
2. One valid GMST record: NAME `iIOSProbe\0` (10 bytes) and INTV holding original
   signed value `-1234567` (4 bytes). Its framed payload is 30 bytes and complete
   record is 46 bytes. Total file size is 370 bytes, with little-endian words.
3. Use the real UTF-8 encoder, kept alive longer than the reader. Check version,
   type, author/description, masters, declared count and file size after open.
   Use `getRecName()`, `getRecHeader()`, cached-name peek/check behavior,
   `getHNRefId("NAME")` and `getHNT(value, "INTV")`. Verify sizes, flags,
   identifier case semantics, exact value, exhausted record/file counters and
   final offset. Close/reopen the same reader to test `skipRecord()` and reuse.
4. Cover missing input, wrong TES3 tag, incomplete record header, record payload
   declared beyond file size, and INTV's declared-size mismatch. Attribute each
   rejection to the actual file helper or reader check.
5. Separately test a tiny short-read case through the strict stream overload:
   shorten final INTV bytes and adjust the enclosing record size to the actual
   file length so the read itself reaches failbit. Do not label this caller-
   configured exception as proof of the default reader's EOF enforcement.
6. Snapshot the owned synthetic-input tree, verify hashes and filenames after
   every subprocess, and require the missing path to stay nonexistent. No
   `ESMWriter` operations, assets, renderer or full startup are invoked.

There are eight generated input files and **ten subprocess cases**: ordinary
ESM/ESP reads, a strict valid stream, five reader-generated structural
rejections, a strict short-read rejection and missing-file rejection. All inputs
are at most 370 bytes. The C++ fixture distinguishes `ESM Error:` checks,
`std::ios_base::failure` from the explicit caller policy, and the file helper's
missing-input exception. Fixture assertions cannot masquerade as these expected
reader/I/O errors. Full negative-case error text remains in the log.

The driver checks exit codes, mode-specific completion markers, the complete
input tree and SHA-256 after every subprocess. It prints final hashes and the
mandatory ten-case completion marker. Python tests verify the binary framing,
known valid-file hash and driver rejection paths; mocked processes test only
the driver. **None of the C++ parsing cases ran in this Windows session; all ten
passed in the user's independent Linux test.** This is not
comprehensive malformed-input security coverage. Writer definitions satisfy real
source coupling only; no writer operation is called.

## Offline validation and local commands

Use an already available Python interpreter, from the repository root:

```powershell
$env:OPENMW_ESM_OSG_SOURCE = 'C:\Users\austi\Projects\OpenSceneGraph-pinned'
python -B -m unittest discover -s experiments/ios-openmw-esm/tools -v
python -B experiments/ios-openmw-esm/tools/audit_sources.py --osg-source "$env:OPENMW_ESM_OSG_SOURCE" --require-complete
git diff --check
```

The audit verifies 53 full OpenMW source/header hashes and seven genuine OSG
files plus the true math include closure and Config template switches. Without
`--osg-source`, it can audit project sources only; `--require-complete` rejects
that incomplete invocation. Even a complete source audit reports
`link_closure_verified: false` and `native_ready: false`: these tools do not
invent native results. Optional `--resolve` emits verified paths for CMake.

Regression tests cover wrong revisions/hashes, missing/unsafe paths, true header
routes, upstream I/O behavior, generated Config use, target isolation, synthetic
layout, process failures, missing evidence and input mutations/creation. On
Windows the native C++ test explicitly skips. On a native POSIX host with the
real pinned checkout and existing CMake/CTest/C++20 tools, that optional test
builds and runs the real fixture; actual build/link/runtime errors fail it.
No package installation or fallback classes are provided.

## Manual native GitHub Actions validation

[`.github/workflows/ios-openmw-esm.yml`](../../.github/workflows/ios-openmw-esm.yml)
has the exact name **iOS OpenMW ESM reader native validation**. It uses only
`workflow_dispatch`: no push, pull-request, schedule or commit-message trigger.
The independent jobs are `host-validation` and `iphoneos-compilation`, both
`macos-26` with 20-minute timeouts. They use the runner's selected Xcode and
record the actual image, compiler and SDK versions; no tools are installed.

GitHub generally requires the workflow to exist on the default branch before
exposing manual dispatch. Once registered, select **Actions → iOS OpenMW ESM
reader native validation → Run workflow → ios-port**. Registration and dispatch
have not been attempted during preparation. Both jobs enforce
`refs/heads/ios-port` and check out the exact `${{ github.sha }}` for that run.

Each job independently checks out two sibling directories under
`$GITHUB_WORKSPACE`: `openmw/` for this repository and `osg-pinned/` for
`OpenMW/osg` at literal commit `9b384d5439977784e5cd250ff8ff7966928ddd27`.
Checkouts use depth 1, no submodules, no LFS and no persisted credentials.
Only the approved pinned OSG dependency is obtained; no ANGLE, renderer,
package manager or additional dependency download/build is invoked. The local
Windows OSG checkout is unrelated to those ephemeral runner directories and is
left untouched.

Both jobs verify the requested OpenMW commit and pinned OSG revision and run the
existing complete source/header audit **before building**. The evidence helper
records all 53 OpenMW and seven OSG raw SHA-256 values, their LF-normalized
counterparts, the exact audit manifest, revision provenance, licenses and
additional validation-input hashes (experiment files, workflow, reused A
validator and the existing OSG pin declaration). Source mismatch is fatal.

After CMake configuration, a separate strict check compares the generated
`osg/Config` against expansion of the entire audited upstream template using
the existing 15 settings. It copies the actual generated file and records its
raw/canonical checksums. This helper verifies configuration content; it does
not generate a replacement header or claim that a C++ compiler ran.

Host acceptance requires:

* The **complete** Milestone D Python suite succeeds. Its optional POSIX CMake
  test also executes when the existing native host toolchain is available.
* Xcode configures `OPENMW_IOS_ESM_HOST_TESTS=ON`, then compiles and links
  `openmw-esm-check` with verbose compiler/linker logs, genuine reader code and
  OSG math, without OSG rendering libraries.
* Verbose CTest succeeds with the exact selector `^openmw-esm-runtime$` and
  `--no-tests=error`. The completion marker for **ten successful subprocess
  cases with unchanged input tree** is mandatory. The existing driver checks
  process outcomes, exact markers, all input hashes/tree names and missing-file
  noncreation. Compilation, linking, runtime and integrity errors fail the job.

Device acceptance requires:

* Genuine iPhoneOS SDK, ordinary ARM64 and exactly minimum iOS 18.0, with signing
  disabled during compilation of `openmw-ios-esm-reader`'s 15 real sources.
* Exactly one nonempty `libopenmw-ios-esm-reader.a` inside the isolated build
  tree. Missing, empty or ambiguous matches fail; actual paths are recorded,
  not guessed from Xcode output conventions.
* `tools/validate_esm_archive.py` requires exactly the manifest's 15 reviewed
  translation units. Xcode `.o` and CMake `.cpp.o` spellings are accepted;
  duplicate aliases for a source, missing/extra/unexpected/unsafe/empty members
  are rejected. Symbol index tables are not counted as translation units.
* Every object uses Milestone A's unchanged ar/Mach-O parser and must be a
  little-endian 64-bit `MH_OBJECT`, ordinary ARM64, iOS-device platform and
  exactly minimum 18.0. macOS, simulator, Catalyst, ARM64e, wrong architectures,
  bitcode, and missing/malformed/ambiguous deployment metadata fail closed.
  Native `lipo`, `ar` and per-object `otool` commands must also succeed.

Separate evidence artifacts upload with `always()` on success/failure, with
missing evidence treated as an error and 14-day retention:

| Artifact | Runner evidence directory |
| --- | --- |
| `ios-openmw-esm-host-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-esm-host-evidence/` |
| `ios-openmw-esm-device-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-esm-device-evidence/` |

Common files include `run.txt`, `source-provenance.json`, `source-audit.log`,
`source-sha256.txt` (60 raw hashes), `source-sha256-lf.txt` (60 canonical hashes),
`validation-input-sha256.txt`, `source-audit-manifest.json`, OpenMW/OSG licenses,
toolchain/configure/build logs, `config-validation.json`, `generated/osg/Config`,
`build-diagnostics/`, `archive-location.json`, the available static archive,
`job-status.txt`/`.json`, and overall `SHA256SUMS`. Manifests explicitly
distinguish canonical source checks from actual generated/binary byte hashes.

The host package additionally includes `python-tests.log`, verbose `ctest.log`,
CTest diagnostics and eight generated files under `synthetic-esm/`, with hashes
in driver output and the overall manifest. The host archive is macOS output,
not a device archive. The device package additionally contains
`archive-validation.log` and `archive-inspection/` with
`archive-validation.json` (per-member source, architecture, platform, deployment
and hashes or failure reason), `archive-tools.log` (including member inventory)
and extracted `objects/` with raw per-object `otool` headers/load commands.

Partial inputs/configuration/archives and nested CMake/CTest failure logs survive
failures. Missing tools and evidence-collection errors fail closed. If checkout
itself fails, an inline fallback preserves available initial diagnostics/status
and hashes without needing repository helpers. `job-status.json` records the
validation outcome after the validation steps and the evidence-collection result
immediately before upload. The GitHub final job conclusion is authoritative:
an upload failure/cancellation happens later and cannot be predicted inside an
artifact uploaded by that job. Hard runner termination can also prevent upload.

Offline contracts cover the exact pinned sibling checkouts, manual triggers,
source/config validation order, ten-case requirement, strict 15-object format,
artifact handoff, wrong platforms, missing tools, failure preservation,
checksums and shell/embedded-Python syntax. Synthetic Mach-O bytes test only
the validator, never substitute OpenMW or OSG implementations. A full GitHub
workflow-schema check and actual Xcode/SDK compatibility remain for the real
runner; no native Apple success is inferred from local contracts or Linux.

## Native macOS and iPhoneOS requirements

Requirements: CMake 3.24+, Python 3.10+, Git for local revision checks, a native
C++20 compiler/standard library and system Threads, and the existing genuine
pinned OSG checkout. Use macOS/Xcode with an iPhoneOS SDK for device compilation.
No dependency or renderer build is necessary merely to generate the inspected
Config template. Native Apple compilation/linking has not been attempted here.

Future macOS host commands (use the actual local checkout path):

```sh
cmake -S experiments/ios-openmw-esm -B experiments/ios-openmw-esm/build-host \
  -DOPENMW_IOS_ESM_HOST_TESTS=ON -DOPENMW_ESM_OSG_SOURCE=/path/to/OpenSceneGraph-pinned
cmake --build experiments/ios-openmw-esm/build-host --target openmw-esm-check --parallel 3
ctest --test-dir experiments/ios-openmw-esm/build-host \
  --verbose --output-on-failure --no-tests=error -R '^openmw-esm-runtime$'
```

The executable link is part of acceptance: it must resolve real OSG math and
all reader symbols without libosg/GUI/rendering libraries. Ten cases must pass
with unchanged input tree. Creating a static archive alone cannot establish
that the source closure links.

Future iPhoneOS compilation, after manual review:

```sh
cmake -S experiments/ios-openmw-esm -B experiments/ios-openmw-esm/build-ios -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DOPENMW_ESM_OSG_SOURCE=/path/to/OpenSceneGraph-pinned
cmake --build experiments/ios-openmw-esm/build-ios --config Release \
  --target openmw-ios-esm-reader -- -jobs 3 CODE_SIGNING_ALLOWED=NO
```

The separate target defaults to iPhoneOS and rejects macOS/simulator/architecture
or deployment misselection unless explicit host mode is enabled. It directly
compiles the 15 listed real files rather than linking A/B/C and accidentally
including BSA/rendering dependencies or duplicate file symbols. Earlier targets
and exact-object acceptance contracts are unchanged. The dedicated native
workflow records all source/header/generated-Config provenance, commands,
SDK/compiler versions, archive hashes and each object's ARM64, iOS-device,
minimum-18.0 metadata. That workflow is prepared but has not run.

The source audit log is written under the isolated build directory as
`source-audit.log`, alongside `osg-math-resolved.cmake` and the generated
`osg-math/include/osg/Config`. These are untested future configure outputs,
not locally produced compilation artifacts. A device static build would still
not prove device linking, iPhone execution or real-content loading.

## Remaining work toward game content

First compile/link/run this real reader fixture on macOS and compile for
ARM64 iPhoneOS, resolving only evidenced failures. Then test actual sandboxed
file I/O on an iPhone, review malformed-input hardening and user-owned data
import, integrate reader streams with genuine VFS where appropriate, resolve
masters/load order and audit selected higher-level record loaders. Decode NIF
and image resources before connecting real assets to the preserved graphics
foundation. No world/store or full `Engine::go()` startup occurs here.

OpenMW's existing license and OSG's genuine `LICENSE.txt`/header notices remain
applicable; preserve them in future redistributed source/binary evidence.
No proprietary game content, dependency changes, external checkout edits or
rendering behavior changes are included.
