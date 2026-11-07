# SPDX-License-Identifier: GPL-3.0-or-later
"""Hash-guarded CSV revisions and append-only rebuilding of message blocks."""
import csv
import hashlib
import json
from pathlib import Path
import struct
from build_cn_patch import align, u16, u32
from usa_text import slots, tokens
from validate_translation import RetailCodec, TOKEN

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def add_newline(data, after_glyph):
    if after_glyph < 1:
        raise ValueError('Invalid newline glyph position')
    source = tokens(data)
    count = 0
    for index, token in enumerate(source):
        if token[0] < 0xc0:
            count += 1
            if count == after_glyph:
                return b''.join(source[:index + 1] + [b'\xc0\0'] + source[index + 1:])
    raise ValueError('Newline position outside text')


def encode(text, approved):
    charset = json.loads((ROOT / 'config/western-charset.json').read_text())
    codec = RetailCodec(charset, [0] * 168)
    out = bytearray()
    pos = 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if match:
            out.extend(codec.token_bytes(match[0]))
            pos = match.end()
            continue
        c = text[pos]
        pos += 1
        if c == '\n':
            out.extend(b'\xc0\0')
        elif c in codec.glyphs and 1 <= codec.glyphs[c] <= 168:
            out.append(codec.glyphs[c])
        elif c in approved:
            index = approved[c]
            if not isinstance(index, int) or not 168 <= index < 4368:
                raise ValueError('Invalid approved glyph index')
            out.extend((index + 0xa858).to_bytes(2, 'big'))
        else:
            raise ValueError('Character lacks reviewed glyph mapping: ' + repr(c))
    return bytes(out)


def read_edits(reference, path, approved):
    source = {s.id: s for s in slots(reference)}
    changes, records = {}, []
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['id', 'source_sha256', 'operation', 'value', 'lines', 'reason']:
            raise ValueError('Unexpected revision CSV schema')
        for row in reader:
            key = row['id']
            if None in row or any(v is None for v in row.values()) or key in changes or key not in source:
                raise ValueError('Malformed, duplicate or unknown revision row')
            before = source[key]
            if row['source_sha256'] != digest(before.data) or not row['reason']:
                raise ValueError('Revision source hash/reason mismatch: ' + key)
            if row['operation'] == 'newline_after_glyph':
                after = add_newline(before.data, int(row['value']))
            elif row['operation'] == 'replace':
                after = encode(row['value'], approved)
                # Plain UI strings use a top-level NUL, unlike script C1 pages.
                if (sum(map(len, tokens(before.data))) < len(before.data) and
                        not any(t[0] == 0xc1 for t in tokens(before.data))):
                    after += b'\0'
            else:
                raise ValueError('Unsupported revision operation')
            controls = lambda data: [t for t in tokens(data) if t[0] >= 0xc0 and t[0] != 0xc0]
            if controls(before.data) != controls(after):
                raise ValueError('Revision altered protected controls: ' + key)
            lines = int(row['lines'])
            if not 0 <= lines <= 255:
                raise ValueError('Invalid revised line metadata')
            changes[key] = (after, lines)
            records.append(dict(id=key, before_sha256=digest(before.data), after_sha256=digest(after),
                before_bytes=len(before.data), after_bytes=len(after), before_lines=before.original_lines,
                after_lines=lines, operation=row['operation'], reason=row['reason'],
                protected_controls_preserved=True))
    return changes, records


def rebuild_multi(idx, pak, edits):
    """Append replacements inside each affected block; update every IDX boundary.

    Unedited payload bytes are retained. No text is squeezed into the original
    allocation. Resource relocation happens separately in the archive owner.
    """
    if len(idx) < 10 or u32(idx) != 0 or any(idx[4 + ((len(idx) - 4) // 6) * 6:]):
        raise ValueError('Malformed message index')
    count = (len(idx) - 4) // 6
    blocks = {}
    for key, (data, lines) in edits.items():
        family, language, block, sid = key.split(':')
        block, sid = int(block), int(sid)
        if family != 'message' or language != '0' or not 0 <= block < count - 1:
            raise ValueError('Only language-0 multi-message revisions are supported')
        blocks.setdefault(block, {})[sid] = (data, lines)
    replacements = []
    for block, strings in sorted(blocks.items()):
        v = u32(idx, 4 + 6 * block)
        start = ((v & 0x7ffffff) >> 3) * 4
        end = ((u32(idx, 10 + 6 * block) & 0x7ffffff) >> 3) * 4
        if v & 7 or not 0 <= start < end <= len(pak):
            raise ValueError('Revision block is absent or out of bounds')
        data = bytearray(pak[start:end])
        entries = u16(data)
        if 2 + entries * 10 > len(data):
            raise ValueError('Message header out of bounds')
        for sid, (text, lines) in sorted(strings.items()):
            if not 0 <= sid < entries:
                raise ValueError('Revision string is absent')
            field = 2 + 10 * sid
            old_size, old_offset = struct.unpack_from('<II', data, field)
            if old_offset < 2 + entries * 10 or old_offset + old_size > end - start:
                raise ValueError('Original text allocation out of bounds')
            data.extend(bytes(align(len(data)) - len(data)))
            offset = len(data)
            data.extend(text)
            struct.pack_into('<IIH', data, field, len(text), offset, lines)
        data.extend(bytes(align(len(data)) - len(data)))
        replacements.append((start, end, bytes(data)))
    result = bytearray()
    cursor = 0
    for start, end, data in replacements:
        if start < cursor:
            raise ValueError('Overlapping revision blocks')
        result.extend(pak[cursor:start])
        result.extend(data)
        cursor = end
    result.extend(pak[cursor:])
    new_idx = bytearray(idx)
    for i in range(count):
        v = u32(idx, 4 + 6 * i)
        offset = ((v & 0x7ffffff) >> 3) * 4
        if offset > len(pak):
            raise ValueError('Original index boundary outside resource')
        offset += sum(len(data) - (end - start) for start, end, data in replacements if end <= offset)
        packed = (offset // 4) << 3
        if offset % 4 or packed > 0x7fffff8:
            raise ValueError('Rebuilt index offset cannot be represented')
        struct.pack_into('<I', new_idx, 4 + 6 * i, (v & ~0x7fffff8) | packed)
    return bytes(new_idx), bytes(result)


def apply_edits(arc, payload, changes):
    from text_resources import PATHS
    ip, pp, _ = PATHS['message']
    idx, ie = arc.read(ip.format(lang=0))
    pak, pe = arc.read(pp.format(lang=0))
    idx, pak = rebuild_multi(idx, pak, changes)
    for entry, data in ((pe, pak), (ie, idx)):
        payload.extend(bytes(align(len(payload)) - len(payload)))
        at = len(payload)
        payload.extend(data)
        payload.extend(bytes(align(len(payload)) - len(payload)))
        arc.redirect(entry, arc.base + at, align(len(data)))
