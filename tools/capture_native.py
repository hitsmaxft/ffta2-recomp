#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture both screens from the native backend's real presentation layers."""
import argparse
import json
from pathlib import Path
import socket
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=19979)
    parser.add_argument('--scale', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error('Keep gameplay captures outside the source repository')
    images = []
    with socket.create_connection(('127.0.0.1', args.port), timeout=60) as connection:
        stream = connection.makefile('rwb')
        for screen in ('A', 'B'):
            command = dict(cmd='framebuffer', engine=screen, native_scale=args.scale)
            stream.write((json.dumps(command) + '\n').encode())
            stream.flush()
            response = json.loads(stream.readline())
            if 'error' in response:
                raise RuntimeError(response['error'])
            size = response['w'], response['h']
            images.append(Image.frombytes('RGB', size, bytes.fromhex(response['rgb'])))
    result = Image.new('RGB', (max(im.width for im in images), sum(im.height for im in images)))
    y = 0
    for im in images:
        result.paste(im, ((result.width-im.width)//2, y))
        y += im.height
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    print(f'Native framebuffer capture: {result.width}x{result.height}: {output}')


if __name__ == '__main__':
    main()
