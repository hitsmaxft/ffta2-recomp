#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert a locally validated test ROM to BPS, source-copying retail glyphs."""
import argparse
import hashlib
import json
from pathlib import Path
from bps import build,apply
from build_cn_patch import Archive,SHA,u16,u32
ROOT=Path(__file__).resolve().parents[1]


def difference_segments(source,target,copies=()):
    if len(source)!=len(target):
        raise ValueError('Test packaging requires unchanged ROM size')
    segments=[]
    def emit(part):
        if part[0]=='source' and part[2]==0 or part[0]=='literal' and not part[1]:
            return
        if segments and part[0]==segments[-1][0]:
            previous=segments[-1]
            if part[0]=='literal':
                segments[-1]=('literal',previous[1]+part[1]);return
            if previous[1]+previous[2]==part[1]:
                segments[-1]=('source',previous[1],previous[2]+part[2]);return
        segments.append(part)
    def diff(start,end):
        for chunk in range(start,end,32768):
            stop=min(chunk+32768,end)
            before=source[chunk:stop];after=target[chunk:stop]
            if before==after:
                emit(('source',chunk,stop-chunk));continue
            pos=chunk
            while pos<stop:
                same=source[pos]==target[pos];last=pos+1
                while last<stop and (source[last]==target[last])==same:
                    last+=1
                emit(('source',pos,last-pos) if same else ('literal',target[pos:last]))
                pos=last
    cursor=0
    for destination,origin,length in sorted(copies):
        if destination<cursor or length<0 or origin<0 or origin+length>len(source) or destination+length>len(target):
            raise ValueError('SourceCopy range invalid or overlapping')
        if target[destination:destination+length]!=source[origin:origin+length]:
            raise ValueError('Relocated retail asset differs from source')
        diff(cursor,destination)
        emit(('source',origin,length));cursor=destination+length
    diff(cursor,len(target))
    return segments


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('target',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--scope',required=True)
    p.add_argument('--experiment-receipt',type=Path)
    p.add_argument('--bank-index',type=Path)
    a=p.parse_args()
    dest=a.output.resolve()
    if dest.suffix!='.bps' or dest in (a.source.resolve(),a.target.resolve()) or ROOT==dest or ROOT in dest.parents:
        p.error('Write an external .bps file, separate from both inputs')
    source=a.source.read_bytes();target=a.target.read_bytes()
    if hashlib.sha256(source).hexdigest()!=SHA:
        raise ValueError('Unsupported source identity')
    before,entry=Archive(source).read('menu/font/UseMoji_image.bin')
    after,newentry=Archive(target).read('menu/font/UseMoji_image.bin')
    if u16(before)!=168 or u16(after)<168:
        raise ValueError('Unsupported retail font layout')
    origin=u32(before,2);destination=u32(after,2)
    last=u32(before,2+4*167);length=last+before[last]-origin
    for i in range(168):
        if u32(after,2+4*i)-destination!=u32(before,2+4*i)-origin:
            raise ValueError('Retail glyph record offsets changed')
    copies=[(newentry['offset']+destination,entry['offset']+origin,length)]
    segments=difference_segments(source,target,copies)
    patch,recreated=build(source,segments,a.scope.encode())
    if recreated!=target or apply(source,patch)!=target:
        raise ValueError('Independent patch reconstruction failed')
    receipt=dict(schema_version=1,scope=a.scope,source_sha256=SHA,
                 target_sha256=hashlib.sha256(target).hexdigest(),
                 patch_sha256=hashlib.sha256(patch).hexdigest(),patch_size=len(patch),
                 original_font_sourcecopy_bytes=length,independent_apply_verified=True,
                 full_game_translation=False)
    if a.experiment_receipt:
        experiment=json.loads(a.experiment_receipt.read_text())
        if experiment['source_sha256']!=SHA or experiment['target_sha256']!=receipt['target_sha256']:
            raise ValueError('Experiment receipt target identity differs')
        receipt['experiment']=experiment
        if a.bank_index:
            glyphs=json.loads(a.bank_index.read_text())['glyphs']
            bank,_=Archive(target).read('menu/font/CJKtest4.bin')
            if len(glyphs)!=experiment['glyph_count'] or len(bank)!=64*len(glyphs) or hashlib.sha256(bank).hexdigest()!=experiment['font_bank_sha256']:
                raise ValueError('Full font bank receipt/map differs')
            receipt['bank_glyphs']=glyphs
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(patch)
    dest.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('experiment','bank_glyphs')},indent=2))

if __name__=='__main__':main()
