# G1B completion and the textured-resource slice

Recorded 2026-11-12 (America/Chicago). Branch `ios-port`; inspected HEAD
`b0e9ff8cd0e92d4c08a8200e16f5420e2cdd6d83`.

## G1B completion

G1B is complete for its synthetic decoded-triangle scope on the physical iPhone
16 Plus. These are distinct forms of evidence:

| Evidence | Finding and boundary |
| --- | --- |
| [Build #2, run 43341030144](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43341030144) | Independently inspected GitHub job results and native log: host regressions, ANGLE device validation, single-provider configuration, genuine parser/geometry and UIKit linking, SDK/bundle inspection, unsigned IPA and independent reopening succeeded at the commit above. CI did not run on the phone. |
| Independently reviewed recording and `g1b-render.json/log`, reported by the user | Session `3C1E5A1C-894F-45E8-BB22-291D20597F33`, source `b0e9ff8cd0e92d4c08a8200e16f5420e2cdd6d83`. Visible green synthetic NIF triangle, all six genuine parser cases passed, NIF-derived owned geometry, shader linked, 840 OSG frames, 887 successful EGL swaps, zero app-polled GL errors, input fixtures unchanged. The user identified the reviewed exports as `/mnt/data/g1b-render(1).json` and `/mnt/data/g1b-render(1).log`; those paths are review-environment paths, not repository files. The original recording/exports remain outside Git and are not rewritten. Export file digests were not provided and are not invented. |
| **USER-CONFIRMED DEVICE FUNCTIONAL TEST: clear toggle** | The triangle disappears in diagnostic-clear mode and returns afterward. The reviewed JSON's `clear_only: false` is a single snapshot, not independent measurement of the toggle transitions. |
| **USER-CONFIRMED DEVICE FUNCTIONAL TEST: background/resume** | The triangle continues rendering after leaving the app and returning. The export's `lifecycle_acceptance: null` does not independently measure this behavior. |
| Export's intentionally conservative acceptance fields | `physical_rendering_acceptance` remained UNVERIFIED pending external review. The independent visible-render review supplies corroboration; it does not justify editing that original field or treating it as an automatic PASS. |

Presented FPS, GPU-completion instrumentation and sustained performance are not
established. Swaps and app-polled GL errors are not those measurements. G1B does
not demonstrate real Morrowind models/scenes, textures, physics, UI or gameplay.
The original G1B preparation README remains historical; this report records its
subsequent completion without changing working implementation or exports.

## Chosen next increment: G1C textured resource slice

The new isolated `experiments/ios-openmw-nif-render-smoke/textured/` experiment
adds one self-authored 4.0.0.2 NIF with genuine UV, NiTexturingProperty,
NiSourceTexture and diffuse-material records; a deterministic uncompressed TGA;
and a synthetic ESM/BSA containing both model and image. It must obtain model
and texture through real OpenMW VFS, not bypass the archive with loose images.

The selected genuine engine resource components are
`Misc::ResourceHelpers::correctTexturePath` and
`Resource::GenericObjectCache<std::string, osg::ref_ptr<osg::Image>>`. The first
exercises Morrowind's normalization/prefix/DDS-preference rules, the second
provides real cache ownership, reuse and clearing. The pinned OSG TGA reader is
linked statically and registered explicitly. This adds one source-only image
decoder from the existing OSG revision, with no external image library or pin
update. The seven-library viewer and ANGLE Metal context owner remain the same.

`Resource::ImageManager` was inspected and deliberately deferred: its static
translation unit forces PNG/TGA/DDS/JPEG/BMP/OSG plus serializer registration,
and its GL-extension/compression/warning-image paths introduce a much larger
closure. Full NifOsg::Loader/SceneManager also imports material, animation and
shader systems beyond this gate. The selected helpers/cache are a real,
testable step into that resource path without pretending to be the full loader.

The first material is explicit unlit base-texture modulation. UVs, texture
reference, sampler policy and diffuse/alpha values must come from decoded NIF
records. Input/provenance hashes, exact source-to-owned values, resource/cache
behavior and rejection cases are separate host gates; native packaging and
physical texture visibility are later gates. Old G0/G1 fixtures and Build #15
remain untouched. No completed milestone is declared superseded or weakened.

## Deferred instrumentation

Presented-frame timing, GPU fences/timestamps, richer thermal/performance
sampling and a formally measured lifecycle-transition acceptance state belong
in separate focused work. Cheap session/toggle event logging may be useful,
but changing the accepted G1B telemetry while adding a texture would obscure
the new resource/rendering result. New exports keep measured facts and external
device acceptance separate; an API link or swap count never becomes visibility.

G1C implementation, validation results and the concrete device checklist are
recorded in its own README. G1C is not complete until its own native and physical
evidence supports that claim.
