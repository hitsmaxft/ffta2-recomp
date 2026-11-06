#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse,hashlib
from pathlib import Path
from bps import apply
p=argparse.ArgumentParser(description='Apply a BPS patch without overwriting the source ROM');p.add_argument('rom',type=Path);p.add_argument('patch',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.resolve()==a.rom.resolve():p.error('Output must differ from the original ROM')
if a.output.exists():p.error('Output already exists')
data=apply(a.rom.read_bytes(),a.patch.read_bytes());a.output.write_bytes(data);print(hashlib.sha256(data).hexdigest())
