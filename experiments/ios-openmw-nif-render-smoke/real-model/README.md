# G1D: original Morrowind static model, private runtime content

Prepared 2026-11-14 on `ios-port`, base `7de7ac7a85f6bd616ceaff2362d8c10c03623125`.
G1C physical textured rendering is complete **as independently verified and
reported by the user**. This new slice does not change that implementation.
G1D native compilation, genuine parsing of the private model and phone rendering
are **unverified**. No build was dispatched, staged, committed or pushed here.

## Selected real target and inspected dependencies

Read-only inspection of the user's Steam installation on A: selected the base
`Morrowind.esm` STAT `furn_de_rug_02`, referring to
`meshes/f/furn_rug_02.nif` in the original `Morrowind.bsa`.
The model is 1,103 bytes, SHA-256
`b61c28bfa7e45d8d91cf82da72396c66d8bac32effbd6bf38f1d8aaf1b6b8534`.
Bounded layout inspection found six core record types: NiNode, NiTriShape,
NiTriShapeData, NiTexturingProperty, NiSourceTexture, NiMaterialProperty;
12 vertices, 12 triangles, 36 indices, normals and one UV set. These are
**diagnostic layout findings, not claimed results from the genuine C++ reader**.
The material's diffuse is (1,1,1), alpha 1, specular/emissive zero, gloss zero.

Its `Tx_rug_02.tga` reference resolves through OpenMW's DDS preference to
`textures/tx_rug_02.dds`: 256x128 DXT3, 43,776 bytes, SHA-256
`5044dee54dffa5ebb5022a7e10d6e8ec1834e31d2850a45fe45658be55f455d8`.
This is a recognizable original static object with real triangles, thickness
and an original compressed texture, rather than a fabricated replacement mesh.
Loose mod files are intentionally excluded from the first experiment.

## Implementation and architectural choice

`StaticModel.cpp` scans the real ESM using ESMReader/Static::load, registers the
original BSA through the completed archive/VFS adapter, calls genuine Nif::Reader,
and recursively converts supported static NiNodes/NiTriShapes. It uses
`NiTransform::toMatrix()` for row/column conversion, preserves hierarchy and
inherited material/base-texture state, copies arbitrary indexed triangle/UV
arrays and normals, and retains owned OSG scene/image objects after parsing.
It guards cycles, invalid indices, nonfinite positions/UV/transforms, missing
images and unsupported features. Mirrored transforms select the proper winding.

Texture lookup uses genuine ResourceHelpers and GenericObjectCache. The pinned
OSG DDS plugin is added alongside the existing static TGA reader. RGBA expansion
uses OSG Image::getColor/setColor, following OpenMW ImageManager's software
decompression mechanism; no device BC/S3TC extension is assumed. DDS/TGA origin
handling follows ImageManager's top-left convention. A real DDS must decode;
there is no warning texture or synthetic geometry fallback.

This remains an **opaque, unlit diffuse/base-texture slice**: no lighting,
specular/emissive materials, alpha blending, animation, skinning, extra texture
layers, strips, vertex colors or special node types are claimed. Unsupported
features fail explicitly. Linear base-level sampling is deliberate; original
mip chains/filter modes and full game lighting are not yet reproduced.

The full upstream [NifOsg::Loader](https://github.com/OpenMW/openmw/blob/master/components/nifosg/nifloader.cpp)
and local ImageManager/SceneManager were inspected. The full loader includes
YAML serialization, particles, animation/skeleton/morph/rig and shader/material
systems. ImageManager statically registers multiple image/object serializers.
Importing that whole closure for this one opaque static target would introduce
new libraries and substantial shader integration. This adapter reuses genuine
reader, transform, resource lookup/cache and pinned image decoding now; it does
not pretend to be the full NifOsg loader. Later support should converge on that
architecture rather than grow a competing general-purpose renderer.

The separate CMake roots reuse the completed G1C provider once per binary.
No OpenMW/OSG/Bullet source or dependency pin is changed. The new UIKit app
reuses the immutable external EGL owner and shader ABI, computes world bounds
and automatically orbits with Z-up, allowing inspection around the real model.
It exports `g1d-render.json/log`; those results retain external physical
acceptance as UNVERIFIED. Presented FPS/GPU completion are not inferred.

## Private transfer: original assets never enter public builds

`tools/assets.py --installation <Morrowind> --output <private-directory>`
creates a **new directory outside both repository and installation**. It copies
only the original `Morrowind.esm` and `Morrowind.bsa` plus a hash/selection
manifest. Existing destinations are rejected. Source and copied hashes are
compared before/after; the installation is never written. This first version
transfers about 390 MB rather than rebuilding proprietary BSA/ESM subsets.
It preserves original STAT associations and archive texture resolution.

A verified private copy was prepared locally at
`%TEMP%/OpenMW-G1D-Private-20261114`. **Do not upload that folder or commit it.**
The review ZIP contains source and metadata only, not those files.

After an independently reviewed native build:

1. Sign/install `IOSOpenMWRealModel-unsigned.ipa` using the existing manual process.
2. Use your local USB/Files transfer method to copy the private folder's three
   files into this app's `Documents/Model/`. If desktop file sharing only adds
   files at Documents root, use the iPhone Files app to create `Model` and move
   just those three files into it. No public server or CI upload is involved.
3. Close/relaunch the app after import. Missing content shows a failure; it does
   not substitute a demo. Startup hashes the two files, parses/loads the selected
   STAT and checks the hashes again. The manifest binds the user's local data;
   it is not a claim of Bethesda-signed authenticity.
4. Observe the original rug and DDS texture through a full camera orbit. Check
   orientation, thickness, winding, clear/restore and background/resume.
5. Export recording/screenshot plus unchanged `g1d-render.json/log` privately.
   Correlate session, build/source hashes and decoded counts. Only that review
   can establish physical rendering acceptance.

The public app contains frameworks, licenses, dependency/build provenance and
executable only. The packager requires that exact inventory, rejects additional
asset resources, checks the actual selected SDK using preserved primitives,
and reopens the IPA. Real assets are imported afterward into Documents.

## Validation and native handoff

Local: seven Python policy/fixture tests pass; all new Python files parse.
Self-authored fixture generation is deterministic. Workflow Bash/Python syntax
checks and Git whitespace pass. Completed sources and all nine dirty Build #15
files are preserved; original ESM/BSA copy/content hashes match after export.

Not executed locally: C++ host compilation, genuine parsing of either the new
fixtures or real rug, DDS CPU decompression in the new adapter, iPhoneOS
compilation/linking, new bundle/IPA checks or device rendering. The available
Windows environment has Python and portable CMake but no suitable Apple C++
toolchain. These are **unverified**, not passed.

The host CMake root builds `openmw-real-model-check`. `ctest -R '^g1d-' -V`
requires a self-authored seven-record/two-triangle hierarchy with a translated
child and DXT3 texture, checks world bounds and owned decoded pixels, and rejects
cycles, nonfinite transforms, bad indices, unsafe paths, missing images and bad
DDS. These native tests are prepared but unexecuted. Public fixtures are generated
from source; no original game bytes are used in reproducible tests.

Private native command, after building on a suitable host:
`openmw-real-model-check <private-directory> furn_de_rug_02`.
Expected inspected counts are 12 vertices/12 triangles/one shape; genuine native
output must independently confirm them, without changing expectations to hide
an error. This private command and its assets must stay outside public CI.

`.github/workflows/ios-openmw-real-model-device.yml` is manual-only. It retains
G1C baseline gates and adds G1D host tests, app compilation and strict public-only
packaging. This first review version builds baseline and G1D separately, with
one compatible provider in each executable, at extra compile cost. Compiler and
packager logs go to the native evidence artifact. No private-data step exists.
On a future authorized dispatch, return the run link immediately; do not watch
or poll the long-running build. Native CI must pass before any IPA is accepted.
