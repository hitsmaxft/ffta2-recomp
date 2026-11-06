# Model-safe translation handoff

Give the model `data/model/PROMPT.txt` and a batch of `model-input.jsonl`.
The prompt explicitly forbids translating, deleting, inserting or reordering
control characters/placeholders/variable IDs and parameters. It requires source
proofreading before translation and translation proofreading afterwards.

Models receive pure text only. `reconstruction.json` is an immutable program
input; do not send it for rewriting. It holds the protected control bytes,
original ordered recipes, source hashes and a catalog-bound integrity hash.
Newlines and special encoded symbols are protected too. The exporter audits
all 33198 first-language source recipes before producing model inputs.

The committed combined input has 37705 unique text fragments. Export creates
128-fragment batches so a model does not need to process the complete file in
one context. Each fragment includes byte/pixel limits from the original text;
Chinese bank encoding is planned as three bytes per glyph and 12px advance.
Final message-wide checks still apply after reassembly.

```sh
python tools/model_text_package.py export \
  --catalog data/text/catalog.csv --metrics data/analysis/font-metrics.json \
  --output /external/model-package --batch-size 128
```

Return JSONL with exactly `id` and `translation`, one object per ID. Translation
values must be pure text without backslashes, script syntax, newlines, tabs or
hidden Unicode controls. Never echo or edit the reconstruction manifest.
Concatenate completed batch responses into one JSONL file, then import:

```sh
python tools/model_text_package.py import \
  --catalog data/text/catalog.csv \
  --manifest /external/model-package/reconstruction.json \
  --response /external/responses.jsonl --output /external/review.csv
```

Missing IDs fail by default. `--allow-partial` explicitly permits checkpoint
imports while keeping incomplete messages untranslated. Duplicate/unknown IDs,
changed source or manifest identities, malformed response fields and injected
control syntax fail closed. Only the program restores the exact control stream.
Imported rows start as `review`, never patch-eligible automatically. Proofread,
run `tools/validate_translation.py`, resolve encoding/width/capacity failures and
then explicitly accept reviewed rows before building and testing a patch.

No prompt alone can guarantee model compliance. Detached controls, source-bound
reconstruction, strict response validation and patch preflight enforce it.
