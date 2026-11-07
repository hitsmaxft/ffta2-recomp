// SPDX-License-Identifier: GPL-3.0-or-later
#include "localization_runtime.h"
#include "host/digest.h"
#include <cstdio>

namespace ffta2 {
namespace {
LocalizationStore store;
std::string pack_directory, rom_identity;
std::string quote(const std::string& value) {
    std::string result = "\"";
    for (unsigned char c : value) {
        if (c == '\\' || c == '"') { result += '\\'; result += char(c); }
        else if (c < 32) { char escaped[7]; std::snprintf(escaped, sizeof escaped, "\\u%04x", c); result += escaped; }
        else result += char(c);
    }
    return result + '"';
}
}
bool initialize_localization(const std::string& directory, const uint8_t* rom,
                             size_t rom_size, std::string& error) {
    if (directory.empty()) return true;
    if (!rom || !rom_size || rom_size > UINT32_MAX) {
        error = "Localization requires the original ROM"; return false;
    }
    const auto digest=host::sha256(rom,rom_size);
    constexpr char hex[] = "0123456789abcdef";
    std::string identity;
    for (unsigned char c : digest) { identity += hex[c >> 4]; identity += hex[c & 15]; }
    if (!store.reload(directory, identity, error)) return false;
    pack_directory = directory; rom_identity = identity;
    auto pack = store.snapshot();
    std::fprintf(stderr, "[ffta2-localization] External pack: %zu texts, %zu glyphs, 5 palettes; ROM unchanged\n",
                 pack->text_count(), pack->glyph_count());
    return true;
}
std::shared_ptr<const LocalizationPack> runtime_localization() { return store.snapshot(); }
std::string localization_info_json() {
    auto pack = store.snapshot();
    if (!pack) return "{\"enabled\":false,\"game_render_hook\":false}";
    return "{\"enabled\":true,\"integrity_verified\":true,\"texts\":" +
        std::to_string(pack->text_count()) + ",\"glyphs\":" + std::to_string(pack->glyph_count()) +
        ",\"palettes\":5,\"rom_sha256\":" + quote(pack->source_rom_sha256()) +
        ",\"game_render_hook\":" + std::string(pack->retail_codepoint(1) ? "true" : "false") + "}";
}
std::string reload_localization_json() {
    if (pack_directory.empty()) return "{\"error\":\"No --localization pack configured\"}";
    std::string error;
    if (!store.reload(pack_directory, rom_identity, error)) return "{\"error\":" + quote(error) + ",\"previous_pack_retained\":true}";
    return localization_info_json();
}
}
