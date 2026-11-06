#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Allowlisted ROM-free patch bundle; generated retail assets are never staged."""
import argparse,zipfile,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('patch',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1]
if a.patch.suffix!='.bps':p.error('Expected a .bps patch')
receipt=json.loads(a.patch.with_suffix('.json').read_text())
with zipfile.ZipFile(a.output,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for src,name in [(a.patch,'prologue-cn.bps'),(a.patch.with_suffix('.json'),'prologue-cn.json'),(root/'tools/apply_cn_patch.py','tools/apply_cn_patch.py'),(root/'tools/bps.py','tools/bps.py'),(root/'LICENSE','LICENSE'),(root/'docs/fusion-pixel-OFL.txt','fusion-pixel-OFL.txt')]:z.write(src,name)
 z.writestr('README.txt','CN prototype for FFTA2 EU A6FP revision 0. Scope: '+receipt['scope']+'\nRequires your original ROM.\nApply: python3 tools/apply_cn_patch.py original.nds prologue-cn.bps --output cn.nds\nNo ROM, save, original font, or generated game code is included.\n')
print(a.output)
