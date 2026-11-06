#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a source-copy BPS opening-scene patch. Never distribute an input ROM."""
import argparse,hashlib,json,struct,sys,re
from pathlib import Path
import ndspy.rom
from bps import build,apply
SHA='f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
ROOT=Path(__file__).resolve().parents[1]
def u16(b,o=0):return struct.unpack_from('<H',b,o)[0]
def u32(b,o=0):return struct.unpack_from('<I',b,o)[0]
def align(n,a=4):return (n+a-1)&-a
def hashname(s):
 v=0
 for c in s.encode():v=(v*37+c)&0xffffffff
 return v&1023

def crc16(data):
 crc=0xffff
 for b in data:
  crc^=b
  for _ in range(8):crc=(crc>>1)^ (0xa001 if crc&1 else 0)
 return crc

class Archive:
 def __init__(self,raw):
  rom=ndspy.rom.NintendoDSRom(raw);fat=u32(raw,0x48)
  def where(name):
   fid=rom.filenames.idOf(name)
   if fid is None:raise ValueError('Missing '+name)
   return fat+8*fid,u32(raw,fat+8*fid),u32(raw,fat+8*fid+4)
  self.bin_fat,self.base,self.end=where('master/pc.bin');_,self.idxbase,ie=where('master/pc.idx');self.idx=bytearray(raw[self.idxbase:ie]);self.raw=raw
 def entry(self,name):
  h=hashname(name);p=8+9*h;a,b=struct.unpack_from('<II',self.idx,p);size=((a>>26)+(b&65535)*64)*4
  if a&1:
   q=((a&0x3ffffff)*2)//4;n=self.idx[q];q+=1
   for i in range(n):
    op=q;off=u32(self.idx,q)*4;q+=4;sp=None;sz=size
    if i:sp=q;sz=u32(self.idx,q)*4;q+=8
    c,cp=self.idx[q:q+2];q+=3
    if cp<len(name) and ord(name[cp])==c:return dict(name=name,offset=self.base+off,size=sz,main=p,offset_pos=op,size_pos=sp)
   raise ValueError('Archive collision miss '+name)
  return dict(name=name,offset=self.base+(a&0x3ffffff)*2,size=size,main=p,offset_pos=None,size_pos=None)
 def redirect(self,e,offset,size):
  if offset%4 or size%4:raise ValueError('Unaligned archive payload')
  p=e['main'];a,b=struct.unpack_from('<II',self.idx,p);rel=offset-self.base
  if e['offset_pos'] is not None:
   struct.pack_into('<I',self.idx,e['offset_pos'],rel//4)
   if e['size_pos'] is not None:struct.pack_into('<I',self.idx,e['size_pos'],size//4);return
  else:a=(rel//2)&0x3ffffff
  a=(a&0x3ffffff)|((size//4&63)<<26);b=(b&0xffff0000)|(size//256)
  struct.pack_into('<II',self.idx,p,a,b)
 def read(self,name):
  e=self.entry(name);return self.raw[e['offset']:e['offset']+e['size']],e

def bdf_glyphs(path,wanted):
 found={}
 for block in path.read_text().split('STARTCHAR ')[1:]:
  lines=block.splitlines();enc=next((x for x in lines if x.startswith('ENCODING ')),None)
  if not enc:continue
  code=int(enc.split()[1])
  if chr(code) not in wanted:continue
  w,h,dx,dy=map(int,next(x for x in lines if x.startswith('BBX ')).split()[1:]);bi=lines.index('BITMAP');rows=lines[bi+1:bi+1+h];pix=[[0]*16 for _ in range(16)]
  # Font ascent 10, descent 2; center the 12-pixel cell in the 16-pixel cell.
  top=2+10-dy-h
  for y,row in enumerate(rows):
   bits=int(row,16);total=len(row)*4
   for x in range(w):
    xx=1+dx+x;yy=top+y
    if 0<=xx<16 and 0<=yy<16 and bits&(1<<(total-1-x)):pix[yy][xx]=3
  data=b''.join(struct.pack('<I',sum(v<<(x*2) for x,v in enumerate(row))) for row in pix)
  found[chr(code)]=data
 if set(found)!=set(wanted):raise ValueError('Missing font glyphs: '+repr(set(wanted)-set(found)))
 return found

def main():
 p=argparse.ArgumentParser();p.add_argument('rom',type=Path);p.add_argument('--font',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--config',type=Path,default=ROOT/'config/prologue-zh-hans.json');p.add_argument('--test-rom',type=Path);p.add_argument('--translations-csv',type=Path);p.add_argument('--catalog',type=Path);a=p.parse_args()
 if a.output.suffix.lower()!='.bps':p.error('Output must be .bps')
 if a.test_rom and a.test_rom.resolve()==a.rom.resolve():p.error('Test ROM must differ from the original ROM')
 for dest in [a.output,a.test_rom]:
  if dest and (dest.resolve()==ROOT or ROOT in dest.resolve().parents):p.error('Private outputs must stay outside the checkout')
 raw=a.rom.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Unsupported ROM identity')
 cfg=json.loads(a.config.read_text())
 if a.translations_csv:
  if not a.catalog:p.error('--translations-csv requires --catalog')
  from text_catalog import import_csv
  imported=import_csv(a.translations_csv,a.catalog);cfg['strings']=imported['strings'];cfg['records']=imported['records']
 expected_sources={r['id']:r['source_sha256'] for r in cfg.get('records',[])}
 text=cfg['strings']['event:0:42:1'];chars=sorted(set(c for value in cfg['strings'].values() for c in value if ord(c)>127))
 if len(chars)>23:raise ValueError('Prototype supports at most 23 additional glyphs')
 newcodes={c:0xa9+i for i,c in enumerate(chars)};fontdata=bdf_glyphs(a.font,set(chars));arc=Archive(raw);changes=[];report={};cursor=align(u32(raw,0x80),32)
 def change(pos,segments):
  size=sum(s[2] if s[0]=='source' else len(s[1]) for s in segments);changes.append((pos,size,segments))
 def literal(pos,data):change(pos,[('literal',data)])
 def append(name,segments):
  nonlocal cursor
  e=arc.entry(name);size=sum(s[2] if s[0]=='source' else len(s[1]) for s in segments);pad=align(size)-size
  if pad:segments=segments+[('literal',bytes(pad))]
  size+=pad
  if cursor+size>len(raw) or any(x!=255 for x in raw[cursor:cursor+size]):raise ValueError('No verified blank ROM space')
  change(cursor,segments);arc.redirect(e,cursor,size);report[name]=dict(old_rom_offset=e['offset'],new_rom_offset=cursor,size=size);cursor=align(cursor+size,32)
 # Keep the original 168 glyph records verbatim via SourceCopy actions.
 image,ie=arc.read('menu/font/UseMoji_image.bin');n=u16(image);assert n==168
 oldbody=u32(image,2);bodyend=u32(image,2+4*(n-1))+image[u32(image,2+4*(n-1))];nn=n+len(chars);headsize=2+4*nn;delta=headsize-oldbody
 offsets=[u32(image,2+4*i)+delta for i in range(n)];newbody=bytearray()
 for c in chars:
  offsets.append(headsize+(bodyend-oldbody)+len(newbody))
  pixels=fontdata[c];top=0;bottom=0
  while top<15 and pixels[top*4:(top+1)*4]==bytes(4):top+=1
  while bottom<15-top and pixels[(15-bottom)*4:(16-bottom)*4]==bytes(4):bottom+=1
  payload=pixels[top*4:(16-bottom)*4]
  newbody+=bytes([4+len(payload),(top<<4)|bottom])+struct.pack('<H',newcodes[c]-1)+payload
 head=struct.pack('<H',nn)+b''.join(struct.pack('<I',o) for o in offsets)
 append('menu/font/UseMoji_image.bin',[('literal',head),('source',ie['offset']+oldbody,bodyend-oldbody),('literal',bytes(newbody))])
 table,te=arc.read('menu/font/UseMoji_table.bin');ts=len(table.rstrip(b'\0'));append('menu/font/UseMoji_table.bin',[('source',te['offset'],ts),('literal',''.join(chars).encode()+b'\0')])
 width,we=arc.read('menu/font/FontWidthTable.bin');append('menu/font/FontWidthTable.bin',[('literal',struct.pack('<H',nn)),('source',we['offset']+2,n),('literal',bytes([12]*len(chars)))])
 def controls(d):
  result=[];j=0
  while j<len(d):
   if d[j]&0xc0==0xc0:
    if d[j]!=0xc0:result.append(d[j:j+2])
    j+=2
   else:j+=1
  return result
 translations=[]
 for key,text in cfg['strings'].items():
  family,language,block,sid=key.split(':');language=int(language);block=int(block);sid=int(sid)
  if family!='event' or language!=0:raise ValueError('Only event language 0 is supported in this prototype')
  idx,_=arc.read(f'event/rom/ev_msg{language}_rom.idx');pak,pe=arc.read(f'event/rom/ev_msg{language}.pak')
  bo=((u32(idx,4+6*block)&0x7ffffff)>>3)*4
  if sid>=u16(pak,bo):raise ValueError('String index out of bounds')
  entry=bo+2+10*sid;le=u32(pak,entry);so=u32(pak,entry+4);old=pak[bo+so:bo+so+le]
  if key in expected_sources and hashlib.sha256(old).hexdigest()!=expected_sources[key]:raise ValueError('CSV source bytes differ from actual ROM: '+key)
  cmap={int(e['code_hex'],16):e['display'] for e in json.loads((ROOT/'config/western-charset.json').read_text())['entries']};enc={v:k for k,v in cmap.items() if k<0xc0 and len(v)==1};out=bytearray();i=0
  commands={'\\endPage\\':b'\xc3\0','\\end\\':b'\xc1\0','\\var2:00\\':b'\xc2\0','\\varA:00\\':b'\xca\0'}
  while i<len(text):
   if text[i]=='\\':
    match=next((k for k in commands if text.startswith(k,i)),None)
    if not match:raise ValueError('Unknown control token at '+repr(text[i:]))
    out+=commands[match];i+=len(match)
   else:
    c=text[i];i+=1
    if c=='\n':out+=b'\xc0\0'
    else:out.append(newcodes[c] if c in newcodes else enc[c])
  if controls(old)!=controls(out):raise ValueError('Script controls changed: '+key)
  if len(out)>le:raise ValueError('Translated message exceeds original allocation: '+key)
  literal(pe['offset']+entry,struct.pack('<I',len(out)));literal(pe['offset']+bo+so,bytes(out)+bytes(le-len(out)))
  translations.append(dict(id=key,text=text,rom_offset=pe['offset']+bo+so,byte_length=len(out),original_byte_length=le))
 font_need=sum(report['menu/font/'+name+'.bin']['size'] for name in ['UseMoji_table','UseMoji_image','FontWidthTable'])+2*160
 if font_need>0x2800:raise ValueError('Expanded font resources exceed verified arena size')
 # The fixed font arena must contain the expanded resources.
 codepatch=[]
 for address in [0x208426c,0x2084418,0x2084428]:
  off=u32(raw,0x20)+address-u32(raw,0x28);word=u32(raw,off)
  imm=word&255;rot=((word>>8)&15)*2;value=((imm>>rot)|(imm<<(32-rot)))&0xffffffff if rot else imm
  if value!=0x2400:raise ValueError('Font arena instruction guard failed')
  nw=(word&~0xfff)|0xb0a # ARM immediate 0x2800 = ROR(10,22); guarded resource need is computed above
  literal(off,struct.pack('<I',nw));codepatch.append(dict(address=address,old=word,new=nw))
 oldidx=raw[arc.idxbase:arc.idxbase+len(arc.idx)];j=0
 while j<len(arc.idx):
  if arc.idx[j]==oldidx[j]:j+=1;continue
  start=j
  while j<len(arc.idx) and arc.idx[j]!=oldidx[j]:j+=1
  literal(arc.idxbase+start,bytes(arc.idx[start:j]))
 literal(arc.bin_fat+4,struct.pack('<I',cursor));literal(0x80,struct.pack('<I',cursor))
 # Update header CRC after used-ROM-size change.
 header=bytearray(raw[:0x15e]);struct.pack_into('<I',header,0x80,cursor);literal(0x15e,struct.pack('<H',crc16(header)))
 changes.sort();segments=[];pos=0
 for off,size,segs in changes:
  if off<pos:raise ValueError('Overlapping edits')
  if off>pos:segments.append(('source',pos,off-pos))
  segments+=segs;pos=off+size
 if pos<len(raw):segments.append(('source',pos,len(raw)-pos))
 patch,target=build(raw,segments,b'FFTA2 EU Rev0 - opening CN font/text prototype')
 if apply(raw,patch)!=target:raise ValueError('Independent BPS apply mismatch')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(patch)
 if a.test_rom:a.test_rom.write_bytes(target)
 report.update(schema_version=1,source_sha256=SHA,target_sha256=hashlib.sha256(target).hexdigest(),patch_sha256=hashlib.sha256(patch).hexdigest(),patch_size=len(patch),font_sha256=hashlib.sha256(a.font.read_bytes()).hexdigest(),characters=newcodes,translated_text=translations[0]['text'],translated_string_rom_offset=translations[0]['rom_offset'],translated_byte_length=translations[0]['byte_length'],original_byte_length=translations[0]['original_byte_length'],translations=translations,font_resource_need=font_need,blank_end=cursor,font_arena_size=0x2800,arm9_edits=codepatch,language=0,scope=cfg['scope'])
 a.output.with_suffix('.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
