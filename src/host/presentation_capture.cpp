// SPDX-License-Identifier: GPL-3.0-or-later
#include "presentation_capture.h"
#include <filesystem>
#include <mutex>
namespace ffta2::host {
namespace {
std::mutex mutex;
std::string requested;
bool pending=false,success=false;
std::string failure;
std::string quote(const std::string& s) {
    std::string out="\"";
    for(unsigned char c:s) {if(c=='"'||c=='\\')out+='\\';if(c>=32)out+=char(c);}
    return out+'"';
}
}
std::string request_presentation_capture(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex);
    if(pending)return "{\"error\":\"A presentation capture is pending\"}";
    const std::filesystem::path file(path);
    if(!file.is_absolute() || file.extension()!=".bmp")
        return "{\"error\":\"An absolute BMP output path is required\"}";
    std::error_code ec;
    if(std::filesystem::exists(file,ec) || ec)
        return "{\"error\":\"Capture output already exists or is inaccessible\"}";
    requested=path;pending=true;success=false;failure.clear();
    return "{\"queued\":true}";
}
std::string take_presentation_capture() {
    std::lock_guard<std::mutex> lock(mutex);
    std::string path;path.swap(requested);return path;
}
void finish_presentation_capture(bool ok,const std::string& error) {
    std::lock_guard<std::mutex> lock(mutex);pending=false;success=ok;failure=error;
}
std::string presentation_capture_status() {
    std::lock_guard<std::mutex> lock(mutex);
    return std::string("{\"pending\":")+(pending?"true":"false")+",\"success\":"+(success?"true":"false")+",\"error\":"+quote(failure)+"}";
}
}
