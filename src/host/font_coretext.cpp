// SPDX-License-Identifier: GPL-3.0-or-later
#include "font.h"
#include <CoreText/CoreText.h>
#include <CoreGraphics/CoreGraphics.h>
#include <cmath>
namespace ffta2::host {
namespace {
class CoreTextFont final : public Font {
public:
    bool rasterize(char32_t cp, float size, GlyphCoverage& output) const override {
        if (cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ||
            !std::isfinite(size) || size < 4 || size > 256) return false;
        CTFontRef base = CTFontCreateWithName(CFSTR("PingFangSC-Regular"), size, nullptr);
        if (!base) return false;
        UniChar units[2]; CFIndex count = 1;
        if (cp <= 0xffff) units[0] = cp;
        else { cp -= 0x10000; units[0] = 0xd800 + (cp >> 10); units[1] = 0xdc00 + (cp & 1023); count = 2; }
        CFStringRef string = CFStringCreateWithCharacters(nullptr, units, count);
        CTFontRef font = CTFontCreateForString(base, string, CFRangeMake(0, count));
        CFRelease(string); CFRelease(base);
        if (!font) return false;
        CGGlyph glyphs[2] = {};
        bool valid = CTFontGetGlyphsForCharacters(font, units, glyphs, count);
        if (!valid || !glyphs[0]) { CFRelease(font); return false; }
        CGSize advance;
        CTFontGetAdvancesForGlyphs(font, kCTFontOrientationHorizontal, glyphs, &advance, 1);
        GlyphCoverage result;
        result.width = result.height = unsigned(std::ceil(size + size/3));
        result.advance = advance.width;
        result.alpha.resize(result.width * result.height);
        CGContextRef context = CGBitmapContextCreate(result.alpha.data(), result.width,
            result.height, 8, result.width, nullptr, kCGImageAlphaOnly);
        if (!context) { CFRelease(font); return false; }
        CGContextSetShouldAntialias(context, true);
        CGContextSetGrayFillColor(context, 1, 1);
        // The title's 16-pixel line cell has its baseline at y=14.
        // CoreGraphics uses a bottom-left baseline, whereas coverage rows are
        // presented top-down. Keep this contract at every output scale.
        CGPoint position = CGPointMake(size/12, result.height - size*14/12);
        CTFontDrawGlyphs(font, glyphs, &position, 1, context);
        CGContextRelease(context); CFRelease(font);
        output = std::move(result);
        return true;
    }
};
}
std::unique_ptr<Font> make_system_font() { return std::make_unique<CoreTextFont>(); }
}
