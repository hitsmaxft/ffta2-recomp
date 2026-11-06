# Native bank preparation

`tools/prepare_recomp.py` accepts only the original European A6FP revision 0
ROM. It writes executable images, identity-pinned TOML configurations, generated
C AOT banks, full generation logs, and a hash inventory outside the checkout.
It preserves the input ROM and refuses to overwrite a nonempty output directory.

```sh
python3 tools/prepare_recomp.py --rom /path/to/retail.nds \
  --output /path/outside/checkout/recomp/title
```

The default recompiler is `build/recompiler/nds_recompile`. Override it with
`--recompiler`. Each bank uses eight source shards and live-byte validation.
The header entry point and the recompiler's recursive CFG finder provide the
initial code discovery. The pinned ARM9 startup's literal load at `0x02000914`
and `BX r1` at `0x0200092C` prove application main `0x02000BDC`; this explicit
seed compensates for the finder's missed constant transfer. All three words
are checked before emission. Linear assembly listings and BL scans are not trusted
as exhaustive function inventories. The finder also attempts startup relocation
discovery; unresolved indirect transfers remain visible in the generation logs.

Pass `--coverage observed.json` (repeatable) to add real runtime entry points.
Supported inputs are the runner's `tier3_coverage` response or a coverage
manifest's `entry_points_arm9` / `entry_points_arm7` arrays. Preserve the ROM
identity when storing a debug response. A declared mismatching ROM identity,
invalid mode, or misaligned address is rejected. Entries outside the original
main image are recorded as skipped unless a byte-verified runtime copy maps them
back to the original image. Overlays remain independently identified banks.

Overlay `staticInitStart` identifies an initialization pointer array, not code.
This ROM's 18 such arrays contain zero pointers. The initial tool deliberately
does not emit overlay banks from those addresses. Many overlays share a load
address, so future banks must retain generation-aware live-byte validation.

Generated C becomes native macOS ARM64 code when compiled into the runner.
Preparation alone does not prove execution, rendering, input, audio, or saves.
Report ARM9 and ARM7 Tier3 instruction counts separately after a real run; a
working interpreter fallback is not evidence of complete AOT coverage.

## Runtime copies and resident overlays

Pass `--runtime-captures /external/captures` with paused-runner `read_region`
outputs named `mainram.bin`, `itcm.bin`, `wramshared.bin`, and `wram7.bin`.
The preparer rejects every declared copy whose complete bytes differ from the
pinned source image. Snapshot and source hashes are recorded in the manifest.
Observed entries in verified copies become seeds at their real runtime address.

| CPU | Source address | Runtime address | Verified length | ROM offset |
| --- | --- | --- | --- | --- |
| ARM9 | `0x0211E8E0` | `0x01FF8000` | `0x2D20` | `0x001228E0` |
| ARM7 | `0x023801E8` | `0x037F8000` | `0xF28C` | `0x001823E8` |
| ARM7 | `0x0238F56C` | `0x027E0000` | `0x17855` | `0x0019176C` |

The ARM7 WRAM copy crosses the shared/private boundary at `0x03800000`.
Its continuation maps original source `0x023881E8` to private WRAM offset zero.
The startup scanner finds a longer `0xF384` range, but the last `0xF8` bytes
contain runtime data: twenty bytes differed in the first observed snapshot.
The explicit verified code range therefore ends before the first changed byte.
ARM9's temporary startup copy at `0x027E0000` has subsequently been overwritten
by the ARM7 image and is not asserted to match the ARM9 live image.

`tools/prepare_runtime_banks.py` reads the ROM's actual overlay table and FAT,
requires complete equality against the live resident image, and seeds only
observed ARM9 coverage entries. It emits neither empty unobserved banks nor
banks for an overlay with mismatched live bytes. Supply `--rom`, `--captures`,
repeatable `--coverage`, and an external `--output`. It can append overlay banks
to a completed main-bank generation without replacing existing outputs.

The first observed capture matched overlay 0 at `0x01FFAD20` (20608 bytes,
ROM `0x00125C00`) and overlay 10 at `0x02132FC0` (10304 bytes,
ROM `0x00163E00`). Both use independent identity checks and live-byte validation;
other overlays that later occupy the same address must never reuse these banks
without matching bytes. `runtime-banks.json` records accepted and skipped banks.
The generated v3 set used 117 MiB, with 16559 ARM9 main functions, 3079 ARM7 main
functions, 940 overlay-0 functions and 894 overlay-10 functions. These counts are
CFG entries and landing pads, not a claimed inventory of original C functions.
