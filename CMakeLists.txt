cmake_minimum_required(VERSION 3.24)
project(ffta2_recomp LANGUAGES C CXX)
option(FFTA2_HOST_ONLY "Build portable host tests without ROM-derived banks" OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include(CTest)
if(APPLE)
    set(FFTA2_FONT_SOURCE src/host/font_coretext.cpp)
    set(FFTA2_PLATFORM_LIBRARIES "-framework CoreText" "-framework CoreGraphics" "-framework CoreFoundation")
elseif(WIN32)
    set(FFTA2_FONT_SOURCE src/host/font_directwrite.cpp)
    set(FFTA2_PLATFORM_LIBRARIES dwrite bcrypt)
    add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN)
    if(MSVC)
        add_compile_options(/utf-8)
    endif()
else()
    message(FATAL_ERROR "A Linux font factory is not implemented yet; use the host/font.h extension point")
endif()
add_library(ffta2_platform STATIC ${FFTA2_FONT_SOURCE} src/host/digest.cpp)
target_include_directories(ffta2_platform PUBLIC "${CMAKE_SOURCE_DIR}/src")
target_link_libraries(ffta2_platform PUBLIC ${FFTA2_PLATFORM_LIBRARIES})
if(NOT FFTA2_HOST_ONLY)
set(FFTA2_BANK_DIR "" CACHE PATH "External ROM-derived title bank directory")
set(FFTA2_BIOS_BANK_DIR "" CACHE PATH "External open FreeBIOS generated banks")
if(NOT FFTA2_BANK_DIR OR NOT FFTA2_BIOS_BANK_DIR)
    message(FATAL_ERROR "Set FFTA2_BANK_DIR and FFTA2_BIOS_BANK_DIR to external generated banks")
endif()
find_package(Python3 COMPONENTS Interpreter REQUIRED)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/stage_runtime.py"
    --source "${CMAKE_SOURCE_DIR}/third_party/ndsrecomp"
    --output "${CMAKE_BINARY_DIR}/framework"
    RESULT_VARIABLE stage_result)
if(NOT stage_result EQUAL 0)
    message(FATAL_ERROR "Runtime staging failed")
endif()
set(NDS_GENERATED_DIR "${FFTA2_BIOS_BANK_DIR}" CACHE PATH "" FORCE)
set(NDS_TITLE_BANK_DIR "${FFTA2_BANK_DIR}" CACHE PATH "" FORCE)
set(NDS_TITLE_ROM_SHA1 "09a4a90eb05d187e7cd896497866d58da36353b0" CACHE STRING "" FORCE)
set(NDS_RECOMP_UI_ROOT "${CMAKE_SOURCE_DIR}/third_party/recomp-ui" CACHE PATH "" FORCE)
set(NDS_BOOTSTRAP_FIRMWARE ON CACHE BOOL "" FORCE)
set(NDS_ENABLE_COMPUTE_RENDERER OFF CACHE BOOL "" FORCE)
set(NDS_SDL_BACKEND SDL3 CACHE STRING "" FORCE)
set(NDSRECOMP_COMPILER_CACHE OFF CACHE STRING "" FORCE)
set(NDSRECOMP_COMPILE_JOBS 3 CACHE STRING "" FORCE)
set(NDSRECOMP_LINK_JOBS 1 CACHE STRING "" FORCE)
add_subdirectory("${CMAKE_BINARY_DIR}/framework/runner" backend)
set_target_properties(nds_runner PROPERTIES OUTPUT_NAME ffta2-recomp)

target_sources(nds_runner PRIVATE
    src/host/presentation_capture.cpp
    src/host/tile_text.cpp
    src/host/text_layer.cpp
    src/host/display_options.cpp
    src/ffta2/unicode_layout.cpp
    src/ffta2/guest_texture.cpp
    src/ffta2/guest_text.cpp
    src/ffta2/localization_pack.cpp
    src/ffta2/localization_runtime.cpp)
target_include_directories(nds_runner PRIVATE "${CMAKE_SOURCE_DIR}/src")
# debug_server.cpp belongs to nds_support and calls the title-owned host API.
target_include_directories(nds_support PRIVATE "${CMAKE_SOURCE_DIR}/src")
target_include_directories(nds_armv4t PRIVATE "${CMAKE_SOURCE_DIR}/src")
target_link_libraries(nds_runner PRIVATE ffta2_platform)
if(WIN32)
    if(MSVC)
        target_link_options(nds_runner PRIVATE /STACK:67108864)
    else()
        target_link_options(nds_runner PRIVATE -Wl,--stack,67108864)
    endif()
endif()
endif() # Runtime; the host tests below need no retail assets.

add_executable(ffta2_localization_test
    tests/native_localization_test.cpp src/ffta2/localization_pack.cpp)
target_include_directories(ffta2_localization_test PRIVATE src)
target_compile_features(ffta2_localization_test PRIVATE cxx_std_17)

target_link_libraries(ffta2_localization_test PRIVATE ffta2_platform)

add_executable(ffta2_unicode_layout_test
    tests/unicode_layout_test.cpp src/ffta2/unicode_layout.cpp)
target_include_directories(ffta2_unicode_layout_test PRIVATE src)
target_compile_features(ffta2_unicode_layout_test PRIVATE cxx_std_17)
add_executable(ffta2_host_presentation_test
    tests/host_presentation_test.cpp
    src/host/text_layer.cpp src/host/tile_text.cpp src/host/display_options.cpp)
target_include_directories(ffta2_host_presentation_test PRIVATE src)
target_compile_features(ffta2_host_presentation_test PRIVATE cxx_std_17)
target_link_libraries(ffta2_host_presentation_test PRIVATE ffta2_platform)

add_executable(ffta2_digest_test tests/digest_test.cpp)
target_link_libraries(ffta2_digest_test PRIVATE ffta2_platform)
foreach(test IN ITEMS ffta2_unicode_layout_test ffta2_host_presentation_test ffta2_digest_test)
    if(MSVC)
        target_compile_options(${test} PRIVATE /UNDEBUG)
    else()
        target_compile_options(${test} PRIVATE -UNDEBUG)
    endif()
    add_test(NAME ${test} COMMAND ${test})
endforeach()
