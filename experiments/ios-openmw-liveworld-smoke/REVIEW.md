# G6 independent review checkpoint

Base: `cb089f4141782f6c136d68d7e71b03f4f30b73a9`, branch `ios-port`.
All source changes are additions inside `experiments/ios-openmw-liveworld-smoke`
and `.github/workflows/ios-openmw-liveworld-device.yml`. No accepted milestone,
upstream source or dependency pin is edited. The nine unrelated Build #15
working-tree files remain byte-for-byte preserved and are not part of G6.
There is no staging, commit, push or workflow dispatch in this task.

The ZIP's root `REVIEW-INVENTORY.json` is the exact source-addition/evidence
inventory, with both raw and LF-normalized source SHA-256 hashes. `SHA256SUMS`
covers every payload except itself, including the inventory. The ZIP is reopened
and every byte compared before handoff. A sidecar contains the ZIP SHA-256.
Validation refuses packaging if current source bytes differ from the final
validation inventory.

Review the public API and lifecycle in `src/LiveWorld.*`, checked projection
rules in `engine-lock.json` and `tools/prepare.py`, real dependency/ABI setup in
`cmake/dependencies.cmake`, shader/resource reuse in `tools/prepare_renderer.py`,
and strict preflight/provenance/package checks. `WINDOWS-FAULT.md` contains the
reproduced native stack and evidence-supported service-boundary correction.
`ARCHITECTURE.md` explains why full Scene activation is not claimed.

Evidence includes authored native results with exit codes and streams, Python
logs, syntax/source/fixture audits, preservation results, configured source
inventories, sanitized private-content counts/hashes, captured fault summary
and final build/configure diagnostics. Original private assets, profiles,
physical recordings, full private logs, dependency archives, executables,
libraries and PDBs are excluded. Review evidence remains ignored local output;
it is not intended for Git or public CI artifacts.

After review, a separately authorized publishing task should check the exact
source inventory and protection snapshots, stage only approved additions,
commit/push normally and dispatch the new manual workflow for that exact commit.
Return its URL immediately without waiting or polling. Keep G5's published
checkpoint separate. Do not infer physical success from compilation or packaging.
