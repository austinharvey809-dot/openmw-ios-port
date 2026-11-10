# Milestone E: genuine STAT-to-BSA/VFS resource lookup

This isolated target connects OpenMW's **actual high-level `ESM::Static::load`** to its original-format BSA reader and `VFS::Manager`. It retrieves exact original synthetic bytes. These bytes are **not a NIF model**; there is no geometry parsing, rendering, cell loading or engine startup.

Milestones A–D have native verification according to the supplied project evidence (D run `42556348837`). Milestone E has additionally passed independent Linux GCC 14.2 compile/link/runtime review: all 21 units, two separate archives, all sixteen cases and unchanged inputs, without OSG rendering libraries. That is user-supplied Linux evidence, not an Apple build repeated here. The dedicated native workflow below is prepared but has not been dispatched; macOS execution, iPhoneOS compilation and combined iPhoneOS linking/runtime remain unverified.

## Source closure and link ownership

The complete, per-file SHA-256 inventory is [data/source-audit.json](data/source-audit.json). All 79 project files are checked in full after CRLF-to-LF normalization: 20 genuine engine translation units, 57 engine headers, and C's existing registration helper `.cpp`/`.hpp`. The baseline OpenMW commit is `c5722246874b5bae9f01eebca4a57fd7021f31a0`. This records provenance rather than requiring all future experiment commits to have that HEAD.

The unchanged [Milestone D target](../ios-openmw-esm/CMakeLists.txt) builds and owns these fifteen units:

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

The new `openmw-ios-esm-vfs` static target owns exactly six additional units:

| Source | Purpose |
| --- | --- |
| `components/esm3/loadstat.cpp` | Genuine `Static::load`, NAME/MODL/DELE handling; save/blank methods remain original |
| `components/bsa/bsafile.cpp` | Original uncompressed Morrowind BSA directory and entry reader |
| `components/files/constrainedfilestreambuf.cpp` | Entry-bounded streams |
| `components/platform/fileposix.cpp` | Real read-only POSIX file handles |
| `components/vfs/manager.cpp` | Real archive index, precedence and resource lookup |
| `experiments/ios-openmw-bsa-vfs/src/register_bsa.cpp` | Unchanged C helper: require existing regular original-format archive before real adapter construction |

Link graph: `openmw-esm-vfs-check` → `openmw-ios-esm-vfs` → `openmw-ios-esm-reader` → `Threads::Threads` and the system C++ runtime. CMake propagates D's genuine OSG math include/config directories. There are no additional compile definitions or compatibility patches. C++20 is required, including the existing BSA source's `std::format` and `std::rotr` requirements.

**A/B/C libraries are deliberately not added or linked.** A overlaps D in `conversion.cpp`/`openfile.cpp`; C overlaps D in `toutf8.cpp`/`debuglog.cpp`. This selection compiles each of the 21 total units exactly once instead of relying on a static linker's incidental lazy extraction to conceal duplicate definitions. Existing implementations and validation contracts are untouched. In a future native validation, inspect E's six-object and D's fifteen-object archives separately; this is not A/B/C's archive acceptance contract.

`loadstat.hpp` adds `esm/path.hpp` → `vfs/pathutil.hpp`, alongside existing `RefId`/defs. `loadstat.cpp` also contains `Static::save`; its real writer dependencies are already provided by D. The complete 58-header list, all standard/POSIX includes and full hashes are in the manifest. `BsaArchive<BSAFile>` includes BA2/compressed class declarations, but the broader `makeBsaArchive` factory and their implementation files are not used; this follows C's already verified selection. No compression library is selected. The new combined link still needs native confirmation.

The external math dependency remains the genuine separate `OpenMW/osg` checkout at **`9b384d5439977784e5cd250ff8ff7966928ddd27`**. D's unchanged audit verifies the Git revision and seven original OSG files: `Vec3f`, `Vec2f`, `Math`, `Export`, `Config.in`, root CMake and license. D generates `osg/Config` from that real template in the build directory. No OSG class replacement or rendering library is supplied. Selected inline math operations linked in D's verified fixture; this does not establish that all OSG math APIs are header-only.

Other dependencies are standard C/C++20, native POSIX headers (`errno.h`, `fcntl.h`, `string.h`, `sys/types.h`, `unistd.h`) and system threads. There is no SDL, GUI, Bullet, audio, ANGLE, Metal, OpenGL, Boost or full engine dependency in this target. The source audit also locks the unchanged reused C/D fixture generators, D CMake, D source manifest and D auditor. No dependency fetch is implemented.

## Actual integration and lifetime

The fixture opens TES3 through `ESMReader`, checks version 1.3, ESM/ESP type and record count, reads `STAT` framing, then invokes `ESM::Static::load`. It verifies the real `RefId` (`eIOSStatic`) and exact `MODL` (`TeSt.NIF`), including the normalized form provided by `ESM::Path`.

An explicit mesh-category policy uses `VFS::Path::join(NormalizedView("meshes"), object.mModel.getNormalized())`. This matches the prefix operation inspected in `components/misc/resourcehelpers.cpp::correctMeshPath`; that larger helper translation unit is not compiled or impersonated. VFS alone does not infer asset categories. This fixture uses a category-relative MODL, not an already `meshes/`-prefixed name. It does not exercise actor model substitution or other higher-level resource corrections.

C's genuine registration helper constructs `VFS::BsaArchive<Bsa::BSAFile>` with a real Windows-1252 encoder. `Manager::buildIndex` is explicit; the last registered archive wins duplicate paths. After extracting the key, the fixture opens actual entry streams and checks exact bytes, over-reads, out-of-range seeks, end-relative seek, EOF and rewind. Already opened streams are checked after `Manager::reset` and destruction; archive-entry pointers are never retained past archive lifetime. Both borrowed encoders outlive their users. The ESM and BSA readers are used read-only.

ASCII case, backslashes, repeated/leading separators are exercised in the ESM path and mixed-case BSA directory. This is not Unicode case folding, `..` resolution, or filesystem sandboxing. No speculative filename-normalization implementation is introduced.

## Synthetic inputs and sixteen subprocess cases

[tools/fixtures.py](tools/fixtures.py) reuses the original C/D deterministic byte builders, not their C++ implementations. It creates fourteen tiny files in an owned build directory:

| Input | Content |
| --- | --- |
| `valid.esm`, `valid.esp` | TES3/HEDR (300-byte payload) and one STAT containing NAME `eIOSStatic` and MODL `TeSt.NIF` |
| `normalized.esm` | Same object with two leading backslashes and mixed-case MODL |
| `no-stat.esm` | TES3 declares one record but none follows; explicit fixture record-presence check |
| `no-name.esm` | STAT missing required NAME; genuine loader rejects |
| `no-model.esm` | STAT without MODL; loader permits it, fixture rejects a model-less resource request |
| `deleted.esm` | STAT with DELE; genuine deletion flag, explicit fixture policy rejects requesting a model |
| `unknown-sub.esm` | Unexpected NOPE subrecord; genuine loader rejects |
| `wrong-tag.esm` | Non-TES3 first tag; genuine reader rejects |
| `oversized.esm` | STAT declares a payload beyond EOF; genuine record-size check rejects |
| `base.bsa` | `Meshes\Test.NIF` plus an adjacent sentinel entry |
| `overlay.bsa` | Same normalized resource, mixed-case/slashes, different payload |
| `missing-resource.bsa` | Valid original archive with only an unrelated entry |
| `unsupported.bsa` | Wrong archive magic; C's existing input policy rejects before adapter creation |

The base model payload is exactly `b'\x00OMW-E\xff\n\x00synthetic-model'` (24 bytes). The override is `b'Override-E\x00\xfe'` (12 bytes). Neither is valid NIF geometry or game data.

Sixteen fresh processes cover: ESM success; ESP success; ASCII normalization; duplicate precedence in each order; absent referenced resource; absent STAT; absent NAME; unknown subrecord; invalid header; oversized/truncated record; absent model; deleted object; missing ESM; missing BSA; unsupported BSA. Successful resource cases include bounded reads/seeking and stream lifetime after reset/destruction. Missing resource checks exercise `exists`, `find` and throwing `get`. All 16 must exit successfully with their own completion marker.

The Python driver hashes the entire input tree before and after **every** process, including failures/timeouts. Unexpected directories, symlinks, modified files or newly created missing-file sentinels fail. Reruns allow only identical known inputs and never overwrite changed/unknown files. SHA-256 results and an aggregate sixteen-case completion marker are printed. Input generation is separate from the read-only C++ fixture; no copyrighted content is used.

## Offline checks and later native review

Run Python 3.10+ from the repository root:

```powershell
python -B experiments/ios-openmw-esm-vfs/tools/audit_sources.py --osg-source C:/Users/austi/Projects/OpenSceneGraph-pinned --require-complete
python -B -m unittest discover -s experiments/ios-openmw-esm-vfs/tools -v
git diff --check
```

The normal suite tests provenance, true dependency closure, byte generation, case inventory and driver failure/integrity contracts. Its subprocess mocks test orchestration only; they do not claim any OpenMW C++ behavior. An optional test runs the genuine compiled fixture when `OPENMW_ESM_VFS_CHECK` points to it. Without that executable it is explicitly skipped. On this Windows host there is no compatible CMake/C++20 POSIX toolchain available; neither C++ compilation nor runtime is asserted.

For manual native macOS/Linux validation with already available tools and the exact separate OSG checkout (no automatic downloads):

```bash
cmake -S experiments/ios-openmw-esm-vfs -B experiments/ios-openmw-esm-vfs/build-host \
  -DOPENMW_IOS_ESM_VFS_HOST_TESTS=ON \
  -DOPENMW_ESM_OSG_SOURCE=/absolute/path/to/OpenSceneGraph-pinned
cmake --build experiments/ios-openmw-esm-vfs/build-host --target openmw-esm-vfs-check --verbose
ctest --test-dir experiments/ios-openmw-esm-vfs/build-host \
  -R '^openmw-esm-vfs-runtime$' --no-tests=error --output-on-failure -V
```

The exact CTest selector excludes D's inherited fixture definition. Native acceptance requires a genuine C++20 compile/link, all sixteen cases, exact payloads and unchanged full-tree hashes. Preserve toolchain/provenance/build/test logs, source manifests, synthetic inputs and hashes. Failed reader/link behavior must be investigated rather than substituted or bypassed.

For **future** iPhoneOS compile-only validation on macOS/Xcode:

```bash
cmake -S experiments/ios-openmw-esm-vfs -B experiments/ios-openmw-esm-vfs/build-device -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$(xcrun --sdk iphoneos --show-sdk-path)" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0 \
  -DOPENMW_IOS_ESM_VFS_HOST_TESTS=OFF \
  -DOPENMW_ESM_OSG_SOURCE=/absolute/path/to/OpenSceneGraph-pinned
cmake --build experiments/ios-openmw-esm-vfs/build-device --config Release \
  --target openmw-ios-esm-vfs -- CODE_SIGNING_ALLOWED=NO
```

Validate both archives independently (six E objects plus fifteen D objects), every member's ARM64 architecture, Mach-O iOS **device** platform and minimum 18.0 metadata. ARM64 alone is insufficient. This static target is not an application or IPA. The workflow prepares these jobs without running them; no iPhone data-runtime execution is claimed.

## Dedicated manual native validation

[`.github/workflows/ios-openmw-esm-vfs.yml`](../../.github/workflows/ios-openmw-esm-vfs.yml) is named **iOS OpenMW ESM-to-VFS native validation**. It has only `workflow_dispatch`: ordinary pushes, pull requests and commit-message tags do not start it. GitHub generally requires a manually dispatched workflow to exist on the default branch first. Once registered, select this workflow in Actions, choose **Run workflow**, and select **ios-port**. Both jobs verify `refs/heads/ios-port` and the exact dispatched `${{ github.sha }}`; another branch fails closed. Registration and dispatch are manual user steps, not performed here.

Two independent `macos-26` jobs use the runner's installed Xcode/CMake/Python toolchain, with versions recorded rather than assumed. Each checks out OpenMW into `openmw/` at the dispatched SHA and `OpenMW/osg` into sibling `osg-pinned/` at the literal pin `9b384d5439977784e5cd250ff8ff7966928ddd27`. No submodules, LFS or other dependencies are fetched. These CI directories do not modify the separate local OSG checkout.

**`host-validation` acceptance:**

- Verify E's 79 full project-file hashes and dependency inventory, inherited D integrity checks, all seven OSG hashes and exact OSG revision before configuration.
- Run the complete E Python suite, configure with `OPENMW_IOS_ESM_VFS_HOST_TESTS=ON`, and verify the actual generated `esm-reader/osg-math/include/osg/Config` using D's unchanged verifier and real audited template/settings.
- Compile and link `openmw-esm-vfs-check` through the original D + E CMake link graph; no multiple-definition or forced-loading workaround is added. Preserve both archives and their exact 15 + 6 source/member inventories.
- Run only `^openmw-esm-vfs-runtime$` with `--no-tests=error`, verbose output and JUnit. Missing, failed, skipped or incorrectly selected tests fail. Require every one of the sixteen unique case markers and the aggregate unchanged-input completion marker in CTest's log.
- Verify the final fourteen-file tree against deterministic hashes. The existing fixture driver separately compares the whole tree around every subprocess, including failures/timeouts. Modified inputs or unexpected files/directories fail. Preserve actual generated inputs and hashes.

The Python suite's optional externally supplied runtime test may skip before compilation. It is not the host acceptance gate: the later mandatory CTest step must compile, link and run the real fixture and all sixteen cases.

**`iphoneos-compilation` acceptance:**

- Independently repeat source/revision/config verification and select genuine `iphoneos`, `arm64`, minimum iOS `18.0`, with host tests disabled and signing disabled.
- Build `openmw-ios-esm-vfs`, which also builds its unchanged D dependency. Require exactly one nonempty output archive for each library; missing, empty or ambiguous paths fail.
- Invoke D's unchanged `validate_esm_archive.py` for exactly fifteen objects. Invoke E's `validate_esm_vfs_archive.py` for exactly six objects. Both use A's unchanged strict archive/Mach-O parser. The six source paths must match E's manifest. The two native inspection steps are independent after successful archive location, so one validation failure does not skip the other's diagnostics.
- Inspect each object with `otool` and independently parse its Mach-O metadata: ordinary ARM64 `MH_OBJECT`, iOS-device `LC_BUILD_VERSION`, exact minimum 18.0. Reject simulator/macOS/Catalyst, arm64e/x86, missing/duplicate/ambiguous metadata, unsafe/unknown members, duplicate aliases, empty objects and incorrect counts. Preserve tool output and structured per-object reports.

Passing the device job proves static compilation and object metadata only. It does **not** prove that a combined iPhoneOS executable links, launches, or reads content on the physical iPhone. Host link/runtime evidence and device static evidence remain separately labeled.

Both jobs use `set -euo pipefail` and always attempt evidence collection/upload after failure. Upload names are `ios-openmw-esm-vfs-host-<run_id>-<run_attempt>` and `ios-openmw-esm-vfs-device-<run_id>-<run_attempt>`, retained fourteen days. Staging directories are respectively `$RUNNER_TEMP/openmw-esm-vfs-host-evidence/` and `$RUNNER_TEMP/openmw-esm-vfs-device-evidence/`:

```text
run.txt, toolchain.log, source-audit.log, source-provenance.log
source-provenance.json
source-sha256.txt, source-sha256-lf.txt          # all 79 project + 7 OSG files
validation-input-sha256.txt                  # experiment, reused helpers and workflow
milestone-d-source-audit.json, milestone-e-source-audit.json
OpenMW-LICENSE.txt, OSG-LICENSE.txt
configure.log, config-validation.log, config-validation.json
generated/osg/Config                         # actual generated header, checksum in report
build.log, build-diagnostics/                # nested CMake/CTest and source audit logs
python-tests.log                             # host
ctest.log, ctest-results.xml, host-results.log, host-validation.json  # host
synthetic-esm-vfs/, synthetic-input-sha256.txt # host inputs and exact hashes
milestone-d-host-members.log, milestone-e-host-members.log           # host
libopenmw-ios-esm-reader.a, libopenmw-ios-esm-vfs.a
archive-locations.json
archive-location.log, milestone-{d,e}-archive-validation.log         # device
archive-inspection/milestone-d/              # device: archive-validation.json, tools, objects
archive-inspection/milestone-e/              # device: archive-validation.json, tools, objects
ambiguous-archives/                          # only if conflicting outputs need diagnosis
job-status.txt, job-status.json, SHA256SUMS
```

Only outputs that exist at failure time can be collected. Device compilation does not run the host fixture or generate synthetic inputs. Collection verifies successful handoffs against the Config/archive hashes recorded by their validators and refuses missing success evidence. Failure collection retains available partial logs, archives and inputs. `SHA256SUMS` covers collected files except itself. Status is captured before upload; GitHub's final job conclusion remains authoritative for upload failures or cancellation.

Offline workflow checks cover triggers, checkout pins, initialization/config paths, exact host selection, strict six-object validation, unchanged D's fifteen-object acceptance, invalid metadata/counts, failure collection, all Bash blocks and embedded Python. They do not assert GitHub schema acceptance or native compiler success. Review these changes before manually committing or dispatching.

## Limits and next boundary

Existing malformed-input limitations remain. The BSA reader can allocate excessively for an undersized directory (`dirsize - 12 * filenum`); an existing-file/magic check is not a safe-input guarantee. ESM's default path stream enables `badbit` only and `getExact` does not check short-read counts. Subrecord boundaries/seeks, untrusted sizes/allocations and optional HEDR behavior have the previously documented limitations. These deliberately small structural cases are not comprehensive security tests or a fix for those issues. Do not feed untrusted archives to this experiment.

The original STAT loader requires NAME, permits absent MODL and reports DELE; the fixture's model-required/deleted policies are explicit caller behavior. No LOD/texture/graphics changes occur here. Licenses and provenance of real OpenMW and pinned OSG sources remain unchanged; synthetic payloads are original experiment data.

After source review and native verification, the next boundary is genuine NIF parsing/resource loading: audit its additional source and link closure, supported NIF versions and real OSG/plugin dependencies; then connect to the independently working iPhone graphics foundation. Asset-category handling, installation/sandbox paths, game-data import/licensing, real-content validation and eventual world/cell/material loading remain separate work. Returning a `.nif`-named byte stream proves none of them. No `Engine::go()` integration is attempted.
