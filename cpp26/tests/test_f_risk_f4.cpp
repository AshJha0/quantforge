// Stage F risk_f4 unit tests. No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/risk_f4.hpp"
#include "quantforge/core/rng.hpp"

using namespace quantforge;

namespace {
template <class F>
std::string f4_code_of(F f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "ok";
}
bool near(double a, double b, double tol) { return std::fabs(a - b) <= tol * std::max(1.0, std::fabs(b)); }
}  // namespace

TEST_CASE("historical VaR: third largest of 250 at 99%, ES includes it", "[f4]") {
    std::vector<double> pnl(250);
    for (std::size_t i = 0; i < 250; ++i) pnl[i] = -double(i + 1);  // losses 1..250
    const VarResult r = var_historical(pnl, 0.99);
    CHECK(r.var == 248.0);
    CHECK(r.tail_count == 3);
    CHECK(r.es == 249.0);
    CHECK(f4_code_of([] { var_historical({}, 0.99); }) == "E_INPUT");
    CHECK(f4_code_of([] { var_historical({1.0}, 1.0); }) == "E_DOMAIN");
    CHECK(f4_code_of([] { var_historical({1.0}, 0.4); }) == "E_DOMAIN");
}

TEST_CASE("FHS equals historical when every return has the same size", "[f4]") {
    const std::vector<double> r = {0.01, -0.01, 0.01, -0.01, -0.01, 0.01};
    const FhsResult f = var_filtered_historical(r, 1e6, 0.94, 0.5);
    std::vector<double> pnl;
    for (const double x : r) pnl.push_back(1e6 * x);
    const VarResult h = var_historical(pnl, 0.5);
    CHECK(near(f.v.var, h.var, 1e-12));
    CHECK(near(f.v.es, h.es, 1e-12));
    CHECK(near(f.sigma_next, 0.01, 1e-12));
    CHECK(f4_code_of([] { var_filtered_historical({0.01}, 1.0, 1.0, 0.99); }) == "E_DOMAIN");
}

TEST_CASE("parametric VaR: c = 0.5 gives -mu", "[f4]") {
    CHECK(var_parametric(3.0, 2.0, 0.5).var == -3.0);
    const ParametricVar v = var_parametric(0.0, 1e6, 0.99);
    CHECK(near(v.var, 2326347.8740408407, 1e-13));
    CHECK(near(v.es, 2665214.2203458045, 1e-13));
    CHECK(f4_code_of([] { var_parametric(0.0, 0.0, 0.99); }) == "E_DOMAIN");
}

TEST_CASE("Monte Carlo VaR tends to the parametric one for one asset", "[f4]") {
    const VarResult r = var_monte_carlo({0.0}, {{1e-4}}, {1e6}, 10000, 11, 0.99);
    const double target = var_parametric(0.0, 1e4, 0.99).var;
    CHECK(std::fabs(r.var - target) / target < 0.05);
    CHECK(f4_code_of([] { var_monte_carlo({0, 0}, {{1e-4, 2e-4}, {2e-4, 1e-4}}, {1, 1}, 10, 1, 0.99); }) == "E_NOT_POSITIVE_DEFINITE");
}

TEST_CASE("Kupiec: x = n p gives LR 0 and p-value 1 (F-32)", "[f4]") {
    const Kupiec k = backtest_kupiec(500, 5, 0.99);
    CHECK(k.lr_uc == 0.0);
    CHECK(k.p_value == 1.0);
    const Kupiec z = backtest_kupiec(250, 0, 0.99);
    CHECK(near(z.lr_uc, 5.025167926750725, 1e-12));
    CHECK(near(z.p_value, 0.024981503053449705, 1e-12));
    CHECK(f4_code_of([] { backtest_kupiec(10, 11, 0.99); }) == "E_DOMAIN");
    CHECK(f4_code_of([] { backtest_kupiec(0, 0, 0.99); }) == "E_DOMAIN");
}

TEST_CASE("Christoffersen counts transitions", "[f4]") {
    const Christoffersen c = backtest_christoffersen({false, true, true, false, false}, 0.99);
    CHECK(c.n00 == 1);
    CHECK(c.n01 == 1);
    CHECK(c.n11 == 1);
    CHECK(c.n10 == 1);
    CHECK(c.lr_cc == c.lr_uc + c.lr_ind);
    CHECK(f4_code_of([] { backtest_christoffersen({true}, 0.99); }) == "E_INPUT");
}

TEST_CASE("traffic light zones at 250 and 99%", "[f4]") {
    CHECK(backtest_traffic_light(250, 4, 0.99).zone == TrafficZone::Green);
    CHECK(backtest_traffic_light(250, 5, 0.99).zone == TrafficZone::Yellow);
    CHECK(*backtest_traffic_light(250, 5, 0.99).plus_factor == 0.40);
    CHECK(backtest_traffic_light(250, 9, 0.99).zone == TrafficZone::Yellow);
    CHECK(backtest_traffic_light(250, 10, 0.99).zone == TrafficZone::Red);
    CHECK(near(backtest_traffic_light(250, 0, 0.99).cumulative_probability, 0.08105851616218128, 1e-13));
    CHECK(!backtest_traffic_light(500, 1, 0.99).plus_factor);
}

TEST_CASE("GIRR delta: one tenor gives RW |s|, high binds", "[f4]") {
    const GirrResult g = frtb_girr_delta({{"USD", "SOFR", GirrFactor::T5, 1e6}}, false, std::nullopt);
    CHECK(near(g.capital, 11000.0, 1e-14));
    CHECK(g.binding == 0);
    // Two currencies of opposite-sign basis: the alternative S_b is used in every scenario.
    std::vector<GirrSensitivity> basis;
    for (int i = 0; i < 4; ++i) {
        basis.push_back({"USD", "U" + std::to_string(i), GirrFactor::XccyBasis, 1e6});
        basis.push_back({"EUR", "E" + std::to_string(i), GirrFactor::XccyBasis, -1e6});
    }
    const GirrResult a = frtb_girr_delta(basis, false, std::nullopt);
    for (const auto& sc : a.scenarios) CHECK(sc.alternative_used);
    CHECK(f4_code_of([] {
              frtb_girr_delta({{"USD", "S", GirrFactor::T5, 1}, {"USD", "S", GirrFactor::T5, 1}}, false, std::nullopt);
          }) == "E_INPUT");
    CHECK(f4_code_of([] { frtb_girr_delta({}, false, std::nullopt); }) == "E_INPUT");
}
