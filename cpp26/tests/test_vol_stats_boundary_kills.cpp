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
    // n = 200. "R" = E_NO_CONVERGENCE (no interior maximum), "." = an estimate is returned, "-" = not pinned.
    // The returns go through libm log and cos, which may differ by an ulp between glibc, MinGW and MSVC, so only
    // seeds whose outcome is stable are pinned. Stability was checked (2026-11-15, g++ 15 on glibc) by re-running each
    // seed 24 times with every return moved by up to 4 ulps: every Normal outcome below and every Student-t refusal
    // kept its outcome in 24 of 24; Student-t seeds 3 and 6 (estimates whose Newton stop flips on 2 and 15 of 24
    // perturbations) are left unpinned, and seeds 24 and 38 (stable Student-t estimates, smallest of alpha, beta and
    // 1 - alpha - beta at least 0.04) take their place. Every Normal estimate pinned has that margin at least 0.006,
    // far above the 1e-6 interior tolerance. The kills come from the refusals, all of which are kept.
    struct Pin { unsigned long long seed; char normal, student; };
    const std::vector<Pin> pins = {{1, 'R', 'R'},  {2, '.', 'R'},  {3, 'R', '-'},  {4, 'R', 'R'},  {5, 'R', 'R'},
                                   {6, '.', '-'},  {7, 'R', 'R'},  {8, 'R', 'R'},  {9, '.', 'R'},  {10, '.', 'R'},
                                   {11, '.', 'R'}, {12, 'R', 'R'}, {24, '.', '.'}, {38, '.', '.'}};
    const auto expect = [](char c) { return std::string(c == 'R' ? "E_NO_CONVERGENCE" : "none"); };
    for (const Pin& p : pins) {
        const std::vector<double> r = j2_iid_returns(200, p.seed);
        INFO("seed " << p.seed);
        CHECK(j2_outcome(r, GarchDistribution::Normal) == expect(p.normal));
        if (p.student != '-') CHECK(j2_outcome(r, GarchDistribution::StudentT) == expect(p.student));
    }
}
