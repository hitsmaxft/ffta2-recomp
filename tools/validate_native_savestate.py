#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise live native text snapshot restoration and atomic rejection.

Run against a headless native session already displaying Chinese text. All
snapshots and captures stay outside the repository. Restores the starting state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=19979)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output == ROOT or ROOT in output.parents:
        p.error('Evidence must stay outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    with socket.create_connection(('127.0.0.1', a.port), timeout=180) as connection:
        stream = connection.makefile('rwb')
        def ask(**command):
            stream.write((json.dumps(command)+'\n').encode())
            stream.flush()
            return json.loads(stream.readline())
        def checked(**command):
            result = ask(**command)
            if 'error' in result or result.get('terminal'):
                raise RuntimeError(result)
            return result
        def capture(name):
            canvas = Image.new('RGB', (1024, 1536))
            digest = hashlib.sha256()
            for i, engine in enumerate('AB'):
                frame = checked(cmd='framebuffer', engine=engine, native_scale=4)
                pixels = bytes.fromhex(frame['rgb'])
                digest.update(pixels)
                canvas.paste(Image.frombytes('RGB', (frame['w'], frame['h']), pixels), (0, i*768))
            canvas.save(output / (name+'.png'))
            return digest.hexdigest()
        state = output / 'start.nss'
        checked(cmd='state_save', path=str(state))
        before = capture('before')
        try:
            checked(cmd='keys', mask=4094)
            checked(cmd='run_vblanks', count=12)
            checked(cmd='keys', mask=4095)
            checked(cmd='run_vblanks', count=120)
            advanced = capture('advanced')
            checked(cmd='state_load', path=str(state))
            restored = capture('restored')
            assert before == restored, 'Restored presentation differs before executing a frame'
            raw = state.read_bytes()
            # FTXT is an optional, CRC-protected section in the native container.
            count = struct.unpack_from('<I', raw, 12)[0]
            entry = next(24+i*32 for i in range(count)
                         if raw[24+i*32:28+i*32] == b'FTXT')
            offset, size = struct.unpack_from('<QQ', raw, entry+8)
            assert size >= 8
            incompatible = bytearray(raw)
            font = struct.unpack_from('<I', incompatible, offset+4)[0]
            struct.pack_into('<I', incompatible, offset+4, font ^ 1)
            crc = zlib.crc32(incompatible[offset:offset+size])
            struct.pack_into('<I', incompatible, entry+24, crc)
            errors = {}
            for name, data in [('wrong-font', incompatible), ('truncated', raw[:-17])]:
                path = output / (name+'.nss')
                path.write_bytes(data)
                result = ask(cmd='state_load', path=str(path))
                assert 'error' in result, f'{name} was accepted'
                assert capture(name+'-retained') == before, f'{name} changed live presentation'
                errors[name] = result['error']
            report = dict(before_sha256=before, advanced_sha256=advanced,
                          restored_sha256=restored, page_changed=before != advanced,
                          rejection_errors=errors, native_section_bytes=size,
                          text=checked(cmd='localization_render_stats'))
            (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(report, indent=2))
        finally:
            checked(cmd='keys', mask=4095)
            checked(cmd='state_load', path=str(state))


if __name__ == '__main__':
    main()
