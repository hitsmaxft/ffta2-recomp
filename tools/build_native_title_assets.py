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
from title_texture import RESOURCE, LABELS, ROLES, parse_dst, render, preview


def digest(data):
    return hashlib.sha256(data).hexdigest()


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
