// SPDX-License-Identifier: GPL-3.0-or-later
#include "text_layer.h"
#include "font.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
namespace ffta2::host {
namespace {
std::mutex frame_mutex;
std::vector<TextDraw> building, published;
std::map<uint32_t,TextDraw> retained;
void blend(uint32_t& dst, uint32_t color, unsigned coverage) {
    unsigned alpha = (color >> 24) * coverage / 255;
    unsigned previous = dst >> 24;
    unsigned out_alpha = alpha + previous * (255-alpha) / 255;
    if (!out_alpha) return;
    uint32_t result = out_alpha << 24;
    for (unsigned shift : {0u, 8u, 16u}) {
        unsigned c = (((color >> shift)&255)*alpha +
            ((dst >> shift)&255)*previous*(255-alpha)/255) / out_alpha;
        result |= c << shift;
    }
    dst = result;
}
}
std::optional<uint16_t> system_glyph_advance(char32_t codepoint) {
    thread_local auto font=make_system_font();
    thread_local std::map<char32_t,std::optional<uint16_t>> advances;
    auto it=advances.find(codepoint);
    if(it!=advances.end())return it->second;
    GlyphCoverage coverage;
    std::optional<uint16_t> result;
    if(font && font->rasterize(codepoint,12,coverage) && coverage.advance>0 && coverage.advance<=32)
        result=uint16_t(std::ceil(coverage.advance));
    if(advances.size()>65536)advances.clear();
    advances.emplace(codepoint,result);
    return result;
}
bool vector_text_enabled() {
    static bool enabled = [] { const char* p = std::getenv("FFTA2_FONT"); return p && std::strcmp(p,"system")==0; }();
    return enabled;
}
void submit_text(TextDraw draw) {
    std::lock_guard<std::mutex> lock(frame_mutex);
    if(draw.owner)retained[draw.owner]=std::move(draw);
    else building.push_back(std::move(draw));
}
void remove_text_owner(uint32_t owner) {
    std::lock_guard<std::mutex> lock(frame_mutex);
    retained.erase(owner);
    published.erase(std::remove_if(published.begin(),published.end(),
        [owner](const TextDraw& draw){return draw.owner==owner;}),published.end());
}
void publish_text_frame() {
    std::lock_guard<std::mutex> lock(frame_mutex);
    published.swap(building); building.clear();
    for(const auto& item:retained)published.push_back(item.second);
}
void clear_text_frames() {
    std::lock_guard<std::mutex> lock(frame_mutex);
    published.clear(); building.clear();retained.clear();
}
std::vector<uint32_t> render_text_layer(int screen, unsigned width, unsigned height) {
    if (!vector_text_enabled() || !width || !height || width>4096 || height>3072) return {};
    std::vector<TextDraw> draws;
    { std::lock_guard<std::mutex> lock(frame_mutex); draws=published; }
    bool any=false; for (const auto& draw:draws) if(draw.screen==screen&&!draw.glyphs.empty()) any=true;
    if (!any) return {};
    struct FrameCache {
        unsigned width=0,height=0;
        uint64_t signature=0;
        std::vector<uint32_t> pixels;
    };
    thread_local FrameCache frames[2];
    uint64_t signature=1469598103934665603ull;
    auto mix=[&](uint64_t value) { signature=(signature^value)*1099511628211ull; };
    for(const auto& draw:draws) if(draw.screen==screen) {
        mix(draw.glyphs.size());
        for(const auto& glyph:draw.glyphs) {
            mix(glyph.codepoint);mix(uint32_t(std::lround(glyph.x*256)));
            mix(uint32_t(std::lround(glyph.y*256)));mix(glyph.color);mix(glyph.outline);
        }
    }
    auto& frame=frames[screen&1];
    if(frame.width==width && frame.height==height && frame.signature==signature)
        return frame.pixels;
    // Cache belongs to each renderer thread, independent of guest/pack lifetime.
    thread_local auto font=make_system_font();
    thread_local std::map<std::pair<char32_t,unsigned>,GlyphCoverage> cache;
    if (!font) return {};
    const float sx=float(width)/256, sy=float(height)/192;
    const unsigned size=std::max(4u,unsigned(std::lround(12*sy)));
    if (cache.size()>8192) cache.clear();
    std::vector<uint32_t> pixels(size_t(width)*height);
    for (const auto& draw:draws) {
        if(draw.screen!=screen) continue;
        for (const auto& glyph:draw.glyphs) {
            auto key=std::make_pair(glyph.codepoint,size);
            auto it=cache.find(key);
            if(it==cache.end()) {
                GlyphCoverage coverage;
                if(!font->rasterize(glyph.codepoint,float(size),coverage)) continue;
                it=cache.emplace(key,std::move(coverage)).first;
            }
            const auto& coverage=it->second;
            const int origin_x=int(std::lround(glyph.x*sx));
            const int origin_y=int(std::lround(glyph.y*sy));
            auto paint=[&](int dx,int dy,uint32_t color) {
                for(unsigned y=0;y<coverage.height;++y) for(unsigned x=0;x<coverage.width;++x) {
                    int px=origin_x+int(x)+dx,py=origin_y+int(y)+dy;
                    if(px<0||py<0||px>=int(width)||py>=int(height))continue;
                    blend(pixels[size_t(py)*width+px],color,coverage.alpha[y*coverage.width+x]);
                }
            };
            const int outline=std::max(1,int(std::lround(sy*0.55f)));
            for(int dy=-outline;dy<=outline;++dy) for(int dx=-outline;dx<=outline;++dx)
                if(dx*dx+dy*dy<=outline*outline) paint(dx,dy,glyph.outline);
            paint(0,0,glyph.color);
        }
    }
    frame={width,height,signature,pixels};
    return pixels;
}
}
