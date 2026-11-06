# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import struct,json,hashlib,re
import ndspy.rom, ndspy.codeCompression
R=Path(os.environ['FFTA2_ANALYSIS_DIR']); p=next((R/'rom').glob('*.nds')); raw=p.read_bytes(); assert hashlib.sha256(raw).hexdigest() == 'f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59', 'Unsupported ROM revision'
rom=ndspy.rom.NintendoDSRom(raw)
u16=lambda b,o=0:struct.unpack_from('<H',b,o)[0]
u32=lambda b,o=0:struct.unpack_from('<I',b,o)[0]
out=R/'extracted'; out.mkdir(exist_ok=True)
files={}
def walk(folder,prefix=''):
 for i,n in enumerate(folder.files):
  fid=folder.firstID+i; start,end=struct.unpack_from('<II',raw,u32(raw,0x48)+fid*8)
  name=prefix+n; files[name]={'id':fid,'rom_offset':start,'size':end-start}
  dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw[start:end])
 for n,f in folder.folders:walk(f,prefix+n+'/')
walk(rom.filenames)
arm9=ndspy.codeCompression.decompress(rom.arm9);(out/'arm9.decompressed.bin').write_bytes(arm9)
strings=[]
for m in re.finditer(rb'[\x20-\x7e]{5,}',arm9):
 s=m.group().decode()
 if any(k in s.lower() for k in ['font','message','questtext','uwasa','freepaper','ev_msg','pc.idx','pc.bin','.fnt','.nftr']):strings.append({'offset':m.start(),'ram_address':rom.arm9RamAddress+m.start(),'text':s})
meta={'title':raw[:12].decode('ascii').rstrip('\0'),'gamecode':raw[12:16].decode(),'revision':raw[0x1e],'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'sha1':hashlib.sha1(raw).hexdigest(),'arm9_rom_offset':u32(raw,0x20),'arm9_ram_address':rom.arm9RamAddress,'arm9_size_compressed':len(rom.arm9),'arm9_size_decompressed':len(arm9),'files':files,'resource_strings':strings}
(R/'rom_inventory.json').write_text(json.dumps(meta,indent=2))
print(json.dumps({k:v for k,v in meta.items() if k not in ['files','resource_strings']},indent=2));print('Files',files);print('Strings',strings)
