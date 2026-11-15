// Stage J-2: garch_estimate refuses a boundary maximum (ruling F-11). J0C_CPP_EQUIVALENT_MUTANTS.md listed the
// interior-check mutants at vol_stats.cpp:460, 462 and 468 as equivalent ("a bound that never fails alone once the
// polish converged"); that was wrong. On i.i.d. normal returns (no GARCH effect) the maximum often sits on alpha = 0,
// and the refusal is the only defence. No earlier test asserted the refusal, so those mutants survived. This table kills
// 460:24, 460:44, 460:68, 460:86, 462:30, 462:60 and 468:17 (each turns some refusals into an estimate).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <numbers>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/vol_stats.hpp"

using namespace quantforge;

namespace {
std::vector<double> j2_iid_returns(std::size_t n, unsigned long long s) {
    const auto u = [&] {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        return double((s >> 11) + 1) / 9007199254740994.0;
    };
    std::vector<double> r(n);
    for (auto& x : r) x = 0.01 * std::sqrt(-2.0 * std::log(u())) * std::cos(2.0 * std::numbers::pi * u());
    return r;
}

std::string j2_outcome(const std::vector<double>& r, GarchDistribution d) {
    try {
        garch_estimate(r, std::nullopt, d, false);
    } catch (const Error& e) {
        return e.code();
    }
    return "none";
}
}  // namespace

TEST_CASE("garch estimate refuses boundary maxima on i.i.d. returns", "[j2][vol_stats]") {
    // Seeds 1..12, n = 200. "R" = E_NO_CONVERGENCE (no interior maximum), "." = an estimate is returned.
    const std::string normal = "R.RRR.RR...R", student = "RR.RR.RRRRRR";
    for (unsigned long long seed = 1; seed <= 12; ++seed) {
        const std::vector<double> r = j2_iid_returns(200, seed);
        INFO("seed " << seed);
        CHECK(j2_outcome(r, GarchDistribution::Normal) == (normal[seed - 1] == 'R' ? "E_NO_CONVERGENCE" : "none"));
        CHECK(j2_outcome(r, GarchDistribution::StudentT) == (student[seed - 1] == 'R' ? "E_NO_CONVERGENCE" : "none"));
    }
}
