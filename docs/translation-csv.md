# Translation CSV contract

Use CSV as the canonical editable translation input. Exported catalogs contain
all 132792 original table entries across four languages, including duplicates
and placeholders. Do not use a spreadsheet's naive comma-split or line-split:
fields may contain commas, quotes, CR/LF and script tokens.

Encoding: UTF-8 with BOM for spreadsheet compatibility. Delimiter: comma.
Record terminator: CRLF. Every field is quoted; embedded quotes are doubled.
Newlines inside quoted fields are real newlines. Python's csv module reads and
writes the files with newline=''. No spreadsheet formulas are emitted by the
tools; import the text/translation columns explicitly as text in Excel.

| Column | Meaning |
| --- | --- |
| id | Stable family:language:block_id:string_id; do not edit |
| rom_offset | Original string's ROM offset, hexadecimal; do not edit |
| byte_length | Original encoded byte count; do not edit |
| source_sha256 | SHA-256 of original encoded bytes, including control bytes |
| source_text | Original readable text with script tokens; optional/blank in small tracked translation-only samples |
| translation | Unicode translation with original script tokens preserved |
| status | untranslated, review, or translated; only translated rows are imported |
| notes | Translator/editor notes; not inserted into the game |

The importer accepts a full catalog or a sparse subset. It rejects duplicate
IDs/columns, unknown IDs, malformed records, missing source identities, changed
original metadata, invalid statuses and changed/removed/reordered script tokens.
Newline layout may change; variable IDs, page ends and execution-affecting tokens
must retain order. JSON output preserves Unicode and stable IDs. The ROM builder
also compares source-byte hashes against the actual supplied ROM.

```sh
build/venv/bin/python tools/text_catalog.py export \
  --extraction /external/extraction --output /external/text-catalog.csv
build/venv/bin/python tools/text_catalog.py import /external/translated.csv \
  --catalog /external/text-catalog.csv --output /external/translations.json
build/venv/bin/python tools/build_cn_patch.py /path/to/retail.nds \
  --font /path/to/fusion-pixel-12px-monospaced-zh_hans.bdf \
  --translations-csv config/prologue-zh-hans.csv \
  --catalog /external/text-catalog.csv \
  --output /external/classroom-dialogue-cn.bps \
  --test-rom /external/classroom-dialogue-cn.nds
```

The CSV importer handles all families and all four language variants. The
current retail ROM insertion prototype supports language-0 event strings that
fit their existing allocations, with at most 23 additional ordinary glyphs.
Exceeding those limits is an explicit build error, not silent truncation. Full
translation-table import and Unicode storage therefore work independently of
future expanded ROM encoding or native runtime text replacement. The original
full catalog remains external; the tracked sample includes only translated
content, IDs and source hashes. Character naming remains untouched.

config/prologue-zh-hans.json is a compatibility sample. CSV builds validate the
CSV and use its strings instead. Programmatic import emits JSON for future
runtime/resource pipelines without requiring all translations to fit the current
retail one-byte font prototype.
