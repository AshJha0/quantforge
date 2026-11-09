#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/multicurve.hpp"

using namespace quantforge;
using Catch::Approx;
using Vec = std::vector<double>;

namespace {
Date d(const char* s) { return *parse_date(s); }
Date plus(Date x, int n) { return Date(x + std::chrono::days(n)); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
const RateConvention& sofr_conv() { static const RateConvention& c = *rate_convention("SOFR"); return c; }
const RateConvention& estr_conv() { static const RateConvention& c = *rate_convention("ESTR"); return c; }
// SOFR fixings on 2026-11-12 .. 2026-11-20, rate 0.04 + day/10000.
std::vector<Fixing> fixings() {
    std::vector<Fixing> f;
    for (int day = 12; day <= 20; ++day) f.push_back({plus(d("2026-11-01"), day - 1), 0.04 + day / 10000.0});
    return f;
}
double fix(int day) { return 0.04 + day / 10000.0; }
}  // namespace

TEST_CASE("ESTR is a listed overnight convention") {
    CHECK(estr_conv().calendar == Calendar::Euta);
    CHECK(estr_conv().spot_lag == 2);
    CHECK(estr_conv().payment_lag == 2);
    CHECK(estr_conv().denominator == 360.0);
    const auto p = ois_periods(estr_conv(), d("2026-11-06"), {1, 'Y'});
    REQUIRE(p.size() == 1);
    CHECK(p[0].start == d("2026-11-10"));
    CHECK(p[0].payment == add_business_days(Calendar::Euta, p[0].end, 2));
}

TEST_CASE("curve jumps apply strictly after their date") {
    const Date as_of = d("2026-11-06");
    const std::vector<Jump> jumps{{d("2026-12-31"), 0.999}};
    const Curve c(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}, {d("2028-11-06"), 0.92}}, jumps);
    CHECK(c.discount(d("2027-11-06")) == Approx(0.96).epsilon(1e-15));
    CHECK(c.pillars()[0].discount_factor == Approx(0.96).epsilon(1e-15));
    const double s = 0.96 / 0.999;  // jump-free node
    const auto smooth = [&](Date x) { return std::exp(c.time(x) / c.time(d("2027-11-06")) * std::log(s)); };
    CHECK(c.discount(d("2026-12-31")) == Approx(smooth(d("2026-12-31"))).epsilon(1e-14));
    CHECK(c.discount(d("2027-01-01")) == Approx(smooth(d("2027-01-01")) * 0.999).epsilon(1e-14));
    CHECK(code_of([&] { Curve(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}}, {{as_of, 0.99}}); }) == "E_INPUT");
    CHECK(code_of([&] {
              Curve(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}},
                    {{d("2027-01-02"), 0.99}, {d("2027-01-01"), 0.99}});
          }) == "E_INPUT");
    CHECK(code_of([&] { Curve(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}}, {{d("2027-01-01"), 0.0}}); }) == "E_DOMAIN");
}

TEST_CASE("ESTR bootstrap with a jump reprices, both methods agree") {
    const std::vector<OisQuote> q{{{1, 'M'}, 0.022}, {{6, 'M'}, 0.021}, {{1, 'Y'}, 0.02}, {{2, 'Y'}, 0.019}, {{5, 'Y'}, 0.02}};
    const std::vector<Jump> jumps{{d("2026-12-31"), std::exp(-0.002 / 365.0)}};
    const auto a = ois_bootstrap(estr_conv(), d("2026-11-06"), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential, jumps);
    const auto b = ois_bootstrap(estr_conv(), d("2026-11-06"), q, CurveInterpolation::LinearZero, SolveMethod::Global, jumps);
    CHECK(a.max_repricing_error < 1e-13);
    CHECK(b.max_repricing_error < 1e-13);
    for (std::size_t j = 0; j < q.size(); ++j)
        CHECK(ois_legs(estr_conv(), ois_periods(estr_conv(), d("2026-11-06"), q[j].tenor), a.curve).par() == Approx(q[j].rate).margin(1e-13));
    const auto plain = ois_bootstrap(estr_conv(), d("2026-11-06"), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential);
    CHECK(plain.curve.pillars()[2].discount_factor != a.curve.pillars()[2].discount_factor);
    CHECK(code_of([&] {
              ois_bootstrap(estr_conv(), d("2026-11-06"), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential, {{d("2026-12-31"), -1.0}});
          }) == "E_DOMAIN");
}

TEST_CASE("dated compounding by method") {
    const Date mon = d("2026-11-16"), tue = d("2026-11-17"), thu = d("2026-11-19");
    auto r = compound_dated(sofr_conv(), mon, tue, ShiftMethod::None, 0, fixings());
    CHECK(r.compounded_rate == Approx(fix(16)).margin(1e-12));
    CHECK(r.accrual == Approx(1.0 / 360.0).epsilon(1e-15));
    CHECK(r.interest == Approx(fix(16) / 360.0).margin(1e-14));
    r = compound_dated(sofr_conv(), mon, tue, ShiftMethod::Lookback, 1, fixings());
    CHECK(r.compounded_rate == Approx(fix(13)).margin(1e-12));
    // Observation shift: one step from Friday 13 to Monday 16, weighted 3 days, still the one rate.
    r = compound_dated(sofr_conv(), mon, tue, ShiftMethod::ObservationShift, 1, fixings());
    CHECK(r.compounded_rate == Approx(fix(13)).margin(1e-12));
    // Lockout k = 2 over 3 steps: the fixing of d_1 applies to steps 1 and 2.
    r = compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lockout, 2, fixings());
    const double g = (1 + fix(16) / 360) * (1 + fix(17) / 360) * (1 + fix(17) / 360);
    CHECK(r.compounded_rate == Approx((g - 1) * 360 / 3).epsilon(1e-14));
    // Lockout k = 1 is the plain rate (ARRC rule, ruling D3).
    CHECK(compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lockout, 1, fixings()).compounded_rate ==
          compound_dated(sofr_conv(), mon, thu, ShiftMethod::None, 0, fixings()).compounded_rate);
    // A weekend step weighs 3 days.
    r = compound_dated(sofr_conv(), d("2026-11-13"), mon, ShiftMethod::None, 0, fixings());
    CHECK(r.compounded_rate == Approx(fix(13)).margin(1e-12));
    CHECK(r.accrual == Approx(3.0 / 360.0).epsilon(1e-15));
}

TEST_CASE("dated compounding checks, in order") {
    const Date mon = d("2026-11-16"), thu = d("2026-11-19");
    const auto f = fixings();
    CHECK(code_of([&] { compound_dated(*rate_convention("USD-TERM-3M"), mon, thu, ShiftMethod::None, 0, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), thu, mon, ShiftMethod::None, 0, f); }) == "E_DATE_ORDER");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, mon, ShiftMethod::None, 0, f); }) == "E_DATE_ORDER");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lookback, -1, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::None, 1, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lockout, 0, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lockout, 3, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), d("2026-11-14"), thu, ShiftMethod::None, 0, f); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, d("2026-11-22"), ShiftMethod::None, 0, f); }) == "E_INPUT");
    auto dup = f;
    dup.push_back(f[0]);
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::None, 0, dup); }) == "E_INPUT");
    CHECK(code_of([&] { compound_dated(sofr_conv(), mon, thu, ShiftMethod::Lookback, 5, f); }) == "E_INPUT");  // fixing missing
    auto extra = f;
    extra.push_back({d("2020-01-02"), 9.0});
    CHECK(compound_dated(sofr_conv(), mon, thu, ShiftMethod::None, 0, extra).compounded_rate ==
          compound_dated(sofr_conv(), mon, thu, ShiftMethod::None, 0, f).compounded_rate);
}

TEST_CASE("IBOR fallback adds the ISDA spread to a 2-day shifted compound") {
    const auto r = fallback_rate("USD-LIBOR-3M", d("2026-11-17"), d("2026-11-19"), fixings());
    const auto c = compound_dated(sofr_conv(), d("2026-11-17"), d("2026-11-19"), ShiftMethod::ObservationShift, 2, fixings());
    CHECK(r.compounded_rate == c.compounded_rate);
    CHECK(r.spread_adjustment == 0.0026161);
    CHECK(r.fallback_rate == c.compounded_rate + 0.0026161);
    CHECK(fallback_rate("USD-LIBOR-12M", d("2026-11-17"), d("2026-11-19"), fixings()).spread_adjustment == 0.0071513);
    CHECK(code_of([] { fallback_rate("EUR-EURIBOR-3M", d("2026-11-17"), d("2026-11-19"), fixings()); }) == "E_SCHEMA");
    CHECK(fallback_rate("GBP-LIBOR-3M", d("2026-11-17"), d("2026-11-19"), fixings()).spread_adjustment == 0.0011930);
}

TEST_CASE("step curve integrates a flat forward per step, jumps after their date") {
    const Date as_of = d("2026-11-06");
    StepCurve sc{as_of, 0.04, {{plus(as_of, 73), 0.02}}, {{plus(as_of, 10), 0.99}}};
    sc.check();
    CHECK(sc.discount(as_of) == 1.0);
    CHECK(sc.discount(plus(as_of, 10)) == Approx(std::exp(-0.04 * 10 / 365.0)).epsilon(1e-15));
    CHECK(sc.discount(plus(as_of, 11)) == Approx(std::exp(-0.04 * 11 / 365.0) * 0.99).epsilon(1e-15));
    CHECK(sc.discount(plus(as_of, 146)) == Approx(std::exp(-(0.04 * 0.2 + 0.02 * 0.2)) * 0.99).epsilon(1e-15));
    CHECK(sc.forward(plus(as_of, 72)) == 0.04);
    CHECK(sc.forward(plus(as_of, 73)) == 0.02);
    CHECK(code_of([&] { sc.discount(plus(as_of, -1)); }) == "E_OUT_OF_RANGE");
    CHECK(code_of([&] { StepCurve{as_of, 0.04, {{as_of, 0.02}}, {}}.check(); }) == "E_INPUT");
    CHECK(code_of([&] { StepCurve{as_of, 0.04, {{plus(as_of, 9), 0.02}, {plus(as_of, 9), 0.01}}, {}}.check(); }) == "E_INPUT");
    CHECK(code_of([&] { StepCurve{as_of, 0.04, {}, {{plus(as_of, 9), 0.0}}}.check(); }) == "E_DOMAIN");
}

TEST_CASE("step fit recovers the rates behind OIS par quotes") {
    const Date as_of = d("2026-11-06");
    const std::vector<Date> steps{d("2026-12-10"), d("2027-01-28"), d("2027-03-18")};
    const StepCurve truth{as_of, 0.0425, {{steps[0], 0.04}, {steps[1], 0.038}, {steps[2], 0.0365}}, {{d("2026-12-31"), 0.9999}}};
    const std::vector<Tenor> tenors{{3, 'W'}, {2, 'M'}, {3, 'M'}, {6, 'M'}};
    std::vector<OisQuote> q;
    for (const Tenor t : tenors)
        q.push_back({t, ois_legs(sofr_conv(), ois_periods(sofr_conv(), as_of, t), [&](Date x) { return truth.discount(x); }).par()});
    const StepFit f = fit_steps(sofr_conv(), as_of, steps, q, truth.jumps);
    CHECK(f.base_rate == Approx(0.0425).margin(1e-12));
    CHECK(f.step_rates[0] == Approx(0.04).margin(1e-12));
    CHECK(f.step_rates[1] == Approx(0.038).margin(1e-12));
    CHECK(f.step_rates[2] == Approx(0.0365).margin(1e-12));
    CHECK(f.max_repricing_error < 1e-13);
    CHECK(code_of([&] { fit_steps(sofr_conv(), as_of, steps, {q[0], q[1], q[2]}, {}); }) == "E_INPUT");
    CHECK(code_of([&] { fit_steps(sofr_conv(), as_of, {}, {q[0]}, {}); }) == "E_INPUT");
    auto swapped = q;
    std::swap(swapped[1], swapped[2]);
    CHECK(code_of([&] { fit_steps(sofr_conv(), as_of, steps, swapped, {}); }) == "E_INPUT");  // pillar rule
    CHECK(code_of([&] { fit_steps(sofr_conv(), as_of, steps, q, {{as_of, 0.99}}); }) == "E_INPUT");
    CHECK(code_of([&] { fit_steps(*rate_convention("USD-TERM-3M"), as_of, steps, q, {}); }) == "E_INPUT");
}

TEST_CASE("futures convexity, Hull-White") {
    const auto r = futures_convexity(96.0, 0.25, 0.5, 0.01, 0.0);
    CHECK(r.futures_rate == Approx(0.04).epsilon(1e-15));
    const double t = 0.25, dd = 0.25, z = 0.01 * 0.01 / 2 * (2 * t * dd * dd + dd * t * t);
    CHECK(r.convexity == Approx(-std::expm1(-z) * (0.04 + 1 / dd)).epsilon(1e-14));
    CHECK(r.forward_rate == r.futures_rate - r.convexity);
    // The a -> 0 limit is continuous.
    CHECK(futures_convexity(96.0, 0.25, 0.5, 0.01, 1e-9).convexity == Approx(r.convexity).epsilon(1e-7));
    CHECK(futures_convexity(96.0, 0.25, 0.5, 0.0, 0.03).convexity == 0.0);
    CHECK(code_of([] { futures_convexity(96, 0.5, 0.5, 0.01, 0.03); }) == "E_INPUT");
    CHECK(code_of([] { futures_convexity(96, -0.1, 0.5, 0.01, 0.03); }) == "E_DOMAIN");
    CHECK(code_of([] { futures_convexity(96, 0.1, 0.5, -0.01, 0.03); }) == "E_DOMAIN");
    CHECK(code_of([] { futures_convexity(96, 0.1, 0.5, 0.01, -0.03); }) == "E_DOMAIN");
}

TEST_CASE("CSA discounting") {
    const Date as_of = d("2026-11-06");
    const Curve c(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}, {d("2031-11-06"), 0.82}});
    const Date x = d("2028-11-06");
    CHECK(csa_discount(c, 0.0, std::nullopt, {x})[0] == c.discount(x));
    CHECK(csa_discount(c, 0.01, std::nullopt, {x})[0] == Approx(c.discount(x) * std::exp(-0.01 * c.time(x))).epsilon(1e-15));
    const CsaFx fx{1.10, {{x, 1.12}}};
    CHECK(csa_discount(c, 0.0, fx, {x})[0] == Approx(c.discount(x) * 1.10 / 1.12).epsilon(1e-15));
    CHECK(code_of([&] { csa_discount(c, 0.0, CsaFx{0.0, {{x, 1.12}}}, {x}); }) == "E_DOMAIN");
    CHECK(code_of([&] { csa_discount(c, 0.0, CsaFx{1.1, {{x, -1.0}}}, {x}); }) == "E_DOMAIN");
    CHECK(code_of([&] { csa_discount(c, 0.0, fx, {d("2029-01-01")}); }) == "E_INPUT");
    CHECK(code_of([&] { csa_discount(c, 0.0, CsaFx{1.1, {{x, 1.1}, {x, 1.2}}}, {x}); }) == "E_INPUT");
    CHECK(code_of([&] { csa_discount(c, 0.0, std::nullopt, {d("2026-11-05")}); }) == "E_OUT_OF_RANGE");
}

TEST_CASE("OIS index basis and joint bootstrap") {
    const Date as_of = d("2026-11-06");
    const Curve disc(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}, {d("2031-11-06"), 0.82}});
    const Curve other(as_of, CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.958}, {d("2031-11-06"), 0.815}});
    CHECK(ois_index_spread(sofr_conv(), {2, 'Y'}, disc, disc, disc) == 0.0);
    const auto p = ois_periods(sofr_conv(), as_of, {2, 'Y'});
    const double par_a = ois_legs(sofr_conv(), p, other).par();  // single curve: projection = discount
    CHECK(ois_index_spread(sofr_conv(), {2, 'Y'}, other, other, other) == 0.0);
    CHECK(ois_index_spread(sofr_conv(), {2, 'Y'}, disc, other, disc) > 0.0);
    (void)par_a;
    const Curve shifted(d("2026-11-05"), CurveInterpolation::LogLinearDf, {{d("2027-11-06"), 0.96}});
    CHECK(code_of([&] { ois_index_spread(sofr_conv(), {2, 'Y'}, disc, shifted, disc); }) == "E_INPUT");

    const std::vector<OisQuote> oq{{{1, 'M'}, 0.0386}, {{1, 'Y'}, 0.0365}, {{2, 'Y'}, 0.035}, {{5, 'Y'}, 0.035}};
    const std::vector<ProjectionQuote> tq{{ProjectionQuoteType::Deposit, 3, 0.0395},
                                          {ProjectionQuoteType::Fra, 3, 0.0385},
                                          {ProjectionQuoteType::Swap, 24, 0.037}};
    const auto& term = *rate_convention("USD-TERM-3M");
    const auto a = joint_bootstrap(sofr_conv(), term, as_of, oq, tq, CurveInterpolation::LogLinearDf, SolveMethod::Sequential);
    const auto b = joint_bootstrap(sofr_conv(), term, as_of, oq, tq, CurveInterpolation::LogLinearDf, SolveMethod::Global);
    CHECK(a.max_repricing_error < 1e-13);
    for (std::size_t i = 0; i < tq.size(); ++i)
        CHECK(a.projection.pillars()[i].discount_factor == Approx(b.projection.pillars()[i].discount_factor).margin(1e-12));
    CHECK(code_of([&] { joint_bootstrap(sofr_conv(), term, as_of, oq, {}, CurveInterpolation::LogLinearDf, SolveMethod::Sequential); }) == "E_INPUT");
    CHECK(code_of([&] { joint_bootstrap(sofr_conv(), term, as_of, {}, tq, CurveInterpolation::LogLinearDf, SolveMethod::Sequential); }) == "E_INPUT");
}

TEST_CASE("smooth forward fit") {
    auto f = smooth_fit({1, 2}, {1, 2}, {0.03, 0.04}, 0.0, std::nullopt);
    CHECK(f.forwards[0] == Approx(0.03).margin(1e-15));
    CHECK(f.forwards[1] == Approx(0.05).margin(1e-15));
    CHECK(f.objective == Approx(0.0).margin(1e-28));
    f = smooth_fit({1, 2}, {1, 2}, {0.03, 0.04}, 1e9, std::nullopt);
    CHECK(f.forwards[0] == Approx(f.forwards[1]).margin(1e-9));
    // Weight 0 on the second point leaves it free: the penalty pulls f_2 to f_1.
    f = smooth_fit({1, 2}, {1, 2}, {0.03, 0.04}, 1.0, Vec{1, 0});
    CHECK(f.forwards[1] == Approx(0.03).margin(1e-14));
    CHECK(code_of([] { smooth_fit({1}, {}, {}, 0, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({1}, {1}, {0.03, 0.04}, 0, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({1}, {1}, {0.03}, 0, Vec{1, 1}); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({2, 1}, {1}, {0.03}, 0, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({0, 1}, {1}, {0.03}, 0, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({1}, {1}, {0.03}, -1, std::nullopt); }) == "E_DOMAIN");
    CHECK(code_of([] { smooth_fit({1}, {1}, {0.03}, 0, Vec{-1}); }) == "E_DOMAIN");
    CHECK(code_of([] { smooth_fit({1}, {0}, {0.03}, 0, std::nullopt); }) == "E_DOMAIN");
    CHECK(code_of([] { smooth_fit({1}, {1.5}, {0.03}, 0, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { smooth_fit({1, 2}, {1}, {0.03}, 0, std::nullopt); }) == "E_SINGULAR");
}

TEST_CASE("Huber Nelson-Siegel") {
    const Vec m{0.5, 1, 2, 3, 5, 7, 10, 20};
    const double tau = 2.0, b0 = 0.04, b1 = -0.01, b2 = 0.005;
    Vec y;
    for (const double x : m) {
        const double u = x / tau, e = -std::expm1(-u) / u;
        y.push_back(b0 + b1 * e + b2 * (e - std::exp(-u)));
    }
    auto r = robust_fit(m, y, tau, 1e-3);
    CHECK(r.betas[0] == Approx(b0).margin(1e-12));
    CHECK(r.betas[1] == Approx(b1).margin(1e-12));
    CHECK(r.betas[2] == Approx(b2).margin(1e-12));
    CHECK(r.outliers.empty());
    y[3] += 0.01;  // one outlier
    r = robust_fit(m, y, tau, 5e-4);
    REQUIRE(r.outliers.size() == 1);
    CHECK(r.outliers[0] == 3);
    // First-order optimality of the Huber objective.
    for (int k = 0; k < 3; ++k) {
        double g = 0.0;
        for (std::size_t j = 0; j < m.size(); ++j) {
            const double u = m[j] / tau, e = -std::expm1(-u) / u;
            const double xk = k == 0 ? 1.0 : k == 1 ? e : e - std::exp(-u);
            const double rj = r.residuals[j];
            g += (std::fabs(rj) <= 5e-4 ? rj : 5e-4 * (rj > 0 ? 1 : -1)) * xk;
        }
        CHECK(std::fabs(g) < 1e-15);
    }
    CHECK(code_of([] { robust_fit({1, 2}, {0.03, 0.04}, 1, 1e-3); }) == "E_INPUT");
    CHECK(code_of([] { robust_fit({1, 2, 3}, {0.03, 0.04}, 1, 1e-3); }) == "E_INPUT");
    CHECK(code_of([] { robust_fit({1, 2, 3}, {0.03, 0.04, 0.05}, 0, 1e-3); }) == "E_DOMAIN");
    CHECK(code_of([] { robust_fit({1, 2, 3}, {0.03, 0.04, 0.05}, 1, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { robust_fit({0, 2, 3}, {0.03, 0.04, 0.05}, 1, 1e-3); }) == "E_DOMAIN");
}

TEST_CASE("SOFR compounding skips every Good Friday (ruling R1-6)") {
    using namespace quantforge;
    const auto sofr = *rate_convention("SOFR");
    const Date gf = *parse_date("2021-04-02");  // a USGS business day, but no SOFR is published
    REQUIRE(is_business_day(Calendar::Usgs, gf));
    std::vector<Fixing> fx;
    for (Date x = *parse_date("2021-03-25"); x <= *parse_date("2021-04-09"); x = Date(x + std::chrono::days(1)))
        if (x != gf) fx.push_back({x, 0.0001});
    // Missing the Good Friday fixing is fine: the day is not a compounding date.
    const auto r = compound_dated(sofr, *parse_date("2021-03-31"), *parse_date("2021-04-06"), ShiftMethod::None, 0, fx);
    CHECK(r.compounded_rate > 0.0);
    CHECK_THROWS(compound_dated(sofr, gf, *parse_date("2021-04-06"), ShiftMethod::None, 0, fx));
}
