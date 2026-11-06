// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>
namespace ffta2::host {
// Device-independent coverage. Presentation backends upload this as an alpha
// texture at their output scale; no game palette or ROM encoding lives here.
// A 12-pixel em occupies a 16-pixel cell with a baseline at row 14.
struct GlyphCoverage {
    unsigned width = 0, height = 0;
    float advance = 0;
    std::vector<uint8_t> alpha;
};
class Font {
public:
    virtual ~Font() = default;
    virtual bool rasterize(char32_t codepoint, float pixel_size,
                           GlyphCoverage& output) const = 0;
};
// Platform factory. Windows/Linux can supply DirectWrite/FreeType implementations.
std::unique_ptr<Font> make_system_font();
std::optional<uint16_t> system_glyph_advance(char32_t codepoint);
}
