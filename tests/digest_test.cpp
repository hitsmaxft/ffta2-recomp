// SPDX-License-Identifier: GPL-3.0-or-later
#include "host/digest.h"
#include <cassert>
#include <string>
std::string hash(const std::string& input) {
    constexpr char digits[]="0123456789abcdef";std::string out;
    for(auto b:ffta2::host::sha256(input.data(),input.size())){out+=digits[b>>4];out+=digits[b&15];}
    return out;
}
int main() {
    assert(hash("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(hash("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    assert(hash(std::string(1000000,'a'))=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}
