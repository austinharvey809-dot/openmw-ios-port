# G1D original rug compatibility correction — source review

2026-11-14. Branch `ios-port`; unchanged base HEAD
`5a94bd5e7328141aa17111598d54fd386989c742`.
Initial review preparation performed no staging, commits, pushes, workflow
dispatches or device installation. Independent source review has since approved
publication and dispatch of native Build #2, including the edge-case correction below.

## Physical failure and identified cause

Read the original JSON, LOG and README in the user's
`Downloads/G1D-device-diagnostics-2026-11-14` directory (the supplied unsuffixed
path does not exist). Inspected extracted recording frames at 5 and 20 seconds.
The 20-second frame corroborates session prefix `714C5D18`, the property error,
zero OSG frames and an empty background. The JSON identifies full session
`714C5D18-819B-4988-BBA1-175F8E11D8C6`, that base commit, iPhone17,4/iOS 27.2,
`shader_linked=false`, `osg_frames=0`, 5,058 successful EGL swaps and zero
app-polled GL errors. The LOG contains multiple sessions; the relevant session
starts at 18:36:01 UTC and immediately logs the same error. EGL swaps do not
establish model rendering, shader execution or GPU completion.

Read the original model directly from the legitimate installation's BSA in
memory, without extracting original content into the repository. Sequential
bounded layout diagnostics consume all 1,103 bytes, validate all references
and account for all seven records:

| Index | Type | Relevant relationship/state |
| --- | --- | --- |
| 0 | NiNode | Child 1, no properties |
| 1 | NiTriShape | Properties **2, 3, 5**; geometry 6; no skin |
| 2 | **NiVertexColorProperty** | Flags 0, **SrcIgnore (0)**, EmiAmbDif (1) |
| 3 | NiTexturingProperty | **Hilight (3)**; base source 4; clamp 3; **filter 2**; UV 0 |
| 4 | NiSourceTexture | External `Tx_rug_02.tga` |
| 5 | NiMaterialProperty | Diffuse/ambient white, alpha 1, emission/specular/gloss zero |
| 6 | NiTriShapeData | 12 vertices, 12 triangles, 36 indices, normals, one UV set, no colors |

The first property visited is record 2. The old adapter accepts only material
and texturing properties, so it throws exactly the reported error there.
This identifies the failure without guessing a property from the generic message.
The old six-type metadata scan omitted this seventh record; it was not a complete
inventory. The diagnostic inspector now walks records rather than counting a
fixed selection of type-name strings. Production still exclusively uses genuine
`Nif::Reader`; Python layout checks are not native parser acceptance evidence.

## Other confirmed rug compatibility findings

After record 2, the old adapter would reject record 3's Hilight apply mode.
OpenMW's `NifOsg::Loader` passes this value to shader setup; its ShaderVisitor
only special-cases mode 4 for parallax. MW Hilight takes the ordinary diffuse-map
modulation path. The fix explicitly accepts Modulate and MW Hilight, and still
rejects other modes. It does not enable PS2 highlight or Oblivion parallax.

The original requests trilinear filtering. The old fixed LINEAR/base-level
sampler discarded this intent. Modes 0-5 now map to their actual nearest/linear
and mipmapped filters. CPU expansion continues to use pinned OSG's DDS decoder
and `Image::getColor/setColor`, as OpenMW ImageManager does. RGBA mips are
generated when requested; the source DDS's authored compressed mip chain is
not retained. This quality difference needs device review, not a claim of exact
pixel equivalence to desktop OpenMW.

The DDS resolves through genuine ResourceHelpers to `textures/tx_rug_02.dds`,
256x128 DXT3, 43,776 bytes. It has varying alpha and five stored mip levels.
The rug has **no alpha, stencil or depth property**. Alpha in the texture alone
must not invent transparency; blending and alpha testing remain off, depth
test/write are on, front faces are CCW and back-face culling remains on.
Layout checks found finite transforms/positions/normals/UVs, valid indices,
zero degenerate triangles, UV range approximately 0.0004995–0.9995005,
unit scales and only a tiny shape Z translation. No other current adapter
rejection was identified for this model. Actual revised native decoding and
display still need to confirm these findings.

Model SHA-256:
`b61c28bfa7e45d8d91cf82da72396c66d8bac32effbd6bf38f1d8aaf1b6b8534`.
DDS SHA-256:
`5044dee54dffa5ebb5022a7e10d6e8ec1834e31d2850a45fe45658be55f455d8`.
These are metadata, not copies of original assets.

## Reusable implementation and rendering semantics

`StaticProperties.hpp` holds effective inherited property pointers while the
genuine reader owns them. Traversal copies this state per branch; child values
replace the corresponding type and cannot mutate sibling state. Resulting
OSG attributes, colors, geometry and images remain independently owned after
the reader/VFS/cache are released. No parser or upstream source is changed.

- Vertex SrcIgnore keeps material diffuse/alpha even if a color array exists.
  SrcAmbDif uses the full vertex color instead of multiplying it by material
  diffuse. Without a color array, explicit SrcAmbDif falls back to white as
  OpenMW does. Default selection follows color-array presence. Invalid modes
  fail; emission modes remain explicitly unsupported by this unlit shader.
- MW specular is disabled as in upstream, even with NiSpecularProperty or a
  nonzero finite specular material value. Nonzero material emission is rejected.
  Finite/range checks remain; this is not full game lighting.
- NiZBufferProperty uses test/write flags, LEQUAL, or ALWAYS when writes are
  required without testing. Both disabled turns the test off. As in upstream,
  the encoded depth comparison field is deliberately not used.
- Disabled-stencil NiStencilProperty controls CCW/CW/both face modes. World
  transform parity still adjusts winding. Enabled stencil testing fails because
  the current EGL framebuffer has zero stencil bits. Invalid face modes fail.
- NiAlphaProperty supplies validated blend factors and optional depth sorting,
  honors no-sort, and retains independent depth flags. OpenMW's destination
  DST_ALPHA-to-ONE compatibility rule is preserved. GLES3 alpha testing uses
  the final sampled texture * color alpha and normalized threshold in GLSL;
  all eight NIF comparisons are represented, including ALWAYS/NEVER. A child
  disabling alpha overrides inherited state. No texture-based alpha inference.
- Smooth NiShadeProperty and disabled NiWireframeProperty are accepted. Flat
  shading, enabled wireframe, property controllers and all unknown properties
  fail explicitly. NiDitherProperty deliberately remains an unsupported test
  case rather than an ignored property.

Failures now identify `stage`, exact node type/index/name, property type/index
and reason. For example, an unsupported authored fixture reports
`stage=properties node=NiTriShape#2[Quad] property=NiDitherProperty#7`.
Inherited material and texture failures retain the actual property record's
identity. Geometry, image decoding and OSG-state failures also identify stages.
The existing application exports the exception as `scene_error`; it needs no
application/lifecycle changes to convey the improved message.

Compared against local upstream implementations in
`components/nifosg/nifloader.cpp` (`applyDrawableProperties`, `handleDepthFlags`,
`handleAlphaBlending`, stencil handling), `components/sceneutil/depth.hpp`,
`components/shader/shadervisitor.cpp`, `files/shaders/lib/material/vertexcolors.glsl`
and `components/resource/imagemanager.cpp`. Official reference links:
[OpenMW loader](https://github.com/OpenMW/openmw/blob/master/components/nifosg/nifloader.cpp),
[OpenMW shader visitor](https://github.com/OpenMW/openmw/blob/master/components/shader/shadervisitor.cpp),
[Niftools filter definitions](https://www.niftools.org/nifxml/TexFilterMode.html).
No dependency revision or source overlay was changed.

## Changed-file inventory

All paths below are relative to `experiments/ios-openmw-nif-render-smoke/real-model/`.
The archive preserves the full repository paths and contains SHA-256 inventory
entries, a tracked-file diff and the complete new files.

| File | Change |
| --- | --- |
| `src/StaticProperties.hpp` | New inherited property validation and OSG state |
| `src/StaticModel.cpp` | Property traversal, contextual errors, vertex colors, Hilight, sampler |
| `device/src/OSGScene.hpp` | GLES3 alpha-test shader logic |
| `tools/nif_layout.py` | New bounded sequential metadata diagnostics |
| `tools/assets.py` | Complete layout inventory replaces selected-type scan |
| `tools/fixtures.py` | Self-authored positive/negative property cases |
| `tests/model_check.cpp` | Native ownership/bounds/pixels and actual OSG state assertions |
| `tools/run_cases.py` | Expanded native case runner and precise negative diagnostics |
| `tools/test_g1d.py` | Retained seven tests plus 14 offline regression tests |
| `README.md` | Correct inventory, current status, supported semantics/limitations |
| `RUG-COMPATIBILITY-REVIEW.md` | This investigation and handoff |

## Validation and preservation

- **159 Python tests passed:** G1D 21, G1C 32, G1B 21, G1A 14, G0C 25,
  G0B 46. All seven G1D Python files pass syntax parsing.
- New offline tests consume all 17 positive fixture layouts, check property
  references/overrides, reproducibility/distinctness, misleading embedded type
  names, invalid references/numerics, every truncated prefix, unknown types and
  trailing bytes. They validate encoders/diagnostics, not C++ rendering behavior.
- **Prepared, not executed:** 17 positive and 24 negative native cases. The
  executable checks owned bounds/DDS pixels, real color arrays, depth test/write,
  mirrored winding, culling, blend factors/sorting, alpha uniforms (all eight
  test functions), mip filtering and sibling isolation. Negatives must fail
  with the expected error and context; inputs must remain unchanged. The
  existing workflow invokes these through CTest; the expanded offline tests
  remain in its existing `test_g1d.py` discovery path.
- **Passed:** ESSL 300 vertex/fragment syntax and cross-stage linking using
  official Khronos glslang 16.6.0. This is not ANGLE, shader execution or GPU proof.
  A temporary portable validator and video decoder were used locally; neither
  is a project dependency or included in the source-review archive.
- **Passed:** G1A/G1B/G1C source/provenance audits, exact fixture inventory/hashes,
  all 53 A–E preservation entries, F/G0B preservation, pinned OSG and dependency
  checks, all nine dirty Build #15 hashes, and the 247-file before/after snapshot.
  Completed G0B/G0C/G1A/G1B/G1C code and all upstream sources are unchanged.
- **Passed:** unchanged manual workflow's 23 Bash run blocks and two embedded
  Python blocks parse; Git whitespace check passes. Branch and HEAD unchanged;
  index was unstaged during source-review validation. Only the eleven listed G1D source/documentation files
  are changed or added by this task. Existing Build #15 changes are excluded.
- Original installation ESM/BSA hashes are checked against the existing private
  transfer manifest. No original assets, device recording or private manifest
  enter the review ZIP, public source or CI artifacts. Diagnostic output is
  metadata only; the reproducible fixtures remain entirely self-authored.

No suitable local C++/Apple toolchain is available. Revised host C++ tests,
iPhoneOS compilation/linking, bundle/IPA validation, ANGLE mip generation,
alpha visual behavior, original rug native acceptance, lifecycle recovery
and physical rendering are **unverified**. Previous native build success
does not establish success for this correction.

## Manual handoff

Build #2 preparation review correction: reject `LightMode_Emissive` even when
combined with `VertMode_SrcIgnore`. Upstream only assigns its local `lightmode`
from SrcAmbDif; when active, emission-only mode zeros material diffuse/ambient.
SrcIgnore does not select that branch in the current upstream implementation.
Our unlit shader implements neither an emission term nor emission-only lighting,
so the conservative adapter contract explicitly rejects this encoding in all
vertex modes, as requested by review. A distinct self-authored native negative
case and offline fixture regression cover (SrcIgnore, Emissive); the genuine
rug's (SrcIgnore, EmiAmbDif) remains supported. No shader approximation is added.
The unchanged application bundle identifier is
`org.openmw.experiments.real-model`, preserving update compatibility with the
installed app. Actual data retention still depends on the signing/install process.

Source review is approved. Commit only the listed
G1D files and push normally, then dispatch the existing manual
`ios-openmw-real-model-device.yml`. Return the new commit/run URL immediately
without waiting or polling. Native host cases, device compilation and strict
bundle/IPA checks must pass. Sign/install the resulting IPA manually and
privately retain/transfer the user's original `Documents/Model` inputs.

On the iPhone, require the original rug with the original DDS to be visible
through a full orbit, with correct surface orientation, thickness and texture;
verify no scene error, shader link, advancing OSG frames, unchanged input hashes
and expected 12 vertices/12 triangles/one shape. Export JSON/LOG plus recording
and screenshots bound to the new commit/session. Check suspend/resume and
clear/restore separately. Neither a successful swap nor a linked binary is a
physical rendering PASS. Native Build #2 and device results require separate review.
