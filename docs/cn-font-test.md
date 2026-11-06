# Chinese font integration test release

The test adds a complete 2613-glyph bank for its recorded translation snapshot,
using three-byte D0 bank/code sequences. Five slot-0 event records are replaced:
`event:0:42:1` and `event:0:103:3` through `event:0:103:6`. Character naming is
unchanged. This is a font/dialogue smoke-test patch, not a complete translation.

The original 168 glyph records and widths are preserved. Twenty-three ordinary
code slots serve as bank-local selectors, with 12px advance. Glyphs are read on
demand as 64-byte indexed 2bpp records from verified ROM padding; the 167232-byte
bank is not allocated in the small font heap. The arena uses 9756/10240 bytes.

Indices retain semantic layers: 0 transparent, 1 outline, 2 shadow, 3 foreground.
Colors come from the original palette path. The unmodified palette resource has
five 16-color banks (20 four-color groups, including original same-color filler
groups). The generated glyphs preserve foreground bits while adding indexed
outline/shadow layers, rather than encoding fixed RGB colors. Dark prologue and
lighter classroom dialogue are verified in the actual emulator framebuffer.

## Accepted basic tests

- Fresh boot, title and new game with the recorded patched ROM.
- Both Chinese opening pages and A-button progression.
- Naming screen retains default Luso.
- Three Chinese classroom lines; teacher portrait with name-variable + Chinese.
- Three teacher pages and A-button progression to subsequent original dialogue.
- All five original source hashes, byte capacities and control sequences match.
- Independent BPS application and decoding of all five patched strings match.
- All 2613 font records and their order/hash are verified; rebuilding the font
  from BDF and rebuilding the ROM reproduce the exact tested target SHA-256.

The evidence is in data/analysis/cn-font-smoke.json and the release screenshots.
The oracle is DeSmuME, not native recomp execution. Other rendering paths,
battles, long sessions and save/load are not acceptance claims for this test.
The retail-style async read wait currently has no verified cancellation path.
The +0x25 per-glyph metadata byte was checked in observed consumers; indirect
object accesses outside this test have not been exhaustively proven.

## Apply

Use the release ZIP's Python applier with your own exact A6FP revision-0 ROM:

```sh
python3 tools/apply_cn_patch.py original.nds ffta2-cn-font-test.bps --output chinese-test.nds
```

Source SHA-256: f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59.
Target SHA-256: 9a286e55bc0f6e7e2d5c1ee9ef72b509fcc277a172ebaa4636b0a74a47462921.
The original ROM is never overwritten. No ROM or extracted retail bitmap font
is included in the source tree or the patch bundle; retail glyph relocation is
encoded with BPS SourceCopy.

## Rebuild and extract

Install requirements.txt and GNU arm-none-eabi-as/objcopy. Supply the external
Fusion Pixel 12px monospaced zh_hans BDF (see README and OFL license).

```sh
python tools/build_font_bank.py --font /external/font.bdf \
  --recipe /external/ffta2-cn-font-test.json \
  --output /external/font-bank.bin --index /external/font-bank.json
python tools/cjk_runtime_experiment.py /rom/original.nds \
  --font /external/font.bdf --bank /external/font-bank.bin \
  --bank-index /external/font-bank.json --output /external/test.nds
python tools/extract_bank_patch.py /rom/original.nds /external/ffta2-cn-font-test.bps \
  --output /external/extracted
```

The extractor verifies source, patch, target, font bank and translations before
exporting fonts, numeric resource addresses, character/bank-code/width mapping,
source hashes and text CSVs. Private binary extraction outputs stay external.
The builder deliberately checks its frozen 2613-character test recipe and five
records. Do not feed all reviewed translation drafts into this narrow renderer.
