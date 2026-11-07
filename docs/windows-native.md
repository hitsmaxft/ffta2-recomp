# Windows native backend

Windows uses the same pinned guest banks and SDL3 frontend as macOS. DirectWrite
provides vector glyph coverage; BCrypt provides SHA-256. The NDS 3D renderer is
currently the software renderer. SDL's presentation driver is a separate layer.

## Build on Windows

Install CMake 3.24+, Python 3.12, Visual Studio 2022 C++ tools (or llvm-mingw), and
an SDL3 development package matching the host architecture. Initialize the pinned
recursive submodules. Generate the title and open FreeBIOS banks locally using
the existing extraction/recompilation workflow; keep these outside the checkout.

```powershell
cmake -S . -B build/windows-x64 -A x64 `
  -DFFTA2_BANK_DIR=C:/private/ffta2/title-banks `
  -DFFTA2_BIOS_BANK_DIR=C:/private/ffta2/freebios-banks `
  -DSDL3_DIR=C:/dependencies/SDL3/cmake
cmake --build build/windows-x64 --config Release --target nds_runner --parallel 3
```

Place the matching SDL3 DLL and compiler runtime DLLs beside the executable.
The build reserves a 64 MiB main-thread stack for the nested dual-CPU runtime.
For a macOS/Linux cross build, use `cmake/toolchains/windows-llvm-mingw.cmake`
and set `LLVM_MINGW_ROOT` to an extracted llvm-mingw distribution. Cross-building
an executable is not a Windows gameplay test.

```powershell
python tools/run_native.py --rom C:/private/ffta2/retail.nds `
  --session C:/private/ffta2/session `
  --binary build/windows-x64/backend/Release/ffta2-recomp.exe `
  --localization C:/private/ffta2/native-localization
```

The required unmodified ROM SHA-256 is listed in the [README](../README.md).
The launcher rejects a different hash before executing the native program.
The localization directory is remembered in the external session directory.
Bitmap menu fallback and machine-review pack inclusion are enabled by default.
`--no-bitmap-fallback` and the pack builder's `--no-include-review` are explicit
opt-outs. Untranslated strings and unsupported rendering paths remain incomplete.

## Font selection

DirectWrite checks Microsoft YaHei, DengXian, SimHei, Noto Sans CJK SC,
WenQuanYi Zen Hei, Yu Gothic and Segoe UI, checking glyph availability rather than
assuming that a font-family name supplies Chinese. No proprietary font is bundled.
An external font file can be selected without system-wide installation:

```powershell
python tools/fetch_wqy_font.py --output build/fonts
$env:FFTA2_FONT_FILE = (Resolve-Path build/fonts/wqy-zenhei/wqy-zenhei.ttc).Path
```

The downloader uses the upstream WenQuanYi 0.9.45 archive, checks its SHA-256 and
keeps its license and a download receipt. The font remains outside public source.
See [WenQuanYi upstream](https://sourceforge.net/projects/wqy/files/wqy-zenhei/)
and the [DirectWrite coverage API](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwriteglyphrunanalysis-createalphatexture).

## Asset-free Windows checks

```powershell
cmake -S . -B build/windows-host -DFFTA2_HOST_ONLY=ON -A x64
cmake --build build/windows-host --config Release --parallel 3
ctest --test-dir build/windows-host -C Release --output-on-failure
```

The Windows CI job executes these checks on a Windows runner without retail
assets. It checks Chinese glyph coverage, scaling/baseline, bitmap palette roles,
text clipping/lifetime, snapshot-frame restoration, control-safe layout and hash
vectors. These host tests do not establish full Windows gameplay coverage.

## Validation record (2026-11-07)

- Windows runner / MSVC: all three asset-free CTest cases passed in
  [Windows host validation](https://github.com/hitsmaxft/ffta2-recomp/actions/runs/42325860128).
- macOS ARM64: full runtime build and all three host tests passed; 36 Python tests
  passed. Existing native inventory captures verify separate Chinese category,
  item names and quantity columns.
- Windows x64 full runtime cross-build completed with llvm-mingw (PE32+ x86-64).
  Host executables passed the same three
  tests under Wine 11, using an external WenQuanYi font. The full executable
  boots the unchanged ROM with 10,565 external text entries, 37,603 glyphs and
  five palettes; SDL Direct3D presentation and WASAPI initialize successfully.
  This compatibility-layer run is not a Windows performance benchmark.

MSVC CI covers the host layer only. Full retail gameplay on a physical Windows
machine has not been validated; do not infer that from the asset-free CI result.
