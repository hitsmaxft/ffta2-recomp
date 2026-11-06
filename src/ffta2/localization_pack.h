// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace ffta2 {
struct LocalizedText {
    std::string id, utf8, source_utf8, status;
    uint32_t source_rom_offset = 0, source_byte_capacity = 0;
    std::vector<uint8_t> source_bytes;
    std::array<uint8_t, 32> source_sha256{};
    // Script tokens remain in utf8 in their original order and parameters.
    // A native text hook must parse them, never draw them as literal letters.
};
struct LocalizedGlyph {
    uint32_t codepoint = 0, index = 0;
    uint16_t advance = 0;
    std::array<uint8_t, 64> pixels_2bpp{}; // 16x16, row-major, LSB pixel first.
};
class LocalizationPack {
public:
    const LocalizedText* text(const std::string& stable_id) const;
    const LocalizedText* text_at_rom_offset(uint32_t offset) const;
    const LocalizedGlyph* glyph(uint32_t codepoint) const;
    const std::array<std::array<uint16_t, 16>, 5>& palettes() const { return palettes_; }
    size_t text_count() const { return texts_.size(); }
    size_t glyph_count() const { return glyphs_.size(); }
    const std::string& source_rom_sha256() const { return rom_sha256_; }
    bool integrity_verified() const { return verified_; }
private:
    friend class LocalizationStore;
    std::string rom_sha256_;
    bool verified_ = false;
    std::unordered_map<std::string, LocalizedText> texts_;
    std::unordered_map<uint32_t, std::string> offsets_;
    std::unordered_map<uint32_t, LocalizedGlyph> glyphs_;
    std::array<std::array<uint16_t, 16>, 5> palettes_{};
};
class LocalizationStore {
public:
    // Builds and verifies a complete candidate before publishing it. Errors
    // preserve the previous immutable snapshot. Existing readers remain valid.
    bool reload(const std::filesystem::path& directory,
                const std::string& expected_rom_sha256, std::string& error);
    std::shared_ptr<const LocalizationPack> snapshot() const;
private:
    std::shared_ptr<const LocalizationPack> current_;
};
} // namespace ffta2
