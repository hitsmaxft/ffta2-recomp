# Native text presentation

The external localization pack leaves the cartridge unchanged. The title hook
matches original resource bytes, prepares a Unicode line plan, and preserves the
original script control stream. The initial hook covers the prologue dialogue
pipeline, not every menu or image containing text.

`tools/run_native.py --font system` selects the macOS CoreText backend using
PingFang SC and system font fallback. No Apple font is bundled. `--font pixel`
keeps the external indexed glyph path.

System text is rendered at the output viewport resolution. It is **not** reduced
to the original 16x16 glyph texture. The original upload remains allocated and
owned by the game, but its pixels are transparent. Original text-object drawing
provides position, per-character reveal state, visibility, alpha, modulation and
palette selection to the host presentation layer. Cached menu draws retain their
host glyphs by object ownership until hidden, replaced or freed; a VBlank without
new geometry does not erase the menu. Palette selectors are 8-byte
offsets into the original palette area, not serialized palette IDs.

The SDL3 presenter uploads the host ARGB coverage layer after the game surface.
On macOS this can use SDL's Metal presentation backend; it does not constitute a
Metal implementation of the NDS 3D renderer. CoreText is isolated behind
`host::Font`; future DirectWrite/FreeType implementations can return the same
coverage structure. The game-specific code never calls CoreText or SDL.

## Display options

- `--window-scale 1..8`: initial window size, default 3. Resizing retains the
  upstream aspect-preserving logical presentation.
- `--lcd 0..1`: optional LCD pixel-grid strength, default off. Disabled below
  2x magnification to avoid an unreadable grid.
- `--lcd-text`: include high-resolution text in the LCD grid. By default text
  remains clear while the game image receives the grid.

Diagnostic `framebuffer` accepts `native_scale` from 1 to 8. Scales above 1 use
the same native text and LCD layers as desktop presentation. The game image is
nearest-neighbor enlarged; only the host text is rasterized at output resolution.
These captures are native runtime framebuffer captures, not desktop screenshots.

## Current validation boundary

CoreText coverage, antialiasing, line layout/control preservation, screen routing,
transient frame expiry, cached-menu object lifetime and LCD strength validation have focused native tests. Live prologue
captures have exercised actual recompiled/interpreted guest execution with the
unmodified ROM and the external localization pack.

Image-based labels (title, questionnaire, naming) use separate resources. Naming
is intentionally unchanged. Title assets use an exact-source-byte runtime override built by
`tools/build_native_title_assets.py` and selected with `--title-assets`. The
original atlas dimensions, rectangle table and five palette banks are preserved.
These labels remain original-resolution artwork, separate from vector dialogue. Arbitrary scene occlusion, widescreen text transforms and
full SUB-background font coverage need further validation. Windows and
Linux backends are extension points, not verified builds.


## UI regression evidence

`tools/replay_native_ui.py` replays ordinary buttons against a headless native
session. A scenario is a JSON list such as:

```json
[
  {"button": "Down", "hold": 12, "settle": 60, "capture": "next-item"},
  {"button": "B", "settle": 60, "capture": "closed-menu"}
]
```

Use `--scenario scenario.json --output /external/captures --scale 4`. The output
contains both-screen captures and per-step execution/text diagnostics. Successful
execution alone is not a visual pass. Check label baselines, selected/disabled
palettes, the right quantity/stat column, long names, scrolling, and menu closure.

The 3D list hook reserves the original right column and scrollbar gutter before
accepting translated text. Unsupported or oversized lines retain their original
rendering. SUB-background tile text is a separate path: diagnostics count matched
but untranslated labels, without changing its tile ownership or GPU priorities.
It is not covered by the 3D dialogue/list hook.

A power reset clears host text ownership. New snapshots serialize the native
line plans and reconstruct visible text immediately on load, including cached
menu objects. See [instant saves](native-savestates.md) for slot management,
validation and the limitations of older snapshots without a native text section.
