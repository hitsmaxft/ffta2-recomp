#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze the pinned retail ROM into an external private directory."""
import argparse,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('rom',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];out=a.output.resolve();rom=a.rom.resolve()
if out==root or root in out.parents:p.error('Resource output must be outside the source checkout')
link=out/'rom/retail.nds';link.parent.mkdir(parents=True,exist_ok=True)
if not link.exists():link.symlink_to(rom)
elif link.resolve()!=rom:p.error('Output directory already belongs to another ROM')
env=dict(os.environ,FFTA2_ANALYSIS_DIR=str(out))
for tool in ['inspect_rom','resources','extract_text_font']:
 subprocess.run([sys.executable,str(root/'tools'/f'{tool}.py')],env=env,check=True)
