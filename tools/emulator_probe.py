#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent libretro emulator oracle; never used by the recomp runtime.
Read JSON step commands from stdin: {frames, buttons:[ids], touch:[x,y], capture}.
"""
import argparse,ctypes as C,json,os,time,hashlib
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,required=True);p.add_argument('--rom',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
core=C.CDLL(str(a.core.resolve()));frame=0;buttons=set();touch=None;pixels=None;fmt=1;defaults={};keep=[]
class Variable(C.Structure):_fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class Game(C.Structure):_fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
class Info(C.Structure):_fields_=[('name',C.c_char_p),('version',C.c_char_p),('extensions',C.c_char_p),('need_fullpath',C.c_bool),('block_extract',C.c_bool)]
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p);VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t);AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16);BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t);POLL=C.CFUNCTYPE(None);INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
options={k.encode():v.encode() for k,v in {'desmume_cpu_mode':'interpreter','desmume_opengl_mode':'disabled','desmume_firmware_language':'English','desmume_screens_layout':'top/bottom','desmume_internal_resolution':'256x192','desmume_num_cores':'1','desmume_frameskip':'0','desmume_pointer_mouse':'enabled','desmume_pointer_type':'touch','desmume_use_external_bios':'disabled','desmume_use_external_firmware':'disabled'}.items()}
LOG=C.CFUNCTYPE(None,C.c_int,C.c_char_p)
@LOG
def logger(level,message):
 if level>=2:print("CORELOG",message.decode(errors="replace"),flush=True)
@ENV
def env(cmd,data):
 global fmt
 cmd&=~0x10000
 if cmd==27:C.cast(data,C.POINTER(C.c_void_p))[0]=C.cast(logger,C.c_void_p).value;return True
 if cmd==10:fmt=C.cast(data,C.POINTER(C.c_int))[0];return fmt in [0,1,2]
 if cmd in [9,31]:C.cast(data,C.POINTER(C.c_char_p))[0]=os.fsencode(a.output);return True
 if cmd==15:
  v=C.cast(data,C.POINTER(Variable)).contents;v.value=options.get(v.key,defaults.get(v.key));return v.value is not None
 if cmd==16:
  arr=C.cast(data,C.POINTER(Variable));i=0
  while arr[i].key:
   desc=arr[i].value.decode();defaults[arr[i].key]=desc.split('; ',1)[-1].split('|')[0].encode();i+=1
  return True
 if cmd==17:C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
 if cmd in [3,18]:return False
 if cmd in [6,11,65]:C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
 if cmd==39:C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
 return False
@VIDEO
def video(data,w,h,pitch):
 global pixels
 if data and data!=C.c_void_p(-1).value:pixels=(C.string_at(data,h*pitch),w,h,pitch,fmt)
@AUDIO
def audio(l,r):pass
@BATCH
def batch(data,frames):return frames
@POLL
def poll():pass
@INPUT
def input_(port,device,index,id):
 if device==1:return int(id in buttons)
 if device==6 and touch:
  return [int(touch[0]*65534/255-32767),int(touch[1]*65534/191-32767),1][id] if id<3 else 0
 return 0
for name,cb,tp in [('environment',env,ENV),('video_refresh',video,VIDEO),('audio_sample',audio,AUDIO),('audio_sample_batch',batch,BATCH),('input_poll',poll,POLL),('input_state',input_,INPUT)]:
 f=getattr(core,'retro_set_'+name);f.argtypes=[tp];f(cb)
core.retro_init();info=Info();core.retro_get_system_info(C.byref(info));print('CORE',info.name,info.version,flush=True)
rom=a.rom.read_bytes();buffer=C.create_string_buffer(rom);game=Game(os.fsencode(a.rom.resolve()),C.cast(buffer,C.c_void_p),len(rom),None);core.retro_load_game.argtypes=[C.POINTER(Game)];core.retro_load_game.restype=C.c_bool
if not core.retro_load_game(C.byref(game)):raise RuntimeError('Core rejected ROM')
core.retro_serialize_size.restype=C.c_size_t
print('READY',flush=True)
try:
 for line in __import__('sys').stdin:
  try:
   req=json.loads(line);buttons=set(req.get('buttons',[]));touch=req.get('touch');start=time.monotonic()
   if req.get('quit'):break
   if 'load_state' in req:
    d=(a.output/req['load_state']).read_bytes();b=C.create_string_buffer(d);core.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_unserialize.restype=C.c_bool
    if not core.retro_unserialize(b,len(d)):raise RuntimeError('State rejected')
   for _ in range(req.get('frames',0)):core.retro_run();frame+=1
   result=dict(frame=frame,seconds=round(time.monotonic()-start,3))
   if req.get('memory'):
    core.retro_get_memory_data.argtypes=[C.c_uint];core.retro_get_memory_data.restype=C.c_void_p;core.retro_get_memory_size.argtypes=[C.c_uint];core.retro_get_memory_size.restype=C.c_size_t
    mp=core.retro_get_memory_data(2);mn=core.retro_get_memory_size(2);(a.output/req['memory']).write_bytes(C.string_at(mp,mn));result['memory_size']=mn
   if 'save_state' in req:
    n=core.retro_serialize_size();b=C.create_string_buffer(n);core.retro_serialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_serialize.restype=C.c_bool
    if not core.retro_serialize(b,n):raise RuntimeError('State capture failed')
    (a.output/req['save_state']).write_bytes(b.raw)
   if 'capture' in req:
    if pixels is None:raise RuntimeError('No emulator framebuffer')
    d,w,h,pitch,f=pixels
    if f==1:im=Image.frombytes('RGB',(w,h),d,'raw','BGRX',pitch)
    else:
     out=bytearray()
     for y in range(h):
      for x in range(w):
       v=int.from_bytes(d[y*pitch+x*2:y*pitch+x*2+2],'little')
       out+=bytes((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31)) if f==2 else bytes((((v>>10)&31)*255//31,((v>>5)&31)*255//31,(v&31)*255//31))
     im=Image.frombytes('RGB',(w,h),bytes(out))
    dest=a.output/req['capture'];im.save(dest);result.update(capture=str(dest),width=w,height=h)
   print(json.dumps(result),flush=True)
  except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
finally:core.retro_unload_game();core.retro_deinit()
