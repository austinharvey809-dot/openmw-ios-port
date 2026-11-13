# G1C: synthetic textured NIF resource slice

Implementation prepared for first native CI review. **G1C is not complete.**
No new native compilation, iPhone texture visibility, shader execution, IPA,
GPU completion or lifecycle acceptance is claimed from local policy tests.
The completed G1B evidence is recorded separately in
[the completion report](../../../docs/ios-port/g1b-completion-and-textured-resource-slice.md).

## Implemented path

`textured.esm` -> genuine ESM STAT `eIOSStatic` / `TeXtUrEd.NIF` -> genuine
BSA/VFS `meshes/textured.nif` -> genuine six-record OpenMW NIF reader -> owned
G1A geometry plus decoded UV/material copies -> real OpenMW texture-path helper
and object cache -> pinned static OSG TGA reader -> OSG Texture2D and GLES3
base-texture modulation -> existing externally owned EGL/ANGLE Metal renderer.

The adapter validates the property/source relationships, one complete finite UV
set, opaque diffuse material, external true-color image, NEAREST/clamp policy
and no mipmaps. It rejects unsafe texture references before normalization.
The real helper exercises mixed case/backslash normalization, `textures/`
prefixing and the existing DDS-first/TGA-fallback policy. Only the expected
archive resource key and SHA-256 are accepted; there is no loose-file image or
warning-image fallback. The image cache must demonstrate one reuse hit, then
clear while the owned image remains valid.

After copying properties/UVs, the adapter moves the **actual** first three
parsed records into a temporary NIFFile and calls unchanged `G1A::copyGeometry`.
It never fabricates replacement parser records or production vertices. The
original property/source records remain alive until copying finishes. Returned
positions, indices, UVs, colors, image and texture outlive parser, VFS, encoder
and cache. This is a narrowly supported unlit material adapter, not OpenMW's
full NifOsg loader, ImageManager, material system or game scene.

The 8x8 self-authored TGA has cyan/yellow checker cells and a red UV-origin
corner. Decoded diffuse `(0.75, 1, 0.5, 1)` modulates it. The unit triangle uses
decoded UVs `(0,0), (1,0), (0,1)`, NEAREST sampling and no mipmaps. A constant
green triangle cannot meet this milestone's visible-texture acceptance.

| Input/result | SHA-256 |
| --- | --- |
| Six-record NIF | `7677739cca6c8b86b600e53184734b4c3c2d5f1fc42b775ff74b295e1315af13` |
| TGA archive resource | `e2362c56b06c28fd52957917bfcdcad1eadffe745e11b7283b641ae762df2532` |
| Decoded bottom-left RGBA pixels | `758a41b756ff0a329f9579ec27db5c6cd6504101c3b0546e5d96be73b7865290` |

`data/fixture-manifest.json` records every input's size/hash and each negative
case's intended stage. Per-case expected corrupt-input hashes are confined to
the native host test harness. The app uses compiled positive expectations.
All new fixtures are reproducible from `tools/fixtures.py`; existing G0 fixtures
are untouched. Regeneration refuses to overwrite changed inputs.

## Dependency and packaging architecture

Exactly one OSG/OpenThreads provider uses the unchanged G1B version-2 baseline:
OSG `9b384d5439977784e5cd250ff8ff7966928ddd27`, seven viewer libraries,
ANGLE `6ea96bcca6d7f05199f5565c6d5c4722af7269da` and the existing Metal-only
device-package recipe. Bullet remains 3.25 with the original SHA-512,
double precision and all 12 genuine NIF units. C++20, ARM64 iPhoneOS 18.0,
generated headers and Apple framework linkage are preserved. No G0C GLES2
provider or Build #15 observer overlay is added.

New closure: unchanged `components/misc/resourcehelpers.cpp/.hpp`, header-only
`components/resource/objectcache.hpp` and `cachestats.hpp`, and one static
`src/osgPlugins/tga/ReaderWriterTGA.cpp` from the existing OSG pin. No external
image library is introduced. `source-closure.json` freezes their hashes. Both
the clean reference and actual overlaid TGA compiler input must match.
`g1b-source-sha256.json` freezes 19 completed G1B files in addition to the
existing nested preservation audits. TGA-specific notices are bundled too.

`tools/support.py` privately loads the original strict validators. The package
wrapper changes only app identity and adds G1C resources/source checks. It
retains real Mach-O/SDK/dependency inspection, exact bundle inventory, unsigned
packaging and independent reopening. `g1b-build.json`, `G1BExpected` and the
scene-delegate class name intentionally retain the original validator's
compatibility contract; metadata includes a separate `g1c` section and the app
has its own `org.openmw.experiments.ios-openmw-textured-nif` identity.

`device/src/OSGScene.hpp` retains the proven viewer/camera setup, replaces only
the color shader with `texture(baseTexture, uv) * decodedDiffuse`, and binds UV
attribute 6. The original immutable `AngleRenderer.hpp` and GL debug capture
are included directly. The new UIKit entry point keeps lifecycle/controller
handling and validates all 12 original plus 11 textured input snapshots.

## Local validation and remaining boundaries

Executed on Windows with a temporary, non-system Python 3.14.10 embeddable
runtime. Its ZIP SHA-256 matched official python.org HTTPS Sigstore metadata;
no claim is made of independently verifying that Sigstore signature. No TLS
verification or security setting was disabled. Git's Perl HTTP::Tiny/OpenSSL
provided verified HTTPS when Windows Schannel could not.

| Check | Local result |
| --- | --- |
| G1C offline suite | 31 tests passed; includes 11 inherited binary/bundle/SDK/IPA policy tests and an actual CMake configure-only flag-scope regression |
| Existing G0B / G0C / G1A / G1B suites | 46 / 25 / 14 / 21 tests passed |
| ANGLE offline suite | 77 run: 76 passed, one host C++ compile test skipped |
| Separate unfinished Build #15 suite | 105 run: 96 passed, four failures, five C++ tests skipped; unchanged working tree |
| Source/fixture/preservation audits | Passed, including 53 A-E entries, F/G0B, G0C/G1A/G1B, nine Build #15 hashes, clean pinned OSG and unchanged dependency pins |
| Python syntax | Seven new Python files parsed/compiled without executing native code |
| Workflow syntax | 21 Bash blocks and two embedded Python blocks passed; GitHub schema/execution remains CI work |
| Git/documentation checks | Existing diff and all 36 new files pass whitespace checks; local document links resolve |
| Native host / iPhoneOS compilation and new IPA | Unverified: local C++/Apple toolchain unavailable; temporary portable CMake supports the configure-only regression |

All 247 files snapshotted before this task remain byte-for-byte unchanged;
branch, HEAD and Git index remain unchanged too. The 36 additions comprise this
34-file experiment plus the completion report and manual workflow. The only
pre-existing modified files are the eight Build #15 tracked files and its
untracked ninth observer; none were edited by this task.

Review preparation corrected one include-directory entry in `cmake/texture.cmake`:
`register_bsa.hpp` lives in `ios-openmw-bsa-vfs/src`, not the nonexistent
`ios-openmw-esm-vfs/src`. The target already inherited the correct directory
through E's public interface; its explicit include now names the real provider.

First native CI attempt: [Build #1](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43354934100)
at `de638bd798c75398ba60e927c56c521d1c88cd5e` passed source regressions,
Bullet acquisition, and CMake generation, then failed the configured-command
audit before compilation. Its artifact proves a pinned OSG macOS `CACHE FORCE`
leaked `-std=c++11` into consumer commands alongside `-std=c++20`.
The isolated host root now binds the caller's `CMAKE_CXX_FLAGS` in directory
scope before adding G1A. OSG's own child flags remain C++11/libc++; consumer
C++20 flags stay target-controlled. The strict single-standard audit remains
unchanged. A real CMake regression reproduces the unguarded leak and verifies
the guarded G1A/G1C and OSG scopes, preserving an unrelated caller definition.
Temporary CMake 4.2.1 was fetched from Kitware's official release with TLS
verification and its published SHA-256 checked; no system tool was installed.

The four pre-existing Build #15 failures are three `test_lod_bias` expectations
for the changed Texture.cpp mipmap overlay and one `test_texture_scene` expected
overlay label. Full diagnostics are in ignored `artifacts/local-validation/`.
They are reported, not repaired or treated as passing. This experiment imports
the frozen successful G1B/version-2 recipe, whose regressions pass, rather than
the dirty Build #15 implementation.

The native host harness is implemented but **not locally executed**. It must
prove exact source/owned UV/material/geometry equivalence and survival after
parser/VFS/cache destruction; 11 native mutations must fail at their intended
gates. Six negative archives cover invalid NIF header/reference/UV, unsafe or
missing texture, and malformed image. The unchanged G1A 20 geometry negatives
and six genuine parser cases remain separate required native gates.

Local commands, from the repository root (substitute a functioning Python):

```sh
python3 -B -m unittest discover -s experiments/ios-openmw-nif-render-smoke/textured/tools -p test_g1c.py -v
python3 -B experiments/ios-openmw-nif-render-smoke/textured/tools/resources.py audit --osg-reference /path/to/clean/pinned-osg --local-build15
python3 -B experiments/ios-openmw-nif-render-smoke/textured/tools/check_workflow.py --workflow .github/workflows/ios-openmw-textured-nif-device-smoke.yml --bash /path/to/bash
```

On macOS, configure `textured/` out of tree with the existing verified Bullet
source and pinned OSG (`-DCMAKE_POLICY_VERSION_MINIMUM=3.5`, Release, ARM64,
compile commands enabled). Build `openmw-textured-nif-check`,
`openmw-nif-geometry-check`, `openmw-nif-parse-check`. Run the G1A test from
`build/g1a` and G1C test from `build`, each with `ctest --no-tests=error -V`.
The workflow contains the exact configure, source-audit and product commands.

## Native and physical handoff

After source review, publish only this slice and its documentation/workflow;
exclude the nine dirty Build #15 files. Manually run
`.github/workflows/ios-openmw-textured-nif-device-smoke.yml` on `ios-port`.
It gates host parsing/ownership/negatives, unchanged ANGLE acquisition,
single-provider configuration, device link, UIKit compile, SDK/dependency and
exact bundle inspection, unsigned IPA creation and independent reopening.
Actual target paths are generated with CMake target-file/bundle expressions.
Failure artifacts retain configure/compiler/linker/package output, compile
commands, prepared provenance/resources and separate gate statuses.

Only if all gates pass:

1. Review that run's source commit, hashes, binary platform and unsigned IPA.
   Sign/install through the user's established manual iPhone process.
2. On iPhone 16 Plus, verify a visibly patterned triangle: cyan/yellow cells
   modulated by the material, with the red UV-origin region. Record the screen
   and session UUID. Shader link, frame and swap counters alone are insufficient.
3. Use Triangle/Y to clear and restore the textured triangle. Background and
   resume; confirm the pattern returns without a failure overlay.
4. Export `g1c-render.json` and `g1c-render.log` unchanged and keep them outside
   Git. Inspect all six original parser cases, geometry and image hashes, real
   texture key, UV count, decoded diffuse, cache hit, source commit and unchanged
   12+11 input snapshots; correlate recording and exports by session UUID.

Only independent visible-texture review plus matching provenance/exports and
functional device checks can complete G1C. Presented FPS and GPU completion
remain unmeasured. No real Morrowind texture/model, full material loader or
gameplay acceptance is implied. No workflow was dispatched, IPA installed,
staging, commit or push performed during this preparation.

## New file inventory

All implementation additions are under this directory:

```text
.gitattributes  .gitignore  README.md  NOTICES.txt
source-closure.json  g1b-source-sha256.json
CMakeLists.txt  cmake/texture.cmake
src/TextureAdapter.hpp  src/TextureAdapter.cpp
tests/texture_check.cpp
device/CMakeLists.txt  device/Info.plist.in  device/cmake/provider.cmake
device/src/main.mm  device/src/OSGScene.hpp
tools/fixtures.py  tools/support.py  tools/resources.py
tools/package_textured.py  tools/run_texture.py  tools/check_workflow.py
tools/test_g1c.py
data/fixture-manifest.json  data/textured.esm  data/textured.nif
data/pattern.tga  data/textured.bsa  data/invalid-header.bsa
data/invalid-reference.bsa  data/invalid-uv.bsa  data/unsafe-texture.bsa
data/missing-texture.bsa  data/bad-image.bsa
```

Outside this directory, only the new workflow and
`docs/ios-port/g1b-completion-and-textured-resource-slice.md` are added. Existing
tracked files and the pre-existing untracked mipmap observer are unchanged.
