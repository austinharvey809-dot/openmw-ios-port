# Architecture and upstream integration

## What actually executes

The explicit source closure in `engine-sources.json` contains 194 entries,
including the unmodified upstream units and accepted BSA registration adapter.
It adds a platform file implementation and six G4 coordination units. The accepted G3 character controller
is reused. Upstream source/header/shader hashes and accepted G3 consumer hashes
are locked independently in `accepted-source-lock.json` (560 files).

| Responsibility | Actual provider |
| --- | --- |
| Content/master mappings | ESM::ESMReader, ReadersCache, genuine record codecs |
| CELL/LAND/LTEX and static bases | MWWorld::Store specializations in the genuine store.cpp |
| Resource precedence | VFS::Manager, genuine BSA adapter, FileSystemArchive |
| NIF parsing and scene creation | ResourceSystem → SceneManager → NifOsg::Loader |
| Images and NIF lifetime | ImageManager, NifFileManager, actual pinned OSG readers |
| Model collision | Resource::BulletShapeManager → genuine NifBullet |
| Terrain sampling/topology/blending | ESMTerrain::Storage → Terrain::TerrainGrid |
| Lighting/material state | SceneUtil LightManager/LightUtil/Material and original GLSL |
| Presentation | One pinned OSG viewer closure → existing external EGL → ANGLE/Metal |
| Platform coordination | New Session, Area, WorldIndex, InputProfile and UIKit shell |

No StaticModel, MeshBridge, WorldMesh or G1A/G1C geometry adapter is linked into
the G4 app. The old targets remain available solely for accepted regression
builds. G4's one OSG/OpenThreads provider includes the seven accepted viewer
libraries plus osgAnimation, osgParticle and osgShadow from the same revision.
The additional libraries are genuine loader dependencies, not a second provider.
All three Bullet libraries retain the verified 3.25 pin and double ABI.

## Ownership, streaming and threading

WorldIndex retains original CELL metadata and lazy reader contexts; it does
not load every reference or LAND height array at startup. Genuine Store<Cell>
handles moved-reference leases. RefNum identity includes content-file index;
plugin updates replace master references rather than producing duplicate roots.
The skipped-moved-record branch is handled explicitly before reading CellRef.
Missing/deleted bases reject; known unsupported record classes have counted
exclusions rather than masquerading as successfully rendered models.

One Resources owns VFS and upstream manager caches for the session. SceneManager
clones mutable scene instances while sharing templates, images and collision
shapes. The scene's upstream source hash must equal its parsed NIF hash;
marker_error and warning-image fallbacks cannot satisfy preparation. Real
ImageManager capabilities are initialized on the render thread before background
loads. Unsupported S3TC is decompressed by the genuine ImageManager when needed.

An Area owns a maximum nine-cell exterior neighborhood or one interior, scene
instances, LAND owners, terrain and physics. On crossing a center-cell boundary,
one worker stages the next neighborhood. The render thread publishes only a
complete result, then retires the old scene. At most two neighborhoods are live
during staging; the whole world is never instantiated. References per area,
content files and import counts have explicit bounds. This is a spatial bound,
not a hard byte budget or adaptive LOD system. High-resolution mod assets can
still exceed device memory; that remains a validation requirement.

The original pinned Terrain::World destructor does not delete its raw storage
pointer despite an older ownership comment. Area therefore owns TerrainStorage
explicitly and destroys TerrainGrid first. LAND arrays outlive heightfields.
Weak LAND cache entries avoid retaining the world's height arrays. Genuine
resource caches expire after five seconds; NIF parser cache delay remains zero.
Memory warnings request background cache cleanup. Active objects retain their
owners throughout cleanup. Image CPU data remains retained pending physical
context-loss validation.

Only one resource/index worker mutates managers at a time. Initial hashing and
loading stay off UIKit's main thread. The pinned OSG notify stream has a shared
string buffer, so all G4 OSG work (loading, maintenance, frames and retirement)
uses the existing recursive capability gate. The frame path tries the gate;
while busy it submits a clear-only loading frame and counts it separately.
This avoids main-thread waits and unsafe concurrent notification formatting;
it may show a temporary loading background, rather than the prior world image.
The notification sink uses atomic counters and serialized callbacks/closure;
file append operations and their failures are serialized too. Workers join
before context/session destruction and before restoring the previous handler.
OSG remains
single-threaded with external EGL ownership and one app swap per frame.
Backgrounding resets input and physics timing; no elapsed background simulation
is performed. The accepted 120 Hz, bounded 30-step/.25-second physics policy is
retained, with dropped-time diagnostics accumulated across scene replacement.

Replacement CPU preparation is provisional: the render thread compiles/links
the candidate's actual programs before changing the active root. Rejection
leaves the previous scene/physics active and allows B recovery. Shader success
is bound to an explicit accepted load number; initial failure resets success.
Context/GL faults still stop visibly.

Cache expiry uses viewer FrameStamp referenceTime, independently of animation
simulationTime and device uptime. Maintenance uses the same gate and one-worker
ownership; manager registry contents are fixed after session construction.
Statistics snapshots return with worker results rather than racing cache
mutation on the UI thread. Maintenance errors/counts are separate from scene
load failures and do not freeze navigation. Strong active-instance and LAND/
Bullet owners survive cache clearing and candidate/retired-scene destruction.

## Terrain and GLES3 adaptation

TerrainStorage supplies genuine LandObject data and per-plugin LTEX lookup to
ESMTerrain::Storage. Original normal/color sampling, neighboring texture samples,
blend weights, topology and multipass state are retained. Heightfields use the
same diamond subdivision and BulletHelpers height shift as the upstream path.

`prepare_shaders.py` generates separate platform copies of original object and
terrain shaders. Upstream files are never modified. GLES permits one shader
object per stage, so conditional @link modules are inlined after their interfaces.
The adapter maps compatibility builtins to OSG vertex/uniform bindings, emits
ESSL 300, guards duplicate uniforms, and makes the upstream integer truncation
explicit before float arithmetic. Material, lighting, fog and terrain arithmetic
remain upstream. All input/generated hashes are recorded.

The explicit profile has one color attachment, disableNormals=1, eight maximum
lights, no clustered compute, shadows, multiview, user clip planes, reflections
or postprocessing. Upstream terrain adds an inert indexed blend enable for the
unused normals attachment. GLES3Terrain copies pass state and omits **only**
Enablei(GL_BLEND,1); it preserves real color blending, depth, programs and
textures and rejects other indexed capability requirements. GL_ALPHA_TEST is
disabled as a fixed-function capability because the genuine ShaderVisitor
implements alpha comparison in GLSL. GL error checking remains enabled.

SceneAudit checks every drawable's inherited program and terrain pass, exact
vertex/fragment stage inventory and valid images. The real device then compiles
and links every actual program; source validation never counts as shader/GPU
execution. Generated source adaptation remains experimental until Apple/ANGLE
and physical images have been reviewed.

The original nine-cell inspection's 418 terrain passes are prepared inventory,
not measured visible per-frame draw calls. Genuine TerrainGrid splits each ESM3
cell into 4x4 chunks; each drawable submits original layer passes after culling.
Material blending/depth semantics are unchanged. Extra passes can cost CPU
submissions and fragment blending, but reducing layer coverage or changing
topology before profiling would be speculative. Inventory, preparation/commit
latency, traversal timing, cache counters and kernel/sample footprint peaks are
now exported. Profile the first device build before considering genuine
QuadtreeWorld/LOD integration.

## Lighting comparison with G2/G3

The accepted experimental renderer used a custom light formula, exterior ambient
0.35 and diffuse 0.65. Desktop OpenMW instead supplies a default inherited
SceneUtil::Material, LightManager sunlight/point lights, original NIF material
and vertex modes, and fog arithmetic. G4 supplies that genuine default material,
depth and culling state; missing inherited uniforms otherwise shade default
materials black because NifOsg omits redundant default material state.

The explicit clear-day baseline is derived from this source tree's
`files/openmw.cfg`: ambient RGB 137/140/160 and sunlight 255/252/238, with original
clear-day fog/sky values. Sun direction is deterministic, not a weather/time
simulation. Interiors use original CELL ambient/sunlight/fog and genuine light
attenuation helpers; off-default lights remain off. These source differences
explain why arbitrary brightness boosts would be unjustified. No desktop OpenMW
screenshot comparison or iPhone lighting-fidelity acceptance has been performed.

## Moddability and the engine boundary

Ordered content, true parent-file mapping, distinct plugin RefNums, moved/deleted
references, plugin terrain palettes, shared VFS and loose-file precedence are
foundational for expansions and Tamriel Rebuilt. Authored native cases test these
boundaries. Original Tribunal/Bloodmoon/Tamriel_Data/Tamriel Rebuilt packs were
not exercised; modern material/shader combinations and giant textures remain
uncertified. ESM3 only, at most 254 content files; deleted CELL/LAND are rejected.

Full ESMStore, CellStore, MWWorld::Scene, World, PhysicsSystem, SkyManager and
WeatherManager are not compiled into this isolated target. Their actual source
interfaces couple mutable object state, MWBase::Environment services, actor
classes, scripting/Lua, mechanics, gameplay activation and save-state handling.
Pulling those in piecemeal and stubbing services would undermine genuine-engine
semantics. This task integrates reusable upstream lower layers directly and
keeps the remaining coordinator deliberately small.

Next convergence should introduce genuine ESMStore/CellStore state and engine
scene lifecycle behind real platform services, then genuine actor/character
physics and activation. Adapt Terrain::World/QuadtreeWorld, Water/Sky/Weather
with their real rendering prerequisites. Avoid implementing inventory, AI,
weather, scripts or a new physics engine inside Session. Water levels are
currently metadata only; water drawing/swimming are explicitly unimplemented.
Actors, leveled lists and inventory-class placements are counted/excluded;
static STAT/ACTI/CONT/DOOR/LIGH/MISC scenes render without gameplay simulation.

## Provenance and CI

New dependencies are exact-source yaml-cpp (the upstream OpenMW revision), MyGUI
headers only, Boost headers/program_options, zlib, libpng and libjpeg-turbo.
Existing OSG/ANGLE/Bullet pins and overlays are untouched. Six genuine OSG image
plugins and genuine osg serializers are compiled; there are no registration
stubs or substitute image decoders. JPEG builds in its required separate CMake
project without installation, carrying the actual Apple platform/sysroot flags.

The manual workflow retains all accepted host suites and independent iPhoneOS
executable/bundle/IPA checks. Framework preflight runs before ANGLE; the new
configured-consumer preflight syntax-compiles real new source using the actual
Apple compiler, SDK, architecture and generated headers before the long G4
library build. Only SHA-512-reverified source ZIPs are cached. Reusing binary
artifacts would require binding source, overlay, options, toolchain/SDK and
inventories and is deliberately deferred.

Primary architecture references are the checked-out unmodified
`components/resource/`, `components/nifosg/nifloader.cpp`, `apps/openmw/mwworld/`,
`components/esmterrain/`, `components/terrain/` and
`apps/openmw/mwrender/renderingmanager.cpp`. User data organization follows
[OpenMW paths](https://openmw.readthedocs.io/en/latest/reference/modding/paths.html).
