#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/calibration.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/fx.hpp"
#include "quantforge/core/money.hpp"
#include "quantforge/core/rates.hpp"

using namespace quantforge;
using Catch::Approx;
using Vec = std::vector<double>;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
std::vector<OisQuote> sample_quotes() {
    return {{{1, 'W'}, 0.0372}, {{3, 'M'}, 0.0368}, {{1, 'Y'}, 0.035}, {{2, 'Y'}, 0.0335}, {{5, 'Y'}, 0.0335}, {{10, 'Y'}, 0.036}};
}
}  // namespace

TEST_CASE("money is exact") {
    CHECK(format_shortest(parse_amount("1.50") + parse_amount("-1.5")) == "0");
    CHECK(format_shortest(parse_amount("0.1") + parse_amount("0.2")) == "0.3");
    CHECK(round_to_places(parse_amount("2.675"), 2) == "2.68");
    CHECK(round_to_places(parse_amount("2.665"), 2) == "2.66");
    CHECK(round_to_places(parse_amount("-0.001"), 2) == "0.00");
    CHECK(round_to_places(parse_amount("1000.5"), 0) == "1000");
    CHECK(classify_amount("1e3") == AmountForm::Malformed);
    CHECK(classify_amount("1.") == AmountForm::Malformed);
    CHECK(classify_amount("1234567890123456789") == AmountForm::TooManyDigits);
    CHECK(convert_unit(5.0, RateUnit::Percent, RateUnit::Bp) == Approx(500.0));
}

TEST_CASE("schedules stub first and drop what adjusts onto start") {
    const auto p = generate_schedule(d("2026-01-15"), d("2027-03-15"), 12, Calendar::Gblo, false, 0);
    REQUIRE(p.size() == 2);
    CHECK(p[0].start == d("2026-01-15"));
    CHECK(p[0].end == d("2026-03-16"));
    CHECK(generate_schedule(d("2027-02-26"), d("2027-02-28"), 1, Calendar::Gblo, false, 0).empty());
    CHECK(code_of([] { generate_schedule(d("2027-01-01"), d("2026-01-01"), 3, Calendar::Gblo, false, 0); }) == "E_DATE_ORDER");
}

TEST_CASE("curves interpolate and extrapolate") {
    const Curve c(d("2026-01-01"), CurveInterpolation::LogLinearDf, {{d("2027-01-01"), 0.96}, {d("2028-01-01"), 0.92}});
    CHECK(c.discount(d("2026-01-01")) == 1.0);
    CHECK(c.discount(d("2027-01-01")) == Approx(0.96));
    CHECK(c.discount(d("2026-07-02")) == Approx(std::exp(std::log(0.96) * 182.0 / 365.0)));
    CHECK(code_of([&] { c.discount(d("2025-12-31")); }) == "E_OUT_OF_RANGE");
    const Curve z(d("2026-01-01"), CurveInterpolation::LinearZero, {{d("2027-01-01"), 0.96}});
    CHECK(-std::log(z.discount(d("2026-04-01"))) / z.time(d("2026-04-01")) == Approx(-std::log(0.96)));
}

TEST_CASE("both bootstraps reprice below 1e-13 and agree") {
    const RateConvention& sofr = *rate_convention("SOFR");
    for (const auto interpolation : {CurveInterpolation::LogLinearDf, CurveInterpolation::LinearZero}) {
        const auto s = ois_bootstrap(sofr, d("2026-11-06"), sample_quotes(), interpolation, SolveMethod::Sequential);
        const auto g = ois_bootstrap(sofr, d("2026-11-06"), sample_quotes(), interpolation, SolveMethod::Global);
        CHECK(s.max_repricing_error < 1e-13);
        CHECK(g.max_repricing_error < 1e-13);
        for (std::size_t i = 0; i < s.curve.size(); ++i) CHECK(s.curve.log_df(i) == Approx(g.curve.log_df(i)).margin(1e-12));
    }
}

TEST_CASE("the OIS floating leg is the general form") {
    const RateConvention& sofr = *rate_convention("SOFR");
    const Curve c = ois_bootstrap(sofr, d("2026-11-06"), sample_quotes(), CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const auto periods = ois_periods(sofr, d("2026-11-06"), {10, 'Y'});
    const double telescoped = c.discount(periods.front().start) - c.discount(periods.back().end);
    CHECK(std::fabs(ois_legs(sofr, periods, c).floating - telescoped) > 1e-5);
}

TEST_CASE("a par trade is worth nothing, and key rates sum to the DV01") {
    const RateConvention& sonia = *rate_convention("SONIA");
    const auto q = sample_quotes();
    const Curve c = ois_bootstrap(sonia, d("2026-11-06"), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    OisTrade t{&sonia, {5, 'Y'}, 0.0335, 1e6, FixedSide::Pay};
    CHECK(ois_price(t, c).valuation.pv == Approx(0.0).margin(1e-6));
    t.fixed_rate = 0.03;
    const RateRisk r = rate_risk(t, bumped_curves(sonia, d("2026-11-06"), q, CurveInterpolation::LogLinearDf));
    double sum = 0.0;
    for (const double v : r.key_rate) sum += v;
    CHECK(sum == Approx(r.dv01).epsilon(1e-5));
    CHECK(r.dv01 > 0.0);
}

TEST_CASE("compounding in arrears") {
    CHECK(ois_compound({0.05}, {1}, 365) == Approx(0.05));
    CHECK(code_of([] { ois_compound({0.05}, {0}, 365); }) == "E_INPUT");
}

TEST_CASE("projection reprices, and equal curves leave no basis") {
    const RateConvention& index = *rate_convention("USD-TERM-3M");
    const Curve disc(d("2026-11-06"), CurveInterpolation::LogLinearDf, {{d("2036-11-06"), 0.7}});
    double error = 1.0;
    const Curve p = projection_bootstrap(disc, index, d("2026-11-06"),
                                         {{ProjectionQuoteType::Deposit, 3, 0.04}, {ProjectionQuoteType::Fra, 3, 0.041}, {ProjectionQuoteType::Swap, 24, 0.042}},
                                         CurveInterpolation::LogLinearDf, &error);
    CHECK(error < 1e-13);
    const SwapTrade t{&index, 24, 0.042, 1e6, FixedSide::Pay};
    CHECK(swap_price(t, disc, p).valuation.pv == Approx(0.0).margin(1e-6));
    CHECK(basis_spread(disc, disc, index, 24) == Approx(0.0).margin(1e-15));
}

TEST_CASE("FX forward parity and delta") {
    const FxPair& pair = *fx_pair("GBPUSD");
    const Date as_of = d("2026-11-06");
    CHECK(fx_spot_date(pair, as_of) == d("2026-11-10"));
    const Curve base(as_of, CurveInterpolation::LogLinearDf, {{d("2036-11-06"), 0.7}});
    const Curve quote(as_of, CurveInterpolation::LogLinearDf, {{d("2036-11-06"), 0.6}});
    const auto pv = [&](double s) {
        return fx_forward_price({&pair, s, as_of, &base, &quote}, {1e6, 1.3, d("2027-11-10"), FxSide::Buy});
    };
    const double bump = (pv(1.2801).valuation.pv - pv(1.2799).valuation.pv) / 0.0002;
    CHECK(pv(1.28).fx_delta == Approx(bump).epsilon(1e-8));
    CHECK(fx_outright({&pair, 1.28, as_of, &base, &quote}, d("2026-11-10")).forward == Approx(1.28));
}

TEST_CASE("the three solvers find the same minimum") {
    FitInputs f;
    f.model = FitModel::Exponential;
    for (const double x : {0.25, 0.5, 1.0, 2.0, 3.0, 5.0}) {
        f.x.push_back(x);
        f.y.push_back(3.0 * std::exp(-0.4 * x));
    }
    f.start = {2.0, 0.3};
    for (const FitMethod m : {FitMethod::GaussNewton, FitMethod::LevenbergMarquardt, FitMethod::Bfgs}) {
        f.method = m;
        const FitResult r = fit(f);
        CHECK(r.parameters[0] == Approx(3.0).margin(1e-6));
        CHECK(r.objective < 1e-12);
    }
}

TEST_CASE("BFGS on Rosenbrock, and a bound held") {
    FitInputs f;
    f.model = FitModel::Rosenbrock;
    f.start = {-1.2, 1.0};
    f.method = FitMethod::Bfgs;
    CHECK(fit(f).parameters[1] == Approx(1.0).margin(1e-6));
    FitInputs b;
    b.model = FitModel::Linear;
    b.x = {0, 1, 2};
    b.y = {1, 3, 5};
    b.start = {0, 0};
    b.method = FitMethod::LevenbergMarquardt;
    b.upper = Vec{100.0, 1.5};
    b.lower = Vec{-100.0, -100.0};
    const FitResult r = fit(b);
    CHECK(r.parameters[1] == 1.5);
    CHECK(r.parameters[0] == Approx(1.5).margin(1e-6));
}

TEST_CASE("the hedge meets its first-order conditions") {
    const Matrix a{{1.0, 0.2}, {0.3, 1.0}, {0.1, 0.4}};
    const Vec b{10.0, -4.0, 1.0}, w{1.0, 2.0, 1.0}, c{0.5, 30.0};
    const HedgeResult h = hedge_solve(a, b, w, c, 1.0);
    for (std::size_t i = 0; i < 2; ++i) {
        double g = 0.0;
        for (std::size_t r = 0; r < 3; ++r) g += 2.0 * w[r] * a[r][i] * h.residual[r];
        if (h.x[i] != 0.0) CHECK(g + c[i] * (h.x[i] > 0 ? 1.0 : -1.0) == Approx(0.0).margin(1e-9));
        else CHECK(std::fabs(g) <= c[i]);
    }
    CHECK(code_of([] { hedge_solve({{1, 1}, {1, 1}}, {1, 2}, {1, 1}, {0, 0}, 0); }) == "E_SINGULAR");
}

TEST_CASE("spot counts from as_of itself") {
    const auto p = ois_periods(*rate_convention("SOFR"), d("2026-11-07"), {1, 'W'});
    CHECK(p[0].start == d("2026-11-10"));
    CHECK(code_of([] { Curve(d("2026-01-01"), CurveInterpolation::LogLinearDf, std::vector<Pillar>{}); }) == "E_INPUT");
}

TEST_CASE("cashflow risk") {
    const auto r = cashflow_risk({{2.0, 100.0}}, 0.05);
    CHECK(r.duration == Approx(2.0));
    CHECK(r.convexity == Approx(4.0));
    CHECK(code_of([] { cashflow_risk({{1.0, 1.0}, {1.0, -1.0}}, 0.0); }) == "E_DOMAIN");
}
