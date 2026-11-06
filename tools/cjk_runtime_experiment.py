#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local, bounded D0 glyph-bank experiment; not a complete translation."""
import argparse, csv, hashlib, json, struct, subprocess, tempfile
from pathlib import Path
from build_cn_patch import Archive, SHA, align, bdf_glyphs, crc16, hashname, u16, u32
ROOT = Path(__file__).resolve().parents[1]
NAME = 'menu/font/CJKtest4.bin'
TEXT = ('暑假就要到了，\n我都等不及了。' + '\\endPage\\' + '\\end\\' +
        '老师一讲完，\n我就冲出教室。' + '\\var2:00\\' + '\\end\\')
TOKENS = {'\\endPage\\':b'\xc3\0','\\end\\':b'\xc1\0','\\var2:00\\':b'\xc2\0','\\varA:00\\':b'\xca\0'}
IDS = ['event:0:42:1'] + [f'event:0:103:{i}' for i in (3,4,5,6)]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('rom',type=Path);p.add_argument('--font',type=Path,required=True);p.add_argument('--bank',type=Path,required=True);p.add_argument('--bank-index',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fallback-only',action='store_true');p.add_argument('--vanilla-text',action='store_true');p.add_argument('--no-hook',action='store_true');p.add_argument('--probe-control',type=lambda x:int(x,16));a=p.parse_args()
 dest=a.output.resolve()
 for root in (a.rom.resolve().parent,ROOT):
  if dest==root or root in dest.parents:p.error('Output must be outside ROM directory and checkout')
 raw=a.rom.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Wrong ROM')
 with tempfile.TemporaryDirectory(prefix='cjk-arm-') as td:
  obj=Path(td)/'stub.o';binfile=Path(td)/'stub.bin'; trampoline=Path(td)/'trampoline.s';trampobj=Path(td)/'tramp.o';trampbin=Path(td)/'tramp.bin'
  subprocess.run(['arm-none-eabi-as','-mcpu=arm946e-s','-o',str(obj),str(ROOT/'tools/cjk_runtime_stub.s')],check=True)
  subprocess.run(['arm-none-eabi-objcopy','-O','binary','-j','.text',str(obj),str(binfile)],check=True);stub=binfile.read_bytes()
  trampoline.write_text('.syntax unified\n.arm\nldr ip, [pc, #4]\nldr ip, [ip, #0x1c]\nadd pc, ip, #0x2000\n.word 0x0212e4b0\n')
  subprocess.run(['arm-none-eabi-as','-mcpu=arm946e-s','-o',str(trampobj),str(trampoline)],check=True)
  subprocess.run(['arm-none-eabi-objcopy','-O','binary','-j','.text',str(trampobj),str(trampbin)],check=True);tramp=trampbin.read_bytes()
 if len(tramp)!=16:raise ValueError('Trampoline length')
 if a.fallback_only:
  # The 0xd8 fallback label is guarded against the current assembled stub.
  if stub[0xd8:0xdc] != bytes.fromhex('f8432de9'):raise ValueError('Fallback label changed')
  stub=bytes.fromhex('08c04fe220e18ce5320000ea')+stub[12:]+bytes(4)
 with (ROOT/'data/text/machine-cn.csv').open(encoding='utf-8-sig',newline='') as f:
  rows={r['id']:r for r in csv.DictReader(f) if r['id'] in IDS}
 if set(rows)!=set(IDS) or any(r['status']!='translated' for r in rows.values()) or rows[IDS[0]]['translation']!=TEXT:raise ValueError('Expected test translations missing')
 stripped='\n'.join(rows[k]['translation'] for k in IDS)
 for t in TOKENS:stripped=stripped.replace(t,'')
 chars=json.loads(a.bank_index.read_text())['glyphs'];bank=a.bank.read_bytes()
 if len(chars)!=2613 or len(set(chars))!=2613 or len(bank)!=2613*64:raise ValueError('Unexpected full glyph bank')
 if any(c not in chars for c in stripped if ord(c)>127):raise ValueError('Missing text glyph')
 arc=Archive(raw);image,ie=arc.read('menu/font/UseMoji_image.bin');width,we=arc.read('menu/font/FontWidthTable.bin');table,te=arc.read('menu/font/UseMoji_table.bin')
 n=u16(image)
 if n!=168 or u16(width)!=n:raise ValueError('Unexpected font')
 oldbody=u32(image,2);bodyend=u32(image,2+4*(n-1))+image[u32(image,2+4*(n-1))];nn=n+23;headsize=2+4*nn;delta=headsize-oldbody
 offsets=[u32(image,2+4*i)+delta for i in range(n)];newbody=bytearray(image[oldbody:bodyend])
 for i in range(23):
  offsets.append(headsize+len(newbody));newbody.extend(bytes([4,255])+struct.pack('<H',n+i))
 img=struct.pack('<H',nn)+b''.join(struct.pack('<I',o) for o in offsets)+bytes(newbody)
 if len(img)>0x2000:raise ValueError('No room for stub')
 img+=bytes(0x2000-len(img))+stub
 table=table.rstrip(b'\0')+(''.join(chars[:23])).encode()+b'\0'
 width=struct.pack('<H',nn)+width[2:2+n]+bytes([12]*23)
 arena=sum(align(len(x)) for x in (img,table,width))+2*160
 if arena>0x2800:raise ValueError(f'Font arena needs {arena:#x}')
 target=bytearray(raw);cursor=align(u32(raw,0x80),32);resources={}
 def append(name,data,entry=None):
  nonlocal cursor
  data=bytes(data)+bytes(align(len(data))-len(data));end=cursor+len(data)
  if end>len(raw) or raw[cursor:end]!=b'\xff'*len(data):raise ValueError('ROM tail not blank')
  target[cursor:end]=data;e=entry or arc.entry(name);arc.redirect(e,cursor,len(data));resources[name]={'offset':cursor,'size':len(data)};cursor=align(end,32)
 append('menu/font/UseMoji_image.bin',img);append('menu/font/UseMoji_table.bin',table);append('menu/font/FontWidthTable.bin',width)
 h=hashname(NAME);pos=8+9*h
 if struct.unpack_from('<II',arc.idx,pos)!=(0,0):raise ValueError('Experimental hash bucket occupied')
 append(NAME,bank,{'main':pos,'offset_pos':None})
 mapping={c:i for i,c in enumerate(chars)}
 def controls(d):
  z=[];j=0
  while j<len(d):
   if d[j]>=0xc0:
    if d[j] not in (0xc0,0xd0):z.append(d[j:j+2])
    j+=2
   else:j+=1
  return z
 idx,_=arc.read('event/rom/ev_msg0_rom.idx');pak,pe=arc.read('event/rom/ev_msg0.pak');translations=[]
 for key in IDS:
  row=rows[key];text=row['translation'];out=bytearray();i=0
  while i<len(text):
   if text[i]=='\\':
    tok=next((t for t in TOKENS if text.startswith(t,i)),None)
    if not tok:raise ValueError('unknown control in '+key)
    out.extend(TOKENS[tok]);i+=len(tok)
   elif text[i]=='\n':out.extend(b'\xc0\0');i+=1
   else:
    n=mapping[text[i]];out.extend((0xd0,n//23+1,0xa9+n%23));i+=1
  _,_,block,sid=key.split(':');bo=((u32(idx,4+6*int(block))&0x7ffffff)>>3)*4;entry=bo+2+10*int(sid);le=u32(pak,entry);so=u32(pak,entry+4);old=pak[bo+so:bo+so+le]
  if hashlib.sha256(old).hexdigest()!=row['source_sha256'] or le!=int(row['byte_length']):raise ValueError('Catalog source bytes mismatch: '+key)
  if a.probe_control is not None and key==IDS[0]:
   if not 0xc0<=a.probe_control<=0xff:raise ValueError('Invalid control')
   out=bytes((a.probe_control,0))+old[2:]
  if len(out)>le or (a.probe_control is None and controls(out)!=controls(old)):raise ValueError(f'text overflow or controls changed {key} {len(out)}/{le}')
  clean=text
  for tok in TOKENS:clean=clean.replace(tok,'')
  if any(len(line)*3+4 > 0x3d for line in clean.splitlines()):raise ValueError('Encoded line exceeds bounded layout scratch buffer: '+key)
  if not a.vanilla_text:
   struct.pack_into('<I',target,pe['offset']+entry,len(out));target[pe['offset']+bo+so:pe['offset']+bo+so+le]=out+bytes(le-len(out))
  translations.append({'id':key,'text':text,'source_sha256':row['source_sha256'],'text_bytes':len(out),'original_bytes':le,'original_control_sequence_preserved':controls(out)==controls(old)})
 off=u32(raw,0x20)+0x20845f0-u32(raw,0x28)
 if raw[off:off+16]!=bytes.fromhex('f8432de90160a0e10250a0e10340a0e1'):raise ValueError('Glyph entry guard failed')
 if not a.no_hook:target[off:off+16]=tramp
 if not a.no_hook and not a.fallback_only:
  for site,expected in ((0x0204c2dc,0xea000076),(0x0204d82c,0xea0000d5),(0x0204dd18,0xebfff3ac)):
   off=u32(raw,0x20)+site-u32(raw,0x28)
   if u32(raw,off)!=expected:raise ValueError('Control copy hook guard failed')
   displacement=(0x020845f0-site-8)//4
   struct.pack_into('<I',target,off,0xeb000000|(displacement&0xffffff))
 for address in (0x208426c,0x2084418,0x2084428):
  off=u32(raw,0x20)+address-u32(raw,0x28);w=u32(raw,off)
  if w&0xfff!=0xb09:raise ValueError('Arena guard failed')
  struct.pack_into('<I',target,off,(w&~0xfff)|0xb0a)
 target[arc.idxbase:arc.idxbase+len(arc.idx)]=arc.idx;struct.pack_into('<I',target,arc.bin_fat+4,cursor);struct.pack_into('<I',target,0x80,cursor);struct.pack_into('<H',target,0x15e,crc16(target[:0x15e]))
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(target)
 edits=[]
 for addr,length,role in ((0x020845f0,16,'font trampoline'),(0x0204c2dc,4,'per-glyph bank metadata'),(0x0204d82c,4,'preserve D0 in dialogue line'),(0x0204dd18,4,'diagnostic line-copy trace'),(0x0208426c,4,'font arena'),(0x02084418,4,'font arena'),(0x02084428,4,'font arena')):
  off=u32(raw,0x20)+addr-u32(raw,0x28);edits.append({'address':hex(addr),'role':role,'old_hex':raw[off:off+length].hex(),'new_hex':target[off:off+length].hex()})
 receipt={'warning':'Experimental ARM9 hook, one rendering caller only; no game-wide safety validation','source_sha256':SHA,'target_sha256':hashlib.sha256(target).hexdigest(),'font_bank_sha256':hashlib.sha256(bank).hexdigest(),'arena_need':arena,'arena_capacity':0x2800,'stub_size':len(stub),'glyph_count':len(chars),'translations':translations,'arm9_edits':edits,'resources':resources}
 dest.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
