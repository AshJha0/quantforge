#include "quantforge/conventions.hpp"

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <chrono>
#include <stdexcept>

using namespace std::chrono;

TEST_CASE("ACT/360 counts actual days") {
    const auto start = sys_days{year{2025} / 1 / 1};
    const auto end = sys_days{year{2025} / 1 / 31};
    REQUIRE(quantforge::act_360(start, end) == Catch::Approx(30.0 / 360.0).epsilon(1e-14));
}

TEST_CASE("ACT/365F spans a leap day") {
    const auto start = sys_days{year{2024} / 2 / 28};
    const auto end = sys_days{year{2024} / 3 / 1};
    REQUIRE(quantforge::act_365f(start, end) == Catch::Approx(2.0 / 365.0).epsilon(1e-14));
}

TEST_CASE("Reversed dates are rejected") {
    const auto start = sys_days{year{2025} / 1 / 1};
    const auto end = sys_days{year{2025} / 1 / 31};
    REQUIRE_THROWS_AS(quantforge::act_360(end, start), std::invalid_argument);
}
