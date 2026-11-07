// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace ffta2::host {
std::array<uint8_t,32> sha256(const void* data, size_t size);
}
