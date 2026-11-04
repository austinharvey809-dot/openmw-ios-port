# Mesa/Zink 25.1.9 Vulkan requirements audit

Audited 2026-11-04 for the iPhone 16 Plus capability-query experiment. This audit examines the exact `mesa-25.1.9` tag, rather than applying the current Zink documentation to an older driver. No Mesa source archive, checkout, binary dependency or build was obtained. Four individual source files were read in memory; the application contains a derived requirements manifest, not Mesa or the Vulkan Profiles implementation.

The previously tested Vulkan cube establishes that the public MoltenVK presentation endpoint works on the developer's physical phone. It does not establish Zink's feature contract. No real-device capability export has been collected by this new application yet. Every device-specific verdict remains pending its first device run.

## Source identity and access

Canonical upstream sources are linked below. Direct upstream GitLab access was unavailable in this environment. The identical tag paths were read through the existing Mesa source mirror using HTTPS. SHA-256 values below identify the UTF-8 source text returned by that transport. The mirror tag was not independently checked against a signed upstream release archive; no stronger provenance claim is made.

| Pinned file | SHA-256 of inspected UTF-8 text |
| --- | --- |
| [VP_ZINK_requirements.json](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/VP_ZINK_requirements.json) | `10fed270d703d477e068e42b838d449130011c7ee012eb4a27b7e7821f002983` |
| [zink_device_info.py](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_device_info.py) | `434a498bc87aaba2be174620074994c050040ee5db168158fbdbe288c0d135a6` |
| [zink_screen.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_screen.c) | `d4a3e4c4964b8e7edcb9d1b0a4c6da7a5fad19a99a24572d8983103844f0adf3` |
| [zink_kopper.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.1.9/src/gallium/drivers/zink/zink_kopper.c) | `2652602f9ff16aecceac26a9daae518bb12421a2b2ea95231aaf68128966e9de` |

The manifest's `sources` array records both canonical and transport URLs. Cached browser renderings differed from the direct HTTP text in some line offsets; the hashes and tag paths above identify the actual text used here. References should therefore use symbols and capability names as well as approximate line locations.

## Exact Vulkan Profiles content

The pinned file uses Vulkan Profiles schema `profiles-0.8.2-271.json`, contains **50 capability blocks** and **13 profiles**:

- `VP_ZINK_gl21_baseline`, `gl30`, `gl31`, `gl32`, `gl33`, `gl40`, `gl41` and `gl42` baseline profiles declare API **1.2.0**.
- `VP_ZINK_gl43_baseline`, `gl44`, `gl45`, `gl46` and `VP_ZINK_gl46_optimal` declare API **1.3.0**.
- Their complete names, labels, API metadata, capability references and optional references are preserved in [the derived manifest](data/mesa-25.1.9-requirements.json).

These formal profile API values differ from the loader's Vulkan 1.0 fallback and from the weaker requirements sufficient to create a particular Zink screen. The application reports both sets separately. A formal-profile failure does not alone prove that no OpenGL scene can run; successful startup does not prove full profile correctness either.

The GL2.1 baseline explicitly includes:

| Category | Exact pinned profile requirement |
| --- | --- |
| Core feature bits | `robustBufferAccess`, `logicOp`, `fillModeNonSolid`, `alphaToOne`, `shaderClipDistance` |
| Extension/spec-version entries | Version 1 or greater of `VK_KHR_maintenance1`, `VK_KHR_create_renderpass2`, `VK_KHR_imageless_framebuffer`, `VK_KHR_timeline_semaphore`, `VK_EXT_custom_border_color`, `VK_EXT_line_rasterization`, `VK_KHR_swapchain_mutable_format`, `VK_KHR_incremental_present`, `VK_EXT_border_color_swizzle`, `VK_KHR_descriptor_update_template` |
| Extension feature bits | `customBorderColorWithoutFormat`, `borderColorSwizzleFromImage`, `rectangularLines` |
| API-feature alternative | All of the extension-path scalar-block-layout/timeline/imageless requirements **or** all Vulkan12-path `scalarBlockLayout`, `drawIndirectCount`, `imagelessFramebuffer`, `timelineSemaphore` bits |
| Line alternative | `bresenhamLines=true` **or** the queried device limit `strictLines=false` |

The alternative paths must be evaluated as **OR between complete AND blocks**. Picking one supported field from each branch would incorrectly produce a pass. The manifest retains this structure using nested `any`/`all` nodes. Higher profiles explicitly include earlier blocks, additional feature/extension/format requirements and numeric minima. The GL4.6 optimal profile's `optionals` remain advisory; they are not prerequisites for an OpenMW GL2 investigation.

Formal-profile extension rows preserve the literal names/spec versions in the upstream JSON. They do not silently replace an absent extension with a core version. The separate runtime checks explicitly permit known core promotions where stated, then check relevant feature bits independently. This prevents a core-promotion convenience from rewriting the pinned formal profile being audited.

Most limits are max-prefixed minimum capacities, compared with `>=`; `strictLines` is compared as a boolean; format/property flag arrays require all named bits. The optional shader-ballot `subgroupSize=64` entry is retained as **manual/unknown** because this lightweight evaluator does not implement the Vulkan registry's complete property-comparison metadata. It is not guessed to be a lower bound. This is an explicit limitation, not a claim that the full Khronos Vulkan Profiles checker has been implemented.

## Driver startup and optional paths

`zink_device_info.py` marks **four** extensions `required=True`: maintenance1, create_renderpass2, imageless_framebuffer and descriptor_update_template. The earlier investigation's abbreviated list omitted the last entry; it is included here. The runtime checks allow their known promotions to Vulkan 1.1/1.2.

`zink_screen.c` rejects startup when **both** `have_KHR_timeline_semaphore` and Vulkan12 `timelineSemaphore` are false. The manifest preserves that source predicate and also checks the usable timeline feature bit: advertising the extension must not be confused with a queried enabled-capable bit or an execution test. The imageless framebuffer feature is likewise reported independently of the extension name.

The same source asserts `maxStorageBufferRange >= 1 << 27`. This capacity is included in runtime checks.

`nullDescriptor` is **not a universal default startup requirement in this revision**. The screen code rejects an explicitly requested descriptor-buffer mode when robustness2 `nullDescriptor` is absent; otherwise that path is disabled. The manifest includes this as an advisory optional-path check, not as a hard failure of every Zink configuration. That check does not cover every prerequisite of descriptor-buffer mode. Do not transplant the latest Mesa requirement table or claim that a later Mesa revision has the same policy.

Feature advertisements, supported format bits and passing comparisons do not execute shader compilation, resource allocation, descriptor updates or OpenGL draws. The app creates no logical device and enables no optional device features. Missing query fields are **unknown**, never fabricated `false` values; a complete extension enumeration can establish that an extension is absent.

## iOS presentation is a separate blocker

Pinned Kopper switches on XCB, Wayland and Win32 surfaces. It does not provide a UIKit/Metal native-window case. Building that frontend remains separate work even if the physical phone reports every capability needed by a selected profile. `VK_EXT_metal_surface` availability is an adaptation prerequisite, not evidence that Zink already uses it.

Kopper requests swapchain usage `TRANSFER_SRC | TRANSFER_DST | SAMPLED | COLOR_ATTACHMENT`, numeric mask **0x17**. The capability app checks that full mask against the actual Metal surface's reported `supportedUsageFlags`, and checks for a graphics/present queue. These are only surface queries: it creates no swapchain and performs no acquire/present or framebuffer readback. Actual drawable allocation, presentation, shader behavior, lifecycle recovery and thermal cost remain unknown until the later Zink experiment.

## Decision rules after the device run

1. Retain the raw device JSON and comparison JSON with the app/source and dependency identifiers. Inspect identity and missing query diagnostics before interpreting totals.
2. Inspect the four required-extension checks, timeline/imageless feature checks and other runtime requirements first. An unsupported hard startup prerequisite is a concrete blocker for that configuration.
3. Inspect `VP_ZINK_gl21_baseline` independently. Unsupported compatibility features identify correctness risks even if Zink might initialize. Unknowns require additional queries or actual implementation tests, not capability overrides.
4. Higher GL profiles and GL4.6 optimal optionals inform later requirements; they must not be mislabeled as requirements for this first GL2 proof.
5. Keep native-window integration and shader/presentation/performance/thermal tests unknown. Passing query rows is permission to investigate the next gate, not evidence of a working OpenMW port or sustained 30 displayed FPS.

No device-specific supported/unsupported verdict is asserted by this document. Use the export from the real iPhone, not a simulator, macOS device table, or synthetic host-test fixture.
