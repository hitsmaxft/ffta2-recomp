#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay ordinary button input and capture native UI regression evidence.

Scenario JSON is a list of {"button":"A", "hold":12, "settle":60,
"capture":"items"}. Button is optional; captures and the result log remain
outside the checkout. A successful replay proves execution, not visual correctness.
"""
import argparse
import json
from pathlib import Path
import socket
from PIL import Image

BUTTONS = {name: 1 << bit for bit, name in enumerate(
    ('A', 'B', 'Select', 'Start', 'Right', 'Left', 'Up', 'Down', 'R', 'L', 'X', 'Y'))}
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=19979)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scale', type=int, choices=range(1, 9), default=4)
    a = p.parse_args()
    output = a.output.resolve()
    if output == ROOT or ROOT in output.parents:
        p.error('Keep gameplay evidence outside the source repository')
    steps = json.loads(a.scenario.read_text())
    if not isinstance(steps, list) or len(steps) > 1000:
        p.error('Expected at most 1000 replay steps')
    for step in steps:
        if not isinstance(step, dict) or set(step) - {'button', 'hold', 'settle', 'capture'}:
            p.error('Invalid replay step')
        if 'button' in step and step['button'] not in BUTTONS:
            p.error('Unknown button')
        for key, default in [('hold', 12), ('settle', 60)]:
            value = step.get(key, default)
            if type(value) is not int or not 0 <= value <= 3600:
                p.error('Frame counts must be integers in 0..3600')
        name = step.get('capture')
        if name is not None and (not isinstance(name, str) or not name or
                                 any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in name)):
            p.error('Capture labels must use lowercase ASCII, digits, hyphens or underscores')
    output.mkdir(parents=True, exist_ok=True)
    report = []
    with socket.create_connection(('127.0.0.1', a.port), timeout=180) as connection:
        stream = connection.makefile('rwb')
        def ask(**command):
            stream.write((json.dumps(command) + '\n').encode())
            stream.flush()
            response = json.loads(stream.readline())
            if 'error' in response or response.get('terminal'):
                raise RuntimeError(response)
            return response
        try:
            for i, step in enumerate(steps):
                if 'button' in step:
                    ask(cmd='keys', mask=4095 ^ BUTTONS[step['button']])
                    ask(cmd='run_vblanks', count=step.get('hold', 12))
                ask(cmd='keys', mask=4095)
                result = ask(cmd='run_vblanks', count=step.get('settle', 60))
                record = {'step': i, 'input': step, 'execution': result,
                          'text': ask(cmd='localization_render_stats')}
                if 'capture' in step:
                    image = Image.new('RGB', (256*a.scale, 384*a.scale))
                    for n, engine in enumerate('AB'):
                        frame = ask(cmd='framebuffer', engine=engine, native_scale=a.scale)
                        image.paste(Image.frombytes('RGB', (frame['w'], frame['h']),
                                                   bytes.fromhex(frame['rgb'])), (0, 192*a.scale*n))
                    image.save(output / (step['capture'] + '.png'))
                report.append(record)
                (output / 'replay.json').write_text(json.dumps(report, indent=2) + '\n')
                print(f'Step {i}: {step}; {record["text"]}', flush=True)
        finally:
            ask(cmd='keys', mask=4095)


if __name__ == '__main__':
    main()
