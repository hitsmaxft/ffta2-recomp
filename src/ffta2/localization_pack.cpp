// SPDX-License-Identifier: GPL-3.0-or-later
#include "localization_pack.h"
#include <CommonCrypto/CommonDigest.h>
#include <algorithm>
#include <atomic>
#include <fstream>
#include <iterator>
#include <regex>
#include <set>
#include <stdexcept>

namespace ffta2 {
namespace {
using Bytes = std::vector<uint8_t>;
const std::set<std::string> required_files = {"localization.bin", "translations.csv", "glyphs.csv",
    "font-2bpp.bin", "widths.bin", "palettes-bgr555.bin", "font-OFL.txt", "manifest.json"};
Bytes read(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw std::runtime_error("Cannot read pack file: " + path.filename().string());
    auto length = stream.tellg();
    if (length < 0 || length > 64 * 1024 * 1024) throw std::runtime_error("Pack file exceeds 64 MiB bound");
    Bytes bytes(static_cast<size_t>(length)); stream.seekg(0);
    if (!bytes.empty() && !stream.read(reinterpret_cast<char*>(bytes.data()), bytes.size()))
        throw std::runtime_error("Truncated pack read");
    return bytes;
}
std::array<uint8_t, 32> sha(const Bytes& bytes) {
    std::array<uint8_t, 32> result{};
    CC_SHA256(bytes.data(), static_cast<CC_LONG>(bytes.size()), result.data());
    return result;
}
std::string hex(const std::array<uint8_t, 32>& bytes) {
    std::string result; constexpr char digits[] = "0123456789abcdef";
    for (auto byte : bytes) { result += digits[byte >> 4]; result += digits[byte & 15]; }
    return result;
}
bool valid_utf8(const std::string& value) {
    size_t i = 0;
    while (i < value.size()) {
        auto c = static_cast<uint8_t>(value[i++]);
        if (c < 0x80) { if (!c) return false; continue; }
        unsigned n; uint32_t point, minimum;
        if (c >= 0xc2 && c <= 0xdf) { n = 1; point = c & 31; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { n = 2; point = c & 15; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { n = 3; point = c & 7; minimum = 0x10000; }
        else return false;
        if (i + n > value.size()) return false;
        for (unsigned k = 0; k < n; ++k) { auto t = static_cast<uint8_t>(value[i++]);
            if ((t & 0xc0) != 0x80) return false; point = (point << 6) | (t & 63); }
        if (point < minimum || point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff)) return false;
    }
    return true;
}
std::vector<std::string> controls(const std::string& text) {
    static const std::regex token(R"(\\[^\\\r\n]+\\|<unknown:[0-9A-Fa-f]+>)");
    std::vector<std::string> result;
    for (std::sregex_iterator i(text.begin(), text.end(), token), end; i != end; ++i) result.push_back(i->str());
    if (std::regex_replace(text, token, "").find('\\') != std::string::npos)
        throw std::runtime_error("Malformed script control token");
    return result;
}
struct Reader {
    const Bytes& bytes; size_t p = 0;
    Bytes take(size_t count) { if (count > bytes.size() - p) throw std::runtime_error("Truncated host pack");
        Bytes result(bytes.begin() + p, bytes.begin() + p + count); p += count; return result; }
    uint32_t u32() { auto b = take(4); return b[0] | (uint32_t(b[1]) << 8) | (uint32_t(b[2]) << 16) | (uint32_t(b[3]) << 24); }
    uint16_t u16() { auto b = take(2); return b[0] | (uint16_t(b[1]) << 8); }
    Bytes field() { auto n = u32(); if (n > 16 * 1024 * 1024) throw std::runtime_error("Host field too large"); return take(n); }
    std::string string() { auto b = field(); std::string s(b.begin(), b.end());
        if (!valid_utf8(s)) throw std::runtime_error("Invalid UTF-8 in host pack"); return s; }
};
} // namespace

const LocalizedText* LocalizationPack::text(const std::string& id) const {
    auto i = texts_.find(id); return i == texts_.end() ? nullptr : &i->second;
}
const LocalizedText* LocalizationPack::text_at_rom_offset(uint32_t offset) const {
    auto i = offsets_.find(offset); return i == offsets_.end() ? nullptr : text(i->second);
}
const LocalizedGlyph* LocalizationPack::glyph(uint32_t point) const {
    auto i = glyphs_.find(point); return i == glyphs_.end() ? nullptr : &i->second;
}
std::shared_ptr<const LocalizationPack> LocalizationStore::snapshot() const { return std::atomic_load(&current_); }

bool LocalizationStore::reload(const std::filesystem::path& directory,
                               const std::string& expected_rom_sha256, std::string& error) {
    try {
        if (!std::regex_match(expected_rom_sha256, std::regex("[0-9a-f]{64}")))
            throw std::runtime_error("Expected ROM SHA256 is required");
        const auto inventory = read(directory / "checksums.tsv");
        std::string lines(inventory.begin(), inventory.end());
        std::set<std::string> seen;
        Bytes blob;
        size_t pos = 0;
        while (pos < lines.size()) {
            auto end = lines.find('\n', pos); if (end == std::string::npos) throw std::runtime_error("Incomplete checksum row");
            auto line = lines.substr(pos, end - pos); pos = end + 1;
            if (line.size() < 66 || line[64] != '\t') throw std::runtime_error("Malformed checksum row");
            auto name = line.substr(65);
            if (!required_files.count(name) || !seen.insert(name).second) throw std::runtime_error("Unknown or duplicate pack file");
            auto bytes = read(directory / name);
            if (hex(sha(bytes)) != line.substr(0, 64)) throw std::runtime_error("File integrity mismatch: " + name);
            if (name == "localization.bin") blob = std::move(bytes);
        }
        if (seen != required_files) throw std::runtime_error("Missing required pack file");
        Reader r{blob}; auto magic = r.take(8);
        const auto version = r.u32();
        if (!((std::string(magic.begin(), magic.end()) == "FFTALOC1" && version == 1) ||
              (std::string(magic.begin(), magic.end()) == "FFTALOC2" && version == 2)))
            throw std::runtime_error("Unsupported host pack format");
        auto text_count = r.u32(), glyph_count = r.u32(), palette_count = r.u32();
        if (text_count > 200000 || glyph_count == 0 || glyph_count > 65536 || palette_count != 5)
            throw std::runtime_error("Invalid host pack counts");
        auto candidate = std::make_shared<LocalizationPack>();
        candidate->rom_sha256_ = r.string();
        if (candidate->rom_sha256_ != expected_rom_sha256) throw std::runtime_error("Localization ROM identity mismatch");
        for (uint32_t n = 0; n < text_count; ++n) {
            LocalizedText t; t.id = r.string(); t.utf8 = r.string(); t.source_utf8 = r.string(); t.status = r.string();
            if (!std::regex_match(t.id, std::regex("(event|message|questtext|uwasatext|freepapermes):[0-3]:[0-9]+:[0-9]+")) ||
                (t.status != "translated" && t.status != "review") || t.utf8.empty())
                throw std::runtime_error("Invalid text ID, status or value");
            t.source_rom_offset = r.u32(); t.source_byte_capacity = r.u32(); t.source_bytes = r.field();
            auto expected = r.take(32); std::copy(expected.begin(), expected.end(), t.source_sha256.begin());
            if (t.source_bytes.size() != t.source_byte_capacity || sha(t.source_bytes) != t.source_sha256 ||
                controls(t.utf8) != controls(t.source_utf8)) throw std::runtime_error("Source integrity or script control mismatch");
            // Aliased source offsets are allowed only for identical translations.
            auto old = candidate->offsets_.find(t.source_rom_offset);
            if (old != candidate->offsets_.end() && candidate->texts_.at(old->second).utf8 != t.utf8)
                throw std::runtime_error("Conflicting translations for aliased ROM source");
            candidate->offsets_.emplace(t.source_rom_offset, t.id);
            if (!candidate->texts_.emplace(t.id, std::move(t)).second) throw std::runtime_error("Duplicate stable text ID");
        }
        for (uint32_t n = 0; n < glyph_count; ++n) {
            LocalizedGlyph g; g.index = n; g.codepoint = r.u32(); g.advance = r.u16();
            if (r.u16() != 64 || !g.advance || g.advance > 32 || g.codepoint > 0x10ffff ||
                (g.codepoint >= 0xd800 && g.codepoint <= 0xdfff)) throw std::runtime_error("Invalid glyph record");
            auto pixels = r.take(64); std::copy(pixels.begin(), pixels.end(), g.pixels_2bpp.begin());
            if (!candidate->glyphs_.emplace(g.codepoint, g).second) throw std::runtime_error("Duplicate Unicode glyph");
        }
        for (auto& palette : candidate->palettes_) for (auto& color : palette) color = r.u16();
        if (version == 2) {
            for (auto& point : candidate->retail_cmap_) {
                point = r.u32();
                if (point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff))
                    throw std::runtime_error("Invalid retail character map");
            }
        }
        if (r.p != blob.size()) throw std::runtime_error("Trailing host pack bytes");
        static const std::regex token(R"(\\[^\\\r\n]+\\|<unknown:[0-9A-Fa-f]+>)");
        for (const auto& item : candidate->texts_) {
            const auto plain = std::regex_replace(item.second.utf8, token, "");
            for (size_t p = 0; p < plain.size();) {
                auto c = static_cast<uint8_t>(plain[p++]);
                if (c == '\n') continue;
                if (c < 32 || c == 127) throw std::runtime_error("Unsupported text layout control");
                uint32_t point = c; unsigned continuation = 0;
                if (c >= 0xf0) { point = c & 7; continuation = 3; }
                else if (c >= 0xe0) { point = c & 15; continuation = 2; }
                else if (c >= 0xc0) { point = c & 31; continuation = 1; }
                for (unsigned k = 0; k < continuation; ++k)
                    point = (point << 6) | (static_cast<uint8_t>(plain[p++]) & 63);
                if (!candidate->glyphs_.count(point))
                    throw std::runtime_error("Translation references a missing font glyph");
            }
        }
        candidate->verified_ = true;
        std::atomic_store(&current_, std::shared_ptr<const LocalizationPack>(std::move(candidate)));
        error.clear(); return true;
    } catch (const std::exception& exception) { error = exception.what(); return false; }
}
} // namespace ffta2
