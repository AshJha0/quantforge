// Boundary and accuracy tests aimed at mutants left alive in rates_vol and arb_surface (stage F mutation pass).
// All test data is local to the test functions (no namespace-scope statics).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <string>
#include <vector>

#include "quantforge/core/arb_surface.hpp"
#include "quantforge/core/correlation.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/rates_vol.hpp"

using namespace quantforge;

namespace {
std::string code_of(auto&& f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "none";
}
Curve flat_curve(Date as_of, double r) {
    std::vector<Pillar> p;
    for (int y = 1; y <= 12; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}
}  // namespace

TEST_CASE("rates_vol: zero is outside the strictly positive domains") {
    // A zero discount factor is refused (check_bondfut).
    CHECK(code_of([] { bondfut_option_price(1, 110, 112, 0.5, 0.0, 0.07, 100000); }) == "E_DOMAIN");
    // A zero modified duration is refused by the implied vol.
    const double p = bondfut_option_price(1, 110, 112, 0.5, 0.98, 0.07, 100000).price;
    CHECK(code_of([&] { bondfut_implied_vol(1, 110, 112, 0.5, 0.98, p, 0.04, 0.0); }) == "E_DOMAIN");
    CHECK(code_of([&] { bondfut_implied_vol(1, 110, 112, 0.5, 0.98, p, 0.04, 8.0); }) == "none");
    const Date as_of = *parse_date("2026-11-06");
    const Curve c = flat_curve(as_of, 0.03);
    // BLACK_76 cap strip at a zero strike is refused; start_months = 1200 is not an input error (the curve range check comes later).
    CHECK(code_of([&] { cap_strip(c, c, RateVolModel::Black76, 1, 0.0, {12}, {0.2}, 1e6); }) == "E_DOMAIN");
    CHECK(code_of([&] { cap_strip(c, c, RateVolModel::Black76, 1200, 0.03, {12}, {0.2}, 1e6); }) != "E_INPUT");
    // A cube node beta of exactly 1 is inside [0, 1].
    SabrCube cube{{12, 24}, {12, 24}, {{0.01, 0.01}, {0.01, 0.01}}, {{1.0, 1.0}, {1.0, 1.0}},
                  {{0.0, 0.0}, {0.0, 0.0}}, {{0.3, 0.3}, {0.3, 0.3}}};
    CHECK(code_of([&] { swaption_price_cube(c, c, cube, 1, 12, 12, 0.03, 1e6); }) == "none");
}

TEST_CASE("arb_surface: forward vols refuse a zero vol") {
    CHECK(code_of([] { forward_vols({0.5, 1.0}, {0.2, 0.0}); }) == "E_DOMAIN");
    CHECK(code_of([] { forward_vols({0.5, 1.0}, {0.2, 0.2}); }) == "none");
}

TEST_CASE("arb_surface: smile dynamics delta matches a spot finite difference") {
    const Svi svi{0.02, 0.1, -0.4, 0.0, 0.2};
    for (const SmileRule rule : {SmileRule::StickyStrike, SmileRule::StickyDelta}) {
        const double s = 100.0, h = 1e-4;
        const auto run = [&](double s1) {
            return smile_dynamics({svi, 1.0, s, s1, 0.03, 0.01, {90.0, 110.0}, rule, OptionType::Call});
        };
        const SmileDynamics up = run(s + h), down = run(s - h);
        for (std::size_t i = 0; i < 2; ++i) {
            const double fd = (up.prices_shifted[i] - down.prices_shifted[i]) / (2 * h);
            CHECK(std::fabs(up.deltas[i] - fd) < 1e-6);
        }
    }
}

TEST_CASE("arb_surface: local vol checks finite points at exactly the slice limit") {
    std::vector<SviSlice> sl;
    for (int i = 1; i <= 100; ++i) {
        const double t = 0.05 * i;
        sl.push_back({t, Svi{0.04 * t, 0.1 * t, -0.3, 0.0, 0.2}});
    }
    CHECK(code_of([&] { local_vol_dupire(sl, {{1.0, 0.0}}); }) == "none");
    CHECK(code_of([&] { local_vol_dupire(sl, {{1.0, std::nan("")}}); }) == "E_DOMAIN");
}

TEST_CASE("correlation: dispersion refuses a zero index realized vol") {
    const std::vector<double> w{0.5, 0.5}, k{0.2, 0.25}, s{0.22, 0.24};
    CHECK(code_of([&] { corr_dispersion(w, k, 0.18, s, 0.0, 1e5); }) == "E_DOMAIN");
    CHECK(code_of([&] { corr_dispersion(w, k, 0.18, s, 0.2, 1e5); }) == "none");
}
