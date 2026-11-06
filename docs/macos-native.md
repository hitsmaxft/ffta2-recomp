# macOS ARM64 backend

The backend compiles ARM9/ARM7 AOT C banks into a native arm64 Mach-O executable.
NDS device models and software 2D/3D rendering come from the pinned ndsrecomp
runtime; SDL3 provides host presentation. Tier3 fallback remains visible and is
not equivalent to complete native coverage. The original ROM stays unchanged.

## Build

Install CMake, the Apple command-line tools and SDL3 (Homebrew `sdl3`). Initialize
`third_party/ndsrecomp`, its `external/arm-recomp-core` and `third_party/freebios`
submodules, and this project's `third_party/recomp-ui`. Build the recompiler as
described in README, then prepare title banks using `tools/prepare_recomp.py`.
All generated game code must stay outside the repository. Generate the open
replacement BIOS banks in a second external directory:

```sh
build/recompiler/nds_recompile \
  --config third_party/ndsrecomp/bios/freebios9.toml \
  --bin third_party/ndsrecomp/third_party/freebios/drastic_bios_arm9.bin \
  --out /external/open-bios-banks --bank freebios_arm9
build/recompiler/nds_recompile \
  --config third_party/ndsrecomp/bios/freebios7.toml \
  --bin third_party/ndsrecomp/third_party/freebios/drastic_bios_arm7.bin \
  --out /external/open-bios-banks --bank freebios_arm7
cmake -S . -B build/macos -G 'Unix Makefiles' \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++ -DCMAKE_PREFIX_PATH=/opt/homebrew \
  -DFFTA2_BANK_DIR=/external/title-banks \
  -DFFTA2_BIOS_BANK_DIR=/external/open-bios-banks
cmake --build build/macos --target nds_runner -j3
```

`tools/stage_runtime.py` copies tracked upstream files into the build directory
and applies explicit, guarded Darwin platform adaptations. It never edits the
canonical submodule. A receipt records source and adapted hashes. Only generated
FreeBIOS banks are linked; this backend does not require proprietary BIOS dumps.
The optional Linux/Windows live compiler plumbing is adapted to Darwin dynamic
libraries, but live library compilation/loading has not yet been validated.

## Run with external localization

```sh
python3 tools/run_native.py --rom /external/original.nds \
  --session /external/native-session \
  --localization /external/native-localization
```

The launcher checks the exact original ROM SHA256, uses direct boot with open
FreeBIOS and generated firmware, and keeps firmware/diagnostics/identity outside
the checkout. Saves are disabled unless an explicit `--save` path is supplied.
`--serve` selects a headless diagnostic server; the default uses SDL. No patched
ROM is needed. External font/width/palette/text resources are described in
[native-localization.md](native-localization.md).

## Evidence and limits

A real ARM64 headless run with the first main-bank set reached the retail title
screen at 1000 VBlanks. An A-button press advanced New Game to difficulty
selection; another A press continued startup. Framebuffers came from the actual
NDS GPU models, not a resource viewer or synthetic reconstruction. Early captures
at 130 and 600 VBlanks were black during startup.

At 1142 ARM9 VBlanks, ARM9 executed 67,234,920 instructions, including 54,899,803
Tier3 instructions; ARM7 executed 24,485,716, including 16,198,962 Tier3
instructions. Neither CPU rejected a clean-RAM dispatch. This is mixed AOT and
interpreter execution with substantial remaining fallback. An expanded bank set
was generated from real RAM/coverage to improve this; its function counts alone
are not evidence of improved execution.

The expanded bank set repeated a 1000-VBlank boot with the full external font
pack loaded: ARM9 used 320,200 Tier3 instructions of 55,547,457 total (0.58%);
ARM7 used 298,368 of 19,737,090 (1.51%). The combined GPU frame at the same
VBlank was byte-identical to the earlier set. Both clean-RAM reject counts were
zero. These are startup measurements, not full-game coverage.

SDL3 selected Metal presentation and CoreAudio, then closed gracefully after
4673 presented frames. A queried 3446-frame snapshot reported 3446 real presents
and zero synthetic presents. CoreAudio was open and unmuted; the guest audio
ring produced nonzero stereo PCM (1024 tested frames, range -3104..3104). This
proves generated samples, not listening verification. The measured title run
was about 36 FPS with audio underruns, so full-speed playback is not achieved.
Computer-use inspection was unavailable because its native pipe failed to
start; actual window pixels and physical keyboard operation remain unverified.
Save-file round trips and game-rendered Unicode replacement remain pending. A successful external pack load is recorded
separately from a successful game text-rendering hook. ROM-derived banks, native
executables containing them, screenshots, firmware and saves remain local and
are excluded from publication.
