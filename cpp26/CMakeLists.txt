cmake_minimum_required(VERSION 3.25)
project(quantforge_cpp26 VERSION 0.5.0 LANGUAGES CXX)

include(CTest)
set(CMAKE_CXX_STANDARD 26)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Sanitizer build, for Linux CI: -DQF_SANITIZE=address,undefined
set(QF_SANITIZE "" CACHE STRING "Comma-separated -fsanitize list; empty for none")
if(QF_SANITIZE)
  add_compile_options(-fsanitize=${QF_SANITIZE} -fno-omit-frame-pointer -fno-sanitize-recover=all)
  add_link_options(-fsanitize=${QF_SANITIZE})
endif()

# The CLI contract requires this for conformance builds. Never add -ffast-math.
add_compile_options(-ffp-contract=off -Wall -Wextra)

# CI turns this on (plan 12.1 G7); local builds keep warnings soft.
option(QF_WERROR "Treat warnings as errors and add -Wconversion -Wshadow" OFF)
# Applied to QuantForge's own targets only (see qf_strict below), never to fetched third-party code such as Catch2.
set(QF_STRICT_FLAGS)
if(QF_WERROR)
  set(QF_STRICT_FLAGS -Werror -Wconversion -Wshadow -Wno-sign-conversion)
endif()
function(qf_strict target)
  target_compile_options(${target} PRIVATE ${QF_STRICT_FLAGS})
endfunction()

add_library(quantforge_core
  src/core/calendar.cpp
  src/core/calibration.cpp
  src/core/compounding.cpp
  src/core/cos.cpp
  src/core/data_checks.cpp
  src/core/dates.cpp
  src/core/sabr.cpp
  src/core/surface.cpp
  src/core/smile.cpp
  src/core/black.cpp
  src/core/equity.cpp
  src/core/daycount.cpp
  src/core/fx.cpp
  src/core/integrate.cpp
  src/core/interp.cpp
  src/core/json.cpp
  src/core/linalg.cpp
  src/core/mc.cpp
  src/core/money.cpp
  src/core/pde.cpp
  src/core/rates.cpp
  src/core/rates_d.cpp
  src/core/bonds.cpp
  src/core/misc_d.cpp
  src/core/inflation.cpp
  src/core/equity_d.cpp
  src/core/credit.cpp
  src/core/risk.cpp
  src/core/rng.cpp
  src/core/root.cpp
  src/core/snapshot.cpp
  src/core/sobol.cpp
  src/core/stats.cpp
  src/core/store.cpp
  src/core/timeseries.cpp
  src/core/timezone.cpp
  src/core/vol_stats.cpp
  src/core/arb_surface.cpp
  src/core/fx_smile.cpp
  src/core/heston.cpp
  src/core/correlation.cpp
  src/core/exotics.cpp
  src/core/credit_e.cpp)
target_include_directories(quantforge_core PUBLIC include)
target_compile_features(quantforge_core PUBLIC cxx_std_26)
# sobol.cpp pulls the direction numbers in with #embed, so no command reads a file at run time.
set(QF_SOBOL_DATA ${CMAKE_CURRENT_SOURCE_DIR}/../specifications/01-core/data)
set_property(SOURCE src/core/sobol.cpp APPEND PROPERTY OBJECT_DEPENDS ${QF_SOBOL_DATA}/sobol-joe-kuo-d6-64.json)

add_library(quantforge_cli_lib src/cli/dispatch.cpp src/cli/test_functions.cpp)
target_include_directories(quantforge_cli_lib PUBLIC src/cli)
target_link_libraries(quantforge_cli_lib PUBLIC quantforge_core)
target_compile_definitions(quantforge_cli_lib PRIVATE QF_VERSION="${PROJECT_VERSION}")

add_executable(quantforge src/cli/main.cpp)
qf_strict(quantforge_core)
qf_strict(quantforge_cli_lib)
qf_strict(quantforge)
target_link_libraries(quantforge PRIVATE quantforge_cli_lib)
if(MINGW)
  # One self-contained executable, so the runner needs no compiler on PATH.
  target_link_options(quantforge PRIVATE -static)
endif()

if(BUILD_TESTING)
  include(FetchContent)
  FetchContent_Declare(Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG 08092139210881f01a34e60c5f2fd6afa0ea4024) # v3.16.1
  FetchContent_MakeAvailable(Catch2)
  add_executable(quantforge_core_tests
    tests/test_dates.cpp tests/test_data.cpp tests/test_numerics.cpp tests/test_models.cpp tests/test_cli.cpp tests/test_stage_b.cpp tests/test_stage_c.cpp tests/test_stage_d.cpp tests/test_bonds.cpp tests/test_stage_d2.cpp tests/test_stage_d3.cpp tests/test_cli_golden.cpp tests/test_r2.cpp tests/test_mutants_d.cpp tests/test_mutants_e.cpp tests/test_coverage.cpp tests/test_stage_e.cpp tests/test_limits_e.cpp)
  target_link_libraries(quantforge_core_tests PRIVATE quantforge_cli_lib Catch2::Catch2WithMain)
  qf_strict(quantforge_core_tests)
  if(MINGW)
    target_link_options(quantforge_core_tests PRIVATE -static)
  endif()
  add_test(NAME quantforge_core_tests COMMAND quantforge_core_tests)
endif()

# G2 microbenchmarks (Google Benchmark). Off by default; -DQF_BENCH=ON builds qf_micro.
option(QF_BENCH "Build the qf_micro Google Benchmark target" OFF)
if(QF_BENCH)
  include(FetchContent)
  set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
  set(BENCHMARK_ENABLE_GTEST_TESTS OFF CACHE BOOL "" FORCE)
  set(BENCHMARK_ENABLE_WERROR OFF CACHE BOOL "" FORCE)
  set(BENCHMARK_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(googlebenchmark
    GIT_REPOSITORY https://github.com/google/benchmark.git
    GIT_TAG v1.9.4)
  FetchContent_MakeAvailable(googlebenchmark)
  add_executable(qf_micro bench/micro.cpp)
  target_link_libraries(qf_micro PRIVATE quantforge_core benchmark::benchmark)
  target_compile_definitions(qf_micro PRIVATE QF_REPO_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/..")
  if(MINGW)
    target_link_options(qf_micro PRIVATE -static)
  endif()
endif()
