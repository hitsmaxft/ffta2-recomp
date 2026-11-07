#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private USA 0.6 human-text extraction and 0.6.1 content/codec audit.

Exports RFC4180 UTF-8 BOM CSVs, addresses, glyph IDs and font assets externally.
An optional recovered glyph map is review data, never an implicit translation.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import struct
from build_cn_patch import Archive, u16, u32
from text_resources import PATHS, block_slot
from usa_cn_release import USA_SHA, REFERENCE_SHA, ROOT, sha
from usa_text import slots, tokens

WESTERN = {int(r['code_hex'], 16): r['display'] for r in
           json.loads((ROOT/'config/western-charset.json').read_text())['entries']}



def decode(data, chinese, mapping):
    text, controls, glyphs, issues = [], [], [], []
    pos = 0
    while pos < len(data):
        code = data[pos]
        pos += 1
        if not code:
            if any(data[pos:]):
                issues.append('data_after_terminator')
            break
        if code >= 0xc0:
            if pos == len(data):
                issues.append('truncated_control')
                text.append(f'<truncated:{code:02X}>')
                break
            parameter = data[pos]
            pos += 1
            controls.append(f'{code:02X}{parameter:02X}')
            text.append(WESTERN.get(code*256+parameter,
                        WESTERN.get(code, f'<unknown:{code:02X}{parameter:02X}>')).replace('%02X', f'{parameter:02X}'))
        elif chinese and code >= 0xa9:
            if pos == len(data):
                issues.append('truncated_glyph')
                text.append(f'<truncated:{code:02X}>')
                break
            code = code*256+data[pos]
            pos += 1
            glyph = code-0xa858
            glyphs.append(glyph)
            text.append(mapping.get(glyph, f'<glyph:{code:04X}>'))
            if not 168 <= glyph < 4368:
                issues.append('glyph_out_of_range')
        else:
            text.append(WESTERN.get(code, f'<unknown:{code:02X}>'))
    return ''.join(text), controls, glyphs, issues


def semantic_controls(controls):
    # Page/newline/end-page layout can legitimately change in a human translation.
    # Variable parameters, choices, portraits/sprites and other script effects cannot.
    return [c for c in controls if c[:2] not in {'C0', 'C1', 'C3'}]


def csv_file(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--revision-manifest', type=Path, help='Candidate receipt listing every approved text revision')
    p.add_argument('--glyph-map', type=Path, help='Private JSON glyph-index to Unicode mapping; review required')
    p.add_argument('--output', type=Path, required=True, help='New external private directory')
    args = p.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents or output.exists():
        p.error('Use a new directory outside Git for private text/assets')
    original, reference = args.original.read_bytes(), args.reference.read_bytes()
    if sha(original) != USA_SHA or sha(reference) != REFERENCE_SHA:
        raise ValueError('Input ROM hash differs from the approved USA pair')
    mapping = {int(k): v for k, v in json.loads(args.glyph_map.read_text()).items()} if args.glyph_map else {}
    if any(not 168 <= k < 4368 or not isinstance(v, str) or len(v) != 1 for k, v in mapping.items()):
        raise ValueError('Glyph map must contain one Unicode scalar per valid glyph ID')
    output.mkdir(parents=True)
    source = {s.id: s for s in slots(original)}
    translated = {s.id: s for s in slots(reference)}
    if source.keys() != translated.keys():
        raise ValueError('Original and translated resource IDs differ')
    candidate = {s.id: s for s in slots(args.candidate.read_bytes())} if args.candidate else None
    revisions = {r['id']: r for r in json.loads(args.revision_manifest.read_text())['text_revisions']} if args.revision_manifest else {}
    verified_revisions = []
    rows, issues, preserved, normalized, usage = [], [], [], [], collections.Counter()
    for key, before in source.items():
        after = translated[key]
        english, old_controls, _, old_issues = decode(before.data, False, {})
        chinese, new_controls, glyphs, row_issues = decode(after.data, True, mapping)
        usage.update(glyphs)
        if semantic_controls(old_controls) != semantic_controls(new_controls):
            row_issues.append('semantic_control_difference_review')
        if candidate is not None:
            revision = revisions.get(key)
            if revision and key in candidate and revision['before_sha256'] == sha(after.data) and revision['after_sha256'] == sha(candidate[key].data) and revision['after_lines'] == candidate[key].original_lines:
                verified_revisions.append(key)
            elif key not in candidate or candidate[key].original_lines != after.original_lines or tokens(candidate[key].data) != tokens(after.data):
                preserved.append(key)
            elif candidate[key].data != after.data:
                normalized.append(key)
        unmapped = sorted(set(glyphs)-mapping.keys())
        if unmapped:
            row_issues.append('unmapped_glyphs')
        rows.append(dict(id=key, rom_offset=f'0x{before.offset:08X}', byte_length=before.capacity,
                         source_sha256=sha(before.data), source_text=english, translation=chinese,
                         status='review', notes='Private human 0.6 import; glyph mapping is review data',
                         translated_rom_offset=f'0x{after.offset:08X}', translated_byte_length=after.capacity,
                         translated_sha256=sha(after.data), original_lines=before.original_lines,
                         translated_lines=after.original_lines, controls_original=json.dumps(old_controls),
                         controls_translated=json.dumps(new_controls), glyph_ids=json.dumps(glyphs),
                         unmapped_glyph_ids=json.dumps(unmapped), issues=';'.join(row_issues)))
        if candidate is not None and key in candidate:
            current = candidate[key]
            text, current_controls, _, _ = decode(current.data, True, mapping)
            rows[-1].update(candidate_translation=text, candidate_sha256=sha(current.data),
                candidate_rom_offset=f'0x{current.offset:08X}', candidate_byte_length=current.capacity,
                candidate_controls=json.dumps(current_controls), candidate_lines=current.original_lines)
        issues.extend(dict(id=key, issue=issue, rom_offset=f'0x{after.offset:08X}') for issue in row_issues)
    fields = list(rows[0])
    csv_file(output/'human-0.6-private.csv', fields, rows)
    csv_file(output/'text-issues.csv', ['id','issue','rom_offset'], issues)
    arc = Archive(reference)
    for name in ['UseMoji_table','UseMoji_image','FontWidthTable','fontpalette']:
        data, entry = arc.read('menu/font/'+name+'.bin')
        (output/(name+'.bin')).write_bytes(data)
    font, entry = arc.read('menu/font/UseMoji_image.bin')
    widths, width_entry = arc.read('menu/font/FontWidthTable.bin')
    glyph_rows = []
    for i in range(4368):
        offset = u32(font, 2+4*i)
        if offset+4 > len(font):
            raise ValueError('Glyph pointer is out of range')
        length, pad = font[offset:offset+2]
        bits = bytes(64) if pad == 255 else bytes((pad >> 4)*4)+font[offset+4:offset+length]+bytes((pad & 15)*4)
        if len(bits) != 64 or offset+length > len(font):
            raise ValueError('Glyph expansion is invalid')
        code = i+0xa858 if i >= 168 else i+1
        # Binary glyph payload remains private; its hash supports later font imports.
        glyph_rows.append(dict(glyph_index=i, code_hex=f'{code:04X}' if i >= 168 else f'{code:02X}',
                               unicode=mapping.get(i, '') if i >= 168 else WESTERN.get(i+1,''),
                               mapping_status='review' if i >= 168 and i in mapping else 'unmapped' if i >= 168 else 'western',
                               uses=usage[i], rom_offset=f"0x{entry['offset']+offset:08X}",
                               record_bytes=length, width_table_index=u16(font,offset+2),
                               advance_pixels=widths[2+u16(font,offset+2)], expanded_sha256=sha(bits)))
    csv_file(output/'glyph-map-private.csv', list(glyph_rows[0]), glyph_rows)
    csv_file(output/'width-table-private.csv', ['glyph_index','width_table_index','advance_pixels'],
             [{k:row[k] for k in ('glyph_index','width_table_index','advance_pixels')} for row in glyph_rows])
    palette, _ = arc.read('menu/font/fontpalette.bin')
    palette_rows = [dict(palette=p, index=i, bgr555=f'{u16(palette,1+(p*16+i)*2):04X}')
                    for p in range(palette[0]) for i in range(16)]
    csv_file(output/'palettes-private.csv', list(palette_rows[0]), palette_rows)
    report = dict(schema_version=1, source_rom_sha256=USA_SHA, reference_06_sha256=REFERENCE_SHA,
                  text_rows=len(rows), issue_counts=dict(collections.Counter(i['issue'] for i in issues)),
                  unique_used_chinese_glyphs=len(usage), mapped_used_chinese_glyphs=len(set(usage)&mapping.keys()),
                  mapping_is_review_data=True, candidate_text_mismatches=preserved,
                  candidate_all_human_tokens_preserved=candidate is not None and not preserved and not verified_revisions,
                  candidate_all_unrevised_human_tokens_preserved=candidate is not None and not preserved,
                  candidate_all_changes_documented=candidate is not None and not preserved and set(verified_revisions) == set(revisions),
                  candidate_padding_repairs=normalized,
                  candidate_recorded_revisions=verified_revisions,
                  machine_translation_imported=False, private_do_not_publish=True)
    if candidate is not None:
        report['candidate_codec_issue_counts'] = dict(collections.Counter(
            issue for slot in candidate.values() for issue in decode(slot.data,True,mapping)[3]))
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    if preserved or set(verified_revisions) != set(revisions):
        raise ValueError('Candidate changed private human text payloads')


if __name__ == '__main__':
    main()
