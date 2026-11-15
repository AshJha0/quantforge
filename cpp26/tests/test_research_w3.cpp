// Stage J wave 3 unit and property tests (rulings J-W3-10 to J-W3-13), own data.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <random>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace rs = quantforge::research;
using Vec = std::vector<double>;

TEST_CASE("w3 cusum hand case and restart", "[research][w3]") {
    const rs::Alarms a = rs::cusum({0.0, 3.0, 3.0}, 0.5, 4.0, 0.0, 1.0, true);
    REQUIRE(a.alarms == std::vector<long long>{2});
    REQUIRE(a.directions == std::vector<long long>{1});
    REQUIRE(a.s_plus == 0.0);
    REQUIRE_THROWS_AS(rs::cusum({}, 0.5, 4.0, 0.0, 1.0, true), quantforge::Error);
}

TEST_CASE("w3 page-hinkley constant series never alarms", "[research][w3]") {
    REQUIRE(rs::page_hinkley(Vec(50, 1.0), 0.0, 1.0, 0, true).alarms.empty());
}

TEST_CASE("w3 psi identical samples is zero", "[research][w3]") {
    Vec x;
    for (int i = 0; i < 100; ++i) x.push_back(i);
    const rs::Psi p = rs::psi(x, x, 10, 0.25);
    REQUIRE(p.psi == 0.0);
    REQUIRE_FALSE(p.alarm);
}

TEST_CASE("w3 ks: separated samples and the fallback walk agrees with the 128-bit count", "[research][w3]") {
    const rs::Ks k = rs::ks({1, 2, 3, 4}, {5, 6, 7, 8}, 0.05);
    REQUIRE(k.statistic == 1.0);
    REQUIRE(std::fabs(k.p_value - 2.0 / 70.0) < 1e-15);
    for (const auto& [n, m] : {std::pair{4LL, 4LL}, {7LL, 5LL}, {12LL, 9LL}})
        for (long long d = 1; d <= n * m; ++d) REQUIRE(std::fabs(rs::ks_p_count(n, m, d) - rs::ks_p_walk(n, m, d)) < 1e-13);
}

TEST_CASE("w3 fsum is correctly rounded", "[research][w3]") {
    REQUIRE(rs::fsum({1e100, 1.0, -1e100}) == 1.0);
    REQUIRE(rs::fsum({0.1, 0.1, 0.1}) == 0.30000000000000004);
}

TEST_CASE("w3 replay flat outside the shock tenors", "[research][w3]") {
    const rs::Replay r = rs::replay({0.5, 1.0, 40.0}, {1, 1, 1}, {1.0, 10.0}, {10.0, 20.0}, 1.0, Vec{1, 1, 1});
    REQUIRE(r.applied_bp == Vec{10.0, 10.0, 20.0});
    REQUIRE(*r.pnl == -40.0);
}
