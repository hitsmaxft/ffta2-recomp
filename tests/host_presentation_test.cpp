// SPDX-License-Identifier: GPL-3.0-or-later
#include "host/font.h"
#include "host/text_layer.h"
#include "host/display_options.h"
#include <cassert>
#include <cstdlib>
#include <algorithm>
#include <cmath>
int main() {
    setenv("FFTA2_FONT","system",1);
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
    setenv("FFTA2_LCD","0.4",1);
    auto mask=ffta2::host::lcd_mask(1024,768);
    assert(mask.size()==1024*768);
    assert(mask[0]!=mask[2*1024+2]);
    assert(ffta2::host::lcd_mask(256,192).empty());
    setenv("FFTA2_LCD","nan",1);
    assert(ffta2::host::lcd_mask(1024,768).empty());
}
