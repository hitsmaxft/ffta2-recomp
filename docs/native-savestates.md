# Native instant saves

The launcher configures 12 slots under `<session>/states/<ROM SHA-1>/`.
`--savestate-dir /external/states` selects a shared external root instead.
This is independent of `--save`, which controls the game's battery save.
Neither kind belongs in the public repository.

Press **Esc**, enter **Instant saves**, choose a slot with Left/Right, and use
**Save current state** or **Load selected state**. Each slot displays its local
modification time or `Empty`. Empty slots cannot be loaded. Saving replaces the
selected slot. The menu pauses guest execution and clears queued audio/input;
closing it resumes execution. On keyboards that reserve function keys for system
controls, the menu avoids needing Fn combinations.

- **Shift+F1..F12:** save the corresponding slot.
- **F1..F12:** load the corresponding slot.

Saves capture on the scheduler owner and publish atomically on the framework's
worker. The notice distinguishes a pending capture from durable success. Loads
wait for a pending save and use the same renderer, input and diagnostic epoch
invalidation as the framework shortcut path. This does not automatically replace
the game's canonical battery save after a historical load.

## Native text transaction

The `FTXT` section stores sessions, original resource IDs, source/translated
strings, page offsets, resolved Unicode placements, pending texture uploads,
active text owners and list-column gaps. Version 5 also stores tile/widget
ownership, the published frame with clipping masks, and palette-role bitmap
glyphs so transient UI text is available immediately after import. It uses explicit bounded little-endian
fields; no host pointers or C++ object memory are persisted. The section shares
the core container's CRC, atomic publication and rollback transaction. Async
publication serializes an already captured payload and never reads live objects.

Loading validates text resources and font mode before importing guest state.
After a successful import, the native text layer is immediately reconstructed
from restored object positions, palette selectors, reveal counters and alpha.
The saved dialogue does not need a new page to become visible. Game glyphs are
suppressed on the screen occupied by the host management menu.

Snapshots remain exact-build and exact-ROM. Changing `--font system` to
`--font pixel`, or changing translations referenced by the snapshot, causes load
to fail rather than silently restoring incompatible text. Legacy snapshots with
no `FTXT` section retain their old limitation: already-transparent native text
cannot be recovered until the game creates its next message. This is not a
cross-version save migration format.

## Validation

`tools/validate_native_savestate.py --port PORT --output /external/new-directory`
operates on a headless session displaying Chinese text. It saves, advances a
page, loads, compares both 4x presentation buffers byte-for-byte, and verifies
that a CRC-valid wrong-font snapshot and a truncated snapshot are rejected
without changing the current presentation. It restores the starting state.
Evidence remains external, including all state files and screenshots.

Live validation on macOS ARM64 passed the first prologue dialogue: before and
immediately-restored captures had identical SHA-256, while the advanced page
was different. A separate SDL window session exercised ordinary debug-injected
Esc/Return/arrows through the actual runtime menu: frame counts stopped while
open, slot 1 asynchronously committed, and slot 2 loaded the Chinese dialogue.
The window's game framebuffer was inspected. Desktop capture was unavailable,
so this does not establish a visual pass for the menu's on-screen layout.

The save feature does not extend translation coverage. Inventory and unit-status
SUB-background text still require their separate native font integration; see
[native UI validation](native-ui-validation.md).
