// SPDX-License-Identifier: GPL-3.0-or-later
#include "unicode_layout.h"
#include <algorithm>
#include <map>
#include <regex>
#include <stdexcept>

namespace ffta2 {
namespace {
std::u32string decode(const std::string& s) {
    std::u32string out;
    for (size_t p = 0; p < s.size();) {
        auto c = static_cast<uint8_t>(s[p++]); uint32_t cp = c, minimum = 0; unsigned n = 0;
        if (c >= 0xc2 && c <= 0xdf) { cp = c & 31; n = 1; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { cp = c & 15; n = 2; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { cp = c & 7; n = 3; minimum = 0x10000; }
        else if (c >= 0x80) throw std::runtime_error("Invalid UTF-8 lead byte");
        if (p + n > s.size()) throw std::runtime_error("Truncated UTF-8");
        for (unsigned i = 0; i < n; ++i) { auto t = static_cast<uint8_t>(s[p++]);
            if ((t & 0xc0) != 0x80) throw std::runtime_error("Invalid UTF-8 continuation"); cp = (cp << 6) | (t & 63); }
        if (cp < minimum || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ||
            (cp < 32 && cp != '\n') || cp == 127) throw std::runtime_error("Invalid Unicode text or layout control");
        out.push_back(cp);
    }
    return out;
}
std::string encode(const std::u32string& s) {
    std::string out;
    for (uint32_t cp : s) {
        if (cp < 0x80) out += char(cp);
        else if (cp < 0x800) { out += char(0xc0 | (cp >> 6)); out += char(0x80 | (cp & 63)); }
        else if (cp < 0x10000) { out += char(0xe0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
        else { out += char(0xf0 | (cp >> 18)); out += char(0x80 | ((cp >> 12) & 63)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
    }
    return out;
}
struct ParsedPage { uint32_t begin = 0, end = 0; std::vector<std::vector<UnicodeRun>> lines; };
struct Parsed { std::vector<ParsedPage> pages; std::vector<std::pair<uint8_t,uint8_t>> controls; };
std::pair<uint8_t,uint8_t> token(const std::string& s) {
    if (s == "end") return {0xc1,0};
    if (s == "endPage") return {0xc3,0};
    std::smatch m;
    if (std::regex_match(s, m, std::regex("var([0-9A-F]):([0-9A-Fa-f]{2})")))
        return {static_cast<uint8_t>(0xc0 + std::stoi(m[1], nullptr, 16)), static_cast<uint8_t>(std::stoi(m[2], nullptr, 16))};
    throw std::runtime_error("Unsupported script token: " + s);
}
Parsed parse(const std::string& text, const std::vector<uint8_t>* raw) {
    auto s = decode(text); Parsed out; ParsedPage page; std::vector<UnicodeRun> line;
    size_t byte = 0; bool after_boundary = false;
    auto consume = [&](uint8_t code, uint8_t parameter, bool control) {
        const size_t count = control ? 2 : 1;
        if (raw) {
            if (byte + count > raw->size()) throw std::runtime_error("Source text exceeds original bytes");
            if (control ? ((*raw)[byte] != code || (*raw)[byte+1] != parameter) : ((*raw)[byte] == 0 || (*raw)[byte] >= 0xc0))
                throw std::runtime_error("Source control/text structure differs from original bytes");
        }
        byte += count;
    };
    auto finish = [&]() { page.lines.push_back(std::move(line)); line.clear(); page.end = static_cast<uint32_t>(byte);
        out.pages.push_back(std::move(page)); page = ParsedPage{}; page.begin = static_cast<uint32_t>(byte); };
    for (size_t p = 0; p < s.size();) {
        auto cp = s[p++];
        if (cp == '\\') {
            size_t end = p; while (end < s.size() && s[end] != '\\') ++end;
            if (end == s.size()) throw std::runtime_error("Unclosed script token");
            auto t = token(encode(s.substr(p, end-p))); p = end + 1;
            consume(t.first, t.second, true); out.controls.push_back(t);
            if (t.first == 0xc1 || t.first == 0xc3) {
                if (!after_boundary) finish();
                else if (!out.pages.empty()) out.pages.back().end = static_cast<uint32_t>(byte);
                page.begin = static_cast<uint32_t>(byte); after_boundary = true;
            } else if (t.first == 0xca) {
                line.push_back({{}, true, t.second}); after_boundary = false;
            } else if (t.first != 0xc2) throw std::runtime_error("Unsupported layout-affecting control");
            continue;
        }
        if (cp == '\n') { consume(0xc0, 0, true); page.lines.push_back(std::move(line)); line.clear(); after_boundary = false; }
        else { consume(0, 0, false); if (line.empty() || line.back().name_variable) line.push_back({});
            line.back().text.push_back(cp); after_boundary = false; }
    }
    if (raw && byte != raw->size()) throw std::runtime_error("Unconsumed original source bytes");
    if (!after_boundary && (!line.empty() || !page.lines.empty() || out.pages.empty())) finish();
    return out;
}
std::vector<uint8_t> variables(const std::vector<UnicodeRun>& runs) {
    std::vector<uint8_t> out; for (const auto& run : runs) if (run.name_variable) out.push_back(run.parameter); return out;
}
void bounds(const std::u32string& s, const GlyphAdvance& advance, UnicodeLinePlan* plan) {
    if (s.size() > 61) throw std::runtime_error("Line exceeds 61 glyph descriptors");
    uint32_t width = 0;
    for (auto cp : s) {
        auto a = advance(cp); if (!a || !*a || *a > 32) throw std::runtime_error("Missing or invalid external glyph advance");
        if (width + *a > 255) throw std::runtime_error("Line exceeds 255-pixel descriptor width");
        if (plan) plan->glyphs.push_back({cp, static_cast<uint16_t>(width), *a}); width += *a;
    }
    if (plan) { plan->codepoints = s; plan->width = static_cast<uint16_t>(width); }
}
std::string pattern(const std::vector<UnicodeRun>& runs) {
    std::string out = "^";
    for (const auto& run : runs) {
        if (run.name_variable) { out += "(.*?)"; continue; }
        for (char c : encode(run.text)) { if (std::string("\\.^$|()[]{}*+?").find(c) != std::string::npos) out += '\\'; out += c; }
    }
    return out + "$";
}
} // namespace

const UnicodePageTemplate* UnicodeTextLayout::page_at_source_offset(uint32_t offset) const {
    for (const auto& page : pages) if (page.source_begin <= offset && offset < page.source_end) return &page;
    return nullptr;
}
bool prepare_unicode_layout(const LocalizedText& text, const GlyphAdvance& advance,
                            UnicodeTextLayout& result, std::string& error) {
    try {
        auto source_bytes = text.source_bytes;
        if (text.id.rfind("message:0:", 0) == 0 && !source_bytes.empty() &&
            source_bytes.back() == 0 && text.source_utf8.find_first_of("\\\n") == std::string::npos)
            source_bytes.pop_back(); // Catalog capacity includes the menu terminator.
        auto source = parse(text.source_utf8, &source_bytes), translated = parse(text.utf8, nullptr);
        if (source.controls != translated.controls || source.pages.size() != translated.pages.size())
            throw std::runtime_error("Translation changed script control stream or page count");
        UnicodeTextLayout candidate; candidate.stable_id = text.id;
        for (size_t p = 0; p < source.pages.size(); ++p) {
            const auto& a = source.pages[p]; const auto& b = translated.pages[p];
            if (b.lines.size() > a.lines.size()) throw std::runtime_error("Translation adds a line to the original page");
            UnicodePageTemplate page{a.begin, a.end, {}};
            for (size_t n = 0; n < a.lines.size(); ++n) {
                UnicodeLineTemplate line; line.stable_id = text.id; line.page_index = p; line.line_index = n;
                line.source_page_begin = a.begin; line.source_page_end = a.end; line.source_runs = a.lines[n];
                if (n < b.lines.size()) line.translated_runs = b.lines[n];
                if (variables(line.source_runs) != variables(line.translated_runs))
                    throw std::runtime_error("Name variables moved between original line slots");
                line.source_pattern_utf8 = pattern(line.source_runs);
                std::u32string static_text;
                for (const auto& run : line.translated_runs) if (!run.name_variable) static_text += run.text;
                bounds(static_text, advance, nullptr); page.lines.push_back(std::move(line));
            }
            candidate.pages.push_back(std::move(page));
        }
        result = std::move(candidate); error.clear(); return true;
    } catch (const std::exception& e) { error = e.what(); return false; }
}
bool resolve_unicode_line(const UnicodeLineTemplate& line, const std::string& actual,
                          const GlyphAdvance& advance, UnicodeLinePlan& result, std::string& error) {
    try {
        decode(actual); std::smatch matches;
        if (!std::regex_match(actual, matches, std::regex(line.source_pattern_utf8)))
            throw std::runtime_error("Actual expanded original line does not match source template");
        std::map<uint8_t, std::u32string> names; size_t capture = 1;
        for (const auto& run : line.source_runs) if (run.name_variable) {
            auto value = decode(matches[capture++].str()); auto previous = names.find(run.parameter);
            if (previous != names.end() && previous->second != value) throw std::runtime_error("Conflicting name-variable expansion");
            names[run.parameter] = std::move(value);
        }
        std::u32string codepoints;
        for (const auto& run : line.translated_runs) codepoints += run.name_variable ? names.at(run.parameter) : run.text;
        UnicodeLinePlan candidate; candidate.stable_id = line.stable_id; candidate.page_index = line.page_index;
        candidate.line_index = line.line_index; bounds(codepoints, advance, &candidate);
        result = std::move(candidate); error.clear(); return true;
    } catch (const std::exception& e) { error = e.what(); return false; }
}
bool find_unicode_line(const UnicodeTextLayout& layout, uint32_t offset,
                       const std::u32string& actual_source, const GlyphAdvance& advance,
                       UnicodeLinePlan& result, std::string& error) {
    try {
        auto page = layout.page_at_source_offset(offset);
        if (!page) throw std::runtime_error("Original cursor is outside planned page ranges");
        auto actual = encode(actual_source); decode(actual);
        const UnicodeLineTemplate* selected = nullptr;
        for (const auto& line : page->lines) {
            if (!std::regex_match(actual, std::regex(line.source_pattern_utf8))) continue;
            if (selected) throw std::runtime_error("Ambiguous original line in current page");
            selected = &line;
        }
        if (!selected) throw std::runtime_error("No original line matches current page");
        return resolve_unicode_line(*selected, actual, advance, result, error);
    } catch (const std::exception& e) { error = e.what(); return false; }
}
bool find_unicode_line(const LocalizedText& text, uint32_t offset,
                       const std::u32string& actual, const GlyphAdvance& advance,
                       UnicodeLinePlan& result, std::string& error) {
    UnicodeTextLayout layout;
    return prepare_unicode_layout(text, advance, layout, error) &&
           find_unicode_line(layout, offset, actual, advance, result, error);
}
} // namespace ffta2
