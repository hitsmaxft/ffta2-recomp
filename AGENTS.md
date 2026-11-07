# Project policy

Build an independent macOS native FFTA2 recompilation project, pinned initially
to the supplied European A6FP revision 0 ROM. Runtime Chinese text and font
replacement is part of the architecture. Do not change sibling projects or their
processes. Read upstream policies before editing vendored code.

Use English for source and documentation. Keep ROMs, extracted assets, saves,
generated game code and captures outside the checkout. Build artifacts belong
in root build/. Preserve upstream licenses. Never describe a resource viewer,
synthetic frame or interpreter-only run as native game execution. Report ARM9,
ARM7, fallback counts, rendered screens, input, audio and save gates separately.
Missing native dispatches must be visible. Avoid silent instruction fallback.

Runtime localization must use stable resource IDs and Unicode host strings;
do not patch the original ROM or force Chinese into the retail one-byte charset.
Keep original control-token streams and script effects available to the guest.
Native renderer integration and resource extraction are separate acceptance gates.


The owner explicitly authorized publishing decoded text CSVs, source hashes,
address maps and derived translation tables under data/. This exception does
not include ROM payloads, extracted binary assets, saves, generated guest code,
private execution paths or credentials. Preserve per-row translation status;
never label incomplete translation tables as a complete Chinese release.

## Build environment and development workflow

- Use CMake 3.24+, Python 3.11+, a C++20 compiler and SDL3. Keep the pinned
  `ndsrecomp`, `arm-recomp-core` and `recomp-ui` revisions; initialize recursive
  submodules. Do not edit upstream checkouts to make a local build pass.
- Generate ROM-derived title banks and open FreeBIOS banks outside this checkout.
  Configure with `FFTA2_BANK_DIR` and `FFTA2_BIOS_BANK_DIR`; never publish generated
  guest C, retail binaries, ROMs, save files or screenshots containing private paths.
- Use separate `build/macos`, `build/windows-x64` and `build/windows-arm64`
  directories. Keep downloads/toolchains under `build/toolchains` or an external
  reusable cache. Limit compile parallelism to 3 by default; do not run concurrent
  builds against the same directory. Remove redundant rebuildable caches after
  successful validation, preserving evidence and active sessions.
- `tools/stage_runtime.py` is the only place for pinned upstream adaptations.
  Re-run CMake configuration after changing it. Its transformations must be guarded
  and reproducible from pristine upstream sources; never rely on edits under build/.
- Use `tools/run_native.py` with an unchanged European revision-0 ROM and an external
  localization directory. Runtime Chinese text/font replacement and ROM-patch tools
  share source tables, but the native launcher must not require a prepatched ROM.
- Include machine-translation review rows in test packs by default, keeping their
  review status and validating original source hashes and all control tokens.
  Keep palette-aware bitmap Chinese enabled as the fallback for surfaces whose
  vector layout has not been validated. Naming remains unchanged. Reject unsafe
  layouts rather than overflowing guest allocations.

## Platform fonts and validation

- macOS uses CoreText and PingFang when available. On platforms without PingFang,
  the agent must select an installed CJK sans-serif font, for example Microsoft
  YaHei, DengXian, SimHei or Noto Sans CJK. Check actual Chinese glyph coverage;
  accepting a substituted Latin-only face is not sufficient.
- If no suitable system face exists, obtain the open-source WenQuanYi font from
  its upstream distribution, record the download hash and license, and use an
  external font path. Never copy or redistribute Apple's or Microsoft's fonts.
- Keep font rasterization behind `src/host/font.h`, platform hashing behind a
  host interface, and SDL presentation separate from title-specific text hooks.
  Keep Windows and Linux extension points; do not introduce macOS APIs into
  common text layout or localization code.
- Validate control/width rejection, font scaling, palette roles, transient/cached
  text lifetime and snapshot restoration. For UI text, validate final native
  renderer captures, list scrolling, quantity columns, menu closure and restored
  states. Resolve positions after guest matrix/viewport transforms; scratch widget
  coordinates are not screen coordinates and can be reused across list rows.
- Report host-unit tests, cross-compilation, actual Windows execution and actual
  game execution separately. Wine/CI smoke tests are not proof of a complete
  Windows gameplay session. Public CI must not download or upload retail assets.
- Before publication, stage explicit source/document paths and run
  `python tools/check_public_tree.py` against the staged blobs.

## Repeatable regression scenes

- Prefer `tools/native_scenario.py` with a dedicated headless session, an exact-build
  named scene and recorded DS input. Restore RAM checkpoints for repeated checks;
  do not navigate manually and capture every step to reconstruct a known scene.
- Approve the baseline visually once, then compare both presentation hashes and
  scheduler/CPU timestamps. Generate images on divergence or at an intentional
  visual checkpoint. SDL window behavior still needs actual presentation captures.
- Never bypass snapshot build/ROM/font checks or use another agent/player's RAM
  slots. Keep recordings, states and reports external. A matching replay confirms
  reproducibility, not translation accuracy or complete gameplay coverage.

## USA Chinese 0.6.1 development direction

- USA A6FE revision 0 (config/rom-us-rev0.json) is now the primary validation
  target. Keep EU identities, address maps and banks separate. Existing EU native
  dispatches are not validated for USA; never bypass the launcher identity gate.
- Maintain two independent implementations: an original-ROM patch backend
  (codec, font/width/palette packing, archive rebuilding and bounded guest hooks)
  and native localization backends (external Unicode resources and host rendering).
  Share stable text IDs and import data, not runtime dependencies. A patched ROM
  must run directly in an emulator without host overlays or sidecar assets.
- The supplied USA human translation 0.6 is the source for 0.6.1, replacing
  machine-translation input for this target. Keep its original text, derived CSVs,
  glyph maps, font assets, reference code, ROMs, BPS files and packages PRIVATE
  and outside this checkout. Do not publish them to Git or releases until the
  user explicitly revisits publication. This overrides the earlier data/ export
  exception for this USA source. Tools, schemas, addresses, hashes, synthetic
  tests and implementation plans may be tracked.
- Reuse legacy glyph numbers as import/export mapping only. Do not treat OCR
  candidates as approved Unicode text. Preserve byte-exact 0.6 payloads while
  validating a ROM compatibility candidate; do not silently replace controls,
  untranslated lines or uncertain characters with machine-generated content.
- Fix only guarded, evidenced faults. Bounds must match the actual owning heap
  and allocation, not just a font-copy limit. Rebuild NitroFS normally, preserve
  resource IDs, verify BPS independently and test game progression from local
  checkpoints. Report local candidate validation separately from a full playthrough.
- The owner subsequently authorized ROM/text backups only in the separate private
  `hitsmaxft/ffta2-us-cn` repository, using LFS and local builds without workflows.
  That exception does not permit retail binaries or supplied human text in this
  public repository. Keep generic tooling here and versioned private release data
  there. Verify private visibility before pushing private inputs.
