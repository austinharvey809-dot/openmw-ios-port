# Engine integration boundary and next vertical slice

## Current ownership

`G5::EngineIndex` owns one genuine `MWWorld::ESMStore`, one UTF-8 encoder and a
16-reader cache. Its CELL/LAND/LTEX references refer directly into that engine
store. Content files are resolved in the supplied master-before-plugin order,
with duplicate filename and missing-master rejection. Genuine ESMStore processes
all ESM3 metadata and initializes its native ID index only after all files load.
The engine store outlives all borrowed metadata pointers and streamed areas.

The accepted coordinator owns one active area and at most one prepared candidate.
Only its existing background operation mutates engine/resource state; only the
GL thread publishes a shader-accepted candidate. Cache maintenance uses the
accepted OSG reference clock, registry gate, failure separation and retirement
ownership. This slice does not add a second asynchronous owner of ESMStore or
mutable gameplay state. Holding full record metadata does not load full-world
geometry, textures or collision data simultaneously.

G4 source is immutable. `engine-lock.json` guards all source inputs to the build
view. `prepare_frontend.py` reuses accepted Resource/World/Terrain/Session code
through mechanical namespace/diagnostic identity changes. The only semantic
frontend additions are engine metadata counters and context-specific label
dispatch. The reference-merge body remains byte-equivalent after renaming; the
temporary WorldIndex dispatcher is not copied. Tests verify those boundaries.
This mechanism avoids duplicating a large source tree, but is still integration
debt. Future engine integration should remove this frontend view, not proliferate
more generated gameplay coordinators.

## Why not instantiate the complete application now?

The pinned upstream source, rather than header names alone, establishes these
dependencies:

| Upstream system | Existing behavior and dependency boundary |
| --- | --- |
| `apps/openmw/mwworld/esmstore.cpp` | Full ESM3 dispatcher and StoreTuple, native setup/ID index; Lua config data remapping; also unrelated ESM4 loader and gameplay spell-list service in the same TU. |
| `cellstore.cpp`, `cellreflist.hpp` | Genuine unloaded/preloaded/loaded mutable reference lifecycle, containers, ownership, moved objects, restocking and saved state. Preloading is not a replacement for loaded LiveCellRefs. |
| `livecellref.cpp`, `refdata.cpp`, `class.cpp` | Construction calls genuine `Class::get(type)`; data ownership includes scripts, inventory/stats and WorldModel registration/deregistration. A null/fabricated Class or MWBase service would violate this boundary. |
| `worldmodel.cpp`, `cells.cpp`, `scene.cpp` | World/cell ownership and activation through real World, Player, CellPreloader, RenderingManager, PhysicsSystem and navigator. These are not interchangeable with the current const reference snapshots. |
| `mwphysics/physicssystem.cpp`, `actor.cpp`, `movementsolver.cpp` | Genuine collision/movement requires live Ptr/Class/creature state and task scheduling; using only Bullet collision shapes does not constitute this integration. |
| `mwrender/animation.cpp`, `npcanimation.cpp`, `mwmechanics/character.cpp` | Animation resources, skeleton/controller state, sound/text keys, inventory/equipment and actor mechanics are linked behavior, not simply a NIF render flag. |
| `engine.cpp`, `mwinput`, `mwwindow`, `mwsound`, `mwlua` | Full application startup adds SDL/platform event/window assumptions, MyGUI, OpenAL, Lua scheduling, settings/content configuration, save/filesystem paths and game services. UIKit/EGL owns the working iOS context; desktop window/context creation cannot be allowed to replace it. |

Local full-ESMStore linkage exposed actual unresolved ESM4 readers and SpellList
service dependencies. The selected component omits only those two API definitions
and supplies the real Lua configuration/serialization implementation and stock
Lua interpreter. No upstream source was edited and no undefined symbol was
silenced. `LuaState`'s scheduler/sandbox is not constructed; four independent
helpers referenced by genuine serialization retain their upstream bodies.
The native Lua target uses the upstream `LUA_USE_IOS` configuration: its OS
library provides Lua's own iOS behavior for the unavailable C `system()` call.
The Apple preflight rejects a missing/conflicting flag. No Lua source overlay,
fabricated OS API, JIT or gameplay scheduler is introduced. Standard libraries
are compiled as part of the genuine runtime, but are not opened by this component.

The functioning component and private-world tests establish a useful ESMStore
boundary. They do not establish that full CellStore or the above application
closure compiles or operates on Apple platforms. Source inspection identifies
those remaining dependencies; no successful full-CellStore runtime test is claimed.

## Next integration sequence

1. Validate this content-store migration on macOS and iPhoneOS, then on the same
   private iPhone installation. Confirm original scenes, transitions and resource
   bounds remain intact; confirm KHR labeling without hiding other messages.
2. Introduce genuine WorldModel/Cells/CellStore and real Class registration as one
   coherent mutable-object ownership slice. Resolve required genuine mechanics,
   Lua and container dependencies together. Do not fake MWBase services merely to
   link. Bind scene identities to live Ptrs, preserve refnum/load-order semantics,
   and add unloading/script/ownership regressions before actor activation.
3. Replace experimental movement with real PhysicsSystem/Actor/movement solver
   tied to a real player/live reference. Integrate genuine character/animation
   state and navigation support; keep controller input mapped to engine actions.
4. Converge streamed publication/preloading on MWWorld::Scene/CellPreloader and
   genuine RenderingManager/Terrain::World lifecycle. Retain external UIKit/EGL
   ownership and the working single GLES3 provider. Engine integration must
   preserve bounded resident cells, cancellation, shader acceptance, lifetime and
   diagnostics rather than loading the entire world.
5. Integrate true environment/water/sky/weather and gameplay services with their
   data dependencies. Test official expansions and an explicit multi-file mod
   profile before claiming compatibility. Tamriel Rebuilt/Tamriel_Data require
   actual load-order, resources, distant/streamed-cell and actor/gameplay testing.

The temporary APIs should shrink as genuine ownership moves inward. No parallel
inventory, quest, script, actor or savegame implementation is proposed.

## Performance and appearance

ESMStore retains more metadata than G4's selected tables. Private Windows timing
is recorded as CPU wall time, not an iPhone prediction; Apple memory/startup and
thermal impact must be measured. The safety prepass reads metadata twice to keep
unsupported CELL/LAND deletions explicit. No game asset copy, duplicate world
scene, JIT, speculative terrain-pass reduction or brightness adjustment is added.

The 418 genuine terrain passes are retained. Existing peak physical footprint,
active/peak neighborhood counts, preparation/commit latency, cache activity,
frame callback intervals and physics diagnostics remain available. Callback
frequency is not GPU/display FPS. GPU timers/fences and representative thermal
testing remain necessary for broader performance claims.

For pale geometry, compare the same camera, clear-day lighting/fog, alpha-tested
foliage and NIF material/texture state against desktop OpenMW. Current fog can
make distant geometry pale against a differently colored background, but this is
an inference, not a complete diagnosis. Preserve driver messages and capture
state before proposing material changes.
