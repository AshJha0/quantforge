// F-4 library API finite checks, vol group: every public function rejects NaN and infinity with E_DOMAIN.
#include <catch2/catch_test_macros.hpp>

#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/arb_surface.hpp"
#include "quantforge/core/black.hpp"
#include "quantforge/core/equity.hpp"
#include "quantforge/core/equity_carry.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/fx.hpp"
#include "quantforge/core/fx_smile.hpp"
#include "quantforge/core/heston.hpp"
#include "quantforge/core/models.hpp"
#include "quantforge/core/rates_vol.hpp"
#include "quantforge/core/sabr.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/surface.hpp"
#include "quantforge/core/vol_stats.hpp"

using namespace quantforge;

namespace {

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "OK";
}

// Calls g(x) for x = NaN, +inf, -inf and expects E_DOMAIN each time.
template <class G>
void each_bad(G g) {
    const double nan = std::numeric_limits<double>::quiet_NaN(), inf = std::numeric_limits<double>::infinity();
    for (const double x : {nan, inf, -inf}) CHECK(code_of([&] { g(x); }) == "E_DOMAIN");
}

Date day(int y, unsigned m, unsigned d) { return Date{std::chrono::year{y} / m / d}; }

OptionInput bs_call() {
    OptionInput o{VolModel::BlackScholes, OptionType::Call, 100.0, 1.0};
    o.spot = 100.0;
    o.rate = 0.05;
    return o;
}

Svi svi0() { return {0.04, 0.1, -0.3, 0.0, 0.2}; }
std::vector<SviSlice> slices0() { return {{0.5, svi0()}, {1.0, {0.08, 0.1, -0.3, 0.0, 0.2}}}; }
SabrParameters sabr0() { return {0.2, 0.5, -0.3, 0.4}; }
HestonParams heston0() { return {0.04, 1.5, 0.04, 0.5, -0.7}; }
Jumps jumps0() { return {0.1, -0.1, 0.15}; }
EquityOption eq_option() { return {100.0, 1.0, 0.03, 0.01, OptionType::Call, {100.0}}; }
GkMarket gk0() { return {1.3, 1.0, 0.05, 0.03}; }

}  // namespace

TEST_CASE("finite vol: black option functions", "[finite]") {
    each_bad([](double x) { auto o = bs_call(); o.spot = x; check_option(o); });
    each_bad([](double x) { option_price(bs_call(), x); });
    each_bad([](double x) { auto o = bs_call(); o.strike = x; option_price(o, 0.2); });
    each_bad([](double x) { checked_option_price(bs_call(), x); });
    each_bad([](double x) { auto o = bs_call(); o.rate = x; checked_option_price(o, 0.2); });
    each_bad([](double x) { implied_vol(bs_call(), x); });
    each_bad([](double x) { auto o = bs_call(); o.expiry_years = x; implied_vol(o, 10.0); });
    each_bad([](double x) { option_greeks(bs_call(), x); });
    each_bad([](double x) { auto o = bs_call(); o.yield = x; bump_greeks(o, 0.2); });
    each_bad([](double x) { auto o = bs_call(); o.shift = x; require_finite(o); });
}

TEST_CASE("finite vol: black negative zero", "[finite]") {
    auto plus = bs_call(), minus = bs_call();
    plus.yield = 0.0;
    minus.yield = -0.0;
    CHECK(checked_option_price(plus, 0.2) == checked_option_price(minus, 0.2));
    CHECK(option_greeks(plus, 0.2).delta == option_greeks(minus, 0.2).delta);
    const double p = checked_option_price(plus, 0.2);
    CHECK(implied_vol(plus, p) == implied_vol(minus, p));
    plus.rate = 0.0;
    minus.rate = -0.0;
    CHECK(checked_option_price(plus, 0.2) == checked_option_price(minus, 0.2));
}

TEST_CASE("finite vol: smile functions", "[finite]") {
    each_bad([](double x) { delta_to_strike(x, 0.2, 1.0, OptionType::Call, 0.5, 1.0); });
    each_bad([](double x) { delta_to_strike(100.0, 0.2, 1.0, OptionType::Call, x, 1.0); });
    each_bad([](double x) { delta_from_strike(100.0, 0.2, 1.0, OptionType::Call, x, 1.0); });
    each_bad([](double x) { delta_from_strike(100.0, 0.2, 1.0, OptionType::Call, 100.0, x); });
    each_bad([](double x) { Svi s = svi0(); s.m = x; check_svi(s); });
    each_bad([](double x) { svi_calibrate({-0.2, -0.1, 0.0, 0.1, x}, {0.05, 0.045, 0.04, 0.045, 0.05}, std::nullopt); });
    each_bad([](double x) { svi_calibrate({-0.2, -0.1, 0.0, 0.1, 0.2}, {0.05, 0.045, 0.04, 0.045, 0.05}, std::vector<double>(5, x)); });
    each_bad([](double x) { check_ssvi({x, 1.0, 0.5}, {0.04}); });
    each_bad([](double x) { check_ssvi({-0.3, 1.0, 0.5}, {x}); });
    each_bad([](double x) { ssvi_butterfly_free({-0.3, x, 0.5}, {0.04}); });
    each_bad([](double x) { ssvi_calendar_free({-0.3, 1.0, x}, {0.04}); });
    each_bad([](double x) { ssvi_calibrate({0.04, 0.09}, {-0.1, 0.0}, {{0.05, 0.04}, {0.1, x}}); });
}

TEST_CASE("finite vol: smile negative zero", "[finite]") {
    Svi plus = svi0(), minus = svi0();
    plus.m = 0.0;
    minus.m = -0.0;
    CHECK_NOTHROW(check_svi(minus));
    CHECK(plus.w(0.1) == minus.w(0.1));
    const std::vector<double> k{-0.2, -0.1, 0.0, 0.1, 0.2}, kz{-0.2, -0.1, -0.0, 0.1, 0.2}, w{0.05, 0.045, 0.04, 0.045, 0.05};
    CHECK(svi_calibrate(k, w, std::nullopt).rmse == svi_calibrate(kz, w, std::nullopt).rmse);
}

TEST_CASE("finite vol: sabr functions", "[finite]") {
    each_bad([](double x) { check_sabr(x, sabr0(), 0.03, {0.03}); });
    each_bad([](double x) { SabrParameters p = sabr0(); p.nu = x; check_sabr(1.0, p, 0.03, {0.03}); });
    each_bad([](double x) { check_sabr(1.0, sabr0(), 0.03, {x}); });
    each_bad([](double x) { sabr_density(0.03, {0.03}, 1.0, sabr0(), x); });
    each_bad([](double x) { sabr_density(x, {0.03}, 1.0, sabr0(), 1e-4); });
    each_bad([](double x) { sabr_calibrate(0.03, 1.0, x, {0.02, 0.03, 0.04}, {0.2, 0.19, 0.2}, std::nullopt); });
    each_bad([](double x) { sabr_calibrate(0.03, 1.0, 0.5, {0.02, 0.03, 0.04}, {0.2, x, 0.2}, std::nullopt); });
    each_bad([](double x) { sabr_arbfree(x, {0.03}, 1.0, sabr0(), {200, 100, 10}); });
    each_bad([](double x) { SabrParameters p = sabr0(); p.rho = x; sabr_arbfree(0.03, {0.03}, 1.0, p, {200, 100, 10}); });
}

TEST_CASE("finite vol: sabr negative zero", "[finite]") {
    SabrParameters plus = sabr0(), minus = sabr0();
    plus.rho = 0.0;
    minus.rho = -0.0;
    CHECK_NOTHROW(check_sabr(1.0, minus, 0.03, {0.03}));
    CHECK(sabr_density(0.03, {0.03}, 1.0, plus, 1e-4).min_density == sabr_density(0.03, {0.03}, 1.0, minus, 1e-4).min_density);
}

TEST_CASE("finite vol: surface functions", "[finite]") {
    const auto surf = [](double x) {
        return Surface{{0.5, 1.0}, {-0.1, 0.0, 0.1}, {{0.2, 0.2, 0.2}, {0.2, x, 0.2}}};
    };
    each_bad([&](double x) { check_surface(surf(x)); });
    each_bad([&](double x) { surface_check(surf(x)); });
    each_bad([&](double x) { surface_total_variance(surf(0.2), x, 0.0); });
    each_bad([&](double x) { surface_total_variance(surf(0.2), 0.7, x); });
}

TEST_CASE("finite vol: surface negative zero", "[finite]") {
    const Surface plus{{0.5, 1.0}, {-0.1, 0.0, 0.1}, {{0.2, 0.2, 0.2}, {0.2, 0.2, 0.2}}};
    const Surface minus{{0.5, 1.0}, {-0.1, -0.0, 0.1}, {{0.2, 0.2, 0.2}, {0.2, 0.2, 0.2}}};
    CHECK(surface_total_variance(plus, 0.7, 0.0) == surface_total_variance(minus, 0.7, -0.0));
    CHECK(surface_check(plus).butterfly.size() == surface_check(minus).butterfly.size());
}

TEST_CASE("finite vol: arbitrage-free surface functions", "[finite]") {
    const auto bad_slices = [](double x) {
        auto s = slices0();
        s[1].svi.rho = x;
        return s;
    };
    each_bad([&](double x) { check_slices(bad_slices(x)); });
    each_bad([&](double x) { check_slices_input(bad_slices(x)); });
    each_bad([&](double x) { check_slices_domain(bad_slices(x)); });
    each_bad([&](double x) { auto s = slices0(); s[0].expiry_years = x; check_slices(s); });
    each_bad([&](double x) { svi_surface_check(bad_slices(x), {0.0}, false); });
    each_bad([&](double x) { svi_surface_check(slices0(), {x}, false); });
    each_bad([](double x) { ssvi_to_svi(-0.3, 1.0, 0.5, x); });
    each_bad([](double x) { ssvi_to_svi(x, 1.0, 0.5, 0.04); });
    each_bad([](double x) {
        svi_fit_surface({0.5, 1.0}, {-0.2, -0.1, 0.0, 0.1, 0.2},
                        {{0.05, 0.045, 0.04, 0.045, 0.05}, {0.1, 0.09, x, 0.09, 0.1}}, false);
    });
    each_bad([&](double x) { local_vol_dupire(slices0(), {{0.7, x}}); });
    each_bad([&](double x) { local_vol_dupire(bad_slices(x), {{0.7, 0.0}}); });
    each_bad([](double x) { forward_vols({0.5, x}, {0.2, 0.2}); });
    each_bad([](double x) { forward_vols({0.5, 1.0}, {0.2, x}); });
    each_bad([](double x) {
        SmileDynamicsInputs in{svi0(), 1.0, 100.0, 101.0, 0.03, x, {100.0}, SmileRule::StickyDelta, OptionType::Call};
        smile_dynamics(in);
    });
    each_bad([](double x) { vol_of_vol({0.2, 0.21, 0.19}, x, VolChange::Log); });
    each_bad([](double x) { vol_of_vol({0.2, x, 0.19}, 252.0, VolChange::Log); });
}

TEST_CASE("finite vol: arbitrage-free surface negative zero", "[finite]") {
    SmileDynamicsInputs plus{svi0(), 1.0, 100.0, 101.0, 0.0, 0.0, {100.0}, SmileRule::StickyDelta, OptionType::Call};
    SmileDynamicsInputs minus = plus;
    minus.rate = -0.0;
    minus.dividend_yield = -0.0;
    CHECK(smile_dynamics(plus).deltas == smile_dynamics(minus).deltas);
    CHECK(local_vol_dupire(slices0(), {{0.7, 0.0}}).local_vol == local_vol_dupire(slices0(), {{0.7, -0.0}}).local_vol);
}

TEST_CASE("finite vol: heston functions", "[finite]") {
    each_bad([](double x) { HestonParams h = heston0(); h.rho = x; check_heston(h); });
    each_bad([](double x) { Jumps j = jumps0(); j.mean_log_jump = x; check_jumps(j); });
    each_bad([](double x) { EquityOption o = eq_option(); o.rate = x; heston_price(o, heston0()); });
    each_bad([](double x) { HestonParams h = heston0(); h.xi = x; heston_price(eq_option(), h); });
    each_bad([](double x) { Jumps j = jumps0(); j.intensity = x; bates_price(eq_option(), heston0(), j); });
    each_bad([](double x) { merton_price(eq_option(), x, jumps0()); });
    each_bad([](double x) { EquityOption o = eq_option(); o.strikes = {x}; merton_price(o, 0.2, jumps0()); });
    each_bad([](double x) {
        slv_leverage(100.0, 1.0, x, 0.0, heston0(), slices0(), {10, 10, 5, std::log(50.0), std::log(200.0), 1.0});
    });
    each_bad([](double x) {
        slv_leverage(100.0, 1.0, 0.0, 0.0, heston0(), slices0(), {10, 10, 5, std::log(50.0), std::log(200.0), x});
    });
}

TEST_CASE("finite vol: heston negative zero", "[finite]") {
    EquityOption plus = eq_option(), minus = eq_option();
    plus.dividend_yield = 0.0;
    minus.dividend_yield = -0.0;
    CHECK(merton_price(plus, 0.2, jumps0()) == merton_price(minus, 0.2, jumps0()));
    CHECK(heston_price(plus, heston0()) == heston_price(minus, heston0()));
}

TEST_CASE("finite vol: fx functions", "[finite]") {
    const Date as_of = day(2025, 1, 6);
    const Curve c(as_of, CurveInterpolation::LogLinearDf);
    const auto market = [&](double spot) { return FxMarket{fx_pair("GBPUSD"), spot, as_of, &c, &c}; };
    each_bad([&](double x) { check_fx_market(market(x)); });
    each_bad([&](double x) { fx_outright(market(x), as_of); });
    each_bad([&](double x) { fx_forward_price(market(1.25), {x, 1.26, day(2025, 4, 8), FxSide::Buy}); });
    each_bad([&](double x) { fx_swap_price(market(1.25), {1e6, day(2025, 1, 8), 1.25, day(2025, 4, 8), x, FxSide::Buy}); });
    each_bad([&](double x) { fx_implied(market(1.25), {{Tenor{3, 'M'}, x}}); });
}

TEST_CASE("finite vol: fx smile functions", "[finite]") {
    each_bad([](double x) { GkMarket m = gk0(); m.foreign_rate = x; fx_option_price(m, 1.3, 0.1, OptionType::Call, 1e6); });
    each_bad([](double x) { fx_option_price(gk0(), 1.3, 0.1, OptionType::Call, x); });
    each_bad([](double x) { fx_deltas_from_strike(gk0(), x, 0.1, OptionType::Call); });
    each_bad([](double x) { fx_delta_to_strike(gk0(), 0.1, OptionType::Call, x, FxDeltaType::Spot); });
    each_bad([](double x) { GkMarket m = gk0(); m.domestic_rate = x; fx_atm_strike(m, 0.1, FxAtmType::Dns, FxDeltaType::Spot); });
    each_bad([](double x) { fx_smile_from_quotes(gk0(), 0.1, x, 0.005, 0.25, FxDeltaType::Spot, FxAtmType::Dns); });
    each_bad([](double x) { fx_smile_from_quotes(gk0(), 0.1, 0.01, x, 0.25, FxDeltaType::Spot, FxAtmType::Dns); });
}

TEST_CASE("finite vol: fx smile negative zero", "[finite]") {
    GkMarket plus = gk0(), minus = gk0();
    plus.foreign_rate = 0.0;
    minus.foreign_rate = -0.0;
    CHECK(fx_option_price(plus, 1.3, 0.1, OptionType::Call, 1e6).price ==
          fx_option_price(minus, 1.3, 0.1, OptionType::Call, 1e6).price);
    CHECK(fx_smile_from_quotes(gk0(), 0.1, 0.0, 0.005, 0.25, FxDeltaType::Spot, FxAtmType::Dns).call_strike ==
          fx_smile_from_quotes(gk0(), 0.1, -0.0, 0.005, 0.25, FxDeltaType::Spot, FxAtmType::Dns).call_strike);
}

TEST_CASE("finite vol: rates vol functions", "[finite]") {
    const Curve c(day(2025, 1, 6), CurveInterpolation::LogLinearDf);
    each_bad([&](double x) { cap_price(c, c, RateVolModel::Black76, {x}, true, 1.0, 12, 24, 0.03, 1e6); });
    each_bad([&](double x) { cap_price(c, c, RateVolModel::Black76, {0.2}, true, 1.0, 12, 24, x, 1e6); });
    each_bad([&](double x) { swaption_price(c, c, RateVolModel::Black76, x, 1.0, 12, 24, 0.03, 1e6); });
    each_bad([&](double x) { swaption_price(c, c, RateVolModel::Black76, 0.2, 1.0, 12, 24, 0.03, x); });
    each_bad([&](double x) {
        const SabrCube cube{{12}, {24}, {{0.2}}, {{0.5}}, {{x}}, {{0.4}}};
        swaption_price_cube(c, c, cube, 1.0, 12, 24, 0.03, 1e6);
    });
    each_bad([&](double x) {
        const SabrCube cube{{12}, {24}, {{0.2}}, {{0.5}}, {{-0.3}}, {{0.4}}};
        swaption_price_cube(c, c, cube, 1.0, 12, 24, x, 1e6);
    });
    each_bad([&](double x) { cap_strip(c, c, RateVolModel::Black76, 12, 0.03, {12, 24}, {0.2, x}, 1e6); });
    each_bad([](double x) { bondfut_option_price(1.0, 110.0, 110.0, 0.25, 0.99, x, 1e5); });
    each_bad([](double x) { bondfut_option_price(1.0, 110.0, 110.0, 0.25, 0.99, 0.05, x); });
    each_bad([](double x) { bondfut_implied_vol(1.0, 110.0, 110.0, 0.25, 0.99, 1.0, x, 7.0); });
    each_bad([](double x) { yoy_cap_price(RateVolModel::Black76, 1.0, 0.02, 1e6, {{1.0, 0.97, 0.025, x, 0.01}}); });
    each_bad([](double x) { yoy_cap_price(RateVolModel::Black76, 1.0, x, 1e6, {{1.0, 0.97, 0.025, 1.0, 0.01}}); });
    each_bad([](double x) { zc_cap_price(RateVolModel::Black76, 1.0, 1.1, 5.0, 0.02, x, 0.01, 1e6); });
}

TEST_CASE("finite vol: rates vol negative zero", "[finite]") {
    CHECK(bondfut_option_price(1.0, 110.0, 110.0, 0.25, 0.99, 0.0, 1e5).price ==
          bondfut_option_price(1.0, 110.0, 110.0, 0.25, 0.99, -0.0, 1e5).price);
    CHECK(zc_cap_price(RateVolModel::Bachelier, 1.0, 1.1, 5.0, 0.0, 0.95, 0.01, 1e6).price ==
          zc_cap_price(RateVolModel::Bachelier, 1.0, 1.1, 5.0, -0.0, 0.95, 0.01, 1e6).price);
}

TEST_CASE("finite vol: vol stats functions", "[finite]") {
    const auto returns = [](double x) {
        std::vector<double> r(40, 0.01);
        for (std::size_t i = 0; i < r.size(); i += 2) r[i] = -0.012;
        r[5] = x;
        return r;
    };
    each_bad([&](double x) { garch_loglik(returns(x), 1e-5, 0.1, 0.8, std::nullopt); });
    each_bad([&](double x) { garch_loglik(returns(0.01), 1e-5, 0.1, 0.8, x); });
    each_bad([](double x) { garch_forecast(1e-5, 0.1, 0.8, x, 10, 252.0); });
    each_bad([](double x) { garch_forecast(1e-5, 0.1, 0.8, 1e-4, 10, x); });
    each_bad([&](double x) { garch_fit(returns(x), std::nullopt); });
    each_bad([&](double x) { garch_fit(returns(0.01), x); });
    each_bad([](double x) {
        VarSwapInputs in{day(2025, 1, 6), day(2026, 1, 6), 100.0, 0.03, 0.0, {80.0, 90.0}, {110.0, 120.0},
                         {{80.0, 0.25}, {90.0, x}}, 5.0, 0.04, 1e4};
        varswap_fair_strike(in);
    });
    each_bad([](double x) {
        VarSwapInputs in{day(2025, 1, 6), day(2026, 1, 6), 100.0, x, 0.0, {80.0, 90.0}, {110.0, 120.0}, {}, 5.0, 0.04, 1e4};
        varswap_fair_strike(in);
    });
    each_bad([](double x) { varswap_realized({100.0, 101.0, x}, 252.0, 0.04, 1e4); });
    each_bad([](double x) { varswap_realized({100.0, 101.0, 102.0}, 252.0, x, 1e4); });
    const auto term = [](long long minutes, double x) {
        return VixTerm{minutes, 0.03, {{90.0, 11.0, 11.5, 0.5, 0.6}, {100.0, 4.0, 4.5, 4.0, x}, {110.0, 0.5, 0.6, 11.0, 11.5}}};
    };
    each_bad([&](double x) { vix_term_variance(term(30000, x)); });
    each_bad([&](double x) { vix_index(term(30000, 4.5), term(50000, x)); });
}

TEST_CASE("finite vol: vol stats negative zero", "[finite]") {
    CHECK(varswap_realized({100.0, 101.0, 102.0}, 252.0, 0.0, 1e4).payoff ==
          varswap_realized({100.0, 101.0, 102.0}, 252.0, -0.0, 1e4).payoff);
    VixTerm a{30000, 0.0, {{90.0, 11.0, 11.5, 0.5, 0.6}, {100.0, 4.0, 4.5, 4.0, 4.5}, {110.0, 0.5, 0.6, 11.0, 11.5}}};
    VixTerm b = a;
    b.rate = -0.0;
    CHECK(code_of([&] { vix_term_variance(a); }) == code_of([&] { vix_term_variance(b); }));
}

TEST_CASE("finite vol: equity functions", "[finite]") {
    const Date as_of = day(2025, 1, 6);
    const Curve c(as_of, CurveInterpolation::LogLinearDf);
    each_bad([&](double x) { equity_forward(x, as_of, day(2026, 1, 6), c, nullptr, {}); });
    each_bad([&](double x) { equity_forward(100.0, as_of, day(2026, 1, 6), c, nullptr, {{day(2025, 6, 1), x}}); });
    each_bad([](double x) { equity_forward_flat(100.0, x, 0.0, 1.0, {}); });
    each_bad([](double x) { equity_forward_flat(100.0, 0.03, 0.0, 1.0, {{x, 1.0}}); });
    each_bad([](double x) { parity_forward({{100.0, 5.0, x, 4.0, 4.2}}, 0.97); });
    each_bad([](double x) { parity_forward({{100.0, 5.0, 5.2, 4.0, 4.2}}, x); });
}

TEST_CASE("finite vol: equity negative zero", "[finite]") {
    CHECK(equity_forward_flat(100.0, 0.0, 0.0, 1.0, {}) == equity_forward_flat(100.0, -0.0, -0.0, 1.0, {}));
    CHECK(equity_forward_flat(100.0, 0.03, 0.0, 1.0, {{0.0, 1.0}}) == equity_forward_flat(100.0, 0.03, 0.0, 1.0, {{-0.0, 1.0}}));
}

TEST_CASE("finite vol: equity carry functions", "[finite]") {
    const Date as_of = day(2025, 1, 6), expiry = day(2026, 1, 6);
    const Curve c(as_of, CurveInterpolation::LogLinearDf);
    each_bad([&](double x) { implied_dividends(100.0, c, x, {{expiry, 101.0}}); });
    each_bad([&](double x) { implied_dividends(100.0, c, 0.0, {{expiry, x}}); });
    each_bad([&](double x) { implied_borrow(100.0, c, {}, expiry, x); });
    each_bad([&](double x) { implied_borrow(100.0, c, {{day(2025, 6, 1), x}}, expiry, 101.0); });
    each_bad([&](double x) { equity_futures_basis(100.0, c, 0.0, x, {}, expiry, 101.0); });
    each_bad([&](double x) { equity_futures_basis(100.0, c, 0.0, 0.0, {}, expiry, x); });
    each_bad([&](double x) { index_dividends(x, {}, {}, {}); });
    each_bad([&](double x) { index_dividends(1.0, {{"A", 10.0, x, {}}}, {}, {}); });
    each_bad([&](double x) { index_dividends(1.0, {}, {{as_of, expiry}}, {x}); });
    each_bad([&](double x) { index_rebalance(1.0, {{"A", x, 10.0, {}}}, {{"B", 1.0, 10.0, {}}}); });
    each_bad([&](double x) { index_rebalance(1.0, {{"A", 1.0, 10.0, {}}}, {{"B", 1.0, x, {}}}); });
    each_bad([](double x) { corporate_action(CorporateAction::Split, x, 100.0, 50.0, 2.0, 0.0); });
    each_bad([](double x) { corporate_action(CorporateAction::Rights, 50.0, 100.0, 50.0, 0.5, x); });
    each_bad([&](double x) { trs_price(x, c, 0.0, {}, {as_of, expiry, 100.0, 10.0, 0.01, 1.0}, std::nullopt); });
    each_bad([&](double x) { trs_price(100.0, c, 0.0, {}, {as_of, expiry, 100.0, 10.0, x, 1.0}, std::nullopt); });
    each_bad([&](double x) { trs_price(100.0, c, 0.0, {}, {as_of, expiry, 100.0, 10.0, 0.01, 1.0}, x); });
}

TEST_CASE("finite vol: equity carry negative zero", "[finite]") {
    const ActionResult plus = corporate_action(CorporateAction::Rights, 50.0, 100.0, 0.0, 0.5, 40.0);
    const ActionResult minus = corporate_action(CorporateAction::Rights, 50.0, 100.0, -0.0, 0.5, 40.0);
    CHECK(plus.factor == minus.factor);
    CHECK(plus.adjusted_strike == minus.adjusted_strike);
    CHECK(index_rebalance(1.0, {{"A", 0.0, 10.0, {}}, {"B", 1.0, 10.0, {}}}, {{"B", 1.0, 10.0, {}}}).level ==
          index_rebalance(1.0, {{"A", -0.0, 10.0, {}}, {"B", 1.0, 10.0, {}}}, {{"B", 1.0, 10.0, {}}}).level);
}

TEST_CASE("finite vol: pde, mc and cos engines", "[finite]") {
    const auto pde = [](double r) { return PdeInputs{OptionType::Call, 100.0, 100.0, r, 0.0, 0.2, 1.0, 100, 50}; };
    const auto mc = [](double sigma) {
        return McInputs{OptionType::Call, 100.0, 100.0, 0.03, 0.0, sigma, 1.0, 1000, 1, 42, 0, McMethod::Plain};
    };
    const auto cos = [](double rho) {
        return CosInputs{OptionType::Call, 100.0, 100.0, 0.03, 0.0, 1.0,
                         CosModel{CosModelName::Heston, 0.5, 0.04, 1.5, 0.04, rho}, 128, 10.0};
    };
    each_bad([&](double x) { pde_bs_european(pde(x)); });
    each_bad([&](double x) { auto in = pde(0.03); in.width = x; pde_bs_european(in); });
    each_bad([&](double x) { mc_gbm_european(mc(x)); });
    each_bad([&](double x) { cos_european(cos(x)); });
    each_bad([&](double x) { auto in = cos(-0.7); in.truncation = x; cos_european(in); });
}

TEST_CASE("finite vol: pde, mc and cos negative zero", "[finite]") {
    PdeInputs p{OptionType::Call, 100.0, 100.0, 0.0, 0.0, 0.2, 1.0, 100, 50};
    PdeInputs pm = p;
    pm.r = -0.0;
    pm.q = -0.0;
    CHECK(pde_bs_european(p).price == pde_bs_european(pm).price);
    McInputs m{OptionType::Call, 100.0, 100.0, 0.0, 0.0, 0.2, 1.0, 1000, 1, 42, 0, McMethod::Plain};
    McInputs mm = m;
    mm.r = -0.0;
    CHECK(mc_gbm_european(m).price == mc_gbm_european(mm).price);
    CosInputs c{OptionType::Call, 100.0, 100.0, 0.03, 0.0, 1.0, CosModel{CosModelName::Heston, 0.5, 0.04, 1.5, 0.04, 0.0}, 128, 10.0};
    CosInputs cm = c;
    cm.model.rho = -0.0;
    cm.q = -0.0;
    CHECK(cos_european(c).price == cos_european(cm).price);
}
