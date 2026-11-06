# ffta2-recomp

Independent FFTA2 European revision-0 resource recovery, Chinese patch tooling,
and macOS native recompilation work. Supply your own A6FP ROM. Source and patch
packages contain no ROM, extracted retail font, save, or generated guest code.

The current experimental test integrates a 2613-glyph Chinese bank and replaces
five opening/classroom event records in the first language slot. Fresh-boot
Chinese pages, teacher portrait/name variable, pagination and continuation were
verified in DeSmuME. Character naming is unchanged. It is a partial translation.
See [the test release notes](docs/cn-font-test.md) and GitHub Releases for a ROM-free
patch. The older 23-glyph single-byte builder remains as a bounded prototype.

The macOS ARM64 backend now builds and reaches the original title screen and
New Game difficulty selection in a real mixed AOT/Tier3 run. Runtime external
font/width/palette/text packs load independently of the unchanged ROM. Game text
rendering hooks are still pending, and fallback coverage is incomplete. See
[the native backend](docs/macos-native.md) and [external localization](docs/native-localization.md).
The patch's Chinese gameplay verification still uses an independent emulator oracle.

## Patch application

Python 3.11+ suffices to apply the generated BPS patch:

```sh
python3 tools/apply_cn_patch.py /path/to/retail.nds /path/to/prologue-cn.bps \
  --output /path/to/prologue-cn.nds
```

The applier verifies patch/source/target CRCs, refuses to overwrite the input
or an existing output, and writes a separate ROM. The builder additionally
requires the exact SHA-256 in config/rom-eu-rev0.json.

## Build the patch and export resources

```sh
python3 -m venv build/venv
build/venv/bin/pip install -r requirements.txt
build/venv/bin/python tools/build_cn_patch.py /path/to/retail.nds \
  --font /path/to/fusion-pixel-12px-monospaced-zh_hans.bdf \
  --output /external/prologue-cn.bps --test-rom /external/prologue-cn.nds
build/venv/bin/python tools/analyze.py /path/to/retail.nds \
  --output /external/extraction
build/venv/bin/python tools/extract_cn_patch.py /path/to/retail.nds \
  /external/prologue-cn.bps --output /external/cn-extraction
build/venv/bin/python tools/extract_asm.py /path/to/retail.nds \
  --output /external/asm
```

Get Fusion Pixel's 2026.10.25 release from
https://github.com/TakWolf/fusion-pixel-font/releases/tag/2026.10.25 and select
its **12px monospaced BDF zh_hans** face. The build receipt records the font hash.
OFL terms are retained in docs/fusion-pixel-OFL.txt. Font binaries are supplied
externally; the BPS includes only the selected additional glyphs.

The extraction outputs resource names and ROM offsets, all four languages'
text tables with raw hex/control tokens/lengths/line counts, character mappings,
width tables, raw font resources, expanded glyph records and an atlas. The CN
extractor applies the patch in memory and validates its receipt before dumping
the modified font and translation map. Linear ARM/Thumb ASM exports include
code and data; their 6552 entry candidates are not proven function boundaries.

See docs/resource-layout.md for format, addresses, traced routines and observed
failure causes; docs/recomp-references.md for the runtime/recompiler decision.

## Recompiler tool on macOS

```sh
git submodule update --init third_party/ndsrecomp
git -C third_party/ndsrecomp submodule update --init external/arm-recomp-core
cmake -S third_party/ndsrecomp/recompiler -B build/recompiler \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/recompiler --target nds_recompile armv5te_decode_test -j 3
build/recompiler/armv5te_decode_test
python3 -m unittest discover -s tests
```

This builds the tool and its instruction tests, not an FFTA2 game executable.
ROM-derived banks belong outside the checkout. Keep native dispatch, software
hardware models and host presentation as separate acceptance gates.

## Emulator verification

`tools/emulator_probe.py` is a diagnostic libretro host, independent of the
recomp runtime. Supply a DeSmuME core, original/patched ROM and external output
directory. It accepts newline-delimited JSON step/input/capture commands and
captures the actual emulator framebuffer. It does not synthesize screenshots.
Use only an owned test save directory. Button IDs follow libretro (A=8, Start=3).

## Licensing

Original project source: GPL-3.0-or-later. Charset data is derived from the
MIT-licensed Rurusachi/ffta2-editor, with its license retained. Fusion Pixel is
OFL-1.1. The ndsrecomp submodule retains its separate component licenses and
is not relicensed here. ROMs and generated guest binaries are excluded from publication.

For full-table CSV export/import and validation, see [the CSV contract](docs/translation-csv.md).


## Public text and address data

The owner authorized publishing extracted text and address information.
`data/text/catalog.csv` contains all 132792 decoded text records, source hashes
and ROM addresses for four language slots. `data/text/machine-cn.csv` contains
slot-0 Terra translation drafts and explicit per-row review status; the matching
manifest records snapshot coverage. This is an incomplete machine translation,
not a full Chinese release. A `translated` row denotes a conservative three-byte
encoding/layout planning check, not game runtime validation.

`data/analysis/` contains numeric text-slot and archive-resource addresses.
These exports contain no ROM payloads, font bitmaps, saves or guest binaries.
Game text remains the property of its respective owners and is not covered by
the project's software license. Supply your own exact-revision ROM to run tools.

Preflight tools reject changed control tokens, byte allocation overflow, extra
lines and wider static text footprints. Dynamic substitutions and the new CJK
renderer still require actual game validation. The original single-byte CN
prototype supports only 23 new glyphs; importing the complete draft table into
that prototype intentionally fails. The three-byte CJK path is experimental.
