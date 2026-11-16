# Independent source-review handoff

Base: `cd5e74396fc75a502d441925adc77efcac4af1ec`, branch `ios-port`.
This candidate contains **30 source additions and no modifications to accepted
implementation files**. The eight pre-existing modified Build #15 files and its
untracked mipmap header remain byte-for-byte unchanged and are excluded.

No files were staged; no commit, push, workflow dispatch or installation occurred.
The ZIP preserves repository-relative source paths. `REVIEW-INVENTORY.json`
records the exact source/evidence inventories, raw and LF-normalized source
hashes. `SHA256SUMS` covers every payload including that inventory. A sibling
`.zip.sha256` records the archive digest. The package is independently reopened
and every entry compared with its original bytes before handoff.

## Review focus

- G4 closure is limited to the independently accepted static-world scope; CI,
  JSON/log measurements and independent visual findings remain distinct.
- ESMStore is genuine. Generated component views omit two unprovided application
  APIs without implementing stubs; remaining method/helper bodies are upstream.
- ResourceSystem/SceneManager/NifOsg/TerrainGrid/Bullet resources and the accepted
  bounded coordinator are reused. This is not full CellStore, MWWorld::Scene,
  character physics, animation or gameplay integration.
- The core/KHR label dispatch correction retains synchronous diagnostics and
  actual extension/context checks. Pale geometry is documented without a
  speculative material/lighting change.
- Exact provider/source/resource/SDK/registration/IPA gates remain mandatory.
  Stock Lua's real iOS platform configuration is required, and every new consumer
  is checked before the long OSG build. Lua's archive objects are independently
  inspected for ARM64/iPhoneOS rather than trusting configuration success.
- The existing bundle identifier and Documents/Model import formats are retained.
  Proprietary assets, profiles, physical exports/recordings, dependency archives,
  compiled objects and executables are absent from the review payload.

See `ARCHITECTURE.md`, `VALIDATION.md` and `G4-COMPLETION.md` for the architectural
boundary, actual test results and carried limitations. Windows CPU results are
not Apple execution or physical G5 acceptance.

## Exact source inventory

- `.github/workflows/ios-openmw-engine-device.yml`
- `experiments/ios-openmw-engine-smoke/.gitignore`
- `experiments/ios-openmw-engine-smoke/ARCHITECTURE.md`
- `experiments/ios-openmw-engine-smoke/G4-COMPLETION.md`
- `experiments/ios-openmw-engine-smoke/README.md`
- `experiments/ios-openmw-engine-smoke/REVIEW.md`
- `experiments/ios-openmw-engine-smoke/VALIDATION.md`
- `experiments/ios-openmw-engine-smoke/cmake/attach_device.cmake`
- `experiments/ios-openmw-engine-smoke/cmake/attach_host.cmake`
- `experiments/ios-openmw-engine-smoke/cmake/device.cmake`
- `experiments/ios-openmw-engine-smoke/cmake/host.cmake`
- `experiments/ios-openmw-engine-smoke/cmake/store.cmake`
- `experiments/ios-openmw-engine-smoke/dependencies.json`
- `experiments/ios-openmw-engine-smoke/engine-lock.json`
- `experiments/ios-openmw-engine-smoke/src/EngineIndex.cpp`
- `experiments/ios-openmw-engine-smoke/src/EngineIndex.hpp`
- `experiments/ios-openmw-engine-smoke/src/LabelDispatch.hpp`
- `experiments/ios-openmw-engine-smoke/tests/store_check.cpp`
- `experiments/ios-openmw-engine-smoke/tools/acquire.py`
- `experiments/ios-openmw-engine-smoke/tools/native_preflight.py`
- `experiments/ios-openmw-engine-smoke/tools/package.py`
- `experiments/ios-openmw-engine-smoke/tools/prepare_engine.py`
- `experiments/ios-openmw-engine-smoke/tools/prepare_frontend.py`
- `experiments/ios-openmw-engine-smoke/tools/preserve.py`
- `experiments/ios-openmw-engine-smoke/tools/provenance.py`
- `experiments/ios-openmw-engine-smoke/tools/review_package.py`
- `experiments/ios-openmw-engine-smoke/tools/run_engine_cases.py`
- `experiments/ios-openmw-engine-smoke/tools/test_g5.py`
- `experiments/ios-openmw-engine-smoke/tools/validate.py`
- `experiments/ios-openmw-engine-smoke/tools/verify_lua.py`

## After independent approval

Inspect and stage only these 30 additions, verify preservation again, then create
one focused commit and push normally to `ios-port`. Dispatch only the manual
`ios-openmw-engine-device.yml` workflow against that exact commit and return its
run link without waiting or polling. No publication is authorized by this report.

Review all host/ANGLE/iPhoneOS gates and the packaged G5 evidence before signing.
The workflow deliberately retains a G4 regression IPA as well as the new product;
use **IOSOpenMWEngine-unsigned.ipa** for G5. Retain the same Sideloadly signing
identity and bundle identifier; install over the existing app, preserving its
Documents/Model files. Do not delete the app or transfer game data again without
an independently demonstrated need.

On the actual iPhone, verify startup order, the added label-API checkpoint,
`content_store = MWWorld::ESMStore`, metadata counts and no repeat core-label
version errors. Exercise original exterior/interior views, doors, repeated world
streaming, controller movement, interruption/resume and cache/memory behavior.
Compare startup preparation and footprint with accepted G4. Export complete
`g5-startup.json`, `g5-render.json`, accumulated `g5-render.log` and an original
screen recording with the exact session/source identity. Confirm private-input
hash checks. Callback intervals do not constitute GPU/display FPS.

Full CellStore/Scene/character integration and mod compatibility require their
own genuine runtime evidence. Do not infer them from this component's metadata
or static-world tests. Return for independent review before publication.
