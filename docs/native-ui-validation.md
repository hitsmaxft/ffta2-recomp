# Native UI validation — 2026-11-07

This is a partial validation record, not a complete Chinese release. Tests used
an unchanged European A6FP revision-0 ROM, a review-inclusive external pack
(10,565 strings and 37,603 glyphs), and mixed AOT/Tier3 execution on macOS ARM64.
Captures came from the native framebuffer/presentation layer, not the desktop.
ROMs, snapshots, captures and generated guest banks remain outside this repository.

| Surface | Observed exercise | Result |
| --- | --- | --- |
| Prologue dialogue | Teacher and later first-battle dialogue, name variables, multiple pages | Chinese CoreText glyphs displayed; baseline corrected and Latin advances measured from the host font |
| Title | New Game, Load, Continue, Trade, Language; disabled/selected styles | Chinese external atlas labels; original dimensions and five palette banks retained |
| Difficulty/language | Selection, opening, returning; first language entry | Chinese labels displayed; first slot reads Chinese |
| Configuration rows | Four left labels and four right values; selection change; 180 idle VBlanks | Chinese vector text retained; no observed column collision; selected color follows the game |
| Configuration closure | Close, return to main menu, enter inventory | No observed retained Chinese glyphs over the next screen |
| Inventory categories | Edged weapons, bludgeons, ranged weapons, helms, armor, shields, items; wrap around | All opened, quantities and descriptions displayed; text remains English, so Chinese coverage FAILS |
| Inventory navigation | Select another weapon; toggle equipment-job information; scroll consumables from Potion to Eye Drops | Input, scrolling, right quantity columns and descriptions worked; English text only |
| Unit overview | White Mage status, HP/MP, equipment, abilities, empty buff/debuff panel | Opened successfully; background text remains English, so Chinese coverage FAILS |

Changing equipment/assigned abilities, shops, a full battle, save persistence,
widescreen transforms and Windows/Linux builds were not validated by this run.
Opening a character overview does not establish those gates.

## Defects found and changes made

- The vector font baseline was above the retail cell baseline. CoreText now uses
  baseline 14 in a 16-pixel logical cell, at each output scale. Latin character
  advances come from the host font instead of the narrower retail bitmap widths.
- Title package validation used a pixel address displaced by `0x200`. The actual
  resource starts at ROM `0x03C426E0`, with pixels at `0x03C427E0`. Exact-byte
  validation and original allocation bounds remain enforced.
- Text uploaded synchronously through `020835AC` from `0204D658` previously bypassed
  the queued `020A1678` path. Both paths now adapt the allocation owned by `0204D500`.
- Reused menu geometry caused the host layer to disappear when no new glyph draw
  happened in the next VBlank. Text now retains guest-object ownership and is
  removed on hide, replacement, free or reset. New snapshots restore ownership
  and line plans transactionally; see [instant saves](native-savestates.md).
- List planning reserves the original right-column anchor and scrollbar gutter.
  After snapshot restore, it can recover the right-column anchor from the guest
  object instead of requiring an old host pointer map.

## Remaining failures

Inventory, unit overview and several battle labels use SUB-background tile text
rather than the covered 3D text object path. The observer identifies matching
resource IDs without changing tile ownership. A correct native integration must
preserve BG scroll, clipping, palette generations, windows and layer priority.
A screen-wide subtitle overlay would not satisfy this requirement.

Some help strings contain `sprite` or other layout-affecting control tokens;
the current planner rejects these and retains the original rendering. A repeated
source string with conflicting translations was also rejected. Main-menu text
restored from an older diagnostic snapshot can remain in its original cached
texture until the game recreates it. These are not counted as translation passes.

## Reproduction and automated checks

Use `tools/replay_native_ui.py` with external JSON button scenarios and output
folders. It records execution results and text counters beside captures. A
`terminal: false` result establishes continued execution, not visual correctness.

The Python suite (36 tests), Unicode control/layout tests, CoreText scaling and
baseline tests, and transient/cached text lifetime tests passed. Original-ROM
identity is checked by the launcher; no ROM patch is required for the native run.
