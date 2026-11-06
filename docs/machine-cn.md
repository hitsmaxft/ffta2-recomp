# Terra machine-translation and CJK runtime experiment

The target is the complete first language slot, not four redundant translations.
The catalog has 33198 slot-0 records and 16868 unique decoded source strings.
Counts include unused placeholders and duplicate entries. The public snapshot
manifest reports draft/review/planning-accepted counts, not gameplay coverage.
Character naming is intentionally unchanged.

## Independent gates

1. Translate every unique source with Terra, preserve script-token order and
   parameters, retain source identity, and checkpoint drafts outside the repo.
2. Merge drafts into the public RFC 4180 CSV. Untranslated/review entries remain
   explicitly marked; importing the table includes only translated entries.
3. Verify encoded length against each original allocation, preserve pages and
   option delimiters, and check static line widths and line counts using the
   retail width table. Dynamic variable widths still need runtime validation.
4. Implement extended CJK encoding and font reads across the actual rendering
   consumers; validate code residency, heap use, ASCII behavior and source hashes.
5. Build a separate ROM and BPS, independently apply the BPS, then fresh-boot in
   the diagnostic emulator and check real Chinese framebuffers and progression.

Passing an earlier gate does not imply later gates pass. The original prototype
supports 23 new ordinary single-byte glyphs; it deliberately refuses a full
translation. Directly appending thousands of glyphs would exceed the measured
font heap and does not widen the retail byte-based rendering consumers.

The new bank experiment considers a control-pair bank selector followed by an
ordinary glyph byte. Its planning cost is three encoded bytes per Chinese glyph,
with 12-pixel advance. This is not UTF-8. Font code/records are being tested in
the existing loaded font resource, with glyph payloads in verified ROM padding.
Control handling, each glyph consumer and the resource-read path need individual
verification. No unverified experiment is included as a playable full release.

## Tools

- `tools/text_resources.py`: verifies all source addresses, bounded table slots,
  byte lengths and source hashes against the pinned ROM.
- `tools/validate_translation.py`: fail-closed control, encoding, byte allocation
  and conservative static layout preflight; `--planned-cjk-bytes 3` is explicitly
  planning only. It never edits a ROM.
- `tools/export_public_data.py`: merges owner-authorized decoded text and draft
  mappings, preserving revision-specific source identities and review states.
- `tools/check_public_tree.py`: audits actual staged blobs using a text/type
  allowlist and credential/binary checks; vendored source uses a pinned submodule.
- `tools/cjk_runtime_patch.py`: deterministic, read-only candidate call-site audit.
  Linear ARM/Thumb scans include data and cannot prove all indirect consumers.
- `tools/machine_translate.py`: experimental Codex CLI batching/checkpoint driver.
  A tested ChatGPT-account CLI request for `gpt-6.1-terra` returned model_not_found;
  this path is not a working translation service in that account. Current draft
  files were generated directly by Terra workers, not another translation model.

Publication includes tools, decoded CSVs and numeric address information only.
ROM images, extracted font bitmaps, guest binaries, saved states and emulator
cores remain external. Original source identity is preserved throughout.
