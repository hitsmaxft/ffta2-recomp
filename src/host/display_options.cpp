// SPDX-License-Identifier: GPL-3.0-or-later
#include "display_options.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
namespace ffta2::host {
int initial_window_scale() {
    const char* value=std::getenv("FFTA2_WINDOW_SCALE");
    if(!value)return 3;
    char* end=nullptr;long scale=std::strtol(value,&end,10);
    return end && !*end && scale>=1 && scale<=8 ? int(scale) : 3;
}
bool lcd_includes_text() {
    const char* value=std::getenv("FFTA2_LCD_TEXT");
    return value && std::strcmp(value,"1")==0;
}
std::vector<uint32_t> lcd_mask(unsigned width,unsigned height) {
    const char* value=std::getenv("FFTA2_LCD");
    if(!value||!width||!height||width>4096||height>3072)return {};
    char* end=nullptr;float strength=std::strtof(value,&end);
    if(!end||*end||!std::isfinite(strength)||strength<=0||strength>1)return {};
    float sx=float(width)/256,sy=float(height)/192;
    if(sx<2||sy<2)return {}; // No moire grid below useful pixel magnification.
    std::vector<uint32_t> result(size_t(width)*height);
    for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x) {
        float fx=std::fmod(float(x)+0.5f,sx),fy=std::fmod(float(y)+0.5f,sy);
        float edge=std::max(std::max(0.f,1.f-fx),std::max(0.f,1.f-fy));
        unsigned alpha=unsigned(std::lround(strength*255*edge));
        result[size_t(y)*width+x]=alpha<<24;
    }
    return result;
}
}
