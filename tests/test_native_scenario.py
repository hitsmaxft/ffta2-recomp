# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('native_scenario', Path(__file__).parents[1] / 'tools/native_scenario.py')
scenario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenario)


class Machine:
    def __init__(self, port):
        self.position = 17
        self.slots = {}
        self.inputs = 0
        self.diverge = False

    def close(self):
        pass

    def ask(self, cmd, **fields):
        if cmd == 'checkpoint_identity':
            return dict(headless=True, build_id='test', rom_sha1='a' * 40)
        if cmd == 'checkpoint_save':
            if fields['slot'] in self.slots:
                raise RuntimeError('occupied')
            self.slots[fields['slot']] = self.position
        elif cmd == 'checkpoint_load':
            self.position = self.slots[fields['slot']]
        elif cmd == 'checkpoint_drop':
            del self.slots[fields['slot']]
        elif cmd == 'state_save':
            Path(fields['path']).write_text(str(self.position))
        elif cmd == 'state_load':
            self.position = int(Path(fields['path']).read_text())
        return dict(ok=True)

    def step(self, step):
        self.inputs += 1
        self.position += step['frames'] + len(step['buttons']) + int(self.diverge)

    def observe(self, scale, failure_dir=None):
        if failure_dir:
            (failure_dir / 'failure-A.ppm').write_text('failure')
        return dict(screens=[str(self.position)] * 2, cycles=[self.position] * 3)


class ScenarioTest(unittest.TestCase):
    def run_tool(self, machine, *args):
        with patch.object(sys, 'argv', ['native_scenario.py', *map(str, args)]), patch.object(scenario, 'Client', return_value=machine):
            return scenario.main()

    def test_replay_restores_machine_and_detects_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'steps.json'
            source.write_text(json.dumps([dict(buttons=['A', 'Right'], frames=12), dict(frames=60)]))
            machine = Machine(0)
            self.assertEqual(self.run_tool(machine, 'record', '--scenario', source, '--output', root / 'record'), 0)
            self.assertEqual(machine.position, 17)
            machine.position = 123
            recording = root / 'record/recording.json'
            self.assertEqual(self.run_tool(machine, 'replay', '--recording', recording, '--repeat', 3, '--output', root / 'replay'), 0)
            self.assertEqual(machine.position, 123)
            self.assertEqual(machine.slots, {})
            machine.diverge = True
            self.assertEqual(self.run_tool(machine, 'replay', '--recording', recording, '--output', root / 'failure'), 1)
            report = json.loads((root / 'failure/report.json').read_text())
            self.assertEqual(report['failed_step'], 0)
            self.assertTrue(report['original_state_restored'])
            self.assertTrue((root / 'failure/failure-A.ppm').exists())
            self.assertEqual(machine.position, 123)
            # Tampering is rejected before any input is applied.
            (root / 'record/start.nss').write_text('456')
            inputs = machine.inputs
            self.assertEqual(self.run_tool(machine, 'replay', '--recording', recording, '--output', root / 'tampered'), 1)
            self.assertEqual(inputs, machine.inputs)

    def test_existing_output_is_never_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'report.json').write_text('preserve')
            source = root / 'steps.json'
            source.write_text('[{"frames":1}]')
            self.assertEqual(self.run_tool(Machine(0), 'record', '--scenario', source, '--output', root), 1)
            self.assertEqual((root / 'report.json').read_text(), 'preserve')

    def test_occupied_bookmarks_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'steps.json'
            source.write_text('[{"frames":1}]')
            machine = Machine(0)
            machine.slots[0] = 999  # Second slot reservation fails.
            self.assertEqual(self.run_tool(machine, 'record', '--scenario', source, '--output', root / 'evidence'), 1)
            self.assertEqual(machine.position, 17)
            self.assertEqual(machine.slots, {0: 999})

    def test_invalid_input_is_rejected(self):
        for step in [dict(frames=0), dict(frames=True), dict(frames=6001),
                     dict(frames=1, buttons=['A', 'A']), dict(frames=1, buttons=['Esc']),
                     dict(frames=1, touch=dict(x=256, y=10, down=True))]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                scenario.validate_step(step)


if __name__ == '__main__':
    unittest.main()
