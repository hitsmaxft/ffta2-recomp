#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record/replay frame-counted DS input from a validated native checkpoint.

Headless serve mode only. No wall-clock sleeps or screenshots are needed for
replay. All state files, recordings and failure evidence remain external.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BUTTONS = {name: 1 << i for i, name in enumerate(
    ('A', 'B', 'Select', 'Start', 'Right', 'Left', 'Up', 'Down', 'R', 'L', 'X', 'Y'))}


def validate_step(step):
    if not isinstance(step, dict) or set(step) - {'buttons', 'frames', 'touch', 'label'}:
        raise ValueError('Step fields: buttons, frames, touch, label')
    frames = step.get('frames')
    if type(frames) is not int or not 1 <= frames <= 6000:
        raise ValueError('frames must be an integer in 1..6000')
    buttons = step.get('buttons', [])
    if (not isinstance(buttons, list) or any(not isinstance(b, str) or b not in BUTTONS for b in buttons)
            or len(set(buttons)) != len(buttons)):
        raise ValueError('buttons must be a unique list of DS button names')
    touch = step.get('touch')
    if touch is not None:
        if (not isinstance(touch, dict) or set(touch) != {'x', 'y', 'down'} or
                type(touch['down']) is not bool or type(touch['x']) is not int or
                type(touch['y']) is not int or not 0 <= touch['x'] <= 255 or
                not 0 <= touch['y'] <= 191):
            raise ValueError('touch requires x=0..255, y=0..191, down=boolean')
    label = step.get('label', '')
    if not isinstance(label, str) or len(label) > 128:
        raise ValueError('label must be a string of at most 128 characters')
    return dict(buttons=buttons, frames=frames, touch=touch, label=label)


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 1000:
        raise ValueError('Expected 1..1000 input steps')
    result = [validate_step(step) for step in steps]
    if sum(step['frames'] for step in result) > 36000:
        raise ValueError('A scenario is limited to 36000 VBlanks')
    return result


class Client:
    def __init__(self, port):
        self.connection = socket.create_connection(('127.0.0.1', port), timeout=180)
        self.stream = self.connection.makefile('rwb')

    def close(self):
        self.stream.close()
        self.connection.close()

    def ask(self, cmd, **fields):
        self.stream.write((json.dumps(dict(cmd=cmd, **fields)) + '\n').encode())
        self.stream.flush()
        line = self.stream.readline()
        if not line:
            raise RuntimeError('Native server disconnected')
        result = json.loads(line)
        if 'error' in result or result.get('terminal'):
            raise RuntimeError(result)
        return result

    def observe(self, scale, failure_dir=None):
        state = self.ask('sched_state')
        if state['terminal9'] or state['terminal7']:
            raise RuntimeError('CPU halted: ' + json.dumps(state))
        hashes = []
        for engine in 'AB':
            frame = self.ask('framebuffer', engine=engine, native_scale=scale)
            pixels = bytes.fromhex(frame['rgb'])
            if len(pixels) != frame['w'] * frame['h'] * 3:
                raise RuntimeError('Framebuffer size differs from declared dimensions')
            hashes.append(hashlib.sha256(pixels).hexdigest())
            if failure_dir:
                # Portable lossless PPM; no image-library dependency for testing.
                (failure_dir / f'failure-{engine}.ppm').write_bytes(
                    f"P6\n{frame['w']} {frame['h']}\n255\n".encode() + pixels)
        return dict(screens=hashes, cycles=[state['sys'], state['arm9'], state['arm7']])

    def step(self, step):
        self.ask('keys', mask=4095 ^ sum(BUTTONS[b] for b in step['buttons']))
        self.ask('touch', **(step['touch'] or dict(x=0, y=0, down=False)))
        result = self.ask('run_vblanks', count=step['frames'])
        if result.get('vblanks') != step['frames']:
            raise RuntimeError('Runtime did not execute the exact requested VBlank count')


def external(path):
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Keep recordings, snapshots and evidence outside the repository')
    return path


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('record', 'replay'))
    parser.add_argument('--port', type=int, default=19979)
    parser.add_argument('--output', type=Path, required=True, help='New external evidence directory')
    parser.add_argument('--scenario', type=Path, help='Input JSON steps for record mode')
    parser.add_argument('--console', action='store_true', help='Record JSON input steps typed one per line; EOF ends')
    parser.add_argument('--start', type=Path, help='Exact-build .nss scene to load before recording')
    parser.add_argument('--recording', type=Path, help='recording.json for replay mode')
    parser.add_argument('--repeat', type=int, default=1, help='Replay count, 1..20; RAM restore between passes')
    parser.add_argument('--scale', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--slot', type=int, choices=range(4), default=3)
    args = parser.parse_args()
    client = None
    owned = False
    created_output = False
    report = dict(success=False, passes=[])
    try:
        output = external(args.output)
        if not 1 <= args.repeat <= 20:
            raise ValueError('--repeat must be 1..20')
        if args.mode == 'record':
            if bool(args.scenario) == args.console or args.recording or args.repeat != 1:
                raise ValueError('record needs exactly one of --scenario or --console')
            steps = validate_steps(json.loads(args.scenario.read_text(encoding='utf-8'))) if args.scenario else None
        else:
            if not args.recording or args.scenario or args.console or args.start:
                raise ValueError('replay requires --recording and no input scenario/start')
            source = external(args.recording)
            recording = json.loads(source.read_text(encoding='utf-8'))
            if recording.get('schema') != 1:
                raise ValueError('Unsupported recording schema')
            steps = validate_steps(recording['steps'])
            if len(recording['expected']) != len(steps):
                raise ValueError('Expected observations must match input steps')
            state = source.parent / 'start.nss'
            if hashlib.sha256(state.read_bytes()).hexdigest() != recording['state_sha256']:
                raise ValueError('Starting snapshot hash differs')
            args.scale = recording['scale']
            if type(args.scale) is not int or not 1 <= args.scale <= 8:
                raise ValueError('Invalid recording scale')
        output.mkdir(parents=True, exist_ok=False)
        created_output = True
        client = Client(args.port)
        identity = client.ask('checkpoint_identity')
        if not identity.get('headless'):
            raise ValueError('Use a dedicated --serve session; SDL owns interactive execution')
        if args.mode == 'replay' and identity != recording['identity']:
            raise ValueError('Recording build/ROM identity differs; regenerate the baseline')
        # Reserve without replacing an existing user's RAM bookmark. On any later
        # failure restore the original machine, including input and native text.
        client.ask('checkpoint_save', slot=args.slot)
        owned = True
        if args.mode == 'replay' or args.start:
            client.ask('state_load', path=str(state if args.mode == 'replay' else external(args.start)))
        start = output / 'start.nss'
        if args.mode == 'record':
            client.ask('state_save', path=str(start))
        # The separate base slot is unnecessary: load the disk scene once and
        # use a second RAM checkpoint for all repeat passes.
        base_slot = (args.slot + 1) % 4
        base_owned = False
        try:
            client.ask('checkpoint_save', slot=base_slot)
            base_owned = True
            initial = client.observe(args.scale)
            if args.mode == 'replay' and initial != recording['initial']:
                raise RuntimeError('Starting presentation/cycles differ from the recording')
            if args.mode == 'record':
                recording = dict(schema=1, identity=identity, scale=args.scale, initial=initial,
                                 state_sha256=hashlib.sha256(start.read_bytes()).hexdigest(),
                                 steps=[], expected=[])
                if args.console:
                    print('Enter one JSON step per line, e.g. {"buttons":["A"],"frames":12}; EOF finishes.', flush=True)
                    inputs = (validate_step(json.loads(line)) for line in sys.stdin if line.strip())
                else:
                    inputs = iter(steps)
                for step in inputs:
                    validate_steps(recording['steps'] + [step])
                    client.step(step)
                    recording['steps'].append(step)
                    recording['expected'].append(client.observe(args.scale))
                    write_json(output / 'recording.json', recording)
                    print(f"Recorded {len(recording['steps'])}: {step['label'] or step['buttons']}", flush=True)
                validate_steps(recording['steps'])
            else:
                for run in range(args.repeat):
                    begin = time.monotonic()
                    client.ask('checkpoint_load', slot=base_slot)
                    for i, (step, expected) in enumerate(zip(steps, recording['expected'])):
                        client.step(step)
                        actual = client.observe(args.scale)
                        if actual != expected:
                            report.update(failed_pass=run + 1, failed_step=i, expected=expected, actual=actual)
                            client.observe(args.scale, output)
                            raise RuntimeError(f'Replay diverged at step {i}: {step["label"]}')
                    report['passes'].append(dict(run=run + 1, steps=len(steps), seconds=time.monotonic() - begin))
                    print(f"Replay {run + 1}: {len(steps)} steps matched", flush=True)
            report['success'] = True
        finally:
            if base_owned:
                client.ask('checkpoint_drop', slot=base_slot)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        report['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        if owned:
            try:
                client.ask('checkpoint_load', slot=args.slot)
                client.ask('checkpoint_drop', slot=args.slot)
                report['original_state_restored'] = True
            except (OSError, RuntimeError, ValueError) as error:
                report.update(success=False, restore_error=str(error))
        if client:
            client.close()
        if created_output:
            write_json(output / 'report.json', report)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
