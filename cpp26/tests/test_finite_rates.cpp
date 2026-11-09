// F-4 library API finite checks, rates group: every public function rejects NaN and infinity with E_DOMAIN.
#include <catch2/catch_test_macros.hpp>

#include <limits>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/bonds.hpp"
#include "quantforge/core/calibration.hpp"
#include "quantforge/core/commodity.hpp"
#include "quantforge/core/compounding.hpp"
#include "quantforge/core/credit.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/inflation.hpp"
#include "quantforge/core/mbs.hpp"
#include "quantforge/core/money.hpp"
#include "quantforge/core/multicurve.hpp"
#include "quantforge/core/rates.hpp"
#include "quantforge/core/risk.hpp"

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

std::vector<double> bad_values() {
    return {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity()};
}

Date as_of() { return make_date(2024, 1, 2); }

Curve flat_curve() {
    return Curve(as_of(), CurveInterpolation::LogLinearDf,
                 {{make_date(2025, 1, 2), 0.96}, {make_date(2030, 1, 2), 0.82}, {make_date(2040, 1, 2), 0.65}});
}

const RateConvention& sofr() { return *rate_convention("SOFR"); }

std::vector<OisQuote> ois_quotes() { return {{Tenor{1, 'Y'}, 0.04}, {Tenor{2, 'Y'}, 0.041}, {Tenor{5, 'Y'}, 0.042}}; }

Bond bond() { return {make_date(2030, 6, 15), 0.05, 2}; }

MbsPool pool() { return {1e6, 0.06, 0.055, 360, 0, true, 100.0}; }

}  // namespace

TEST_CASE("finite rates: curve, jumps and solve") {
    for (const double x : bad_values()) {
        CHECK(code_of([&] { check_jumps(as_of(), {{make_date(2024, 6, 1), x}}); }) == "E_DOMAIN");
        CHECK(code_of([&] { Curve(as_of(), CurveInterpolation::LogLinearDf, {{make_date(2025, 1, 2), x}}); }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  Curve(as_of(), CurveInterpolation::LogLinearDf, {{make_date(2025, 1, 2), 0.9}}, {{make_date(2024, 6, 1), x}});
              }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  solve_curve(as_of(), CurveInterpolation::LogLinearDf, {make_date(2025, 1, 2)}, {x},
                              [](std::size_t, const Curve&) { return 0.0; }, SolveMethod::Sequential);
              }) == "E_DOMAIN");
        auto q = ois_quotes();
        q[1].rate = x;
        CHECK(code_of([&] { ois_bootstrap(sofr(), as_of(), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential); }) ==
              "E_DOMAIN");
        CHECK(code_of([&] { bumped_curves(sofr(), as_of(), q, CurveInterpolation::LogLinearDf); }) == "E_DOMAIN");
        CHECK(code_of([&] { ois_compound({0.01, x}, {1, 1}, 360.0); }) == "E_DOMAIN");
        CHECK(code_of([&] { ois_compound({0.01}, {1}, x); }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  projection_bootstrap(flat_curve(), sofr(), as_of(), {{ProjectionQuoteType::Deposit, 3, x}},
                                       CurveInterpolation::LogLinearDf);
              }) == "E_DOMAIN");
    }
}

TEST_CASE("finite rates: trades and cashflow risk") {
    const Curve c = flat_curve();
    for (const double x : bad_values()) {
        CHECK(code_of([&] { ois_price({&sofr(), Tenor{2, 'Y'}, x, 1e6, FixedSide::Pay}, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { ois_price({&sofr(), Tenor{2, 'Y'}, 0.04, x, FixedSide::Pay}, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { swap_price({rate_convention("USD-TERM-3M"), 24, x, 1e6, FixedSide::Pay}, c, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { fra_price({rate_convention("USD-TERM-3M"), make_date(2024, 6, 3), 0.04, x, FixedSide::Pay}, c, c); }) ==
              "E_DOMAIN");
        BumpedCurves b;
        CHECK(code_of([&] { rate_risk({&sofr(), Tenor{2, 'Y'}, x, 1e6, FixedSide::Pay}, b); }) == "E_DOMAIN");
        CHECK(code_of([&] { cashflow_risk({{1.0, 100.0}}, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { cashflow_risk({{x, 100.0}}, 0.05); }) == "E_DOMAIN");
        CHECK(code_of([&] { cashflow_risk({{1.0, x}}, 0.05); }) == "E_DOMAIN");
    }
    const CashflowRisk p = cashflow_risk({{1.0, 100.0}, {2.0, 100.0}}, 0.0);
    const CashflowRisk m = cashflow_risk({{1.0, 100.0}, {2.0, 100.0}}, -0.0);
    CHECK(p.pv == m.pv);
    CHECK(p.duration == m.duration);
    CHECK(p.convexity == m.convexity);
}

TEST_CASE("finite rates: multicurve") {
    const Curve c = flat_curve();
    for (const double x : bad_values()) {
        const std::vector<Fixing> fixings{{make_date(2024, 3, 4), x}};
        CHECK(code_of([&] { compound_dated(sofr(), make_date(2024, 3, 4), make_date(2024, 3, 5), ShiftMethod::None, 0, fixings); }) ==
              "E_DOMAIN");
        CHECK(code_of([&] { fallback_rate("USD-LIBOR-3M", make_date(2024, 3, 4), make_date(2024, 6, 4), fixings); }) == "E_DOMAIN");
        CHECK(code_of([&] { StepCurve{as_of(), x, {}, {}}.check(); }) == "E_DOMAIN");
        CHECK(code_of([&] { StepCurve{as_of(), 0.04, {{make_date(2024, 3, 1), x}}, {}}.check(); }) == "E_DOMAIN");
        auto q = ois_quotes();
        q[0].rate = x;
        CHECK(code_of([&] { fit_steps(sofr(), as_of(), {make_date(2025, 6, 1), make_date(2026, 6, 1)}, q, {}); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_convexity(x, 0.25, 0.5, 0.01, 0.03); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_convexity(95.0, x, 0.5, 0.01, 0.03); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_convexity(95.0, 0.25, x, 0.01, 0.03); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_convexity(95.0, 0.25, 0.5, x, 0.03); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_convexity(95.0, 0.25, 0.5, 0.01, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { csa_discount(c, x, std::nullopt, {make_date(2025, 1, 2)}); }) == "E_DOMAIN");
        CHECK(code_of([&] { csa_discount(c, 0.0, CsaFx{x, {}}, {}); }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  joint_bootstrap(sofr(), *rate_convention("USD-TERM-3M"), as_of(), q, {{ProjectionQuoteType::Deposit, 3, 0.04}},
                                  CurveInterpolation::LogLinearDf, SolveMethod::Sequential);
              }) == "E_DOMAIN");
        CHECK(code_of([&] { smooth_fit({1.0, x}, {1.0}, {0.04}, 0.1, std::nullopt); }) == "E_DOMAIN");
        CHECK(code_of([&] { smooth_fit({1.0, 2.0}, {1.0}, {0.04}, x, std::nullopt); }) == "E_DOMAIN");
        CHECK(code_of([&] { smooth_fit({1.0, 2.0}, {1.0}, {0.04}, 0.1, std::vector<double>{x}); }) == "E_DOMAIN");
        CHECK(code_of([&] { robust_fit({1.0, 2.0, 3.0}, {0.04, x, 0.04}, 1.0, 0.01); }) == "E_DOMAIN");
        CHECK(code_of([&] { robust_fit({1.0, 2.0, 3.0}, {0.04, 0.04, 0.04}, x, 0.01); }) == "E_DOMAIN");
        CHECK(code_of([&] { xccy_leg({as_of(), make_date(2024, 4, 2)}, x, c, c, 0.0); }) == "E_DOMAIN");
        CHECK(code_of([&] { xccy_leg({as_of(), make_date(2024, 4, 2)}, 1.0, c, c, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { xccy_bootstrap(c, as_of(), {{12, x}}, CurveInterpolation::LogLinearDf); }) == "E_DOMAIN");
        CHECK(code_of([&] { ndf_price(c, c, x, make_date(2024, 6, 3), make_date(2024, 6, 5), 80.0, 1e6, 1.0, std::nullopt); }) ==
              "E_DOMAIN");
        CHECK(code_of([&] { ndf_price(c, c, 80.0, make_date(2024, 6, 3), make_date(2024, 6, 5), 80.0, 1e6, 1.0, x); }) == "E_DOMAIN");
    }
    const Convexity p = futures_convexity(95.0, 0.0, 0.5, 0.01, 0.0);
    const Convexity m = futures_convexity(95.0, -0.0, 0.5, 0.01, -0.0);
    CHECK(p.convexity == m.convexity);
    CHECK(p.forward_rate == m.forward_rate);
    CHECK(csa_discount(c, 0.0, std::nullopt, {make_date(2025, 1, 2)}) == csa_discount(c, -0.0, std::nullopt, {make_date(2025, 1, 2)}));
    const std::vector<Date> leg{as_of(), make_date(2024, 4, 2)};
    CHECK(xccy_leg(leg, 1.0, c, c, 0.0) == xccy_leg(leg, 1.0, c, c, -0.0));
}

TEST_CASE("finite rates: bonds") {
    const Curve c = flat_curve();
    const Date s = make_date(2024, 3, 1);
    for (const double x : bad_values()) {
        const Bond bad{make_date(2030, 6, 15), x, 2};
        CHECK(code_of([&] { bond_period(bad, s); }) == "E_DOMAIN");
        CHECK(code_of([&] { coupon_amount(bad); }) == "E_DOMAIN");
        CHECK(code_of([&] { accrued(bad, s); }) == "E_DOMAIN");
        CHECK(code_of([&] { price_from_yield(bond(), s, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { yield_from_price(bond(), s, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { curve_dirty(bond(), s, c, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { z_spread(bond(), s, c, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { asset_swap(bond(), s, c, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { frn_price({make_date(2027, 3, 1), 4, x, 0.001, 0.001}, s, c, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { frn_price({make_date(2027, 3, 1), 4, 0.05, x, 0.001}, s, c, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { frn_price({make_date(2027, 3, 1), 4, 0.05, 0.001, x}, s, c, c); }) == "E_DOMAIN");
        CHECK(code_of([&] { repo_forward(bond(), s, make_date(2024, 4, 1), 99.0, x, std::nullopt); }) == "E_DOMAIN");
        CHECK(code_of([&] { repo_forward(bond(), s, make_date(2024, 4, 1), 99.0, 0.05, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { repo_implied_rate(bond(), s, make_date(2024, 4, 1), 99.0, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { conversion_factor(bond(), make_date(2024, 6, 1), x); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_basis(x, s, make_date(2024, 6, 1), 0.05, {{bond(), 99.0, 0.9}}); }) == "E_DOMAIN");
        CHECK(code_of([&] { futures_basis(110.0, s, make_date(2024, 6, 1), 0.05, {{bond(), 99.0, x}}); }) == "E_DOMAIN");
        CHECK(code_of([&] { bond_nelson_siegel(s, x, {}, std::nullopt); }) == "E_DOMAIN");
        CHECK(code_of([&] { bond_nelson_siegel(s, 1.0, {{bond(), x}}, std::nullopt); }) == "E_DOMAIN");
    }
    const YieldPrice p = price_from_yield(bond(), s, 0.0);
    const YieldPrice m = price_from_yield(bond(), s, -0.0);
    CHECK(p.dirty == m.dirty);
    CHECK(p.modified_duration == m.modified_duration);
    CHECK(curve_dirty(bond(), s, c, 0.0) == curve_dirty(bond(), s, c, -0.0));
}

TEST_CASE("finite rates: inflation") {
    const Curve c = flat_curve();
    const long long base = month_index(make_date(2024, 1, 1));
    for (const double x : bad_values()) {
        CHECK(code_of([&] { CpiCurve{base, x, {{1.0, 0.02}}, std::nullopt}.check(); }) == "E_DOMAIN");
        CHECK(code_of([&] { CpiCurve{base, 300.0, {{1.0, x}}, std::nullopt}.check(); }) == "E_DOMAIN");
        const CpiCurve good{base, 300.0, {{1.0, 0.02}, {5.0, 0.025}}, std::nullopt};
        CHECK(code_of([&] { zcis_price(good, c, 1.0, x, 1e6, 1.0, make_date(2025, 1, 2)); }) == "E_DOMAIN");
        CHECK(code_of([&] { zcis_price(good, c, 1.0, 0.02, 1e6, x, make_date(2025, 1, 2)); }) == "E_DOMAIN");
        CHECK(code_of([&] { linker_price(bond(), make_date(2024, 3, 1), x, 290.0, {}); }) == "E_DOMAIN");
        CHECK(code_of([&] { linker_price(bond(), make_date(2024, 3, 1), 0.01, 290.0, {{base, x}}); }) == "E_DOMAIN");
        CHECK(code_of([&] { linker_price_curve(bond(), make_date(2024, 3, 1), x, good, c); }) == "E_DOMAIN");
    }
}

TEST_CASE("finite rates: compounding and money") {
    const Compounding cont{CompoundingKind::Continuous, std::nullopt};
    for (const double x : bad_values()) {
        CHECK(code_of([&] { discount_factor(x, 1.0, cont); }) == "E_DOMAIN");
        CHECK(code_of([&] { discount_factor(0.05, x, cont); }) == "E_DOMAIN");
        CHECK(code_of([&] { convert_rate(x, 1.0, cont, cont); }) == "E_DOMAIN");
        CHECK(code_of([&] { convert_rate(0.05, x, cont, cont); }) == "E_DOMAIN");
        CHECK(code_of([&] { convert_unit(x, RateUnit::Percent, RateUnit::Bp); }) == "E_DOMAIN");
    }
    CHECK(discount_factor(0.05, 0.0, cont) == discount_factor(0.05, -0.0, cont));
    CHECK(discount_factor(0.0, 2.0, cont) == discount_factor(-0.0, 2.0, cont));
    CHECK(convert_rate(0.0, 2.0, cont, cont) == convert_rate(-0.0, 2.0, cont, cont));
    CHECK(convert_unit(0.0, RateUnit::Percent, RateUnit::Bp) == convert_unit(-0.0, RateUnit::Percent, RateUnit::Bp));
}

TEST_CASE("finite rates: calibration and hedging") {
    for (const double x : bad_values()) {
        FitInputs in{.model = FitModel::Linear, .x = {1.0, 2.0, 3.0}, .y = {1.0, 2.0, x}, .start = {0.0, 1.0}, .method = FitMethod::GaussNewton};
        CHECK(code_of([&] { fit(in); }) == "E_DOMAIN");
        in.y = {1.0, 2.0, 3.0};
        in.regularisation = x;
        CHECK(code_of([&] { fit(in); }) == "E_DOMAIN");
        in.regularisation = 0.0;
        in.lower = std::vector<double>{x, 0.0};
        CHECK(code_of([&] { fit(in); }) == "E_DOMAIN");
        CHECK(code_of([&] { check_bid_ask({x}, {0.0}, {1.0}); }) == "E_DOMAIN");
        CHECK(code_of([&] { check_bid_ask({0.5}, {0.0}, {x}); }) == "E_DOMAIN");
        auto q = ois_quotes();
        q[2].rate = x;
        CHECK(code_of([&] { curve_report(sofr(), as_of(), q, CurveInterpolation::LogLinearDf); }) == "E_DOMAIN");
        CHECK(code_of([&] { hedge_solve({{1.0, x}}, {1.0}, {1.0}, {0.0, 0.0}, 0.0); }) == "E_DOMAIN");
        CHECK(code_of([&] { hedge_solve({{1.0}}, {1.0}, {1.0}, {0.0}, x); }) == "E_DOMAIN");
        CHECK(code_of([&] { spread_cost({x}, {0.01}); }) == "E_DOMAIN");
        CHECK(code_of([&] { spread_cost({1.0}, {x}); }) == "E_DOMAIN");
    }
    CHECK(spread_cost({0.0}, {0.01}) == spread_cost({-0.0}, {0.01}));
    CHECK(spread_cost({1.0}, {0.0}) == spread_cost({1.0}, {-0.0}));
}

TEST_CASE("finite rates: credit") {
    const Curve c = flat_curve();
    for (const double x : bad_values()) {
        const HazardCurve bad{as_of(), {make_date(2029, 1, 2)}, {x}};
        CHECK(code_of([&] { bad.check(); }) == "E_DOMAIN");
        const HazardCurve h{as_of(), {make_date(2029, 1, 2)}, {0.9}};
        CHECK(code_of([&] {
                  cds_price(as_of(), c, h, x, make_date(2028, 12, 20), 0.01, 1e6, CdsSide::Buy, CdsPayout::Standard);
              }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  cds_price(as_of(), c, h, 0.4, make_date(2028, 12, 20), x, 1e6, CdsSide::Buy, CdsPayout::Standard);
              }) == "E_DOMAIN");
        CHECK(code_of([&] {
                  cds_price(as_of(), c, h, 0.4, make_date(2028, 12, 20), 0.01, x, CdsSide::Buy, CdsPayout::Standard);
              }) == "E_DOMAIN");
        CHECK(code_of([&] { cds_bootstrap(as_of(), c, x, {{Tenor{5, 'Y'}, 0.01}}); }) == "E_DOMAIN");
        CHECK(code_of([&] { cds_bootstrap(as_of(), c, 0.4, {{Tenor{5, 'Y'}, x}}); }) == "E_DOMAIN");
    }
}

TEST_CASE("finite rates: commodity and mbs") {
    const Curve c = flat_curve();
    for (const double x : bad_values()) {
        CHECK(code_of([&] { commodity_forwards({{24300, x}}, std::nullopt, {24300}); }) == "E_DOMAIN");
        CHECK(code_of([&] { commodity_forwards({{24300, 80.0}}, std::vector<double>(12, x), {24300}); }) == "E_DOMAIN");
        CHECK(code_of([&] { storage_carry(c, {{make_date(2024, 3, 1), 80.0}, {make_date(2024, 6, 1), x}}, 0.01); }) == "E_DOMAIN");
        CHECK(code_of([&] { storage_carry(c, {{make_date(2024, 3, 1), 80.0}, {make_date(2024, 6, 1), 81.0}}, x); }) == "E_DOMAIN");
        MbsPool p = pool();
        p.wac = x;
        CHECK(code_of([&] { mbs_cashflows(p); }) == "E_DOMAIN");
        p = pool();
        p.rate_or_speed = x;
        CHECK(code_of([&] { mbs_cashflows(p); }) == "E_DOMAIN");
        CHECK(code_of([&] { mbs_price(pool(), x, 0); }) == "E_DOMAIN");
    }
    const std::vector<DatedPrice> f{{make_date(2024, 3, 1), 80.0}, {make_date(2024, 6, 1), 81.0}};
    CHECK(storage_carry(c, f, 0.0).carry_values == storage_carry(c, f, -0.0).carry_values);
    CHECK(mbs_price(pool(), 0.0, 0).price == mbs_price(pool(), -0.0, 0).price);
    MbsPool z = pool();
    z.rate_or_speed = -0.0;
    MbsPool zp = pool();
    zp.rate_or_speed = 0.0;
    CHECK(mbs_cashflows(z).wal == mbs_cashflows(zp).wal);
}

TEST_CASE("finite rates: risk") {
    const Curve c = flat_curve();
    const CurvePricer price = [](const Curve& k) { return k.discount(make_date(2026, 1, 2)); };
    for (const double x : bad_values()) {
        CHECK(code_of([&] { check_bump(x); }) == "E_DOMAIN");
        auto q = ois_quotes();
        q[0].rate = x;
        CHECK(code_of([&] { par_risk(sofr(), as_of(), q, CurveInterpolation::LogLinearDf, price, 1.0, BumpScheme::Central); }) ==
              "E_DOMAIN");
        CHECK(code_of([&] {
                  par_risk(sofr(), as_of(), ois_quotes(), CurveInterpolation::LogLinearDf, price, x, BumpScheme::Central);
              }) == "E_DOMAIN");
        CHECK(code_of([&] { key_rate_risk(c, KeyRateMode::Pillar, {}, price, x, BumpScheme::Central); }) == "E_DOMAIN");
        CHECK(code_of([&] { pnl_explain(sofr(), as_of(), ois_quotes(), q, CurveInterpolation::LogLinearDf, price, 1.0, 1e6); }) ==
              "E_DOMAIN");
        CHECK(code_of([&] {
                  pnl_explain(sofr(), as_of(), ois_quotes(), ois_quotes(), CurveInterpolation::LogLinearDf, price, 1.0, x);
              }) == "E_DOMAIN");
        CHECK(code_of([&] { zero_jacobian(sofr(), as_of(), q, CurveInterpolation::LogLinearDf, 1.0); }) == "E_DOMAIN");
    }
    const PnlExplain p = pnl_explain(sofr(), as_of(), ois_quotes(), ois_quotes(), CurveInterpolation::LogLinearDf, price, 1.0, 0.0);
    const PnlExplain m = pnl_explain(sofr(), as_of(), ois_quotes(), ois_quotes(), CurveInterpolation::LogLinearDf, price, 1.0, -0.0);
    CHECK(p.threshold == m.threshold);
    CHECK(p.explained == m.explained);
}
