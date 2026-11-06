# European revision 0 resource evidence

Input: A6FP, revision 0, 134217728 bytes.
SHA-256: f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59.

The NitroFS file master/pc.bin begins at ROM 0x001AA000 and contains the
hash-indexed archive; master/pc.idx starts at 0x0542AE00. The index has 1024
buckets and 1285 resolved subfiles. Name hashing is h = h * 37 + byte, modulo
1024. Collision groups discriminate by a character and its filename position.
Archive entries contain packed offsets and sizes, not literal filenames.

Internal IDX/PAK pairs have a four-byte header followed by six-byte records.
The packed record offset is ((word & 0x07ffffff) >> 3) * 4. The next record
sets the current subfile end. Low three bits identify absent entries; equal
consecutive offsets may represent empty entries. A string table starts with
u16 count followed by {u32 byte_length, u32 relative_offset, u16 line_count}.
Quest/rumor/paper strings instead have a 14-byte header and a single string.
All numeric fields are little endian. Control opcodes consume two bytes.

Each of the four language variants contains 9276 general-message strings,
23154 event strings, 512 quest strings, 128 rumors and 128 paper strings.
Counts include unused placeholders, duplicated dialogue and empty strings;
these are resource entries, not unique lines or translated coverage.
The decoded contents identify slot 0 as English. Other language slot names
must be inferred from the extracted contents rather than guessed from the
filename number.

| Resource | Original ROM offset | Size |
| --- | --- | --- |
| menu/font/UseMoji_table.bin | 0x04F09AC4 | 0x110 |
| menu/font/UseMoji_image.bin | 0x04F07C34 | 0x1E90 |
| menu/font/FontWidthTable.bin | 0x04EC5AE8 | 0xAC |
| menu/font/fontpalette.bin | 0x04F00470 | 0xA4 |

The UTF-8-BOM character table has 168 entries, followed by zero padding.
Some table labels differ from the actual glyph art: e.g. the table's
backslash slot displays a yen glyph. Preserve both the table labels and the
renderer-oriented western mapping; neither is a Unicode font cmap.

The image starts with u16 glyph_count and unaligned u32 offsets. Each glyph
has a byte record length, a nibble-packed top/bottom blank-row count and a
u16 glyph index. Pixel payload consists of four bytes per scanline, sixteen
2-bit pixels in low-to-high order. 0xFF in the row-padding byte means blank.
The expansion routine produces exactly 64 bytes (16 by 16, 2bpp).
The width table contains u16 count and one byte per glyph. Text code 1 selects
glyph index 0. Text code 0 is blank/terminating context; 0xC0-0xFF are control
bytes according to (byte & 0xC0) == 0xC0. This leaves 0xA9-0xBF for 23
additional ordinary glyphs without changing the script decoder.

# Traced ARM9 routines

These are inferred semantic labels, not retail debug symbols. Original
instructions and call/dataflow evidence support the labels. Full function
boundaries must still be qualified before AOT acceptance.

| RAM address | Inferred role |
| --- | --- |
| 0x020842F8 | Load character table |
| 0x02084344 | Load glyph image resource and count |
| 0x02084410 | Initialize fixed font arena and palette resources |
| 0x020845F0 | Expand one glyph to 16x16 2bpp |
| 0x020846D0 | Convert expanded glyph for tiled display |
| 0x020848A0 | Load language-specific JD message index |
| 0x02084BC8 | Load JD message subtable synchronously |
| 0x0204A95C | Test control-byte high bits |
| 0x0204A98C | Extract control opcode |
| 0x0201FE38 | Open named archive resource |
| 0x0201FEA0 | Obtain opened resource size |
| 0x0201FFA4 | Read resource synchronously |
| 0x0201FFE8 | Close resource handle |
| 0x0201F134 | Allocate from numbered heap |

ARM9 RAM 0x02000000 maps to original ROM 0x00004000. Overlays have separate
load addresses and lifetimes; do not reuse that mapping for them.

# CN prototype and failure evidence

The opening classroom monologue is event language 0, block 42, string 1.
Its original text starts at ROM 0x023B800E with 107 allocated bytes. The
38-byte translation retains the non-newline script control pairs exactly.
Only this two-page monologue is translated; menus and the remaining prologue
remain untranslated. Runtime Unicode replacement remains a separate goal.

Fusion Pixel 12px monospaced zh_hans, release 2026.10.25 (OFL-1.1), supplies
20 additional glyphs. A 12px cell is placed inside the original 16px canvas.
Original glyph records and widths are copied unchanged using BPS SourceCopy.
New image/table/width data starts at verified 0xFF tail space 0x07AFB340,
0x07AFD780 and 0x07AFD8E0. The original ROM size remains 128 MiB.

The pc.bin FAT extent is extended to encompass the added records. This creates
an intentional containing extent overlapping existing later NitroFS files;
their bytes and FAT records are preserved. Only pc.idx redirects the three
font resources. Header used-size and CRC16 are updated. Rebuilding through
another NitroFS packer is not covered by this layout contract.

The first experiment requested a 0x4000 font arena and black-screened. Emulator
RAM showed the arena pointer remained zero: heap 9 could not satisfy it.
The actual expanded resource need is 10108 (0x277C) bytes. The final 0x2800
arena fits both the resources and the existing free block. The three guarded
ARM immediate operands changed at 0x0208426C, 0x02084418 and 0x02084428;
no branch/return is bypassed. Emulator RAM confirms count 188, nonzero arena
and final used offset 0x277C. Broader title/heap stress is not validated.

A second visual failure was diagnosed against the unpatched oracle at the
same new-game checkpoint: the black background was intentional, but only the
ASCII punctuation appeared in the CN version. RAM matched the appended glyph
resource exactly. The original font uses index 3 for foreground strokes and
index 2 for shadow pixels. Encoding monochrome strokes as index 2 made them
invisible on this scene. Rebuilding the selected glyphs with foreground 3
fixed the actual emulator framebuffer without changing guest control flow.
