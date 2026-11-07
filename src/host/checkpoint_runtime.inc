// SPDX-License-Identifier: GPL-3.0-or-later
// Included by the staged savestate.cpp: reuse its capture/validation transaction.
#include "host/checkpoint.h"
namespace ffta2::host {
namespace {
struct Checkpoint { NdsSavestateIdentity identity; CoreState core; };
std::unique_ptr<Checkpoint> checkpoints[4];
bool valid_slot(unsigned slot, std::string* error) {
    if (slot < 4) return true;
    set_error(error,"Memory checkpoint slot must be 0..3");return false;
}
}
bool save_checkpoint(unsigned slot,const NdsSavestateIdentity& identity,std::string* error) {
    if (!valid_slot(slot,error))return false;
    if (checkpoints[slot]) {set_error(error,"Memory checkpoint is occupied; drop it explicitly");return false;}
    auto captured=std::make_unique<Checkpoint>();captured->identity=identity;
    if (!capture_core(identity,&captured->core,error))return false;
    checkpoints[slot]=std::move(captured);return true;
}
bool load_checkpoint(unsigned slot,const NdsSavestateIdentity& identity,std::string* error) {
    if (!valid_slot(slot,error))return false;
    if (!checkpoints[slot]) {set_error(error,"Memory checkpoint is empty");return false;}
    const auto& saved=*checkpoints[slot];
    if (saved.identity.build_id!=identity.build_id || saved.identity.rom_sha1!=identity.rom_sha1) {
        set_error(error,"Memory checkpoint identity mismatch");return false;
    }
    nds_savestate_wait_for_pending_save();
    TransactionGuard transaction;
    if (!transaction.locked) {set_error(error,"Checkpoint requires scheduler owner between rounds");return false;}
    if (!transaction_allowed(error) || !validate_core_state(saved.core,error))return false;
    auto loaded=std::make_unique<CoreState>(saved.core);
    loaded->peripherals.backup_persistence_detached=1;
    loaded->peripherals.firmware_persistence_detached=1;
    auto previous=std::make_unique<CoreState>();
    if (!export_core_state(previous.get(),error))return false;
    if (!import_core_state(*loaded,error)) {
        const std::string primary=error?*error:std::string{};std::string rollback;
        if (!import_core_state(*previous,&rollback)) {if(error)*error=primary+"; rollback failed: "+rollback;}
        else if(error)*error=primary;
        return false;
    }
    return true;
}
bool drop_checkpoint(unsigned slot,std::string* error) {
    if (!valid_slot(slot,error))return false;
    checkpoints[slot].reset();return true;
}
}
