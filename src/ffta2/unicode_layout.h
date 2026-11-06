// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "localization_pack.h"
#include <functional>
#include <optional>

namespace ffta2 {
using GlyphAdvance = std::function<std::optional<uint16_t>(char32_t)>;
struct UnicodeRun {
    std::u32string text;
    bool name_variable = false;
    uint8_t parameter = 0;
};
struct UnicodeLineTemplate {
    std::string stable_id;
    size_t page_index = 0, line_index = 0;
    uint32_t source_page_begin = 0, source_page_end = 0; // Relative bytes, [begin,end).
    std::string source_pattern_utf8; // Anchored regex; captures original varA expansions.
    std::vector<UnicodeRun> source_runs, translated_runs;
};
struct UnicodePageTemplate {
    uint32_t source_begin = 0, source_end = 0;
    std::vector<UnicodeLineTemplate> lines;
};
struct UnicodeTextLayout {
    std::string stable_id;
    std::vector<UnicodePageTemplate> pages;
    const UnicodePageTemplate* page_at_source_offset(uint32_t offset) const;
};
struct UnicodePlacement { char32_t codepoint = 0; uint16_t x = 0, advance = 0; };
struct UnicodeLinePlan {
    std::string stable_id;
    size_t page_index = 0, line_index = 0;
    std::u32string codepoints;
    std::vector<UnicodePlacement> glyphs;
    uint16_t width = 0;
};

// Never changes source/control bytes. Rejects extra translated lines/pages,
// changed control streams, unsupported control effects, and missing glyphs.
// Shorter pages retain empty slots for missing trailing translated lines.
bool prepare_unicode_layout(const LocalizedText& text, const GlyphAdvance& advance,
                            UnicodeTextLayout& result, std::string& error);
// actual_source_utf8 is the original game's expanded line, not Chinese bytes.
// Captures varA names and inserts them into corresponding translated runs.
// Rejects mismatches, missing glyphs, >61 glyphs and >255 pixels atomically.
bool resolve_unicode_line(const UnicodeLineTemplate& line,
                          const std::string& actual_source_utf8,
                          const GlyphAdvance& advance,
                          UnicodeLinePlan& result, std::string& error);
// Finds exactly one original line in the current page. Duplicate source-line
// matches are rejected even when their translations happen to be identical.
bool find_unicode_line(const UnicodeTextLayout& layout, uint32_t source_page_offset,
                       const std::u32string& actual_source,
                       const GlyphAdvance& advance, UnicodeLinePlan& result,
                       std::string& error);
bool find_unicode_line(const LocalizedText& text, uint32_t source_page_offset,
                       const std::u32string& actual_source,
                       const GlyphAdvance& advance, UnicodeLinePlan& result,
                       std::string& error);
} // namespace ffta2
