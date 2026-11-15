# G4 genuine world integration foundation

## Build #3 GLES serializer and native coverage

Build #2 passed JPEG configuration, real dependency archive validation and the
consumer preflight, then failed compiling BufferIndexBinding.cpp: GLES3/gl3.h
does not expose GL_BUFFER, while the selected ANGLE gl2ext.h exposes the
identical Khronos GL_BUFFER_KHR value 0x82E0. The serializer macro consumes a
numeric default, not the token spelling. Only this translation unit receives
GL_BUFFER=GL_BUFFER_KHR; no API, upstream source or serialization value changes.
The pinned source/semantic anchor and both ANGLE token declarations are checked
before configuring the alias. No desktop GL or GLES3.2 header replaces the
selected GLES3 headers. The gl32.h declaration is read only to verify equality.

The complete new OSG source inventory is locked: 137 serializers, eight image
plugin units and 76 units in osgAnimation/osgParticle/osgShadow (221 total).
Every unit compiled locally against genuine CMake-generated GLES3 headers and
the exact pinned ANGLE headers. The original failure reproduced without the
alias; no second compile incompatibility appeared. This supplemental Windows
object audit does not establish Apple linking or runtime support for every
serialized object/capability.

Native preflight now builds the actual new targets, validates every resulting
ARM64/iPhoneOS object and performs a real static-registration link probe. Those
same objects are reused in the final G4 application build, avoiding a duplicate
syntax-only pass over 221 files. The probe forces all genuine reader/serializer
registration symbols. A host runtime check verifies reader discovery and the
BufferIndexBinding.Target serializer. The modern osg2 reader, already compiled
in the plugin archive, now has an explicit static reference in the application
so the linker cannot discard it. Genuine image implementations are retained.

ANGLE package reuse uses an exact cache key containing the complete ANGLE source
recipe tree, Xcode, SDK version/build, compiler, host/architecture and runner
image. There are no fallback keys. Cache hits must pass the saved exact inventory
and digests before SDK validation can refresh diagnostics; recorded toolchain,
pins, GN configuration, symbols, device platform and dependencies are rechecked.
The first cache miss still builds ANGLE normally. Existing source ZIP caches
remain hash-verified. The separate accepted baseline build tree is retained;
merging its path-sensitive provenance contracts is deferred rather than weakened.

Local results: 39 Python tests, all 221 GLES3 source objects, genuine host
registration linking/runtime, retained 41 CPU regressions and preservation
checks. All Apple linking, final app/IPA and physical G4 gates remain separate
and unverified until their tests execute. No performance mods or G5 work.

## Build #2 JPEG cross-compilation correction

Build #1 reached G4 application compilation but failed while configuring the
genuine pinned libjpeg-turbo ExternalProject. With CMAKE_SYSTEM_NAME=iOS,
CMake expects the caller to provide the processor; it can remain empty despite
CMAKE_OSX_ARCHITECTURES=arm64. The old conditional forwarding omitted that empty
value, and upstream's unquoted string(TOLOWER ...) lost an argument.

The JPEG recipe now derives CMAKE_SYSTEM_PROCESSOR=arm64 from the explicit
single ARM64 iPhoneOS target and rejects conflicting processor/SDK/architecture
settings. It preserves the selected SDK, deployment target 18.0, compiler,
archive tools, static linking and original dependency pins. Host processor
selection is retained for genuine host regression builds.

The native preflight now runs before either application's compilation. It
configures the real JPEG ExternalProject first, then builds JPEG, yaml-cpp,
zlib, portable libpng and Boost program_options. These other dependencies use
the parent toolchain; MyGUI is headers-only and is checked through consumer
compilation. The gate checks actual JPEG cache/system/compile settings and all
new dependency compiler commands, then independently examines every static
archive member for thin ARM64 MH_OBJECT and iPhoneOS 18.0 LC_BUILD_VERSION.
Host, simulator, universal, missing-platform and malformed objects fail. Final
executable, bundle and IPA checks are retained independently.

Local validation: 35 Python tests, including actual CMake argument forwarding
with an empty target processor and an unrelated host CPU; real pinned JPEG
Windows configuration/build; and a real cross-Clang authored ARM64/iOS object
archive accepted by the inspector. Actual Apple-built dependency archives and
the complete G4 application remain unverified until Build #2 executes. No G4
physical, full-engine or mod compatibility acceptance is inferred.

Status: independent source review conditionally approved; focused corrections
and supplemental Windows CPU validation completed for authorized native Build #1.
G4 iPhoneOS compilation, IPA packaging, GPU rendering and physical acceptance
remain **UNVERIFIED**. [G3 remains physically accepted](G3-COMPLETION.md).

This experiment replaces the temporary model/terrain mesh bridge with genuine
OpenMW ResourceSystem, SceneManager, NifOsg::Loader, ImageManager,
BulletShapeManager, ESM store specializations and Terrain::TerrainGrid. It
streams a bounded exterior neighborhood and follows original unlocked door
destinations. It is a substantial integration foundation, not completion of
every G4 objective or a playable engine.

- [Architecture, lighting comparison and integration boundaries](ARCHITECTURE.md)
- [Validation and remaining acceptance work](VALIDATION.md)
- [Exact review inventory](REVIEW.md)

## Private data and installation continuity

The application retains `org.openmw.experiments.real-model`, file sharing and
the existing `Documents/Model` directory. Install over the accepted G3 app;
do not delete it. Existing `Morrowind.esm`, `Morrowind.bsa` and schema-1
`manifest.json` work without retransferring game data. Their SHA-256 values are
checked before and after initial preparation, off the UIKit main thread.

An optional private `Documents/Model/world-profile.json` selects ordered
ESM/ESP files, BSA archives and loose directories. Generate metadata locally:

```powershell
python tools/private_profile.py --data-dir 'D:/Private/MorrowindImport' `
  --content Morrowind.esm --content Tribunal.esm --content Bloodmoon.esm `
  --archive Morrowind.bsa --archive Tribunal.bsa --archive Bloodmoon.bsa `
  --loose Loose --output 'D:/Private/Transfer/world-profile.json'
```

The tool writes hashes and ordered names only, outside the original
installation. Copy selected files and that profile privately into the existing
app's `Documents/Model`, preserving relative paths. Use local Apple file
sharing or the same private transfer method already used for G1D–G3. CI and
the public IPA contain no game data or private profile. Do not add either to
Git or public build artifacts. The generator rejects escapes, links, duplicate
content basenames and overlapping file inventories. The app independently
checks regular files, confinement, exact selected inventories and hashes.

Later content and archives override earlier ones; loose directories are
registered after archives. Genuine master mappings, moved references,
deletions and per-plugin LAND/LTEX indexing are retained. This is a necessary
mod architecture boundary, **not Tamriel Rebuilt/Tamriel_Data certification**.
Deleted CELL/LAND records, non-ESM3 content and unsupported gameplay classes
are explicit limitations. Missing bases and resource fallbacks fail visibly.

## Controls and runtime behavior

Left stick: grounded movement. Right stick: look. A: jump. X: activate a
nearby facing unlocked teleport door. B: recover to the committed area's
arrival position. Y: diagnostics. Basic taps toggle status; double tap recovers.
No virtual joystick or permanent touch movement overlay is provided. Normal
gameplay hides status when a controller is attached. Controller disconnect
sets movement axes to zero and exposes recovery information.

Initial hashing/indexing/scene loading runs on a worker after actual EGL/OSG
capabilities are initialized. OSG work is serialized because its pinned notify
stream is global. While the worker holds this gate, UIKit stays responsive and
the device submits separately counted clear-only loading frames, not OSG frames.
Translation freezes during a scene load; ordinary look resumes with rendering.
A failed replacement retains the old scene and reports its stage/destination.
Actual shader program acceptance occurs before publication. Initial acceptance
failure clears shader success and stops visibly; replacement rejection retains
the previously accepted scene and reports that scene's accepted load number.
Use B/double tap to recover; failed locations do not retry every frame.

The world starts at the genuine Fargoth return-door exterior destination.
The original Fargoth entrance is locked and is not bypassed. The nearby
Lighthouse is an unlocked first transition target. Door selection is currently
distance/facing based; collision occlusion, scripts, keys, lockpicking and
animated door activation are not implemented.

## Reproducible source builds

Use Python 3.11+, CMake 3.24+ and a suitable compiler. Dependency acquisition
uses normal TLS certificate verification, explicit official source URLs and
exact SHA-512 values. No system installation or upstream edits occur.

```bash
python3 tools/prepare_dependencies.py --output /tmp/g4-dependencies
cmake -S . -B /tmp/g4-host -G 'Unix Makefiles' \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release \
  -DOPENMW_ESM_OSG_SOURCE=/path/to/pinned-osg \
  -DG0_BULLET_SOURCE=/path/to/verified-bullet-3.25 \
  -DG4_DEPENDENCIES_SOURCE=/tmp/g4-dependencies \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build /tmp/g4-host --target openmw-world-check g4-device-headers --parallel 4
ctest --test-dir /tmp/g4-host -R '^g4-' --no-tests=error -V
python3 -B -m unittest discover -s tools -p test_g4.py -v
```

The default host build shares the accepted G3 OSG/Bullet provider and retains
the G1D/G2/G3 harnesses. The optional Windows CPU provider imports the already
audited desktop libraries; it is never an iPhoneOS provider. Apple builds use
the one pinned OSG ANGLE GLES3 provider, iPhoneOS ARM64 and double-precision
Bullet. Existing OSG, ANGLE and Bullet pins/checksums are unchanged. Six real
OSG image plugins support DDS/TGA/BMP/PNG/JPEG/OSG resources.

The new manual-only workflow is
`.github/workflows/ios-openmw-world-device.yml`. It retains accepted regressions,
Apple framework preflight, dependency verification, executable inspection,
exact public bundle validation, unsigned packaging and independent reopening.
It also syntax-compiles the actual new Objective-C++/C++ consumers against the
Apple SDK before the long library build. Only verified **source ZIPs** are
cached; every restore repeats archive hashes and extracted-source inventories.
No prebuilt binary cache is trusted. After a later approved dispatch, return
the run URL immediately; do not poll or wait for CI completion.

## Remaining objectives

Water levels are recorded but water rendering/swimming are unimplemented.
The environment uses original interior light data or a deterministic upstream
clear-day profile; there is no genuine dynamic sky/weather/time progression.
The accepted G3 experimental Bullet character controller remains; full upstream
character physics, actors, collision fidelity and gameplay are not established.
Full ESMStore/CellStore/MWWorld::Scene integration remains a deliberate next
architectural step. Do not add gameplay systems to this small coordinator.

Native Build #1 publication/dispatch is authorized after the review corrections.
Physical evidence
must demonstrate genuine rendering, streaming, transitions, controller behavior,
input integrity and resource/performance behavior before accepting G4.
