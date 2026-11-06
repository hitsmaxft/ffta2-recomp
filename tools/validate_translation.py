#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed encoding and conservative layout preflight; never edits a ROM.

Passing this check is not a claim that every retail UI path has been tested.
Unmeasured dynamic substitutions and source decoding anomalies require review.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from text_catalog import read_rows, normalize_newlines

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'\\[^\\\r\n]+\\|<[^>\r\n]+>')

class RetailCodec:
    def __init__(self, charset, widths, extra=None, extended_bytes=None):
        self.glyphs = {}
        self.tokens = {}
        self.patterns = []
        self.extra = extra or {}
        self.extended_bytes = extended_bytes
        self.widths = widths
        for item in charset['entries']:
            code = int(item['code_hex'], 16)
            text = item['display']
            if '%02X' in text:
                self.patterns.append((re.compile('^' + re.escape(text).replace('%02X', '([0-9A-Fa-f]{2})') + '$'), code))
            elif code > 255:
                self.tokens[text] = code.to_bytes(2, 'big')
            elif code >= 0xc0:
                # Parameterless aliases, if any, must still consume a pair.
                self.tokens[text] = bytes([code, 0])
            elif len(text) == 1:
                self.glyphs[text] = code
            else:
                self.tokens[text] = bytes([code])

    def token_bytes(self, text):
        if text in self.tokens:
            return self.tokens[text]
        for pattern, code in self.patterns:
            match = pattern.fullmatch(text)
            if match:
                return bytes([code, int(match[1], 16)])
        raise ValueError('Unrecognized script token: ' + repr(text))

    def analyze(self, text):
        text = normalize_newlines(text)
        size = 0
        pages = [[0]]
        controls = []
        dynamic = []
        pos = 0
        while pos < len(text):
            match = TOKEN.match(text, pos)
            if match:
                token = match[0]
                encoded = self.token_bytes(token)
                size += len(encoded)
                if len(encoded) == 1:
                    pages[-1][-1] += self.widths[encoded[0] - 1]
                controls.append(token)
                if token == '\\endPage\\' or token == '\\endOption\\':
                    pages.append([0])
                elif token.startswith(('\\var', '\\sprite:')):
                    dynamic.append(token)
                pos = match.end()
                continue
            char = text[pos]
            pos += 1
            if char == '\n':
                size += 2
                pages[-1].append(0)
            elif char in self.extra:
                size += 1
                pages[-1][-1] += 12
            elif char in self.glyphs:
                code = self.glyphs[char]
                if code == 0:
                    raise ValueError('NUL/zero glyph in text')
                size += 1
                if code > len(self.widths):
                    raise ValueError('Width missing for glyph')
                pages[-1][-1] += self.widths[code - 1]
            elif ord(char) > 127 and self.extended_bytes:
                size += self.extended_bytes
                pages[-1][-1] += 12
            else:
                raise ValueError('Unencodable character: ' + repr(char))
        # Empty page produced by a closing page delimiter has no text footprint.
        return dict(encoded_bytes=size, pages=pages, controls=controls, dynamic_tokens=dynamic)


def inspect_row(row, original, codec):
    errors = []
    warnings = []
    try:
        src = codec.analyze(original['source_text'])
        dst = codec.analyze(row['translation'])
    except ValueError as exc:
        return dict(id=row['id'], errors=[str(exc)], warnings=[])
    if row['source_sha256'] != original['source_sha256']:
        errors.append('Source identity differs')
    if src['controls'] != dst['controls']:
        errors.append('Control sequence or parameters differ')
    capacity = int(original['byte_length'])
    if dst['encoded_bytes'] > capacity:
        errors.append(f"Encoded length {dst['encoded_bytes']} exceeds original allocation {capacity}")
    if src['encoded_bytes'] != capacity:
        errors.append('Source decoding does not round-trip original byte length')
    if len(src['pages']) != len(dst['pages']):
        errors.append('Page/option count differs')
    for index, (before, after) in enumerate(zip(src['pages'], dst['pages'])):
        # Original text is only a conservative footprint, not a measured UI box.
        if len(after) > len(before):
            errors.append(f'Page {index}: additional lines')
        if max(after, default=0) > max(before, default=0):
            errors.append(f'Page {index}: wider than original text footprint')
    if dst['dynamic_tokens']:
        warnings.append('Dynamic substitutions need runtime width validation')
    return dict(id=row['id'], encoded_bytes=dst['encoded_bytes'], capacity=capacity,
                source_pages=src['pages'], translation_pages=dst['pages'], errors=errors, warnings=warnings)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', type=Path)
    p.add_argument('--catalog', required=True, type=Path)
    p.add_argument('--widths', required=True, type=Path)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--patch-receipt', type=Path, help='Verified legacy glyph code map')
    group.add_argument('--planned-cjk-bytes', type=int, choices=[2, 3], help='Planning only, does not assert runtime support')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    if ROOT == args.output.resolve() or ROOT in args.output.resolve().parents:
        p.error('Private reports must stay outside the checkout')
    raw = args.widths.read_bytes()
    count = int.from_bytes(raw[:2], 'little')
    if len(raw) < 2 + count:
        p.error('Truncated width table')
    extra = json.loads(args.patch_receipt.read_text())['characters'] if args.patch_receipt else {}
    codec = RetailCodec(json.loads((ROOT/'config/western-charset.json').read_text()), list(raw[2:2+count]), extra, args.planned_cjk_bytes)
    refs = {row['id']:row for row in read_rows(args.catalog)}
    results = []
    for row in read_rows(args.csv):
        if row['status'] != 'translated':
            continue
        if row['id'] not in refs:
            results.append(dict(id=row['id'], errors=['Unknown source ID'], warnings=[]))
        else:
            results.append(inspect_row(row, refs[row['id']], codec))
    failed = sum(bool(r['errors']) for r in results)
    report = dict(schema_version=1, csv_sha256=hashlib.sha256(args.csv.read_bytes()).hexdigest(),
                  translated_rows=len(results), failed_rows=failed,
                  planning_only=bool(args.planned_cjk_bytes),
                  runtime_verified=False, results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}, ensure_ascii=False))
    raise SystemExit(1 if failed else 0)

if __name__ == '__main__':
    main()
