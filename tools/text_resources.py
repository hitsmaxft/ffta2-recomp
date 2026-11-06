#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded retail text lookup shared by translation audits and patch builders."""
from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
from build_cn_patch import Archive, SHA, u16, u32
from text_catalog import read_rows

PATHS = {
    'event': ('event/rom/ev_msg{lang}_rom.idx', 'event/rom/ev_msg{lang}.pak', False),
    'message': ('system/rom/JD_message_rom_{lang}.idx', 'system/rom/JD_message_{lang}.pak', False),
    **{name: (f'system/rom/JH_{name}_rom_{{lang}}.idx', f'system/rom/JH_{name}_{{lang}}.pak', True)
       for name in ('questtext', 'uwasatext', 'freepapermes')},
}

@dataclass(frozen=True)
class TextSlot:
    id: str
    offset: int
    capacity: int
    length_field: int
    lines_field: int
    original_lines: int
    data: bytes


def block_slot(idx, pak, base, key, block, sid, single):
    if len(idx) < 10 or u32(idx) != 0:
        raise ValueError('Malformed message index: '+key)
    count = (len(idx)-4)//6
    if not 0 <= block < count-1:
        raise ValueError('Block outside message index: '+key)
    packed = u32(idx, 4+6*block)
    if packed & 7:
        raise ValueError('Absent message block: '+key)
    start = ((packed & 0x7ffffff) >> 3)*4
    end = ((u32(idx, 4+6*(block+1)) & 0x7ffffff) >> 3)*4
    if not 0 <= start < end <= len(pak):
        raise ValueError('Message block outside archive resource: '+key)
    if single:
        if sid != 0 or start+14 > end:
            raise ValueError('Invalid single-string header: '+key)
        length_field, offset, lines_field = start+4, start+14, start+12
        capacity = u32(pak, length_field)
    else:
        if start+2 > end:
            raise ValueError('Truncated string table: '+key)
        entries = u16(pak, start)
        table_end = start+2+10*entries
        if table_end > end or not 0 <= sid < entries:
            raise ValueError('Invalid string table entry: '+key)
        length_field = start+2+10*sid
        capacity = u32(pak, length_field)
        offset = start+u32(pak, length_field+4)
        lines_field = length_field+8
        if offset < table_end:
            raise ValueError('String overlaps table header: '+key)
    if offset+capacity > end:
        raise ValueError('String extends beyond block: '+key)
    return TextSlot(key, base+offset, capacity, base+length_field,
                    base+lines_field, u16(pak, lines_field), pak[offset:offset+capacity])


class TextResources:
    def __init__(self, raw):
        if hashlib.sha256(raw).hexdigest() != SHA:
            raise ValueError('Unsupported ROM identity')
        self.archive = Archive(raw)
        self.cache = {}

    def locate(self, key):
        family, language, block, sid = key.split(':')
        language, block, sid = int(language), int(block), int(sid)
        if family not in PATHS or language not in range(4):
            raise ValueError('Unsupported text resource: '+key)
        cache_key = (family, language)
        if cache_key not in self.cache:
            ip, pp, single = PATHS[family]
            idx, _ = self.archive.read(ip.format(lang=language))
            pak, entry = self.archive.read(pp.format(lang=language))
            self.cache[cache_key] = idx, pak, entry['offset'], single
        idx, pak, base, single = self.cache[cache_key]
        return block_slot(idx, pak, base, key, block, sid, single)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--catalog', required=True, type=Path)
    p.add_argument('--language', type=int, choices=range(4), default=0)
    p.add_argument('--output', required=True, type=Path)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if a.output.resolve()==a.rom.resolve() or root==a.output.resolve() or root in a.output.resolve().parents:
        p.error('Private reports must stay outside source and input ROM')
    resources=TextResources(a.rom.read_bytes())
    slots=[]
    intervals={}
    for row in read_rows(a.catalog):
        if int(row['id'].split(':')[1]) != a.language:
            continue
        slot=resources.locate(row['id'])
        if slot.capacity != int(row['byte_length']) or slot.offset != int(row['rom_offset'],16):
            raise ValueError('Catalog layout differs from ROM: '+slot.id)
        if hashlib.sha256(slot.data).hexdigest() != row['source_sha256']:
            raise ValueError('Catalog source identity differs from ROM: '+slot.id)
        intervals.setdefault((slot.offset, slot.capacity), []).append(slot.id)
        slots.append(dict(id=slot.id, rom_offset=slot.offset, capacity=slot.capacity,
                          length_field=slot.length_field, lines_field=slot.lines_field,
                          original_lines=slot.original_lines))
    report=dict(schema_version=1, rom_sha256=SHA, language=a.language, slots=slots,
                shared_allocations=[dict(offset=k[0],capacity=k[1],ids=v)
                                    for k,v in intervals.items() if len(v)>1])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(verified_slots=len(slots), shared_allocations=len(report['shared_allocations']))))

if __name__=='__main__': main()
