# G1A: genuine NIF to owned OSG geometry

Status: implemented for manual review; **native compilation and execution are
unverified**. No GPU rendering, UIKit application, IPA or device installation is
part of G1A. G0C remains complete for synthetic NIF parsing on iPhone 16 Plus,
including the independently reviewed exports and final PASS screenshot recorded
in the [completion report](../../docs/ios-port/g0c-completion-and-g1-plan.md).

## Scope and architecture

`src/GeometryAdapter.cpp` uses the same real APIs as G0B:

1. Open `valid.esm` using `ESM::ESMReader` with the WINDOWS_1252 encoder and load
   its single `ESM::Static`. Check object `eIOSStatic`, original model `TeSt.NIF`,
   record framing and the normalized ESM-selected key `meshes/test.nif`.
2. Register `triangle-candidate.bsa` using the preserved genuine BSA/VFS bridge,
   build `VFS::Manager`'s index and read that key. Check its SHA-256 using Apple's
   CommonCrypto against the expectation generated from the audited fixture
   manifest. Compare returned bytes with the standalone NIF comparator.
3. Parse a fresh BSA/VFS stream using `Nif::Reader` into `Nif::NIFFile`. The
   standalone NIF never substitutes for the selected VFS parsing stream.
4. Require NIF 4.0.0.2, exactly three records and one root, the decoded
   NiNode -> NiTriShape -> NiTriShapeData relationships, identity root/shape
   transforms, three finite vertices, one grouped triangle, valid distinct
   indices and nonzero finite cross-product area.
5. Copy the decoded vectors into `OwnedGeometry` and independently into OSG-owned
   `osg::Vec3Array`/`osg::DrawElementsUShort(GL_TRIANGLES)`. Retain
   `osg::Geometry` and `osg::Geode` through `osg::ref_ptr`; request VBO/VAO storage
   and disable display lists. No GL context or draw call is created.

Every rotation matrix component is checked explicitly in addition to the
upstream identity predicate, including off-diagonal values. Unsupported
transforms fail instead of being discarded. Production output contains no
position/index constants; only the tests contain expected coordinate/index
arrays. Record pointers are used while `NIFFile` owns their storage and are not
retained in the copied result. The native test compares all source/owned/OSG
values, alters the original vectors, destroys the parser-owned file, then reads
the OSG arrays and evaluates their lazy bounds.

## Native build closure

The isolated CMake project adds the **unchanged G0B host project exactly once**.
That supplies D/E's genuine ESM/BSA/VFS integration, the twelve NIF translation
units plus hash.cpp/MurmurHash3.cpp, pinned OSG core/OpenThreads and verified
double-precision BulletCollision/LinearMath. G1A adds only the adapter archive
and its host executable. It does not add G0C's GLES2 adapter or a second OSG.
The actual G0B generated include tree propagates to the new consumers; the
configured audit checks all five genuine generated OSG/OpenThreads headers,
G0B precision contracts and the new C++20 compile commands.

This project requires a native macOS toolchain for CommonCrypto. The manual CI
workflow verifies an ARM64 runner and products. Host OSG may link macOS graphics
frameworks through its existing recipe; structural acceptance does not exercise
those APIs and supplies no ANGLE/iPhoneOS/GPU compatibility proof.

## Source and fixture provenance

`data/source-lock.json` records preparation commit
`22f267edd49f191ec1c29eed28368f8093c49d7a` and committed graphics baseline
`8799e90148c3ea1985b2547fa8e9b31be19b45c2`. All **23 committed version-2 graphics
blobs** are recorded with exact SHA-256 and Git blob IDs and re-read with
`git show` during audits. No graphics source is copied or compiled in G1A. No
checkout/reset/restore/stash operation is used to obtain that baseline.

Pins remain:

| Dependency | Exact source identity |
| --- | --- |
| OSG | `9b384d5439977784e5cd250ff8ff7966928ddd27` |
| ANGLE (future G1B) | `6ea96bcca6d7f05199f5565c6d5c4722af7269da` |
| depot_tools (future G1B) | `816da11f80777dcf8c10bdaa84df18450dcba12a` |
| Bullet | `https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz` |
| Bullet SHA-512 | `7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4` |

Fixtures are referenced in `../ios-openmw-nif-smoke/data/`; none is copied into
the new source tree or altered. All ten binary fixture sizes/hashes are exact.
The twelve-entry inventory includes both metadata JSON files. Only those two
metadata files use canonical LF hash/size comparisons to accommodate Git's
Windows CRLF conversion. Runtime before/after snapshots hash the **raw bytes of
all twelve files**, so any input mutation during tests still fails. Unexpected,
missing, linked or nonregular entries are rejected.

`data/preserved-source-sha256.json` freezes 191 existing non-graphics experiment,
workflow and iOS audit-document files, including completed A-F/G0B/G0C. Existing
upstream closure audits are reused. `data/build15-local-sha256.json` freezes all
nine dirty graphics files in their current local byte representation. The local
check is opt-in because CI correctly checks out committed version 2 and cannot
contain the user's uncommitted version-3 changes. CI does not claim to verify
those local bytes. No original Morrowind installation is accessed.

Runtime evidence records the actual current source commit, binary SHA-256s,
dependency pins, source/fixture contracts, new G1A/workflow hashes, raw input
snapshots and the canonical geometry SHA-256. Configured evidence separately
records generated-header hashes. Geometry serialization is ASCII
`G1A-geometry-v1`, then two little-endian uint32 counts (vertex count and index
count), XYZ IEEE754 float32 components in vertex order, then little-endian
uint16 indices in primitive order. The Python test driver computes the expected
fixture digest independently; no host ABI padding/native byte order is hashed.

## Tests and manual CI

Fourteen offline Python tests cover exact/tampered inventories, metadata newline
handling, invalid evidence, preserved source/baseline identities, syntax,
single-provider recipes, native mutation coverage and manual workflow gates.
Their synthetic result objects test evidence policy, not native execution.

The actual native `openmw-nif-geometry-check` executable tests positive decoding,
source-to-adapter and source-to-OSG equivalence, OSG primitive type/mode/count,
owned storage, post-parser-release lifetime and bounds. It exercises **20
rejection cases**, each starting from a genuine parse: bad vertex counts and
metadata, bad triangle grouping and metadata, NaN/infinity, out-of-range and
repeated indices, collinearity, root translation/off-diagonal rotation, shape
scale/rotation, NaN transform, wrong version, missing/wrong root, missing child,
missing data reference and missing record. Release builds use throwing checks,
not disabled `assert()` calls.

The driver then executes all six preserved G0B positive/negative parser cases
using the same linked parser provider. Missing binaries, nonzero exits, malformed
or incomplete reports, wrong geometry/resource hashes and input mutation fail.
No native PASS is inferred from Python-only tests. stdout/stderr, result JSON,
configuration/build logs and separate gate outcomes are retained on failure.

The separate manually triggered workflow is
[ios-openmw-nif-geometry-host-smoke.yml](../../.github/workflows/ios-openmw-nif-geometry-host-smoke.yml).
This is the sole new file outside the isolated experiment, as explicitly allowed
by Task 3 for host validation; existing workflows are unchanged. It checks source
history for provenance, clean pinned OSG, existing G0B/G0C tests, exact verified
Bullet acquisition, native CMake configuration/compile commands, actual ARM64
host products and CTest runtime results. It retains failure artifacts. It has no
push/PR trigger and has **not been dispatched**.

On a suitable host with the exact clean pinned OSG checkout and Bullet source
already verified by the preserved acquisition tool:

```sh
export PYTHONDONTWRITEBYTECODE=1
export OPENMW_ESM_OSG_SOURCE=/path/to/clean-pinned-osg
python3 experiments/ios-openmw-nif-render-smoke/tools/contracts.py --osg-source "$OPENMW_ESM_OSG_SOURCE"
python3 -m unittest discover -s experiments/ios-openmw-nif-render-smoke/tools -p test_g1a.py -v
cmake -S experiments/ios-openmw-nif-render-smoke -B /tmp/openmw-g1a-build -G 'Unix Makefiles' \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release \
  -DOPENMW_ESM_OSG_SOURCE="$OPENMW_ESM_OSG_SOURCE" -DG0_BULLET_SOURCE=/path/to/verified-bullet/source \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build /tmp/openmw-g1a-build --target openmw-nif-geometry-check openmw-nif-parse-check --parallel 4
ctest --test-dir /tmp/openmw-g1a-build -R '^g1a-owned-geometry-and-six-parser-cases$' --output-on-failure -V
```

Optional Windows preservation check, when Python is functional:
`python tools/contracts.py --osg-source ... --check-local-build15` from this
experiment. Evidence/build outputs belong in ignored directories or external
build storage, never preserved fixtures or dependency source directories.

## G1B: one ANGLE-compatible OSG provider

G1A's host geometry proof is a prerequisite, not an iPhone renderer. G1B must
build a separate matched device closure in its own configuration:

1. Use the recorded committed **version-2** graphics preparation/provider and
   source-specific KHR aliases, never the dirty version-3 observer. Prepare a
   separate scratch renderer source from the same OSG pin; leave the clean
   audit-reference checkout untouched. Keep the original integrity checks.
2. Build exactly one static provider of OpenThreads, osg, osgUtil, osgDB, osgGA,
   osgText and osgViewer. Preserve GLES3/None, ANGLE EGL/GLES header selection and
   EGL resolver adaptation. Do not add G0C's SDK GLES2/OpenGLES adapter, link a
   second osg archive or load an osgDB NIF plugin.
3. Rebuild the unchanged genuine NIF units and D/E against that provider and the
   exact double-precision Bullet recipe. Apply canonical generated includes
   BEFORE source/math-only includes to every consumer from the new project;
   verify OpenThreads/Config and Version plus osg/Config, GL and Version are
   genuine configuration output, not placeholders. Match D's double matrix/
   plane/quaternion, float bounding types and all other audited configuration
   switches; do not edit preserved D/E sources to achieve it.
4. Keep C++20 consumers, AppleClang, ARM64-only iPhoneOS/minimum 18.0 and strict
   SDK/load-command checks. ANGLE's full locked dependency graph and device
   frameworks must be built or independently revalidated; neither G1A host OSG
   nor an old packaged smoke executable is a reusable matched device SDK.
5. Reuse only the colored ESSL300 shader initially: osg_Vertex slot 0,
   osg_Color slot 3 and osg_ModelViewProjectionMatrix with OSG matrix uniforms
   and attribute aliases. Attach adapter-owned geometry, use decoded bounds and
   explicit two-sided unlit state. Keep parsing outside the display callback.
6. Retain application-owned CAMetalLayer/EGL ES3 currentness, embedded
   SingleThreaded viewer, one external swap, resize, suspension/resume/teardown,
   raw GL diagnostics and actual shader-link verification. New app identity,
   combined provenance and strict bundle/IPA reopening are later separate gates.

No G1B code, shaders, UIKit integration or G1C device evidence is implemented
here. Structural host acceptance cannot establish visible rendering or gameplay.

## Current validation and preservation

Python cannot launch locally (WindowsApps alias: `The file cannot be accessed
by the system`); no compatible CMake/C++/Apple host toolchain is available.
All 14 new Python tests/syntax, native compilation/linking, 20 native geometry
negative cases and six genuine parser cases are **unverified for G1A**. No
compiler/linker success or failure has been observed for this new target.

Available PowerShell audits verified preservation manifests, all 53 A-E entries,
F/G0B and completed G0C, exact fixtures, pinned OSG cleanliness, dependency locks,
23 historical graphics blobs and nine dirty graphics file hashes. Workflow shell
syntax, documentation links and whitespace checks passed. Existing protected
files, HEAD and index were unchanged at the end of this task. No dependency was
downloaded, no private asset was copied, and no source outside this experiment
was changed other than adding the separate manual host workflow.

Ready for source review and a separately authorized native CI run. No staging,
commit, push, dispatch, IPA creation, installation or rendering claim.
