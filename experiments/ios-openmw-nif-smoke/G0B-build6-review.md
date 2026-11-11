# G0B Build #6 synthetic NIF layout correction

Prepared 2026-11-10 (America/Chicago), branch `ios-port`, starting HEAD
`aef5b0ac28bbfeb92ee6dc0d50ac90b03a968f09`. **Ready for manual review only. The corrected
candidate has not been executed through the genuine parser. G0 has not passed.**

## Build #5 evidence and confirmed format defects

Read-only inspection of [Build #5](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/42951788360)
confirmed all 38 then-current contract tests passed, Bullet acquisition and
configuration passed, and the native `openmw-nif-parse-check` executable linked.
The genuine runtime failed its first case with `FAIL: Invalid index: -155`.
The positive-case failure stopped the harness before the negative cases.

The first incorrect serialized field begins at byte **90**, the root
NiAVObject rotation. The generator wrote four float32 quaternion values (16
bytes), while `NIFStream::read<Matrix3>` reads nine contiguous float32 values
(36 bytes) into `Matrix3::mValues[3][3]`. The same error occurs in the shape.
The correct identity array is `1,0,0, 0,1,0, 0,0,1`, in the order of the nested
array. `Matrix3::toOsgMatrix` transposes that representation when converting;
no quaternion encoding belongs at these NiAVObject fields.

In addition, all six serialized fields read via `get<bool>()` use **signed
int32** in 4.0.0.2: node/shape bounds presence and geometry vertex, normal,
vertex-color and UV presence. The former generator used int8. Flags/counts are
independently typed integers and retain their widths.

These discrepancies confirm the old fixture was incompatible with the reader.
They explain loss of field alignment; this review does not claim to have traced
the particular `-155` value to one field, nor that the corrections establish
parser acceptance. No additional format correction was identified in the full
layout audit.

## Complete layout comparison

Offsets are zero-based. The old generator column describes its intended fields,
which the reader cannot reliably reach after the first mismatch.

| Reader field / version condition | Old 334-byte generator | Corrected encoding |
| --- | --- | --- |
| Header / version / record count | Correct 40-byte LF line; uint32 version and count at 40/44 | Unchanged: 0x04000002, three records |
| Record type names | uint32 length + ASCII; starts 48/139/234 | Same encoding; starts 48/162/280: NiNode, NiTriShape, NiTriShapeData |
| NiObjectNET | Sized name, int32 extra=-1, controller=-1 | Unchanged; names G0Root/G0Triangle; no newer extra list |
| NiAVObject flags / translation | uint16=0, three float32 zeros | Unchanged widths and values |
| NiAVObject rotation | Four float32 at old offsets 90/189 | Nine float32 identity values at 90/212 (36 bytes each) |
| Scale / velocity / property list | float32=1, three float32 zeros, uint32 count=0 | Unchanged widths and values; velocity/properties present for this old version |
| Node/shape bounds presence | int8=0 at 126/225 | int32=0 at 146/268; no bounds payload |
| NiNode children / effects | uint32 count=1, int32 child=1, uint32 effects=0 | Same fields at 150–162; root transform reset in reader consumes no additional bytes |
| NiTriShape geometry / skin | int32 data=2, skin=-1 | Same fields at 272–280; no material fields before 10.0.1.0 or modern shader refs |
| NiGeometryData vertex count / presence | uint16=3 at 252, int8=1 at 254 | uint16=3 at 298, int32=1 at 300 |
| Vertex payload | Nine float32 values (36 bytes) | Unchanged intended triangle vertices at 304–340 |
| Normals presence / sphere | int8=0 at 291; center + radius as four float32 | int32=0 at 340; sphere (0,0,0,1) at 344–360 |
| Vertex-color presence | int8=0 at 308 | int32=0 at 360; no color payload |
| UV flags/count / presence | uint16=0 at 309; int8=0 at 311 | uint16=0 at 364; int32=0 at 366; no UV arrays |
| Modern geometry fields | Absent | Remain absent: group ID, keep/compress flags, modern data flags, consistency/additional data |
| NiTriBasedGeomData triangle count | uint16=1 | Unchanged at 370 |
| NiTriShapeData indices | uint32 count=3, three uint16 indices 0/1/2 | Unchanged at 372/376; no newer triangle-presence Boolean |
| Match groups | uint16 count=0 | Unchanged at 382; no group payload |
| Root references / EOF | uint32 count=1, int32 index=0 at 326; EOF 334 | Same at 384; EOF 392 |

Source authority is the unchanged local `components/nif/base.cpp`,
`node.cpp`, `data.cpp/.hpp`, `nifstream.cpp/.hpp`, `niftypes.hpp`,
`niffile.cpp/.hpp` and `recordptr.hpp`. The 4.0.0.2 header has no modern
endianness/user/Bethesda header, record type table, record sizes, separator,
string table or groups. Record lists use uint32 counts and int32 references;
match-group counts use uint16. All references and version branches above were
checked against those implementations.

## Authorized fixture regeneration and provenance

The two Matrix3 corrections add 40 bytes; six Boolean corrections add 18 bytes.
The candidate is now **392 bytes**, preserving one root, one shape, one geometry
data record, three vertices and one triangle as acceptance targets. It contains
no textures or private game content.

The generator adds a version-specific `mw_bool` helper and changes only those
six Boolean fields and the two rotations. It retains its refusal to overwrite
unexpected/modified fixtures. The byte updates were explicitly authorized for
this demonstrably invalid synthetic candidate; they do not relax future
regeneration or runtime checks.

The four BSA containers were rebuilt with their matching NIF payload and size.
The invalid-header variant changes only byte zero; truncation removes the final
17 bytes (leaving an incomplete uint32 index count); invalid-reference changes
only the shape data index at 272 from 2 to 99. Missing-resource BSA and ESM remain
byte-identical. The unchanged wrong-resource test pairs the positive archive
with the new invalid-header NIF. Exact data inventory remains twelve entries.
`nif-source-sha256.json` is unchanged.

This table preserves the complete original-to-new size/SHA-256 trail. The
original bytes remain in the starting Git commit; they are not duplicated in
the current fixture inventory.

| Fixture | Bytes: original → new | Original SHA-256 | New SHA-256 |
| --- | --- | --- | --- |
| `invalid-header.bsa` | 382 → 440 | `20d27b747ea2c8b6c5e5891b39e312584a0785f6bbf8f9d39eea1333b3a693fd` | `aa4b690a654334ab392417db891e67f93ca89dad975f636fbc9363ad86370c18` |
| `invalid-header.nif` | 334 → 392 | `ff4e2b49ee5baca0f8e1708d9cb9fcf2c538ff1d123833001e49f4186baeb42a` | `772cba6c6370d6c0d0b23667026e3acb9de9c22f9f5a4fdc8b0dfee963b3a95b` |
| `invalid-reference.bsa` | 382 → 440 | `5085c50d4c260a30f813128a68d8595b2d8c178ce94717e9d3358c0f05add827` | `aacba465160ee4c7e7bb5e20635a3bfb38df806bb9aa24601d0482085006e08a` |
| `invalid-reference.nif` | 334 → 392 | `994e93861282a759542207b5034e4ed1488271c27eb2a6bc5d7b45d8b0149c0c` | `55c27c3592f14f69feb1a665488294e015e0b1c7e6cb296023886d213131e4bb` |
| `missing-resource.bsa` | 58 → 58 | `ecc6ad80b0bda91fc90200161d92b2f8786d996ead4a7d0c087f9f9afccc798b` | `ecc6ad80b0bda91fc90200161d92b2f8786d996ead4a7d0c087f9f9afccc798b` |
| `triangle-candidate.bsa` | 382 → 440 | `47546cb468b4b86dd78b55d095105096fcd34543a6e2975eff0c729b3c202f1f` | `72adc5667e62f146d4bfa770b568b29b3f519def6cce1784a49f67c632058ec3` |
| `triangle-candidate.nif` | 334 → 392 | `d1b9b0158fc3a1857a0f7ec5063c74171210e5bd8e11cf412214ca4350bdf6c4` | `0b77632dd08be22a3df33be66939065e4d467fa1231b9a12459f844224f846ff` |
| `truncated.bsa` | 365 → 423 | `ca657139826f5b796d385b1509117ac95f28e3b6c523b97c2dde5198dd6456b6` | `d48bc2bc014f99ff84ee12ae8ecc867f1ff05798b67524961c703cf7cbe590ed` |
| `truncated.nif` | 317 → 375 | `ca7e14793779778a3badbc01d160c7b46627595eec32d0a989758300738f5758` | `66c8c54b1623a796f151c009a5c164da6f25250103a2e7aedc790bddd92fa63b` |
| `valid.esm` | 376 → 376 | `48fdfa9d1aed2bb3d82169cd16574088373c4deaff3a39e9b40ea809157fcd9f` | `48fdfa9d1aed2bb3d82169cd16574088373c4deaff3a39e9b40ea809157fcd9f` |

## Validation and remaining uncertainty

Python still resolves to a WindowsApps alias that cannot launch. No suitable
local CMake/native POSIX toolchain or compatible genuine parser executable is
available. Therefore **Python tests, Python syntax, Python regeneration/audit
execution, and genuine parser execution of the corrected fixture are
unverified**. Historical Build #5 results apply to the old fixture.

Available independent checks passed:

- A PowerShell/.NET binary encoder reproduced **all ten original fixture
  hashes exactly** before writing any fixture. Its corrected encoding follows
  the changed generator's field sequence. Two corrected generations produced
  identical bytes/hashes; sorted UTF-8/LF manifest serialization was preserved.
  Actual execution of the Python generator remains unverified.
- A separate sequential byte inspector consumed exactly 392 bytes, checked
  record boundaries 48/162/280, root-list offset 384, both matrices, all six
  int32 Boolean fields, every reference/count, sphere, vertices and indices.
  This inspects serialization only and is not a replacement NIF reader or
  genuine parser evidence.
- All four BSA resource payloads match their NIF bytes exactly, their directory
  sizes/offsets and payload lengths match, all ten manifest sizes/SHA-256 values
  match, and the exact twelve-entry inventory contains no unsafe entries.
- Invalid header, truncation and invalid-reference variants are exact deliberate
  mutations. The three native parser negatives are still unexecuted for this
  corrected layout, as are missing-resource and wrong-resource native cases.
- All 53 A–E preservation hashes, 59 G0 source/header hashes, 79 E source/header
  hashes, five reused E build hashes and seven pinned OSG hashes match.
- Four successful build/runtime configuration files (G0 CMake, workflow, C++
  parser check and runtime harness), all eighteen F files, all nine unfinished
  graphics files, the ESM, missing-resource BSA and NIF source manifest retain
  their starting raw hashes. OSG remains clean at
  `9b384d5439977784e5cd250ff8ff7966928ddd27`. Bullet 3.25 and its exact SHA-512
  are unchanged. Git HEAD and index are unchanged.
- Workflow shell syntax and Git whitespace checks pass.

Eight added `FixtureLayoutContracts` tests cover header/record/object
boundaries, Matrix3 transforms, all six int32 Booleans, references/root list,
geometry payloads, exact BSA resources, deliberate negatives, and deterministic
manifest regeneration with unexpected-file rejection. All 38 existing tests
are retained, for **46 total**; none was run locally in this task.

The positive geometry acceptance checks, SHA-256 verification, before/after
input snapshots, strict PASS markers/exit codes and fail-fast workflow are
unchanged. No upstream implementation, milestone A–F, original Morrowind file,
dependency pin or rendering code was modified. No tools/dependencies were
installed, and no assets were obtained from the Morrowind installation.

## Exact files and manual handoff

Changed:
- `tools/generate_fixtures.py`, `tools/test_g0_ci.py`, `README.md`;
- `data/fixture-manifest.json`;
- `data/triangle-candidate.nif`, `data/triangle-candidate.bsa`;
- `data/invalid-header.nif`, `data/invalid-header.bsa`;
- `data/truncated.nif`, `data/truncated.bsa`;
- `data/invalid-reference.nif`, `data/invalid-reference.bsa`.

Added: `G0B-build6-review.md` (this record). Paths are relative to this experiment.

Build #6 preparation is ready for manual review. A later separately authorized
run must execute the current tests/audits and genuine positive and negative
parser cases. Only actual parsed output can establish the intended three
records, one root, one geometry, three vertices and one triangle.
No staging, commit, push or GitHub Actions dispatch occurred.
