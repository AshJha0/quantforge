// Stage F wave 1a unit tests (cdsindex). No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <limits>
#include <string>

#include "quantforge/core/credit_options.hpp"
#include "quantforge/core/error.hpp"

using namespace quantforge;

namespace {
CdsIndexOptionInputs base_index() {
    return {make_date(2026, 11, 9), make_date(2027, 2, 17), make_date(2031, 12, 20), 0.037, 0.0105, 0.4, true, 0.0065, 0.01, 1e7, 0.45};
}
template <class F>
std::string code_of(F f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "ok";
}
std::string run(CdsIndexOptionInputs in) { return code_of([&] { (void)cds_index_option_price(in); }); }
}  // namespace

TEST_CASE("cdsindex: payer minus receiver = N A (F_adj - K_adj)", "[cdsindex]") {
    for (double k : {0.003, 0.0065, 0.01, 0.02}) {
        for (double c : {0.0, 0.01, 0.05}) {
            for (double v : {0.0, 0.2, 0.8}) {
                CdsIndexOptionInputs in = base_index();
                in.strike = k, in.coupon = c, in.vol = v;
                if (run(in) != "ok") continue;
                const auto p = cds_index_option_price(in);
                in.payer = false;
                const auto r = cds_index_option_price(in);
                const double want = in.notional * p.risky_annuity * (p.adjusted_forward - p.adjusted_strike);
                CHECK(std::fabs((p.price - r.price) - want) <= 1e-10 * std::max(std::fabs(want), p.price + r.price));
            }
        }
    }
}

TEST_CASE("cdsindex: strike hazard reprices the strike and C = K gives K_adj = K", "[cdsindex]") {
    CdsIndexOptionInputs in = base_index();
    in.coupon = in.strike;
    const auto p = cds_index_option_price(in);
    CHECK(p.exercise_upfront == 0.0);
    CHECK(p.adjusted_strike == in.strike);
    CHECK(p.strike_hazard > 0.0);
    CHECK(p.adjusted_forward > p.forward_spread);
}

TEST_CASE("cdsindex: input check edges", "[cdsindex]") {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    auto in = base_index();
    CHECK(run(in) == "ok");
    in = base_index(); in.expiry = in.as_of; CHECK(run(in) == "E_INPUT");
    in = base_index(); in.maturity = in.expiry; CHECK(run(in) == "E_INPUT");
    in = base_index(); in.recovery = 0.0; CHECK(run(in) == "ok");
    in = base_index(); in.recovery = 1.0; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.recovery = -1e-12; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.hazard_rate = -1e-12; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.hazard_rate = 0.0; CHECK(run(in) == "E_DOMAIN");  // F_adj = 0
    in = base_index(); in.strike = 0.0; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.strike = 1e-6; in.coupon = 0.0; CHECK(run(in) == "ok");
    in = base_index(); in.coupon = 0.0; CHECK(run(in) == "ok");
    in = base_index(); in.coupon = -1e-12; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.vol = 0.0; CHECK(run(in) == "ok");
    in = base_index(); in.vol = -1e-12; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.notional = 0.0; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.notional = 1e-9; CHECK(run(in) == "ok");
    in = base_index(); in.strike = 0.0005; in.coupon = 0.05; CHECK(run(in) == "E_DOMAIN");  // K_adj <= 0
    in = base_index(); in.rate = nan; CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.vol = std::numeric_limits<double>::infinity(); CHECK(run(in) == "E_DOMAIN");
    in = base_index(); in.coupon = nan; CHECK(run(in) == "E_DOMAIN");
}

TEST_CASE("cdsindex: zero vol is intrinsic", "[cdsindex]") {
    auto in = base_index();
    in.vol = 0.0;
    const auto p = cds_index_option_price(in);
    CHECK(std::fabs(p.price - in.notional * p.risky_annuity * std::max(p.adjusted_forward - p.adjusted_strike, 0.0)) <= 1e-9 * in.notional);
}
