# Milestone C: original Morrowind BSA through genuine OpenMW VFS

This isolated experiment registers synthetic original-format BSAs with
`VFS::BsaArchive<Bsa::BSAFile>` and retrieves payloads through `VFS::Manager`.
It reuses Milestones [A](../ios-openmw-core/README.md) and
[B](../ios-openmw-bsa/README.md) unchanged and adds real OpenMW encoding/logging
sources. It does not start the engine, parse ESM/NIF files, load copyrighted game
content, create an application or interact with the graphics experiments.

Baseline: branch `ios-port`, commit
`634caacb5ee68d651aaf7574603954085566ec1c`. The user reports successful Milestone
B native host execution and iPhoneOS ARM64/iOS 18.0 compilation in run
`42535463699`, independently validating the BSA and data-core archives. Those
results do **not** prove this new integration's compilation or runtime behavior.
The nine unfinished Build #15 graphics files remain separate and unchanged.

## Source audit and chosen integration

[`bsaarchive.hpp`](../../components/vfs/bsaarchive.hpp) provides the genuine
header-only `BsaArchive<T>` and `BsaArchiveFile<T>` implementations. The original
adapter owns its `BSAFile` and resource records. `listResources()` inserts
normalized names and file pointers into the real VFS index; opening a resource
delegates to the original BSA reader's bounded file stream. The encoder pointer
is borrowed: its owner must outlive every registered archive.

`src/register_bsa.cpp` is only an existing-file/original-format input guard and
a call to `Manager::addArchive(std::make_unique<BsaArchive<BSAFile>>(...))`.
It does not implement a replacement archive, index, stream, encoder or logger.
The caller explicitly builds the index. Constructing the named template avoids
**calling** the inline multi-format `makeBsaArchive()` factory.

The same header still includes compressed-BSA and BA2 class declarations and
defines that unused factory. These are compile-time interface dependencies,
not a reason to select their `.cpp` implementations. No dead-strip flag or stub
is added to hide unresolved symbols. A genuine host executable link is the
required evidence that this narrow selection is sufficient on a compiler; that
link remains unexecuted locally. If the toolchain emits unwanted decoder
references, report that blocker rather than adding speculative substitutes.

[`manager.cpp`](../../components/vfs/manager.cpp) owns archives and builds its
index by calling each archive's `listResources()` in registration order. Later
assignments replace earlier file pointers, so the last registered archive wins.
`addArchive()` does not update the current index until `buildIndex()`.
`reset()` clears the index before destroying archives.

[`registerarchives.cpp`](../../components/vfs/registerarchives.cpp) uses the
broader factory, `Files::Collections`, directory archives and logging, then
builds the index. It is unnecessary for these two explicitly named Morrowind
archives and is not compiled here. No loose directories or later TES formats
are registered.

## Exact source/dependency inventory

| Library | Translation units compiled |
| --- | --- |
| Unchanged `openmw-ios-data-core` (A) | `components/files/conversion.cpp`, `openfile.cpp`, `constrainedfilestreambuf.cpp`; `components/platform/fileposix.cpp`; `components/vfs/manager.cpp` |
| Unchanged `openmw-ios-bsa-reader` (B) | `components/bsa/bsafile.cpp` |
| New `openmw-ios-bsa-vfs` | `src/register_bsa.cpp`; genuine `components/toutf8/toutf8.cpp` and `components/debug/debuglog.cpp` |
| Host executable | `tests/vfs_check.cpp`, linked with all three libraries |

There are **eight unchanged engine translation units**, one small registration
translation unit and the host fixture. The new static archive contains three
objects, separate from B's one and A's five; static libraries do not absorb their
link dependencies. CMake's public target links carry this dependency chain.
`components/files/openfile.cpp` is inherited to preserve A's tested target and
exact-five contract; it is not an additional direct requirement of this adapter.
The logical reader/manager/encoding/logging closure is the other seven engine
translation units, but this experiment deliberately reuses A rather than
splitting or modifying it.

The recursively inspected project-header closure comprises these 25 engine
headers plus `src/register_bsa.hpp`:

```text
components/bsa/ba2dx10file.hpp
components/bsa/ba2gnrlfile.hpp
components/bsa/bsafile.hpp
components/bsa/compressedbsafile.hpp
components/debug/debuglog.hpp
components/esm/fourcc.hpp
components/files/constrainedfilestream.hpp
components/files/constrainedfilestreambuf.hpp
components/files/conversion.hpp
components/files/istreamptr.hpp
components/files/openfile.hpp
components/files/streamwithbuffer.hpp
components/files/utils.hpp
components/misc/strings/conversion.hpp
components/misc/strings/lower.hpp
components/platform/file.hpp
components/toutf8/tablesgen.hpp
components/toutf8/toutf8.hpp
components/vfs/archive.hpp
components/vfs/bsaarchive.hpp
components/vfs/file.hpp
components/vfs/filemap.hpp
components/vfs/manager.hpp
components/vfs/pathutil.hpp
components/vfs/recursivedirectoryiterator.hpp
```

Including all translation units and local fixture/header files, the inspected
closure is 36 project files. Offline tests walk it and reject external includes
outside the explicitly listed standard-C++/POSIX headers.

Additional dependencies and exclusions:

* C++20 compiler/standard library: existing reader code uses `std::format` and
  `std::rotr`; encoding uses `std::span`. The POSIX backend uses ordinary file
  descriptors and bounded streams.
* `toutf8.cpp` uses checked-in `tablesgen.hpp`. No iconv/ICU runtime or table
  generation is needed. Its legacy-conversion implementation references `Log`
  even though that error branch is not intentionally executed by this fixture.
  A null encoder would not remove compiled references or test real encoding.
* `debuglog.cpp` is the real lightweight logger: standard I/O, file-path/string
  conversions and `std::mutex`. CMake's built-in `Threads::Threads` supplies any
  system threading link requirements. It downloads nothing. This does not pull
  in `components/debug/debugging.cpp` or its wider platform/debug facilities.
* No selected source/header requires Boost, Bullet, SDL, MyGUI, OSG, ANGLE,
  zlib, LZ4 or a separate serialization library. Later compressed BSA/BA2 source
  files would broaden this closure and are deliberately unselected.

## Synthetic fixture and actual intended checks

`tools/fixtures.py` independently encodes five deterministic original-format
archives, all at most 300 bytes. These contain only original text/binary data,
not a real mesh or texture. They include a Windows-1252 `Textures\Caf\xe9X.TXT`
name, duplicate normalized mesh keys across two archives, and base/overlay-only
resources. Hash table words are encoded, but the inspected original reader
does not validate or use them for lookup; this is not a hash-lookup test.

The C++ fixture has six subprocess cases:

1. Register base then overlay using real adapters, build/rebuild the VFS index,
   and verify exact binary payloads. Repeat with reversed archive order to
   verify last-added duplicate precedence. No resource pointers are retained
   beyond archive ownership.
2. Reject a missing archive before adapter construction; the path must remain
   nonexistent.
3. Reject a directory used as an archive path.
4. Reject an existing unsupported-format file before adapter construction.
5. Register a valid BSA with an unexpected resource, then require the fixture's
   expected index manifest to reject it.
6. Register a valid BSA missing an expected resource, then require that manifest
   comparison to reject it.

Manifest checks are fixture assertions, **not** a new restriction on OpenMW's
archive format. Positive traversal also checks:

* `exists`, `find`, `get`, index enumeration, original-case UTF-8 `getStem`,
  backing-archive timestamp and selected archive description.
* ASCII case normalization, backslash/slash conversion, repeated-separator
  collapse and removal of the leading separator, using `Path::Normalized`.
  `NormalizedView` requires already normalized input and rejects an invalid
  literal. Queries do not pass raw unnormalized strings into internal APIs.
* Windows-1252 to UTF-8 conversion using a **real**, nonnull
  `StatelessUtf8Encoder(WINDOWS_1252)`, kept alive until all managers disappear.
  Uppercase ASCII is folded, but non-ASCII UTF-8 bytes are not case-folded.
* Dot components are **not** resolved by VFS normalization. A `meshes/../...`
  name stays that way and misses this index. This API is not filesystem
  canonicalization or a security boundary.
* Missing resource `exists`/`find` return false/null, and `get` throws.
* Oversized reads stop at an entry's byte length without leaking adjacent
  payloads; out-of-range seeks fail; a valid seek from entry end still works.
* Open streams retain their bounded file handles across index rebuild,
  `Manager::reset()` and manager destruction. This does not permit an archived
  `VFS::File*` or borrowed encoder to dangle.

The Python driver generates inputs only in an explicitly owned build/test
directory. For each C++ invocation it checks successful exit, a mode-specific
completion marker, and the entire input tree's filenames and SHA-256 values.
It checks that no missing archive was created, then prints final input hashes.
Reader operations themselves are read-only; setup deliberately writes the
original synthetic inputs. No fixture data is committed as a binary asset.

## Existing read-only/security limits remain

`BSAFile::open()` can create missing archives. The small registration helper
checks an existing regular file and original magic **before** invoking it. This
is sufficient for the fixture's stable, owned inputs, not atomic protection
against a concurrently replaced/deleted path; the original API reopens by path.
Symlinks/permissions, sandbox imports and hostile-file races need separately
reviewed production policies.

The upstream reader's malformed-BSA allocation issue remains unchanged:
`readHeader()` does not first require `dirsize >= 12 * filenum` before
`mStringBuf.resize(dirsize - 12 * filenum)`. A negative size can become an
enormous allocation request and lead to exceptions/resource exhaustion. Magic
detection does not fix it. This fixture does not generate undersized directories
or deliberately exercise dangerous allocations. It is not a parser hardening
or security test. See the [Milestone B limitation](../ios-openmw-bsa/README.md).

## Offline local validation

From the repository root using an existing Python interpreter:

```powershell
python -B -m unittest discover -s experiments/ios-openmw-bsa-vfs/tools -v
python -B -m unittest discover -s experiments/ios-openmw-bsa/tools -v
python -B -m unittest discover -s experiments/ios-openmw-core/tools -v
git diff --check
```

Run each suite as a separate Python invocation. Python contracts check target
composition, the full include closure, fixture layouts/hashes, intended API
coverage and the driver rejecting process failures, missing evidence, mutated
inputs and newly created files. Mocked subprocess tests validate the **driver**,
not OpenMW execution. On Windows the C++ test explicitly skips. On a native
POSIX host with existing CMake/CTest/C++20 tools, the optional test compiles and
links the real sources and executes CTest; build failures do not skip or cause
a stub fallback.

This milestone's C++ compile/link/runtime remains unexecuted locally. A dedicated
manual workflow is prepared below; it has not been triggered. There is no native
compilation or iPhone runtime claim from this offline work.

## Dedicated manual native validation workflow

[`.github/workflows/ios-openmw-bsa-vfs.yml`](../../.github/workflows/ios-openmw-bsa-vfs.yml)
has the exact name **iOS OpenMW BSA-to-VFS native validation**. It accepts only
`workflow_dispatch`, with no push, pull-request, schedule or commit-message
trigger. Its two independent jobs are `host-validation` and
`iphoneos-compilation`, each using `macos-26` with a 20-minute timeout. The
runner's selected Xcode is used and recorded, following the proven A/B setup;
the image and SDK versions are not assumed constant.

After manual review/commit/upload, GitHub generally needs the workflow on the
default branch before offering dispatch. Once registered, select **Actions →
iOS OpenMW BSA-to-VFS native validation → Run workflow → ios-port**. Merely
adding it on a non-default branch may not expose that control. Both jobs require
`refs/heads/ios-port` and verify the checked-out revision against `GITHUB_SHA`.

Host acceptance:

* The focused Python suite must succeed. Its optional POSIX CMake test actually
  compiles/links/runs the real fixture when the existing tools are available;
  format, workflow and mocked tool tests alone do not prove native success.
* Xcode separately configures this project with
  `OPENMW_IOS_BSA_VFS_HOST_TESTS=ON` and compiles/links
  `openmw-bsa-vfs-check`, with verbose compiler/linker output captured.
* Verbose CTest must pass with the exact selector
  `^openmw-bsa-vfs-runtime$`, excluding the inherited A/B fixture definitions.
  The completion marker for **six** successful subprocess cases with unchanged
  input tree is mandatory. The existing driver verifies tree entries, file
  SHA-256 values, missing-file noncreation, process exit codes and result markers.
* Any regression, configure, compilation, linking, runtime or integrity failure
  fails the job. No failure-tolerant compilation or substitute OpenMW classes
  are introduced.

Device acceptance:

* Configure the actual iPhoneOS SDK, ordinary ARM64 and exactly minimum iOS 18.0.
  Compile `openmw-ios-bsa-vfs` and its unchanged B/A dependencies, with signing
  disabled during compilation. No graphics dependencies or packages are fetched.
* Locate exactly one nonempty archive for each of
  `libopenmw-ios-bsa-vfs.a`, `libopenmw-ios-bsa-reader.a` and
  `libopenmw-ios-data-core.a` within the isolated build tree. Missing, empty or
  multiple matches fail after a successful compile. Record actual build paths
  rather than guessing nested Xcode product directories.
* `tools/validate_vfs_archive.py` independently requires exactly
  `register_bsa.cpp`, `toutf8.cpp` and `debuglog.cpp` objects (accepting Xcode
  `.o` and CMake `.cpp.o` spellings). Duplicate aliases for a source, missing,
  unexpected, empty or additional objects are rejected.
* Reuse A's **unchanged** ar/Mach-O inspection: every object must be little-endian
  64-bit Mach-O `MH_OBJECT`, ordinary ARM64, iOS device platform and exactly
  minimum 18.0. Reject macOS, simulator, Catalyst, ARM64e, wrong architecture,
  bitcode and missing/malformed/ambiguous platform metadata. Native `lipo`,
  `ar` and `otool` results are required too; missing/failing tools fail closed.
* Invoke B's unchanged exact-one validator and A's unchanged exact-five
  validator separately, yielding **3 + 1 + 5**. After successful compilation,
  all three validation steps are attempted even if archive location or another
  validation fails; missing copied inputs get explicit failure reports. The job
  cannot pass if any collection or inspection failed.

Evidence artifacts upload with `always()` on success or failure; missing evidence
is an error. Names include the run ID and attempt, with 14-day retention:

| Artifact | Runner evidence directory |
| --- | --- |
| `ios-openmw-bsa-vfs-host-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-bsa-vfs-host-evidence/` |
| `ios-openmw-bsa-vfs-device-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-bsa-vfs-device-evidence/` |

Both contain available `run.txt`, `toolchain.log`, `source-sha256.txt`,
`OpenMW-LICENSE.txt`, configure/build logs, nested `cmake-diagnostics/`,
`job-status.txt` (status before upload), and an overall `SHA256SUMS` manifest.
Commands are captured with shell tracing and failed piped commands retain their
failure status. Source manifests include this experiment, A/B and the audited
BSA/VFS/file/encoding/logging sources and headers, including checked-in tables.

The host package additionally preserves `python-tests.log`, verbose `ctest.log`,
CTest failure logs, the generated `synthetic-bsa-vfs/` inputs, their hashes in
test output and `SHA256SUMS`, `host-archive-paths.json` and any uniquely located
`host-lib*.a` archives. Its successful marker proves the input hashes/tree
matched before/after every subprocess; copying inputs alone would not prove it.

The device package preserves the three available static archives,
`device-archive-paths.json`, `archive-location.log`, and separate
`vfs-inspection/`, `bsa-inspection/` and `core-inspection/` directories. Each
inspection contains `archive-validation.json` (result, archive/object hashes and
platform metadata, or a failure reason), `archive-tools.log` with member
inventory, and safe extracted `objects/` with per-object `otool` metadata.
Available partial outputs and raw platform evidence survive validation failures.

Offline regression tests cover exact source counts, every member's platform,
invalid/duplicate/empty objects, missing tools, failed inspections, producer/
consumer paths, nested outputs, failure collectors, checksums, manual-only
triggers, inline Python and available Bash syntax. Synthetic Mach-O fixtures
test the validators, not OpenMW execution. Hosted toolchain behavior, GitHub
registration/schema acceptance, native linking (including the narrow adapter
and system Threads dependency) and iPhoneOS compilation remain unverified until
the jobs actually run. No engine files, earlier validators or source overlays
are modified, and the malformed-BSA limitation above remains unchanged.

## Native validation requirements after manual review

Use an existing macOS/Xcode toolchain, CMake 3.24+ and Python 3.10+. No package
download is required. On a future macOS host, the explicit fixture commands are:

```sh
cmake -S experiments/ios-openmw-bsa-vfs -B experiments/ios-openmw-bsa-vfs/build-host \
  -DOPENMW_IOS_BSA_VFS_HOST_TESTS=ON
cmake --build experiments/ios-openmw-bsa-vfs/build-host \
  --target openmw-bsa-vfs-check --parallel 3
ctest --test-dir experiments/ios-openmw-bsa-vfs/build-host \
  --verbose --output-on-failure --no-tests=error -R '^openmw-bsa-vfs-runtime$'
```

The explicit CTest selector excludes A/B fixture definitions inherited from
their subprojects; validate A/B independently with their unchanged workflows.
The host executable must really link and all six cases must complete with the
unchanged-input-tree marker. This proves more than creating a static library
containing potentially unresolved references.

For a later iPhoneOS compilation (instructions only; not run now):

```sh
cmake -S experiments/ios-openmw-bsa-vfs -B experiments/ios-openmw-bsa-vfs/build-ios -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0
cmake --build experiments/ios-openmw-bsa-vfs/build-ios --config Release \
  --target openmw-ios-bsa-vfs -- -jobs 3 CODE_SIGNING_ALLOWED=NO
```

The unchanged A platform guard rejects macOS/simulator/device misselection when
host tests are off. The dedicated workflow records toolchain,
source provenance, build commands, archive members and hashes, and inspects all
**3 + 1 + 5** objects for ARM64, Mach-O **iOS device** and exactly minimum 18.0.
It keeps A's exact-five and B's exact-one validators unchanged. The new
three-object validator supplies C's separate acceptance contract.
An iOS static compile would still not prove device linking or execution.

## Remaining steps toward Morrowind content

1. Compile/link/run this genuine adapter on macOS, then compile for iPhoneOS;
   resolve only evidenced failures. A later device fixture must test sandboxed
   files and lifetimes in an actual app. No such execution has occurred here.
2. For low-level TES3 ESM/ESP parsing, supply real pinned OSG math headers
   (`osg/Vec3f` is reached through position/cell declarations) and validate the
   larger reader/record-ID/cache/writer/encoding closure described in the
   [content audit](../../docs/ios-port/content-loading-audit.md). This milestone
   supplies real encoding/logging prerequisites but does not compile that reader.
3. Review parser hardening and user-owned sandboxed game-data import. Do not
   distribute game files or treat path normalization as access control.
4. Actual asset decoding requires `Nif::Reader` and OpenMW resource/NifOsg/image
   systems; returning synthetic `.BIN` bytes is not mesh/image loading. Their
   dependencies and GLES shaders must be audited separately before connecting
   them to the preserved UIKit/ANGLE/OSG graphics foundation.
5. World/store resolution and full engine startup remain later milestones, with
   broader settings, input, audio, physics, GUI and lifecycle requirements.

All engine licensing remains applicable; see the repository's existing
[`LICENSE`](../../LICENSE). This experiment adds no proprietary content or new
third-party dependency pin.
