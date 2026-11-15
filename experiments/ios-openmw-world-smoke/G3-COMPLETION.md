# G3 physical acceptance

G3 is accepted for original static exterior rendering and observed experimental
first-person traversal on the iPhone 16 Plus. Accepted source:
`d60ca603e82935a9ccce9ae5ec8dc9ec22013580`; session:
`41AACAFC-A29A-404B-BC25-5A891523B57F`.
[Native workflow](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43676376065).

The supplied independent review reports nine Seyda Neen exterior cells, 1,679
instances, 179 models, 184 textures, 345,898 model triangles, 73,728 terrain
triangles and 920 collision objects. The exports report 47,267 physics steps,
23,624 OSG frames and successful EGL swaps, zero polled GL errors, successful
shader linking, unchanged private inputs and a nominal final thermal state.
Final physical footprint is 261,523,248 bytes. Mean display callback interval
is 16.6897 ms across 23,622 samples; one interval exceeds 50 ms. Native scene
preparation is approximately 701 ms; total reported startup is approximately
1.60 seconds.

The local evidence folder `Downloads/OpenMW-G3-device-review-2026-11-15`
contains JSON, LOG, a 14-frame rotated contact sheet and the independent review.
All four entries in the supplied SHA256SUMS were verified locally. The JSON
source commit, session and reported counters match the accepted findings.
The original 397.767-second recording is retained separately. Sampled images
corroborate recognizable terrain, architecture, vegetation, ship and docks,
changing viewpoints and the unobstructed gameplay screen. Sampled frames do
not constitute a continuous recording review.

This acceptance does not establish actual display FPS, peak memory, complete
collision fidelity, individual jump or reconnection acceptance, full lifecycle
acceptance, long-term thermal stability, gameplay, water or world streaming.
Private evidence and original assets remain outside source and CI artifacts.
