// SPDX-License-Identifier: GPL-3.0-or-later
#include "ffta2/unicode_layout.h"
#include <iostream>

namespace {
ffta2::LocalizedText example(std::string source, std::string translated) {
    ffta2::LocalizedText t; t.id = "event:0:42:1"; t.source_utf8 = source; t.utf8 = translated;
    for (size_t i = 0; i < source.size();) {
        if (source[i] == '\n') { t.source_bytes.insert(t.source_bytes.end(), {0xc0,0}); ++i; }
        else if (source[i] == '\\') {
            auto end = source.find('\\', i+1); auto name = source.substr(i+1,end-i-1);
            uint8_t code = name == "endPage" ? 0xc3 : name == "end" ? 0xc1 : name == "varA:00" ? 0xca : 0xc2;
            t.source_bytes.insert(t.source_bytes.end(), {code,0}); i = end+1;
        } else { t.source_bytes.push_back(2); ++i; }
    }
    return t;
}
bool require(bool good, const char* label) { if (!good) std::cerr << label << '\n'; return good; }
}
int main() {
    ffta2::GlyphAdvance advance = [](char32_t c)->std::optional<uint16_t> { return c == U'缺' ? std::nullopt : std::optional<uint16_t>(c > 127 ? 12 : 6); };
    auto t = example("Summer\nSoon\\endPage\\\\end\\Teacher\nOutside\\var2:00\\\\end\\",
                     "暑假\n快了\\endPage\\\\end\\老师\n出去\\var2:00\\\\end\\");
    ffta2::UnicodeTextLayout layout; ffta2::UnicodeLinePlan line; std::string error;
    if (!require(ffta2::prepare_unicode_layout(t, advance, layout, error), error.c_str()) || layout.pages.size()!=2 ||
        layout.pages[0].lines.size()!=2 || layout.pages[1].source_begin != layout.pages[0].source_end) return 1;
    if (!ffta2::resolve_unicode_line(layout.pages[0].lines[0], "Summer", advance, line, error) || line.width!=24 || line.codepoints!=U"暑假") return 1;
    auto old = line;
    if (ffta2::resolve_unicode_line(layout.pages[0].lines[0], "Other", advance, line, error) || line.codepoints != old.codepoints) return 1;
    auto teacher = example("Not you, \\varA:00\\\nClemens!\\endPage\\\\end\\Next\\var2:00\\\\end\\",
                           "\\varA:00\\ Clemens,\n你先留下!\\endPage\\\\end\\下页\\var2:00\\\\end\\");
    teacher.id="event:0:103:6";
    if (!ffta2::prepare_unicode_layout(teacher, advance, layout, error) ||
        !ffta2::resolve_unicode_line(layout.pages[0].lines[0], "Not you, Luso", advance, line, error) || line.codepoints!=U"Luso Clemens,") return 1;
    if (!ffta2::find_unicode_line(layout, 0, U"Not you, Luso", advance, line, error) || line.codepoints!=U"Luso Clemens,") return 1;
    old = line;
    if (ffta2::resolve_unicode_line(layout.pages[0].lines[0], "Not you, "+std::string(70,'A'), advance, line, error) || line.codepoints!=old.codepoints) return 1;
    teacher.utf8="\\varA:01\\ Clemens,\n你先留下!\\endPage\\\\end\\下页\\var2:00\\\\end\\";
    if (ffta2::prepare_unicode_layout(teacher, advance, layout, error)) return 1;
    auto reduced=example("One\nTwo\\end\\", "一\\end\\");
    if (!ffta2::prepare_unicode_layout(reduced, advance, layout, error) || layout.pages[0].lines.size()!=2 ||
        !ffta2::resolve_unicode_line(layout.pages[0].lines[1], "Two", advance, line, error) || !line.codepoints.empty()) return 1;
    reduced.utf8="一\n二\n三\\end\\";
    if (ffta2::prepare_unicode_layout(reduced, advance, layout, error)) return 1;
    auto too_wide=example("One\\end\\", "一一一一一一一一一一一一一一一一一一一一一一\\end\\");
    if (ffta2::prepare_unicode_layout(too_wide, advance, layout, error)) return 1;
    auto missing=example("One\\end\\", "缺\\end\\");
    if (ffta2::prepare_unicode_layout(missing, advance, layout, error)) return 1;
    auto corrupt=example("One\\end\\", "一\\end\\"); corrupt.source_bytes.back()=1;
    if (ffta2::prepare_unicode_layout(corrupt, advance, layout, error)) return 1;
    auto many=example("One\\end\\", std::string(62,'x')+"\\end\\");
    ffta2::GlyphAdvance narrow=[](char32_t)->std::optional<uint16_t>{return 1;};
    if (ffta2::prepare_unicode_layout(many,narrow,layout,error)) return 1;
    auto ambiguous=example("One\nOne\\end\\", "一\n二\\end\\");
    if (ffta2::find_unicode_line(ambiguous,0,U"One",advance,line,error)) return 1;
    auto menu=example("Potion", "治疗药");
    menu.id="message:0:3:1"; menu.source_bytes.push_back(0);
    if (!ffta2::find_unicode_line(menu,0,U"Potion",advance,line,error) || line.width!=36) return 1;
    menu.source_bytes.push_back(0);
    if (ffta2::prepare_unicode_layout(menu,advance,layout,error)) return 1;
    menu.source_bytes.pop_back(); menu.id="event:0:3:1";
    if (ffta2::prepare_unicode_layout(menu,advance,layout,error)) return 1;
    std::cout << "Unicode layout: prologue pages, dynamic name, source-byte controls, slot preservation and bounds passed\n";
}
