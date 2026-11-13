// Stage F wave 1a unit tests (curve_interp). No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/interp.hpp"
#include "quantforge/core/rates.hpp"

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

Date as_of() { return make_date(2026, 11, 9); }

std::vector<Pillar> pillars() {
    return {{make_date(2027, 5, 14), 0.979}, {make_date(2027, 11, 16), 0.961}, {make_date(2028, 11, 15), 0.929},
            {make_date(2031, 11, 14), 0.839}, {make_date(2036, 11, 14), 0.695}, {make_date(2056, 11, 15), 0.337}};
}

Curve curve(CurveInterpolation m, CurveShape s = {}) { return Curve(as_of(), m, pillars(), {}, s); }

std::vector<CurveInterpolation> stage_f_methods() {
    return {CurveInterpolation::MonotoneConvex, CurveInterpolation::MonotonicLogCubic,
            CurveInterpolation::TensionSpline, CurveInterpolation::Hybrid};
}

CurveShape full_shape() { return {0.5, make_date(2027, 11, 16)}; }

}  // namespace

TEST_CASE("stage F curves return their pillars and extrapolate flat", "[f][curve_interp]") {
    for (const CurveInterpolation m : stage_f_methods()) {
        const Curve c = curve(m, full_shape());
        for (const Pillar& p : pillars()) CHECK(std::fabs(c.discount(p.date) - p.discount_factor) < 1e-15);
        CHECK(c.discount(as_of()) == 1.0);
        const Date last = make_date(2056, 11, 15), later = make_date(2060, 11, 15);
        const double f = c.instantaneous_forward(last);
        CHECK(c.instantaneous_forward(later) == f);
        CHECK(std::fabs(std::log(c.discount(later) / c.discount(last)) + f * c.time(later) - f * c.time(last)) < 1e-12);
    }
}

TEST_CASE("stage F forwards are continuous at interior pillars", "[f][curve_interp]") {
    for (const CurveInterpolation m : {CurveInterpolation::MonotoneConvex, CurveInterpolation::MonotonicLogCubic}) {
        const Curve c = curve(m);
        for (std::size_t i = 0; i + 1 < pillars().size(); ++i) {
            const Date d = pillars()[i].date;
            const double left = c.instantaneous_forward(d - std::chrono::days(1));
            CHECK(std::fabs(c.instantaneous_forward(d) - left) < 2e-3);  // one day away: slope bound only
        }
    }
}

TEST_CASE("tension and step_end checks at their edges", "[f][curve_interp]") {
    using enum CurveInterpolation;
    CHECK(code_of([] { curve(TensionSpline); }) == "E_INPUT");
    CHECK(code_of([] { curve(TensionSpline, {0.0, {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { curve(TensionSpline, {-1e-300, {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { curve(TensionSpline, {1e-300, {}}); }) == "OK");
    CHECK(code_of([] { curve(TensionSpline, {1000.0, {}}); }) == "OK");
    CHECK(code_of([] { curve(TensionSpline, {std::nextafter(1000.0, 2000.0), {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { curve(TensionSpline, {std::numeric_limits<double>::quiet_NaN(), {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { curve(TensionSpline, {std::numeric_limits<double>::infinity(), {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { curve(Hybrid); }) == "E_INPUT");
    CHECK(code_of([] { curve(Hybrid, {{}, make_date(2027, 1, 1)}); }) == "E_INPUT");
    CHECK(code_of([] { curve(Hybrid, {{}, make_date(2027, 5, 14)}); }) == "OK");
    CHECK(code_of([] { curve(Hybrid, {{}, make_date(2056, 11, 15)}); }) == "OK");
    CHECK(code_of([] { curve(MonotoneConvex, {-5.0, make_date(2027, 1, 1)}); }) == "OK");  // ignored
    CHECK(code_of([] { curve(MonotoneConvex).instantaneous_forward(make_date(2026, 11, 8)); }) == "E_OUT_OF_RANGE");
    CHECK(code_of([] { curve(MonotoneConvex).instantaneous_forward(as_of()); }) == "OK");
}

TEST_CASE("hybrid with step_end at the last pillar is log-linear", "[f][curve_interp]") {
    const Curve h = curve(CurveInterpolation::Hybrid, {{}, make_date(2056, 11, 15)});
    const Curve l = curve(CurveInterpolation::LogLinearDf);
    for (const Date d : {make_date(2027, 2, 1), make_date(2040, 1, 1), make_date(2070, 1, 1)}) {
        CHECK(h.discount(d) == l.discount(d));
        CHECK(h.instantaneous_forward(d) == l.instantaneous_forward(d));
    }
}

TEST_CASE("monotone convex: equal discrete forwards give a flat curve", "[f][curve_interp]") {
    const NodeLogCurve c(NodeCurveMethod::MonotoneConvex, {0.0, 1.0, 3.0, 4.0}, {0.0, -0.03, -0.09, -0.12});
    for (const double t : {0.0, 0.5, 1.0, 2.2, 3.9, 6.0}) {
        CHECK(std::fabs(c.forward(t) - 0.03) < 1e-15);
        CHECK(std::fabs(c.ln_s(t) + 0.03 * t) < 1e-15);
    }
    const NodeLogCurve one(NodeCurveMethod::MonotoneConvex, {0.0, 2.0}, {0.0, -0.1});
    CHECK(std::fabs(one.forward(1.0) - 0.05) < 1e-15);
    CHECK(std::fabs(one.ln_s(5.0) + 0.25) < 1e-15);
}

TEST_CASE("tension spline: small tension nears the natural log cubic", "[f][curve_interp]") {
    const std::vector<double> t{0.0, 0.5, 1.0, 2.0, 5.0, 10.0}, y{0.0, -0.02, -0.041, -0.075, -0.18, -0.36};
    const NodeLogCurve a(NodeCurveMethod::TensionSpline, t, y, 1e-4);
    const NodeLogCurve b(NodeCurveMethod::TensionSpline, t, y, 1e-2);
    const NodeLogCurve stiff(NodeCurveMethod::TensionSpline, t, y, 1000.0);
    for (const double s : {0.25, 1.5, 7.0}) {
        CHECK(std::fabs(a.ln_s(s) - b.ln_s(s)) < 1e-5);
        const auto i = s < 0.5 ? 0 : s < 2.0 ? 2 : 4;
        const double u = (s - t[i]) / (t[i + 1] - t[i]);
        CHECK(std::fabs(stiff.ln_s(s) - ((1 - u) * y[i] + u * y[i + 1])) < 1e-4);
    }
}

TEST_CASE("bootstrap with every stage F method reprices", "[f][curve_interp]") {
    const RateConvention& sofr = *rate_convention("SOFR");
    const std::vector<OisQuote> q{{{1, 'Y'}, 0.039}, {{2, 'Y'}, 0.0365}, {{5, 'Y'}, 0.0352}, {{10, 'Y'}, 0.0364}};
    for (const CurveInterpolation m : stage_f_methods()) {
        for (const SolveMethod s : {SolveMethod::Sequential, SolveMethod::Global}) {
            const CurveShape shape{0.5, ois_periods(sofr, as_of(), {2, 'Y'}).back().payment};
            const SolvedCurve r = ois_bootstrap(sofr, as_of(), q, m, s, {}, shape);
            CHECK(r.max_repricing_error < 1e-13);
        }
    }
    CHECK(code_of([&] { ois_bootstrap(sofr, as_of(), q, CurveInterpolation::Hybrid, SolveMethod::Global, {}, {{}, make_date(2027, 1, 1)}); }) == "E_INPUT");
    CHECK(code_of([&] { ois_bootstrap(sofr, as_of(), q, CurveInterpolation::TensionSpline, SolveMethod::Global); }) == "E_INPUT");
}
