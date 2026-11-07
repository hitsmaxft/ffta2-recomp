# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare USA retail/Chinese line layout using their actual glyph metrics.

Reports are private. Unknown dynamic widths are never reported as fitting.
The original English footprint is a review baseline, not a UI-box measurement.
"""
import argparse
import csv
import json
from pathlib import Path
import struct
import ndspy.rom
import ndspy.codeCompression
from build_cn_patch import Archive, u16, u32
from usa_text import slots

ROOT = Path(__file__).resolve().parents[1]


def icon_widths(raw):
    """Follow the guarded USA CB dispatch to its actual DST rectangle widths."""
    rom = ndspy.rom.NintendoDSRom(raw)
    arm = ndspy.codeCompression.decompress(rom.arm9)
    if (u32(arm, 0x4ba74), u32(arm, 0x4ba9c)) != (0xe92d4010, 0xe20000ff):
        raise ValueError('USA icon-width routine differs from audited layout')
    mapping = u32(arm, 0x4baa8) - rom.arm9RamAddress
    if not 0 <= mapping <= len(arm) - 32:
        raise ValueError('Icon mapping outside ARM9')
    dst, _ = Archive(raw).read('menu/dst_bin/us/com_key_dst.bin')
    palette, width, height, fmt, count = struct.unpack_from('<3H2B', dst)
    if (palette, width, height, fmt, count) != (160, 32, 224, 1, 25):
        raise ValueError('Unsupported USA icon atlas')
    result = {}
    for parameter, index in enumerate(arm[mapping:mapping + 32]):
        if index >= count:
            raise ValueError('Icon index outside atlas rectangle table')
        x, y, w, h = struct.unpack_from('<4H', dst, 8 + index * 8)
        if not 0 < w <= width or x + w > width or y + h > height:
            raise ValueError('Invalid icon rectangle')
        result[f'CB{parameter:02X}'] = w
    return result


class FontMetrics:
    def __init__(self, image, widths, glyph_count):
        self.image, self.widths, self.count = image, widths, glyph_count
        self.cache = {}

    def glyph(self, index):
        if index in self.cache:
            return self.cache[index]
        if not 0 <= index < self.count or 2 + index * 4 + 4 > len(self.image):
            raise ValueError('glyph index outside font')
        at = u32(self.image, 2 + index * 4)
        if at + 4 > len(self.image):
            raise ValueError('glyph record outside font')
        size, padding = self.image[at:at + 2]
        width_index = u16(self.image, at + 2)
        if size < 4 or at + size > len(self.image) or 2 + width_index >= len(self.widths):
            raise ValueError('glyph record/width index outside resource')
        advance = self.widths[2 + width_index]
        if advance > 32:
            raise ValueError('implausible glyph advance')
        bits = bytes(64) if padding == 255 else (bytes((padding >> 4) * 4) +
                    self.image[at + 4:at + size] + bytes((padding & 15) * 4))
        if len(bits) != 64:
            raise ValueError('glyph expansion exceeds 16x16 cell')
        ink = [x for y in range(16) for x in range(16)
               if u32(bits, y * 4) >> (2 * x) & 3]
        result = (advance, min(ink) if ink else None, max(ink) + 1 if ink else None)
        self.cache[index] = result
        return result

    @classmethod
    def from_rom(cls, raw, chinese):
        arc = Archive(raw)
        image, _ = arc.read('menu/font/UseMoji_image.bin')
        widths, _ = arc.read('menu/font/FontWidthTable.bin')
        return cls(image, widths, 4368 if chinese else u16(image))


def measure(data, metrics, chinese, dynamic_widths=None):
    """Consume bounded tokens; C1/C3 coalesce, C0 adds a line, C8 ends an option."""
    dynamic_widths = dynamic_widths or {}
    pages, lines, problems, controls, breaks = [], [], [], [], []
    def empty_line():
        return dict(advance_px=0, ink_right_px=0, glyphs=0, unknown_width_tokens=[],
                    reserved_dynamic_px=0, byte_start=pos, byte_end=pos)
    pos = 0
    line = empty_line()
    active = False
    def finish_page():
        nonlocal line, lines, active
        if active or lines:
            line['byte_end'] = pos
            lines.append(line)
            pages.append(lines)
        lines = []
        line = empty_line()
        active = False
    while pos < len(data):
        at, code = pos, data[pos]
        pos += 1
        if not code:
            if any(data[pos:]):
                problems.append('nonzero data after NUL')
            break
        if code >= 0xc0:
            if pos == len(data):
                problems.append('truncated control')
                break
            parameter = data[pos]
            pos += 1
            token = f'{code:02X}{parameter:02X}'
            controls.append(token)
            if code in (0xc0, 0xc1, 0xc3, 0xc8):
                breaks.append(dict(token=token, byte_offset=at))
                if parameter != 0:
                    problems.append('unknown layout-control parameter: ' + token)
                if code == 0xc0:
                    line['byte_end'] = at
                    lines.append(line)
                    line = empty_line()
                    active = True
                else:
                    finish_page()
            elif code in (0xc2, 0xc6, 0xc7, 0xc9, 0xce):
                # Known nonprinting wait/style/selection controls. Preserve all.
                if not ((code in (0xc2, 0xc9) and parameter == 0) or
                        (code == 0xc6 and parameter == 255) or code == 0xc7 or
                        (code == 0xce and parameter < 4)):
                    line['unknown_width_tokens'].append(token)
            else:
                if token in dynamic_widths:
                    amount = dynamic_widths[token]
                    if not isinstance(amount, int) or isinstance(amount, bool) or not 0 <= amount <= 255:
                        raise ValueError('Invalid dynamic-width bound: ' + token)
                    line['reserved_dynamic_px'] += amount
                else:
                    line['unknown_width_tokens'].append(token)
                active = True
            continue
        if chinese and code >= 0xa9:
            if pos == len(data):
                problems.append('truncated Chinese glyph')
                break
            glyph = code * 256 + data[pos] - 0xa858
            pos += 1
        else:
            glyph = code - 1
        try:
            advance, left, right = metrics.glyph(glyph)
        except ValueError as exc:
            problems.append(f'byte {at}: {exc}')
            continue
        if right is not None:
            line['ink_right_px'] = max(line['ink_right_px'], line['advance_px'] + right)
        line['advance_px'] += advance
        line['glyphs'] += 1
        active = True
    finish_page()
    return dict(pages=pages, problems=problems, controls=controls, breaks=breaks,
                encoded_content_bytes=pos, allocation_bytes=len(data))


def inspect(key, before, after, metadata_lines, limits):
    errors = list(after['problems'])
    warnings = []
    width_limit = limits.get('max_width_px', 255)
    glyph_limit = limits.get('max_glyphs_per_line', 61)
    line_limit = limits.get('max_lines_per_page')
    for p, page in enumerate(after['pages']):
        if line_limit is not None and len(page) > line_limit:
            errors.append(f'page {p + 1}: {len(page)} lines exceeds box limit {line_limit}')
        for n, line in enumerate(page):
            prefix = f'page {p + 1} line {n + 1}'
            lower = max(line['advance_px'], line['ink_right_px'])
            if lower > width_limit:
                errors.append(f'{prefix}: literal width {lower}px exceeds {width_limit}px')
            elif lower + line['reserved_dynamic_px'] > width_limit:
                errors.append(f'{prefix}: reserved width exceeds {width_limit}px')
            if line['glyphs'] > glyph_limit:
                errors.append(f'{prefix}: {line["glyphs"]} glyphs exceeds descriptor limit {glyph_limit}')
            if line['unknown_width_tokens']:
                warnings.append(f'{prefix}: unresolved dynamic/icon widths ' + ','.join(line['unknown_width_tokens']))
        if p < len(before['pages']):
            source = before['pages'][p]
            if len(page) != len(source):
                warnings.append(f'page {p + 1}: newline count differs from English ({len(source)} -> {len(page)})')
            source_width = max((max(l['advance_px'], l['ink_right_px']) for l in source), default=0)
            target_width = max((max(l['advance_px'], l['ink_right_px']) for l in page), default=0)
            if target_width > source_width:
                warnings.append(f'page {p + 1}: wider than English footprint ({source_width} -> {target_width}px)')
        if metadata_lines and len(page) > metadata_lines:
            warnings.append(f'page {p + 1}: line count exceeds declared metadata ({len(page)} > {metadata_lines})')
    if len(before['pages']) != len(after['pages']):
        warnings.append('page/option count differs from English')
    return dict(id=key, errors=errors, warnings=warnings,
                source=before, translation=after, limits=limits,
                fully_bounded=not errors and not any(l['unknown_width_tokens']
                    for page in after['pages'] for l in page))


def audit(original, translated, policy=None, glyph_map=None):
    from export_usa_cn import decode
    policy = policy or {}
    source_font, target_font = FontMetrics.from_rom(original, False), FontMetrics.from_rom(translated, True)
    source_dynamic, target_dynamic = icon_widths(original), icon_widths(translated)
    source_dynamic.update(policy.get('dynamic_widths', {}))
    target_dynamic.update(policy.get('dynamic_widths', {}))
    source = {s.id: s for s in slots(original)}
    target = {s.id: s for s in slots(translated)}
    if source.keys() != target.keys():
        raise ValueError('Original/translated stable text IDs differ')
    results = []
    for key, before in source.items():
        after = target[key]
        limits = dict(policy.get('defaults', {}))
        limits.update(policy.get('families', {}).get(key.split(':')[0], {}))
        limits.update(policy.get('rows', {}).get(key, {}))
        a = measure(before.data, source_font, False, source_dynamic)
        b = measure(after.data, target_font, True, target_dynamic)
        row = inspect(key, a, b, after.original_lines, limits)
        row.update(source_rom_offset=f'0x{before.offset:08X}',
                   translated_rom_offset=f'0x{after.offset:08X}',
                   source_declared_lines=before.original_lines,
                   translated_declared_lines=after.original_lines,
                   source_text=decode(before.data, False, {})[0],
                   translated_text=decode(after.data, True, glyph_map or {})[0])
        results.append(row)
    return dict(schema_version=1, private_do_not_publish=True, rows=len(results),
                failed_rows=sum(bool(r['errors']) for r in results),
                review_rows=sum(bool(r['warnings']) for r in results),
                fully_bounded_rows=sum(r['fully_bounded'] for r in results),
                runtime_verified=False, results=results)


def write_report(report, output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Layout reports must remain outside public source checkout')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'layout-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    fields = ['id', 'severity', 'source_rom_offset', 'translated_rom_offset', 'errors', 'warnings',
              'source_declared_lines', 'translated_declared_lines', 'source_pages', 'translation_pages',
              'source_breaks', 'translation_breaks', 'source_text', 'translated_text']
    for name, rows in [('layout-all-private.csv', report['results']),
                       ('layout-issues-private.csv', [r for r in report['results'] if r['errors'] or r['warnings']])]:
        with (output / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(id=row['id'], severity='error' if row['errors'] else 'review' if row['warnings'] else 'pass',
                    **{k: row[k] for k in fields[2:4] + fields[6:8]},
                    **{k: json.dumps(row[k], ensure_ascii=False) for k in ('errors','warnings')},
                    source_pages=json.dumps(row['source']['pages']), translation_pages=json.dumps(row['translation']['pages']),
                    source_breaks=json.dumps(row['source']['breaks']), translation_breaks=json.dumps(row['translation']['breaks']),
                    source_text=row['source_text'], translated_text=row['translated_text']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--translated', type=Path, required=True)
    p.add_argument('--policy', type=Path)
    p.add_argument('--glyph-map', type=Path, help='Optional review-only map for readable Chinese reports')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    from usa_cn_release import USA_SHA, sha
    original, translated = args.original.read_bytes(), args.translated.read_bytes()
    if sha(original) != USA_SHA:
        p.error('Expected the exact original USA ROM')
    mapping = {int(k): v for k, v in json.loads(args.glyph_map.read_text()).items()} if args.glyph_map else {}
    report = audit(original, translated, json.loads(args.policy.read_text()) if args.policy else {}, mapping)
    write_report(report, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))
    raise SystemExit(bool(report['failed_rows']))


if __name__ == '__main__':
    main()
