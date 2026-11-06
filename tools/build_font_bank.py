#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate indexed 2bpp CJK bank data from an external OFL BDF and glyph recipe."""
import argparse
import hashlib
import json
from pathlib import Path
from build_cn_patch import bdf_glyphs
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--font',required=True,type=Path);p.add_argument('--recipe',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--index',required=True,type=Path)
    a=p.parse_args()
    if a.output.resolve()==a.index.resolve():p.error('Bank and index outputs must differ')
    for dest in (a.output.resolve(),a.index.resolve()):
        if dest==ROOT or ROOT in dest.parents or dest in (a.font.resolve(),a.recipe.resolve()):
            p.error('Generated bank/index must stay external and separate from inputs')
    recipe=json.loads(a.recipe.read_text());chars=recipe.get('bank_glyphs',recipe.get('glyphs'))
    if not isinstance(chars,list) or not chars or len(chars)>23*255 or len(set(chars))!=len(chars) or any(not isinstance(c,str) or len(c)!=1 for c in chars):
        p.error('Expected unique single-character glyph recipe within bank capacity')
    glyphs=bdf_glyphs(a.font,set(chars));bank=b''.join(glyphs[c] for c in chars);identity=hashlib.sha256(bank).hexdigest()
    expected=recipe.get('experiment',{}).get('font_bank_sha256')
    if expected and expected!=identity:raise ValueError('Generated font differs from tested patch receipt')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.index.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(bank)
    a.index.write_text(json.dumps(dict(glyphs=chars,count=len(chars),bytes=len(bank),font_sha256=hashlib.sha256(a.font.read_bytes()).hexdigest(),bank_sha256=identity,index_roles={'0':'transparent','1':'outline','2':'shadow','3':'foreground'}),ensure_ascii=False,indent=2)+'\n')
    print('Generated',len(chars),'glyphs; SHA256',identity)

if __name__=='__main__':main()
