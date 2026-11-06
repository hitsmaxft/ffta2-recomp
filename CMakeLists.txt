cmake_minimum_required(VERSION 3.24)
project(ffta2_recomp LANGUAGES C CXX)
if(NOT APPLE OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)$")
    message(FATAL_ERROR "This initial backend targets native macOS ARM64")
endif()
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "Native host architecture")
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
    src/ffta2/localization_pack.cpp
    src/ffta2/localization_runtime.cpp)
target_include_directories(nds_runner PRIVATE "${CMAKE_SOURCE_DIR}/src")
# debug_server.cpp belongs to nds_support and calls the title-owned host API.
target_include_directories(nds_support PRIVATE "${CMAKE_SOURCE_DIR}/src")
add_executable(ffta2_localization_test EXCLUDE_FROM_ALL
    tests/native_localization_test.cpp src/ffta2/localization_pack.cpp)
target_include_directories(ffta2_localization_test PRIVATE src)
target_compile_features(ffta2_localization_test PRIVATE cxx_std_17)
