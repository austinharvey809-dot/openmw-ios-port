# G6: genuine live world ownership

Unpublished review candidate based on G5 commit
`cb089f4141782f6c136d68d7e71b03f4f30b73a9`.
G5 Apple compilation and physical acceptance remain pending: its published
workflow attempts could not allocate a macOS runner. This experiment neither
changes nor redispatches G5.

G6 replaces the renderer's experimental reference merger with genuine
`MWWorld::WorldModel`, `CellStore`, registered record classes and typed
`LiveCellRef` ownership. Genuine NifOsg, ResourceSystem, SceneManager,
TerrainGrid, Bullet shape resources and the G4/G5 renderer remain in use.
The Windows CPU implementation builds and passes the tests in [VALIDATION.md](VALIDATION.md).
No G6 Apple binary, IPA, GPU execution or physical acceptance is claimed.

Implemented operations include content overrides/deletions/moved leases,
owned reference lookup, stable epoch-qualified handles, enabled state,
effective positions, nonzero counts, genuine cross-cell moves and explicit
whole-session retirement. Authored tests verify that live changes reach the
genuine NifOsg scene graph without changing an already prepared graph.

`MWWorld::Scene` compiles unchanged as an interface/dependency gate. It is not
instantiated. Actor classes, animation and physics implementations are linked
where required by real engine classes, but actors are not simulated or drawn.
The remaining service boundary is described in [ARCHITECTURE.md](ARCHITECTURE.md).
The Windows crash reported during development is explained with its captured
stack in [WINDOWS-FAULT.md](WINDOWS-FAULT.md).

## Local validation

Use Python 3.11+, CMake and the existing verified OSG/Bullet provider. No
system-wide tools or private assets are needed for authored regressions.

```powershell
python -B tools/dependencies.py --output artifacts/runtime-deps
python -B tools/windows_build.py --cmake <cmake.exe> --existing-build <verified-G5-build> --build <G4-artifacts/G6-build>
cmake --build <G6-build> --target openmw-g6-live-check openmw-g6-world-check openmw-g6-render-check g6-scene-compile --parallel 3
python -B tools/audit.py --build <G6-build>
ctest --test-dir <G6-build> -R '^g6-' --no-tests=error -V
python -B -m unittest discover -s tools -p test_g6.py -v
```

On Windows, prepend the verified OSG provider's `bin` directory to PATH.
Set `OPENMW_TEST_CMAKE` for preserved CMake regression checks and
`G6_MYGUI_HEADERS` if the verified MyGUI include tree is elsewhere.
The Windows helper reuses existing verified compiler/archive wrappers; it does
not install a toolchain. The shader output safety rule requires an in-repository
build to live under `ios-openmw-world-smoke/artifacts`.
Dependency acquisition verifies pinned size, cryptographic hash and extracted
inventory; `--offline` revalidates existing preparations. Normal TLS verification
is retained; `--cafile` can select a legitimate CA bundle.

## Native and device handoff

The new manual-only workflow is `ios-openmw-liveworld-device.yml`. It retains
accepted native suites, 29 startup assertions, genuine dependency compilation,
early Apple consumer syntax, per-object iPhoneOS archive inspection, all static
registration gates and strict executable/bundle/IPA reopening checks. G6 and
G5 share one OSG/Bullet provider in that build. Source archives alone are
reusable; generated dependency outputs are not accepted as unverified binaries.

The intended package is `IOSOpenMWLiveWorld-unsigned.ipa`, with the existing
`org.openmw.experiments.real-model` identity and `Documents/Model` import path.
No such IPA has been produced locally. After independent source review and
separate publishing authorization, dispatch and return the run link without
waiting for CI. Do not delete the installed app or transfer private game data
again unless actually necessary. Preserve the signing identity used to retain
its data container.

Later physical testing must establish startup, shader acceptance, visible
worlds, repeated streaming/doors, controller movement, resume and resource
bounds. Export matching `g6-startup.json`, `g6-render.json`, `g6-render.log` and
a screen recording. New live-object counters report loaded cells, registered
objects, raw-reference reservations, preparation latency and failures. Callback
intervals are not measured GPU FPS.

No game assets, private profiles or device evidence belong in source control or
public CI artifacts. The source-review inventory and evidence exclusions are in
[REVIEW.md](REVIEW.md).
