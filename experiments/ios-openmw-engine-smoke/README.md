# G5: genuine engine content-store integration

Review candidate, based on physically accepted G4
`cd5e74396fc75a502d441925adc77efcac4af1ec`. No G5 Apple execution or physical
rendering acceptance is claimed. G4's scoped completion is recorded separately
in [G4-COMPLETION.md](G4-COMPLETION.md).

This slice replaces the temporary record dispatcher/type map and six individually
owned stores with the real **MWWorld::ESMStore**. The engine owns all ESM3 record
tables, record dispatch, setup, ID/type indexing, ordinary record deletion,
ignored-record flags, dialogue loading and Lua configuration/remapping. Actor and
item metadata is retained even where gameplay activation remains unsupported.
The private Windows test loaded Morrowind's 2,538 CELL, 574 BOOK and 2,675 NPC
records through this implementation.

The existing genuine ResourceSystem, SceneManager, NifOsg::Loader, TerrainGrid,
BulletShapeManager, image readers and bounded static-world scene preparation are
reused. No new terrain, object renderer, streaming algorithm or character solver
is introduced. The controller-first frontend and existing Documents/Model
manifest/world-profile imports remain compatible. The bundle identifier remains
`org.openmw.experiments.real-model`; a future signed upgrade should retain the
existing Documents data. Do not delete the installed app to test this slice.

## What is deliberately not claimed

This is not full CellStore/WorldModel, MWWorld::Scene, actor, savegame, script
scheduling or gameplay integration. The accepted static-world coordinator still
provides scene loading and the experimental movement solver. BOOK/NPC/CREA and
other unsupported gameplay classes remain explicitly counted exclusions rather
than silently activated static meshes. Water/swimming and dynamic weather remain
absent. Ordered metadata ingestion of Morrowind, Tribunal and Bloodmoon passed
on Windows (2,887 cells, 635 books, 3,041 NPC records). This does not establish
expansion resource, scene, gameplay or device compatibility. Tamriel Rebuilt and
Tamriel_Data have not been tested. The architecture retains ordered content/VFS
inputs and bounded geometry residency for that eventual work.

The ESM3 component omits the upstream definitions of `ESMStore::loadESM4` and
`ESMStore::getSpellList`. They are not replaced with stubs; invoking them fails to
link. Every remaining method body in that TU is genuine upstream code. Independent
Lua helpers are selected verbatim from `luastate.cpp`. These generated component
views are temporary build boundaries, documented in [ARCHITECTURE.md](ARCHITECTURE.md),
not a claim that the entire upstream application has linked.

The pinned Store<Cell>/Store<Land> do not implement generic static erasure.
G5 therefore preserves explicit rejection of CELL/LAND container deletion using
the genuine codecs in a preliminary metadata pass. CELL reference deletion,
master remapping, moved-reference leases, ordinary base deletion and overrides
retain their native behavior. Unknown record types are rejected by the actual
engine dispatcher, rather than silently skipped as in the temporary index.

## Graphics diagnostic correction

Pinned OSG resolves core `glObjectLabel` even when ANGLE exposes ES3.0 plus
GL_KHR_debug. G5 selects `glObjectLabelKHR` for that advertised GLES extension,
core labels for ES3.2+, and the unsuffixed KHR function on desktop GL. Missing
advertised procedures fail explicitly. Selection happens after genuine OSG
capability initialization with a current context, under the existing registry
gate and before resource compilation. Synchronous debug capture, message filters
and the actual rendering path are retained. Native tests exercise dispatch with
distinct function spies; actual iPhone GL dispatch still requires validation.
[KHR_debug specification](https://registry.khronos.org/OpenGL/extensions/KHR/KHR_debug.txt).

Pale distant geometry remains an investigation item. G5 does not alter accepted
lighting, fog, alpha or material math based solely on recording appearance.

## Build and validation

No system installation is required. The additional real interpreter is
[Lua 5.4.9](https://www.lua.org/ftp/), with the official exact archive digest in
`dependencies.json`; it is compiled as C99 without JIT, using stock
`LUA_USE_IOS` on iPhoneOS. This component does not open the standard libraries or
execute gameplay scripts. Existing OSG/ANGLE/Bullet/image-library pins remain unchanged.

Prepare Lua with normal TLS verification:

```sh
python3 experiments/ios-openmw-engine-smoke/tools/acquire.py --output /tmp/g5-deps
```

Configure the accepted G4 host harness using its normal documented provider
arguments, additionally supplying:

```sh
-DCMAKE_PROJECT_OpenMWWorldIntegration_INCLUDE=/absolute/repo/experiments/ios-openmw-engine-smoke/cmake/attach_host.cmake
-DG5_LUA_SOURCE=/tmp/g5-deps/lua-5.4.9
```

Then build `openmw-g5-store-check` and `openmw-engine-check`, and run
`ctest --test-dir <build> -R '^g5-' --no-tests=error -V`. Run the accepted G4
gates separately. The supplemental Windows build uses the existing audited G3/G4
desktop provider; it does not emulate the Apple SDK or ANGLE/Metal GPU.

The new manual-only `.github/workflows/ios-openmw-engine-device.yml` retains all
G4 host, early startup, dependency archive, static registration, Apple framework,
native linking and packaging gates. It adds the genuine engine tests, syntax
compilation of every new engine/Lua/UIKit TU, Lua archive ARM64/iPhoneOS object
inspection and strict G5 bundle/IPA reopening. Exactly one OSG/Bullet/ANGLE provider
is configured per build. The accepted G4 and G5 application executables reuse it.
No workflow has been dispatched for this review candidate.

See [VALIDATION.md](VALIDATION.md) for executed checks and [REVIEW.md](REVIEW.md)
for the exact source inventory and handoff. Source-review evidence is kept under
ignored `artifacts/`; proprietary files, recordings, import profiles, dependency
archives and binaries are excluded from the review source payload and Git.
