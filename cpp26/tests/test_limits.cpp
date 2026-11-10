// Q5a: limit-case and convergence-order checks for the stage E numerical methods that have no
// outside source (plan section 12.1). The same checks run in all four languages.
#include <algorithm>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <vector>

#include "quantforge/core/arb_surface.hpp"
#include "quantforge/core/exotics.hpp"
#include "quantforge/core/heston.hpp"
#include "quantforge/core/models.hpp"

using namespace quantforge;

namespace {
void band(const std::vector<double>& e, double lo, double hi) {
    for (std::size_t i = 0; i + 1 < e.size(); ++i) {
        double p = std::log2(std::abs(e[i] / e[i + 1]));
        INFO("observed order " << p);
        CHECK((p >= lo && p <= hi));
    }
}

ExoticMarket put(double rate) { return {100.0, 100.0, 1.0, rate, 0.0, 0.2, OptionType::Put}; }

double fd(double rate, bool american, long long nx, long long nt) {
    return american_fd(put(rate), american, {nx, nt, 5.0}).price;
}

// Largest |L - 1| near ln(spot) when SLV reduces to Heston (flat 20%, v0 = theta, xi small).
double slv_gap(long long nx, long long nv, long long nt) {
    const double x0 = std::log(100.0);
    std::vector<SviSlice> flat{{1.0, Svi{0.04, 0.0, 0.0, 0.0, 0.1}}};
    auto r = slv_leverage(100.0, 1.0, 0.0, 0.0, {0.04, 2.0, 0.04, 0.01, -0.7}, flat,
                          {nx, nv, nt, x0 - 1.0, x0 + 1.0, 0.25});
    CHECK(std::abs(r.mass - 1.0) < 1e-3);
    double gap = 0.0;
    for (std::size_t i = 0; i < r.x.size(); ++i)
        if (std::abs(r.x[i] - x0) < 0.3) gap = std::max(gap, std::abs(r.leverage[i] - 1.0));
    return gap;
}
}  // namespace

TEST_CASE("Q5a SLV Heston limit: leverage 1 within discretisation error") {
    double coarse = slv_gap(41, 20, 20), fine = slv_gap(81, 40, 40);
    CHECK(coarse < 0.07);
    CHECK(fine < 0.6 * coarse);  // about first order
}

TEST_CASE("Q5a FD American put matches a fine CRR tree") {
    double tree = american_crr(put(0.05), 1000).american;
    // Backward Euler error at this grid is about 2e-3; the tree's about 5e-4.
    CHECK(std::abs(fd(0.05, true, 401, 1600) - tree) < 5e-3);
}

TEST_CASE("Q5a FD American put at zero rate is the European") {
    double am = fd(0.0, true, 401, 400);
    CHECK(std::abs(am - fd(0.0, false, 401, 400)) < 1e-12);
    CHECK(std::abs(am - gbs(OptionType::Put, 100, 100, 1, 0, 0, 0.2)) < 5e-3);
}

TEST_CASE("Q5a Crank-Nicolson PDE is second order") {
    double exact = gbs(OptionType::Call, 100, 105, 1, 0.03, 0.02, 0.2);
    std::vector<double> e;
    for (long long j : {100LL, 200LL, 400LL})
        e.push_back(pde_bs_european({OptionType::Call, 100, 105, 0.03, 0.01, 0.2, 1, j, j / 2}).price - exact);
    band(e, 1.8, 2.2);
}

TEST_CASE("Q5a FD reference scheme orders in space and time") {
    double exact = gbs(OptionType::Put, 100, 100, 1, 0.05, 0.05, 0.2);
    // Space: halve dx and quarter dt, so the O(dt) term keeps pace with O(dx^2).
    band({fd(0.05, false, 51, 25) - exact, fd(0.05, false, 101, 100) - exact, fd(0.05, false, 201, 400) - exact},
         1.8, 2.2);
    // Time: Richardson on successive differences at a fixed fine grid.
    std::vector<double> f;
    for (long long nt : {50LL, 100LL, 200LL, 400LL}) f.push_back(fd(0.05, false, 401, nt));
    band({f[0] - f[1], f[1] - f[2], f[2] - f[3]}, 0.8, 1.2);
}

TEST_CASE("Q5a CRR tree is first order") {
    double exact = gbs(OptionType::Put, 100, 100, 1, 0.05, 0.05, 0.2);
    std::vector<double> e;
    for (long long n : {100LL, 200LL, 400LL}) e.push_back(american_crr(put(0.05), n).european - exact);
    band(e, 0.8, 1.2);
}
