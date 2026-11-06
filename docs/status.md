# Local status, 2026-11-06

## Accepted local gates

- Exact supplied A6FP revision 0 ROM identified and unchanged after patch work.
- Resource extraction: 1024 archive buckets, 1285 subfiles; 132792 string-table
  entries across four languages, including placeholders and duplicates.
- Font extraction: original 168 glyphs, UTF-8 labels, rendered western mapping,
  widths, packed glyph data, expanded 2bpp data and atlas.
- CN patch: first-language slot 0 opening event block 42 string 1; two pages;
  20 additional Fusion Pixel 12px glyphs, total 188. Original glyph records
  remain source-copied. Appended resources occupy verified ROM tail padding.
- BPS: 2503 bytes, two builds deterministic; CRC-checked apply reconstructs the
  declared target SHA-256. The ROM-free patch ZIP uses an explicit allowlist.
- Actual DeSmuME macOS arm64 oracle: boot, title, New Game, first CN page,
  A-button transition to second CN page, then original English continuation.
  Screenshots come directly from the core video callback. The scene's black
  background is original; original-English and patched-Chinese captures prove
  that distinction. Save states, RAM dumps, failed-patch checkpoints, receipts
  and captures remain outside the source checkout.
- ASM exports: 20 modules (ARM9, ARM7, 18 overlays), separate linear ARM/Thumb
  listings, original binaries, module metadata, 6552 candidate entry rows.
  Fifteen routines have evidence-based inferred semantic labels. None of the
  automatic candidates is asserted to be a proven whole-function boundary.
- macOS arm64 builds of the pinned nds_recompile tool and ARMv5TE decode test
  pass; three BPS rejection/relocation checks and Python compile checks pass.

## Remaining gates

- Full prologue/game translation, translated language-menu bitmap labels and
  more than 23 additional ordinary single-byte glyph codes.
- Font/heap stress across menus, battles and long sessions; save/load testing
  and physical Nintendo DS validation.
- Native FFTA2 ARM9/ARM7/overlay bank discovery, recompilation and gameplay.
- Actual macOS game host backend and runtime Unicode/font replacement. The
  emulator oracle must never be presented as satisfying those native gates.

The two diagnosed failures were repaired from measured evidence: initial
0x4000 arena allocation returned null, and pixel index 2 encoded shadow rather
than foreground. Final arena need is 0x277C within 0x2800; glyph strokes use
foreground index 3. No guest script-control pair was removed or bypassed.

## Classroom CSV checkpoint

The current CSV-driven variant adds 23 glyphs (191 total) and patches five
records: the opening monologue, the teacher's first three lines, and only the
first page addressing Luso. Naming UI and the chosen Luso name remain intact.
Trimmed blank glyph rows follow the original format; arena use is 9876 bytes
inside the accepted 10240-byte arena, confirmed in emulator RAM.

From a fresh ROM boot, frame 9751 shows the classroom, teacher portrait, Luso
Clemens and Chinese dialogue together: "你先留下!". The actual core screenshot,
matching ROM/patch/CSV hashes, RAM and save state remain external. The patch is
2532 bytes and a repeated CSV build is deterministic.

RFC 4180 CSV export emits 132792 rows. Import accepts full or sparse catalogs,
validates original byte hashes and script-token order, and emits Unicode JSON.
The ROM builder checks imported byte identities against the supplied ROM. Seven
focused BPS/CSV tests pass. Full CSV import is supported; full ROM translation
insertion beyond the documented glyph/allocation limits is still pending.

## Terra machine-translation work and publication snapshot

Terra workers are translating the first language slot. The public CSV snapshot
is deliberately incomplete: see data/text/manifest.json for exact counts.
The importer ignores review/untranslated rows. Planning-accepted rows satisfy
conservative three-byte capacity/layout checks, but the CJK runtime bank
experiment remains separate and unverified in this publication snapshot.

All 33198 slot-0 addresses, original lengths and source hashes were verified
against the pinned ROM with tools/text_resources.py; no shared allocations
were found. Eighteen focused BPS, catalog, resource-boundary and translation
safety tests pass. The capacity preflight also exposed a wider static line in
the older classroom sample; the sample's prior screen verification is limited
to its documented checkpoint and is not a general layout guarantee.

Public data comprises text CSVs and numeric address maps only. ROMs, guest
binaries, extracted glyph bitmaps, saves, states and emulator cores remain
external. Publication does not change the native gameplay or complete
translation acceptance gates.
