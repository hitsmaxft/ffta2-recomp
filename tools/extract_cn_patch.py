#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract/check font and text payload from a BPS-applied image, in memory."""
import argparse,csv,json,hashlib,struct
from pathlib import Path
from PIL import Image,ImageDraw
from bps import apply
from build_cn_patch import Archive,u16,u32
p=argparse.ArgumentParser();p.add_argument('rom',type=Path);p.add_argument('patch',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();root=Path(__file__).resolve().parents[1]
if a.output.resolve()==root or root in a.output.resolve().parents:p.error('Output must stay outside the source checkout')
receipt=json.loads(a.patch.with_suffix('.json').read_text());source=a.rom.read_bytes()
if hashlib.sha256(source).hexdigest()!=receipt['source_sha256']:raise ValueError('Source identity mismatch')
patch=a.patch.read_bytes()
if hashlib.sha256(patch).hexdigest()!=receipt['patch_sha256']:raise ValueError('Patch receipt mismatch')
raw=apply(source,patch)
if hashlib.sha256(raw).hexdigest()!=receipt['target_sha256']:raise ValueError('Target identity mismatch')
arc=Archive(raw);a.output.mkdir(parents=True,exist_ok=True);resources={}
for name in ['UseMoji_table','UseMoji_image','FontWidthTable','fontpalette']:
 data,e=arc.read('menu/font/'+name+'.bin');(a.output/(name+'.bin')).write_bytes(data);resources[name]=dict(e)
font,fe=arc.read('menu/font/UseMoji_image.bin');width,_=arc.read('menu/font/FontWidthTable.bin');table,_=arc.read('menu/font/UseMoji_table.bin');chars=table.decode('utf-8-sig').rstrip('\0');assert len(chars)==u16(font)==u16(width)
western=json.loads((root/'config/western-charset.json').read_text());mapping={int(e['code_hex'],16):e['display'] for e in western['entries']};mapping.update({code:c for c,code in receipt['characters'].items()})
n=u16(font);atlas=Image.new('RGB',(16*64,((n+15)//16)*76),'#eeeeee');draw=ImageDraw.Draw(atlas);rows=[]
for i in range(n):
 o=u32(font,2+4*i);length=font[o];pad=font[o+1]
 data=bytes(64) if pad==255 else bytes((pad>>4)*4)+font[o+4:o+length]+bytes((pad&15)*4)
 if len(data)!=64:raise ValueError('Glyph does not expand to 64 bytes')
 im=Image.new('RGB',(16,16),'white')
 for y in range(16):
  v=u32(data,y*4)
  for x in range(16):im.putpixel((x,y),[(255,255,255),(170,170,170),(220,220,220),(0,0,0)][v>>(2*x)&3])
 x=i%16*64;y=i//16*76;atlas.paste(im.resize((48,48),Image.Resampling.NEAREST),(x+8,y+22));draw.text((x+4,y+3),'%02X w%d'%(i+1,width[2+i]),fill='black')
 rows.append([f'{i+1:02X}',mapping.get(i+1,''),chars[i],width[2+i],f'0x{fe["offset"]+o:08X}',length,data.hex()])
atlas.save(a.output/'font-atlas.png')
with (a.output/'glyph-map.tsv').open('w') as f:
 w=csv.writer(f,delimiter='\t');w.writerow(['text_code_hex','decoded_character','table_label','width','glyph_rom_offset','record_length','expanded_2bpp_hex']);w.writerows(rows)
(a.output/'resource-addresses.json').write_text(json.dumps(resources,indent=2))
with (a.output/'translations.tsv').open('w') as f:
 w=csv.writer(f,delimiter='\t');w.writerow(['id','rom_offset','byte_length','text']);w.writerows([r['id'],f"0x{r['rom_offset']:08X}",r['byte_length'],r['text']] for r in receipt['translations'])
print('Verified/extracted',n,'glyphs; target SHA-256',receipt['target_sha256'])
