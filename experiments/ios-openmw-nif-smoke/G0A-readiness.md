# Milestone G0A implementation readiness and private-asset inventory

Status on 2026-11-10: **candidate inputs and an uncompiled genuine-reader host check are prepared; genuine NIF parsing has not run.** Branch `ios-port`, source commit `973f873a458b4974af87e792db852d144c492cfb`, pinned OSG `9b384d5439977784e5cd250ff8ff7966928ddd27`. No G0 PASS or geometry result is asserted.

## Confirmed parser and Bullet closure

`Nif::Reader::parse(Files::IStreamPtr&&)` in `components/nif/niffile.cpp` constructs and reads the typed records. `NiNode::mChildren`, `NiGeometry::mData` and `NiTriShapeData::mVertices`/`mTriangles` are inspected by the isolated C++ check. The 12 genuine NIF `.cpp` units are `base`, `controller`, `data`, `effect`, `extra`, `niffile`, `nifstream`, `node`, `particle`, `physics`, `property`, `texture`. Additional direct sources are `components/files/hash.cpp` and bundled `extern/smhasher/MurmurHash3.cpp`. The unchanged D/E `openmw-ios-esm-vfs` library supplies ESM/STAT/BSA/VFS, encoders and logging. Exact final link closure remains unverified until a compiler/linker runs.

The decoding path uses pinned OSG **math headers** for vectors, transforms and bounds; it does not instantiate `osg::Node`, use ANGLE or render. Bullet enters because unchanged `components/nif/node.cpp` also defines `NiTriShape::getCollisionShape` and `NiTriStrips::getCollisionShape`. It includes `btTriangleMesh.h`, `resource/bulletshape.hpp` (which includes `btBvhTriangleMeshShape.h` and `btScaledBvhTriangleMeshShape.h`), and `misc/convert.hpp` (which includes `btQuaternion.h`, `btTransform.h`, `btVector3.h`). The collision methods construct `btTriangleMesh` and `Resource::TriangleMeshShape`; those methods are not called by the candidate parser check, but their translation unit must compile and link. The minimum observed Bullet link components are `BulletCollision` and `LinearMath`; `BulletDynamics` is not selected in OpenMW's root CMake for this component. The host CMake mirrors OpenMW's `>=287` version gate, double-precision compile/link probe and `BT_USE_DOUBLE_PRECISION` definition. Exact transitive Bullet/OSG link behavior remains untested.

The repository's `extern/CMakeLists.txt` names the fallback source **Bullet Physics 3.25** at `https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz`, with archive SHA-512 `7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4`. It enables `USE_DOUBLE_PRECISION`, static libraries when `BULLET_STATIC` is set, and disables demos/extras. No archive or Bullet headers/library are present locally; neither a host C++20 compiler/CMake nor WSL is available in this Windows session. Bullet license text is not locally available to verify; before provisioning, review the supplied archive's license and preserve its notices. Do **not** invoke the root FetchContent recipe while offline. A manually approved acquisition should obtain that exact upstream archive outside this repository, verify the SHA-512 before extraction, preserve the original archive and license, build `BulletCollision`/`LinearMath` in double precision for the host, and expose it to G0's `find_package(Bullet)` without changing pins. A distinct matched iPhoneOS ARM64 build would be required later. No download or installation was attempted here.

The successful F workflow's `macos-26` host job establishes a capable macOS/Xcode/CMake/Python environment for its existing C++20 closure. It does **not** establish Bullet availability on the runner. With a reviewed offline Bullet provisioning mechanism, a separate manual-only G0 workflow could configure the isolated G0 host target, preserve configure/build logs, run positive and negative parser cases and hash binaries/fixtures/dependency sources. This workflow was not created because its required Bullet source provision and license review remain unresolved. Do not change F's workflow. iPhoneOS linking follows host parser acceptance, as a separate gate.

## Original, public candidate fixture (unvalidated)

`tools/generate_fixtures.py` deterministically creates an original 4.0.0.2 NIF from the current OpenMW read order. It writes `NiNode` record 0 with a child reference to record 1, `NiTriShape` record 1 with a data reference to record 2, and `NiTriShapeData` record 2 containing three authored coordinates and one triangle index triplet. It includes no texture record or external resource name. This describes **generator intent**, not observed parser output. A header-corrupted file and a truncated file are negative candidates. The synthetic ESM and BSA are produced with the existing milestone fixture writers, using the same `STAT` ID and normalized `meshes/test.nif` path as F; no game data was used.

| Candidate file | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/triangle-candidate.nif` | 334 | `d1b9b0158fc3a1857a0f7ec5063c74171210e5bd8e11cf412214ca4350bdf6c4` |
| `data/invalid-header.nif` | 334 | `ff4e2b49ee5baca0f8e1708d9cb9fcf2c538ff1d123833001e49f4186baeb42a` |
| `data/truncated.nif` | 317 | `ca7e14793779778a3badbc01d160c7b46627595eec32d0a989758300738f5758` |

`data/fixture-manifest.json` records size/SHA-256 for all eight generated inputs and explicitly marks them `candidate-unvalidated-by-openmw-parser`. These bytes must not be called valid until the genuine C++ parser accepts them. The generator refuses to overwrite changed files. `tests/nif_parse_check.cpp` reads a real synthetic `STAT`, registers the BSA with OpenMW VFS, checks exact returned bytes, passes a fresh VFS stream to `Nif::Reader`, and inspects resolved typed records and actual decoded geometry. `tools/run_host_cases.py` independently checks SHA-256 and unchanged inputs and invokes positive, invalid-header, truncated and missing-resource cases. Both C++ compilation and all runtime cases remain **unexecuted**. No parsed counts are available.

## Private Morrowind installation: metadata only

The user's `Data Files` directory exists. `tools/inspect_private_assets.py` read the actual ESM record boundaries and BSA directory tables, then hashed selected bounded archive byte ranges **without extracting or writing asset bytes**. Its STAT association is from a strict metadata-only Python scan, not a genuine OpenMW ESM or NIF runtime result. It found 2,744 distinct model paths referenced by `STAT` records in `Morrowind.esm`; archive entry counts were 11,090/1,174/1,545 for Morrowind/Tribunal/Bloodmoon, of which 5,798/621/901 names ended in `.nif`. A loose `Meshes` directory exists with 98 immediate subdirectories; it may contain installed mods, so the candidate list below is limited to the base `Morrowind.bsa` and `Morrowind.esm`.

| Base file | Bytes | Last modified UTC |
| --- | ---: | --- |
| `Morrowind.esm` | 79,837,557 | 2000-01-01 00:00:00 |
| `Morrowind.bsa` | 310,459,500 | 2002-06-21 14:31:46 |
| `Tribunal.esm` | 4,565,686 | 2000-01-03 00:00:00 |
| `Tribunal.bsa` | 64,986,032 | 2002-10-29 19:22:06 |
| `Bloodmoon.esm` | 9,631,798 | 2000-01-02 00:00:00 |
| `Bloodmoon.bsa` | 118,425,318 | 2003-05-01 11:37:30 |

Supporting files are also present: root `Morrowind.ini` (28,914 bytes, modified 2025-12-08 00:33:21 UTC), loose `Textures`, `Icons` and `Sound` directories, and `Data Files/Morrowind - Invalidation.bsa` (83 bytes, modified 2025-04-20 01:59:52 UTC). These were inventoried only; the game configuration was not opened or changed. Other installed `.esp` files and loose meshes may affect a private full-data VFS overlay, so the base-archive candidates below are explicitly scoped to `Morrowind.esm` and `Morrowind.bsa`.

| Base archive resource path | STAT ID from metadata scan | Bytes | SHA-256 of exact archive range |
| --- | --- | ---: | --- |
| `meshes/i/in_vs_pitceil_01.nif` | `in_vs_pitceil_01` | 854 | `360822b0a8814c671a98c242120de2141eaf2c6e1106032b67dd81b5d95b2152` |
| `meshes/i/in_vs_pitfloor_01.nif` | `in_vs_pitfloor_01` | 862 | `c1de86352f2f4f7b48fe3a8cf73560ecbefe7daa6291814461c05d0e7d5e351b` |
| `meshes/i/in_6th_chalk00.nif` | `in_6th_chalk00` | 871 | `f71dae40d9beb1a46eb709ea6589a2b38421e1eeb3479dc1454cd2e81225ab62` |
| `meshes/i/in_6th_chalk10.nif` | `in_6th_chalk10` | 871 | `017b6c729ee5a82bc82758edb82e3cd6a0cff55c5c41fced9e96d5a0e31ca3c4` |
| `meshes/i/in_6th_chalk20.nif` | `in_6th_chalk20` | 871 | `de05f68415dfda6107774c66d63de54b86dcc2cc220f494e9402935b3ab1f760` |
| `meshes/i/in_6th_chalk30.nif` | `in_6th_chalk30` | 871 | `8f72afc19ba094fb453e64835e9a17f76776af8f66186c5077ee884691c65b28` |
| `meshes/i/in_lava_blacksquare.nif` | `In_Lava_Blacksquare` | 899 | `69884bf0a524ed4009f86527e2c9ac2e894984120e8709235de8b6376c14b7e6` |
| `meshes/f/furn_rug_02.nif` | `furn_de_rug_02` | 1,103 | `b61c28bfa7e45d8d91cf82da72396c66d8bac32effbd6bf38f1d8aaf1b6b8534` |

The smallest base-archive candidate is a reasonable first **private parser input**, subject to parser acceptance; its 854-byte size says nothing about geometry complexity or texture dependencies. External texture requirements and parsed counts are unknown for all candidates. The original files were opened read-only and no game process/configuration was touched. SHA-256 of all six named ESM/BSA files was identical before and after a repeat inspection (the full archive hashes are retained only in memory); this confirms that inspection did not change those files. No copyrighted bytes were copied into this repository, local G0 artifacts or public CI inputs. `artifacts/` is Git-ignored for any later private extraction/logs; such files must stay local. Public CI must use only the independently parser-validated original synthetic fixture.

## Next gates and evidence boundaries

1. Review and authorize the exact Bullet 3.25 archive acquisition and license handling. Verify its SHA-512 before extraction; build host double-precision `BulletCollision` and `LinearMath` without network access during the build. Record compiler/CMake/Bullet provenance and preserve diagnostics.
2. Configure the isolated host CMake target with pinned OSG and provisioned Bullet. Compile all genuine NIF units, link the check and run `run_host_cases.py`. Any source/link failure is a blocker to resolve openly; never omit `node.cpp` or fake collision symbols. Record actual decoded geometry only from parser output.
3. Privately run the same genuine parser against the selected base-archive model through an actual `STAT` and OpenMW BSA/VFS path. Verify its exact hash and unchanged game-file hashes before/after. Never place game bytes or a signed app containing them in public CI or an artifact.
4. After host positives and negatives pass, prepare a separate manual-only G0 native workflow. Host parser acceptance, native iPhoneOS ARM64 linking and physical-device parsing must be separate gate outcomes. The present G0A sources do not include a native app or workflow and do not claim device readiness.

## Preservation and local validation

All new implementation, generated fixtures and metadata-only inspection code are contained in this isolated G0 directory. Milestones A–F, upstream OpenMW, the pinned OSG checkout and the nine unfinished Build #15 files are unchanged. No internet, download, staging, commit, push, Actions dispatch, game-file modification or rendering integration was performed. Python syntax for all three new scripts passed, and all eight generated inputs matched a fresh deterministic regeneration and their SHA-256 manifest. The existing E source audit passed (21 units, 79 source/header hashes), all 53 A–E preservation entries matched, all nine Build #15 file hashes matched the saved baseline, the pinned OSG checkout is clean, and `git diff --check` found no whitespace errors. Parser compile/run and geometry evidence remain unavailable.
