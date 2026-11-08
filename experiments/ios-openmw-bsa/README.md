# Milestone B: original Morrowind BSA reader

This isolated target compiles the repository's unchanged
`components/bsa/bsafile.cpp`, linked to the five real-source translation units
from [Milestone A](../ios-openmw-core/README.md). It exercises OpenMW's original
uncompressed Morrowind BSA reader using original synthetic bytes. It does not
load an ESM, NIF, world, renderer, or game asset, and provides no iOS application
or IPA.

Milestone A was validated on macOS and iPhoneOS ARM64 at commit
`ffdbc05a81dcfc0483797b38b38d8e4dea7ef13a`. Those results do **not** validate this
additional source file. The BSA target and C++ runtime fixture have not yet been
compiled locally or natively; Windows-side Python checks validate their source
contracts and fixture encoding only. The optional C++ test explicitly skips on
Windows rather than substituting an implementation.

See the [content-loading audit](../../docs/ios-port/content-loading-audit.md) for
the BSA/ESM dependency comparison and follow-on integration boundaries.

## Scope and dependencies

* CMake 3.24+, a native POSIX C++20 compiler and standard library, and Python
  3.10+ for host fixtures. The unchanged reader uses `std::format` and
  `std::rotr`; actual toolchain/library support must be compiled, not assumed.
* Device builds require macOS/Xcode, an iPhoneOS SDK and ARM64, minimum iOS 18.0.
  The child Milestone A project enforces the platform selection. Simulator or
  macOS ARM64 output is not device evidence.
* No dependency fetching, Boost, Bullet, SDL, MyGUI, OSG, ANGLE, zlib, LZ4 or
  external encoding library is needed by this selected source closure.
* This is the `0x100` uncompressed reader. Generic VFS BSA registration and
  newer compressed BSA/BA2 formats are deliberately outside this target.
  VFS filename normalization is checked, but no real archive is registered
  with `VFS::Manager` in this fixture.

`openmw-ios-bsa-reader` contains the one new object. Its public link dependency
is the separate `openmw-ios-data-core` static library. A static library does not
absorb its dependency's objects. Consumers must link both; CMake's target
interface supplies that relationship.

## Original synthetic data

`tools/fixtures.py` writes a 140-byte archive with two original ASCII filenames
and binary/text payloads. It independently encodes the little-endian header,
directory, name table, name hashes and payload offsets. The on-disk directory
order differs from the payload order. The genuine reader must enumerate and
sort entries, normalize paths, return exact bounded payloads, support seeks and
retain a payload stream after the directory closes.

Seven additional small malformed/unsupported inputs exercise rejection: short
header, wrong magic, newer-format magic, oversized directory, payload outside
the archive, invalid name offset and missing name terminator. These are bounded
regression cases, not a security audit or fuzzing of hostile archives.

Known upstream malformed-input limitation: `BSAFile::readHeader()` checks upper
directory/file bounds but does not first require `dirsize >= 12 * filenum`.
Its subsequent `mStringBuf.resize(dirsize - 12 * filenum)` can convert a negative
size into an enormous allocation request for an undersized directory. Depending
on the input and standard library this may produce `length_error`, `bad_alloc`
or resource exhaustion. The existing oversized-directory test does not cover
this separate issue. Do not treat the reader as hardened for untrusted uploads;
this task documents the issue without changing the upstream source or executing
a potentially excessive allocation test. A separately reviewed bounds correction
is needed before making that stronger safety claim.

Important existing API behavior: `BSAFile::open()` creates a new archive when
the path is missing, and its translation unit also implements archive writing.
The fixture requires existing regular files, invokes no writer API, and checks
each input SHA-256 before/after the reader process. Production import code will
need an explicit existing-file policy too. No sources are changed to enforce it
here. The inspected reader uses native integer reads; the fixture requires a
little-endian host, matching the intended Apple ARM64 targets.

## Offline checks on Windows

With an already available Python interpreter, from the repository root:

```powershell
python -B -m unittest discover -s experiments/ios-openmw-bsa/tools -v
python -B -m unittest discover -s experiments/ios-openmw-core/tools -v
git diff --check
```

Do not install a compiler or dependencies just to remove the explicit runtime
skip. On a native POSIX host with `clang++` or `g++` already on PATH, the Python
suite additionally compiles the actual six OpenMW sources plus the fixture and
runs all eight archive cases. A compiler or standard-library error fails that
test; there is no fallback reader or `std::format` shim.

## Future macOS host validation

These commands are instructions for manual review, not claims of execution:

```sh
cmake -S experiments/ios-openmw-bsa -B experiments/ios-openmw-bsa/build-host \
  -DOPENMW_IOS_BSA_HOST_TESTS=ON
cmake --build experiments/ios-openmw-bsa/build-host --target openmw-bsa-check --parallel 3
ctest --test-dir experiments/ios-openmw-bsa/build-host \
  --output-on-failure --no-tests=error -R '^openmw-bsa-runtime$'
```

The explicit test expression selects this experiment's runtime fixture. The
Milestone A subdirectory also defines its own fixture, excluded from the default
build here; continue validating it independently with its existing workflow.

Acceptance requires real C++ compilation/linking and eight successful reader
cases with unchanged input hashes. Python mock/harness tests alone cannot meet
this requirement.

## Manually dispatched native validation workflow

[`.github/workflows/ios-openmw-bsa.yml`](../../.github/workflows/ios-openmw-bsa.yml)
uses **only `workflow_dispatch`**, with two independent `macos-26` jobs and
20-minute timeouts. There are no push, pull-request, commit-message or scheduled
triggers. It uses the runner's selected Xcode, as the successful Milestone A
workflow does, and records its actual version and SDK rather than assuming the
host image never changes. No graphics dependencies are fetched or built.

After manual commit/upload, GitHub normally needs this workflow on the
repository's default branch before exposing manual dispatch. Once registered,
choose **Actions → iOS OpenMW BSA reader native validation → Run workflow →
ios-port**. If it is not registered, publishing it solely on `ios-port` does not
guarantee that the dispatch control will appear. Both jobs explicitly reject a
different branch and verify the checked-out commit equals `GITHUB_SHA`.

* **Host validation:** runs the focused Python regressions, configures this
  project with `OPENMW_IOS_BSA_HOST_TESTS=ON`, and compiles/links
  `openmw-bsa-check` using Xcode/C++20. Verbose CTest selects only
  `openmw-bsa-runtime`. Acceptance requires its successful exit and the explicit
  completion marker for all eight cases with unchanged input bytes. The
  existing fixture hashes each archive before/after reading and checks every
  subprocess exit/result; the final evidence also includes the synthetic inputs
  and their checksums. The optional POSIX Python runtime test additionally
  compiles genuine sources directly when its existing compiler is available.
* **Device compilation:** configures the same target for the actual iPhoneOS SDK,
  ARM64, exactly iOS 18.0 minimum, with signing disabled during compilation.
  The `openmw-ios-bsa-reader` dependency builds the unchanged data-core library.
  Both archives are located by exact filename within the isolated build tree;
  missing, empty or duplicate matches fail after a successful compile. Their
  actual build paths are recorded, avoiding an assumption about the child
  project's Xcode output directory.
* **Independent inspections:** `tools/validate_bsa_archive.py` accepts exactly
  one `bsafile.o`/`bsafile.cpp.o` object and reuses Milestone A's unchanged ar and
  Mach-O parsing. The existing Milestone A CLI independently requires its exact
  five original objects. Both reject macOS, simulator, Catalyst, non-ARM64,
  ARM64e, wrong deployment metadata, bitcode and unexpected archive members.
  Each inspection runs even if the other inspection fails, provided compilation
  and archive collection succeeded. No source list or validator is patched.

Artifacts are uploaded with `always()` and missing evidence is an error:

| Artifact name | Runner evidence directory | Contents when available |
| --- | --- | --- |
| `ios-openmw-bsa-host-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-bsa-host-evidence/` | Toolchain/source provenance, Python/configure/build/verbose CTest logs, CMake/CTest failure diagnostics, synthetic archives, host archives and `host-archive-paths.json`. |
| `ios-openmw-bsa-device-<run_id>-<run_attempt>` | `$RUNNER_TEMP/openmw-bsa-device-evidence/` | Both static archives, `device-archive-paths.json`, compilation/toolchain logs, and separate `bsa-inspection/` and `core-inspection/` reports, extracted objects and `lipo`/`ar`/`otool` evidence. |

Both contain `run.txt`, `source-sha256.txt`, the OpenMW license, job status and
`SHA256SUMS` of all available evidence files. Each inspection's
`archive-validation.json` records archive/object hashes and platform metadata,
or its failure reason. Partial outputs survive failures; missing compilation
outputs cannot be reported as passing. No IPA or iPhone runtime claim is made.

Offline contract tests exercise triggers, commands, artifact handoffs, ambiguous
or missing archive rejection, strict synthetic Mach-O validation, failure
evidence, inline Python and available Bash syntax. They cannot validate GitHub
workflow registration, the hosted image or native compilation. This workflow has
not been run during its offline preparation.

## Future iPhoneOS compilation

For an equivalent manual device compilation after review, use the established
Milestone A runner/Xcode configuration:

```sh
cmake -S experiments/ios-openmw-bsa -B experiments/ios-openmw-bsa/build-ios -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO
cmake --build experiments/ios-openmw-bsa/build-ios --config Release \
  --target openmw-ios-bsa-reader --parallel 3
```

Device acceptance must inspect the resulting BSA archive's **one** object and
Milestone A archive's **five** objects separately: ARM64, Mach-O **iOS device**
platform and minimum deployment 18.0, with source commit, commands, SDK/Xcode
versions, archive members and checksums recorded. Retain Milestone A's exact-five
validator unchanged; do not feed it a different archive or weaken its count.
The workflow records actual output locations before copying to stable artifact
paths. ARM64 architecture alone is insufficient.

No macOS host success would prove iPhoneOS compilation. Neither static archive
would prove iPhone execution or successful loading of real Morrowind assets.
Those require subsequent signed-device fixtures and user-supplied, legally
owned game data in the iOS sandbox. Existing graphics experiments and all pins
remain separate and unchanged.
