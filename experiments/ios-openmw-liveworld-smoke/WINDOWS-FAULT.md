# Captured native access violation

The reported Windows popup is accounted for as a real failed G6 test. The
initial release test passed ownership, transforms and enabled-state cases,
then terminated during the count case with `0xc0000005` and no JSON result.
It was not an ordinary expected rejection and is not included among passes.

The failing executable was preserved. A local Windows Debug API child-process
capture reproduced the null read. DbgHelp/StackWalk64 using local PDB symbols
captured this native call stack:

```text
MWWorld::CellRef::setCount + 0x9e       RVA 0x1fd9de
G6::LiveWorld::setCount + 0x7a          RVA 0x01e69a
main + 0x1174                         RVA 0x005a74
__tmainCRTStartup + 0x1cc
mainCRTStartup + 0x1c
BaseThreadInitThunk + 0x17
RtlUserThreadStart + 0x2c
```

The exception's access type was read, referenced address zero, with RCX zero.
ASLR changes the absolute instruction address between runs. The fault RVA
matches the user's address suffix; an earlier popup's exact loaded module base
was not retained, so that historical absolute address is not independently
symbolized. The original test and reproduced failure agree on the count case.

The original release executable SHA-256 is
`52da92bec580adc962a45f2c8a2accc8f34ea36bc1090f228f44cde5855f844d`.
Relinking the same objects with `-g` generated local symbols; the symbolized
executable SHA-256 is
`3bfc0f422e4a2fb6989558268ffe0ad7ac0b7dcfaf016502688640ca59ba725e`.
Both `.text` sections have RVA 0x1000, virtual size 10,331,494 and SHA-256
`e7227319245f98c782a7e14ee68c91bcac3904ac44ebea2138c74d8a69eccc2e`.
Thus the symbolized stack uses identical optimized instruction bytes, not a
separately invented failure. The review evidence includes fault/section hashes
and stack details; executables and PDBs remain local.

## Cause and correction

The genuine `apps/openmw/mwworld/cellref.cpp` implementation first changes the
count, then calls
`MWBase::Environment::get().getWorld()->removeRefScript(this)` when count is
zero. This isolated slice has genuine ESMStore and WorldModel bindings but no
concrete World service. Release assertions do not stop that null service call.
This is a missing gameplay-service initialization boundary, not evidence of a
corrupt dependency archive or a dangling live-reference owner.

`LiveWorld::setCount(0)` now explicitly rejects the request before any mutation:
`G6 runtime deletion requires genuine MWWorld::World script lifecycle`.
It does not edit upstream code, directly zero raw fields, install a dummy World
or silently omit script cleanup. Nonzero count changes still call the genuine
setter; content-file deleted references still use genuine CellStore semantics.
Full runtime deletion remains unsupported until real World integration.

The corrected native count case has 12 assertions, including unchanged count
after rejection, valid nonzero update/restoration and negative-count rejection.
A separate expected-rejection case requires exit code 1 and the exact runtime
deletion diagnostic. Access violations, signals, unrelated errors, wrong
assertion counts, timeouts and spawn failures cannot satisfy that gate.

Native assertion progress is retained on stderr, and each subprocess's exit
code/hex value, streams, byte counts, signal and partial results are saved.
The runner temporarily prevents only child-process Windows fault dialogs and
restores the previous process error mode. It neither suppresses test failure
nor alters machine-wide security/error settings. `tools/debug_windows.py`
can capture another own-child native fault with local symbols if needed.

The corrected 24-case native suite passes on Windows. macOS and iPhoneOS
behavior still requires their real toolchains; this report makes no Apple
execution or device rendering claim.
