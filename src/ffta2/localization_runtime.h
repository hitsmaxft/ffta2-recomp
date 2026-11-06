// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "localization_pack.h"
#include <cstddef>
#include <cstdint>

namespace ffta2 {
// Called after the original ROM is loaded, before either guest CPU starts.
bool initialize_localization(const std::string& directory, const uint8_t* rom,
                             size_t rom_size, std::string& error);
std::shared_ptr<const LocalizationPack> runtime_localization();
// Debug requests execute on the guest-owning thread between scheduler slices.
std::string localization_info_json();
std::string reload_localization_json();
}
