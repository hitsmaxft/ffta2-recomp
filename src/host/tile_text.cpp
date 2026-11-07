// SPDX-License-Identifier: GPL-3.0-or-later
#include "tile_text.h"
#include <atomic>
#include <map>
#include <mutex>
#include <tuple>
namespace ffta2::host {
namespace {
std::mutex owners_mutex,rows_mutex;
std::map<uint32_t,std::shared_ptr<const TileText>> owners;
std::shared_ptr<const TileTexts> bindings=std::make_shared<const TileTexts>();
std::array<std::vector<TileTextSlice>,384> rows;
void update_bindings() {
    auto next=std::make_shared<TileTexts>();
    for(const auto& entry:owners)next->push_back(entry.second);
    std::atomic_store(&bindings,std::shared_ptr<const TileTexts>(next));
}
}
std::shared_ptr<const TileTexts> tile_texts() {return std::atomic_load(&bindings);}
void set_tile_text(TileText text) {
    std::lock_guard<std::mutex> lock(owners_mutex);
    owners[text.owner]=std::make_shared<const TileText>(std::move(text));update_bindings();
}
void remove_tile_text(uint32_t owner) {
    std::lock_guard<std::mutex> lock(owners_mutex);
    if(owners.erase(owner))update_bindings();
}
void reset_tile_text() {
    std::lock_guard<std::mutex> lock(owners_mutex);
    owners.clear();update_bindings();
    std::lock_guard<std::mutex> rows_lock(rows_mutex);
    for(auto& row:rows)row.clear();
}
void tile_text_scanline(int screen,int y,std::vector<TileTextSlice> slices) {
    std::lock_guard<std::mutex> lock(rows_mutex);
    if(screen>=0&&screen<2&&y>=0&&y<192)rows[screen*192+y]=std::move(slices);
}
void publish_tile_text() {
    std::lock_guard<std::mutex> lock(rows_mutex);
    using Key=std::tuple<uint32_t,int,int,int,uint32_t,uint32_t>;
    std::map<Key,TextDraw> draws;
    for(unsigned i=0;i<rows.size();++i) {
        for(const auto& slice:rows[i]) {
            if(!slice.text)continue;
            Key key{slice.text->owner,int(i/192),slice.x,slice.y,slice.color,slice.outline};
            auto& draw=draws[key];
            if(draw.clip.empty()) {
                draw.screen=int(i/192);draw.clip.resize(256*192);
                for(auto glyph:slice.text->glyphs) {
                    glyph.x+=slice.x;glyph.y+=slice.y;glyph.color=slice.color;glyph.outline=slice.outline;
                    draw.glyphs.push_back(glyph);
                }
            }
            std::copy(slice.visible.begin(),slice.visible.end(),draw.clip.begin()+(i%192)*256);
        }
        rows[i].clear();
    }
    for(auto& entry:draws)submit_text(std::move(entry.second));
}
}
