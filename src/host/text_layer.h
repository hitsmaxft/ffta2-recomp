// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <array>
#include <vector>
namespace ffta2::host {
struct TextGlyph {
    char32_t codepoint;
    float x, y;
    uint32_t color; // Straight ARGB, already modulated by guest alpha/color.
    uint32_t outline = 0xff000000;
    float em = 12;
    bool pixel = false;
    std::array<uint8_t,64> bitmap{};
    uint32_t shadow = 0xff000000;
};
struct TextDraw { int screen; std::vector<TextGlyph> glyphs; uint32_t owner = 0; std::vector<uint8_t> clip; };
bool vector_text_enabled();
void submit_text(TextDraw draw);
void publish_text_frame();
// Cached guest menu scenes retain glyphs until their owning object is hidden,
// replaced or freed. Owner zero is a one-frame draw for transient callers.
void remove_text_owner(uint32_t owner);
void clear_text_frames();
std::vector<TextDraw> snapshot_text_frame();
void restore_text_frame(std::vector<TextDraw> draws);
// Shared by desktop presentation and diagnostic capture. Transparent ARGB.
std::vector<uint32_t> render_text_layer(int screen, unsigned width, unsigned height);
}
