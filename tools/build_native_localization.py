#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Unicode host localization resources; never patches or writes a ROM."""
import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path
from build_cn_patch import Archive, SHA, bdf_glyphs, u16, u32
from text_catalog import FIELDS, controls, normalize_newlines, read_rows
from text_resources import TextResources
from validate_translation import RetailCodec

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def field(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('Host field exceeds bounded pack capacity')
    return struct.pack('<I', len(data)) + data


def checked_text(row, original, resources):
    key = row['id']
    if row['source_sha256'] != original['source_sha256']:
        raise ValueError('CSV source hash mismatch: ' + key)
    slot = resources.locate(key)
    if digest(slot.data) != original['source_sha256']:
        raise ValueError('Actual ROM source bytes mismatch: ' + key)
    text = normalize_newlines(row['translation'])
    source = normalize_newlines(original['source_text'])
    if not text or '\0' in text or '\0' in source:
        raise ValueError('Empty or NUL-containing host text: ' + key)
    if controls(text) != controls(source):
        raise ValueError('Script controls or variable parameters changed: ' + key)
    codec = RetailCodec(json.loads((ROOT / 'config/western-charset.json').read_text()), [0] * 168)
    expected_controls = b''.join(codec.token_bytes(token) for token in controls(source))
    original_controls = bytearray()
    i = 0
    while i < len(slot.data):
        if slot.data[i] >= 0xc0:
            if i + 1 >= len(slot.data):
                raise ValueError('Truncated original control pair: ' + key)
            if slot.data[i] != 0xc0:
                original_controls += slot.data[i:i+2]
            i += 2
        else:
            i += 1
    if expected_controls != original_controls:
        raise ValueError('Catalog control tokens differ from original ROM control bytes: ' + key)
    # A loose backslash is an invalid or newly introduced script token.
    import re
    stripped = re.sub(r'\\[^\\\r\n]+\\|<unknown:[0-9A-Fa-f]+>', '', text)
    if '\\' in stripped:
        raise ValueError('Malformed script control: ' + key)
    return slot, text, source


def font_characters(path):
    """Include all printable Unicode glyphs in an external BDF font."""
    points = set()
    for line in path.read_text().splitlines():
        if line.startswith('ENCODING '):
            code = int(line.split()[1])
            if 0 <= code <= 0x10ffff and not 0xd800 <= code <= 0xdfff:
                char = chr(code)
                if char.isprintable():
                    points.add(char)
    return points


def build(args):
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Binary localization packs must stay outside checkout')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing to overwrite a nonempty localization pack')
    raw = args.rom.read_bytes()
    if digest(raw) != SHA:
        raise ValueError('Unsupported original ROM identity')
    resources = TextResources(raw)
    original = {r['id']: r for r in read_rows(args.catalog)}
    rows = list(read_rows(args.translations))
    wanted = font_characters(args.font) if getattr(args, "all_font_glyphs", False) else set()
    if args.recipe:
        recipe = json.loads(args.recipe.read_text())
        chars = recipe.get('bank_glyphs', recipe.get('glyphs'))
        if not isinstance(chars, list) or any(not isinstance(c, str) or len(c) != 1 for c in chars):
            raise ValueError('Invalid glyph recipe')
        wanted.update(chars)
    for row in rows:
        wanted.update(c for c in row['translation'] if ord(c) > 127)
    accepted = []
    for row in rows:
        if row['status'] != 'translated' and not (args.include_review and row['status'] == 'review'):
            continue
        if row['id'] not in original:
            raise ValueError('Unknown stable text ID: ' + row['id'])
        slot, text, source = checked_text(row, original[row['id']], resources)
        accepted.append((row, slot, text, source))
    arc = Archive(raw)
    image, _ = arc.read('menu/font/UseMoji_image.bin')
    widths, _ = arc.read('menu/font/FontWidthTable.bin')
    palette, _ = arc.read('menu/font/fontpalette.bin')
    if u16(image) != 168 or u16(widths) != 168 or palette[0] != 5:
        raise ValueError('Unexpected retail font resources')
    glyphs = {}
    charset = json.loads((ROOT / 'config/western-charset.json').read_text())
    for item in charset['entries']:
        code = int(item['code_hex'], 16)
        char = item['display']
        if not (1 <= code <= 168 and len(char) == 1):
            continue
        p = u32(image, 2 + 4 * (code - 1))
        length, blank = image[p:p+2]
        pixels = (bytes(64) if blank == 0xff else
                  bytes((blank >> 4) * 4) + image[p+4:p+length] + bytes((blank & 15) * 4))
        if len(pixels) != 64:
            raise ValueError('Invalid original glyph size')
        glyphs[char] = (widths[2 + code - 1], pixels, 'retail', code - 1)
    new = sorted(wanted - glyphs.keys(), key=ord)
    rendered = bdf_glyphs(args.font, set(new))
    for char in new:
        glyphs[char] = (12, rendered[char], 'ofl-bdf', None)
    blob = bytearray(b'FFTALOC2' + struct.pack('<4I', 2, len(accepted), len(glyphs), 5))
    blob += field(SHA)
    for row, slot, text, source in accepted:
        blob += field(row['id']) + field(text) + field(source) + field(row['status'])
        blob += struct.pack('<II', slot.offset, slot.capacity) + field(slot.data)
        blob += bytes.fromhex(row['source_sha256'])
    recipe_rows = []
    for index, (char, (advance, pixels, origin, retail_index)) in enumerate(sorted(glyphs.items(), key=lambda item: ord(item[0]))):
        blob += struct.pack('<IHH', ord(char), advance, 64) + pixels
        recipe_rows.append(dict(index=index, character=char, unicode=f'U+{ord(char):04X}',
                                advance=advance, origin=origin, retail_index=retail_index,
                                sha256=digest(pixels)))
    # Five complete retail BGR555 palettes, 16 entries each. Pixel indices
    # retain semantic roles 0 transparent / 1 outline / 2 shadow / 3 foreground.
    blob += palette[1:161]
    cmap = [0] * 169
    for item in charset['entries']:
        code = int(item['code_hex'], 16)
        if 0 < code < len(cmap) and len(item['display']) == 1:
            cmap[code] = ord(item['display'])
    blob += struct.pack('<169I', *cmap)
    output.mkdir(parents=True)
    (output / 'localization.bin').write_bytes(blob)
    with (output / 'translations.csv').open('w', encoding='utf-8-sig', newline='') as dest:
        writer = csv.DictWriter(dest, fieldnames=FIELDS, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
        writer.writeheader()
        for row, _, text, _ in accepted:
            writer.writerow({key: text if key == 'translation' else row.get(key, '') for key in FIELDS})
    with (output / 'glyphs.csv').open('w', encoding='utf-8-sig', newline='') as dest:
        writer = csv.DictWriter(dest, fieldnames=list(recipe_rows[0]), quoting=csv.QUOTE_ALL, lineterminator='\r\n')
        writer.writeheader(); writer.writerows(recipe_rows)
    (output / 'font-2bpp.bin').write_bytes(b''.join(g[1] for _, g in sorted(glyphs.items(), key=lambda item: ord(item[0]))))
    (output / 'widths.bin').write_bytes(bytes(g[0] for _, g in sorted(glyphs.items(), key=lambda item: ord(item[0]))))
    (output / 'palettes-bgr555.bin').write_bytes(palette[1:161])
    license_path = ROOT / 'docs/fusion-pixel-OFL.txt'
    (output / 'font-OFL.txt').write_bytes(license_path.read_bytes())
    manifest = dict(schema=1, kind='ffta2-native-localization', source_rom_sha256=SHA,
                    translation_count=len(accepted), review_texts_included=args.include_review,
                    glyph_count=len(glyphs), bdf_sha256=digest(args.font.read_bytes()),
                    catalog_sha256=digest(args.catalog.read_bytes()),
                    translations_sha256=digest(args.translations.read_bytes()),
                    pixel_roles=['transparent', 'outline', 'shadow', 'foreground'],
                    palette_count=5, palette_format='16 BGR555 entries per palette',
                    rom_modified=False, runtime_format='FFTALOC2',
                    files={p.name: dict(sha256=digest(p.read_bytes()), bytes=p.stat().st_size)
                           for p in sorted(output.iterdir())})
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (output / 'checksums.tsv').write_text(''.join(f'{digest(p.read_bytes())}\t{p.name}\n' for p in sorted(output.iterdir())))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--recipe', type=Path)
    parser.add_argument('--catalog', type=Path, default=ROOT/'data/text/catalog.csv')
    parser.add_argument('--translations', type=Path, default=ROOT/'data/text/machine-cn.csv')
    parser.add_argument('--include-review', action='store_true')
    parser.add_argument('--all-font-glyphs', action='store_true', help='Bundle every printable font glyph for future translations')
    parser.add_argument('--output', type=Path, required=True)
    result = build(parser.parse_args())
    print(f'Built {result["translation_count"]} texts, {result["glyph_count"]} glyphs, 5 retail palettes; ROM unchanged')
