# Runtime localization resources

The native pack is an independent host resource directory. The original ROM is
read only for identity and original text-byte verification. The builder never
writes a modified ROM or forces Chinese through the retail byte character set.

```sh
python3 tools/build_native_localization.py --rom /path/to/original.nds \
  --font /path/to/fusion-pixel-12px-monospaced-zh_hans.bdf \
  --recipe /path/to/previous-glyph-recipe.json \
  --translations data/text/machine-cn.csv --all-font-glyphs \
  --output /external/native-localization
```

`--all-font-glyphs` bundles every printable Unicode glyph from the supplied BDF,
so later translations do not need to rebuild a subset merely to add a Chinese
character. Original western glyphs retain their original widths.

The optional recipe accepts `bank_glyphs` or `glyphs`; every non-ASCII character
in every available draft is added as well. Only `translated` rows enter runtime
text resources by default. `--include-review` explicitly enables review drafts;
both CSV status and host record retain that distinction. Every accepted row
must match the original catalog hash, actual ROM source bytes, and original
control-token sequence including variable parameters. Line endings normalize
to LF. Host strings carry lengths and are not copied into retail allocations.

Outputs include an RFC 4180 UTF-8 BOM translation CSV, glyph recipe CSV, indexed
16x16 2bpp glyphs, advance widths, all five original 16-entry BGR555 palettes,
font license, manifest, checksums, and `localization.bin`. All binary assets stay
outside checkout. Pixel indices mean transparent, outline, shadow, foreground;
the active native text renderer chooses the appropriate original palette.

`ffta2::LocalizationStore::reload(directory, actual_rom_sha256, error)` validates
all required files with the macOS CommonCrypto SHA256 implementation, parses
the bounded length-prefixed host pack, validates UTF-8, duplicate IDs/glyphs,
source-byte hashes and control streams, and atomically publishes an immutable
snapshot. A bad reload preserves the old snapshot. Integrity checks detect
corruption; the pack is not cryptographically signed or an authenticated update.

The snapshot exposes actual replacement resources through `text(stable_id)`,
`text_at_rom_offset(offset)`, `glyph(codepoint)`, and `palettes()`. Text records
carry original source bytes, capacities, and source offsets for native loader
hooks. UTF-8 text includes original script tokens; hooks must execute these,
including name variables and page transitions, instead of drawing token syntax.
Callers must retain the snapshot while using returned record pointers.

This interface is not a subtitle renderer. It supplies native text/font resource
overrides for a title-owned loader hook. The loader/glyph dispatch hooks and
rendered gameplay verification remain separate integration gates; loading a pack
alone does not prove that game text has been replaced on screen.

## Runner integration

The macOS backend accepts `--localization /external/native-localization`.
It hashes the loaded ROM bytes itself and verifies the entire external pack
before starting either guest CPU. Startup rejects an invalid package. The
runtime holds immutable snapshots for future title-owned text/glyph hooks.
`localization_info` and `localization_reload` debug commands expose loaded counts
and atomically reload the configured directory on the emulation thread. A bad
reload retains the working pack. No ROM file write or guest-code patch occurs.

The diagnostic response explicitly reports `game_render_hook: false` until
Unicode layout and actual glyph drawing are connected and gameplay-tested.
Neither these commands nor a successful load imply Chinese is displayed by the
game. External subtitles alone are insufficient for this project's goal: native
font, character-map, advance-width, palette and script-resource overrides must
reach the actual text rendering path.
