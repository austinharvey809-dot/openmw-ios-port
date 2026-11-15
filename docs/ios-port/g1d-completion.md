# G1D accepted: original static Morrowind model on iPhone

The user reports independent physical-device acceptance of G1D Build #2 on
their iPhone 16 Plus. This records that accepted evidence; the completed tests
were not repeated during G2 preparation.

- Accepted source: `a70ab5a7c8974245b205826ab748d86a79a53b1e`.
- Device session: `37DCFF9A-F0AA-4BD5-BFD7-880B91B2C0B8`.
- [Native workflow run](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43632073590).
- Original STAT `furn_de_rug_02`, genuine NIF `meshes/f/furn_rug_02.nif`,
  original DDS `textures/tx_rug_02.dds`.
- 12 vertices, 12 triangles, one shape; parser and geometry ready; shader linked.
- 929 OSG frames, 1,080 successful EGL swaps, zero polled OpenGL errors.
- Private ESM/BSA inputs unchanged; visibly textured original model observed
  through multiple camera angles; background/resume visually successful.
- ANGLE Metal renderer on the Apple A18 GPU.

**G1D is physically accepted within its original static-model scope.** It does
not establish general NIF compatibility, full game lighting, actor animation,
interior loading, physics, gameplay or full-engine operation. Its accepted
implementation and dependency pins remain unchanged.

G2's original-interior implementation is a separate experiment at
`experiments/ios-openmw-interior-smoke`. G2's native compilation, original-cell
execution and physical rendering require separate acceptance; the G1D evidence
does not transfer those claims to G2.
