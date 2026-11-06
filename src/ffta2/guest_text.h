// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <string>
inline bool ffta2_text_entry_pc(uint32_t pc) {
    return pc == 0x020835AC || pc == 0x02056FBC || pc == 0x0205179C || pc == 0x0204D500 || pc == 0x020A2DC8 || pc == 0x020A3634 || pc == 0x0204D778 || pc == 0x0204C0B8 || pc == 0x0204C0F8 ||
           pc == 0x0204B494 || pc == 0x020A1678 || pc == 0x0204BDB4;
}
void ffta2_text_entry(uint32_t pc);

std::string ffta2_text_status_json();

void ffta2_text_reset();

#include <vector>
// Snapshot payload belongs to the core transaction, including asynchronous saves.
std::vector<uint8_t> ffta2_text_export_state();
bool ffta2_text_import_state(const std::vector<uint8_t>& data, bool commit, std::string* error);
