# SPDX-License-Identifier: GPL-3.0-or-later
import os
from resources import *
from PIL import Image,ImageDraw,ImageFont
import csv,collections
res=json.loads((R/'resource_offsets.json').read_text()); charset=json.loads((Path(__file__).resolve().parents[1]/'config/western-charset.json').read_text()); cmap={int(e['code_hex'],16):e['display'] for e in charset['entries']}
D=R/'analysis';D.mkdir(exist_ok=True)
def decode(d):
 out=[];i=0
 while i<len(d):
  c=d[i];i+=1
  if c==0:continue
  if c>=0xc0:
   if i>=len(d):out.append('<TRUNCATED:%02X>'%c);continue
   p=d[i];i+=1
   key=c*256+p
   if key in cmap:out.append(cmap[key])
   elif c in cmap:out.append(cmap[c].replace('%02X','%02X'%p))
   else:out.append('<%02X%02X>'%(c,p))
  else:out.append(cmap.get(c,'<%02X>'%c))
 return ''.join(out)
def slices(idx,pak):
 assert u32(idx)==0
 nn=(len(idx)-4)//6; offsets=[]
 for i in range(nn):
  v=u32(idx,4+i*6);offsets.append(((v&0x7ffffff)>>3)*4)
 for i in range(nn-1):
  v=u32(idx,4+i*6)
  if v&7:continue
  o,e=offsets[i:i+2]
  if o==e:continue
  assert 0<=o<=e<=len(pak),(i,o,e,len(pak))
  yield i,o,pak[o:e]
summary=[];sample=[]
for lang in range(4):
 for family,idxpath,pakpath,single in [
 ('message',f'system/rom/JD_message_rom_{lang}.idx',f'system/rom/JD_message_{lang}.pak',False),
 ('event',f'event/rom/ev_msg{lang}_rom.idx',f'event/rom/ev_msg{lang}.pak',False),
 *[(f, f'system/rom/JH_{f}_rom_{lang}.idx',f'system/rom/JH_{f}_{lang}.pak',True) for f in ['questtext','uwasatext','freepapermes']]]:
  idx=(R/'resources'/idxpath).read_bytes();pak=(R/'resources'/pakpath).read_bytes();rows=[];blocks=0
  for bi,bo,block in slices(idx,pak):
   blocks+=1
   if single:
    le=u32(block,4);assert 14+le<=len(block);items=[(0,14,le,u16(block,12))]
   else:
    count=u16(block);assert 2+count*10<=len(block)
    items=[(i,u32(block,2+i*10+4),u32(block,2+i*10),u16(block,2+i*10+8)) for i in range(count)]
   for si,off,le,lines in items:
    assert off+le<=len(block),(lang,family,bi,si)
    txt=decode(block[off:off+le]); row=[bi,si,'0x%08X'%(res[pakpath]['rom_offset']+bo+off),le,lines,txt,block[off:off+le].hex()];rows.append(row)
    if len([x for x in sample if x['language']==lang and x['family']==family])<3 and len(txt)>3: sample.append(dict(language=lang,family=family,block=bi,string=si,text=txt[:140]))
  with (D/f'{family}_{lang}.tsv').open('w') as f:
   w=csv.writer(f,delimiter='\t');w.writerow(['block','string','rom_offset','byte_length','lines','text','raw_hex']);w.writerows(rows)
  summary.append(dict(language=lang,family=family,blocks=blocks,strings=len(rows)))
# Expand exactly as ARM9 020845F0: top/bottom blank scanlines, 16x16 2bpp.
font=(R/'resources/menu/font/UseMoji_image.bin').read_bytes(); widths=(R/'resources/menu/font/FontWidthTable.bin').read_bytes(); chars=(R/'resources/menu/font/UseMoji_table.bin').read_text(encoding='utf-8-sig').rstrip('\0');n=u16(font);assert n==u16(widths)==len(chars)
atlas=Image.new('RGB',(16*72,11*84),'#eeeeee');draw=ImageDraw.Draw(atlas);glyphrows=[]
for i in range(n):
 off=u32(font,2+4*i);length=font[off];pad=font[off+1];top=pad>>4;bottom=pad&15
 if pad==255: pixels=bytes(64)
 else:
  pixels=bytes(top*4)+font[off+4:off+length]+bytes(bottom*4);assert len(pixels)==64,(i,len(pixels),top,bottom,length)
 im=Image.new('RGB',(16,16),'white')
 for y in range(16):
  v=u32(pixels,y*4)
  for x in range(16): im.putpixel((x,y),[(255,255,255),(130,130,130),(0,0,0),(210,210,210)][(v>>(2*x))&3])
 x=(i%16)*72;y=(i//16)*84;atlas.paste(im.resize((48,48),Image.Resampling.NEAREST),(x+8,y+20));draw.text((x+8,y+3),'%02X w%d'%(i+1,widths[i+2]),fill='black')
 glyphrows.append(dict(code=i+1,code_hex='%02X'%(i+1),table_character=chars[i],width=widths[i+2],glyph_rom_offset=res['menu/font/UseMoji_image.bin']['rom_offset']+off,length=length,top_blank=top,bottom_blank=bottom,upstream_character=cmap.get(i+1)))
atlas.save(D/'font-atlas.png');(D/'font-glyphs.json').write_text(json.dumps(glyphrows,indent=2,ensure_ascii=False));(D/'text-summary.json').write_text(json.dumps(dict(summary=summary,samples=sample),indent=2,ensure_ascii=False))
print(json.dumps(summary,indent=2));print(json.dumps(sample[:15],indent=2,ensure_ascii=False))
