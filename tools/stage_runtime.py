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
    adapted_names={'runner/CMakeLists.txt','runner/src/main.cpp','runner/src/live_overlay.cpp','runner/src/live_overlay_platform.cpp','runner/src/debug_server.cpp','tools/compile_live_shards.py','runner/src/runtime_arm.cpp','runner/src/tier3.cpp','runner/src/frontend.cpp','runner/src/gpu2d.cpp'}
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
        text = '#include "ffta2/localization_runtime.h"\n#include "ffta2/guest_text.h"\n' + text
        token = '    std::string cmd = json_str(line, "cmd");'
        if text.count(token) != 1: raise ValueError('Localization debug handler guard failed')
        return text.replace(token, token + '\n    if (cmd == "localization_render_stats") return ffta2_text_status_json();\n    if (cmd == "localization_info") return ffta2::localization_info_json();\n    if (cmd == "localization_reload") return ffta2::reload_localization_json();')
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
        return text.replace(load, load + '\n        if (ok && cmd == "state_load") ffta2_text_reset();')
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
    adapt('runner/src/frontend.cpp',hd_frontend)
    def hd_frames(text):
        token='void nds_gpu2d_finish_frame(){'
        if text.count(token)!=1: raise ValueError('Native text frame boundary guard failed')
        return '#include "host/text_layer.h"\n'+text.replace(token,token+'\n    ffta2::host::publish_text_frame();')
    adapt('runner/src/gpu2d.cpp',hd_frames)

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
