cmake_minimum_required(VERSION 3.25)
project(quantforge_cpp26 LANGUAGES CXX)

include(CTest)
set(CMAKE_CXX_STANDARD 26)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(quantforge_core src/conventions.cpp)
target_include_directories(quantforge_core PUBLIC include)
target_compile_features(quantforge_core PUBLIC cxx_std_26)

if(BUILD_TESTING)
  include(FetchContent)
  FetchContent_Declare(Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG 08092139210881f01a34e60c5f2fd6afa0ea4024) # v3.16.1
  FetchContent_MakeAvailable(Catch2)
  add_executable(quantforge_core_tests tests/test_conventions.cpp)
  target_link_libraries(quantforge_core_tests PRIVATE quantforge_core Catch2::Catch2WithMain)
  add_test(NAME quantforge_core_tests COMMAND quantforge_core_tests)
endif()
