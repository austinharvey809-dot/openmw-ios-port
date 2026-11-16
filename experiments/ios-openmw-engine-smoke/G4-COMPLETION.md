# G4 closure: accepted genuine static-world integration

G4 Build #5 is physically accepted within the demonstrated original static-world
rendering, bounded streaming, navigation, door-transition and observed resume
scope. This acceptance does not imply full OpenMW gameplay or actor integration.

Accepted source: `cd5e74396fc75a502d441925adc77efcac4af1ec`.
[Successful native workflow](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/43784796321).
Accepted session: `0E48D978-4819-42E4-BBDB-6BC71DA7AB12`.
Device: iPhone17,4 / iPhone 16 Plus, iOS 27.2, Apple A18, ANGLE Metal,
OpenGL ES 3.0, OSG 3.6.5.

## CI and package evidence

All three completed artifacts were obtained and checked against GitHub's SHA-256
digests. Exact host/native internal inventories and every SHA256SUMS entry were
verified. The ANGLE tar digest, exact package inventory and every resource hash
were also independently verified on Windows.

| Artifact | ZIP SHA-256 | Verified payload |
| --- | --- | --- |
| openmw-g4-host-43784796321-1 | `9eaec6df7bd8dbee7c3b450ad8c840d1ff74b8d54a8d032fb1ee365078cb9bf2` | 230 files |
| g1c-angle-43784796321-1 | `ce418a4d96460b0a9e5cef0ce803b6fdf3c9c8d206a3f532be35e1c1f5d8a0fc` | authenticated ANGLE package |
| g4-native-43784796321-1 | `30c75aef09c9e9bee21559d91cfee96ef9eb60b5d7b6d9f556583fda0ca7351e` | 1,603 files |

The actual macOS standalone startup output reports **29 assertions**, PASS,
exit zero. All **42 native world cases** passed. Preserved G1A genuine parser and
owned-geometry, G1D, G2 and G3 native suites passed; G0B's 46 and G0C's 25 Python
tests passed. Source/preservation evidence reports 560 accepted source contracts.
The G4 static-registration executable passed.

Portable Mach-O inspection and IPA reopening verified ARM64/iPhoneOS platform,
deployment target, dependencies, application identity, exact 1,377-file public
inventory, fixture blobs, generated shader hashes, workflow/source hashes,
binary-bound build metadata, Bullet and ANGLE provenance. Apple SDK checks were
verified as recorded CI evidence; no local Apple SDK execution is claimed.
The real executable retains DDS/TGA/BMP/PNG/JPEG/OSG reader and serializer
registrations, including BufferIndexBinding.

Most native warnings concern upstream missing `override` annotations and
deprecated volatile operations. Remaining portability debt includes
OpenThreads' Apple thread-ID `syscall`, an ignored mesh-optimizer return value
and null-reference constructs in OSG shadow/debug code. The current profile
disables shadows; the warned default-matrix/debug symbols were not found in the
reviewed executable, although some osgShadow code is retained. This is not proof
that every warning is harmless or that future shadow/thread usage is accepted.
No dependency source was modified to hide these warnings.

Unsigned IPA SHA-256:
`e0b88d7e141176942a926acaf17483b9ea19ca605bd4ff9412bc1cf4d1b8e7f6`
(8,531,942 bytes). This is the accepted native package, not a new G5 product.

## Physical evidence and acceptance boundaries

The user's independent review covers the original recording and exports. Local
JSON inspection confirms both exports bind the accepted session and commit, all
50 startup checkpoints completed, and genuine OSG initialization precedes OpenMW
registration. Recording frame inspection corroborates original textured terrain,
architecture and vegetation; it is not a replacement for the supplied full
independent visual review.

| Recorded measurement | Result |
| --- | --- |
| Successful / failed / shader-accepted world loads | 11 / 0 / 11 |
| Door transitions | 2 |
| Active cells / peak resident neighborhood cells | 9 / 18 |
| OSG frames / successful EGL swaps | 17,334 / 17,541 |
| Physics steps | 35,486 |
| Cache maintenance / failures | 295 / 0 |
| Peak / final physical footprint | 292,308,808 / 220,022,600 bytes |
| Initial preparation / maximum commit | 2,516.886 / 8.520 ms |
| Mean display callback interval | 17.068 ms, 17,538 samples |
| Intervals over 50 ms / maximum | 14 / 344.155 ms |
| Final thermal state | nominal |

Grounded movement/collision and continued rendering after interruption were
observed. Automated lifecycle acceptance remains null; observed resume is not
exhaustive lifecycle acceptance. Actual display/GPU FPS and GPU completion remain
unmeasured. Input hashes were unchanged across initial preparation; continuous
full-session immutability is not inferred. Earlier accumulated log sessions are
not all independently classified.

The original evidence remains local under G4 `artifacts/`, excluded from source
and public CI. Review evidence carries only file digests and selected metrics;
no recording, original game asset or private import profile is redistributed.

## Carried limitations

Twelve initial driver messages reject the core `glObjectLabel` call on ES3.0.
Pinned OSG resolves that unsuffixed core entry point despite the advertised
KHR extension. The [KHR_debug specification](https://registry.khronos.org/OpenGL/extensions/KHR/KHR_debug.txt)
requires KHR-suffixed entry points on GLES. G5 provides a capability-selected
dispatch correction without disabling labels, callbacks or message filters.
Its physical effectiveness still needs device validation.

Distant pale/white vegetation is visible. Genuine clear-day fog currently blends
toward RGB (206,227,255), reaching full fog at 8,192 units while the background
uses a different sky color. That can produce pale silhouettes, but the recording
alone does not exclude material, alpha or texture incompatibilities. No arbitrary
brightness/material correction is justified yet. A controlled native comparison
with desktop OpenMW, matched camera/distance/weather and shader/material state
capture remains necessary. G5 retains the accepted rendering math.

Clear-only loading frames and occasional long callbacks remain. Final footprint
and nominal thermal state do not establish peak GPU allocation or sustained
thermal stability. Water/swimming, dynamic sky/weather, actors, full character
physics and gameplay remain unimplemented. Tamriel Rebuilt compatibility has not
been tested. These do not invalidate the demonstrated G4 scope.
