// SPDX-License-Identifier: GPL-3.0-or-later
#include "digest.h"
#include <stdexcept>
#if defined(_WIN32)
#include <windows.h>
#include <bcrypt.h>
#elif defined(__APPLE__)
#include <CommonCrypto/CommonDigest.h>
#else
#include <openssl/sha.h>
#endif
namespace ffta2::host {
std::array<uint8_t,32> sha256(const void* data,size_t size) {
    std::array<uint8_t,32> result{};
#if defined(_WIN32)
    if(size>UINT32_MAX)throw std::runtime_error("SHA256 input exceeds platform bound");
    BCRYPT_ALG_HANDLE algorithm=nullptr;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)
        throw std::runtime_error("Cannot open Windows SHA256 provider");
    BCRYPT_HASH_HANDLE hash=nullptr;
    auto status=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0);
    if(status>=0)status=BCryptHashData(hash,const_cast<PUCHAR>(static_cast<const UCHAR*>(data)),ULONG(size),0);
    if(status>=0)status=BCryptFinishHash(hash,result.data(),ULONG(result.size()),0);
    if(hash)BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm,0);
    if(status<0)throw std::runtime_error("Windows SHA256 failed");
#elif defined(__APPLE__)
    if(size>UINT32_MAX)throw std::runtime_error("SHA256 input exceeds platform bound");
    CC_SHA256(data,CC_LONG(size),result.data());
#else
    if(!SHA256(static_cast<const unsigned char*>(data),size,result.data()))
        throw std::runtime_error("SHA256 failed");
#endif
    return result;
}
}
