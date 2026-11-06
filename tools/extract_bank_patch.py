#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify and extract D0-banked Chinese fonts/text from a local BPS application."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from bps import apply
from build_cn_patch import Archive,u16
from text_resources import TextResources

ROOT=Path(__file__).resolve().parents[1]

def decode(data,glyphs,charset):
    mapping={int(item['code_hex'],16):item['display'] for item in charset['entries']}
    result=[];pos=0
    while pos<len(data):
        code=data[pos];pos+=1
        if code==0xd0:
            if pos+2>len(data):raise ValueError('Truncated banked glyph')
            bank,low=data[pos:pos+2];pos+=2
            index=(bank-1)*23+low-0xa9
            if bank<1 or not 0xa9<=low<=0xbf or not 0<=index<len(glyphs):raise ValueError('Invalid banked glyph index')
            result.append(glyphs[index])
        elif code>=0xc0:
            if pos>=len(data):raise ValueError('Truncated control pair')
            parameter=data[pos];pos+=1
            text=mapping.get(code*256+parameter)
            if text is None:
                text=mapping.get(code)
                if text is None:raise ValueError('Unknown control pair')
                if '%02X' in text:text=text.replace('%02X',f'{parameter:02X}')
                elif parameter!=0:raise ValueError('Unexpected fixed-control parameter')
            result.append(text)
        elif code:
            if code not in mapping:raise ValueError('Unknown original glyph')
            result.append(mapping[code])
        else:
            raise ValueError('NUL within declared text allocation')
    return ''.join(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom',type=Path);p.add_argument('patch',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();dest=a.output.resolve()
    if dest==ROOT or ROOT in dest.parents or dest in (a.rom.resolve(),a.patch.resolve()):p.error('Extraction output must stay external and separate from inputs')
    receipt=json.loads(a.patch.with_suffix('.json').read_text());source=a.rom.read_bytes();patch=a.patch.read_bytes()
    if hashlib.sha256(source).hexdigest()!=receipt['source_sha256'] or hashlib.sha256(patch).hexdigest()!=receipt['patch_sha256']:
        raise ValueError('Source/patch identity mismatch')
    target=apply(source,patch)
    if hashlib.sha256(target).hexdigest()!=receipt['target_sha256']:raise ValueError('Target identity mismatch')
    glyphs=receipt['bank_glyphs'];experiment=receipt['experiment'];arc=Archive(target)
    bank,entry=arc.read('menu/font/CJKtest4.bin')
    if len(bank)!=len(glyphs)*64 or hashlib.sha256(bank).hexdigest()!=experiment['font_bank_sha256']:
        raise ValueError('Font bank differs from receipt')
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'font-bank.bin').write_bytes(bank)
    with (a.output/'font-map.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
        writer.writerow(['index','character','unicode','encoded_hex','width_px','rom_offset','glyph_sha256'])
        for index,char in enumerate(glyphs):
            writer.writerow([index,char,f'U+{ord(char):04X}',bytes((0xd0,index//23+1,0xa9+index%23)).hex(),12,f"0x{entry['offset']+64*index:08X}",hashlib.sha256(bank[index*64:index*64+64]).hexdigest()])
    resources={}
    for name in ('UseMoji_table','UseMoji_image','FontWidthTable','fontpalette'):
        raw,location=arc.read('menu/font/'+name+'.bin');(a.output/(name+'.bin')).write_bytes(raw);resources[name]=location
        if name=='FontWidthTable':
            (a.output/'widths.json').write_text(json.dumps(dict(retail_widths=list(raw[2:2+u16(raw)]),cjk_width=12),indent=2)+'\n')
    original=TextResources(source);charset=json.loads((ROOT/'config/western-charset.json').read_text())
    with (a.output/'texts.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\r\n');writer.writerow(['id','rom_offset','source_sha256','encoded_bytes','original_capacity','translation'])
        for row in experiment['translations']:
            slot=original.locate(row['id']);size=int.from_bytes(target[slot.length_field:slot.length_field+4],'little')
            if size>slot.capacity:raise ValueError('Translated slot overflows original allocation')
            text=decode(target[slot.offset:slot.offset+size],glyphs,charset)
            if text!=row['text'] or size!=row['text_bytes'] or hashlib.sha256(slot.data).hexdigest()!=row['source_sha256']:
                raise ValueError('Translation/source differs from receipt')
            writer.writerow([row['id'],f'0x{slot.offset:08X}',row['source_sha256'],size,slot.capacity,text])
    (a.output/'resource-addresses.json').write_text(json.dumps(resources,ensure_ascii=False,indent=2)+'\n')
    (a.output/'verified.json').write_text(json.dumps(dict(target_sha256=receipt['target_sha256'],glyph_count=len(glyphs),text_count=len(experiment['translations']),source_patch_target_verified=True),indent=2)+'\n')
    print('Verified bank glyphs:',len(glyphs),'translations:',len(experiment['translations']))

if __name__=='__main__':main()
