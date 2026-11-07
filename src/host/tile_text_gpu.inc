// SPDX-License-Identifier: GPL-3.0-or-later
// Included by the pinned GPU2D adapter after its decoder/window types.
// Original VRAM is never changed. Unsupported effects retain retail pixels.
void native_tile_line(int engine,int screen,int y,const Unit& u,
                      const uint8_t* palette,const NdsVramRendererView& vram,
                      std::array<BgLine,4>& lines,size_t count,
                      const std::array<Pixel,256>& obj,const uint8_t* obj_window) {
    using namespace ffta2::host;
    if(engine!=1 || !vector_text_enabled() || ((u.dispcnt>>16)&1u)!=1 ||
       (((u.bldcnt>>6)&3u)==1 || (((u.bldcnt>>6)&3u)>=2 && u.evy)) || (u.master_bright&0xc01fu))return;
    auto texts=tile_texts();
    if(texts->empty())return;
    std::vector<TileTextSlice> slices;
    std::array<std::array<bool,256>,4> erase{};
    const NdsGpu2dWindowState windows{u.dispcnt,u.win};
    for(const auto& text:*texts) {
        int layer=-1;
        for(size_t i=0;i<count;++i)if(lines[i].order==text->bg+1)layer=int(i);
        if(layer<0 || text->bg>3)continue;
        const unsigned bg=text->bg;
        const uint16_t cnt=u.bgcnt[bg];
        // Only the title's ordinary 256x256 4bpp text mode is owned here.
        if(bg_kind(u,bg)!=BgKind::Text || (cnt&0xc0c0u))continue;
        const unsigned sy=(u.bgy[bg]+y)&255;
        const unsigned map_base=(cnt&0x1f00u)<<3;
        const unsigned bank=text->palette_group>>2;
        const unsigned color_base=bank*32+(text->palette_group&3)*8;
        TileTextSlice slice;slice.text=text;
        slice.x=text->x-int(u.bgx[bg]&255);
        slice.y=text->y-int(u.bgy[bg]&255);
        // Match the wrapped image which actually intersects this scanline.
        while(slice.y+16<=y)slice.y+=256;
        while(slice.y>y)slice.y-=256;
        slice.color=0xff000000u|to_rgb32(rgb6(view16(palette,color_base+6)));
        slice.outline=0xff000000u|to_rgb32(rgb6(view16(palette,color_base+2)));
        bool any=false;
        for(int x=0;x<256;++x) {
            const unsigned sx=(u.bgx[bg]+x)&255;
            const unsigned offset=(sy/8*32+sx/8)*2;
            bool owned=false;
            for(unsigned row=0;row<2;++row) {
                if(offset<text->map_offsets[row])continue;
                const unsigned col=(offset-text->map_offsets[row])/2;
                if(col>=text->columns)continue;
                const uint16_t expected=(text->tiles[row]+col)|(bank<<12);
                if(bg_view16(vram,engine,map_base+offset)==expected)owned=true;
            }
            if(!owned)continue;
            erase[layer][x]=true;
            const unsigned mask=nds_gpu2d_window_mask(windows,uint8_t(x),uint8_t(y),obj_window&&obj_window[x]);
            if(!(mask&(1u<<bg)))continue;
            bool covered=obj[x].valid && (mask&0x10u) && obj[x].priority<=lines[layer].prio;
            for(size_t i=0;i<count&&!covered;++i) {
                if(int(i)==layer || !(mask&lines[i].target) || !(lines[i].color[x]&0x8000u))continue;
                covered=lines[i].prio<lines[layer].prio ||
                    (lines[i].prio==lines[layer].prio && lines[i].order<lines[layer].order);
            }
            if(!covered){slice.visible[x]=255;any=true;}
        }
        if(any)slices.push_back(std::move(slice));
    }
    for(size_t i=0;i<count;++i)for(unsigned x=0;x<256;++x)
        if(erase[i][x])lines[i].color[x]=0;
    tile_text_scanline(screen,y,std::move(slices));
}
