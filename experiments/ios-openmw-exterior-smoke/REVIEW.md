# G3 source review handoff

Base: `e9b44ef693ee0cd0580db83326d7bf63555ce960`, branch `ios-port`.
G2's physical acceptance is recorded separately in G2-COMPLETION.md. The original
source-review handoff was uncommitted. Independent review subsequently authorized
the contained corrections below and Native Build #1 publication/dispatch.
Native and physical G3 results must be reviewed separately. No original game
assets are included.

The implementation prepares a real nine-cell Seyda Neen exterior, genuine LAND
terrain and original static objects, material emission, original NIF collision,
grounded Bullet traversal and a controller-first application. README.md explains
the component reuse, limits, dependencies, private import and device acceptance.

Independent source review approved the original archive. Native Build #1
preparation then added a three-material authored terrain case (including a
neighbor-only material and strict missing-neighbor rejection), corrected slow
movement below 20 rendering frames/second with bounded 250 ms/30-step catch-up,
and audited all three Bullet libraries' actual precision/platform compilation.
The early Apple preflights, accepted regression suites and exact package gates
remain mandatory. These contained corrections are authorized for publication;
no runtime iPhoneOS or physical G3 acceptance is implied.

## Validation

| Check | Result |
| --- | --- |
| G3 Python regressions | 16 passed |
| Preserved G2/G1D/G1C/G1B/G1A/G0C/G0B Python suites | 190 passed |
| Supplemental Windows CPU build | compiled and linked with genuine pinned OSG/OpenThreads, Bullet and OpenMW code |
| Authored native G3 cases | 33 passed: 14 positive, 19 specifically matched rejections |
| Genuine private exterior on Windows CPU | PASS: 9 cells, 1,679 instances, 179 models, 184 DDS resources |
| Original LAND/model geometry | 73,728 terrain triangles; 345,898 model triangles; 372,710 model vertices; 6,385 shapes |
| Original collision | 920 collision objects; 768 model instances classified as nonblocking for the actor |
| Arrival grounding / short movement probe | PASS on Windows CPU; no visual/controller claim |
| Original game input hashes | unchanged and match accepted G2 exports |
| GLES300 shader syntax and cross-stage linkage | PASS with portable Khronos glslang; no GPU execution |
| Python syntax, workflow Bash/embedded Python, whitespace | PASS |
| Source/provider/fixture audits | PASS; all 53 A–E entries and accepted F/G0B fixtures/pins retained |
| Raw preservation snapshots | all 310 pre-existing experiment files unchanged, including all nine Build #15 files |
| G3 macOS ARM64 / Apple SDK preflight / iPhoneOS build / IPA | UNVERIFIED; manual CI required |
| G3 physical rendering, controller response and performance | UNVERIFIED; independent iPhone evidence required |

The optional Windows build is reproducible through `tools/windows_cpu.py`, with
supplied portable Zig 0.14.1, Ninja 1.13.1, CMake 4.2.1 and existing verified
dependency inputs. Zig's official archive SHA-256 was
`554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c`.
No tools were installed system-wide. The Windows harness uses upstream Windows
file I/O and a supplemental desktop OSG provider; it is not the Apple application
or a substitute for its static GLES3/ANGLE gates. The original G1A macOS-only guard
and all accepted providers remain unchanged. Review evidence contains CPU outputs,
the generated local build recipe, compiler logs and the binary hash; no binaries,
dependencies, original placement arrays, NIFs or texture pixels are distributed.

The native positive cases include sloped terrain, upstream scale clamping,
missing optional colors, deleted references, emission, inherited/overridden
emission, vertex emission, emission-only lighting, SrcIgnore and vertex-color
fallback. They exercise actual uniform values after parser/VFS release, shared
terrain/model DDS caching, collision geometry, gravity, grounding, jumping,
wall rejection, NC/NCC handling and bounded resume. Native negative cases require
specific expected failures; crashes and unrelated ordinary failures cannot pass.
The Python suite also exercises the actual package validator and IPA reopening,
rejecting game-file injection, macOS platform metadata and missing provenance.

## Remaining limits and review focus

- Review the experimental generated mesh bridge and its exact locked anchors.
  Full ResourceSystem/SceneManager/NifOsg integration remains the intended direction.
- Review multipass terrain blending, coordinate conventions and color/normal
  boundary appearance on iPhone; visual texture orientation is not CPU acceptance.
- Review the kinematic capsule as an initial traversal mechanism. It does not
  implement OpenMW's complete movement, collision response or gameplay systems.
- No actors, particle smoke/fire, animated silt strider, weather, ocean surface,
  swimming, collision streaming or runtime door transitions. Doors supply real
  arrival/destination metadata, not a claim that teleport activation is implemented.
- Daylight is a documented deterministic preset. G2 vs desktop lighting was
  compared in source; a matched desktop/iPhone visual comparison remains open.
- GPU uploads remain on the main thread. First-frame latency, controller pairing,
  disconnection/reconnection, resume, frame pacing, memory and thermal behavior
  require physical profiling. A requested 60 Hz schedule is not measured FPS.

Keep the current application ID and signing identity when updating, so the
already imported `Documents/Model` files remain available. After source approval,
stage only this inventory, commit/push normally and dispatch
`ios-openmw-exterior-device.yml` once. Return its SHA/run URL immediately; do not
wait for or poll CI. Native and physical acceptance must be reviewed separately.

## Exact source additions

The ZIP preserves these repository-relative paths. Additional `review-evidence/`
members are validation material only, not repository additions. SHA256SUMS.json
independently inventories every archive member except itself.

<!-- source-inventory-start -->

33 new source/documentation/workflow files:

- `.github/workflows/ios-openmw-exterior-device.yml`
- `experiments/ios-openmw-exterior-smoke/.gitignore`
- `experiments/ios-openmw-exterior-smoke/accepted-source-lock.json`
- `experiments/ios-openmw-exterior-smoke/CMakeLists.txt`
- `experiments/ios-openmw-exterior-smoke/common.cmake`
- `experiments/ios-openmw-exterior-smoke/device/CMakeLists.txt`
- `experiments/ios-openmw-exterior-smoke/device/Info.plist.in`
- `experiments/ios-openmw-exterior-smoke/device/src/main.mm`
- `experiments/ios-openmw-exterior-smoke/device/src/OSGScene.hpp`
- `experiments/ios-openmw-exterior-smoke/G2-COMPLETION.md`
- `experiments/ios-openmw-exterior-smoke/README.md`
- `experiments/ios-openmw-exterior-smoke/REVIEW.md`
- `experiments/ios-openmw-exterior-smoke/src/Exterior.cpp`
- `experiments/ios-openmw-exterior-smoke/src/Exterior.hpp`
- `experiments/ios-openmw-exterior-smoke/src/Material.hpp`
- `experiments/ios-openmw-exterior-smoke/src/Physics.cpp`
- `experiments/ios-openmw-exterior-smoke/src/Physics.hpp`
- `experiments/ios-openmw-exterior-smoke/src/Terrain.cpp`
- `experiments/ios-openmw-exterior-smoke/src/TerrainCoordinates.hpp`
- `experiments/ios-openmw-exterior-smoke/src/Traversal.hpp`
- `experiments/ios-openmw-exterior-smoke/tests/diagnostics_probe.mm`
- `experiments/ios-openmw-exterior-smoke/tests/exterior_check.cpp`
- `experiments/ios-openmw-exterior-smoke/tools/device_sdk_check.py`
- `experiments/ios-openmw-exterior-smoke/tools/fixtures.py`
- `experiments/ios-openmw-exterior-smoke/tools/inspect_exterior.py`
- `experiments/ios-openmw-exterior-smoke/tools/mesh_bridge.py`
- `experiments/ios-openmw-exterior-smoke/tools/package.py`
- `experiments/ios-openmw-exterior-smoke/tools/paths.py`
- `experiments/ios-openmw-exterior-smoke/tools/provenance.py`
- `experiments/ios-openmw-exterior-smoke/tools/run_cases.py`
- `experiments/ios-openmw-exterior-smoke/tools/test_g3.py`
- `experiments/ios-openmw-exterior-smoke/tools/validate.py`
- `experiments/ios-openmw-exterior-smoke/tools/windows_cpu.py`

<!-- source-inventory-end -->
