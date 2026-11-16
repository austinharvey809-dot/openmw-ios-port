# Component boundary and genuine engine reuse

## Ownership and rendering

The pinned engine's ESMStore remains the authoritative typed content store.
G6's checked namespace projection retains G5's content ordering and setup;
its old snapshot reference-merging API is absent. A real `WorldModel` owns
real `CellStore` objects, which load genuine typed `LiveCellRef` lists using
the original reference override, deletion and moved-reference logic.
All genuine MWClass implementations are registered; fake Class registrations
or empty World/LuaManager services are not supplied.

The public adapter exposes value snapshots and `{RefNum, epoch}` handles, not
unowned engine pointers. Lookup goes through the real WorldModel registry.
Foreign and retired handles fail. Position changes use RefData's effective
position; moves call genuine `CellStore::moveTo` and update the real registry.
Disable, nonzero count and pose changes survive scene graph retirement and
cache maintenance. Actual content-file deletion remains supported. Runtime
deletion is rejected before mutation until genuine World script cleanup exists.

Scoped real `MWBase::Environment` bindings provide only ESMStore/WorldModel.
A process-wide mutex serializes all G6 operations that touch that singleton,
including destruction; final LiveCellRef deregistration happens while its
registry and content store still exist. The upstream environment is global,
not thread-local. This isolated component must not be run concurrently with
another application's independently installed Environment. Integrating the
full application will replace these scoped bindings with its real lifetime.

The existing renderer consumes live CellStore snapshots through the same
WorldIndex boundary. Its Resources, genuine NifOsg loader, SceneManager,
TerrainGrid, shader setup, Bullet shape resources, controller input and
streaming coordinator are mechanically reused. A hash-checked generated view
changes the namespace, index binding, settings-resource path and diagnostics.
It does not substitute authored geometry for original models. Genuine typed
CellStore traversal changes enumeration order; private comparisons establish
the same door multiset and scene counts as G5, not identical door ordering.

## Failure and memory boundaries

Limits are 128 loaded or quarantined data cells, 131,072 raw references per
cell and 524,288 total reserved raw references. Genuine codecs scan without
building another reference vector before typed allocation. Reservations stay
charged after partial failures, and failed cells are quarantined. Missing or
unsupported typed bases and swallowed upstream loading errors become explicit
failures in an isolated source projection; incomplete cells cannot pass.
Duplicate live reference identities cannot silently replace registry entries.

GPU/scene resources retain the accepted bounded neighborhood/cache behavior.
Live CellStores retain mutable state like upstream; they are not silently
evicted when their scene is retired. Exceeding the data budget explicitly
fails. Whole-session `clear()` invalidates handles and retires all data. This
is bounded operation, not arbitrary unlimited exploration or savegame support.
A real persistence-backed eviction policy belongs with the full world lifecycle.

## Required dependency closure

The real MWClass vtables reach mechanics, actor stats, animation, physics,
Lua and UI helpers even when the public slice only manipulates ownership.
G6 builds these genuine implementations instead of resolving them with stubs.
`engine-lock.json` binds 340 original/G5 inputs, 166 direct translation units
and ten checked projections. The core target contains 180 translation units.
Projected helper methods are original implementations; omitted application
entry points are absent and will fail to link if accidentally requested.
`Player::update` is not a fabricated no-op. The full genuine LuaState is built,
avoiding duplicate helper definitions from G5's narrower ESMStore target.

New source preparations are SDL 2.32.10 headers, the existing upstream Detour
revision, ICU 70.1 common/i18n with complete official little-endian data, and
FreeType 2.13.3. Exact pins, hashes, sizes and official URLs are recorded in
`dependencies.json`. Original G4 MyGUI, Lua, OSG and Bullet pins stay unchanged.
The 97 genuine MyGUI units share an isolated header view replacing unsupported
`basic_string<uint32_t/uint16_t>` aliases with `char32_t/char16_t`. Every consumer
uses that view before original headers; mixing a prebuilt MyGUI ABI is forbidden.
The original header remains hash-verified and unchanged. Native UTF-8/16/32,
surrogate and ICU French formatting tests exercise this boundary.

ICU includes 438 genuine common/i18n units plus its 29,466,000-byte official
data image compiled into a target archive. This increases executable/dependency
build size; actual Apple binary size, loading cost and device footprint remain
unmeasured. No empty ICU data or locale-function replacement is used. FreeType's
optional compressed-font codecs are disabled; game image plugins are unchanged.
SDL runtime/window creation is not introduced by the header dependency. ANGLE
still owns external EGL/Metal presentation. Bullet remains double precision.

CMake configures dependencies requiring `add_subdirectory`/ASM before deferred
G5/G6 target attachment. FreeType variables and MyGUI inventory variables are
function-scoped to avoid altering the accepted OSG/Bullet configuration.
Unchanged generated source/header bytes are not rewritten during configure.
The two-phase shared-provider configuration and standalone Windows build were
both audited; Apple execution remains a separate gate.

## Full Scene and character integration

Unchanged `MWWorld::Scene` compiles against the new real dependency closure.
It is not linked or instantiated: its lifecycle requires concrete
`MWWorld::World`, `MWRender::RenderingManager`, LuaManager, mechanics, scripts,
sound/window interfaces and player/actor services. Scene activation performs
these real side effects; simply calling it behind empty services is unsafe.
The count-zero crash demonstrates one such dependency concretely.

`MWRender::Objects` also cannot simply replace the coordinator's parallel
candidate graphs. Each live reference owns one RefData base node; attaching
overlapping candidate and active scenes could cause retiring the old scene
to clear the new scene's node. The next integration should introduce genuine
diff/commit activation with one authoritative world/service lifetime, then
genuine character physics, controller/animation updates and Lua lifecycle.
Actor references already have genuine typed ownership and class identity;
rendering, AI, animation and player physics execution are not implemented here.

Ordered original expansions were inspected locally. Tamriel Rebuilt,
Tamriel_Data, arbitrary ESPs and dense modded neighborhoods remain untested.
ESM4 loading, savegames, scripting/gameplay, water/swimming, weather, actors
and complete engine compatibility remain outside the demonstrated slice.

## Pale distant geometry

The genuine pinned `MWRender::FogManager` is compiled and exercised against
the preserved clear-day profile. Source behavior matches start 2539.52,
end 8192 and color RGB 206/227/255. Linear fog contributions are approximately
0 at 2048, 0.275362 at 4096, 0.637681 at 6144 and 1 at 8192. Authored no-fog
and interior-density cases also pass. Pale distant surfaces are therefore
consistent with one existing fog contribution, but no device pixel correlation
establishes this as the physical root cause. Materials, alpha and lighting
still require image-based comparison against desktop OpenMW. No speculative
brightness, shader or texture changes were made.
