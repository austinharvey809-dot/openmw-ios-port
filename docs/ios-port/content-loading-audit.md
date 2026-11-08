# Milestone B: offline content-reader audit

## Status and boundaries

Audit baseline: branch `ios-port`, commit
`ffdbc05a81dcfc0483797b38b38d8e4dea7ef13a`. The user reports successful Milestone
A macOS host execution and iPhoneOS ARM64/iOS 18.0 compilation with object-level
platform checks. This session inspected those sources and build definitions
offline; it did not rerun GitHub Actions or a native compiler.

The nine unfinished Build #15 mipmap-observer files remain separate. This
milestone preserves their contents, the working graphics applications, engine
sources, dependency pins, source overlays and the Milestone A target/workflow.
No new workflow, application, renderer integration or `Engine::go()` is added.

The implemented next target is
[`experiments/ios-openmw-bsa`](../../experiments/ios-openmw-bsa/README.md): compile
the genuine original-format BSA reader, then enumerate and read independently
encoded synthetic payloads on a host. Its C++ compilation and runtime remain
unverified until an actual suitable compiler runs. Source/include inspection,
Python encoding checks and mocked harness tests are weaker evidence.

## Candidate 1: original Morrowind BSA

Selected implementation:
[`components/bsa/bsafile.cpp`](../../components/bsa/bsafile.cpp) and
[`bsafile.hpp`](../../components/bsa/bsafile.hpp). `BSAFile::readHeader()` reads the
original `0x100` format: a 12-byte header, size/relative-offset records, name
offsets and NUL-terminated names, an eight-byte-per-entry hash table, then
uncompressed payloads. It checks directory bounds, payload ranges and name
offsets/termination and sorts the resulting entries by payload offset. It reads
the stored hashes but does not validate them or use them for lookup.

`BSAFile::getFile()` calls `Files::openConstrainedFileStream()` for an entry's
absolute offset/length. It returns a file-backed bounded stream, not a decoded
mesh or image. Archive payloads can be read without any graphics context.

The complete project-file include closure rooted at `bsafile.cpp` is:

```text
components/bsa/bsafile.cpp
components/bsa/bsafile.hpp
components/esm/fourcc.hpp
components/files/constrainedfilestream.hpp
components/files/constrainedfilestreambuf.hpp
components/files/conversion.hpp
components/files/istreamptr.hpp
components/files/streamwithbuffer.hpp
components/files/utils.hpp
components/platform/file.hpp
```

The new library adds only `bsafile.cpp`; the unchanged Milestone A library
supplies its existing five sources:

```text
components/files/conversion.cpp
components/files/openfile.cpp
components/files/constrainedfilestreambuf.cpp
components/platform/fileposix.cpp
components/vfs/manager.cpp
```

`openfile.cpp` and `manager.cpp` are retained through reuse of that tested target,
not new direct BSA-reader requirements. The file backend is POSIX; the full
selected six-source/header closure has only standard C++ and POSIX includes.
There is no Boost, Bullet, SDL, MyGUI, OSG, compression or external serialization
dependency. `std::format` and `std::rotr` in the additional BSA source require
actual C++20 compiler/standard-library support, beyond merely selecting C++20.
The offline tests rewalk this include closure to catch new external headers.

Filesystem/API qualifications:

* The source reads integer fields in native byte order. Apple ARM64 is little
  endian; the host fixture asserts the same instead of introducing a byteswap
  patch. This is not a claim of big-endian portability.
* `BSAFile::open()` creates an archive if the path does not exist. The same
  translation unit contains writer APIs; `close()` writes when changed. The new
  fixture requires an existing regular input, invokes no writer, and verifies
  input hashes after each process. A future production import boundary must
  handle missing paths explicitly.
* Path access uses `std::filesystem`, `std::ifstream` and independent constrained
  file streams. It requires a readable ordinary file. It does not grant access
  outside an iOS sandbox, perform security-scoped URL handling, or import files.
* These small malformed-input tests are not a security assessment of the
  reader. Real archive sizes, large offset limits, encodings, permission errors
  and hostile-file robustness still need separate validation.

This is the best next target: one additional genuine engine translation unit,
no new third-party packages, a meaningful asset-byte read, and a host link test
that will expose unresolved symbols instead of relying on a static archive's
ability to hold unlinked objects.

## Candidate 2: generic BSA/VFS registration

[`components/vfs/bsaarchive.hpp`](../../components/vfs/bsaarchive.hpp) provides
`BsaArchive<T>`/`BsaArchiveFile<T>`. They retain the parsed archive, expose entry
streams through `VFS::File`, normalize names and optionally convert their
encoding with `ToUTF8::StatelessUtf8Encoder`. The encoder pointer being null at
runtime does not prove that compiled encoder references can be omitted at link
time.

Its inline `makeBsaArchive()` factory switches among original BSA, compressed
BSA, BA2 GNRL and BA2 DX10. The same header includes all those implementations'
interfaces. Using that generic factory is a broader dependency choice than
calling `BSAFile` directly; do not rely on dead stripping to make it narrow.

| Source/path | Additional scope and dependencies |
| --- | --- |
| `components/bsa/compressedbsafile.cpp` | Later TES BSA formats; zlib and `lz4frame.h`/LZ4. Not required for original Morrowind BSA. |
| `components/bsa/ba2file.cpp`, `ba2gnrlfile.cpp`, `ba2dx10file.cpp` | Shared BA2 implementation and later formats; the GNRL/DX10 implementations use zlib. DX10 also constructs texture data headers. |
| `components/toutf8/toutf8.cpp` | Encoding conversion with checked-in `tablesgen.hpp`, plus lightweight logging. No observed ICU/iconv runtime requirement in this source. |
| `components/debug/debuglog.cpp` | Standard-library logging and file-path conversion. Distinct from broader `debugging.cpp`, whose platform/debug facilities bring other dependencies. |
| `components/vfs/registerarchives.cpp` | Generic archive factory, loose filesystem archives, `Files::Collections`, encoding and logging. Adds archives/directories then builds the VFS index. |
| `components/vfs/filesystemarchive.cpp`, `components/files/collections.cpp`, `components/files/multidircollection.cpp` | Loose-file directory traversal/collections for the wider registration path; not selected for this standalone BSA read. |

`components/vfs/manager.cpp` is already in Milestone A, but that fixture's
in-memory archive is not proof of genuine BSA integration. A useful subsequent
step is link-testing `BsaArchive<BSAFile>` and the real encoder/logging closure,
before adding the generic multi-format factory. No new adapter or stub is
introduced in the current milestone.

## Candidate 3: TES3 ESM/ESP record reader

[`components/esm3/esmreader.cpp`](../../components/esm3/esmreader.cpp) and
[`esmreader.hpp`](../../components/esm3/esmreader.hpp) implement real TES3 record
and subrecord traversal. `open()` expects a TES3 header and loads `ESM::Header`;
`openRaw()` accepts a path-backed stream, and a stream-based opening interface
also exists. This is more meaningful than merely detecting the four-byte magic
with `components/esm/format.cpp`, but its source closure is larger than BSA's.

Source inspection identified the following **candidate link closure**, not a
compiler-verified minimal list:

```text
components/esm3/esmreader.cpp
components/esm3/readerscache.cpp
components/esm3/loadtes3.cpp
components/esm3/esmwriter.cpp
components/esm3/cellid.cpp
components/esm/refid.cpp
components/esm/stringrefid.cpp
components/esm/formid.cpp
components/esm/generatedrefid.cpp
components/esm/indexrefid.cpp
components/esm/esm3exteriorcellrefid.cpp
components/toutf8/toutf8.cpp
components/debug/debuglog.cpp
components/files/conversion.cpp
components/files/openfile.cpp
```

Why the additional sources matter:

* `ESMReader` uses `ReadersCache`, TES3 header load/reset, `CellId` loading and
  `RefId` conversion/string handling. The cache implementation also calls back
  into the reader.
* `loadtes3.cpp` and `cellid.cpp` implement save methods alongside load methods,
  referencing `ESMWriter`; omitting writer definitions on the assumption that a
  read-only fixture will dead-strip them is not a verified link strategy.
* `RefId` dispatch covers string, form, generated, indexed and exterior-cell
  forms; their definitions are split across the listed sources.
* Encoding calls remain compiled even when an optional encoder is null.
  `toutf8.cpp` uses existing generated encoding tables; no new table generator,
  ICU download or external serialization package is inherently required here.

The recursively inspected candidate includes 53 project files (15 translation
units plus these 38 headers):

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

The external header obstacle in this inspected closure is **`osg/Vec3f`**, from
`components/esm/position.hpp`, reached through cell-related declarations. This
is an OSG math/header dependency, not proof that this parser requires a live GL
context or the full renderer. A complete matching pinned OSG include/config
tree is not available for a local compile here; fabricating a `Vec3f` stand-in
would be inappropriate. The existing OSG dependency pipeline could provide
headers in a later reviewed native build without changing pins.

No Boost, Bullet, SDL, MyGUI, zlib or LZ4 includes were found in this inspected
generic-reader closure. This does not extend to every record loader or the
whole ESM store. `loadcell.hpp` is reached, but merely including it does not
establish a need to compile `loadcell.cpp`; actual cell/reference loading adds
those implementations and must be audited separately. The 15-source list must
still be linked on a real compiler to establish sufficiency.

TES3 parsing handles records/subrecords and scalar/ID serialization through
`esm/decompose.hpp`, `serializerefid.hpp`, format-version helpers and normal
streams. It does not automatically load a world, resolve all records or decode
archive asset bytes. ESM content files and BSAs serve different roles.

## From content bytes to an OpenMW scene

The verified integration path in current sources is:

1. `apps/openmw/mwworld/esmloader.cpp` determines the content format, sets up
   readers/encoding and parent-file indices, and passes records to `ESMStore`.
   World/cell/reference loading needs more than the low-level reader.
2. `VFS::registerArchives()` registers archives and loose directories and builds
   the manager index, including override precedence. `VFS::Manager::get()`
   returns file streams by normalized resource name.
3. `components/resource/niffilemanager.cpp` parses a genuine NIF using
   `Nif::Reader` and `mVFS->get(name)`.
4. `components/resource/scenemanager.cpp` calls `NifOsg::Loader::load()` with the
   NIF, image manager and material manager; it caches templates and creates
   instances. The image manager uses OSG decoding facilities for image assets.
5. OpenMW world/rendering systems select and place those assets from records.
   The proven UIKit/ANGLE/OSG cube is a graphics foundation, not evidence that
   these engine paths execute or that OpenMW's desktop shaders work in GLES3.

Next steps, in order:

1. Review this isolated target. Later run a macOS host compile/link/runtime test
   and iPhoneOS ARM64/iOS 18.0 archive build with object-platform inspection.
   No workflow is added or triggered now.
2. Add a reviewed read-only BSA/VFS fixture with genuine archive registration
   and encoding, still synthetic. Validate lifetime and normalized lookup.
3. Compile/link a low-level TES3 reader fixture with an original synthetic TES3
   header and minimal records, supplying real pinned OSG math headers. Verify
   malformed records, encoding and dependencies before real-data imports.
4. Design sandboxed user import/storage of legally owned content. Never commit
   or redistribute game assets. Validate actual Morrowind archive/record reads
   on an iPhone separately; no such run has occurred in this milestone.
5. Audit/compile NIF parsing and NifOsg/resource/image loading, then render one
   user-supplied asset through real OpenMW resource systems on the existing
   externally owned EGL context. This requires its own shader/GLES audit.
6. Only then grow toward world/store/engine integration, handling settings,
   filesystem, controller/input, SDL context seams, audio, GUI, physics and
   lifecycle one subsystem at a time. These wider engine dependencies have not
   been eliminated by the small readers' dependency inventories.

## Validation and remaining uncertainty

The new Python suite checks the selected source/target contract and complete
include closure, deterministic original archive layout and hash, bounded
malformed cases, and fixture exit-status/input-integrity handling. Its optional
POSIX test compiles the real sources and runs all eight cases when a suitable
compiler exists. A skipped C++ test is explicitly not reader-runtime evidence.

Future native CI must preserve source provenance and inspect the new BSA
archive's one Mach-O object separately from Milestone A's five-object archive.
Require ARM64 **and** iOS-device platform/minimum 18.0 metadata, commands,
toolchain versions and SHA-256 checksums. Do not weaken Milestone A's exact-five
validator to accept a different library. A macOS runtime pass cannot establish
iPhone execution, nor can archive compilation prove successful linking into an
application. There is no app bundle, signing change or IPA in this milestone.
