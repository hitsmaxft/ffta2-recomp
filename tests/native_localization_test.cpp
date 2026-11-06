// SPDX-License-Identifier: GPL-3.0-or-later
#include "ffta2/localization_pack.h"
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) {
    if (argc != 2 && argc != 3) return 2;
    const std::string rom = "f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59";
    ffta2::LocalizationStore store;
    std::string error;
    if (!store.reload(argv[1], rom, error)) { std::cerr << error << '\n'; return 1; }
    auto original = store.snapshot();
    if (!original || !original->integrity_verified() || original->text_count() == 0 ||
        original->glyph_count() < 2613 || !original->glyph(U'中')) return 1;
    auto glyph = original->glyph(U'中');
    if (glyph->advance != 12) return 1;
    unsigned roles = 0;
    for (auto byte : glyph->pixels_2bpp) for (unsigned bit = 0; bit < 8; bit += 2)
        roles |= 1u << ((byte >> bit) & 3u);
    if (roles != 15) return 1; // Transparent, outline, shadow and foreground survive.
    if (store.reload(argv[1], std::string(64, '0'), error) || error.empty() || store.snapshot() != original) return 1;
    if (store.reload(std::filesystem::path(argv[1]) / "missing", rom, error) || store.snapshot() != original) return 1;
    if (argc == 3 && (store.reload(argv[2], rom, error) || store.snapshot() != original)) return 1;
    if (!store.reload(argv[1], rom, error) || store.snapshot() == original) return 1;
    // A reader holding an older snapshot can continue after atomic replacement.
    if (!original->glyph(U'中')) return 1;
    std::cout << "Loaded " << original->text_count() << " texts, " << original->glyph_count()
              << " glyphs; palette roles and atomic failed-reload retention passed\n";
}
