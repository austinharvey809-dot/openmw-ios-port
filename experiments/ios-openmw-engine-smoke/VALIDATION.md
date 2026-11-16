# G5 review validation

Review checkpoint: 2026-11-16. Base branch `ios-port`, HEAD
`cd5e74396fc75a502d441925adc77efcac4af1ec`. No source publication, workflow
dispatch or device installation was performed.

## Executed locally

| Check | Actual result and scope |
| --- | --- |
| Genuine engine component and reused world harness | CMake configure, Windows x86-64 compilation and final linking PASS against the previously verified desktop OSG/Bullet provider |
| New Python regressions | 19 tests PASS, zero skips |
| Accepted G4 Python regressions | 52 tests PASS, zero skips; CMake explicitly available |
| Genuine engine-store native cases | 14 PASS: ordinary metadata, overrides, deletion, ignored flags, Lua scalar/table/reference serialization, master remapping and specific invalid-content rejections |
| Reused streamed-world native suite | All 42 cases PASS with the genuine ESMStore-backed index; authored inputs unchanged |
| Label dispatch | Native assertions select distinct core/KHR function spies, reject missing advertised procedures and retain exact assertion counts; no actual GPU execution is inferred |
| Configured provider | All 45 new host compilation units audited for exact source inventory, strict C99/C++20, consistent platform options and applicable Bullet double precision |
| Generated public metadata | 17 accepted G4 public files reconstructed from authenticated CI evidence/IPA; 18 G5 public resources generated, bound expectation header checked, unexpected resource rejected |
| Workflow | Manual-only structure, three jobs, 36 Bash blocks and five embedded Python blocks parsed; YAML loaded with PyYAML 6.0.3, source hash recorded |
| Python/source syntax | Every new Python file parsed; new source/workflow whitespace checked; Git whitespace PASS |
| Preservation | All 4,202 files from the resumed accepted-tree snapshot unchanged; all 4,139 original snapshot files unchanged |
| Prior milestone/source audit | 53 A–E entries, Milestone F integration, accepted NIF fixtures/source closure, pinned provider and all nine Build #15 files verified unchanged by retained audit contracts and raw snapshots |

The native rejection runner retains exit codes, signals, binary-safe stdout and
stderr, timeout/spawn failures and partial results. A crash, timeout or arbitrary
ordinary failure cannot satisfy a negative case. New engine cases also require
their exact assertion inventories. Existing G4 source is unchanged; the G5 suite
retains the accepted container-deletion rejection while ordinary record deletion
and CELL reference deletion use genuine engine behavior.

## Private genuine-content inspection

The original installation was accessed read-only. No game content was added to
source, fixtures, public resources or the review ZIP.

| Windows CPU test | Result |
| --- | --- |
| Morrowind.esm engine metadata | 2,538 cells; 574 books; 2,675 NPC records |
| Ordered Morrowind.esm → Tribunal.esm → Bloodmoon.esm metadata | 2,887 cells; 635 books; 3,041 NPC records |
| Original streamed Seyda Neen world | Nine active cells, 1,849 references, 1,715 static instances, 950 collision objects, six prepared programs, 418 terrain passes |
| Original lifecycle probes | Five CPU world loads, two door transitions, arrival grounding and movement probe PASS |
| Integrity | All four checked original files unchanged: Morrowind.esm/bsa and Tribunal.esm/Bloodmoon.esm |

Measured subprocess wall times were approximately 290 ms for base metadata,
360 ms for the three-file metadata sequence and 704 ms for the world probe.
These are individual Windows CPU observations, not benchmarks or predictions of
iPhone startup/frame performance. The world harness repositions the camera to
probe transitions; it does not demonstrate physical traversal.

The static view explicitly excluded gameplay-only BOOK, CREA, LEVC, NPC and WEAP
placements and an editor marker. Metadata retention is not actor/item rendering.
Expansion metadata loading does not establish expansion resource, world,
gameplay or device compatibility. Tamriel Rebuilt/Tamriel_Data remain untested.

## Retained G4 evidence

Successful Build #5 CI artifacts were authenticated and independently reopened.
The actual macOS result contains all 29 standalone startup assertions; all 42
world cases and preserved native suites passed. The ARM64/iPhoneOS IPA contains
the exact 1,377-file public inventory and required static registrations, with
source/pins/resource bindings intact. G4 physical acceptance is recorded in
[G4-COMPLETION.md](G4-COMPLETION.md), separately from new G5 execution.

## Not executed or accepted for G5

macOS ARM64 execution, Apple SDK compilation, iPhoneOS linking, actual Lua archive
platform inspection, complete bundle validation, unsigned IPA packaging/reopening
and physical G5 rendering remain **UNVERIFIED**. Their strict manual CI gates are
prepared, not passed. No fabricated SDK, API, capability or image decoder was used.

The iOS preflight checks every new engine/Lua/UIKit consumer before the long OSG
build and inspects every genuine Lua archive object for ARM64/iPhoneOS 18.0.
It requires Lua's actual `LUA_USE_IOS` configuration; source review identified
that omitting it would compile Lua's unsupported `system()` call on iOS. Final
package validation requires a genuine SDK, defined ESMStore/registration symbols,
exact resources and current source identity before and after IPA reopening.

Remaining risks include the new store's device memory/startup cost, untested
Apple code paths, pale distant geometry, clear-only loading frames, callback
stalls and existing upstream portability warnings. Full CellStore/Scene,
character physics, animation, gameplay, water and dynamic weather integration
remain outside this slice. Actual GPU FPS/completion and sustained thermal
stability remain unmeasured.

## Reproduction and evidence

`tools/validate.py` runs the local checks with explicit CMake, Bash, build and
snapshot paths. Set `OPENMW_G5_OSG_REFERENCE` to the unchanged pinned OSG checkout;
on Windows, include the verified provider's OSG DLL directory in PATH. It writes
UTF-8 logs and source/binary SHA-256 identities under ignored `artifacts/validation`.

The source-review package includes selected validation logs, native results,
sanitized private-content counts, G4 artifact/physical-evidence hash summaries
and the exact source inventory. Original exports, recordings, private profiles,
game assets, third-party archives, compiled libraries and executables remain local.
