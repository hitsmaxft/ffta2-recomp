// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "text_layer.h"
#include <array>
#include <memory>
namespace ffta2::host {
struct TileText {
    uint32_t owner=0;
    unsigned bg=0, columns=0, palette_group=0;
    int x=0,y=0;
    std::array<uint32_t,2> map_offsets{};
    std::array<uint16_t,2> tiles{};
    std::vector<TextGlyph> glyphs; // Positions relative to the guest label origin.
};
using TileTexts=std::vector<std::shared_ptr<const TileText>>;
std::shared_ptr<const TileTexts> tile_texts();
void set_tile_text(TileText text);
void remove_tile_text(uint32_t owner);
void reset_tile_text();
// Render workers own distinct scanlines. Publication runs only after their fence.
struct TileTextSlice {
    std::shared_ptr<const TileText> text;
    int x=0,y=0;
    uint32_t color=0,outline=0;
    std::array<uint8_t,256> visible{};
};
void tile_text_scanline(int screen,int y,std::vector<TileTextSlice> slices);
void publish_tile_text();
}
