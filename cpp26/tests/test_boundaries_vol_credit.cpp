// Boundary, error-path and accuracy tests aimed at mutants that the goldens left alive in three stage E modules
// (rates_vol, vol_stats GARCH/variance swap/VIX, credit_options). Each check names the condition it pins.
// All test data is local to the test functions (no namespace-scope statics).
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/credit_options.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/rates_vol.hpp"
#include "quantforge/core/commodity.hpp"
#include "quantforge/core/mbs.hpp"
#include "quantforge/core/vol_stats.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date day(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
std::string msg_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.what(); }
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
double phi_cdf(double x) { return 0.5 * std::erfc(-x / std::sqrt(2.0)); }
// Independent reference: P(X <= a, Y <= b) = int_{-inf}^{a} phi(x) Phi((b - r x) / sqrt(1 - r^2)) dx, Simpson.
double bvn_reference(double a, double b, double r) {
    const double lo = -12.0, s = std::sqrt(1 - r * r);
    const int n = 200000;
    const double h = (a - lo) / n;
    double sum = 0.0;
    for (int i = 0; i <= n; ++i) {
        const double x = lo + i * h;
        const double f = std::exp(-x * x / 2) / std::sqrt(2 * 3.14159265358979323846) * phi_cdf((b - r * x) / s);
        sum += f * (i == 0 || i == n ? 1 : (i % 2 ? 4 : 2));
    }
    return sum * h / 3;
}
}  // namespace

TEST_CASE("rates_vol: month ranges are inclusive at 1 and 1200") {
    const Date as_of = day("2026-11-06");
    const Curve c = flat_curve(as_of, 0.03);
    // swaption expiry_months = 1 is valid (rates_vol.cpp).
    CHECK(code_of([&] { swaption_price(c, c, RateVolModel::Black76, 0.2, 1, 1, 12, 0.03, 1e6); }) == "none");
    CHECK(code_of([&] { swaption_price(c, c, RateVolModel::Black76, 0.2, 1, 0, 12, 0.03, 1e6); }) == "E_INPUT");
    // cap start_months = 1200 is not an input error; 1201 is (rates_vol.cpp).
    CHECK(msg_of([&] { cap_price(c, c, RateVolModel::Bachelier, {0.01}, true, 1, 1200, 3, 0.03, 1e6); }) !=
          "start_months must be at least 1");
    CHECK(msg_of([&] { cap_price(c, c, RateVolModel::Bachelier, {0.01}, true, 1, 1201, 3, 0.03, 1e6); }) ==
          "start_months must be at least 1");
    // cap_strip start_months = 0 is rejected (rates_vol.cpp).
    CHECK(msg_of([&] { cap_strip(c, c, RateVolModel::Black76, 0, 0.03, {12}, {0.2}, 1e6); }) ==
          "start_months must be at least 1");
    CHECK(code_of([&] { cap_strip(c, c, RateVolModel::Black76, 1, 0.03, {12}, {0.2}, 1e6); }) == "none");
    // MBS age = 1200 is valid (mbs.cpp).
    CHECK(code_of([] { mbs_cashflows({100.0, 0.06, 0.05, 1, 1200, false, 0.0}); }) == "none");
    CHECK(code_of([] { mbs_cashflows({100.0, 0.06, 0.05, 1, 1201, false, 0.0}); }) == "E_INPUT");
}

TEST_CASE("rates_vol: model and domain checks") {
    const Date as_of = day("2026-11-06");
    const Curve c = flat_curve(as_of, 0.03);
    std::vector<Pillar> ones;
    for (int y = 1; y <= 12; ++y) ones.push_back({add_months(as_of, 12 * y), 1.0});
    const Curve zero(as_of, CurveInterpolation::LogLinearDf, ones);  // every forward is exactly 0
    // Bachelier allows a negative strike; BLACK_76 rejects a zero strike or a zero forward (rates_vol.cpp).
    CHECK(code_of([&] { swaption_price(c, c, RateVolModel::Bachelier, 0.01, 1, 12, 24, -0.01, 1e6); }) == "none");
    CHECK(msg_of([&] { swaption_price(c, c, RateVolModel::Black76, 0.2, 1, 12, 24, 0.0, 1e6); }) ==
          "BLACK_76 needs a positive strike and forward");
    CHECK(msg_of([&] { swaption_price(c, zero, RateVolModel::Black76, 0.2, 1, 12, 24, 0.03, 1e6); }) ==
          "BLACK_76 needs a positive strike and forward");
    // cap_strip with a zero forward under BLACK_76 (rates_vol.cpp).
    CHECK(msg_of([&] { cap_strip(c, zero, RateVolModel::Black76, 1, 0.03, {12}, {0.2}, 1e6); }) ==
          "BLACK_76 needs positive forwards");
    // zc cap: a zero forward ratio is rejected under BLACK_76, a zero vol is allowed (rates_vol.cpp).
    CHECK(msg_of([] { zc_cap_price(RateVolModel::Black76, 1, 0.0, 5, 0.02, 0.9, 0.1, 1e6); }) ==
          "BLACK_76 needs a positive forward");
    CHECK(code_of([] { zc_cap_price(RateVolModel::Black76, 1, 1.1, 5, 0.02, 0.9, 0.0, 1e6); }) == "none");
    // MBS yield: 1 + y/12 > 0, so y = -0.5 is fine and y = -12 is not (mbs.cpp).
    CHECK(code_of([] { mbs_price({100.0, 0.06, 0.05, 360, 0, false, 0.0}, -0.5, 0); }) == "none");
    CHECK(code_of([] { mbs_price({100.0, 0.06, 0.05, 360, 0, false, 0.0}, -12.0, 0); }) == "E_DOMAIN");
    // A cube node beta of exactly 0 is inside [0, 1] (rates_vol.cpp).
    SabrCube cube{{12, 24}, {12, 24}, {{0.01, 0.01}, {0.01, 0.01}}, {{0.0, 0.0}, {0.0, 0.0}},
                  {{0.0, 0.0}, {0.0, 0.0}}, {{0.3, 0.3}, {0.3, 0.3}}};
    CHECK(code_of([&] { swaption_price_cube(c, c, cube, 1, 12, 12, 0.03, 1e6); }) == "none");
    cube.beta[1][1] = -0.01;
    CHECK(code_of([&] { swaption_price_cube(c, c, cube, 1, 12, 12, 0.03, 1e6); }) == "E_DOMAIN");
}

TEST_CASE("rates_vol: bond futures option implied vol") {
    // Round trip at a tight tolerance (rates_vol.cppbracket loop).
    const double p = bondfut_option_price(1, 110, 112, 0.5, 0.98, 0.07, 100000).price;
    CHECK(bondfut_implied_vol(1, 110, 112, 0.5, 0.98, p, 0.04, 8).price_vol == Approx(0.07).epsilon(1e-12));
    // The upper bound is D * strike unless phi > 0; phi = 0 is not a call (rates_vol.cpp).
    CHECK(code_of([] { bondfut_implied_vol(0, 100, 90, 1, 1, 95, 0.04, 8); }) == "E_DOMAIN");
}

TEST_CASE("vol_stats: GARCH fit reaches a constrained optimum") {
    // GARCH(1,1) path from a fixed LCG with Box-Muller normals.
    std::vector<double> r;
    unsigned long long st = 12345;
    const auto u01 = [&] {
        st = st * 6364136223846793005ULL + 1442695040888963407ULL;
        return (double(st >> 11) + 0.5) / 9007199254740992.0;
    };
    double v = 1e-4;
    for (int i = 0; i < 800; ++i) {
        const double z = std::sqrt(-2 * std::log(u01())) * std::cos(2 * 3.14159265358979323846 * u01());
        const double x = std::sqrt(v) * z;
        r.push_back(x);
        v = 2e-6 + 0.08 * x * x + 0.9 * v;
    }
    const GarchFit f = garch_fit(r, std::nullopt);
    CHECK(f.alpha > 0);
    CHECK(f.beta > 0);
    CHECK(f.alpha + f.beta < 1);
    CHECK(garch_loglik(r, f.omega, f.alpha, f.beta, std::nullopt).loglik == Approx(f.loglik).epsilon(1e-14));
    // No feasible neighbour is better.
    for (const double d : {-1e-3, 1e-3}) {
        CHECK(garch_loglik(r, f.omega * (1 + d), f.alpha, f.beta, std::nullopt).loglik <= f.loglik + 1e-9);
        CHECK(garch_loglik(r, f.omega, f.alpha + d * f.alpha, f.beta, std::nullopt).loglik <= f.loglik + 1e-9);
        CHECK(garch_loglik(r, f.omega, f.alpha, f.beta + d * (1 - f.alpha - f.beta), std::nullopt).loglik <=
              f.loglik + 1e-9);
    }
}

TEST_CASE("vol_stats: variance swap and VIX validation") {
    VarSwapInputs in{day("2026-11-06"), day("2027-11-06"), 100.0, 0.03, 0.0, {80, 90, 100}, {100, 110, 120},
                     {{80, 0.25}, {90, 0.22}, {100, 0.2}, {110, 0.19}, {120, 0.19}}, 10.0, 0.04, 1.0};
    CHECK(code_of([&] { varswap_fair_strike(in); }) == "none");
    in.extension_step = 0.0;  // vol_stats.cpp:226
    CHECK(msg_of([&] { varswap_fair_strike(in); }) == "extension_step must be positive");

    // Lowest strike at the forward: i0 = 0, so every out-of-the-money put is excluded (vol_stats.cpp:296).
    const VixTerm low{30000, 0.0, {{100, 3, 3, 2, 2}, {105, 1, 1, 6, 6}, {110, 0.5, 0.5, 10.5, 10.5}}};
    CHECK(msg_of([&] { vix_term_variance(low); }) == "every out-of-the-money put is excluded");

    // The terms must bracket 30 days (vol_stats.cpp:343); the edges n1 = 30 days and n2 = 30 days are allowed.
    const std::vector<VixQuote> s{{80, 20, 20, 0.1, 0.1}, {90, 10.5, 10.5, 0.5, 0.5}, {100, 2, 2, 2, 2},
                                  {110, 0.5, 0.5, 10.5, 10.5}, {120, 0.1, 0.1, 20, 20}};
    CHECK(code_of([&] { vix_index({43200, 0.0, s}, {50000, 0.0, s}); }) == "none");
    CHECK(code_of([&] { vix_index({30000, 0.0, s}, {43200, 0.0, s}); }) == "none");
    CHECK(msg_of([&] { vix_index({20000, 0.0, s}, {30000, 0.0, s}); }) ==
          "the terms must bracket 30 days with near before next");
    CHECK(code_of([&] { vix_index({50000, 0.0, s}, {60000, 0.0, s}); }) == "E_INPUT");
    CHECK(code_of([&] { vix_index({43200, 0.0, s}, {43200, 0.0, s}); }) == "E_INPUT");
}

TEST_CASE("credit_options: bivariate normal against an independent integral") {
    const double cases[][3] = {{0.3, -0.2, 0.5},  {0.3, -0.2, -0.5},  {0.5, 0.1, 0.95},   {0.5, 0.1, -0.95},
                               {-0.4, 0.7, 0.99}, {-0.4, 0.7, -0.99}, {1.2, -0.8, 0.999}, {1.2, -0.8, -0.999},
                               {0.2, 0.2, 0.97},  {-1.0, -1.5, 0.93}, {0.6, 1.1, -0.93}};
    for (const auto& x : cases) {
        INFO("a=" << x[0] << " b=" << x[1] << " rho=" << x[2]);
        CHECK(bivariate_normal_cdf(x[0], x[1], x[2]) == Approx(bvn_reference(x[0], x[1], x[2])).margin(1e-10));
    }
    // Just past the |rho| = 0.925 switch with h = k or h close to k, where the Gauss-Legendre remainder term
    // (credit_e.cpp:76-78) is largest; a tighter margin pins that term.
    const double near_switch[][3] = {{0.5, 0.5, 0.926}, {-0.3, -0.3, -0.926}, {0.1, 0.15, 0.93}, {0.0, 0.0, 0.93},
                                     {-0.2, 0.3, -0.93}};
    for (const auto& x : near_switch) {
        INFO("a=" << x[0] << " b=" << x[1] << " rho=" << x[2]);
        CHECK(bivariate_normal_cdf(x[0], x[1], x[2]) == Approx(bvn_reference(x[0], x[1], x[2])).margin(1e-13));
    }
    // Limits at rho = +-1.
    CHECK(bivariate_normal_cdf(0.3, -0.2, 1.0) == Approx(phi_cdf(-0.2)).margin(1e-14));
    CHECK(bivariate_normal_cdf(0.3, -0.2, -1.0) == Approx(phi_cdf(0.3) + phi_cdf(-0.2) - 1).margin(1e-14));
}

TEST_CASE("credit_options: Student t and the large pool checks") {
    // For large nu the bivariate t integral must stay finite and match its margin (credit_e.cpp:192).
    for (const double nu : {50.0, 400.0}) {
        CHECK(bivariate_t_cdf(0.7, 40.0, 0.4, nu) == Approx(student_t_cdf(0.7, nu)).margin(1e-8));
        const double t = bivariate_t_cdf(0.3, -0.2, 0.5, nu);
        CHECK(std::isfinite(t));
        CHECK(t == Approx(bivariate_normal_cdf(0.3, -0.2, 0.5)).margin(0.02));
    }
    CHECK(student_t_cdf(0.0, 3.0) == Approx(0.5).margin(1e-15));
    // Attachment equal to detachment: message names the strict inequality (credit_e.cpp:248).
    CHECK(msg_of([] { lhp_tranche_loss(0.05, 0.3, 0.4, 0.1, 0.1); }) == "0 <= attachment < detachment <= 1 is needed");
    // Loss grid is the open interval (0, 1 - R) (credit_e.cpp:260).
    const double rec = 0.4;
    CHECK(code_of([&] { lhp_loss_cdf(0.05, 0.3, rec, {0.0}); }) == "E_DOMAIN");
    CHECK(code_of([&] { lhp_loss_cdf(0.05, 0.3, rec, {1 - rec}); }) == "E_DOMAIN");
    CHECK(code_of([&] { lhp_loss_cdf(0.05, 0.3, rec, {0.3}); }) == "none");
}

// Surviving mutants judged equivalent (checked by hand, no test forced):
// rates_vol.cpp`&&` -> `||`: hi doubles 200 times, but bisect_up still reaches the same root to the last ulp.
// vol_stats.cpp:55/56 (u[1] + m, e1 * s): a different map onto (alpha, beta); the fit reaches the same interior optimum.
// vol_stats.cpp:78 sort with `<=`: four keys, ties only reorder equal values; best and worst values are unchanged.
// vol_stats.cpp:80 `<=` -> `<`: the stop differs only when the spread equals the tolerance exactly.
// vol_stats.cpp:188 start omega var*(1-a-b) -> var/(1-a-b): only a start point; the restarts reach the same optimum.
// vol_stats.cpp:190/197 `<` -> `<=`: on an exact tie the kept point has the same objective value.
// credit_e.cpp:82 `r > 0` -> `r >= 0`: this branch runs only for |r| >= 0.925, so r == 0 never reaches it.
// credit_e.cpp:113 `<` -> `<=` 1e-16: doubles near 1 are 1.1e-16 apart, so both tests mean del == 1.
// credit_e.cpp:119 `x >= 1` -> `x > 1`: at x == 1 the series front factor is 0 and the result is still 1.
// credit_e.cpp:129 `<=` -> `<`: mid == lo only once the bracket is one ulp wide; the result moves by at most an ulp.
