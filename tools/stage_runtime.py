#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage pinned runtime sources with explicit Darwin/FreeBIOS-only adaptations.
Never edits the submodule or its other users. Build copies are disposable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

PIN='54967a4e26bcd6ad46445d51bab3214decc3fd59'

def stage(source,output):
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=PIN:raise ValueError('Unsupported framework revision')
    if output==source or source in output.parents:raise ValueError('Stage must be outside the submodule')
    names=subprocess.check_output(['git','-C',str(source),'ls-files','-z','--recurse-submodules']).decode().split('\0')
    adapted_names={'runner/CMakeLists.txt','runner/src/main.cpp','runner/src/live_overlay.cpp','runner/src/live_overlay_platform.cpp','runner/src/debug_server.cpp','tools/compile_live_shards.py','runner/src/runtime_arm.cpp','runner/src/tier3.cpp','runner/src/frontend.cpp','runner/src/gpu2d.cpp','runner/src/savestate.cpp'}
    for name in names:
        if not name or name in adapted_names:continue
        old=source/name;new=output/name
        if not old.is_file():continue
        new.parent.mkdir(parents=True,exist_ok=True)
        if not new.exists() or old.read_bytes()!=new.read_bytes():shutil.copy2(old,new)
    # The pinned header is an upstream downloaded dependency, not a game payload.
    header=source/'recompiler/third_party/toml.hpp'
    if header.exists():
        dest=output/'recompiler/third_party/toml.hpp';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(header,dest)
    edits=[]
    def adapt(name,transform):
        path=output/name;before=(source/name).read_text();after=transform(before)
        if before==after:raise ValueError('Expected adaptation absent: '+name)
        if not path.exists() or path.read_text()!=after:path.write_text(after)
        edits.append(dict(path=name,source_sha256=hashlib.sha256(before.encode()).hexdigest(),adapted_sha256=hashlib.sha256(after.encode()).hexdigest()))
    def cmake(text):
        for name in ('arm9_bios.c','arm9_bios_dispatch.c','arm7_bios.c','arm7_bios_dispatch.c'):
            token='${GEN}/'+name
            if text.count(token)!=3:raise ValueError('BIOS source list guard failed: '+name)
            text=text.replace(token,'')
        return text
    adapt('runner/CMakeLists.txt',cmake)
    def main(text):
        old='''            nds_register_dispatch(NDS_ARM9, g_dispatch_arm9_bios,
                                  g_dispatch_arm9_bios_len, 0xFFFF0000u);
            nds_register_dispatch(NDS_ARM7, g_dispatch_arm7_bios,
                                  g_dispatch_arm7_bios_len, 0x00000000u);'''
        if text.count(old)!=1:raise ValueError('BIOS registration guard failed')
        text = text.replace(old,'''            std::fprintf(stderr, "This FFTA2 build requires --freebios and --boot direct\\n");
            std::exit(2);''')
        text = '#include "ffta2/localization_runtime.h"\n' + text
        text = text.replace('    std::string rom_path;', '    std::string rom_path;\n    std::string ffta2_localization_directory;', 1)
        text = text.replace('        } else if (a == "--rom" && i + 1 < argc) {',
            '        } else if (a == "--localization" && i + 1 < argc) {\n            ffta2_localization_directory = argv[++i];\n        } else if (a == "--rom" && i + 1 < argc) {', 1)
        token = '    std::string rom_sha1;'
        if text.count(token) != 1: raise ValueError('ROM localization startup guard failed')
        text = text.replace(token, '''    std::string localization_error;
    if (!ffta2::initialize_localization(ffta2_localization_directory, rom.data(), rom.size(), localization_error)) {
        std::fprintf(stderr, "[ffta2-localization] %s\\n", localization_error.c_str());
        return 2;
    }
''' + token)
        return text
    adapt('runner/src/main.cpp',main)
    def posix(text):
        return text.replace('defined(__linux__)', '(defined(__linux__) || defined(__APPLE__))')
    adapt('runner/src/live_overlay.cpp',posix)
    def platform(text):
        text=posix(text)
        token='''#elif (defined(__linux__) || defined(__APPLE__))
    return ".so";'''
        if text.count(token)!=1:raise ValueError('Library suffix guard failed')
        return text.replace(token,'''#elif defined(__APPLE__)
    return ".dylib";
#elif defined(__linux__)
    return ".so";''')
    adapt('runner/src/live_overlay_platform.cpp',platform)
    def debug(text):
        old='#if defined(NDS_ARM9_DYNARMIC)\n#include "arm9_native.h"\n#endif'
        if text.count(old)!=1:raise ValueError('Native diagnostics include guard failed')
        text = text.replace(old,'#include "arm9_native.h"')
        text = '#include "host/presentation_capture.h"\n#include "ffta2/localization_runtime.h"\n#include "ffta2/guest_text.h"\n' + text
        token = '    std::string cmd = json_str(line, "cmd");'
        if text.count(token) != 1: raise ValueError('Localization debug handler guard failed')
        return text.replace(token, token + '\n    if (cmd == "presentation_capture") return ffta2::host::request_presentation_capture(json_str(line,"path"));\n    if (cmd == "presentation_capture_status") return ffta2::host::presentation_capture_status();\n    if (cmd == "localization_render_stats") return ffta2_text_status_json();\n    if (cmd == "localization_info") return ffta2::localization_info_json();\n    if (cmd == "localization_reload") return ffta2::reload_localization_json();')
    def hd_debug(text):
        text=debug(text)
        text='#include "host/text_layer.h"\n#include "host/display_options.h"\n'+text
        token='        std::string rgb;\n        rgb.reserve(size_t{width} * 192u * 6u);'
        if text.count(token)!=1: raise ValueError('Native capture guard failed')
        return text.replace(token,r'''        const unsigned scale=std::min<uint64_t>(8,std::max<uint64_t>(1,json_u64(line,"native_scale",1)));
        unsigned height=192;
        std::vector<uint32_t> composed;
        if(scale>1 || ffta2::host::vector_text_enabled()) {
            const unsigned old_width=width;
            width*=scale; height*=scale;
            composed.resize(size_t(width)*height);
            for(unsigned y=0;y<height;++y) for(unsigned x=0;x<width;++x)
                composed[size_t(y)*width+x]=fb[size_t(y/scale)*old_width+x/scale];
            auto blend_layer=[&](const std::vector<uint32_t>& layer) {
                if(layer.empty())return;
                for(size_t i=0;i<composed.size();++i) {
                    unsigned a=layer[i]>>24; uint32_t color=0xff000000;
                    for(unsigned shift:{0u,8u,16u}) color|=((((layer[i]>>shift)&255)*a+((composed[i]>>shift)&255)*(255-a))/255)<<shift;
                    composed[i]=color;
                }
            };
            auto mask=ffta2::host::lcd_mask(width,height);
            if(!ffta2::host::lcd_includes_text()) blend_layer(mask);
            blend_layer(ffta2::host::render_text_layer(screen,width,height));
            if(ffta2::host::lcd_includes_text()) blend_layer(mask);
            fb=composed.data();
        }
        std::string rgb;
        rgb.reserve(size_t{width} * height * 6u);''').replace('i < size_t{width} * 192u','i < size_t{width} * height').replace('\",\\\"h\\\":192,\\\"rgb\\\":\\\"\"','\",\\\"h\\\":\" + std::to_string(height) + ",\\\"rgb\\\":\\\"\"')
    def text_lifetime(text):
        text=hd_debug(text)
        reset = '        g_reset_fn();   // full power-on re-init (both cores from reset vectors)'
        if text.count(reset) != 1: raise ValueError('Text reset lifetime guard failed')
        text = text.replace(reset, '        ffta2_text_reset();\n' + reset)
        load = '            : nds_savestate_load_core(path, g_savestate_identity, &error);'
        if text.count(load) != 1: raise ValueError('Text snapshot lifetime guard failed')
        return text
    adapt('runner/src/debug_server.cpp',text_lifetime)
    def dispatch(text):
        token = '        if (entering_static) {\n            guard_scope.invoke();'
        if text.count(token) != 1: raise ValueError('Title dispatch hook guard failed')
        return '#include "ffta2/guest_text.h"\n' + text.replace(token, '        if (entering_static) {\n            if (ffta2_text_entry_pc(pc)) ffta2_text_entry(pc);\n            guard_scope.invoke();')
    adapt('runner/src/runtime_arm.cpp',dispatch)
    def tier3(text):
        token = '        // Only RAM-resident copied code belongs to Tier 3 (main RAM, WRAM,'
        if text.count(token) != 1: raise ValueError('Title interpreter hook guard failed')
        return '#include "ffta2/guest_text.h"\n' + text.replace(token, '        if (!covered && !thumb && ffta2_text_entry_pc(pc)) ffta2_text_entry(pc);\n' + token)
    adapt('runner/src/tier3.cpp',tier3)

    def hd_frontend(text):
        token = '    render_texture(renderer, source, &destination);'
        if text.count(token)!=1: raise ValueError('Native text presentation guard failed')
        text=text.replace("constexpr int kWindowScale = 2;", "const int kWindowScale = ffta2::host::initial_window_scale();")
        return '#include "host/text_layer.h"\n#include "host/display_options.h"\n' + text.replace(token, token + r'''
#if defined(NDS_HAVE_SDL3)
    {
        int output_w=0, output_h=0;
        SDL_GetRenderOutputSize(renderer,&output_w,&output_h);
        const float scale=std::min(float(output_w)/presentation.canvas_width,
                                  float(output_h)/(presentation.separate ? kScreenHeight : kScreenHeight*2));
        const unsigned width=std::max(1,int(std::lround(destination.w*scale)));
        const unsigned height=std::max(1,int(std::lround(destination.h*scale)));
        auto draw_layer=[&](const std::vector<uint32_t>& pixels) {
            if (pixels.empty()) return;
            SDL_Texture* layer=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,
                SDL_TEXTUREACCESS_STATIC,width,height);
            if (!layer) return;
            SDL_UpdateTexture(layer,nullptr,pixels.data(),width*4);
            SDL_SetTextureBlendMode(layer,SDL_BLENDMODE_BLEND);
            SDL_SetTextureScaleMode(layer,SDL_SCALEMODE_LINEAR);
            render_texture(renderer,layer,&destination);
            SDL_DestroyTexture(layer);
        };
        auto mask=ffta2::host::lcd_mask(width,height);
        if (!ffta2::host::lcd_includes_text()) draw_layer(mask);
        draw_layer(ffta2::host::render_text_layer(screen,width,height));
        if (ffta2::host::lcd_includes_text()) draw_layer(mask);
    }
#endif
''')
    def state_frontend(text):
        text=hd_frontend(text)
        text='#include "host/presentation_capture.h"\n'+text
        text=text.replace('void draw_savestate_notice(', r'''void capture_native_presentation(SDL_Renderer* renderer) {
#if defined(NDS_HAVE_SDL3)
    const auto path=ffta2::host::take_presentation_capture();
    if(path.empty())return;
    SDL_Surface* surface=SDL_RenderReadPixels(renderer,nullptr);
    const bool ok=surface && SDL_SaveBMP(surface,path.c_str());
    const std::string error=ok?std::string{}:SDL_GetError();
    if(surface)SDL_DestroySurface(surface);
    ffta2::host::finish_presentation_capture(ok,error);
#endif
}

void draw_savestate_notice(''',1)
        text=text.replace('SDL_RenderPresent(renderer);','capture_native_presentation(renderer);\n        SDL_RenderPresent(renderer);')
        def replace(old,new):
            nonlocal text
            if text.count(old)!=1: raise ValueError('State menu guard failed: '+old[:70])
            text=text.replace(old,new)
        replace('    bool close_requested = false;', '    bool close_requested = false;\n    int state_slot = 1;\n    std::array<std::string,12> slot_labels;\n    std::array<const char*,12> slot_choices{};')
        replace('bool save_runtime_mouse_sensitivity(', r'''void refresh_state_slots(RuntimeMenuState& state) {
    for(unsigned i=0;i<12;++i) {
        const auto meta=nds_savestate_slot_metadata(state.options->savestate_directory,i+1);
        state.slot_labels[i]=std::to_string(i+1)+" - ";
        if(!meta.exists) state.slot_labels[i]+="Empty";
        else {
            std::time_t time=meta.modified_unix_seconds;
            char date[32]{};std::tm local{};
#if defined(_WIN32)
            localtime_s(&local,&time);
#else
            localtime_r(&time,&local);
#endif
            std::strftime(date,sizeof(date),"%m-%d %H:%M",&local);
            state.slot_labels[i]+=date;
        }
        state.slot_choices[i]=state.slot_labels[i].c_str();
    }
}

bool save_runtime_mouse_sensitivity(''')
        replace('    if (!state || !state->options || !item || !value_out) return 0;', '    if (!state || !state->options || !item || !value_out) return 0;\n    if (std::strcmp(item->key,"system.state_slot")==0) {*value_out=state->state_slot;return 1;}')
        token='    if (!state || !state->options || !item) return 0;'
        # The setter and enabled callback share a guard; modify each function independently.
        begin=text.index('int runtime_menu_set_value(')
        end=text.index('int runtime_menu_run_action(',begin)
        part=text[begin:end].replace(token,token+'\n    if (std::strcmp(item->key,"system.state_slot")==0) {if(value<1||value>12)return 0;state->state_slot=value;return 1;}')
        text=text[:begin]+part+text[end:]
        replace('    if (!state || !item) return 0;', r'''    if (!state || !item) return 0;
    const bool save=std::strcmp(item->key,"system.save_state")==0;
    const bool load=std::strcmp(item->key,"system.load_state")==0;
    if(save || load) {
        // Queue the existing shortcut path so loads retain all renderer/input
        // invalidation and asynchronous saves retain the same completion rules.
        SDL_Event event{};event.type=SDL_KEYDOWN;
#if defined(NDS_HAVE_SDL3)
        event.key.scancode=static_cast<SDL_Scancode>(SDL_SCANCODE_F1+state->state_slot-1);
        event.key.mod=save?SDL_KMOD_SHIFT:SDL_KMOD_NONE;
#else
        event.key.keysym.scancode=static_cast<SDL_Scancode>(SDL_SCANCODE_F1+state->state_slot-1);
        event.key.keysym.mod=save?KMOD_SHIFT:KMOD_NONE;
#endif
        if(SDL_PushEvent(&event)<=0)return 0;
        state->close_requested=true;
        return 1;
    }''')
        begin=text.index('int runtime_menu_is_enabled(')
        end=text.index('void runtime_menu_save(',begin)
        part=text[begin:end].replace(token,token+\
            '\n    if (std::strcmp(item->key,"system.load_state")==0) return nds_savestate_slot_metadata(state->options->savestate_directory,state->state_slot).exists;')
        text=text[:begin]+part+text[end:]
        replace('    static const RecompRuntimeUiItem runtime_menu_items[] = {', r'''    refresh_state_slots(runtime_menu_state);
    const RecompRuntimeUiItem runtime_menu_items[] = {
        {"system.state_slot", "Instant saves", "Slot", "Choose a slot; timestamps use local time.",
         RECOMP_RUNTIME_UI_CHOICE, 1, 12, 1, runtime_menu_state.slot_choices.data(), 12, nullptr},
        {"system.save_state", "Instant saves", "Save current state", "Replaces the selected slot. Shift+F1..F12 also saves.",
         RECOMP_RUNTIME_UI_ACTION, 0, 0, 0, nullptr, 0, nullptr},
        {"system.load_state", "Instant saves", "Load selected state", "Restores game and native Chinese text. F1..F12 also loads.",
         RECOMP_RUNTIME_UI_ACTION, 0, 0, 0, nullptr, 0, nullptr},''')
        replace('                   const SDL_Rect& destination) {', '                   const SDL_Rect& destination, bool native_text = true) {')
        replace('        draw_layer(ffta2::host::render_text_layer(screen,width,height));', '        if (native_text) draw_layer(ffta2::host::render_text_layer(screen,width,height));')
        replace('        render_screen(presentation, 0, top_rect);', '        render_screen(presentation, 0, top_rect, !recomp_runtime_ui_is_open(runtime_ui));')
        replace('        render_screen(presentation, 1, screen_rect);', '        render_screen(presentation, 1, screen_rect, !recomp_runtime_ui_is_open(runtime_ui));')
        replace('        render_screen(presentation, screen, screen_rect);', '        render_screen(presentation, screen, screen_rect, screen != 0 || !recomp_runtime_ui_is_open(runtime_ui));')
        replace('    RuntimeMenuState runtime_menu_state{&options, &running, false};', '    RuntimeMenuState runtime_menu_state{};\n    runtime_menu_state.options=&options;runtime_menu_state.running=&running;')
        replace('            while (running && scheduler_system_timestamp() < next_frame &&', '            while (running && !runtime_menu_open() && scheduler_system_timestamp() < next_frame &&')
        replace('        if (!was_open && runtime_menu_open())\n            clear_gameplay_input_for_runtime_menu();', '        if (was_open != bool(runtime_menu_open())) {\n            if (audio) {pause_audio(audio,true);clear_audio_queue(audio,audio_queue);audio_queue.started.store(false,std::memory_order_relaxed); }\n            audio_started=false;\n        }\n        if (!was_open && runtime_menu_open()) {\n            refresh_state_slots(runtime_menu_state);\n            clear_gameplay_input_for_runtime_menu();\n        }')
        replace('runtime_menu_config.title = "Metroid Prime Hunters";', 'runtime_menu_config.title = "Final Fantasy Tactics A2";')
        return '#include <ctime>\n'+text
    adapt('runner/src/frontend.cpp',state_frontend)
    def hd_frames(text):
        def replace(old,new):
            nonlocal text
            if text.count(old)!=1: raise ValueError('Tile renderer guard failed: '+old[:70])
            text=text.replace(old,new)
        text='#include "host/text_layer.h"\n#include "host/tile_text.h"\n#include "ffta2/guest_text.h"\n'+text
        replace('void nds_gpu2d_finish_frame(){\n    drain_pool(NDS_GPU2D_FENCE_FRAME);', 'void nds_gpu2d_finish_frame(){\n    drain_pool(NDS_GPU2D_FENCE_FRAME);\n    ffta2::host::publish_tile_text();\n    ffta2_text_publish_widgets();\n    ffta2::host::publish_text_frame();')
        replace('void compose_line6(int engine, int y,', '#include "host/tile_text_gpu.inc"\n\nvoid compose_line6(int engine, int screen, int y,')
        replace('            compose_line6(engine, y,', '            compose_line6(engine, job.screen[engine], y,')
        replace('                       bg_lines[i]);\n    const uint8_t prio3d = static_cast<uint8_t>(u.bgcnt[0] & 3u);', '                       bg_lines[i]);\n    native_tile_line(engine,screen,y,u,palette,vram,bg_lines,bg_count,obj,obj_window.data());\n    const uint8_t prio3d = static_cast<uint8_t>(u.bgcnt[0] & 3u);')
        replace('    const uint32_t mbmode=u.master_bright>>14;', '    native_tile_line(engine,job.screen[engine],y,u,palette,vram,bg_lines,bg_count,obj,nullptr);\n    const uint32_t mbmode=u.master_bright>>14;')
        return text
    adapt('runner/src/gpu2d.cpp',hd_frames)

    def native_state(text):
        def replace(old,new):
            nonlocal text
            if text.count(old)!=1: raise ValueError('Native savestate guard failed: '+old[:70])
            text=text.replace(old,new)
        text='#include "ffta2/guest_text.h"\n'+text
        replace('count != kRequiredSections || count > kMaxSections ||', '(count != kRequiredSections && count != kRequiredSections+1) || count > kMaxSections ||')
        replace('struct CoreState {','struct CoreState {\n    std::vector<uint8_t> native_text;')
        replace('        tag == kSectionSpu;', '        tag == kSectionSpu || tag == 0x54585446u;')
        replace('    cp15_savestate_export(&out->cp15);','    out->native_text=ffta2_text_export_state();\n    cp15_savestate_export(&out->cp15);')
        replace('    bus_fast_refresh();','    if (!ffta2_text_import_state(state.native_text,true,error)) return false;\n    bus_fast_refresh();')
        replace('    const NdsBusMemorySnapshot& mem = state.memory;', '    if (!ffta2_text_import_state(state.native_text,false,error)) return false;\n    const NdsBusMemorySnapshot& mem = state.memory;')
        replace('    return atomic_write_file(path, build_file(sections), error);','    if (!append_section(sections,0x54585446u,core.native_text,error)) return false;\n    return atomic_write_file(path, build_file(sections), error);')
        replace('    // Historical mutable flash is session-local after load.', '    if (find_section(sections,0x54585446u,&payload)) loaded.native_text=payload;\n    // Historical mutable flash is session-local after load.')
        return text
    adapt('runner/src/savestate.cpp',native_state)

    def provider(text):
        old='".so" if sys.platform.startswith("linux") else "")'
        if text.count(old)!=1:raise ValueError('Provider suffix guard failed')
        text=text.replace(old,'".dylib" if sys.platform == "darwin" else\n    ".so" if sys.platform.startswith("linux") else "")')
        old='    return run(command).returncode == 0\n\n\ndef compile_page'
        if text.count(old)!=1:raise ValueError('Provider linker guard failed')
        return text.replace(old,'    if sys.platform == "darwin":\n        command.extend(["-Wl,-undefined,dynamic_lookup"])\n'+old)
    adapt('tools/compile_live_shards.py',provider)
    result=dict(schema_version=1,framework_commit=actual,adaptations=edits,retail_bios_banks=False,freebios_banks=True)
    (output/'ffta2-platform-adaptations.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    print(json.dumps(stage(a.source.resolve(),a.output.resolve()),indent=2))
