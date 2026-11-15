# G3: original Seyda Neen exterior and controller traversal

Source-review implementation based on physically accepted G2 commit
`e9b44ef693ee0cd0580db83326d7bf63555ce960`. No G3 native CI, IPA or physical
acceptance is claimed. [G2 completion](G2-COMPLETION.md) records its narrower
accepted scope and the evidence inspected locally.

## Real content chosen

The first bounded area contains nine original exterior cells: X=-3..-1,
Y=-10..-8, centered on Seyda Neen (-2,-9). A read-only private survey compared
all nine cells: reference counts are 164/180/243 in the western column,
207/316/231 in the town column, and 140/218/150 in the eastern column. The
center contains the town buildings; the southern town cell includes the dock
area. The nine-cell region provides useful traversal space without claiming
world streaming. These are genuine CELL grids and positions, not arranged demos.

Private-content inventory, confirmed by the genuine supplemental Windows CPU
G3 harness as well as the diagnostic inspection (not iPhoneOS execution):

| Quantity | CPU result |
| --- | ---: |
| CELL references before classification | 1,849 |
| Static renderable placed instances | 1,679 |
| Distinct rendered NIF resources | 179 |
| Instanced model vertices / triangles / shapes | 372,710 / 345,898 / 6,385 |
| LAND vertices / triangles | 38,025 / 73,728 |
| Height range, game units | -1,456 to 3,104 |
| Maximum adjacent height discrepancy | 0 |
| Zero LAND normals in selected cells | 0 |
| Terrain textures in selected VTEX records | 19 |
| Terrain textures including actual blend borders | 20 |
| VFS-resolved DDS texture resources | 184 |
| Expanded RGBA bytes | 21,361,664 |
| Bullet collision objects, including terrain | 920 |

The exact CPU runtime inventory is VFS resolved; its RGBA expansion is about
20.4 MiB. The diagnostic survey also examines textures outside visible branches
and is not the authority for an exact runtime texture count. An additional terrain
material occurs on the sampled border; the 19-texture cell-only count must not
be used as an exact runtime texture inventory. All actual sampled terrain IDs resolve to original LTEX;
the wider halo has ID zero, but the samples used by these nine chunks do not.

The genuine CPU harness loaded all selected assets, confirmed arrival grounding
on original collision, and ran 1,200 fixed simulation steps including a short
forward probe. The observed three-dimensional displacement was about 909 game
units. This is not a controller-input, visual, framerate or iPhone test. Private
input hashes match the accepted G2 exports before and after the run.

Explicit omissions are counted, never replaced by synthetic content: three
chimney smoke instances, one fire, two log-pile effects, one animated silt
strider, 30 editor markers, and non-static base-record classes such as actors
and leveled lists. Every other unexpected/missing base, mesh, material, image,
controller or terrain requirement fails loading with context. Smoke and fire
are omitted as complete resources, so their associated log geometry is also
absent. The scene is a bounded static exterior, not a complete town simulation.

## Reused architecture

- Genuine `ESM::Cell`, `CellRef`, `Land`, `LandTexture` and base-record readers.
  `Land::getLandData` performs upstream VHGT delta decoding and VTEX transpose.
  Only the base master is supported; plugins/moved references require ESMStore.
- Shared accepted BSA/VFS access and owned model/image/sampler caches. Original
  NIF geometry, hierarchy, normals, UVs and ESM transforms remain authoritative.
- Unchanged `Terrain::BufferCache` supplies diamond triangle topology. Both
  render geometry and Bullet terrain meshes consume those exact indices.
  `ESMTerrain::sampleBlendmaps` supplies the genuine neighbor sampling; doubled
  masks and the blend-coordinate transform follow upstream terrain material
  conventions. Original textures repeat 16 times per cell. The selected height
  seams are checked; no invented skirts hide mismatches. Normal/color seam repair
  from the complete ESMTerrain storage is not integrated yet.
- Unchanged `NifBullet::BulletNifLoader` chooses original collision branches and
  marker semantics. `Resource::makeInstance` owns per-instance shape transforms
  while keeping source mesh data alive. NC/NCC visual/camera-only collision does
  not block the player capsule. No render-mesh approximation replaces NIF collision.
- Existing pinned Bullet 3.25, double precision, now links BulletDynamics as
  well as BulletCollision/LinearMath. A Z-up capsule uses Bullet's kinematic
  controller, fixed 120 Hz steps, a 250 ms/30-step frame catch-up bound, gravity, bounded
  slopes, steps and grounded jumps. This is **not** OpenMW's full character movement
  solver: swimming, moving platforms, combat, actor interaction, save state,
  skill-dependent movement and full gameplay are absent.
- One existing OSG/OpenThreads GLES3 viewer provider, seven viewer libraries,
  genuine generated headers, ANGLE/Metal and accepted external EGL ownership.
  No GLES2/OpenGLES provider or dependency revision change is introduced.
- Actual `SceneUtil::Material` and unchanged upstream material GLSL functions
  provide ambient, diffuse, emissive and vertex-color semantics. This addresses
  the original mushrooms, podplants and lantern that fail G2's no-emission gate.
  VER_MW specular remains disabled, matching NifOsg::Loader. Inheritance, alpha
  testing/blending, culling, winding and depth retain accepted strict handling.

`tools/mesh_bridge.py` remains an explicitly temporary integration seam. It
derives a build-directory copy from the hash-locked accepted G2 converter and
substitutes material binding only, with exact anchor counts. It does not edit
G1D, G2 or upstream source. It retains all structural, budget, image, ownership
and unsupported-feature gates. This is not presented as upstream SceneManager.

The next architectural step should integrate ResourceSystem/SceneManager and
NifOsg::Loader, ESMStore/CellStore plus Terrain::World and OpenMW PhysicsSystem
through a platform seam around the working EGL/OSG viewer. Those systems carry
resource/shader/controller, async-task, settings, world-object and actor-state
contracts; pulling in isolated rendering-manager methods would hide dependencies.
G3 already moves terrain topology, sampling, collision loading and material state
onto genuine reusable components. Do not grow this bridge into a second gameplay
engine. Door/world streaming and actor support should drive that integration.

## Lighting comparison

Accepted G2 is unchanged. Its point lighting uses `(1-distance/radius)^2`, a
single baked diffuse/vertex color and CELL ambient. Desktop OpenMW's
`files/shaders/lib/light/util.glsl` uses inverse constant/linear/quadratic
attenuation plus configurable radius fading. `components/sceneutil/lightutil.cpp`
derives coefficients from fallback/settings. NifOsg and the material shader
separate ambient/diffuse/emission; G2 cannot represent those completely. Desktop
vertex/per-pixel lighting settings also affect appearance. These differences
provide concrete causes for material brightness differences; G2 was not
arbitrarily brightened.

G3 fixes the material separation and uses a documented deterministic daylight
preset: ambient .35 RGB, white directional diffuse .65, normalized world sun
direction (.3,-.4,.8660254). It is not a weather/time-of-day recreation or a
photometric match to desktop OpenMW. Exterior point-light illumination is not
enabled in this daytime scope, although static lamp models render. A matched
desktop/iPhone camera and settings comparison remains unperformed; no local
desktop installation/reference capture was found. Fog, shadows, sky/weather,
animated water, underwater rendering and full lighting fidelity are unimplemented.
Coastal terrain is genuine, but there is currently no ocean water surface or
swimming barrier; underwater walking remains an experimental limitation.

## Controller-first operation

Install over the existing app using the same signing identity and the unchanged
bundle ID `org.openmw.experiments.real-model`. Existing `Documents/Model` files
and private two-file SHA manifest are reused; no game-data transfer or deletion
is required by the source change. Back up private files before any manual install.

- Physical extended gamepad: left stick walks/strafe; right stick looks; A jumps;
  Y toggles diagnostic status. There is no trigger-based flight.
- Normal controller gameplay hides the diagnostic overlay, status bar and home
  indicator where iOS permits. No virtual joysticks or touch movement buttons exist.
- CADisplayLink requests a 30–60 Hz range with 60 preferred. This is a scheduling
  request, not measured or accepted display FPS.
- Single tap toggles diagnostics; double tap resets to the genuine door-derived
  exterior arrival. When no supported gamepad is connected, recovery/status is
  visible and movement input becomes zero. Camera navigation requires a controller.
- Resign-active clears input and time history; reconnection primes button edges
  so a held A does not cause an accidental jump. These code paths still need
  physical controller disconnect/reconnect/background testing.
- The loaded nine-cell boundary and extreme falls reset to the arrival point;
  this is explicit recovery, not seamless world streaming or game death logic.

Arrival comes from the original interior teleport door's exterior DODT. Exterior
door destination records are parsed, validated and counted. Runtime door
activation/interior transitions are deliberately not implemented: consistent
scene/physics/light ownership during transitions should use the broader scene
integration, not an ad hoc swap of unrelated rendering demonstrations.

## Memory, performance and evidence

Hashing/ESM/NIF/DDS/terrain/Bullet preparation stays on the existing background
worker. EGL, viewer creation and GPU uploads stay on the main thread. Both private
files are streamed through SHA-256 before and after loading. Resource limits remain
64 MiB decoded RGBA, 128 MiB estimated sampler storage, 256 models, 4096 references
and two million placed model triangles. Repeated geometry/images/samplers are
shared. Collision instances share source mesh buffers. The nine-cell region is
retained as one bounded scene; no LOD/streaming or cache eviction is claimed.

`g3-render.json/log` bind the current source and dependency provenance to original
resource inventories and input hashes. They add terrain counts, exclusions,
collision counts/steps/grounding, load time, last OSG traversal wall time, display
callback interval mean/max/slow samples, process physical footprint and iOS thermal
state. Callback intervals are not measured display FPS or GPU completion. The
actual-display-FPS field stays null; physical rendering acceptance stays UNVERIFIED.
Memory/thermal observations are diagnostics, not sustained stability acceptance.

Native Build #1 preparation corrects the original 50 ms cap: at 10 rendering
frames/second it advanced only half the elapsed time, slowing both walking and
camera turning. Native cadence regressions now verify normal elapsed-time
movement and turning at 60/30/20/10/5/4 rendering frames/second. Catch-up still
has a hard 30-step budget; below 4 frames/second or after a long active stall,
excess wall time is deliberately dropped and counted in `physics_dropped_seconds`.
This protects against unbounded work and large movement jumps, not every
possible scheduling delay. Suspend resets the navigation clock, so actual
background time is never accumulated on resume. Moving to OpenMW's complete
character/world update architecture remains the longer-term direction.

## CI and validation

The new manual-only `.github/workflows/ios-openmw-exterior-device.yml` retains
G2's source/provenance and framework SDK preflight, accepted G1D/G2 host suites,
genuine parser/geometry tests, single-provider checks and strict package reopening.
It adds G3 host cases and a Mach/thermal/controller SDK compile/link probe before
Bullet/ANGLE acquisition. No iPhoneOS product is executed on the host. Current
source and workflow hashes are bound into the executable and exact public bundle.
The configured audit checks new OpenMW/G3 consumers, one OSG provider and
BulletDynamics's ARM64/SDK/double-precision configuration. Failure diagnostics
include compile commands, linker command files, generated bridge and CMake logs.

Build #1 preparation strengthens that audit to all translation units in all
three Bullet libraries, comparing double-precision definitions, compiler,
architecture, target and SDK options with the actual physics consumer. The
macOS host gate requires native ARM64; the iPhoneOS gate requires the selected
device SDK. The optional Windows CPU provider runs the same consistency audit
before compilation. No source/dependency pin or accepted provider source changed.
The authored multi-texture native fixture uses two local materials and a third
material present only in neighboring LAND samples: 23 passes across nine chunks.
It verifies all doubled mask samples, decoded DDS colors, shared genuine topology,
pass ordering and blend/depth semantics; a missing neighbor-only LTEX must fail.

The existing same-run ANGLE package transfer is independently revalidated against
the selected iPhoneOS SDK on restore. Cross-run caches are not added in this first
G3 implementation. Safe future ANGLE cache keys must include exact source/tool
pins, all build/overlay inputs and flags, architecture, platform, deployment,
compiler/Xcode and SDK identity; no partial restore keys. Revalidate inventories,
hashes, Mach-O and current SDK stubs on every hit, preserve regression gates and
regenerate current app provenance. OSG caches additionally need configuration and
generated-header ABI identity. Never reuse an old application as proof of current
source. Further device-provider build consolidation should keep each accepted
gate reviewable rather than drop checks to reduce duration.

Local checks and their exact scope are in REVIEW.md and the review ZIP's
validation evidence. Native harnesses use only deterministic self-authored
CELL/LAND/NIF/DDS/BSA fixtures. The C++ suite covers genuine decoding, reference
placement/cache ownership, terrain topology/collision, gravity/wall collision,
NC/NCC semantics, bounded resume, material modes and strict negative failures.
CI never opens the private installation. Original game files, source placement
arrays, NIF bytes and texture pixels are excluded from source and public artifacts.

An optional reproducible `tools/windows_cpu.py` builds the supplemental CPU
harness from supplied verified Zig/Ninja/CMake tools, pinned OSG and the existing
verified Bullet acquisition. It assembles the accepted source closure with the
unchanged upstream Windows file adapter in place of POSIX file I/O; it does not
override the accepted providers' macOS guard or edit upstream source. Original
parser/OSG/Bullet code executes locally, without an EGL context or renderer. This
desktop test provider may use local OSG DLLs; none is eligible for iOS packaging.
The Apple workflow still builds its required single static GLES3 provider. Run
the script with `--help` for its explicit tool/dependency/output paths. It performs
no downloads or installations. The private-data probe can then invoke the built
`g3-windows.exe` with the local Data Files directory, using streamed input hashes
before and after as in the retained review evidence. Do not upload original data.

After independent source approval: commit only the reviewed G3 additions, push
normally to ios-port, dispatch the new workflow once, return the SHA and run URL
immediately without polling. Review native evidence before signing/installing.
Physical acceptance then requires recognizable terrain/architecture/vegetation,
original textures, stable grounding/wall/step/slope behavior, responsive gamepad
look/move/jump, safe disconnection/recovery, uncluttered gameplay, unchanged input
hashes and exported diagnostics corroborated by video. Shader linking or swaps
alone cannot satisfy that acceptance.

## Primary sources

Local pinned source is authoritative for compilation. Official upstream research:
[ESM terrain storage](https://github.com/OpenMW/openmw/blob/master/components/esmterrain/storage.cpp),
[NIF collision loading](https://github.com/OpenMW/openmw/blob/master/components/nifbullet/bulletnifloader.cpp),
[OpenMW lighting settings](https://openmw.readthedocs.io/en/stable/reference/modding/settings/shaders.html),
[Bullet 3.25 character controller](https://github.com/bulletphysics/bullet3/blob/3.25/src/BulletDynamics/Character/btKinematicCharacterController.h).
