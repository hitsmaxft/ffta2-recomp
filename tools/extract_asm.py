#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export original executable images and explicit-mode assembly listings.
Linear listings include data; candidates are not proven function boundaries.
"""
import argparse,json,hashlib,struct
from pathlib import Path
import ndspy.rom,ndspy.code,ndspy.codeCompression
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM,CS_MODE_THUMB
P=argparse.ArgumentParser();P.add_argument('rom',type=Path);P.add_argument('--output',required=True,type=Path);a=P.parse_args();raw=a.rom.read_bytes()
if hashlib.sha256(raw).hexdigest()!='f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59':raise ValueError('Unsupported ROM revision')
root=Path(__file__).resolve().parents[1]
if a.output.resolve()==root or root in a.output.resolve().parents:raise ValueError('Executable exports must stay outside checkout')
a.output.mkdir(parents=True,exist_ok=True);rom=ndspy.rom.NintendoDSRom(raw)
known={0x20842f8:'font_load_character_table',0x2084344:'font_load_glyph_images',0x2084410:'font_initialize',0x20845f0:'font_expand_glyph_2bpp',0x20846d0:'font_convert_glyph_for_tiles',0x20848a0:'message_load_language_index',0x2084bc8:'message_load_table_sync',0x201fe38:'archive_open_named_resource',0x201fea0:'archive_get_resource_size',0x201ffa4:'archive_read_resource_sync',0x201ffe8:'archive_close_resource',0x204a95c:'text_is_control_byte',0x204a98c:'text_control_opcode',0x208609c:'heap_allocate_aligned',0x201f134:'heap_allocate_by_id'}
modules=[('arm9',rom.arm9RamAddress,ndspy.codeCompression.decompress(rom.arm9),rom.arm9EntryAddress),('arm7',rom.arm7RamAddress,ndspy.codeCompression.decompress(rom.arm7),rom.arm7EntryAddress)]
for cpu,table in [('arm9',rom.arm9OverlayTable),('arm7',rom.arm7OverlayTable)]:
 for oid,ov in ndspy.code.loadOverlayTable(table,lambda oid,fid:rom.files[fid]).items():modules.append((f'{cpu}_overlay_{oid:04d}',ov.ramAddress,bytes(ov.data),ov.staticInitStart))
manifest=[];functions=[]
for name,base,d,entry in modules:
 (a.output/f'{name}.bin').write_bytes(d);candidates={entry:'ROM/module entry (not necessarily a function boundary)'}
 for off in range(0,len(d)-3,4):
  word=struct.unpack_from('<I',d,off)[0]
  if word&0x0f000000==0x0b000000 and word>>28!=15:
   delta=word&0xffffff
   if delta&0x800000:delta-=0x1000000
   target=base+off+8+delta*4
   if base<=target<base+len(d):candidates.setdefault(target,'ARM BL target in linear scan; code/data not qualified')
 for address,label in known.items():
  if base<=address<base+len(d) and name=='arm9':candidates[address]='Call/dataflow evidence; semantic name inferred'
 for address,evidence in sorted(candidates.items()):functions.append(dict(module=name,address=address,address_hex=f'0x{address:08X}',name=known.get(address,f'sub_{address:08X}') if name=='arm9' else f'{name}_sub_{address:08X}',evidence=evidence,boundary_verified=False))
 for mode,flag in [('arm',CS_MODE_ARM),('thumb',CS_MODE_THUMB)]:
  cs=Cs(CS_ARCH_ARM,flag);cs.skipdata=True
  with (a.output/f'{name}.{mode}.s').open('w') as f:
   f.write('; Original bytes, linear '+mode+' decoding. DATA MAY APPEAR AS INSTRUCTIONS.\n; Mode and function boundaries need CFG qualification before recompilation.\n')
   for ins in cs.disasm(d,base):
    if ins.address in candidates:f.write(f'; candidate {known.get(ins.address, f"sub_{ins.address:08X}")} -- {candidates[ins.address]}\n')
    f.write(f'{ins.address:08X}: {ins.bytes.hex():<10} {ins.mnemonic:<9} {ins.op_str}\n')
 manifest.append(dict(module=name,base=base,entry=entry,size=len(d),sha256=hashlib.sha256(d).hexdigest()))
(a.output/'modules.json').write_text(json.dumps(manifest,indent=2));(a.output/'function-candidates.json').write_text(json.dumps(functions,indent=2));print('Modules:',len(modules),'candidates:',len(functions))
