// Stage J curves lane property tests (rulings J-C-1 to J-C-9), own data.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <random>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/term_curves.hpp"

namespace tc = quantforge::termcurves;
using Vec = std::vector<double>;

namespace {
const Vec FT{0.25, 0.5, 1.0, 2.0};
const Vec FZ{0.040, 0.041, 0.0415, 0.042};

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code();
    }
    return "none";
}
}  // namespace

TEST_CASE("term repo quotes round-trip and forwards chain", "[term_curves]") {
    std::mt19937_64 g(31);
    std::uniform_real_distribution<double> u(-0.01, 0.10);
    for (int trial = 0; trial < 50; ++trial) {
        const std::size_t n = 1 + trial % 6;
        Vec qt, qr;
        for (std::size_t i = 0; i < n; ++i) {
            qt.push_back(0.1 * static_cast<double>(i + 1));
            qr.push_back(u(g));
        }
        const tc::TermCurve r = tc::term_curve(tc::build({1.0}, {0.03}, qt, qr, {}, {}), qt);
        double growth = 1, prev = 0;
        for (std::size_t i = 0; i < n; ++i) {
            CHECK(std::abs(r.financing_rate[i] - qr[i]) < 1e-13);
            growth *= 1 + r.forward_financing[i] * (qt[i] - prev);
            prev = qt[i];
            CHECK(std::abs(growth * r.financing_df[i] - 1) < 1e-14);
        }
        CHECK(!r.borrow_fee);
    }
}

TEST_CASE("flat inputs reduce to ruling D22", "[term_curves]") {
    const double r = 0.03, s = 0.004, b = 0.002, t = 0.75;
    const Vec repo{(std::exp((r + s) * 0.25) - 1) / 0.25, std::exp(r + s) - 1};
    const tc::FinancingCurve c = tc::build({1.0}, {r}, {0.25, 1.0}, repo, {1.0}, {b});
    CHECK(std::abs(tc::forward_term_financed(c, 100, t, {}, {}).forward / (100 * std::exp((r + s - b) * t)) - 1) < 1e-14);
    CHECK(std::abs(tc::term_curve(c, {0.5}).spread[0] - s) < 1e-15);
}

TEST_CASE("borrow and dividends lower the forward", "[term_curves]") {
    const tc::FinancingCurve c0 = tc::build(FT, FZ, {1.0}, {0.044}, {}, {});
    const tc::FinancingCurve c1 = tc::build(FT, FZ, {1.0}, {0.044}, {1.0}, {0.01});
    const double base = tc::forward_term_financed(c0, 50, 0.75, {}, {}).forward;
    CHECK(tc::forward_term_financed(c1, 50, 0.75, {}, {}).forward < base);
    CHECK(tc::forward_term_financed(c0, 50, 0.75, {0.5}, {1.0}).forward < base);
}

TEST_CASE("term curve errors", "[term_curves]") {
    CHECK(code_of([] { tc::build(FT, FZ, {0.5, 0.5}, {0.04, 0.04}, {}, {}); }) == "E_INPUT");
    CHECK(code_of([] { tc::build(FT, FZ, {0.5}, {0.04}, {0.5, 1.0}, {0.02, 0.001}); }) == "E_DOMAIN");
    CHECK(code_of([] { tc::build(FT, FZ, {3.0}, {0.04}, {}, {}); }) == "E_DOMAIN");
    const tc::FinancingCurve c = tc::build(FT, FZ, {1.0}, {0.04}, {}, {});
    CHECK(code_of([&] { tc::term_curve(c, {1.5}); }) == "E_DOMAIN");
    CHECK(code_of([&] { tc::forward_term_financed(c, 10, 0.5, {0.1}, {20}); }) == "E_DOMAIN");
    CHECK(code_of([] { tc::liquidity_cost({1, 1e7, 0.02, 1, 0, 0}, {1}, {1}); }) == "E_DOMAIN");
    CHECK(code_of([] { tc::liquidity_cost({1, 1e7, 0.02, 1, 0.5, 0}, {}, {1}); }) == "E_INPUT");
}

TEST_CASE("liquidity curve matches stage H and the optimum is a minimum", "[term_curves]") {
    const tc::LiquidityCurve o = tc::liquidity_cost({0, 1e7, 0.02, 1, 0.5, 0}, {1e5}, {1});
    CHECK(std::abs(o.impact[0][0] - 0.002) < 1e-17);
    CHECK(!o.optimal_horizon);
    std::mt19937_64 g(5);
    std::uniform_real_distribution<double> u(0, 1);
    for (int trial = 0; trial < 50; ++trial) {
        const double d = 0.1 + 0.9 * u(g), q = 1e3 + 1e7 * u(g), z = 0.1 + 3 * u(g);
        const tc::LiquidityCurve r = tc::liquidity_cost({2, 1e7, 0.02, 1, d, z}, {q}, {1});
        const double h = (*r.optimal_horizon)[0];
        for (const double k : {0.9, 1.1}) {
            const double other = tc::liquidity_cost({2, 1e7, 0.02, 1, d, z}, {q}, {h * k}).total_cost[0][0];
            CHECK(other >= (*r.min_cost)[0] - 1e-15);
        }
    }
    const tc::LiquidityCurve zero = tc::liquidity_cost({0, 1e7, 0.02, 1, 0.5, 1}, {0.0}, {1});
    CHECK((*zero.optimal_horizon)[0] == 0.0);
}
