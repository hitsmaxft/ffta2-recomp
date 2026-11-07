// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>
struct NdsSavestateIdentity;
namespace ffta2::host {
// Scheduler-owner only. Bounded, owned machine snapshots; never raw RAM copies.
bool save_checkpoint(unsigned slot, const NdsSavestateIdentity&, std::string* error);
bool load_checkpoint(unsigned slot, const NdsSavestateIdentity&, std::string* error);
bool drop_checkpoint(unsigned slot, std::string* error);
}
