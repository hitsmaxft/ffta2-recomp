// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>
namespace ffta2::host {
std::string request_presentation_capture(const std::string& path);
std::string presentation_capture_status();
std::string take_presentation_capture();
void finish_presentation_capture(bool ok,const std::string& error);
}
