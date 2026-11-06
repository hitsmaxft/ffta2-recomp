// SPDX-License-Identifier: GPL-3.0-or-later
#include "guest_texture.h"
#include "state.h"
#include <array>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>
namespace ffta2 {
namespace {
struct Replacement { std::vector<uint8_t> original, translated; };
std::vector<Replacement> load_replacements() {
    const char* path=std::getenv("FFTA2_TITLE_ASSETS");
    if(!path || !*path)return {};
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    if(!file || file.tellg()<16 || file.tellg()>1024*1024) {
        std::fprintf(stderr,"[title-assets] Invalid external package size\n");return {};
    }
    file.seekg(0);
    char magic[8];file.read(magic,8);
    const std::array<char,8> expected={'F','F','T','A','T','E','X','1'};
    if(!std::equal(expected.begin(),expected.end(),magic))return {};
    auto u32=[&]() { unsigned char b[4]={};file.read(reinterpret_cast<char*>(b),4);
        return uint32_t(b[0])|uint32_t(b[1])<<8|uint32_t(b[2])<<16|uint32_t(b[3])<<24; };
    if(u32()!=1 || u32()!=2)return {};
    std::vector<Replacement> result;
    for(unsigned i=0;i<2;++i) {
        auto size=u32(),offset=u32(),width=u32(),height=u32();
        if((size!=59648&&size!=65536)||offset!=0x03c427e0||width!=256||
           (height!=233&&height!=256)||size!=width*height) {
            std::fprintf(stderr,"[title-assets] Unsupported entry %u: size=%u offset=%08x dimensions=%ux%u\n",i,size,offset,width,height);return {};
        }
        Replacement replacement;
        replacement.original.resize(size);replacement.translated.resize(size);
        file.read(reinterpret_cast<char*>(replacement.original.data()),size);
        file.read(reinterpret_cast<char*>(replacement.translated.data()),size);
        if(!file)return {};
        result.push_back(std::move(replacement));
    }
    if(file.peek()!=std::char_traits<char>::eof())return {};
    std::fprintf(stderr,"[title-assets] Loaded exact-match external title atlas\n");
    return result;
}
}
void replace_title_texture(uint32_t source,uint32_t capacity) {
    if(capacity<59648 || capacity>1024*1024 || source<0x02000000 ||
       source>=0x02400000 || capacity>0x02400000-source)return;
    static const auto replacements=load_replacements();
    for(const auto& replacement:replacements) {
        if(replacement.original.size()>capacity)continue;
        bool match=true;
        for(size_t i=0;i<replacement.original.size();++i)
            if(bus_debug_read8(9,source+i)!=replacement.original[i]) {match=false;break;}
        if(!match)continue;
        for(size_t i=0;i<replacement.translated.size();++i)
            bus_write_u8_slow(source+i,replacement.translated[i]);
        std::fprintf(stderr,"[title-assets] Replaced %zu staging bytes at %08x; palette unchanged\n",
                     replacement.translated.size(),source);
        return;
    }
}
}
