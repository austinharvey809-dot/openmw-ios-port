# G2 physical acceptance

G2 is physically accepted for genuine static-interior rendering and demonstrated
navigation on the iPhone 16 Plus. Acceptance was supplied by independent physical
review, not inferred from successful CI or swap counts.

- Accepted source: `e9b44ef693ee0cd0580db83326d7bf63555ce960`.
- Device session: `768DC2C1-7EDF-4FF6-BD48-4742894E4EBF`.
- [Native workflow](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43665531863).
- Private evidence folder: `C:\Users\austi\Downloads\G2-device-evidence`.

The local JSON was inspected. It identifies Seyda Neen, Fargoth's House, the
accepted commit/session, 46 references, 43 instances, 27 models, 7,589 vertices,
7,057 triangles, 91 shapes, 39 textures and four point lights. It reports 1,473
OSG frames, 1,473 swaps, zero polled GL errors, linked shaders, unchanged private
inputs, 123.853792 ms scene loading and 1295.419125 ms startup preparation.
Its runtime `physical_rendering_acceptance` field deliberately remains UNVERIFIED:
the later independent physical review supplies acceptance; exported bytes were
not edited to change that field.

All three evidence-file hashes match the supplied SHA256SUMS.txt:

| File | SHA-256 |
| --- | --- |
| g2-render.json | b1437c3caa7d20e43e68656089c47569b27d2f749b5022c7b21c99406d095589 |
| g2-render.log | 23e5a78b104d978e12b917b00145cab9d4a6cf123245a9b0f07351cfbc5140cb |
| ScreenRecording_11-14-2026 20-38-38_1.mp4 | 8df3fa88942947cfa1547e6ea8b7a07245bd771735f933269e688ae88d5e3f41 |

The independent reviewer confirmed visible original architecture, furnishings,
textures, lighting and navigation. Rendering continued after Control Center was
used to connect a DualShock 4. This development turn inspected exported metadata
and file integrity; it did not independently replay or visually review the video.
The footage and proprietary game files are not copied into source or the public
review archive.

Acceptance does not establish complete lighting fidelity, collision, gameplay,
measured display FPS, full lifecycle acceptance or sustained thermal stability.
The accepted implementation is unchanged. G3's different capabilities require
their own native and physical validation.
