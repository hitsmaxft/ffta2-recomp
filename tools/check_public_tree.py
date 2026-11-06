#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit the staged Git tree, including blobs rather than working copies."""
import json
from pathlib import PurePosixPath
import re
import subprocess

ALLOWED_SUFFIXES={'.py','.json','.jsonl','.csv','.md','.txt','.yml','.yaml','.cpp','.h'}
ALLOWED_NAMES={'.gitignore','.gitmodules','.gitattributes','LICENSE'}
ALLOWED_SUBMODULES={'third_party/ndsrecomp','third_party/recomp-ui'}
HANDWRITTEN_ASSEMBLY={'tools/cjk_runtime_stub.s'}

def git(*args):
    return subprocess.check_output(['git',*args])

def main():
    errors=[]
    size=0
    files=0
    for record in git('ls-files','--stage','-z').split(b'\0'):
        if not record:
            continue
        metadata,name=record.split(b'\t',1)
        mode,oid,stage=metadata.decode().split()
        name=name.decode()
        path=PurePosixPath(name)
        if stage!='0':
            errors.append(name+': unresolved stage')
        if mode=='160000':
            if name not in ALLOWED_SUBMODULES:
                errors.append(name+': unexpected submodule')
            continue
        if mode not in {'100644','100755'}:
            errors.append(name+': unsupported mode')
        if path.suffix not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES and name not in HANDWRITTEN_ASSEMBLY:
            errors.append(name+': file type not allowlisted')
        if path.name=='AGENTS.local.md' or any(part in {'build','generated','.venv','__pycache__'} for part in path.parts):
            errors.append(name+': private/build path')
        data=git('cat-file','blob',oid)
        size+=len(data)
        files+=1
        if len(data)>40*1024*1024:
            errors.append(name+': unexpectedly large blob')
        try:
            text=data.decode('utf-8-sig')
        except UnicodeDecodeError:
            errors.append(name+': non-UTF8 binary')
            continue
        if '\0' in text:
            errors.append(name+': binary NUL')
        if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)',text):
            errors.append(name+': possible credential')
        if path.suffix=='.csv':
            header=text.splitlines()[0] if text else ''
            if any(field in header.lower() for field in ('raw_hex','base64','payload_bytes')):
                errors.append(name+': raw payload column')
    print(json.dumps(dict(files=files,utf8_blob_bytes=size,errors=errors),indent=2))
    raise SystemExit(bool(errors))

if __name__=='__main__':main()
