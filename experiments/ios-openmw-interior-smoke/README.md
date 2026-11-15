# G2 — original Morrowind interior, source review implementation

Prepared on `ios-port`, unchanged HEAD
`a70ab5a7c8974245b205826ab748d86a79a53b1e`.
G1D Build #2 is physically accepted **within its original static-model scope**;
see [the completion record](../../docs/ios-port/g1d-completion.md). That acceptance
does not establish G2 native execution, physical rendering or gameplay.
Independent source review has approved native Build #1, including the preparation
corrections below. Native CI results and physical acceptance require separate review.

## Chosen original environment

The target is **Seyda Neen, Fargoth's House**, read from the user's legitimate
base `Morrowind.esm` and `Morrowind.bsa`. The application reads original CELL,
base-object and reference records; no original mesh, texture or placement array
is compiled into the application or copied to public source/artifacts.

Four interiors were inspected read-only using bounded TES3/BSA/NIF metadata
diagnostics. Those diagnostics are not replacements for native OpenMW parsing.

| Candidate | Placed references | Distinct model paths | Decision |
| --- | ---: | ---: | --- |
| Fargoth's House | 46 | 28 including editor marker | Selected: furnished Nordic room, fewer mesh variants, no actors |
| Indrele Rathryon's Shack | 37 | 31 | Fewer placements but more distinct meshes and lantern variations |
| Fine-Mouth's Shack | 31 | 27 | Includes an NPC/beast skeleton outside this static scope |
| Caius Cosades' House | 57 | 42 | More record classes and an NPC requiring actor/body-part assembly |

Counts of model paths do not account for separate actor assembly resources.
The selected CELL contains one DOOR, 24 MISC, nine CONT, four LIGH, seven STAT
and one ACTI. The ACTI is the editor north marker, not furniture. Two lights
have no mesh. The resulting static scene is expected to contain:

- **43 model instances, 27 distinct meshes, 91 shape instances**.
- **7,589 instanced vertices and 7,057 triangles**, excluding collision meshes,
  editor geometry, hidden geometry and particle effects.
- **39 original DDS textures**, approximately 2.58 MiB / 2,703,360 bytes of
  shared decoded RGBA base images; generated mipmaps add GPU storage.
- The genuine `in_nord_house_01` room shell, load door and door frame, bed,
  bench, shelf, table, window, cupboards, barrels, baskets, sacks, bottles,
  tankards, cups, broom, bucket, pillow and candle bodies in their ESM positions.
- Four original placed lights: ordinary candle, blue candle, blue light bulb
  and **negative** `dark_64_01`. The two candle flicker modes are explicitly frozen.
- Sixteen collision-branch instances excluded from rendering, four particle
  branches explicitly omitted, one editor north marker excluded, two model-less
  lights still contributing illumination.

These are read-only diagnostic expectations, **not a genuine native G2 PASS**.
The native harness and device exports must independently confirm the counts.
`artifacts/private-content-summary.json` records candidate summaries, per-model
counts/hashes and texture format/dimension/hash metadata, without game bytes or
original placement arrays. Original inputs were rehashed against the existing
private transfer manifest; they are unchanged. Every selected non-marker model
was consumed completely by the sequential diagnostic layout walker. Its visible
geometry has finite attributes, valid indices, one UV set and nondegenerate
triangles; visible materials use supported base-texture treatments.

## Architecture and implemented compatibility

`src/Interior.cpp` uses genuine `ESM::Cell::load`, `ESM::Cell::getNextRef` and
`ESM::CellRef` processing, plus genuine Static, Activator, Container, Door,
Miscellaneous and Light base-record loaders. Deleted references are tracked;
duplicate IDs/reference numbers, missing bases, unprocessed data, moved refs,
water/quasi-exterior cells and unsupported base classes fail explicitly.
This deliberately supports a single standalone base master, not plugin merges.

Reference matrices use OpenMW's non-actor quaternion convention: negative X,
negative Y, negative Z rotations, with reference scale and translation. The
genuine CellRef reader supplies its existing 0.5–2.0 scale clamping; nonfinite
results fail. NIF hierarchy transforms remain intact underneath each placement.
The north marker controls editor/map information and is not drawn or used to
rotate all CELL coordinates.

One `Resources` object opens/indexes the BSA/VFS for the whole load. Mesh
templates are cached by normalized resource path and shared below independent
reference transforms. OpenMW's GenericObjectCache shares owned decoded images;
texture objects are additionally shared by resource/filter/wrap combination.
This avoids per-reference ESM scans, BSA re-indexing, repeated NIF decoding,
repeated RGBA expansion and unnecessary repeated GPU texture objects.

`tools/bridge.py` derives a G2-only mesh converter from the **accepted G1D
source**, checked by exact LF SHA-256 and exact replacement-anchor counts.
It adds a shared resource context, explicit collision/effect policy, normals
validation, texture budgets/caching and original `AttachLight` transforms.
It does not edit completed G1D, upstream OpenMW or OSG sources. The generated
`MeshBridge.cpp` is an ordinary C++ build input, retained as review/failure
evidence. Genuine Nif::Reader, ResourceHelpers DDS preference, OSG image decoding,
owned arrays, G1D property validation, depth/alpha/culling and material semantics
remain in use. No hardcoded mesh or original texture fallback exists.

Actual cell inspection identified and addressed related blockers together:

1. `RootCollisionNode` meshes must not appear as visible surfaces. They are
   excluded with exported counters, matching the upstream loader's render policy.
2. The north marker is excluded as editor content. Its untextured/emissive NIF
   does not masquerade as a furnishing or force a fake material fallback.
3. Candles have renderable bodies and separate NiBSParticleNode branches.
   The bodies are rendered; four effect branches are omitted and counted.
   **Flames, particle animation and exact flame appearance are not implemented.**
4. Two lamps have genuine `AttachLight` nodes. Their original NIF-local light
   offsets are composed with ESM placement rather than guessed from the pivot.
5. The negative light subtracts illumination. A regression case preserves its
   sign; it is not silently converted into a positive light or dropped.

Basic GLES3 lighting uses CELL ambient RGB, original normals, original placed
light RGB/radius and a finite-radius Lambert contribution. Negative contributions
are subtracted and the final illumination is bounded below by zero. Eight active
lights are supported. This is a **static lighting approximation**, not OpenMW's
complete lighting, fog, shadow, attenuation, color-space or flicker pipeline.
Original diffuse/vertex colors, alpha tests/blending and texture sampling remain
active. Specular remains disabled for MW as in the accepted property helper.
Emission materials, animated visible controllers, skinning and unsupported
properties still fail with cell/base/model and NIF processing context.

The source closure reuses the existing single pinned OSG/OpenThreads ANGLE
GLES3 viewer provider, generated headers, seven-library viewer closure, Bullet
3.25 precision/pin, static DDS/TGA plugins and Apple framework linkage. Seven
additional original ESM translation units supply CELL/reference/base loaders;
their hashes are locked. No dependency revision, source overlay or global
configuration is changed. G2 protects its parent CMake C++ flags from legacy
OSG cache changes, retains C++20 and audits actual compile commands.

## Direction toward full OpenMW integration

Upstream [Resource::SceneManager](https://github.com/OpenMW/openmw/blob/master/components/resource/scenemanager.cpp)
and [NifOsg::Loader](https://github.com/OpenMW/openmw/blob/master/components/nifosg/nifloader.cpp)
were compared with the local source. Template reuse and AttachLight composition
follow that architecture; collision branches remain render-hidden. Placement
follows local `apps/openmw/mwrender/renderingmanager.cpp`.

This experiment **does not claim to use the full NifOsg loader or SceneManager**.
Their material/shader, animation, particle, serializer and resource-system
closure is not already linked by the accepted GLES3 provider. Importing those
pieces without matching the GLES3 shader/lifecycle contracts would be a separate
integration change. The resource facade and template/instance boundary are
intended to be replaced by ResourceSystem/SceneManager, not grow into a second
general-purpose engine. Do not expand the bridge with actor/animation/particle
systems; next integrate the upstream loader/resource/shader closure for those.

## Navigation, lifecycle and private input reuse

The initial camera is derived from a genuine placed teleport door and computed
room bounds, at inspection eye height facing inward. No furnishing positions
are adjusted to fit a demonstration. The camera is free-fly, with no collision
or player/gameplay simulation:

- Controller left stick: move; right stick: look; triggers: down/up.
- A: reset to the derived entry; Y: clear/restore the scene.
- Touch drag: look; hold Left/Forward/Back/Right/Up/Down buttons: move;
  double tap: reset. Movement is normalized, pitch limited and elapsed time
  capped; suspend resets inputs/timing to avoid a long resume movement jump.

The existing external EGL/Metal owner, single swap, frame logging and UIKit
pause/resume path are reused. G2 exports `g2-render.json/log`, exact cell/model/
texture inventories, geometry/cache/light/effect counts, source binding, input
integrity, camera pose, scene-load wall time and actual OSG/shader/EGL counters.
GPU completion, physical visibility and lifecycle acceptance remain UNVERIFIED.

**No new game-data transfer or app deletion is required by the design.** The
application keeps `org.openmw.experiments.real-model` and reads the existing
`Documents/Model/Morrowind.esm`, `Morrowind.bsa` and schema-1 private manifest.
It reuses the old manifest's file hashes; its old rug object_id field is not a
G2 cell selector. Hashes are checked before and after loading. The G2 binary/app
name is IOSOpenMWInterior, but bundle identity stays the same. Retain the same
signing team/application identifier and update-install over the existing app;
do not delete it. Actual container retention must still be verified through the
manual signing/install process. Back up private files locally before updating.

## Validation and handoff

Build #3 dependency audit: UIKit supplies views/gestures/constraints;
Foundation and CoreFoundation supply object/runtime/metadata services;
CoreGraphics owns CGPointZero and geometry APIs; QuartzCore supplies CAMetalLayer;
Metal supplies the graphics backend; GameController supplies controller input.
GCD, CommonCrypto, POSIX and C++ runtime services use the system runtime;
EGL/GLES use the existing verified ANGLE libraries. G1A::sha256 is supplied by
the explicitly linked accepted g1b-geometry target. These dependencies were
audited against G2's imports and API calls; no additional provider is introduced.
`device/frameworks.json` is now the explicit application framework inventory.
CoreGraphics is imported and linked directly instead of relying on UIKit's
transitive dependencies. Packaging's existing selected-iPhoneOS-SDK dependency
checks already accept legitimate CoreGraphics and remain unchanged.

An early SDK-only Objective-C++ ARM64 link probe consumes that same inventory
before Bullet or ANGLE acquisition. It references CGPointZero, UIKit/Foundation,
CoreFoundation, CAMetalLayer, Metal, controller, GCD and CommonCrypto APIs, then
inspects the executable and every system dependency against the selected SDK.
It never executes a device binary on the host and is not a substitute for the
full app compile/link, configured-provider audit, packaging or native tests.
Its compiler/linker diagnostics are retained even on failure.

Future safe acceleration: reuse an ANGLE dependency package only with an exact
key covering pinned ANGLE/depot_tools revisions, build flags, ARM64/iPhoneOS
platform, deployment target, Xcode/compiler and SDK identity. Require its
inventory/checksums and rerun the existing dependency validator against the
current selected SDK on every restore; reject stale/mismatched cache entries.
Regenerate current-commit app/source provenance and retain all regression and
packaging gates. OSG/generated headers need equivalent ABI/configuration keys.
This build does not add cross-run caches or trust prior application binaries;
the early SDK probe provides a contained improvement without a cache redesign.

Build #1 preparation addresses the independent review observations:

- The unchanged accepted G1D native harness is explicitly compiled beside G2
  in the existing `g2-host-build`, sharing its OSG/provider/dependency targets.
  Its original CTest suite runs from `g2-host-build/provider` with no-tests=error;
  its Python regressions also remain mandatory. No third dependency build is added.
- Missing-mesh and malformed-CELL cases now require their precise original
  VFS/ESM error messages. Empty rejection contracts fail closed; unrelated ordinary
  errors, crashes and zero-exit outcomes cannot satisfy a negative case.
- Hashing both original inputs twice reads roughly 780 MB, in addition to cell
  parsing and image decoding. That synchronous main-thread work was a concrete
  watchdog/responsiveness risk. One utility worker now performs streaming hashes
  and CPU-only preparation into a private report. Main-thread completion transfers
  the owned scene, merges diagnostics, and attaches EGL/viewer state only while
  active. The worker never mutates the live UI/evidence dictionary. A session
  identity guard discards stale completions; inactive scenes defer attachment.
  CPU preparation uses an autorelease pool and existing resource budgets. Both
  pre/post hash checks remain mandatory; total startup wall time is exported.
- The generated bridge remains an experimental, locked integration mechanism;
  the long-term ResourceSystem/SceneManager/NifOsg direction above is unchanged.

The asynchronous loading/foreground transitions are source-checked locally, not
executed on Apple hardware. GPU setup/uploads and first-frame latency still need
device profiling. Background preparation is not a claim of watchdog or memory
acceptance on the iPhone, and does not bypass any hash or parser gate.

**Passed locally:** 31 G2 Python tests; syntax parsing for all new Python tools;
deterministic/distinct authored fixtures; bounded framing, collision/effect and
signed-light diagnostics; strict configured-build validator positive/negative
cases; false-PASS rejection; source/fixture/provenance audits; workflow Bash and
embedded Python syntax; ESSL 300 vertex/fragment syntax and cross-stage linking
with Khronos glslang; Git and new-file whitespace checks. The shader validator
does not execute ANGLE or a GPU.

**Prepared, unexecuted:** 28 genuine native cases (seven positive, 21 negative).
They use self-authored ESM/CELL/base/reference/NIF/DDS inputs. The C++ harness
checks ownership after VFS/parser release, reference counts, matrix convention,
shared mesh/image/texture caches (including two distinct NIF paths), collision
and particle counters, signed lights, camera movement/reset/time bounds and
strict PASS/FAIL. Negative cases cover missing cells/bases/models/assets,
duplicate IDs/references, nonfinite placement/scale, unsupported properties and
emission, invalid indices/images/CELL data, no entry, missing normals, water
cells and light budgets. Public CI never mounts or loads the private game data.

No suitable local C++/Apple toolchain is available; WSL is not installed.
Native C++ compilation/linking/execution, private original-cell execution,
iPhoneOS executable inspection, complete bundle/IPA validation and physical
G2 rendering are **unverified**, not passed. Controller/touch behavior, initial
camera framing, actual lighting appearance, startup/watchdog cost, GPU memory,
frame performance and lifecycle recovery require device evaluation. The
64 MiB decoded-image, 128 MiB conservative texture-storage estimate, 128-model,
512-reference, two-million vertex/triangle and
eight-light budgets fail explicitly instead of partially loading a room.

The new manual-only workflow is
`.github/workflows/ios-openmw-interior-device.yml`. It retains baseline source,
dependency, host geometry/parser and packaging gates, then builds and executes
G2 authored native cases, configures one iPhoneOS ARM64 GLES3 provider, audits
the actual G2 compile commands, builds UIKit, checks the Mach-O dependency graph,
enforces exact public bundle inventory/provenance and independently reopens the
unsigned IPA. Failure logs, compile commands and generated bridge are retained.
The public G2 IPA contains executable, public frameworks/licenses/provenance
and g2-build.json only, never original assets or the private manifest.

Preservation: all 305 snapshotted existing tracked milestone/document/workflow
files and the dirty Build #15 working-tree bytes are unchanged. Source audits
also check all 53 A–E entries, F/G0B sources, fixtures, pinned OSG and the nine
Build #15 hashes. G1D acceptance is documented separately without editing its
accepted code. Original ESM/BSA hashes match the existing private manifest.
Initial source-review preparation performed no publication. Build #1 publication
and dispatch are now authorized; native results remain unverified at preparation.

Review the complete source ZIP, inventory, generated bridge and validation
evidence first. After approval, publish only the listed additions and launch
the manual workflow; return its commit/run URL immediately without polling.
After native success, sign/update-install the IPA over G1D, retain private
Documents/Model, navigate the original room and review exported evidence plus
screenshots/recording. Require all 43 mesh instances and unchanged input hashes;
verify room shell/furnishings/textures from inside and multiple angles. Explicitly
record omitted flames/static flicker and free-fly limitations. Do not claim
physical G2 acceptance or gameplay before that independent device review.
