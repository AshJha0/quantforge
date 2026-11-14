// Lane J-0c: value-asserting kill tests for src/core/vol_stats.cpp (mutation cells garch_varswap_vix and garch_vix).
// Expected values come from the Python implementation (python/quantforge_core/variance.py, an independent port of
// the same specs) or from closed forms worked by hand; where a test pins current C++ output instead, it says so.
// Each boundary check sits exactly on the edge, so a `<` / `<=` swap flips the outcome. Equivalent survivors are
// listed in program/J0C_CPP_EQUIVALENT_MUTANTS.md. No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>
#include <chrono>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/vol_stats.hpp"

using namespace quantforge;

namespace {
std::string code_of(auto&& f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "none";
}
bool near_rel(double a, double b, double tol = 1e-13) { return std::fabs(a - b) <= tol * std::fabs(b); }
bool near_all(const std::vector<double>& a, const std::vector<double>& b, double tol = 1e-13) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
        if (!near_rel(a[i], b[i], tol)) return false;
    return true;
}
Date day(int y, unsigned m, unsigned d) { return Date{std::chrono::year{y} / m / d}; }
const std::vector<double>& r3() {
    static const std::vector<double> r{0.1, -0.2, 0.05};
    return r;
}
}  // namespace

TEST_CASE("vol_stats kills: stage E garch loglik hand values") {
    // Python variance.garch_loglik([0.1, -0.2, 0.05], 0.01, 0.1, 0.8, initial).
    const GarchLoglik a = garch_loglik(r3(), 0.01, 0.1, 0.8, 0.02);
    CHECK(near_rel(a.loglik, 1.6470068298597322));
    CHECK(near_all(a.variances, {0.02, 0.027, 0.0356}));
    CHECK(near_rel(a.next_variance, 0.03873));
    const GarchLoglik s = garch_loglik(r3(), 0.01, 0.1, 0.8, std::nullopt);  // SAMPLE = mean of squares 0.0175
    CHECK(near_rel(s.loglik, 1.678619712055633));
    CHECK(near_all(s.variances, {0.0175, 0.025, 0.034}));
    CHECK(near_rel(s.next_variance, 0.03745));
}

TEST_CASE("vol_stats kills: stage E garch loglik checks on their edges") {
    const auto ll = [](std::vector<double> r, double o, double a, double b, std::optional<double> v) {
        return code_of([&] { garch_loglik(r, o, a, b, v); });
    };
    CHECK(ll({0.1}, 0.01, 0.1, 0.8, 0.02) == "E_INPUT");
    CHECK(ll({0.1, 0.2}, 0.01, 0.1, 0.8, 0.02) == "none");
    CHECK(ll(r3(), 0.01, 0.1, 0.8, 0.0) == "E_DOMAIN");
    CHECK(ll(r3(), 0.01, 0.1, 0.8, 1e-300) == "none");
    CHECK(ll({0.0, 0.0}, 0.01, 0.1, 0.8, std::nullopt) == "E_DOMAIN");
    CHECK(ll(r3(), 0.0, 0.1, 0.8, 0.02) == "E_DOMAIN");
    CHECK(ll(r3(), 1e-300, 0.1, 0.8, 0.02) == "none");
    CHECK(ll(r3(), 0.01, 0.0, 0.0, 0.02) == "none");
    CHECK(ll(r3(), 0.01, -1e-300, 0.8, 0.02) == "E_DOMAIN");
    CHECK(ll(r3(), 0.01, 0.1, -1e-300, 0.02) == "E_DOMAIN");
    // alpha = beta = 0: every variance after the first is omega (closed form).
    const GarchLoglik z = garch_loglik(r3(), 0.01, 0.0, 0.0, 0.02);
    CHECK(near_all(z.variances, {0.02, 0.01, 0.01}));
}

TEST_CASE("vol_stats kills: stage F garch loglik with a mean and Student-t") {
    GarchLaw t;
    t.distribution = GarchDistribution::StudentT;
    t.degrees_of_freedom = 5.0;
    t.mean = 0.01;
    // Python variance.garch_loglik_t(r, 0.01, 0.1, 0.8, initial, "STUDENT_T", 5.0, 0.01).
    const GarchLoglik a = garch_loglik(r3(), 0.01, 0.1, 0.8, 0.02, t);
    CHECK(near_rel(a.loglik, 1.5543075740725536));
    CHECK(near_all(a.variances, {0.02, 0.02681, 0.035858}));
    CHECK(near_rel(a.next_variance, 0.0388464));
    const GarchLoglik s = garch_loglik(r3(), 0.01, 0.1, 0.8, std::nullopt, t);
    CHECK(near_rel(s.loglik, 1.5479134020778096));
    CHECK(near_all(s.variances, {0.017933333333333336, 0.025156666666666667, 0.034535333333333335}));
    CHECK(near_rel(s.next_variance, 0.03778826666666667));
    GarchLaw n;
    n.mean = 0.01;
    const GarchLoglik m = garch_loglik(r3(), 0.01, 0.1, 0.8, std::nullopt, n);
    CHECK(near_rel(m.loglik, 1.6524254493045563));
    CHECK(near_rel(m.next_variance, 0.03778826666666667));
    // Edges: nu = 2 is out, just above is in; too few returns; missing nu.
    GarchLaw e = t;
    e.degrees_of_freedom = 2.0;
    CHECK(code_of([&] { garch_loglik(r3(), 0.01, 0.1, 0.8, 0.02, e); }) == "E_DOMAIN");
    e.degrees_of_freedom = 2.000001;
    CHECK(code_of([&] { garch_loglik(r3(), 0.01, 0.1, 0.8, 0.02, e); }) == "none");
    CHECK(code_of([&] { garch_loglik({0.1}, 0.01, 0.1, 0.8, 0.02, t); }) == "E_INPUT");
    CHECK(code_of([&] { garch_loglik({0.1, 0.2}, 0.01, 0.1, 0.8, 0.02, t); }) == "none");
    CHECK(code_of([&] { garch_loglik(r3(), 0.0, 0.1, 0.8, 0.02, t); }) == "E_DOMAIN");
    CHECK(code_of([&] { garch_loglik(r3(), 0.01, 0.0, 0.0, 0.02, t); }) == "none");
    // A constant series equal to the mean demeans to zeros: the SAMPLE start is zero.
    CHECK(code_of([&] { garch_loglik({0.01, 0.01}, 0.01, 0.1, 0.8, std::nullopt, n); }) == "E_DOMAIN");
}

TEST_CASE("vol_stats kills: garch forecast closed form and edges") {
    // long-run 0.01 / (1 - 0.9) = 0.1; v_k = 0.1 + 0.9^(k-1) (0.2 - 0.1).
    const GarchForecast f = garch_forecast(0.01, 0.1, 0.8, 0.2, 3, 252.0);
    CHECK(near_all(f.variances, {0.2, 0.19, 0.181}));
    CHECK(near_rel(f.total_variance, 0.571));
    CHECK(near_rel(f.long_run_variance, 0.1));
    CHECK(near_rel(f.annualized_vol, std::sqrt(0.571 * 252.0 / 3.0)));
    const auto fc = [](double o, double a, double b, double v, long long h, double p) {
        return code_of([&] { garch_forecast(o, a, b, v, h, p); });
    };
    CHECK(fc(0.01, 0.1, 0.8, 0.2, 0, 252) == "E_INPUT");
    CHECK(fc(0.01, 0.1, 0.8, 0.2, 1, 252) == "none");
    CHECK(fc(0.01, 0.1, 0.8, 0.2, 1, 0.0) == "E_INPUT");
    CHECK(fc(0.01, 0.1, 0.8, 0.2, 1, 1e-300) == "none");
    CHECK(fc(0.01, 0.1, 0.8, 0.0, 1, 252) == "E_DOMAIN");
    CHECK(fc(0.01, 0.1, 0.8, 1e-300, 1, 252) == "none");
    CHECK(fc(0.0, 0.1, 0.8, 0.2, 1, 252) == "E_DOMAIN");
    CHECK(fc(0.01, 0.25, 0.75, 0.2, 1, 252) == "E_DOMAIN");
    CHECK(fc(0.01, 0.0, 0.0, 0.2, 1, 252) == "none");
    // h = 1 with alpha + beta = 0: one variance, the next variance.
    const GarchForecast g = garch_forecast(0.01, 0.0, 0.0, 0.2, 1, 4.0);
    CHECK(near_all(g.variances, {0.2}));
    CHECK(near_rel(g.annualized_vol, std::sqrt(0.8)));
}

TEST_CASE("vol_stats kills: garch fit and estimate edges") {
    std::vector<double> r(29, 0.01);
    for (std::size_t i = 0; i < r.size(); i += 2) r[i] = -0.012;
    CHECK(code_of([&] { garch_fit(r, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([&] { garch_estimate(r, std::nullopt, GarchDistribution::Normal, false); }) == "E_INPUT");
    r.resize(99, 0.01);
    CHECK(code_of([&] { garch_estimate(r, std::nullopt, GarchDistribution::StudentT, false); }) == "E_INPUT");
}

TEST_CASE("vol_stats kills: realized variance hand values and edges") {
    // Sum of squared log returns ln(101/100), ln(99.5/101), ln(102/99.5), times 252 / 3.
    const VarSwapRealized v = varswap_realized({100, 101, 99.5, 102}, 252.0, 0.04, 10000.0);
    const double a = std::log(1.01), b = std::log(99.5 / 101), c = std::log(102 / 99.5);
    CHECK(near_rel(v.realized_variance, 84.0 * (a * a + b * b + c * c)));
    CHECK(near_rel(v.realized_variance, 0.0788498979464715, 1e-12));  // Python variance.varswap_realized
    CHECK(near_rel(v.realized_vol, 0.28080223992424186, 1e-12));
    CHECK(near_rel(v.payoff, 388.498979464715, 1e-12));
    CHECK(code_of([] { varswap_realized({100}, 252, 0.04, 1); }) == "E_INPUT");
    CHECK(code_of([] { varswap_realized({100, 100}, 252, 0.04, 1); }) == "none");
    CHECK(code_of([] { varswap_realized({100, 0}, 252, 0.04, 1); }) == "E_DOMAIN");
    CHECK(code_of([] { varswap_realized({1e-300, 1}, 252, 0.04, 1); }) == "none");
}

namespace {
VarSwapInputs vs_base() {
    return {day(2026, 1, 1), day(2026, 7, 2), 100.0, 0.03, 0.01, {80.0, 90.0, 100.0}, {100.0, 115.0, 105.0},
            {{80.0, 0.3}, {90.0, 0.25}, {100.0, 0.2}, {105.0, 0.19}, {115.0, 0.18}}, 5.0, 0.04, 1000.0};
}
}  // namespace

TEST_CASE("vol_stats kills: variance swap fair strike value and edges") {
    // Python variance.varswap_fair_strike on the same inputs (unsorted call strikes on purpose).
    const VarSwapFair f = varswap_fair_strike(vs_base());
    CHECK(near_rel(f.fair_variance, 0.048211383289539216, 1e-12));
    CHECK(near_rel(f.fair_vol, 0.21957090720206812, 1e-12));
    CHECK(near_rel(f.pv, 8.089464156083652, 1e-11));
    const auto err = [](auto edit) {
        VarSwapInputs in = vs_base();
        edit(in);
        return code_of([&] { varswap_fair_strike(in); });
    };
    CHECK(err([](VarSwapInputs& in) { in.maturity = in.as_of; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.maturity = in.as_of + std::chrono::days{1}; }) == "none");
    CHECK(err([](VarSwapInputs& in) { in.put_strikes = {}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.call_strikes = {}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.put_strikes = {80, 80, 90, 100}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.call_strikes = {100, 105, 115, 105}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.put_strikes = {80, 90, 100, 105}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.call_strikes = {90, 100, 105, 115}; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.vols.pop_back(); }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.vols.push_back({115.0, 0.18}); }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.vols.back().strike = 120.0; }) == "E_INPUT");
    CHECK(err([](VarSwapInputs& in) { in.vols[2].vol = 0.0; }) == "E_DOMAIN");
    CHECK(err([](VarSwapInputs& in) { in.vols[2].vol = 1e-3; }) == "none");
    CHECK(err([](VarSwapInputs& in) { in.extension_step = 0.0; }) == "E_DOMAIN");
    CHECK(err([](VarSwapInputs& in) { in.extension_step = 80.0; }) == "E_DOMAIN");
    CHECK(err([](VarSwapInputs& in) { in.extension_step = 79.0; }) == "none");
    // A put at spot and a call at spot are both allowed (the base already has them); spot at the edge strike.
    CHECK(err([](VarSwapInputs& in) {
              in.spot = 100.0;
              in.put_strikes = {100.0};
              in.call_strikes = {100.0};
              in.vols = {{100.0, 0.2}};
          }) == "none");
    // Ruling E-B36: a replicated variance below 0 (inputs from the Python kill tests).
    CHECK(err([](VarSwapInputs& in) {
              in.as_of = day(2026, 1, 1);
              in.maturity = day(2027, 1, 1);
              in.rate = 0.5;
              in.dividend_yield = 0.0;
              in.put_strikes = {99.0, 100.0};
              in.call_strikes = {100.0, 101.0};
              in.vols = {{99.0, 0.01}, {100.0, 0.01}, {101.0, 0.01}};
              in.extension_step = 0.5;
          }) == "E_DOMAIN");
}

namespace {
std::vector<VixQuote> strip1() {
    return {{80, 20.5, 21.0, 0.1, 0.2}, {90, 11, 11.4, 0.6, 0.8},  {95, 6.8, 7.0, 1.4, 1.6},  {100, 3.3, 3.5, 3.0, 3.2},
            {105, 1.1, 1.3, 6.0, 6.4},  {110, 0.3, 0.5, 10.2, 10.6}, {120, 0.05, 0.1, 20, 20.5}};
}
std::vector<VixQuote> strip2() {
    std::vector<VixQuote> s = strip1();
    for (auto& q : s) q = {q.strike, *q.call_bid + 0.2, *q.call_bid + 0.4, *q.put_bid + 0.1, *q.put_bid + 0.3};
    return s;
}
}  // namespace

TEST_CASE("vol_stats kills: VIX term variance and index values") {
    // Python variance.vix_term_variance / vix_index on the same strips.
    const VixTermResult a = vix_term_variance({30000, 0.02, strip1()});
    CHECK(near_rel(a.forward, 100.30034266129914));
    CHECK(a.k0 == 100.0);
    CHECK(near_rel(a.variance, 0.1465740821871549, 1e-12));
    CHECK(near_rel(a.t, 30000.0 / 525600.0));
    CHECK(a.strikes_used == std::vector<double>{80, 90, 95, 100, 105, 110, 120});
    const VixTermResult b = vix_term_variance({50000, 0.025, strip2()});
    CHECK(near_rel(b.forward, 100.40095242585657));
    CHECK(near_rel(b.variance, 0.10616637647601626, 1e-12));
    const VixIndex x = vix_index({30000, 0.02, strip1()}, {50000, 0.025, strip2()});
    CHECK(near_rel(x.index, 34.01574411488363, 1e-12));
    CHECK(near_rel(x.near_variance, a.variance));
    CHECK(near_rel(x.next_variance, b.variance));
    // Forward between strikes (K0 = 95), one zero put bid skipped, two zero call bids end the calls.
    const std::vector<VixQuote> s3{{85, 15, 15.2, 0, 0.05},    {90, 10.6, 10.8, 0.6, 0.8}, {95, 6.2, 6.4, 1.6, 1.8},
                                   {100, 2.9, 3.1, 3.3, 3.5},  {105, 0.9, 1.1, 6.4, 6.6},  {110, 0.2, 0.3, 10.6, 10.8},
                                   {115, 0, 0.05, 15, 15.2},   {120, 0, 0.05, 20, 20.2},   {125, 0.01, 0.05, 25, 25.2}};
    const VixTermResult c = vix_term_variance({40000, 0.01, s3});
    CHECK(near_rel(c.forward, 99.59969547013272));
    CHECK(c.k0 == 95.0);
    CHECK(near_rel(c.variance, 0.09293721843209246, 1e-12));
    CHECK(c.strikes_used == std::vector<double>{90, 95, 100, 105, 110});
}

TEST_CASE("vol_stats kills: VIX checks on their edges") {
    const auto term = [](long long m, std::vector<VixQuote> s) { return code_of([&] { vix_term_variance({m, 0.02, s}); }); };
    CHECK(term(0, strip1()) == "E_INPUT");
    CHECK(term(1, strip1()) == "none");
    std::vector<VixQuote> s = strip1();
    s.resize(2);
    CHECK(term(30000, s) == "E_INPUT");
    s = {{90, 11, 11.4, 0.6, 0.8}, {100, 3.3, 3.5, 3.0, 3.2}, {110, 0.3, 0.5, 10.2, 10.6}};
    CHECK(term(30000, s) == "none");
    s = strip1();
    s[2].strike = 90;
    CHECK(term(30000, s) == "E_INPUT");
    s = strip1();
    s[1].put_bid = 0.8;  // bid equal to ask is allowed
    s[1].call_bid = 11.4;
    CHECK(term(30000, s) == "none");
    s[1].put_bid = 0.81;
    CHECK(term(30000, s) == "E_INPUT");
    s = strip1();
    s[1].call_bid = 11.41;
    CHECK(term(30000, s) == "E_INPUT");
    s = strip1();
    s[0].put_bid = 0.0;  // zero quote is allowed
    CHECK(term(30000, s) == "none");
    s[0].put_bid = -0.01;
    CHECK(term(30000, s) == "E_DOMAIN");
    s = strip1();
    s[6].call_ask = -0.01;
    s[6].call_bid = -0.02;
    CHECK(term(30000, s) == "E_DOMAIN");
    // Every out-of-the-money put / call excluded.
    s = strip1();
    for (std::size_t i = 0; i < 3; ++i) s[i].put_bid = std::nullopt;
    CHECK(term(30000, s) == "E_INPUT");
    s = strip1();
    for (std::size_t i = 4; i < 7; ++i) s[i].call_bid = std::nullopt;
    CHECK(term(30000, s) == "E_INPUT");
    // vix_index: the bracket edges, n1 = 30 days and n2 = 30 days are both allowed.
    const auto idx = [](long long n1, long long n2) {
        return code_of([&] { vix_index({n1, 0.02, strip1()}, {n2, 0.025, strip2()}); });
    };
    CHECK(idx(43200, 50000) == "none");
    CHECK(idx(43201, 50000) == "E_INPUT");
    CHECK(idx(30000, 43200) == "none");
    CHECK(idx(30000, 43199) == "E_INPUT");
    CHECK(idx(43200, 43200) == "E_INPUT");
    // n1 = n2 = 30 days would divide by zero; n1 at 30 days uses the near term only (weight on next is 0).
    const VixIndex x = vix_index({43200, 0.02, strip1()}, {50000, 0.025, strip2()});
    CHECK(near_rel(x.index, 100.0 * std::sqrt(x.near_variance)));
    const VixIndex y = vix_index({30000, 0.02, strip1()}, {43200, 0.025, strip2()});
    CHECK(near_rel(y.index, 100.0 * std::sqrt(y.next_variance)));
}

namespace {
// GARCH(1,1) series with a small drift; tnu > 0 gives unit-variance Student-t shocks (normal over a chi-square
// of tnu normals). The same generator, ported to Python, produced the expected values below.
std::vector<double> drift_series(std::size_t n, double omega, double alpha, double beta, int tnu) {
    unsigned long long s = 20261109ULL;
    const auto u = [&] {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        return (double((s >> 11) & ((1ULL << 53) - 1)) + 0.5) / 9007199254740992.0;
    };
    const auto normal = [&] {
        const double a = u();
        return std::sqrt(-2 * std::log(a)) * std::cos(6.283185307179586 * u());
    };
    std::vector<double> r;
    double v = omega / (1 - alpha - beta);
    for (std::size_t i = 0; i < n; ++i) {
        double z = normal();
        if (tnu > 0) {
            double c = 0.0;
            for (int k = 0; k < tnu; ++k) {
                const double g = normal();
                c += g * g;
            }
            z = z / std::sqrt(c / tnu) * std::sqrt(double(tnu - 2) / tnu);
        }
        const double x = std::sqrt(v) * z + 0.0005;
        r.push_back(x);
        v = omega + alpha * x * x + beta * v;
    }
    return r;
}
}  // namespace

// Expected values: Python variance.garch_estimate / garch_fit (numpy Newton polish, independent code) on the same
// series. The Hessian enters only the standard errors, so tight SE checks catch Hessian mistakes the optimum hides.
TEST_CASE("vol_stats kills: garch estimate matches the Python port (normal, demeaned, Student-t)") {
    const std::vector<double> r = drift_series(400, 4e-6, 0.09, 0.88, 0);
    const GarchEstimate n = garch_estimate(r, std::nullopt, GarchDistribution::Normal, false);
    CHECK(n.mean == 0.0);
    CHECK(!n.degrees_of_freedom);
    CHECK(!n.se_degrees_of_freedom);
    CHECK(near_rel(n.loglik, 1237.3228085353899, 1e-12));
    CHECK(near_rel(n.omega, 2.2292615401870416e-06, 1e-7));
    CHECK(near_rel(n.alpha, 0.06421067097221594, 1e-7));
    CHECK(near_rel(n.beta, 0.918761657499621, 1e-8));
    CHECK(near_rel(n.persistence, 0.982972328471837, 1e-9));
    CHECK(near_rel(n.se_omega, 2.0638335248984268e-06, 1e-6));
    CHECK(near_rel(n.se_alpha, 0.027626849984451255, 1e-6));
    CHECK(near_rel(n.se_beta, 0.03429697920374729, 1e-6));
    const GarchFit f = garch_fit(r, std::nullopt);
    CHECK(near_rel(f.loglik, 1237.322808535388, 1e-12));
    CHECK(near_rel(f.alpha, n.alpha, 1e-4));
    CHECK(near_rel(f.beta, n.beta, 1e-5));
    CHECK(near_rel(f.omega, n.omega, 1e-3));

    const GarchEstimate d = garch_estimate(r, std::nullopt, GarchDistribution::Normal, true);
    CHECK(near_rel(d.mean, 5.634039574622141e-05, 1e-10));
    CHECK(near_rel(d.loglik, 1237.3297452674035, 1e-12));
    CHECK(near_rel(d.omega, 2.222491200182798e-06, 1e-7));
    CHECK(near_rel(d.alpha, 0.06408065279847223, 1e-7));
    CHECK(near_rel(d.beta, 0.918933013522448, 1e-8));
    CHECK(near_rel(d.se_omega, 2.057700663129261e-06, 1e-6));
    CHECK(near_rel(d.se_alpha, 0.027553812969650038, 1e-6));
    CHECK(near_rel(d.se_beta, 0.03419803808601487, 1e-6));

    const std::vector<double> rt = drift_series(600, 4e-6, 0.09, 0.88, 5);
    const GarchEstimate t = garch_estimate(rt, std::nullopt, GarchDistribution::StudentT, true);
    REQUIRE(t.degrees_of_freedom);
    REQUIRE(t.se_degrees_of_freedom);
    CHECK(near_rel(t.mean, 0.00043997302795551233, 1e-10));
    CHECK(near_rel(t.loglik, 1892.1801728152418, 1e-12));
    CHECK(near_rel(t.omega, 6.072258446177342e-06, 1e-7));
    CHECK(near_rel(t.alpha, 0.12715829418286145, 1e-7));
    CHECK(near_rel(t.beta, 0.836524756701035, 1e-8));
    CHECK(near_rel(*t.degrees_of_freedom, 4.676842808716924, 1e-7));
    CHECK(near_rel(t.persistence, 0.9636830508838965, 1e-9));
    CHECK(near_rel(t.se_omega, 2.5470433962715344e-06, 1e-6));
    CHECK(near_rel(t.se_alpha, 0.03597271427776877, 1e-6));
    CHECK(near_rel(t.se_beta, 0.038016074998593746, 1e-6));
    CHECK(near_rel(*t.se_degrees_of_freedom, 0.8449552316472203, 1e-6));
}
