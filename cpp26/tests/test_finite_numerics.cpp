// F-4 library API finite checks, numerics group: every public function rejects NaN and infinity with E_DOMAIN.
#include <catch2/catch_test_macros.hpp>

#include <limits>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/correlation.hpp"
#include "quantforge/core/credit_options.hpp"
#include "quantforge/core/data_checks.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/exotics.hpp"
#include "quantforge/core/interp.hpp"
#include "quantforge/core/linalg.hpp"
#include "quantforge/core/stats.hpp"
#include "quantforge/core/timeseries.hpp"

using namespace quantforge;

namespace {

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "none";
}

// Calls check(bad) for NaN, +inf and -inf and expects E_DOMAIN each time.
template <class F>
void rejects_non_finite(F check) {
    const double values[] = {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(),
                             -std::numeric_limits<double>::infinity()};
    for (const double bad : values) CHECK(code_of([&] { check(bad); }) == "E_DOMAIN");
}

ExoticMarket market() { return {100.0, 100.0, 1.0, 0.05, 0.02, 0.2, OptionType::Call}; }

CdsOptionInputs cds() {
    return {make_date(2026, 11, 6), make_date(2027, 3, 20), make_date(2032, 3, 20), 0.035, 0.02, 0.4, true, 0.012, 1e7, true};
}

}  // namespace

TEST_CASE("finite numerics: stats") {
    rejects_non_finite([](double b) { summary({1.0, b, 3.0}); });
    rejects_non_finite([](double b) { quantiles({1.0, b, 3.0}, {0.5}); });
    rejects_non_finite([](double b) { quantiles({1.0, 2.0, 3.0}, {b}); });
    rejects_non_finite([](double b) { covariance({1.0, b, 3.0}, {1.0, 2.0, 4.0}); });
    rejects_non_finite([](double b) { covariance({1.0, 2.0, 3.0}, {1.0, b, 4.0}); });
    rejects_non_finite([](double b) { ols({1.0, b, 3.0, 4.0}, {1.0, 2.0, 4.0, 3.0}); });
    rejects_non_finite([](double b) { ols({1.0, 2.0, 3.0, 4.0}, {1.0, 2.0, b, 3.0}); });
    CHECK(quantiles({1.0, 2.0, 3.0}, {-0.0}) == quantiles({1.0, 2.0, 3.0}, {0.0}));
    CHECK(summary({-0.0, 1.0, 2.0}).mean == summary({0.0, 1.0, 2.0}).mean);
}

TEST_CASE("finite numerics: interp") {
    const std::vector<double> x{1.0, 2.0, 3.0}, y{1.0, 4.0, 9.0};
    rejects_non_finite([&](double b) { interpolate(InterpMethod::Linear, {1.0, b, 3.0}, y, {1.5}); });
    rejects_non_finite([&](double b) { interpolate(InterpMethod::Linear, x, {1.0, b, 9.0}, {1.5}); });
    rejects_non_finite([&](double b) { interpolate(InterpMethod::Linear, x, y, {b}); });
    rejects_non_finite([&](double b) { interpolate(InterpMethod::CubicClamped, x, y, {1.5}, {b, 0.0, 0.0}); });
    rejects_non_finite([&](double b) { interpolate(InterpMethod::CubicClamped, x, y, {1.5}, {0.0, b, 0.0}); });
    rejects_non_finite([&](double b) { interpolate(InterpMethod::Tension, x, y, {1.5}, {0.0, 0.0, b}); });
    rejects_non_finite([&](double b) { monotone_convex({1.0, b, 3.0}, {0.01, 0.02, 0.03}, {1.5}, false); });
    rejects_non_finite([&](double b) { monotone_convex(x, {0.01, b, 0.03}, {1.5}, false); });
    rejects_non_finite([&](double b) { monotone_convex(x, {0.01, 0.02, 0.03}, {b}, false); });
    const auto neg = interpolate(InterpMethod::CubicClamped, x, y, {1.5}, {-0.0, -0.0, 0.0});
    const auto pos = interpolate(InterpMethod::CubicClamped, x, y, {1.5}, {0.0, 0.0, 0.0});
    CHECK(neg.values == pos.values);
    CHECK(neg.derivatives == pos.derivatives);
}

TEST_CASE("finite numerics: linalg") {
    rejects_non_finite([](double b) { cholesky({{4.0, b}, {b, 3.0}}); });
    rejects_non_finite([](double b) { eigen_symmetric({{b, 1.0}, {1.0, 2.0}}); });
    CHECK(eigen_symmetric({{2.0, -0.0}, {-0.0, 1.0}}) == eigen_symmetric({{2.0, 0.0}, {0.0, 1.0}}));
}

TEST_CASE("finite numerics: timeseries") {
    rejects_non_finite([](double b) { returns({1.0, b, 3.0}, ReturnKind::Simple); });
    rejects_non_finite([](double b) { rolling({1.0, b, 3.0}, 2, RollingStatistic::Mean); });
    rejects_non_finite([](double b) { ewma_variance({0.01, b}, 0.94); });
    rejects_non_finite([](double b) { ewma_variance({0.01, 0.02}, b); });
    rejects_non_finite([](double b) { autocorrelation({1.0, b, 3.0, 2.0}, 1); });
    rejects_non_finite([](double b) { ljung_box({1.0, b, 3.0, 2.0}, 1); });
    rejects_non_finite([](double b) { ar1({1.0, b, 3.0, 2.0, 5.0}); });
    rejects_non_finite([](double b) {
        resample_last({make_date(2026, 1, 1), make_date(2026, 1, 2)}, {MaybeReal{1.0}, MaybeReal{b}}, ResampleFrequency::Week);
    });
    rejects_non_finite([](double b) { forward_fill({MaybeReal{1.0}, std::nullopt, MaybeReal{b}}, 1); });
    // Missing values stay missing, not an error.
    CHECK(forward_fill({MaybeReal{1.0}, std::nullopt}, 1).size() == 2);
    CHECK(ewma_variance({-0.0, 0.01}, 0.94) == ewma_variance({0.0, 0.01}, 0.94));
}

TEST_CASE("finite numerics: data checks") {
    const auto base = [] {
        QuoteCheckInputs in{};
        in.as_of = 1000;
        in.stale_after_seconds = 60;
        Quote q{"A", 990, 99.0, 101.0, "FIRM"};
        in.quotes.push_back(q);
        return in;
    };
    rejects_non_finite([&](double b) {
        auto in = base();
        in.quotes[0].bid = b;
        check_quotes(in);
    });
    rejects_non_finite([&](double b) {
        auto in = base();
        in.quotes[0].ask = b;
        check_quotes(in);
    });
    rejects_non_finite([&](double b) {
        auto in = base();
        in.max_relative_spread = b;
        check_quotes(in);
    });
    rejects_non_finite([&](double b) {
        auto in = base();
        in.outlier_threshold = b;
        check_quotes(in);
    });
    rejects_non_finite([&](double b) {
        auto in = base();
        in.history["A"] = {100.0, b, 100.0};
        check_quotes(in);
    });
    CHECK(code_of([&] { check_quotes(base()); }) == "none");
}

TEST_CASE("finite numerics: correlation") {
    rejects_non_finite([](double b) { corr_validate({{1.0, b}, {b, 1.0}}); });
    rejects_non_finite([](double b) { corr_nearest({{1.0, b}, {b, 1.0}}); });
    rejects_non_finite([](double b) { corr_implied({0.5, b}, {0.2, 0.3}, 0.2); });
    rejects_non_finite([](double b) { corr_implied({0.5, 0.5}, {0.2, b}, 0.2); });
    rejects_non_finite([](double b) { corr_implied({0.5, 0.5}, {0.2, 0.3}, b); });
    const std::vector<double> w{0.5, 0.5}, k{0.2, 0.3}, s{0.25, 0.3};
    rejects_non_finite([&](double b) { corr_dispersion({0.5, b}, k, 0.2, s, 0.2, 1e4); });
    rejects_non_finite([&](double b) { corr_dispersion(w, {0.2, b}, 0.2, s, 0.2, 1e4); });
    rejects_non_finite([&](double b) { corr_dispersion(w, k, b, s, 0.2, 1e4); });
    rejects_non_finite([&](double b) { corr_dispersion(w, k, 0.2, {0.25, b}, 0.2, 1e4); });
    rejects_non_finite([&](double b) { corr_dispersion(w, k, 0.2, s, b, 1e4); });
    rejects_non_finite([&](double b) { corr_dispersion(w, k, 0.2, s, 0.2, b); });
    CHECK(corr_validate({{1.0, -0.0}, {-0.0, 1.0}}).valid == corr_validate({{1.0, 0.0}, {0.0, 1.0}}).valid);
}

TEST_CASE("finite numerics: exotics market fields") {
    const auto with = [](int field, double b) {
        ExoticMarket m = market();
        double* f[] = {&m.spot, &m.strike, &m.expiry_years, &m.rate, &m.dividend_yield, &m.vol};
        *f[field] = b;
        return m;
    };
    for (int i = 0; i < 6; ++i) {
        rejects_non_finite([&](double b) { digital_price(with(i, b), DigitalPayoff::CashOrNothing, 1.0); });
        rejects_non_finite([&](double b) { barrier_price(with(i, b), 90.0, 0.0, BarrierType::DownOut); });
        rejects_non_finite([&](double b) { asian_geometric(with(i, b), true, {}); });
        rejects_non_finite([&](double b) { lookback_floating(with(i, b), 100.0); });
        rejects_non_finite([&](double b) { chooser_price(with(i, b), 0.5); });
        rejects_non_finite([&](double b) { american_crr(with(i, b), 10); });
        rejects_non_finite([&](double b) { american_baw(with(i, b)); });
        rejects_non_finite([&](double b) { american_fd(with(i, b), true, {50, 50, 4.0}); });
    }
}

TEST_CASE("finite numerics: exotics other inputs") {
    const ExoticMarket m = market();
    rejects_non_finite([&](double b) { digital_price(m, DigitalPayoff::CashOrNothing, b); });
    rejects_non_finite([&](double b) { barrier_price(m, b, 0.0, BarrierType::DownOut); });
    rejects_non_finite([&](double b) { barrier_price(m, 90.0, b, BarrierType::DownOut); });
    rejects_non_finite([&](double b) { asian_geometric(m, false, {0.5, b}); });
    rejects_non_finite([&](double b) { lookback_floating(m, b); });
    rejects_non_finite([&](double b) { chooser_price(m, b); });
    rejects_non_finite([&](double b) { american_fd(m, true, {50, 50, b}); });
    for (int i = 0; i < 9; ++i) {
        rejects_non_finite([&](double b) {
            QuantoInputs q{100.0, 100.0, 1.0, 0.05, 0.03, 0.0, 0.2, 0.1, 0.3, OptionType::Call};
            double* f[] = {&q.spot, &q.strike, &q.expiry_years, &q.domestic_rate, &q.foreign_rate,
                           &q.dividend_yield, &q.vol, &q.fx_vol, &q.correlation};
            *f[i] = b;
            quanto_price(q);
        });
    }
    for (int i = 0; i < 8; ++i) {
        rejects_non_finite([&](double b) {
            double a[] = {100.0, 90.0, 5.0, 1.0, 0.05, 0.2, 0.3, 0.5};
            a[i] = b;
            kirk_spread(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
        });
    }
    const std::vector<double> f{100.0, 90.0}, w{0.5, 0.5}, v{0.2, 0.3};
    const Matrix c{{1.0, 0.5}, {0.5, 1.0}};
    rejects_non_finite([&](double b) { basket_moment({100.0, b}, w, v, c, 95.0, 1.0, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, {0.5, b}, v, c, 95.0, 1.0, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, w, {0.2, b}, c, 95.0, 1.0, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, w, v, {{1.0, b}, {b, 1.0}}, 95.0, 1.0, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, w, v, c, b, 1.0, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, w, v, c, 95.0, b, 0.05, OptionType::Call); });
    rejects_non_finite([&](double b) { basket_moment(f, w, v, c, 95.0, 1.0, b, OptionType::Call); });

    ExoticMarket neg = m, pos = m;
    neg.dividend_yield = -0.0;  // BAW needs a positive rate (ruling E-A30), so only the yield is zero
    pos.dividend_yield = 0.0;
    CHECK(american_baw(neg) == american_baw(pos));
    CHECK(barrier_price(m, 90.0, -0.0, BarrierType::DownOut) == barrier_price(m, 90.0, 0.0, BarrierType::DownOut));
}

TEST_CASE("finite numerics: credit options") {
    for (int i = 0; i < 5; ++i) {
        rejects_non_finite([&](double b) {
            CdsOptionInputs in = cds();
            double* f[] = {&in.rate, &in.hazard_rate, &in.recovery, &in.strike, &in.notional};
            *f[i] = b;
            cds_option_price(in, 0.5);
        });
        rejects_non_finite([&](double b) {
            CdsOptionInputs in = cds();
            double* f[] = {&in.rate, &in.hazard_rate, &in.recovery, &in.strike, &in.notional};
            *f[i] = b;
            cds_option_implied_vol(in, 1000.0);
        });
    }
    rejects_non_finite([](double b) { cds_option_price(cds(), b); });
    rejects_non_finite([](double b) { cds_option_implied_vol(cds(), b); });
    rejects_non_finite([](double b) { copula_joint_default(CopulaKind::Gaussian, {0.1, b}, 0.3, std::nullopt); });
    rejects_non_finite([](double b) { copula_joint_default(CopulaKind::Gaussian, {0.1, 0.2}, b, std::nullopt); });
    rejects_non_finite([](double b) { copula_joint_default(CopulaKind::StudentT, {0.1, 0.2}, 0.3, b); });
    for (int i = 0; i < 5; ++i) {
        rejects_non_finite([&](double b) {
            double a[] = {0.05, 0.3, 0.4, 0.03, 0.07};
            a[i] = b;
            lhp_tranche_loss(a[0], a[1], a[2], a[3], a[4]);
        });
    }
    rejects_non_finite([](double b) { lhp_loss_cdf(b, 0.3, 0.4, {0.1}); });
    rejects_non_finite([](double b) { lhp_loss_cdf(0.05, b, 0.4, {0.1}); });
    rejects_non_finite([](double b) { lhp_loss_cdf(0.05, 0.3, b, {0.1}); });
    rejects_non_finite([](double b) { lhp_loss_cdf(0.05, 0.3, 0.4, {0.1, b}); });
    CHECK(lhp_tranche_loss(0.05, 0.3, 0.4, -0.0, 0.07) == lhp_tranche_loss(0.05, 0.3, 0.4, 0.0, 0.07));
    CHECK(lhp_loss_cdf(0.05, 0.3, -0.0, {0.1}) == lhp_loss_cdf(0.05, 0.3, 0.0, {0.1}));
    CHECK(copula_joint_default(CopulaKind::Gaussian, {0.1, 0.2}, -0.0, std::nullopt).joint ==
          copula_joint_default(CopulaKind::Gaussian, {0.1, 0.2}, 0.0, std::nullopt).joint);
}
