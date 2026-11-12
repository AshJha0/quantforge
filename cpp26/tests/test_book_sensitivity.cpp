// Stage F risk_f3 unit tests (06-risk/book-sensitivities.md). No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/rates.hpp"
#include "quantforge/core/book_sensitivity.hpp"

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

Date as_of() { return make_date(2026, 11, 10); }

std::vector<OisQuote> sofr_quotes() {
    return {{{1, 'M'}, 0.043},  {{3, 'M'}, 0.0425}, {{6, 'M'}, 0.0412}, {{1, 'Y'}, 0.039},
            {{2, 'Y'}, 0.0365}, {{3, 'Y'}, 0.0355}, {{5, 'Y'}, 0.0352}, {{7, 'Y'}, 0.0356},
            {{10, 'Y'}, 0.0364}, {{15, 'Y'}, 0.0376}, {{20, 'Y'}, 0.038}, {{30, 'Y'}, 0.0368}};
}

double book_pv_bumped(const std::vector<OisQuote>& quotes, std::size_t j, double h, const std::vector<BookSwap>& swaps) {
    std::vector<OisQuote> q = quotes;
    q[j].rate += h;
    const RateConvention& c = *rate_convention("SOFR");
    const Curve curve = ois_bootstrap(c, as_of(), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    double pv = 0.0;
    for (const BookSwap& s : swaps) {
        const Legs v = ois_legs(c, ois_periods(c, as_of(), Tenor{int(s.tenor_years), 'Y'}), curve);
        pv += (s.side == FixedSide::Pay ? 1.0 : -1.0) * (v.floating - s.fixed_rate * v.annuity);
    }
    return pv;
}

}  // namespace

TEST_CASE("f3 ois_sensitivity agrees with a Richardson bump and rebuild", "[f3]") {
    const auto quotes = sofr_quotes();
    const std::vector<BookSwap> swaps{{"A", 7, 0.03, FixedSide::Pay}, {"B", 22, 0.041, FixedSide::Receive}, {"C", 3, 0.05, FixedSide::Pay}};
    const BookSensitivity r = ois_book_sensitivity(*rate_convention("SOFR"), as_of(), quotes, CurveInterpolation::LogLinearDf, swaps);
    for (std::size_t j = 0; j < quotes.size(); ++j) {
        const auto central = [&](double h) {
            return (book_pv_bumped(quotes, j, h, swaps) - book_pv_bumped(quotes, j, -h, swaps)) / (2.0 * h);
        };
        const double richardson = (4.0 * central(5e-5) - central(1e-4)) / 3.0;
        CHECK(std::fabs(richardson - r.book_sensitivity[j]) <= 1e-7 + 1e-6 * std::fabs(r.book_sensitivity[j]));
    }
}

TEST_CASE("f3 zero jacobian is lower triangular with exact zeros", "[f3]") {
    const BookSensitivity r = ois_book_sensitivity(*rate_convention("SOFR"), as_of(), sofr_quotes(),
                                                   CurveInterpolation::LogLinearDf, {{"A", 5, 0.03, FixedSide::Pay}});
    for (std::size_t i = 0; i < r.zero_jacobian.size(); ++i)
        for (std::size_t j = i + 1; j < r.zero_jacobian.size(); ++j) CHECK(r.zero_jacobian[i][j] == 0.0);
}

TEST_CASE("f3 limit: a payer at par has pv 0 and d pv / d q_own equal to its annuity", "[f3]") {
    const auto quotes = sofr_quotes();
    const RateConvention& c = *rate_convention("SOFR");
    const BookSensitivity r = ois_book_sensitivity(c, as_of(), quotes, CurveInterpolation::LogLinearDf, {{"P", 5, 0.0352, FixedSide::Pay}});
    const Curve curve = ois_bootstrap(c, as_of(), quotes, CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const double annuity = ois_legs(c, ois_periods(c, as_of(), Tenor{5, 'Y'}), curve).annuity;
    CHECK(std::fabs(r.pv[0]) < 1e-14);
    CHECK(std::fabs(r.quote_sensitivity[0][6] - annuity) < 1e-12);
    for (std::size_t j = 0; j < quotes.size(); ++j)
        if (j != 6) CHECK(std::fabs(r.quote_sensitivity[0][j]) < 1e-12);
}

TEST_CASE("f3 limit: one pillar matches the closed-form one-period OIS", "[f3]") {
    // One period: q = (1/D - 1) / tau with D = D(pay) and spot before the pillar on a flat log-linear segment.
    const RateConvention& c = *rate_convention("SOFR");
    const std::vector<OisQuote> quotes{{{1, 'Y'}, 0.04}};
    const BookSensitivity r = ois_book_sensitivity(c, as_of(), quotes, CurveInterpolation::LogLinearDf, {{"A", 1, 0.04, FixedSide::Pay}});
    const auto periods = ois_periods(c, as_of(), Tenor{1, 'Y'});
    const Period p = periods[0];
    const Curve curve = ois_bootstrap(c, as_of(), quotes, CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const double tp = curve.time(p.payment), ts = curve.time(p.start), te = curve.time(p.end);
    const double tau = year_fraction(c.fixed_day_count, p.start, p.end);
    // ln D(t) = x t / tp; par = (exp(x (ts - te) / tp) - 1) / tau; d par / d x = exp(...) (ts - te) / (tp tau).
    const double x = curve.log_df(0);
    const double dpar_dx = std::exp(x * (ts - te) / tp) * (ts - te) / (tp * tau);
    const double expected = -(1.0 / dpar_dx) / tp;
    CHECK(std::fabs(r.zero_jacobian[0][0] - expected) <= 1e-13 * std::fabs(expected));
}

TEST_CASE("f3 ois_sensitivity input rules", "[f3]") {
    const RateConvention& c = *rate_convention("SOFR");
    const auto q = sofr_quotes();
    CHECK(code_of([&] { ois_book_sensitivity(c, as_of(), q, CurveInterpolation::LogLinearDf, {}); }) == "E_INPUT");
    CHECK(code_of([&] {
              ois_book_sensitivity(c, as_of(), q, CurveInterpolation::LogLinearDf,
                                   {{"A", 5, 0.03, FixedSide::Pay}, {"A", 5, 0.03, FixedSide::Pay}});
          }) == "E_INPUT");
    CHECK(code_of([&] { ois_book_sensitivity(c, as_of(), q, CurveInterpolation::LogLinearDf, {{"A", 0, 0.03, FixedSide::Pay}}); }) ==
          "E_DOMAIN");
    CHECK(code_of([&] { ois_book_sensitivity(c, as_of(), q, CurveInterpolation::LogLinearDf, {{"A", 5, NAN, FixedSide::Pay}}); }) ==
          "E_DOMAIN");
}

TEST_CASE("f3 LINEAR_ZERO sensitivities agree with a bump", "[f3]") {
    const RateConvention& c = *rate_convention("SOFR");
    const auto quotes = sofr_quotes();
    const Matrix m = ois_curve_ift(c, as_of(), quotes, CurveInterpolation::LinearZero);
    const auto x_at = [&](std::size_t j, double h, std::size_t i) {
        auto q = quotes;
        q[j].rate += h;
        return ois_bootstrap(c, as_of(), q, CurveInterpolation::LinearZero, SolveMethod::Sequential).curve.log_df(i);
    };
    for (std::size_t j = 0; j < quotes.size(); ++j)
        for (std::size_t i = 0; i < quotes.size(); ++i) {
            const double bump = (x_at(j, 1e-5, i) - x_at(j, -1e-5, i)) / 2e-5;
            CHECK(std::fabs(bump - m[i][j]) <= 1e-6 + 1e-5 * std::fabs(m[i][j]));
        }
}

TEST_CASE("f3 pca: one factor plus noise", "[f3]") {
    // Rows: f_t (1, 1, 1) plus a small deterministic wiggle; lambda_1 near 3 var(f).
    Matrix changes;
    double var = 0.0, mean = 0.0;
    std::vector<double> f;
    for (int t = 0; t < 200; ++t) f.push_back(std::sin(0.7 * t) * 1e-3);
    for (const double v : f) mean += v / 200.0;
    for (const double v : f) var += (v - mean) * (v - mean) / 199.0;
    for (int t = 0; t < 200; ++t) {
        const double v = f[std::size_t(t)];
        changes.push_back({v + 1e-6 * std::cos(1.3 * t), v + 1e-6 * std::cos(2.9 * t), v - 1e-6 * std::cos(0.4 * t)});
    }
    const CurvePca r = curve_pca(changes, 1);
    CHECK(std::fabs(r.eigenvalues[0] - 3.0 * var) < 1e-3 * 3.0 * var);
    for (const double l : r.loadings[0]) CHECK(std::fabs(l - 1.0 / std::sqrt(3.0)) < 1e-3);
    CHECK(r.eigenvalues[0] >= r.eigenvalues[1]);
    CHECK(r.eigenvalues[1] >= r.eigenvalues[2]);
}

TEST_CASE("f3 pca input rules", "[f3]") {
    const Matrix m{{1e-4, 2e-4}, {3e-4, -1e-4}, {0.0, 5e-5}};
    CHECK(code_of([&] { curve_pca(m, 3); }) == "E_INPUT");
    CHECK(code_of([&] { curve_pca(m, 0); }) == "E_DOMAIN");
    CHECK(code_of([&] { curve_pca({{1e-4, 2e-4}}, 1); }) == "E_INPUT");
    CHECK(code_of([&] { curve_pca({{1e-4, 2e-4}, {1e-4}}, 1); }) == "E_INPUT");
    CHECK(code_of([&] { curve_pca({{1, 0}, {-1, 0}, {0, 1}, {0, -1}}, 1); }) == "E_DOMAIN");
}

TEST_CASE("f3 cross gamma: a discount bond has no cross terms outside its two pillars", "[f3]") {
    const Curve curve(as_of(), CurveInterpolation::LogLinearDf,
                      {{make_date(2027, 11, 10), 0.96}, {make_date(2028, 11, 10), 0.93}, {make_date(2029, 11, 12), 0.90},
                       {make_date(2031, 11, 10), 0.84}});
    const Date pay = make_date(2029, 5, 10);  // between pillars 1 and 2
    const CrossGamma r = cross_gamma(curve, [pay](const Curve& c) { return 1e6 * c.discount(pay); }, 1.0);
    for (std::size_t i = 0; i < 4; ++i)
        for (std::size_t j = 0; j < 4; ++j)
            if (i != j && !((i == 1 && j == 2) || (i == 2 && j == 1))) CHECK(r.gamma[i][j] == 0.0);
    CHECK(r.gamma[1][2] != 0.0);
    CHECK(r.gamma[1][2] == r.gamma[2][1]);
    CHECK(code_of([&] { cross_gamma(curve, [](const Curve&) { return 0.0; }, 0.0); }) == "E_DOMAIN");
}

TEST_CASE("f3 cross gamma converges as h^2 to the analytic second derivative", "[f3]") {
    // V = D(t) = exp(-z t) on one pillar at t: d2V/dz2 per bp^2 = t^2 D 1e-8.
    const Curve curve(as_of(), CurveInterpolation::LogLinearDf, {{make_date(2031, 11, 10), 0.84}});
    const Date d = make_date(2031, 11, 10);
    const double t = curve.time(d), exact = t * t * 0.84 * 1e-8 * 1e6;
    double previous = 0.0;
    for (const double b : {10.0, 5.0}) {
        const double e = std::fabs(cross_gamma(curve, [d](const Curve& c) { return 1e6 * c.discount(d); }, b).gamma[0][0] - exact);
        if (previous > 0.0) CHECK(std::fabs(previous / e - 4.0) < 0.05);
        previous = e;
    }
}

TEST_CASE("f3 jump to default", "[f3]") {
    const Jtd r = jump_to_default({{"B", JtdKind::Bond, 1e6, 0.4, 985000.0},
                                   {"C", JtdKind::CdsProtectionBuyer, 5e6, 0.4, 120000.0},
                                   {"S", JtdKind::CdsProtectionSeller, 5e6, 0.25, -80000.0}});
    CHECK(r.jtd[0] == -585000.0);
    CHECK(r.jtd[1] == 2880000.0);
    CHECK(r.jtd[2] == -3670000.0);
    CHECK(r.total == r.jtd[0] + r.jtd[1] + r.jtd[2]);
    CHECK(code_of([] { jump_to_default({}); }) == "E_INPUT");
    CHECK(code_of([] { jump_to_default({{"B", JtdKind::Bond, -1.0, 0.4, 0.0}}); }) == "E_DOMAIN");
    CHECK(code_of([] { jump_to_default({{"B", JtdKind::Bond, 1.0, 1.2, 0.0}}); }) == "E_DOMAIN");
}

TEST_CASE("f3 cross gamma of an OIS: the exact-change form agrees with revaluation", "[f3]") {
    const RateConvention& c = *rate_convention("SOFR");
    const Curve curve = ois_bootstrap(c, as_of(), sofr_quotes(), CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const OisTrade trade{&c, {10, 'Y'}, 0.035, 1.0, FixedSide::Receive};
    const CrossGamma a = cross_gamma(curve, trade, 5.0);
    const CrossGamma b = cross_gamma(curve, [trade](const Curve& k) { return ois_price(trade, k).valuation.pv; }, 5.0);
    CHECK(a.value == b.value);
    for (std::size_t i = 0; i < a.gamma.size(); ++i)
        for (std::size_t j = 0; j < a.gamma.size(); ++j) CHECK(std::fabs(a.gamma[i][j] - b.gamma[i][j]) < 1e-14);
}
