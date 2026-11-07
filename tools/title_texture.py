# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared bounded title-atlas rendering for ROM and native output backends."""
import struct

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
    # Title artwork differs from the dialogue font: the colored rim surrounds
    # the light face; black belongs to the displaced lower shadow only.
    'normal': {1: 7, 2: 1, 3: 11},
    'selected': {1: 22, 2: 1, 3: 25},
    'disabled': {1: 1, 2: 1, 3: 28},
    'heading': {1: 7, 2: 26, 3: 31},
}


def label_pixels(text, glyphs, style):
    """Compose the whole label before adding its rim and lower shadow.

    Imported 2bpp glyphs carry dialogue layers. Only their face is applicable
    here. Unioning faces first prevents the next glyph's rim from erasing one.
    Values are A3I5 palette references, shared by all five original banks.
    """
    face = set()
    for n, char in enumerate(text):
        for y in range(16):
            row = struct.unpack_from('<I', glyphs[char], y * 4)[0]
            face.update((n * 12 + x, y) for x in range(16)
                        if (row >> (2 * x)) & 3 == 3)
    silhouette = {(x + dx, y + dy) for x, y in face
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    shadow = {(x, y + 1) for x, y in silhouette} - silhouette
    # The retail atlas uses translucent black along the lower shadow edge.
    result = {pos: 0x60 | ROLES[style][2] for pos in shadow}
    result.update({pos: 0xe0 | ROLES[style][1] for pos in silhouette - face})
    result.update({pos: 0xe0 | ROLES[style][3] for pos in face})
    return result


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
        for (gx, gy), value in label_pixels(text, glyphs, style).items():
            xx, yy = ox + gx, oy + gy
            if not left_limit <= xx < right_limit or not 0 <= yy < h:
                raise ValueError(f'Glyph outline exceeds original rectangle {index}')
            at = (y + yy) * width + x + xx
            pixels[at] = value
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
