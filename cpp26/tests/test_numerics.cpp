#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <numbers>

#include "quantforge/core/error.hpp"
#include "quantforge/core/integrate.hpp"
#include "quantforge/core/interp.hpp"
#include "quantforge/core/linalg.hpp"
#include "quantforge/core/stats.hpp"
#include "quantforge/core/timeseries.hpp"
#include "test_functions.hpp"

using namespace quantforge;
using Catch::Approx;
using Vec = std::vector<double>;

namespace {
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
}  // namespace

TEST_CASE("root finders reach simple roots within the step targets") {
    const auto fn = cli::root_function("exp_minus_two");
    const double root = std::numbers::ln2;
    const auto bi = bisection(fn.f, 0, 1);
    CHECK(std::fabs(bi.root - root) <= 1e-10);
    CHECK(bi.iterations <= 60);
    const auto br = brent(fn.f, 0, 1);
    CHECK(std::fabs(br.root - root) <= 1e-10);
    CHECK(br.iterations <= 20);
    const auto ne = newton(fn.f, fn.df, 1.0, std::nullopt);
    CHECK(std::fabs(ne.root - root) <= 1e-10);
    CHECK(ne.iterations <= 20);
}

TEST_CASE("root finder failures") {
    const auto none = cli::root_function("no_real_root");
    CHECK(code_of([&] { bisection(none.f, -1, 1); }) == "E_NOT_BRACKETED");
    CHECK(code_of([&] { newton(none.f, none.df, 0.0, std::nullopt); }) == "E_ZERO_DERIVATIVE");
    const auto cubic = cli::root_function("cubic_wallis");
    CHECK(code_of([&] { brent(cubic.f, 2, 3, {1e-12, 0, 2}); }) == "E_NO_CONVERGENCE");
    CHECK(code_of([&] { newton(cubic.f, cubic.df, 5.0, Bracket{2, 3}); }) == "E_INPUT");
    CHECK(code_of([&] { cli::root_function("nope"); }) == "E_SCHEMA");
    const auto steep = cli::root_function("steep_atan");
    CHECK(newton(steep.f, steep.df, 0.9, Bracket{0, 1}).root == Approx(0.3).margin(1e-10));
}

TEST_CASE("quadrature numeric targets") {
    const double e1 = std::numbers::e - 1.0;
    CHECK(std::fabs(gauss_legendre(cli::plain_function("exp"), 0, 1, 16) - e1) < 1e-14);
    CHECK(std::fabs(gauss_kronrod(cli::plain_function("inv_sqrt"), 0, 1).value - 2.0) < 1e-9);
    CHECK(std::fabs(adaptive_simpson(cli::plain_function("sqrt"), 0, 1) - 2.0 / 3.0) < 1e-8);
    CHECK(simpson(cli::plain_function("poly5"), 0, 1, 2) == Approx(1.0 / 6 - 1 + 1).margin(0.1));
    CHECK(code_of([] { gauss_kronrod(cli::plain_function("oscillatory"), 0, 10, 1e-12, 1); }) == "E_NO_CONVERGENCE");
    CHECK(code_of([] { simpson(cli::plain_function("exp"), 0, 1, 3); }) == "E_INPUT");
}

TEST_CASE("central differences") {
    const auto f = cli::plain_function("exp");
    CHECK(central_difference(f, 1, 1e-5, 1) == Approx(std::numbers::e).epsilon(1e-9));
    CHECK(central_difference(f, 1, 1e-4, 2) == Approx(std::numbers::e).epsilon(1e-6));
    CHECK(code_of([&] { central_difference(f, 1, 0, 1); }) == "E_INPUT");
    CHECK(code_of([&] { central_difference(f, 1, 1e-4, 3); }) == "E_SCHEMA");
}

TEST_CASE("every interpolant reproduces the knots") {
    const Vec x{0, 1, 2.5, 3, 4.5}, y{1, 2, 1.5, 3, 2.5};
    using enum InterpMethod;
    for (const InterpMethod m : {Linear, LogLinear, CubicNatural, CubicClamped, CubicNotAKnot, MonotonePchip, Tension}) {
        const auto r = interpolate(m, x, y, x, {0.5, -0.5, 1.0});
        for (std::size_t i = 0; i < x.size(); ++i) CHECK(r.values[i] == Approx(y[i]).margin(1e-12));
    }
}

TEST_CASE("cubic splines reproduce what they should") {
    using enum InterpMethod;
    const Vec x{0, 1, 2, 4, 5};
    Vec y;
    for (const double v : x) y.push_back(v * v * v);
    const auto r = interpolate(CubicNotAKnot, x, y, {3.0});
    CHECK(r.values[0] == Approx(27.0));
    CHECK(r.derivatives[0] == Approx(27.0));
    const auto c = interpolate(CubicClamped, {0, 1}, {0, 1}, {0.5}, {0.0, 3.0});
    CHECK(c.values[0] == Approx(0.125));
}

TEST_CASE("pchip never overshoots monotone data") {
    const Vec x{0, 1, 2, 3, 10}, y{0, 0.1, 0.1, 5, 5.5};
    Vec at;
    for (int i = 0; i <= 1000; ++i) at.push_back(i * 0.01);
    const auto r = interpolate(InterpMethod::MonotonePchip, x, y, at);
    for (std::size_t i = 1; i < at.size(); ++i) CHECK(r.values[i] >= r.values[i - 1] - 1e-12);
}

TEST_CASE("tension runs between natural spline and straight lines") {
    using enum InterpMethod;
    const Vec x{0, 1, 2, 3}, y{0, 2, 1, 3}, at{0.5, 1.5, 2.5};
    const auto natural = interpolate(CubicNatural, x, y, at);
    const auto loose = interpolate(Tension, x, y, at, {0, 0, 0.011});
    const auto zero = interpolate(Tension, x, y, at, {0, 0, 0.0});
    const auto tight = interpolate(Tension, x, y, at, {0, 0, 400.0});
    const auto line = interpolate(Linear, x, y, at);
    for (std::size_t i = 0; i < at.size(); ++i) {
        CHECK(loose.values[i] == Approx(natural.values[i]).margin(1e-4));
        CHECK(zero.values[i] == natural.values[i]);
        CHECK(tight.values[i] == Approx(line.values[i]).margin(0.01));
    }
    CHECK(code_of([&] { interpolate(Tension, x, y, at, {0, 0, 0.001}); }) == "E_DOMAIN");
}

TEST_CASE("interpolation check order") {
    using enum InterpMethod;
    CHECK(code_of([] { interpolate(Linear, {0, 1}, {1}, {0.5}); }) == "E_INPUT");
    CHECK(code_of([] { interpolate(LogLinear, {0, 1}, {1, -1}, {5.0}); }) == "E_DOMAIN");
    CHECK(code_of([] { interpolate(Linear, {0, 1}, {1, 1}, {5.0}); }) == "E_OUT_OF_RANGE");
}

TEST_CASE("monotone convex reprices every input") {
    const Vec t{0.5, 1, 2, 5, 10}, r{0.02, 0.025, 0.022, 0.03, 0.028};
    for (const bool positive : {false, true}) {
        const auto v = monotone_convex(t, r, t, positive);
        for (std::size_t i = 0; i < t.size(); ++i) CHECK(v.zero_rates[i] == Approx(r[i]).margin(1e-12));
    }
    // A flat curve gives flat forwards, through the zero region.
    const auto flat = monotone_convex({1, 2}, {0.03, 0.03}, {0.5, 1.5}, false);
    CHECK(flat.forwards[1] == Approx(0.03));
    CHECK(code_of([] { monotone_convex({1, 2}, {0.05, 0.01}, {0.5}, true); }) == "E_DOMAIN");
    CHECK(code_of([] { monotone_convex({1, 2}, {0.05, 0.01}, {0.0}, true); }) == "E_OUT_OF_RANGE");
}

TEST_CASE("linear algebra") {
    const auto x = solve_linear({{0, 2}, {1, 1}}, {2, 3});
    CHECK(x[0] == Approx(2.0));
    CHECK(x[1] == Approx(1.0));
    CHECK(code_of([] { solve_linear({{1, 2}, {2, 4}}, {1, 2}); }) == "E_SINGULAR");
    CHECK(code_of([] { solve_linear({{0, 0}, {0, 0}}, {1, 2}); }) == "E_SINGULAR");
    CHECK(code_of([] { solve_linear({{1, 2}, {3}}, {1, 2}); }) == "E_INPUT");
    const auto l = cholesky({{4, 2}, {2, 5}});
    CHECK(l[0][0] == Approx(2.0));
    CHECK(l[1][0] == Approx(1.0));
    CHECK(l[1][1] == Approx(2.0));
    CHECK(code_of([] { cholesky({{1, 2}, {2, 1}}); }) == "E_NOT_POSITIVE_DEFINITE");
    CHECK(code_of([] { cholesky({{1, 2}, {3, 1}}); }) == "E_INPUT");
    const auto e = eigen_symmetric({{2, 1}, {1, 2}});
    CHECK(e[0] == Approx(1.0));
    CHECK(e[1] == Approx(3.0));
}

TEST_CASE("the normal tail keeps its relative accuracy") {
    // 50-digit value of N(-37), as stored in the stats golden file.
    CHECK(normal_cdf(-37.0) == Approx(5.725571222e-300).epsilon(1e-9));
    CHECK(normal_cdf(0.0) == 0.5);
    CHECK(normal_cdf(1.96) + normal_cdf(-1.96) == Approx(1.0).epsilon(1e-15));
}

TEST_CASE("moments survive a large offset") {
    const Summary s = summary({1000000001.0, 1000000002.0, 1000000004.0, 1000000003.0, 1000000007.0});
    CHECK(s.variance == Approx(5.3).epsilon(1e-12));
    CHECK(*s.skewness == Approx(0.6927284074925394).epsilon(1e-10));
    CHECK_FALSE(summary({2, 2}).skewness.has_value());
}

TEST_CASE("quantile, covariance, OLS") {
    const auto q = quantiles({4, 1, 3, 2}, {0.0, 0.5, 1.0});
    CHECK(q == Vec{1.0, 2.5, 4.0});
    CHECK_FALSE(covariance({1, 1}, {1, 2}).correlation.has_value());
    const Ols o = ols({1, 2, 3, 4}, {3, 5, 7, 9.5});
    CHECK(o.beta == Approx(2.15));
    CHECK(code_of([] { ols({1, 1, 1}, {1, 2, 3}); }) == "E_SINGULAR");
}

TEST_CASE("time series") {
    CHECK(returns({100, 110}, ReturnKind::Simple)[0] == Approx(0.1));
    const auto r = rolling({1e12, 1, 2, 3}, 2, RollingStatistic::Stdev);
    CHECK_FALSE(r[0].has_value());
    CHECK(*r[3] == Approx(std::sqrt(0.5)));  // no residue from the early large value
    CHECK(ewma_variance({1, 2}, 0.5)[1] == Approx(2.5));
    CHECK(code_of([] { autocorrelation({1, 1, 1}, 1); }) == "E_DOMAIN");
    const auto a = ar1({1, 2, 4, 8, 16});
    CHECK(a.phi == Approx(2.0));
    const auto filled = forward_fill({std::nullopt, 1.0, std::nullopt, std::nullopt}, 1);
    CHECK_FALSE(filled[0].has_value());
    CHECK(filled[2] == 1.0);
    CHECK_FALSE(filled[3].has_value());
}

TEST_CASE("resampling buckets") {
    using std::nullopt;
    const std::vector<Date> d{*parse_date("2024-01-07"), *parse_date("2024-01-08"), *parse_date("2024-01-09"),
                              *parse_date("2024-02-01")};
    const auto week = resample_last(d, {1.0, 2.0, nullopt, 4.0}, ResampleFrequency::Week);
    CHECK(week.values == Vec{1.0, 2.0, 4.0});
    const auto month = resample_last(d, {1.0, 2.0, nullopt, 4.0}, ResampleFrequency::Month);
    CHECK(month.values == Vec{2.0, 4.0});
    CHECK(month.dates[0] == d[1]);
}
