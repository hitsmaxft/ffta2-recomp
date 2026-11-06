// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <vector>
namespace ffta2::host {
int initial_window_scale();
bool lcd_includes_text();
std::vector<uint32_t> lcd_mask(unsigned width, unsigned height);
}
