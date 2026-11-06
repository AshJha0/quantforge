cmake_minimum_required(VERSION 3.25)
project(quantforge_cpp26 VERSION 0.1.0 LANGUAGES CXX)

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

add_library(quantforge_core
  src/core/calendar.cpp
  src/core/compounding.cpp
  src/core/cos.cpp
  src/core/data_checks.cpp
  src/core/dates.cpp
  src/core/daycount.cpp
  src/core/integrate.cpp
  src/core/interp.cpp
  src/core/json.cpp
  src/core/linalg.cpp
  src/core/mc.cpp
  src/core/pde.cpp
  src/core/rng.cpp
  src/core/root.cpp
  src/core/snapshot.cpp
  src/core/sobol.cpp
  src/core/stats.cpp
  src/core/timeseries.cpp
  src/core/timezone.cpp)
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
    tests/test_dates.cpp tests/test_data.cpp tests/test_numerics.cpp tests/test_models.cpp tests/test_cli.cpp)
  target_link_libraries(quantforge_core_tests PRIVATE quantforge_cli_lib Catch2::Catch2WithMain)
  if(MINGW)
    target_link_options(quantforge_core_tests PRIVATE -static)
  endif()
  add_test(NAME quantforge_core_tests COMMAND quantforge_core_tests)
endif()
