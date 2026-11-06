# Project policy

Build an independent macOS native FFTA2 recompilation project, pinned initially
to the supplied European A6FP revision 0 ROM. Runtime Chinese text and font
replacement is part of the architecture. Do not change sibling projects or their
processes. Read upstream policies before editing vendored code.

Use English for source and documentation. Keep ROMs, extracted assets, saves,
generated game code and captures outside the checkout. Build artifacts belong
in root build/. Preserve upstream licenses. Never describe a resource viewer,
synthetic frame or interpreter-only run as native game execution. Report ARM9,
ARM7, fallback counts, rendered screens, input, audio and save gates separately.
Missing native dispatches must be visible. Avoid silent instruction fallback.

Runtime localization must use stable resource IDs and Unicode host strings;
do not patch the original ROM or force Chinese into the retail one-byte charset.
Keep original control-token streams and script effects available to the guest.
Native renderer integration and resource extraction are separate acceptance gates.


The owner explicitly authorized publishing decoded text CSVs, source hashes,
address maps and derived translation tables under data/. This exception does
not include ROM payloads, extracted binary assets, saves, generated guest code,
private execution paths or credentials. Preserve per-row translation status;
never label incomplete translation tables as a complete Chinese release.
