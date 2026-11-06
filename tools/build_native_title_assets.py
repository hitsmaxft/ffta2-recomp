#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build original-byte-matched title texture overrides without modifying a ROM.

All binary assets and previews stay outside the source tree. The original DST
rectangle table, dimensions, palette banks, decorative artwork and allocation
size are preserved. This is a native texture replacement, not a subtitle layer.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from build_cn_patch import Archive, SHA, bdf_glyphs

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = 'menu/dst_bin/us/title_2_dst.bin'
# In-order source rectangles, discovered from the original DST rectangle table.
# Values are (Chinese label, source meaning, palette role). Three button styles
# are independent artwork in this atlas, not an assumed runtime recoloring.
LABELS = {
    0: ('新游戏', 'New Game', 'normal'),
    1: ('读取', 'Load', 'normal'),
    2: ('继续', 'Continue', 'normal'),
    3: ('交换', 'Trade', 'normal'),
    4: ('新游戏', 'New Game', 'selected'),
    5: ('读取', 'Load', 'selected'),
    6: ('继续', 'Continue', 'selected'),
    7: ('交换', 'Trade', 'selected'),
    8: ('新游戏', 'New Game', 'disabled'),
    9: ('读取', 'Load', 'disabled'),
    10: ('继续', 'Continue', 'disabled'),
    11: ('交换', 'Trade', 'disabled'),
    14: ('难度', 'Difficulty', 'heading'),
    15: ('普通', 'Normal', 'selected'),
    16: ('普通', 'Normal', 'normal'),
    17: ('困难', 'Hard', 'selected'),
    18: ('困难', 'Hard', 'normal'),
    20: ('中文', 'English (first language slot)', 'normal'),
    21: ('中文', 'English (first language slot)', 'selected'),
    22: ('德语', 'Deutsch', 'normal'),
    23: ('德语', 'Deutsch', 'selected'),
    24: ('西班牙语', 'Español', 'normal'),
    25: ('西班牙语', 'Español', 'selected'),
    26: ('法语', 'Français', 'normal'),
    27: ('法语', 'Français', 'selected'),
    28: ('语言', 'Language', 'selected'),
    29: ('语言', 'Language', 'normal'),
    30: ('语言', 'Language', 'disabled'),
}
ROLES = {
    'normal': {1: 1, 2: 7, 3: 11},
    'selected': {1: 1, 2: 22, 3: 25},
    'disabled': {1: 1, 2: 27, 3: 28},
    'heading': {1: 26, 2: 7, 3: 31},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_dst(data):
    if len(data) != 60224:
        raise ValueError('Unexpected title resource size')
    palette_bytes, width, height, fmt, rect_count = struct.unpack_from('<3H2B', data)
    if (palette_bytes, width, height, fmt, rect_count) != (320, 256, 233, 4, 31):
        raise ValueError('Unsupported original title DST structure')
    rectangles = [struct.unpack_from('<4H', data, 8 + i * 8) for i in range(rect_count)]
    if any(x + w > width or y + h > height or not w or not h for x, y, w, h in rectangles):
        raise ValueError('Invalid original atlas rectangle')
    pixel_offset = 8 + rect_count * 8
    pixel_end = pixel_offset + width * height
    if len(data) - pixel_end != 5 * 32 * 2:
        raise ValueError('Expected five unchanged 32-color BGR555 palette banks')
    return width, height, rectangles, pixel_offset, pixel_end


def render(original, rectangles, width, glyphs):
    pixels = bytearray(original)
    records = []
    changed = set()
    for index, (text, source, style) in LABELS.items():
        x, y, w, h = rectangles[index]
        # Preserve the Trade link-device icon (x78..93) and Difficulty checkbox.
        left_limit, right_limit = (0, 78) if index in (3, 7, 11) else (13, w) if index == 14 else (0, w)
        occupied = [(xx, yy) for yy in range(h) for xx in range(left_limit, right_limit)
                    if original[(y + yy) * width + x + xx] >> 5]
        if not occupied:
            raise ValueError(f'Empty original label rectangle {index}')
        old_left = min(xx for xx, yy in occupied)
        old_right = max(xx for xx, yy in occupied) + 1
        label_width = len(text) * 12 + 2
        ox = (old_left + old_right - label_width) // 2
        oy = (h - 16) // 2
        if ox < left_limit or ox + label_width > right_limit or oy < 0:
            raise ValueError(f'Chinese label exceeds original rectangle: {index} {text}')
        for yy in range(h):
            for xx in range(left_limit, right_limit):
                at = (y + yy) * width + x + xx
                pixels[at] = 0
                changed.add(at)
        for n, char in enumerate(text):
            glyph = glyphs[char]
            for gy in range(16):
                row = struct.unpack_from('<I', glyph, gy * 4)[0]
                for gx in range(16):
                    role = (row >> (2 * gx)) & 3
                    if not role:
                        continue
                    xx, yy = ox + n * 12 + gx, oy + gy
                    if not left_limit <= xx < right_limit or not 0 <= yy < h:
                        raise ValueError(f'Glyph outline exceeds original rectangle {index}')
                    at = (y + yy) * width + x + xx
                    pixels[at] = 0xE0 | ROLES[style][role]
                    changed.add(at)
        records.append({'rectangle': index, 'source_label': source, 'translation': text,
                        'style': style, 'bounds': [x, y, w, h], 'text_origin': [ox, oy],
                        'protected_columns': [0, 13] if index == 14 else [78, w] if index in (3, 7, 11) else None})
    if any(a != b and i not in changed for i, (a, b) in enumerate(zip(original, pixels))):
        raise AssertionError('Unexpected change outside replacement rectangles')
    return bytes(pixels), records


def preview(data, path):
    from PIL import Image
    width, height, _, start, end = parse_dst(data)
    palette = struct.unpack_from('<32H', data, end)
    image = Image.new('RGBA', (width, height))
    image.putdata([((palette[v & 31] & 31) * 255 // 31,
                    ((palette[v & 31] >> 5) & 31) * 255 // 31,
                    ((palette[v & 31] >> 10) & 31) * 255 // 31,
                    (v >> 5) * 255 // 7) for v in data[start:end]])
    image.save(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--font', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Binary title assets must stay outside checkout')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing to overwrite a nonempty asset pack')
    raw = a.rom.read_bytes()
    if digest(raw) != SHA:
        raise ValueError('Unsupported original European A6FP revision 0 ROM')
    original, entry = Archive(raw).read(RESOURCE)
    width, height, rectangles, start, end = parse_dst(original)
    wanted = set(''.join(label[0] for label in LABELS.values()))
    glyphs = bdf_glyphs(a.font, wanted)
    replacement, records = render(original[start:end], rectangles, width, glyphs)
    localized = original[:start] + replacement + original[end:]
    if original[:start] != localized[:start] or original[end:] != localized[end:]:
        raise AssertionError('Header, rectangle table or palette changed')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'title_2_zh_hans.dst').write_bytes(localized)
    blob = bytearray(b'FFTATEX1' + struct.pack('<II', 1, 2))
    manifest = {'schema': 1, 'rom_sha256': SHA, 'resource': RESOURCE,
                'resource_rom_offset': entry['offset'], 'resource_size': len(original),
                'source_sha256': digest(original), 'replacement_sha256': digest(localized),
                'pixel_offset': start, 'pixel_size': end - start, 'texture_format': 'A3I5',
                'width': width, 'height': height, 'palette_banks': 5,
                'palette_sha256': digest(original[end:]), 'palette_modified': False,
                'font_sha256': digest(a.font.read_bytes()), 'labels': records, 'overrides': []}
    for suffix, target_height in [('linear', height), ('padded', 256)]:
        size = width * target_height
        source_bytes = original[start:end] + bytes(size - (end - start))
        replacement_bytes = replacement + bytes(size - len(replacement))
        name = f'title_pixels_{suffix}.bin'
        (output / name).write_bytes(replacement_bytes)
        blob += struct.pack('<IIII', size, entry['offset'] + start, width, target_height)
        blob += source_bytes + replacement_bytes
        manifest['overrides'].append({'name': name, 'byte_length': size, 'width': width,
                                      'height': target_height, 'source_sha256': digest(source_bytes),
                                      'replacement_sha256': digest(replacement_bytes),
                                      'padding': 'zero tail, matched exactly at runtime'})
    (output / 'title-assets.bin').write_bytes(blob)
    manifest['pack_sha256'] = digest(blob)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    preview(original, output / 'title_original.png')
    preview(localized, output / 'title_zh_hans.png')
    print(f'Built {len(records)} original-sized Chinese label variants; five original palettes preserved')
    print(f'Title override pack {len(blob)} bytes: {output}')


if __name__ == '__main__':
    main()
