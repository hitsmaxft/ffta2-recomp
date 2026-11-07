// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_text.h"
#include "guest_texture.h"
#include "host/text_layer.h"
#include "host/tile_text.h"
#include "host/font.h"
#include "localization_runtime.h"
#include "unicode_layout.h"
#include "state.h"
#include "gpu3d.h"
#include "vram.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <atomic>
#include <map>
#include <stdexcept>

namespace {
using namespace ffta2;
struct Session {
    uint32_t base=0, offset=0;
    std::shared_ptr<const LocalizationPack> pack;
    const LocalizedText* text=nullptr;
    UnicodeTextLayout layout;
};
struct Pending { Session session; UnicodeLinePlan line; uint32_t object=0, source=0; int left=0, right=256, align_edge=-1; };
std::map<uint32_t,Session> sessions;
std::map<uint32_t,uint8_t> list_gaps;
std::map<uint32_t,Pending> pending, active, tile_plans, widget_pending, widget_active;
std::atomic<uint64_t> bound{0}, rendered{0}, rejected{0}, tile_labels{0};
bool ram(uint32_t p, size_t size) { return p>=0x02000000 && p<0x02400000 && size<=0x02400000-p; }
uint8_t read8(uint32_t p) { return bus_debug_read8(9,p); }
uint16_t read16(uint32_t p) { return read8(p)|(uint16_t(read8(p+1))<<8); }
uint32_t read32(uint32_t p) { return read16(p)|(uint32_t(read16(p+2))<<16); }
void write8(uint32_t p,uint8_t v) { bus_write_u8_slow(p,v); }
void write16(uint32_t p,uint16_t v) { write8(p,v);write8(p+1,v>>8); }
GlyphAdvance advance(const std::shared_ptr<const LocalizationPack>& p) {
    return [p](char32_t c)->std::optional<uint16_t> { auto g=p->glyph(c);if(!g)return {};
        if(host::vector_text_enabled()) return host::system_glyph_advance(c);
        return g->advance; };
}
void decline(const std::string& why) {
    if(rejected++<40)std::fprintf(stderr,"[native-text] declined: %s\n",why.c_str());
}
void begin_page() {
    const auto dialog=g_cpu.R[0], cursor=g_cpu.R[2], length=g_cpu.R[3];
    if(!ram(dialog,0x284)||!ram(cursor,length)||!length||length>65536)return;
    auto pack=runtime_localization();
    if(!pack || !pack->retail_codepoint(1))return;
    auto old=sessions.find(dialog);
    if(old!=sessions.end() && cursor>=old->second.base &&
       cursor-old->second.base<old->second.text->source_bytes.size() &&
       length==old->second.text->source_bytes.size()-(cursor-old->second.base)) {
        const auto offset=cursor-old->second.base;
        bool same=true;
        for(size_t i=0;i<length;++i)
            if(read8(cursor+i)!=old->second.text->source_bytes[offset+i]) {same=false;break;}
        if(same) {old->second.offset=offset;return;}
    }
    sessions.erase(dialog);
    const LocalizedText* found=nullptr;
    for(const auto& item:pack->texts()) {
        const auto& t=item.second;
        if(t.source_bytes.size()!=length)continue;
        bool same=true;
        for(size_t i=0;i<length;i++)if(read8(cursor+i)!=t.source_bytes[i]){same=false;break;}
        if(same) {
            if(found && found->utf8!=t.utf8){decline("ambiguous original text");return;}
            found=&t;
        }
    }
    if(!found)return;
    Session session;session.base=cursor;session.pack=pack;session.text=found;
    std::string error;
    if(!prepare_unicode_layout(*found,advance(pack),session.layout,error)){decline(found->id+": "+error);return;}
    sessions[dialog]=std::move(session);++bound;
    std::fprintf(stderr,"[native-text] bound %s dialog=%08x source=%08x bytes=%u\n",found->id.c_str(),dialog,cursor,length);
}
bool menu_session(const std::shared_ptr<const LocalizationPack>& pack,
                  const std::string& original, Session& session) {
    static std::shared_ptr<const LocalizationPack> indexed;
    static std::map<std::string,const LocalizedText*> index;
    if(indexed!=pack) {
        index.clear();indexed=pack;
        for(const auto& item:pack->texts()) {
            const auto& text=item.second;
            if(text.id.rfind("message:0:",0)!=0 || text.source_bytes.empty())continue;
            // Index original visible line slots, never translated control tokens.
            // Only the known newline and terminator controls are accepted here.
            std::vector<std::string> lines;std::string line;bool valid=true;
            for(size_t i=0;i<text.source_bytes.size();++i) {
                const auto code=text.source_bytes[i];
                if(code>=0xc0) {
                    if(i+1>=text.source_bytes.size() || text.source_bytes[i+1] || (code!=0xc0 && code!=0xc1 && code!=0xc2)) {valid=false;break;}
                    ++i;line+=char(0);lines.push_back(line);line.clear();
                } else if(!code) {line+=char(0);lines.push_back(line);line.clear();}
                else line+=char(code);
            }
            if(!valid)continue;
            if(!line.empty()){line+=char(0);lines.push_back(line);}
            for(auto& key:lines) {
                if(key.size()<=1)continue;
                auto entry=index.find(key);
                if(entry==index.end())index.emplace(std::move(key),&text);
                else if(entry->second && entry->second->utf8!=text.utf8)entry->second=nullptr;
                else if(entry->second && text.id<entry->second->id)entry->second=&text;
            }
        }
    }
    auto found=index.find(original);
    if(found==index.end() || !found->second)return false;
    session.pack=pack;session.text=found->second;
    std::string error;
    if(!prepare_unicode_layout(*session.text,advance(pack),session.layout,error)) {
        decline(session.text->id+": "+error);return false;
    }
    return true;
}
std::optional<Pending> plan_object_texture(uint32_t object,uint32_t source) {
    if(!ram(object,0x158)||!ram(source,1)||read32(object+0x11c)!=source)return {};
    auto pack=runtime_localization();
    if(!pack || !pack->retail_codepoint(1))return {};
    std::u32string actual;std::string original;
    for(unsigned i=0;i<256;i++) {
        if(!ram(source+i,1))return {};
        auto code=read8(source+i);original+=char(code);if(!code)break;
        auto cp=pack->retail_codepoint(code);
        if(!cp)return {};
        actual+=char32_t(cp);
        if(i==255){decline("unterminated original line");return {};}
    }
    Session session;
    auto parent=read32(object+0x120);auto it=sessions.find(parent);
    if(it!=sessions.end())session=it->second;
    else if(!menu_session(pack,original,session))return {};
    Pending p;p.session=session;p.object=object;p.source=source;std::string error;
    if(!find_unicode_line(session.layout,session.offset,actual,advance(session.pack),p.line,error)) {
        decline(session.text->id+": "+error);return {};
    }
    return p;
}
void prepare_object_texture(uint32_t object,uint32_t source) {
    pending.erase(object);active.erase(object);host::remove_text_owner(object);
    auto plan=plan_object_texture(object,source);
    if(plan)pending[object]=std::move(*plan);
}

void prepare_texture() {
    if(g_cpu.R[1]>=0x14)prepare_object_texture(g_cpu.R[1]-0x14,g_cpu.R[0]);
}
void prepare_list_texture() {
    uint32_t object=0;bool right_column=false;
    if(g_cpu.R[14]==0x02051710)object=g_cpu.R[7];
    else if(g_cpu.R[14]==0x02051744) {object=g_cpu.R[8];right_column=true;}
    if(!object || !ram(object,0x158) || read32(object+0x14)!=g_cpu.R[0])return;
    const uint32_t list=g_cpu.R[10];
    auto gap=list_gaps.find(list);
    if(!ram(list,0x820)||read32(object+0x120)!=list)return;
    const int window_x=int16_t(read16(list+0x10));
    const int window_right=window_x+read16(list+0x14);
    const int left=window_x+16+(read32(list+0x67c)==2?6:0);
    int edge=window_right-(read8(list+0x68d)<read8(list+0x68c)?18:8);
    if(gap!=list_gaps.end())edge-=gap->second;
    // A snapshot can predate host ownership. Recover the original right-column
    // anchor from the guest object instead of trusting a stale host pointer map.
    const uint32_t right_object=g_cpu.R[8];
    if(gap==list_gaps.end() && right_object && ram(right_object,0x158)) {
        const int original_edge=int16_t(read16(right_object+0xa))+read8(right_object+0x127);
        if(original_edge>=left && original_edge<=edge)edge=original_edge;
        else return;
    }
    if(left<0||edge>256||left>=edge)return;
    int right_x=edge;
    const uint32_t other=g_cpu.R[8];
    if(!right_column && other && ram(other,0x158)) {
        auto prepared=plan_object_texture(other,read32(other+0x11c));
        const int width=prepared?prepared->line.width:read8(other+0x127);
        right_x=edge-width;
    }
    prepare_object_texture(object,g_cpu.R[1]);
    auto entry=pending.find(object);
    if(entry==pending.end())return;
    auto& plan=entry->second;
    plan.left=left;
    plan.right=right_column?std::min(window_right,edge+4):right_x-(other?4:0);
    if(right_column)plan.align_edge=edge;
}

// Generic menu widgets use a compact owner distinct from dialogue objects.
void prepare_widget_texture() {
    const uint32_t object=g_cpu.R[4],source=g_cpu.R[1];
    if(!ram(object,0x28) || read32(object+0x20)!=source)return;
    const uint32_t texture=g_cpu.R[0];
    widget_pending.erase(texture);widget_active.erase(texture);host::remove_text_owner(0x10000000u|texture);
    auto pack=runtime_localization();if(!pack)return;
    std::string original;std::u32string actual;
    for(unsigned i=0;i<256;++i) {
        if(!ram(source+i,1))return;
        auto code=read8(source+i);original+=char(code);
        if(!code)break;
        if(code==0xc2 && ram(source+i+1,1) && !read8(source+i+1)) {original.back()=char(0);break;}
        auto cp=pack->retail_codepoint(code);
        if(code>=0xc0 || !cp)return;
        actual+=char32_t(cp);
    }
    if(original.empty() || original.back()!=0)return;
    Session session;if(!menu_session(pack,original,session))return;
    Pending plan;plan.object=object;plan.source=source;plan.session=session;
    std::string error;
    if(!find_unicode_line(session.layout,0,actual,advance(pack),plan.line,error))return;
    const int x=int16_t(read16(object+0xc));
    const unsigned width=read16(object+0x10);
    if(x<0 || x+plan.line.width+2>256 || (width && plan.line.width+2>width))return;
    plan.left=int(g_cpu.R[0]); // Original owned texture allocation, not a RAM pointer.
    plan.align_edge=int((read32(object+8)>>24)&3);
    widget_pending[texture]=std::move(plan);
}
void replace_upload(uint32_t staging,uint32_t texture,uint32_t capacity) {
    for(auto it=widget_pending.begin();it!=widget_pending.end();++it) {
        auto& p=it->second;
        if(uint32_t(p.left)!=texture)continue;
        if(!ram(staging,capacity) || capacity>61*64 || p.line.glyphs.size()>capacity/64 || read32(p.object+0x20)!=p.source) {
            widget_pending.erase(it);return;
        }
        for(unsigned i=0;i<capacity;++i)write8(staging+i,0);
        std::fprintf(stderr,"[native-widget] rendered %s owner=%08x texture=%08x width=%u\n",p.line.stable_id.c_str(),p.object,texture,p.line.width);
        widget_active[texture]=p;widget_pending.erase(it);return;
    }

    for(auto it=pending.begin();it!=pending.end();++it) {
        auto& p=it->second;const auto object=p.object;
        if(!ram(object,0x158)||read32(object+0x14)!=texture)continue;
        auto count=p.line.glyphs.size();
        if(!ram(staging,capacity)||capacity>61*64||count>capacity/64||
           read32(object+0x11c)!=p.source) {decline("texture allocation bound/lifetime");pending.erase(it);return;}
        std::vector<uint16_t> old;
        for(unsigned n=0;n<62;n++) {auto flags=read16(object+0x26+n*4);if(!(flags&0x8000))break;old.push_back(flags);}
        if(old.empty()||old.size()>61){decline("invalid original descriptors");pending.erase(it);return;}
        const auto align=read32(object+0x148)&7;
        int x=int16_t(read16(object+0xa));
        unsigned old_width=read8(object+0x127);
        if(align==1)x+=int(old_width/2)-int(p.line.width/2);
        else if(align==2)x+=int(old_width)-int(p.line.width);
        if(p.align_edge>=0)x=p.align_edge-p.line.width;
        if(x<p.left || x+int(p.line.width)+4>p.right){decline(p.line.stable_id+": line x="+std::to_string(x)+" width="+std::to_string(p.line.width)+" outside "+std::to_string(p.left)+".."+std::to_string(p.right));pending.erase(it);return;}
        // Replace only the allocation owned by the original upload queue.
        // The original script bytes, CPU code, allocator and freeing path stay intact.
        for(unsigned i=0;i<capacity;i++)write8(staging+i,0);
        for(unsigned i=0;i<0xf8;i++)write8(object+0x24+i,0);
        for(size_t n=0;n<count;n++) {
            const auto& placed=p.line.glyphs[n];const auto* glyph=p.session.pack->glyph(placed.codepoint);
            for(unsigned b=0;b<64;b++)write8(staging+n*64+b,host::vector_text_enabled()?0:glyph->pixels_2bpp[b]);
            auto flags=old[std::min(old.size()-1,n*old.size()/count)];
            write8(object+0x24+n*4,uint8_t(placed.x));
            write16(object+0x26+n*4,flags);
        }
        write8(object+0x127,uint8_t(p.line.width));write16(object+0xa,uint16_t(x));
        if(host::vector_text_enabled()) active[object]=p;
        ++rendered;
        std::fprintf(stderr,"[native-text] rendered %s page=%zu line=%zu glyphs=%zu width=%u object=%08x texture=%08x\n",p.line.stable_id.c_str(),p.line.page_index,p.line.line_index,count,p.line.width,object,texture);
        pending.erase(it);return;
    }
}
void prepare_tile_text() {
    const uint32_t object=g_cpu.R[0],source=g_cpu.R[3];
    tile_plans.erase(object);host::remove_tile_text(object);
    if(!host::vector_text_enabled() || !ram(object,0x3a0) || read32(object+0xc)!=3)return;
    const unsigned count=read8(object+0x274);
    if(!count || count>61 || !ram(source,count))return;
    std::string original;std::u32string actual;
    auto pack=runtime_localization();if(!pack)return;
    for(unsigned i=0;i<count;++i) {
        const auto code=read8(source+i);const auto cp=pack->retail_codepoint(code);
        if(!code || code>=0xc0 || !cp)return;
        // Mixed inline palettes need per-run shaping, not one flat label color.
        if(read32(object+0x278+i*4)!=read32(object+0x278))return;
        original+=char(code);actual+=char32_t(cp);
    }
    original+=char(0);Session session;
    if(!menu_session(pack,original,session))return;
    Pending plan;plan.object=object;plan.source=source;plan.session=session;
    std::string error;
    const GlyphAdvance ui_advance=[pack](char32_t c)->std::optional<uint16_t> {
        const auto width=host::system_glyph_advance(c);
        if(!pack->glyph(c)||!width)return {};
        return uint16_t((*width*11+11)/12);
    };
    if(!find_unicode_line(session.layout,0,actual,ui_advance,plan.line,error))return;
    const int width=read8(object+0x370)*8-(int16_t(read16(object+0x10))&7);
    if(int(plan.line.width)+2>width){decline(session.text->id+": tile label allocation too narrow");return;}
    tile_plans[object]=std::move(plan);
}
void bind_tile_text(uint32_t object) {
    auto it=tile_plans.find(object);if(it==tile_plans.end() || !ram(object,0x3a0))return;
    host::TileText text;text.owner=object;
    text.bg=read32(object+0x388);text.palette_group=read32(object+0x384);
    text.x=int16_t(read16(object+0x10));text.y=int16_t(read16(object+0x12));
    text.columns=read8(object+0x370);
    if(text.bg>3 || text.palette_group>=64 || !text.columns || text.columns>32 || read8(object+0x371)!=2)return;
    for(unsigned row=0;row<2;++row) {
        text.map_offsets[row]=read32(object+0x374+row*4);
        text.tiles[row]=read16(object+0x37c+row*2);
        if(text.map_offsets[row]+text.columns*2>2048 || text.tiles[row]+text.columns>1024)return;
    }
    for(const auto& glyph:it->second.line.glyphs)
        text.glyphs.push_back({glyph.codepoint,float(glyph.x),0,0,0,11});
    host::set_tile_text(std::move(text));
}
void draw_native_text(uint32_t object) {
    auto it=active.find(object);
    if(it==active.end() || !ram(object,0x158))return;
    const auto& p=it->second;
    if(read32(object+0x11c)!=p.source) { active.erase(it);host::remove_text_owner(object);return; }
    if(!(read8(object+0x20)&1) || read32(object+0x1c)) {host::remove_text_owner(object);return;}
    host::TextDraw draw;draw.owner=object;
    draw.screen=(read16(0x04000304)&0x8000)?0:1;
    const int x=int16_t(read16(object+0xa)),y=int16_t(read16(object+0xc));
    const unsigned alpha=read8(object+0x126)&31;
    for(size_t n=0;n<p.line.glyphs.size();++n) {
        auto flags=read16(object+0x26+n*4);
        if(!(flags&0x8000)||(flags&1023))continue;
        const unsigned palette=(flags>>10)&31;
        // TEXPLTT_BASE uses 8-byte units for the original 2bpp texture.
        // Each serialized palette contains 16 colors (32 bytes), so the
        // descriptor's palette field is a four-color offset, not a palette ID.
        const unsigned first=palette*4;
        if(first+3>=80)continue;
        auto modulation=read16(object+0x124);
        auto rgba=[&](unsigned role) {
            auto color=p.session.pack->palettes()[(first+role)/16][(first+role)%16];
            auto component=[&](unsigned shift) {
                return (((color>>shift)&31)*((modulation>>shift)&31)*255)/(31*31);
            };
            return uint32_t((alpha*255/31)<<24 | component(0)<<16 | component(5)<<8 | component(10));
        };
        draw.glyphs.push_back({p.line.glyphs[n].codepoint,float(x+read8(object+0x24+n*4)),float(y),rgba(3),rgba(1)});
    }
    host::submit_text(std::move(draw));
}
}
// Resolve menu coordinates from submitted geometry, after guest matrix/viewport
// transforms. Scratch widget positions are local and are reused across list rows.
void ffta2_text_publish_widgets() {
    if(widget_active.empty())return;
    struct Geometry {int x=256,y=192,right=0,bottom=0;uint32_t palette=0,alpha=0;};
    std::map<uint32_t,Geometry> geometry;
    const uint32_t count=nds_gpu3d_render_polygon_count();
    for(uint32_t i=0;i<count;++i) {
        NdsGpu3dPolygonSnapshot polygon{};
        if(!nds_gpu3d_render_polygon(i,&polygon) || ((polygon.tex_param>>26)&7)!=2)continue;
        const uint32_t texture=(polygon.tex_param&65535)*8;
        if(!widget_active.count(texture))continue;
        auto& g=geometry[texture];
        g.x=std::min(g.x,polygon.min_x);g.y=std::min(g.y,polygon.min_y);
        g.right=std::max(g.right,polygon.max_x);g.bottom=std::max(g.bottom,polygon.max_y);
        g.palette=polygon.tex_palette;g.alpha=(polygon.attr>>16)&31;
    }
    if(geometry.empty())return;
    std::array<uint8_t,128*1024> palette{};nds_vram_copy_texpal(palette.data());
    const char* fallback=std::getenv("FFTA2_BITMAP_FALLBACK");
    const bool pixel=!host::vector_text_enabled() || !fallback || std::string(fallback)!="0";
    for(const auto& item:geometry) {
        const auto& p=widget_active.at(item.first);const auto& g=item.second;
        if(g.y<0 || g.y>=192 || g.x<0 || g.x+int(p.line.width)+2>256 || g.bottom-g.y!=16 || g.palette*8+8>palette.size())continue;
        auto rgba=[&](unsigned role) {
            const unsigned at=g.palette*8+role*2;
            const uint16_t color=palette[at]|uint16_t(palette[at+1])<<8;
            return uint32_t((g.alpha*255/31)<<24 | ((color&31)*255/31)<<16 | (((color>>5)&31)*255/31)<<8 | ((color>>10)&31)*255/31);
        };
        host::TextDraw draw;draw.screen=(read16(0x04000304)&0x8000)?0:1;
        for(const auto& glyph:p.line.glyphs) {
            host::TextGlyph placed{glyph.codepoint,float(g.x+glyph.x),float(g.y),rgba(3),rgba(1)};
            placed.pixel=pixel;
            if(pixel){placed.bitmap=p.session.pack->glyph(glyph.codepoint)->pixels_2bpp;placed.shadow=rgba(2);}
            draw.glyphs.push_back(std::move(placed));
        }
        host::submit_text(std::move(draw));
    }
}
void ffta2_text_reset() { sessions.clear();list_gaps.clear();pending.clear();active.clear();tile_plans.clear();widget_pending.clear();widget_active.clear();ffta2::host::reset_tile_text();ffta2::host::clear_text_frames(); }
void ffta2_text_entry(uint32_t pc) {
    if(g_nds_active!=NDS_ARM9)return;
    if(pc==0x020A18AC) {
        if(read32(pc)==0xe92d4038 && ram(g_cpu.R[1],4) && (g_cpu.R[0]==1 || g_cpu.R[0]==8)) {
            const auto texture=read32(g_cpu.R[1]);
            widget_pending.erase(texture);widget_active.erase(texture);host::remove_text_owner(0x10000000u|texture);
        }
        return;
    }
    if(pc==0x02056924) {if(read32(pc)==0xe92d4ff0)prepare_tile_text();return;}
    if(pc==0x0208586C) {if(read32(pc)==0xe5912000)bind_tile_text(g_cpu.R[0]);return;}
    if(pc==0x020530B0 || pc==0x02052FDC) {
        const uint32_t expected=pc==0x020530B0?0xe92d43f8:0xe92d4ff8;
        if(read32(pc)==expected) {tile_plans.erase(g_cpu.R[0]);host::remove_tile_text(g_cpu.R[0]);}
        return;
    }
    // Observe the separate SUB background text path without changing tile
    // ownership, scrolling or GPU window/priority rules.
    if(pc==0x02083600) {
        if(g_cpu.R[14]==0x02056F58)bind_tile_text(g_cpu.R[9]);
        return;
    }
    if(pc==0x020835AC) {
        if(g_cpu.R[14]==0x02056F8C || g_cpu.R[14]==0x02056F08)bind_tile_text(g_cpu.R[9]);
        // D500's synchronous upload has the same owned staging allocation as
        // its queued A1678 path, but takes source/size in r2/r3.
        if(read32(pc)==0xe92d4038 && g_cpu.R[14]==0x0204D658)
            replace_upload(g_cpu.R[2],g_cpu.R[1],g_cpu.R[3]);
        return;
    }
    if(pc==0x02056FBC) {
        const auto config=g_cpu.R[0];
        if(read32(pc)!=0xe92d4ff0 || !ram(config,0x28))return;
        const auto source=read32(config+8);
        if(!ram(source,256))return;
        std::string original;
        for(unsigned i=0;i<256;++i) {
            const auto c=read8(source+i);original+=char(c);
            if(!c)break;
        }
        if(original.back()!=0)return;
        auto pack=runtime_localization();Session session;
        if(pack && menu_session(pack,original,session)) {
            if(tile_labels++<80)
                std::fprintf(stderr,"[native-ui] matched SUB BG label %s x=%d y=%d w=%u h=%u bg=%u\n",
                    session.text->id.c_str(),int16_t(read16(config)),int16_t(read16(config+2)),
                    read16(config+4),read16(config+6),read32(config+0x18));
        }
        return;
    }
    if(pc==0x0205179C) {
        if(read32(pc)==0xe92d000f && ram(g_cpu.R[0],0x820))
            list_gaps[g_cpu.R[0]]=uint8_t(g_cpu.R[3]>>8);
        return;
    }
    if(pc==0x020A2DC8) {
        const auto object=g_cpu.R[0];
        if(read32(pc)==0xe92d4ff8 && ram(object,0x84))
            replace_title_texture(read32(object+0x34),g_cpu.R[2]);
        return;
    }
    if(pc==0x020A3634) {
        const auto object=g_cpu.R[0];
        if(read32(pc)==0xe92d4ff8 && ram(object,0x84) &&
           read16(object+2)==256 && read16(object+4)==233)
            replace_title_texture(g_cpu.R[1],59648);
        return;
    }
    // Pinned ARM prologues also guard interpreted entries against replaced code.
    uint32_t expected=pc==0x0204D500?0xe92d4ff8:pc==0x0204B494?0xe92d4ff0:pc==0x0204D778?0xe92d4ff8:pc==0x0204C0B8?0xe92d40f8:
        pc==0x0204C0F8?0xe92d4070:pc==0x020A1678?0xe92d4008:0xe92d4010;
    if(read32(pc)!=expected)return;
    if(pc==0x0204B494)draw_native_text(g_cpu.R[0]);
    else if(pc==0x0204D778)begin_page();
    else if(pc==0x0204D500) {
        if(g_cpu.R[14]==0x020B02D4 || g_cpu.R[14]==0x020B0398)prepare_widget_texture();
        prepare_list_texture();
    }
    else if(pc==0x0204C0B8||pc==0x0204C0F8)prepare_texture();
    else if(pc==0x020A1678 && g_cpu.R[14]==0x0204D680)
        replace_upload(g_cpu.R[0],g_cpu.R[1],g_cpu.R[2]);
    else if(pc==0x0204BDB4) { pending.erase(g_cpu.R[0]);active.erase(g_cpu.R[0]);host::remove_text_owner(g_cpu.R[0]); }
}
std::string ffta2_text_status_json() {
    return "{\"native_tile_objects\":"+std::to_string(tile_plans.size())+",\"registered_tiles\":"+std::to_string(ffta2::host::tile_texts()->size())+",\"bound_texts\":"+std::to_string(bound.load())+",\"rendered_lines\":"+std::to_string(rendered.load())+",\"rejected_lines\":"+std::to_string(rejected.load())+",\"matched_tile_labels\":"+std::to_string(tile_labels.load())+"}";
}

namespace {
// Explicit little-endian format: never persist pointers or C++ object layouts.
struct TextStateCodec {
    std::vector<uint8_t> data;
    size_t at=0;
    bool reading=false;
    void number(uint32_t& value) {
        if(reading) {
            if(at+4>data.size())throw std::runtime_error("truncated native text state");
            value=0;for(unsigned i=0;i<4;++i)value|=uint32_t(data[at++])<<(i*8);
        } else for(unsigned i=0;i<4;++i)data.push_back(uint8_t(value>>(i*8)));
    }
    void string(std::string& value) {
        uint32_t n=uint32_t(value.size());number(n);
        if(n>1048576)throw std::runtime_error("native text string too large");
        if(reading) {
            if(n>data.size()-at)throw std::runtime_error("truncated native text string");
            value.assign(reinterpret_cast<const char*>(data.data()+at),n);at+=n;
        } else data.insert(data.end(),value.begin(),value.end());
    }
    void session(Session& value) {
        number(value.base);number(value.offset);
        std::string id,translation,source;
        if(!reading) {id=value.text->id;translation=value.text->utf8;source=value.text->source_utf8;}
        string(id);string(translation);string(source);
        if(reading) {
            value.pack=runtime_localization();
            value.text=value.pack?value.pack->text(id):nullptr;
            std::string error;
            if(!value.text || value.text->utf8!=translation || value.text->source_utf8!=source ||
               !prepare_unicode_layout(*value.text,advance(value.pack),value.layout,error))
                throw std::runtime_error("savestate localization differs: "+id);
        }
    }
    void plan(Pending& value) {
        session(value.session);number(value.object);number(value.source);
        auto signed_number=[&](int& v){uint32_t n=uint32_t(v);number(n);v=int32_t(n);};
        signed_number(value.left);signed_number(value.right);signed_number(value.align_edge);
        string(value.line.stable_id);
        uint32_t page=value.line.page_index,line=value.line.line_index,width=value.line.width;
        number(page);number(line);number(width);
        value.line.page_index=page;value.line.line_index=line;value.line.width=uint16_t(width);
        uint32_t count=value.line.glyphs.size();number(count);
        if(count>61 || width>255 || !ram(value.object,0x158) || !ram(value.source,1))
            throw std::runtime_error("invalid native text geometry");
        if(reading)value.line.glyphs.resize(count);
        for(auto& glyph:value.line.glyphs) {
            uint32_t cp=glyph.codepoint,x=glyph.x,a=glyph.advance;
            number(cp);number(x);number(a);
            if(cp>0x10ffff || (cp>=0xd800&&cp<=0xdfff) || x>255 || a>32 || !a || !value.session.pack->glyph(cp))
                throw std::runtime_error("invalid native text glyph");
            glyph={char32_t(cp),uint16_t(x),uint16_t(a)};
        }
    }
    void frame(std::vector<host::TextDraw>& draws,bool bitmap_fields=true) {
        uint32_t count=draws.size();number(count);
        if(count>4096)throw std::runtime_error("native frame draw limit exceeded");
        if(reading)draws.resize(count);
        for(auto& draw:draws) {
            uint32_t screen=draw.screen,glyph_count=draw.glyphs.size();
            number(screen);number(draw.owner);number(glyph_count);
            if(screen>1 || glyph_count>61 || (draw.owner && !ram(draw.owner,1) &&
               (draw.owner<0x10000000 || draw.owner>=0x10080000)))
                throw std::runtime_error("invalid native frame owner");
            draw.screen=int(screen);
            if(reading)draw.glyphs.resize(glyph_count);
            for(auto& glyph:draw.glyphs) {
                uint32_t cp=glyph.codepoint;
                number(cp);number(glyph.color);number(glyph.outline);
                if(!runtime_localization() || !runtime_localization()->glyph(cp))
                    throw std::runtime_error("invalid native frame glyph");
                glyph.codepoint=char32_t(cp);
                auto fixed=[&](float& v,int minimum,int maximum) {
                    uint32_t n=reading?0:uint32_t(int32_t(v*256));number(n);
                    if(int32_t(n)<minimum*256 || int32_t(n)>maximum*256)
                        throw std::runtime_error("invalid native frame coordinate");
                    v=float(int32_t(n))/256;
                };
                fixed(glyph.x,-512,768);fixed(glyph.y,-512,768);fixed(glyph.em,4,32);
                if(bitmap_fields) {
                    uint32_t pixel=glyph.pixel;number(pixel);number(glyph.shadow);
                    if(pixel>1)throw std::runtime_error("invalid bitmap mode");
                    glyph.pixel=bool(pixel);
                    if(pixel)for(auto& b:glyph.bitmap){uint32_t n=b;number(n);if(n>255)throw std::runtime_error("invalid bitmap byte");b=uint8_t(n);}
                }
            }
            std::string mask;
            if(!reading)mask.assign(draw.clip.begin(),draw.clip.end());
            string(mask);
            if(!mask.empty() && mask.size()!=256*192)throw std::runtime_error("invalid native frame clip");
            if(reading)draw.clip.assign(mask.begin(),mask.end());
        }
    }
    template<class T,class F> void map(std::map<uint32_t,T>& values,F item,bool texture_keys=false) {
        uint32_t count=values.size();number(count);
        if(count>4096)throw std::runtime_error("native text object limit exceeded");
        if(reading) {
            for(uint32_t i=0;i<count;++i) {
                uint32_t key=0;number(key);T value{};item(value);
                if((texture_keys ? key>=0x80000 : !ram(key,1))||!values.emplace(key,std::move(value)).second)
                    throw std::runtime_error("invalid native text owner");
            }
        } else for(auto& entry:values){uint32_t key=entry.first;number(key);item(entry.second);}
    }
};
}
std::vector<uint8_t> ffta2_text_export_state() {
    TextStateCodec codec;
    uint32_t version=5,vector=ffta2::host::vector_text_enabled();codec.number(version);codec.number(vector);
    codec.map(sessions,[&](Session& s){codec.session(s);});
    codec.map(pending,[&](Pending& p){codec.plan(p);});
    codec.map(active,[&](Pending& p){codec.plan(p);});
    codec.map(list_gaps,[&](uint8_t& g){uint32_t n=g;codec.number(n);});
    codec.map(tile_plans,[&](Pending& p){codec.plan(p);});
    codec.map(widget_pending,[&](Pending& p){codec.plan(p);},true);
    codec.map(widget_active,[&](Pending& p){codec.plan(p);},true);
    auto frame=host::snapshot_text_frame();codec.frame(frame);
    return std::move(codec.data);
}
bool ffta2_text_import_state(const std::vector<uint8_t>& data,bool commit,std::string* error) {
    try {
        // Legacy snapshots predate the host layer and have no recoverable glyphs.
        if(data.empty()) {if(commit)ffta2_text_reset();return true;}
        if(data.size()>8*1024*1024)throw std::runtime_error("native text state too large");
        TextStateCodec codec;codec.reading=true;codec.data=data;
        uint32_t version=0,vector=0;codec.number(version);codec.number(vector);
        if((version<1 || version>5) || vector!=uint32_t(ffta2::host::vector_text_enabled()))
            throw std::runtime_error("savestate native font mode differs");
        decltype(sessions) restored_sessions;
        decltype(pending) restored_pending,restored_active,restored_tiles,restored_widget_pending,restored_widget_active;
        decltype(list_gaps) restored_gaps;
        codec.map(restored_sessions,[&](Session& s){codec.session(s);});
        codec.map(restored_pending,[&](Pending& p){codec.plan(p);});
        codec.map(restored_active,[&](Pending& p){codec.plan(p);});
        codec.map(restored_gaps,[&](uint8_t& g){uint32_t n=0;codec.number(n);if(n>255)throw std::runtime_error("invalid list gap");g=uint8_t(n);});
        if(version>=2)codec.map(restored_tiles,[&](Pending& p){codec.plan(p);});
        if(version>=3) {
            codec.map(restored_widget_pending,[&](Pending& p){codec.plan(p);},true);
            codec.map(restored_widget_active,[&](Pending& p){codec.plan(p);},true);
        }
        std::vector<host::TextDraw> restored_frame;
        if(version>=4)codec.frame(restored_frame,version>=5);
        if(codec.at!=data.size())throw std::runtime_error("trailing native text data");
        if(commit) {
            ffta2_text_reset();sessions=std::move(restored_sessions);pending=std::move(restored_pending);
            active=std::move(restored_active);list_gaps=std::move(restored_gaps);
            tile_plans=std::move(restored_tiles);widget_pending=std::move(restored_widget_pending);widget_active=std::move(restored_widget_active);
            for(const auto& entry:tile_plans)bind_tile_text(entry.first);
            std::vector<uint32_t> owners;for(const auto& entry:active)owners.push_back(entry.first);
            for(auto owner:owners)draw_native_text(owner);
            ffta2::host::publish_text_frame();
            if(version>=4)host::restore_text_frame(std::move(restored_frame));
        }
        return true;
    } catch(const std::exception& e) {if(error)*error=e.what();return false;}
}
