# Checkpoint-based native regression

Use a dedicated headless session (`tools/run_native.py --serve`), not the active
player's SDL window. Its scheduler advances only on explicit requests. Tests use
DS button names and exact VBlank counts; no wall-clock key sleeps are involved.

`tools/native_scenario.py` records a starting full-machine snapshot and an input
timeline. It checks the exact build/ROM identity and starting file SHA-256 before
replay. The core also validates localization/font compatibility. Each step records
both presentation-buffer SHA-256 values and scheduler/CPU cycle timestamps.
Unfulfilled frame requests, terminal CPUs, identity mismatches and divergent
observations fail visibly. This is a reproducibility check, not proof that the
baseline translation or layout is correct; approve each baseline visually once.

## Record and replay

Input JSON is a list of steps, for example:

```json
[
  {"buttons": ["A"], "frames": 12, "label": "next dialogue page"},
  {"frames": 60, "label": "release and settle"},
  {"buttons": ["Down", "R"], "frames": 12, "label": "combined input"},
  {"frames": 60, "touch": {"x": 128, "y": 96, "down": true}}
]
```

Each step defines the complete held button set and touch state; omitted buttons
and touch mean released. Supported buttons are A/B/X/Y/L/R, Start/Select and the
four directions. Bounds are 1..6000 VBlanks per step, at most 1000 steps and
36000 VBlanks per recording. Put scene inputs and evidence outside the checkout.

```sh
python3 tools/native_scenario.py record --port 19979 \
  --start /external/scenes/teacher.nss \
  --scenario /external/scenes/teacher-input.json \
  --output /external/teacher-recording

python3 tools/native_scenario.py replay --port 19979 \
  --recording /external/teacher-recording/recording.json \
  --repeat 3 --output /external/teacher-regression
```

Omit `--start` to record from the current headless position. To record inputs
incrementally, use `--console` instead of `--scenario`, enter one JSON step per
line and finish with EOF. This is an input-driven headless recorder, not automatic
recording of manual SDL keyboard/gamepad events. The player window is untouched.

Recording writes `start.nss`, `recording.json` and `report.json`. Replay loads the
scene once, then restores a RAM checkpoint between passes, without rereading or
rewriting the state file. No screenshot is produced on success. A divergence
records the failing step, expected/actual hashes and timestamps, plus two lossless
PPM presentation buffers. These buffers include the native text compositor but
are not SDL window readbacks. Use an actual SDL capture when checking window
placement, scaling or display-driver behavior.

The original headless machine state is restored at exit, including input and
native text. Failure to restore makes the command fail. Existing output folders
are refused; occupied RAM slots are preserved. Cross-build snapshot migration is
not supported. Rebuilds or intentional font/layout changes require a freshly
approved baseline; do not bypass identity checks to obtain a pass.

## RAM checkpoint interface

Local debug commands, on the scheduler owner in headless mode:

- `checkpoint_identity`: build ID, ROM SHA-1 and headless flag.
- `checkpoint_save`, `checkpoint_load`, `checkpoint_drop`: `slot` in 0..3.

Snapshots own the CPU/scheduler, memory, devices, VRAM, GPU, sound and FTXT data.
They reuse the existing eligibility, validation and rollback path rather than
copying only RAM or persisting pointers. Loads detach historical battery/firmware
data from canonical disk persistence. Slots are process-local, bounded to four,
and never evicted silently. Each full snapshot costs tens of MiB; this is not an
unbounded per-frame rewind buffer. The tool reserves `--slot` (default 3) and its
next slot modulo four, then releases both. Durable named scenes remain `.nss`
files outside the repository.

## Reusing emulator components

The pinned runtime already incorporates melonDS GPU/device code and uses its
device serializers within native snapshots; see the upstream
[component attribution](../third_party/ndsrecomp/THIRD_PARTY_ATTRIBUTION.md).
Its CPU execution remains the project's AOT/Tier3 dispatcher.

Useful extensions include bounded rewind checkpoints, pause/frame advance,
input movies, controller mapping, audio controls and renderer improvements.
Reuse device algorithms or frontend code behind the current host interfaces;
keep a single scheduler and input owner. Rewind/movies must restore GPU, sound,
RTC and FTXT together. Emulator savestates cannot be loaded as native states,
and importing an emulator CPU core would require a deliberate architecture
change. An OpenGL/compute renderer port also does not automatically supply a
Metal renderer.

Keep upstream component licenses and provenance. The linked melonDS-derived
runner is a GPL-3.0-or-later combined work; distributed binaries need the
corresponding source and license, as described by the pinned upstream policy.

## Validation record (2026-11-07)

A dedicated macOS ARM64 native session recorded five input segments (204 VBlanks)
from a fresh-boot scene, including Start/A press and release. Three consecutive
RAM-restored replays matched both screen hashes and all recorded CPU/scheduler
timestamps at every step; the original machine was restored afterward. No
screenshots were required. This checks the mechanism on the opening scene, not
new Chinese UI coverage. The 40-test Python suite also checks deliberate replay
divergence, snapshot tampering, invalid input, occupied slots and output preservation.
