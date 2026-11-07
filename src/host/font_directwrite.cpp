// SPDX-License-Identifier: GPL-3.0-or-later
#include "font.h"
#include <windows.h>
#include <dwrite.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
namespace ffta2::host {
namespace {
template<class T> struct Release {void operator()(T* p)const {if(p)p->Release();}};
template<class T> using Com=std::unique_ptr<T,Release<T>>;
class DirectWriteFont final:public Font {
    Com<IDWriteFactory> factory;
    std::vector<Com<IDWriteFontFace>> faces;
public:
    DirectWriteFont() {
        IDWriteFactory* created=nullptr;
        if(FAILED(DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED,__uuidof(IDWriteFactory),
                                      reinterpret_cast<IUnknown**>(&created))))return;
        factory.reset(created);
        if(const char* path=std::getenv("FFTA2_FONT_FILE")) {
            IDWriteFontFile* file=nullptr;
            const auto wide=std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(path))).wstring();
            if(SUCCEEDED(factory->CreateFontFileReference(wide.c_str(),nullptr,&file))) {
                Com<IDWriteFontFile> owned(file);BOOL supported=FALSE;
                DWRITE_FONT_FILE_TYPE file_type;DWRITE_FONT_FACE_TYPE face_type;UINT32 count=0;
                if(SUCCEEDED(file->Analyze(&supported,&file_type,&face_type,&count)) && supported && count) {
                    IDWriteFontFace* face=nullptr;
                    if(SUCCEEDED(factory->CreateFontFace(face_type,1,&file,0,DWRITE_FONT_SIMULATIONS_NONE,&face)))
                        faces.emplace_back(face);
                }
            }
        }
        IDWriteFontCollection* collection=nullptr;
        if(FAILED(factory->GetSystemFontCollection(&collection)))return;
        Com<IDWriteFontCollection> owned(collection);
        for(const wchar_t* name:{L"Microsoft YaHei",L"DengXian",L"SimHei",L"Noto Sans CJK SC",
                                L"WenQuanYi Zen Hei",L"Yu Gothic",L"Segoe UI"}) {
            UINT32 index=0;BOOL exists=FALSE;
            if(FAILED(collection->FindFamilyName(name,&index,&exists)) || !exists)continue;
            IDWriteFontFamily* family=nullptr;
            if(FAILED(collection->GetFontFamily(index,&family)))continue;
            Com<IDWriteFontFamily> family_owned(family);IDWriteFont* font=nullptr;
            if(FAILED(family->GetFirstMatchingFont(DWRITE_FONT_WEIGHT_NORMAL,DWRITE_FONT_STRETCH_NORMAL,
                                                  DWRITE_FONT_STYLE_NORMAL,&font)))continue;
            Com<IDWriteFont> font_owned(font);IDWriteFontFace* face=nullptr;
            if(SUCCEEDED(font->CreateFontFace(&face)))faces.emplace_back(face);
        }
    }
    bool rasterize(char32_t cp,float size,GlyphCoverage& output)const override {
        if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff) || !std::isfinite(size) || size<4 || size>256 || !factory)return false;
        IDWriteFontFace* face=nullptr;UINT16 glyph=0;const UINT32 point=cp;
        for(const auto& candidate:faces) {
            if(SUCCEEDED(candidate->GetGlyphIndices(&point,1,&glyph)) && glyph){face=candidate.get();break;}
        }
        if(!face)return false;
        DWRITE_FONT_METRICS metrics{};face->GetMetrics(&metrics);
        DWRITE_GLYPH_METRICS glyph_metrics{};
        if(!metrics.designUnitsPerEm || FAILED(face->GetDesignGlyphMetrics(&glyph,1,&glyph_metrics)))return false;
        const FLOAT advance=size*glyph_metrics.advanceWidth/metrics.designUnitsPerEm;
        const DWRITE_GLYPH_OFFSET offset{};
        const DWRITE_GLYPH_RUN run{face,size,1,&glyph,&advance,&offset,FALSE,0};
        IDWriteGlyphRunAnalysis* analysis=nullptr;
        if(FAILED(factory->CreateGlyphRunAnalysis(&run,1,nullptr,DWRITE_RENDERING_MODE_NATURAL_SYMMETRIC,
            DWRITE_MEASURING_MODE_NATURAL,size/12,size*14/12,&analysis)))return false;
        Com<IDWriteGlyphRunAnalysis> owned(analysis);
        GlyphCoverage result;result.width=result.height=unsigned(std::ceil(size+size/3));result.advance=advance;
        const RECT bounds{0,0,LONG(result.width),LONG(result.height)};
        std::vector<BYTE> coverage(size_t(result.width)*result.height*3);
        if(FAILED(analysis->CreateAlphaTexture(DWRITE_TEXTURE_CLEARTYPE_3x1,&bounds,coverage.data(),UINT32(coverage.size()))))return false;
        result.alpha.resize(size_t(result.width)*result.height);
        for(size_t i=0;i<result.alpha.size();++i)
            result.alpha[i]=uint8_t((unsigned(coverage[i*3])+coverage[i*3+1]+coverage[i*3+2])/3);
        output=std::move(result);return true;
    }
};
}
std::unique_ptr<Font> make_system_font(){return std::make_unique<DirectWriteFont>();}
}
