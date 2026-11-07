// SPDX-License-Identifier: GPL-3.0-or-later
#include "host/font.h"
#include "host/text_layer.h"
#include "host/tile_text.h"
#include "host/display_options.h"
#include <cassert>
#include <cstdlib>
#include <algorithm>
#include <cmath>
namespace {
void set_environment(const char* key,const char* value) {
#ifdef _WIN32
    _putenv_s(key,value);
#else
    setenv(key,value,1);
#endif
}
}
int main() {
    set_environment("FFTA2_FONT","system");
    auto font=ffta2::host::make_system_font();
    ffta2::host::GlyphCoverage small,large;
    assert(font->rasterize(U'暑',12,small));
    assert(font->rasterize(U'暑',48,large));
    assert(large.width==small.width*4);
    auto ink_top=[](const ffta2::host::GlyphCoverage& glyph) {
        for(unsigned y=0;y<glyph.height;++y)
            for(unsigned x=0;x<glyph.width;++x)
                if(glyph.alpha[y*glyph.width+x]>127)return y;
        return glyph.height;
    };
    // Retina scaling must not shift the baseline back to the top of the cell.
    assert(ink_top(small)>=2 && ink_top(small)<=5);
    assert(std::abs(int(ink_top(large))-int(ink_top(small)*4))<=4);
    assert(ffta2::host::system_glyph_advance(U'暑')==12);
    unsigned name_width=0;
    for(char32_t c:U"Luso") if(c)name_width+=*ffta2::host::system_glyph_advance(c);
    assert(name_width>19 && name_width<40); // Retail widths crowded the vector name.

    assert(std::any_of(large.alpha.begin(),large.alpha.end(),[](auto a){return a>0&&a<255;}));
    assert(!font->rasterize(0xd800,48,large));
    assert(!font->rasterize(U'A',0,large));
    ffta2::host::submit_text({1,{{U'暑',20,30,0xffffffff}}});
    ffta2::host::publish_text_frame();
    assert(ffta2::host::render_text_layer(0,1024,768).empty());
    auto layer=ffta2::host::render_text_layer(1,1024,768);
    assert(layer.size()==1024*768);
    assert(std::any_of(layer.begin(),layer.end(),[](auto p){return p>>24;}));
    ffta2::host::publish_text_frame();
    assert(ffta2::host::render_text_layer(1,1024,768).empty());
    ffta2::host::submit_text({1,{{U'暑',20,30,0xffffffff}},0x02001234});
    ffta2::host::publish_text_frame();
    ffta2::host::publish_text_frame(); // Reused menu geometry must retain text.
    assert(!ffta2::host::render_text_layer(1,1024,768).empty());
    ffta2::host::remove_text_owner(0x02001234);
    assert(ffta2::host::render_text_layer(1,1024,768).empty());
    // Native tile text is clipped by GPU visibility at logical-pixel bounds.
    ffta2::host::TileText tile;tile.owner=0x02001234;tile.glyphs={{U'暑',0,0,0xffffffff}};
    ffta2::host::set_tile_text(tile);
    auto bindings=ffta2::host::tile_texts();assert(bindings->size()==1);
    for(int y=30;y<46;++y) {
        ffta2::host::TileTextSlice slice;slice.text=bindings->front();slice.x=20;slice.y=30;
        slice.color=0xffffffff;slice.outline=0xff000000;
        for(int x=20;x<26;++x)slice.visible[x]=255;
        ffta2::host::tile_text_scanline(1,y,{slice});
    }
    ffta2::host::publish_tile_text();ffta2::host::publish_text_frame();
    auto clipped=ffta2::host::render_text_layer(1,1024,768);
    assert(std::any_of(clipped.begin(),clipped.end(),[](auto p){return p>>24;}));
    for(int y=0;y<768;++y)for(int x=0;x<1024;++x)
        if(x<80||x>=104||y<120||y>=184)assert(clipped[y*1024+x]==0);
    auto saved=ffta2::host::snapshot_text_frame();
    ffta2::host::clear_text_frames();
    assert(ffta2::host::render_text_layer(1,1024,768).empty());
    ffta2::host::restore_text_frame(saved);
    assert(ffta2::host::render_text_layer(1,1024,768)==clipped);
    ffta2::host::publish_tile_text();ffta2::host::publish_text_frame();
    assert(ffta2::host::render_text_layer(1,1024,768).empty());
    ffta2::host::remove_tile_text(tile.owner);
    assert(ffta2::host::tile_texts()->empty());
    assert(bindings->size()==1); // In-flight renderer snapshots retain their owner.
    ffta2::host::clear_text_frames();
    ffta2::host::TextGlyph pixel{U'暑',0,0,0xffff0000,0xff00ff00};
    pixel.pixel=true;pixel.shadow=0xff0000ff;pixel.bitmap[0]=1|(2<<2)|(3<<4);
    ffta2::host::submit_text({0,{pixel}});ffta2::host::publish_text_frame();
    auto bitmap=ffta2::host::render_text_layer(0,1024,768);
    assert(bitmap[0]==0xff00ff00 && bitmap[4]==0xff0000ff && bitmap[8]==0xffff0000);
    assert(bitmap[3]==bitmap[0] && bitmap[12]==0); // Exact nearest-neighbor roles.
    auto bitmap_state=ffta2::host::snapshot_text_frame();ffta2::host::clear_text_frames();
    ffta2::host::restore_text_frame(bitmap_state);
    assert(ffta2::host::render_text_layer(0,1024,768)==bitmap);
    set_environment("FFTA2_LCD","0.4");
    auto mask=ffta2::host::lcd_mask(1024,768);
    assert(mask.size()==1024*768);
    assert(mask[0]!=mask[2*1024+2]);
    assert(ffta2::host::lcd_mask(256,192).empty());
    set_environment("FFTA2_LCD","nan");
    assert(ffta2::host::lcd_mask(1024,768).empty());
}
