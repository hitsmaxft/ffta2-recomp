#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the private USA 0.6.1 ROM patch from a user's original and 0.6 data.

Neither input, decoded text, nor generated release data belongs in public Git.
The 0.6 engine is an isolated compatibility input, not a native dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import shutil
import ndspy.rom
from build_cn_patch import Archive, u16, u32
from bps import build, apply
from package_test_rom import difference_segments
from usa_text import slots, repair_terminal_padding

ROOT = Path(__file__).resolve().parents[1]
USA_SHA = '3b5d469aae5d351de31a89cf2bf592c98cb5b68cb4efc30b34426a119fee2372'
REFERENCE_SHA = 'b2c1a20fc5ce649e658e94ef7e9c91ee632119e7642a04ed4825acc840a37fee'
FONT_BASE = 0x0237c8b0


def sha(data):
    return hashlib.sha256(data).hexdigest()


def arm_immediate(value):
    for rotation in range(16):
        for byte in range(256):
            shift = rotation * 2
            expanded = ((byte >> shift) | (byte << (32-shift))) & 0xffffffff if shift else byte
            if expanded == value:
                return (rotation << 8) | byte
    raise ValueError('ARM immediate is not encodable')


def patch_word(data, offset, expected, replacement, label, changes, address):
    actual = u32(data, offset)
    if actual != expected:
        raise ValueError(f'{label}: expected {expected:08X}, got {actual:08X}')
    struct.pack_into('<I', data, offset, replacement)
    changes.append(dict(label=label, ram_address=f'0x{address:08X}',
                        before=f'{expected:08X}', after=f'{replacement:08X}'))


def archive_parts(arc):
    """Enumerate packed archive allocations without inventing resource names."""
    index = arc.idx
    for bucket in range(u32(index)):
        a, b = struct.unpack_from('<II', index, 8+9*bucket)
        if not a and not b:
            continue
        size = ((a >> 26) + (b & 65535)*64)*4
        if a & 1:
            pos = ((a & 0x3ffffff)*2)//4
            count = index[pos]
            pos += 1
            for part in range(count):
                offset = u32(index, pos)*4
                pos += 4
                length = size
                if part:
                    length = u32(index, pos)*4
                    pos += 8
                pos += 3
                yield arc.base+offset, length
        else:
            yield arc.base+(a & 0x3ffffff)*2, size


def source_copies(source, target):
    before, after = Archive(source), Archive(target)
    lookup = {}
    for offset, size in archive_parts(before):
        if offset+size > len(source):
            raise ValueError('Original archive allocation out of range')
        lookup.setdefault((size, sha(source[offset:offset+size])), offset)
    ranges = []
    for offset, size in archive_parts(after):
        if offset+size > len(target):
            raise ValueError('Target archive allocation out of range')
        origin = lookup.get((size, sha(target[offset:offset+size])))
        if origin is not None and size:
            ranges.append((offset, origin, size))
    # Other unchanged NitroFS files (overlays, cutscene data, etc.).
    a, b = ndspy.rom.NintendoDSRom(source), ndspy.rom.NintendoDSRom(target)
    for fid, data in enumerate(b.files):
        if fid < len(a.files) and data == a.files[fid] and data:
            origin = u32(source, u32(source, 0x48)+fid*8)
            dest = u32(target, u32(target, 0x48)+fid*8)
            ranges.append((dest, origin, len(data)))
    result = []
    end = 0
    for dest, origin, size in sorted(set(ranges), key=lambda r: (r[0], -r[2])):
        if dest < end:
            continue
        result.append((dest, origin, size))
        end = dest+size
    return result


def candidate(original, reference, fix_ascii=True, ui_font=None, edits_csv=None, approved_map=None):
    if sha(original) != USA_SHA or sha(reference) != REFERENCE_SHA:
        raise ValueError('Expected exact USA original and supplied private 0.6 ROM')
    rom = ndspy.rom.NintendoDSRom(reference)
    arm = bytearray(rom.arm9)
    changes = []
    def instruction(address, expected, replacement, label):
        patch_word(arm, address-rom.arm9RamAddress, expected, replacement, label, changes, address)
    # The 0.6 reference copied 0x40410 bytes into a 0x2400 allocation inside
    # a 0x7800 child heap. Grow the owning heap AND allocation, not just its bound.
    instruction(0x0201f0d0, 0xe3a02000 | arm_immediate(0x7800),
                0xe3a02000 | arm_immediate(0x47000), 'font child heap extent')
    instruction(0x02084410, 0xe3a01000 | arm_immediate(0x2400),
                0xe3a01000 | arm_immediate(0x41000), 'font arena allocation')
    instruction(0x02084420, 0xe3a02000 | arm_immediate(0x2400),
                0xe3a02000 | arm_immediate(0x41000), 'font arena initialization')
    if u32(arm, 0x02084264-rom.arm9RamAddress) != 0xe3500000 | arm_immediate(0x41000):
        raise ValueError('Font arena limit differs from compatibility contract')
    arc = Archive(reference)
    width, entry = arc.read('menu/font/FontWidthTable.bin')
    width = bytearray(width)
    if fix_ascii:
        # These paths already index two-byte temporary cells on entry. Their
        # ASCII fallback erroneously reverted to byte indexing for index > 0.
        for address, old, new in [(0x0237cae8, 0xe7d04005, 0xe7d04085),
                                  (0x0237cbb8, 0xe7d00005, 0xe7d00085)]:
            patch_word(width, address-FONT_BASE, old, new, 'ASCII cell stride', changes, address)
    bin_id = rom.filenames.idOf('master/pc.bin')
    idx_id = rom.filenames.idOf('master/pc.idx')
    payload = bytearray(rom.files[bin_id])
    rel = entry['offset']-arc.base
    payload[rel:rel+len(width)] = width
    text_repairs = []
    for slot in slots(reference):
        fixed = repair_terminal_padding(slot.data)
        if fixed != slot.data:
            at = slot.offset-arc.base
            payload[at:at+slot.capacity] = fixed
            text_repairs.append(dict(id=slot.id, before_sha256=sha(slot.data), after_sha256=sha(fixed),
                                     reason='NUL gap interrupted final control tokens'))
    title_records = []
    revisions = []
    if edits_csv:
        from usa_text_edits import read_edits, apply_edits
        if approved_map is None:
            raise ValueError('Text edits require a reviewed glyph subset')
        approved = json.loads(Path(approved_map).read_text())
        image, _ = arc.read('menu/font/UseMoji_image.bin')
        if approved['font_image_sha256'] != sha(image):
            raise ValueError('Reviewed glyph subset belongs to another font')
        edits, revisions = read_edits(reference, edits_csv, approved['glyphs'])
        apply_edits(arc, payload, edits)
    if ui_font:
        from build_cn_patch import bdf_glyphs
        from title_texture import RESOURCE, LABELS, parse_dst, render
        title, te = arc.read(RESOURCE)
        width, height, rectangles, start, end = parse_dst(title)
        glyphs = bdf_glyphs(ui_font, set(''.join(label[0] for label in LABELS.values())))
        pixels, title_records = render(title[start:end], rectangles, width, glyphs)
        localized = title[:start]+pixels+title[end:]
        at = te['offset']-arc.base
        payload[at:at+len(localized)] = localized
    rom.files[bin_id] = bytes(payload)
    rom.files[idx_id] = bytes(arc.idx)
    rom.arm9 = bytes(arm)
    # Use a normal NitroFS rebuild, not overlapping FAT extents or overwritten
    # unowned heap memory. Keep all resource payloads and archive offsets intact.
    result = bytearray(rom.save())
    if len(result) > len(original):
        raise ValueError('Rebuilt candidate exceeds original cartridge size')
    result.extend(b'\xff'*(len(original)-len(result)))
    final = Archive(result)
    if bytes(final.idx) != bytes(arc.idx):
        raise ValueError('Rebuilt archive index differs unexpectedly')
    if rom.files[idx_id] != bytes(arc.idx):
        raise ValueError('Archive index ownership mismatch')
    return bytes(result), changes, text_repairs, title_records, revisions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='New external directory')
    p.add_argument('--ui-font', type=Path, required=True, help='External open BDF for manual title labels')
    p.add_argument('--layout-policy', type=Path, help='Measured UI limits and explicit variable-width bounds')
    p.add_argument('--glyph-map', type=Path, help='Review-only mapping for readable layout reports')
    p.add_argument('--edits-csv', type=Path, help='Hash-guarded, versioned text revisions')
    p.add_argument('--approved-map', type=Path, help='Visually reviewed glyph subset for replacement text')
    p.add_argument('--heap-only', action='store_true', help='Diagnostic candidate without ASCII stride fixes')
    args = p.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        p.error('Private output must remain outside Git')
    if output.exists():
        p.error('Output directory already exists')
    original, reference = args.original.read_bytes(), args.reference.read_bytes()
    target, changes, text_repairs, title_records, revisions = candidate(original, reference, not args.heap_only, args.ui_font, args.edits_csv, args.approved_map)
    output.mkdir(parents=True)
    from usa_layout_audit import audit, write_report
    policy = json.loads(args.layout_policy.read_text()) if args.layout_policy else {}
    mapping = {int(k): v for k, v in json.loads(args.glyph_map.read_text()).items()} if args.glyph_map else {}
    layout = audit(original, target, policy, mapping)
    write_report(layout, output / 'audit')
    if layout['failed_rows']:
        raise SystemExit(f'Layout preflight rejected {layout["failed_rows"]} rows; see {output / "audit"}. No release ROM/BPS written.')
    path = output/'ffta2-usa-cn-0.6.1.nds'
    path.write_bytes(target)
    segments = difference_segments(original, target, source_copies(original, target))
    patch, rebuilt = build(original, segments, b'FFTA2 USA private Chinese 0.6.1 candidate')
    if rebuilt != target or apply(original, patch) != target:
        raise ValueError('Independent BPS application differs')
    patch_path = path.with_suffix('.bps')
    patch_path.write_bytes(patch)
    receipt = dict(schema_version=1, version='0.6.1-local-candidate',
                   original_sha256=USA_SHA, reference_06_sha256=REFERENCE_SHA,
                   target_sha256=sha(target), patch_sha256=sha(patch),
                   patch_bytes=len(patch), rom_bytes=len(target), changes=changes,
                   ui_font_sha256=sha(args.ui_font.read_bytes()), ui_font_license='OFL-1.1',
                   text_repairs=text_repairs, title_label_variants=len(title_records),
                   text_revisions=revisions,
                   layout_audit={k: v for k, v in layout.items() if k != 'results'},
                   source_copy_bytes=sum(s[2] for s in segments if s[0]=='source'),
                   human_text_origin='private supplied 0.6 reference; no machine translation',
                   independent_bps_apply_verified=True, full_game_validated=False)
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    shutil.copyfile(ROOT/'docs/fusion-pixel-OFL.txt',output/'fusion-pixel-OFL.txt')
    (output/'README-private.txt').write_text('Private local USA Chinese 0.6.1 test build. Do not publish.\nSource: user-supplied human translation 0.6; no machine translation.\nApply the BPS only to the exact original USA ROM SHA-256 in receipt.json.\nThe NDS file runs directly without native sidecars.\nBasic validation is recorded separately; no full-campaign claim.\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
