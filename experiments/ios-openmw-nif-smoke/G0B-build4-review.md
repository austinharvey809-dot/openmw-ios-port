# G0B Build #4 preparation review

Reviewed 2026-11-10 (America/Chicago), branch `ios-port`, HEAD
`7d96b83e617e98fd289c234e1cae32ceefda7c0b`. Ready for manual review of the proposed
Build #4 changes; **not a successful build or parser claim**. No workflow was
dispatched, and nothing was staged, committed or pushed during this review.

## Verified sandbox HTTPS

Git reports `git version 2.56.0.windows.4`. Both requested public, read-only
commands exited 0:

```text
git -c http.sslBackend=openssl -c credential.helper= ls-remote https://github.com/bulletphysics/bullet3.git HEAD
d3afe76132fc76b0f9b2359cbaef47a3766e7fbb  HEAD
d517f2b064d5681aea60ffb6004cc8d7006fc55b  refs/remotes/origin/HEAD

git -c http.sslBackend=openssl -c credential.helper= ls-remote https://gitlab.com/OpenMW/openmw.git HEAD
97722d48f98f14b323c3880a698e8ce81babf7b3  HEAD
```

The shells used `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=Never` for these
requests. URL-specific `http.sslVerify` is unset (Git's verified-TLS default),
and `GIT_SSL_NO_VERIFY` is absent. No credentials, insecure verification option,
global Git configuration change or unrestricted execution was used.

Verified Git HTTPS works through OpenSSL in the restricted sandbox. This
isolates a working alternative to the earlier Windows Schannel failures; it
does not establish that PowerShell HTTPS now works. Use the same command-scoped
OpenSSL override for future public Git research. Filesystem restrictions and
manual approval for GitHub writes/dispatch remain in force.

## CMake compatibility and Build #3 evidence

[Build #3](https://github.com/austinharvey809-dot/openmw-ios-port/actions/runs/42946304046)
was inspected through read-only GitHub API/log calls. At the same HEAD it passed
the source gate (including 23 then-current contract tests) and verified Bullet
acquisition. CMake 4.4.5 failed at Bullet's `CMakeLists.txt:1` with
`Compatibility with CMake < 3.5 has been removed from CMake.` Compile and parser
steps were skipped. Those historical tests do not validate this working diff.

The already-prepared workflow line `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` is
correctly continued inside the single configure command, before its output pipe.
[Official CMake guidance](https://cmake.org/cmake/help/latest/variable/CMAKE_POLICY_VERSION_MINIMUM.html)
documents this external override for old third-party policy declarations.
[Bullet 3.25's CMake source](https://github.com/bulletphysics/bullet3/blob/3.25/CMakeLists.txt)
declares minimum version 2.4.3 and enables `BT_USE_DOUBLE_PRECISION` when
`USE_DOUBLE_PRECISION` is on.

Static review confirmed preservation of:
- native POSIX/C++20 configuration and the genuine OpenMW parser target;
- the separate source, Bullet, configure, compile and parser gates;
- static `BulletCollision` then `LinearMath`, double precision on both and the parser;
- static pinned OSG/OpenThreads and all five audited OSG math precision switches;
- demos/extras disabled, disconnected CMake acquisition, and mandatory runtime cases;
- manual-only dispatch, fail-fast shell pipelines, and always-run diagnostics.

The exact Bullet 3.25 source URL and SHA-512 still match unchanged
`extern/CMakeLists.txt`, `prepare_bullet.py`, and the isolated G0 CMake file:

```text
https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz
7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4
```

No other build-configuration defect was independently demonstrated by this
review. Configure, compile, link and runtime remain gates for the next manually
authorized run; no speculative dependency or upstream-source changes were made.

## Fixture correction and regression coverage

The old runner expected ten fixture inputs plus `fixture-manifest.json`:
11 entries. The directory actually has those files plus
`nif-source-sha256.json`: 12 entries. Therefore a present parser binary would
have encountered `Fixture inventory mismatch` before its first invocation.

The production correction adds only that exact source-manifest filename to
the required set. It remains in the SHA-256 before/after snapshot; the ten inputs
retain their manifest size/hash checks. Unexpected entries, missing entries,
links/directories and changed input bytes remain errors. Source-manifest
contents continue to be checked by the separate required G0 source audit.
No fixture bytes, fixture metadata or parser PASS/FAIL conditions were changed.

Nine added regression methods cover the reviewed inventory reaching all six
process invocations, missing source metadata, missing fixtures, unexpected
NIF/JSON files, a directory replacing metadata, hash/size corruption, metadata
mutation, each parser case's exit-code/marker requirements, and the
wrong-resource failure/diagnostic requirement. These mock processes to test the
harness; they cannot establish genuine parser success.

## Validation performed in this sandbox

| Check | Result |
| --- | --- |
| A–E preservation manifest | 53/53 canonical-LF SHA-256 values match |
| G0 source closure | 14 units, 59 local files and 48 external includes match; 59/59 hashes match |
| E source closure | 21 units, 79 local files and 48 external includes match; 79/79 hashes match |
| D source hashes / E reused build hashes | 53/53 and 5/5 match |
| Pinned OSG source/header hashes | 7/7 match |
| G0 fixtures | 10/10 sizes and raw SHA-256 values match; corrected exact 12-entry inventory passes |
| G0 data preservation | All 12 files retain their initial raw SHA-256 values |
| Build #15 graphics preservation | 9/9 raw SHA-256 values unchanged (below) |
| Milestone F preservation | All 18 tracked files retain their initial raw SHA-256 values; no Git diff |
| OSG checkout | Clean at `9b384d5439977784e5cd250ff8ff7966928ddd27`; workflow and lock pins match |
| Workflow shell syntax | All 7 run blocks pass Git Bash `bash --noprofile --norc -n` |
| Static workflow/build contracts | Manual trigger, gate order, configure arguments, precision and pins pass |
| Git whitespace | `git diff --check` passes; only existing LF/CRLF conversion warnings |
| Git index / HEAD | Unchanged |
| Python suite and syntax | **Unverified**: Python WindowsApps alias cannot launch; 34 test methods present, zero executed locally |
| Python source audits / deterministic regeneration | **Unverified as Python executions**; independent PowerShell hash/include-closure checks above passed |
| CMake configure, native build/link, CTest/parser execution | **Unverified**: no usable local CMake/C++ host toolchain or parser executable |

Hash/include-closure and static-contract checks used PowerShell/.NET.
The OSG Git reads used the same exact-directory, command-scoped
`safe.directory` setting already used by the unchanged D source auditor;
no global trust configuration was changed. No system-wide tools or dependencies
were installed or downloaded for this task. The original Morrowind installation
was not accessed or modified, and no private game assets were added to Git.

### Preserved Build #15 raw SHA-256 values

Paths below are relative to `experiments/ios-osg-smoke/`. These values were
captured before edits and matched afterward; the unfinished graphics work is
still unfinished.

| File | SHA-256 |
| --- | --- |
| `CMakeLists.txt` | `3226dfb98a9a1c6ae2010893ef18eeb383b42215dbabb9b93992fc5a54b3f4d1` |
| `data/osg-lock.json` | `9be3b2672af540fa417861540c230574d1aa78ce530ee478d25d5e40a151e24d` |
| `src/main.mm` | `fb7b07c9f3351a6733444f166741c5d8fa4761c004f0bed1943c1af0c5157692` |
| `src/MipmapObservation.hpp` | `f50b296f4e506fa631ed3e01e80ee6958408143f62bba8a63932ae2b53398600` |
| `src/OSGScene.hpp` | `29c051b7a8b0fceb53ab4ff23de241a85c91f6d0a03b16cf292f28e2d7d6e664` |
| `tools/package_ios.py` | `ce2b96a048ad9338883a6c3cccc178d43de8653a964b8c77d89a5b7c19c8a741` |
| `tools/prepare_osg.py` | `2ff0ac669f8ee096dd362fe54372d07ce5b11001d5a4aa41b0ca8d422d7014a4` |
| `tools/test_integration.py` | `19b48e345775c928a097b8305209da7f13c37627ab4c86b4b4941a504b800dd8` |
| `tools/test_package_ios.py` | `c4296b42f7a4c22bcb829f69afdb9ff2433bc401e6c5089e3ddbe5ee0b2cdca8` |

## Files and manual handoff

Changed during this turn:
- `experiments/ios-openmw-nif-smoke/tools/run_host_cases.py`: exact metadata inventory correction.
- `experiments/ios-openmw-nif-smoke/tools/test_g0_ci.py`: nine targeted regression methods and their imports; retained prior prepared tests.
- `experiments/ios-openmw-nif-smoke/G0B-build4-review.md`: this evidence and handoff record.

The pre-existing workflow edit in
`.github/workflows/ios-openmw-nif-host-smoke.yml` remains part of the proposed
Build #4 diff and was verified without further editing. The nine graphics paths
are pre-existing unrelated changes. Milestones A–F, upstream OpenMW/Bullet,
OSG sources and all NIF fixtures were preserved. No G1/G2 rendering was added.

Before treating Build #4 as successful, require the current 34-test suite and
source audits on a functioning Python runtime, successful configuration and
precision audit, native compilation/link, and the genuine parser's positive and
negative cases. Candidate acceptance is still unverified. Review this diff
manually before any separately authorized stage/commit/push/dispatch.
