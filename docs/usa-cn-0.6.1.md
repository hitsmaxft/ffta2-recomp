# USA Chinese ROM 0.6.1 (local development)

USA A6FE revision 0 is the primary target. Its original SHA-256 is
`3b5d469aae5d351de31a89cf2bf592c98cb5b68cb4efc30b34426a119fee2372`.
The supplied private human-translation 0.6 reference has SHA-256
`b2c1a20fc5ce649e658e94ef7e9c91ee632119e7642a04ed4825acc840a37fee`.
No text, glyph map, reference ROM, font payload or generated release is published.

## Agreed scope

- Use the supplied 0.6 human text for USA, replacing machine-translation input.
- Maintain independent original-ROM and native localization implementations.
  They share IDs, import schemas and validation; neither runtime depends on the
  other. A patched ROM needs no sidecar assets or host subtitle renderer.
- Reuse legacy glyph numbers for import mapping, without imposing its original
  code-injection architecture on the common data layer.
- Keep source bytes, addresses, widths, palette roles and control tokens auditable.
  Never let a model translate script tokens; unverified Unicode recovery remains
  review data, not an instruction to rewrite the original human payload.
- Keep the USA human text, exported CSVs/fonts, ROMs and BPS packages external and
  private until the owner explicitly revisits publication. Tools, synthetic tests,
  hashes, addresses and this implementation plan may be tracked.

## Implementation boundaries

`usa_text.py` provides bounded archive-slot lookup and token-aware normalization.
`export_usa_cn.py` exports a private RFC4180 UTF-8 BOM catalog and source hashes,
original/translated addresses, glyph IDs, widths, palettes and font assets.
An optional glyph-to-Unicode map is explicitly review-only. ROM construction
uses byte-exact human source tokens, not OCR output or machine translation.

`usa_cn_release.py` is the ROM output backend. It verifies both input hashes,
retains the isolated 0.6 compatibility code, applies individually guarded fixes,
rebuilds ordinary NitroFS and generates a source-copy BPS from the original USA
ROM. Independent BPS application must reconstruct the candidate exactly. The
compatibility code remains private input; it is not copied into public source.

`title_texture.py` contains bounded atlas rendering shared by ROM and native
outputs. The ROM backend writes the localized pixels into the archive; the
native builder emits an external override. Header, rectangles, dimensions,
allocation size and all five palette banks are preserved in both cases.
The title face, colored rim and displaced lower shadow have independent palette
roles; label-wide composition prevents adjacent outlines from erasing strokes.

The native runtime retains platform font/render interfaces and stable Unicode
resource IDs. Existing EU native addresses/banks remain EU-only. Porting USA
dispatch and native hooks is a separate acceptance gate; do not bypass the ROM
hash guard or claim the USA ROM test establishes native USA execution.

## Evidenced fixes

The reference's font copy bound was 0x41000, but its actual allocation remained
0x2400 inside a 0x7800 child heap. A live emulator RAM export showed 0x40410
bytes in use, beyond the owned allocation. The candidate grows heap 9 to 0x47000
and its font allocation/initialization to 0x41000. The fixed compatibility-code
addresses remain stable because the font resource order and sizes are preserved.

Two widened-cell ASCII fallback reads reverted to byte indexing. Guarded
instruction changes restore a two-byte cell stride at 0x0237CAE8/0x0237CBB8.
These remain isolated version-specific patches, not a generic decoder API.

Seven text records had NUL gaps before their final C1/C2 controls. Move those
gaps to the end of each existing allocation, preserving every nonzero token,
its order, parameters, line metadata and capacity. Do not globally restore
English controls over a human translation: other differences may be deliberate
localization or require individual script review.

The mandatory `usa_layout_audit.py` preflight compares all language-0 records
using the original and translated glyph-record width indices, image extents,
explicit C0 newlines, coalesced C1/C3 page boundaries and C8 option boundaries.
It reads icon widths through the guarded USA CB dispatch and com_key atlas rather
than guessing an icon advance. Unknown dynamic substitutions remain review gates.
The English footprint is a comparison baseline, not a measured widget boundary.

The private release CSV records six length corrections: three missing newlines
and three shorter one-line summaries. `usa_text_edits.py` verifies each source
hash and protected control sequence; Unicode replacement uses a visually reviewed
glyph subset. Longer strings append to their owning message block, with every
IDX boundary rebuilt and resources relocated through the archive index. No string
is squeezed into an old allocation or silently truncated. Unrevised human tokens
remain unchanged. The baseline and each release retain separate version records.

## Local construction

```sh
python3 tools/usa_cn_release.py \
  --original /external/usa-original.nds \
  --reference /external/usa-human-0.6.nds \
  --ui-font /external/fusion-pixel-12px-monospaced-zh_hans.bdf \
  --edits-csv /external/0.6.1/text-revisions.csv \
  --approved-map /external/0.6.1/approved-glyph-subset.json \
  --layout-policy /external/0.6.1/layout-policy.json \
  --output /external/usa-0.6.1

python3 tools/export_usa_cn.py \
  --original /external/usa-original.nds \
  --reference /external/usa-human-0.6.nds \
  --candidate /external/usa-0.6.1/ffta2-usa-cn-0.6.1.nds \
  --revision-manifest /external/usa-0.6.1/receipt.json \
  --glyph-map /external/reviewed-glyph-map.json \
  --output /external/usa-human-export
```

Outputs are private, refuse existing output directories and never overwrite inputs.
The release receipt lists exact guarded changes and hashes, not Chinese content.
Keep the Fusion Pixel license with any local package containing its derived UI
artwork; do not redistribute unrelated font assets.
Without the private correction CSV, the supplied 0.6 source fails the six known
length checks. A failed preflight writes diagnostics and refuses a release ROM/BPS.

The owner authorized a separate private `hitsmaxft/ffta2-us-cn` repository to back
up the original and human 0.6 ROMs through LFS, store private text/revision CSVs,
and build locally. No online build workflow is used. That authorization does not
extend to this public repository or public releases.

## Validation gates

Check original identity, independent patch reconstruction, all 33198 language-0
text records, unchanged human tokens/line metadata, font ownership and control
termination. Use a dedicated emulator with recorded frame-counted inputs and
local checkpoints for title, prologue, naming, classroom dialogue and menus.
A screenshot must be an actual emulator framebuffer; decoded-font previews do
not count. A basic local test is not a full campaign/mission playthrough.
