# Review validation, Windows 2026-11-16

The local source review is based on unchanged G5 commit
`cb089f4141782f6c136d68d7e71b03f4f30b73a9`, branch `ios-port`.
Evidence in the review ZIP binds final LF-normalized source bytes. It separates
executed native cases from configured build contracts and pending Apple gates.

| Check | Executed result |
| --- | --- |
| Genuine Windows live-object cases | 24 PASS: 17 positive, seven exact expected rejections |
| Genuine Windows world cases | 42 PASS: 27 positive, 15 exact expected rejections |
| Live-to-NifOsg render lifecycle | PASS, ten assertions; CPU scene graph only |
| Unmodified MWWorld::Scene translation unit | Compiled; not linked/activated |
| G6 Python suite | 27 PASS, zero skips |
| Preserved Python suites G0B through G5 | 277 PASS, zero skips |
| New and preserved Python total | 304 PASS, zero skips |
| Actual core/provider/dependency compiler commands | PASS, 180 genuine core units and 185 core/render consumers |
| Standalone and shared-hook Windows configuration | PASS; existing imported genuine OSG provider |
| Original model/texture and fixture/source audits | PASS using unchanged official pinned OSG |
| Exact dependency preparations | Full archive hashes and extracted inventories PASS offline |
| Public provenance/resource producer chain | G4 -> G5 -> G6 PASS; not an Apple bundle |
| Workflow syntax | 39 Bash blocks; YAML structure and embedded Python parse PASS |
| Raw preservation snapshots | 4,232 / 4,202 / 4,139 files PASS, including all nine Build #15 files |
| Git and added-source whitespace | PASS; no staged files |

Preserved Python counts are G0B 46, G0C 25, G1A 14, G1B 21, G1C 32,
G1D 21, G2 31, G3 16, G4 52 and G5 19. CMake was explicitly available
for its seven G4 platform-forwarding cases. No unavailable-runtime check is
reported as passed. Existing unchanged native G5 evidence remains applicable
to its identical protected source; the new workflow retains actual execution
of all accepted native suites on macOS rather than substituting those logs.

## Native coverage

Live cases exercise ownership, typed NPC identity, mutations, effective poses,
genuine moves and return, registry retirement, foreign epochs, plugin overrides,
new content identities, content deletion, moved leases, budgets, quarantined
partial failure, duplicate identity rejection, concurrent serialized reads,
Unicode/ICU data and genuine FogManager behavior. The rejected runtime-delete
case verifies the real service boundary discovered in the captured Windows
fault. A fault or unrelated error cannot pass a negative test.

The render-lifecycle test checks that actual NifOsg graph placement changes
after live changes, already prepared graphs remain unchanged, disabled objects
are absent, data cells are not duplicated and state survives scene retirement
and cache expiry. This has no current graphics context and is not visible or
GPU rendering evidence.

Clang 19.1.7/Zig 0.14.1 and CMake 4.2.1 reused the existing verified Windows
OSG/Bullet provider and archive wrappers. The new genuine dependency inventory
contains 97 MyGUI, 438 ICU, seven Detour, 42 FreeType and 32 Lua source units,
plus the official ICU data object. The Windows provider is imported desktop
OSG; this is explicitly distinguished from future single-provider ANGLE GLES3
iPhoneOS compilation. Source-view and API audit gates cannot establish Apple
ABI compatibility. Existing OSG override warnings and FreeType's CMake minimum
version deprecation remain visible in retained logs; no warnings are treated
as physical acceptance evidence.

## Private original-content inspection

The user's original installation was read locally without copying assets into
source or public artifacts. Genuine CellStore ownership loaded 1,849 references
across nine exterior cells plus 46 interior references: 1,895 registered objects
in ten loaded cells, including 17 actual actor references. Both base content
and ordered Morrowind/Tribunal/Bloodmoon ownership probes passed 1,857 assertions.
Original ESM/BSA and expansion hashes were unchanged.

The CPU scene reproduced nine cells, 1,715 instances, 950 collision objects,
six program objects, 418 terrain passes, five loads and two door-transition
probes. Fargoth's interior retained 43 instances. Counts, exclusions, door
multiset and probes match the unchanged G5 Windows executable against the same
inputs. Reference traversal changes door enumeration order. These G5/G6 scene
counts should not be presented as the earlier G3 device's 1,679-instance result.

Sanitized evidence contains measured per-process Windows peak working sets and
CPU timings. These are single local probes, not peak iPhone footprint, sustained
performance, measured display/GPU FPS or proof of actor rendering. The full
private reports, door lists, original inputs and profiles remain local and
excluded from the review archive. Official expansion loading is not Tamriel
Rebuilt or arbitrary-mod compatibility.

## Remaining acceptance gates

G5 Apple compilation and physical acceptance remain pending after runner
allocation failures. G6 macOS execution, Apple consumer compilation, actual
ARM64/iPhoneOS dependency archives, final application linking, symbol retention,
SDK/dependency checks, IPA packaging/reopening and physical-device acceptance
are UNVERIFIED. The new workflow prepares those gates; it has not been run.
Authored symbol-table and forbidden-inventory unit fixtures test rejection
contracts only and cannot count as Apple product acceptance.

The intended IPA retains the accepted bundle ID and Documents/Model import
contract. Native CI must independently establish that the added real engine
dependency closure fits Apple APIs and that the full ICU data object targets
iPhoneOS 18.0. Physical testing must establish rendering, retained private data,
streaming behavior, startup cost, lifecycle and memory/thermal bounds before
accepting this milestone. Full Scene/World activation and runtime deletion,
actor simulation and genuine character movement remain future service work.
