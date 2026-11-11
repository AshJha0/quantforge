// Stage G property tests: the acceptance checks of 04-pricing/short-rate-models.md, exotics.md "Stage G addition"
// (R9), 06-risk/mc-greeks.md (G-10 report, G-10b gate) and 06-risk/xva-exposure.md.
// No namespace-scope static objects (static-init order has broken ASan before): fixtures are built by functions.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/exotics.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/shortrate.hpp"
#include "quantforge/core/stats.hpp"

using namespace quantforge;
namespace sr = quantforge::shortrate;

namespace {
sr::Curve g_curve() {
    return sr::Curve::from({0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795, 10.005479452054795,
                            15.01095890410959, 20.013698630136986, 30.019178082191782},
                           {0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332});
}

sr::Params g_hw(double a = 0.05, double sigma = 0.01) {
    sr::Params p;
    p.model = sr::Model::HullWhite;
    p.a = a;
    p.sigma = sigma;
    p.curve = g_curve();
    return p;
}

sr::Params g_vasicek() {
    sr::Params p;
    p.model = sr::Model::Vasicek;
    p.a = 0.15, p.b = 0.045, p.sigma = 0.012, p.r0 = 0.035;
    return p;
}

sr::Params g_cir() {
    sr::Params p;
    p.model = sr::Model::Cir;
    p.a = 0.25, p.b = 0.04, p.sigma = 0.08, p.r0 = 0.03;
    return p;
}

std::vector<sr::Params> g_models() { return {g_vasicek(), g_cir(), g_hw()}; }

std::vector<double> g_years(double from, double to, double step) {
    std::vector<double> v;
    for (double t = from; t <= to + 1e-12; t += step) v.push_back(t);
    return v;
}

double g_rel(double x, double y) { return std::fabs(x - y) / std::max(std::fabs(y), 1e-300); }

double g_number_after(const std::string& json, const std::string& key) {
    const auto at = json.find("\"" + key + "\":");
    REQUIRE(at != std::string::npos);
    return std::strtod(json.c_str() + at + key.size() + 3, nullptr);
}
}  // namespace

// ---- Wave 1, G1 ----

TEST_CASE("G1 bond options satisfy put-call parity to 1e-12 per unit face") {
    for (const auto& p : g_models())
        for (const auto& [T, S, K] : {std::tuple{1.0, 5.0, 0.85}, std::tuple{0.5, 20.0, 0.5}, std::tuple{5.0, 10.0, 0.8}}) {
            const double c = sr::bond_option(p, T, S, K, true), q = sr::bond_option(p, T, S, K, false);
            CHECK(std::fabs(c - q - (sr::bond0(p, S) - K * sr::bond0(p, T))) <= 1e-12);
            CHECK(c >= 0);
            CHECK(q >= 0);
        }
}

TEST_CASE("G1 Hull-White zcb at t = 0 returns the curve to 1e-14 relative") {
    const sr::Params p = g_hw();
    const double r0 = p.curve.fwd(0.0);  // the short rate the curve implies at 0
    for (double T : {0.01, 0.4986301369863014, 1.0, 2.5, 7.0, 30.0, 45.0}) CHECK(g_rel(sr::bond(p, 0.0, T, r0), p.curve.df(T)) <= 1e-14);
}

TEST_CASE("G1 zero_rate tends to short_rate as T - t tends to 0") {
    for (const auto& p : g_models())
        for (double r : {0.0, 0.02, 0.07})
            for (double t : {0.0, 0.75, 3.0}) {
                const double tau = 1e-6, P = sr::bond(p, t, t + tau, r);
                CHECK(std::fabs(-std::log(P) / tau - r) <= 1e-6);
            }
}

TEST_CASE("G1 CIR options at low sigma: no underflow of exp(-lambda/2); CDF 0 for x <= 0") {
    CHECK(sr::ncx2_cdf(0.0, 3.0, 5.0) == 0.0);
    CHECK(sr::ncx2_cdf(-1.0, 3.0, 5.0) == 0.0);
    CHECK(std::fabs(sr::ncx2_cdf(4.0, 3.0, 0.0) - sr::gamma_p(1.5, 2.0)) <= 1e-15);  // central limit
    sr::Params p = g_cir();
    for (double s : {0.005, 0.003}) {
        p.sigma = s;  // lambda/2 is far above 745, where exp(-lambda/2) alone underflows
        const double c = sr::bond_option(p, 1.0, 5.0, 0.86, true), q = sr::bond_option(p, 1.0, 5.0, 0.86, false);
        CHECK(std::isfinite(c));
        CHECK(c > 0);
        CHECK(q >= -1e-11);  // put by parity: cancellation at the 1e-12 level
        // Near-deterministic limit: the call is close to its forward intrinsic value.
        CHECK(std::fabs(c - std::max(sr::bond0(p, 5.0) - 0.86 * sr::bond0(p, 1.0), 0.0)) <= 1e-3);
    }
}

// ---- Wave 1, R9 acceptance ----

TEST_CASE("R9 daily down-and-out call and put match an exact-date Monte Carlo within 3 SE") {
    const double S = 100, K = 100, H = 90, r = 0.05, q = 0.02, v = 0.25, T = 1.0;
    const int m = 252;
    const long long paths = 40000;
    const double dt = T / m, drift = (r - q - v * v / 2) * dt, vol = v * std::sqrt(dt), D = std::exp(-r * T);
    Xoshiro256 rng(20261109ULL, 0);
    double sc = 0, sc2 = 0, sp = 0, sp2 = 0;
    for (long long i = 0; i < paths; ++i) {
        double lnS = std::log(S);
        bool out = false;
        for (int k = 0; k < m; ++k) {
            lnS += drift + vol * rng.next_normal();
            if (std::exp(lnS) <= H) out = true;
        }
        const double ST = std::exp(lnS);
        const double c = out ? 0.0 : D * std::max(ST - K, 0.0), pu = out ? 0.0 : D * std::max(K - ST, 0.0);
        sc += c, sc2 += c * c, sp += pu, sp2 += pu * pu;
    }
    const double n = static_cast<double>(paths);
    const auto se = [&](double s1, double s2) { return std::sqrt((s2 - s1 * s1 / n) / (n - 1) / n); };
    const auto cli_price = [&](const char* type) {
        char buf[512];
        std::snprintf(buf, sizeof buf,
                      R"({"schema_version":"1.0","case_id":"r9","operation":"exotic.barrier.price","inputs":{"spot":100,"strike":100,"expiry_years":1,"rate":0.05,"dividend_yield":0.02,"vol":0.25,"option_type":"%s","barrier":90,"barrier_type":"DOWN_OUT","rebate":0,"monitoring":"DISCRETE","monitoring_per_year":252}})",
                      type);
        const auto res = cli::run_case(buf);
        INFO(res.json);
        return g_number_after(res.json, "price");
    };
    const double call = cli_price("CALL"), put = cli_price("PUT");
    // The CLI value is the stage E formula at the BGK-shifted barrier (G-7).
    const ExoticMarket mc{S, K, T, r, q, v, OptionType::Call};
    CHECK(g_rel(call, barrier_price(mc, H * std::exp(-0.5826 * v * std::sqrt(1.0 / m)), 0.0, BarrierType::DownOut)) <= 1e-12);
    INFO("call BGK " << call << " MC " << sc / n << " +- " << se(sc, sc2));
    INFO("put BGK " << put << " MC " << sp / n << " +- " << se(sp, sp2));
    CHECK(std::fabs(call - sc / n) <= 3 * se(sc, sc2));
    CHECK(std::fabs(put - sp / n) <= 3 * se(sp, sp2));
    // The check discriminates: the continuous price is outside 3 SE of the call MC.
    CHECK(std::fabs(barrier_price(mc, H, 0.0, BarrierType::DownOut) - sc / n) > 3 * se(sc, sc2));
}

// ---- Wave 2a and 2f, Jamshidian swaptions ----

TEST_CASE("G2a/G2f payer minus receiver equals annuity (F - K) to 1e-8 per unit notional") {
    for (const auto& p : g_models())
        for (double T0 : {0.5, 1.0, 5.0})
            for (double K : {0.0, 0.03, 0.05}) {
                if (p.model == sr::Model::Cir && K == 0.0) continue;  // no non-negative critical rate (G-20)
                const auto pay = g_years(T0 + 1, T0 + 5, 1.0);
                const auto a = sr::swaption(p, T0, pay, K, true), b = sr::swaption(p, T0, pay, K, false);
                CHECK(std::fabs(a.price - b.price - a.annuity * (a.forward_swap_rate - K)) <= 1e-8);
            }
}

TEST_CASE("G2f CIR with no non-negative critical rate is E_DOMAIN") {
    CHECK_THROWS_AS(sr::swaption(g_cir(), 1.0, {2.0, 3.0}, 0.0, true), Error);
}

// ---- Wave 2b, G2++ ----

namespace {
sr::G2 g_g2(double eta = 0.008, double rho = -0.75) { return {0.5, 0.01, 0.05, eta, rho, g_curve()}; }
}  // namespace

TEST_CASE("G2b G2++ put-call parity, curve at t = 0, and the one-factor limit") {
    const sr::G2 m = g_g2();
    for (const auto& [T, S, K] : {std::tuple{1.0, 5.0, 0.86}, std::tuple{0.5, 20.0, 0.5}}) {
        const double c = sr::g2_bond_option(m, T, S, K, true), q = sr::g2_bond_option(m, T, S, K, false);
        CHECK(std::fabs(c - q - (m.curve.df(S) - K * m.curve.df(T))) <= 1e-12);
    }
    for (double T : {0.01, 1.0, 5.0, 30.0}) CHECK(g_rel(sr::g2_bond(m, 0.0, T, 0.0, 0.0), m.curve.df(T)) <= 1e-14);
    // eta -> 0: the Hull-White price with (a, sigma).
    const sr::G2 one{0.05, 0.01, 0.3, 1e-12, 0.0, g_curve()};
    const sr::Params hw = g_hw(0.05, 0.01);
    CHECK(g_rel(sr::g2_bond_option(one, 1.0, 5.0, 0.86, true), sr::bond_option(hw, 1.0, 5.0, 0.86, true)) <= 1e-9);
    // Small a or b uses the series: continuous across a tau = 1e-2.
    const sr::G2 lo{1e-2 / 5.0 * (1 - 1e-9), 0.01, 0.3, 0.008, 0.2, g_curve()}, hi{1e-2 / 5.0 * (1 + 1e-9), 0.01, 0.3, 0.008, 0.2, g_curve()};
    CHECK(g_rel(sr::g2_bond(lo, 1.0, 6.0, 0.003, -0.002), sr::g2_bond(hi, 1.0, 6.0, 0.003, -0.002)) <= 1e-12);
}

// ---- Wave 2c, calibration ----

TEST_CASE("G2c calibration recovers sigma from exact targets") {
    const sr::Params p = g_hw(0.01, 0.007);
    std::vector<sr::CalSwaption> strip;
    for (double T0 : {1.0, 2.0, 3.0, 5.0, 7.0}) {
        const auto pay = g_years(T0 + 1, 10.0, 1.0);
        const double F = sr::swaption(p, T0, pay, 0.04, true).forward_swap_rate;
        strip.push_back({T0, pay, F, true, sr::swaption(p, T0, pay, F, true).price});
    }
    const sr::Calibration c = sr::hw_calibrate(p.curve, 0.01, strip);
    CHECK(g_rel(c.sigma, 0.007) <= 1e-9);
    CHECK(c.rmse <= 1e-12);
}

// ---- Wave 2d, Bermudan scheme ----

TEST_CASE("G2d one exercise date converges to Jamshidian at order about 1; Bermudan >= European") {
    const sr::Params p = g_hw();
    const std::vector<double> pay{2.0, 3.0, 4.0, 5.0, 6.0};
    const double jam = sr::swaption(p, 1.0, pay, 0.04, true).price;
    std::vector<double> err;
    for (const auto& [nx, spy] : {std::pair{51LL, 25LL}, std::pair{101LL, 50LL}, std::pair{201LL, 100LL}, std::pair{401LL, 200LL}})
        err.push_back(std::fabs(sr::bermudan_swaption(p, pay, 0.04, true, {1.0}, {nx, spy, 6.0}) - jam));
    for (std::size_t i = 1; i < err.size(); ++i) CHECK(err[i] < err[i - 1]);
    const double order = std::log2(err[2] / err[3]);
    INFO("errors per unit notional " << err[0] << " " << err[1] << " " << err[2] << " " << err[3] << ", last order " << order);
    CHECK(order > 0.6);
    CHECK(order < 1.4);
    for (bool payer : {true, false})
        for (double K : {0.035, 0.04, 0.045}) {
            const double berm = sr::bermudan_swaption(p, pay, K, payer, {1.0, 2.0, 3.0, 4.0, 5.0}, {201, 100, 6.0});
            const double euro = sr::bermudan_swaption(p, pay, K, payer, {1.0}, {201, 100, 6.0});
            CHECK(berm >= euro);
            CHECK(berm >= sr::swaption(p, 1.0, pay, K, payer).price * (1 - 0.01));
        }
}

// ---- Wave 2e, caps and floors ----

TEST_CASE("G2e cap minus floor equals the swaplet sum on the model's bond prices") {
    for (const auto& p : g_models())
        for (double K : {0.03, 0.04, 0.05}) {
            const auto t = g_years(0.5, 5.0, 0.5);
            const double cap = sr::capfloor(p, t, K, true).price, floor = sr::capfloor(p, t, K, false).price;
            double swaplets = 0.0;
            for (std::size_t i = 1; i < t.size(); ++i)
                swaplets += sr::bond0(p, t[i - 1]) - (1 + K * (t[i] - t[i - 1])) * sr::bond0(p, t[i]);
            CHECK(std::fabs(cap - floor - swaplets) <= 1e-12);
        }
}

// ---- Wave 2g, callable bonds ----

TEST_CASE("G2g no call times converges to the straight bond at order about 1; callable <= straight") {
    const sr::Params p = g_hw();
    const auto pay = g_years(1.0, 10.0, 1.0);
    const double c = 0.045;
    double straight = 0.0;
    for (std::size_t i = 0; i < pay.size(); ++i) straight += c * (pay[i] - (i ? pay[i - 1] : 0.0)) * p.curve.df(pay[i]);
    straight += p.curve.df(pay.back());
    std::vector<double> err;
    for (const auto& [nx, spy] : {std::pair{51LL, 25LL}, std::pair{101LL, 50LL}, std::pair{201LL, 100LL}, std::pair{401LL, 200LL}})
        err.push_back(std::fabs(sr::callable_bond(p, pay, c, {}, 1.0, {nx, spy, 6.0}) - straight));
    for (std::size_t i = 1; i < err.size(); ++i) {
        const double order = std::log2(err[i - 1] / err[i]);
        INFO("step " << i << " order " << order);
        CHECK(order > 0.8);
        CHECK(order < 1.2);
    }
    for (double cc : {0.03, 0.045, 0.06})
        for (const auto& calls : {std::vector<double>{3, 4, 5, 6, 7, 8, 9}, std::vector<double>{5}}) {
            double s = p.curve.df(10.0);
            for (std::size_t i = 0; i < pay.size(); ++i) s += cc * (pay[i] - (i ? pay[i - 1] : 0.0)) * p.curve.df(pay[i]);
            CHECK(sr::callable_bond(p, pay, cc, calls, 1.0, {201, 100, 6.0}) <= s);
        }
}

// ---- Wave 3a, Q9 Monte Carlo Greeks ----

namespace {
mcgreeks::Inputs g_digital(mcgreeks::Method m, long long paths, std::uint64_t seed, int stream = 0) {
    mcgreeks::Inputs q{};
    q.spot = 100, q.strike = 100, q.expiry_years = 1, q.rate = 0.03, q.dividend_yield = 0, q.vol = 0.2;
    q.payoff = mcgreeks::Payoff::DigitalCall;
    q.method = m;
    q.paths = paths;
    q.seed = seed;
    q.stream = stream;
    return q;
}

struct Moments {
    double var, kurt;
};
Moments g_moments(const std::vector<double>& x) {
    double m = 0.0;
    for (double v : x) m += v;
    m /= static_cast<double>(x.size());
    double m2 = 0.0, m4 = 0.0;
    for (double v : x) {
        const double d = (v - m) * (v - m);
        m2 += d;
        m4 += d * d;
    }
    const double n = static_cast<double>(x.size());
    const double var = m2 / (n - 1);
    return {var, (m4 / n) / (var * var)};
}
}  // namespace

TEST_CASE("Q9 G-10 as registered (report only) and G-10b (gating)") {
    const double closed = std::exp(-0.03) * std::exp(-0.5 * std::pow((0.03 - 0.02) / 0.2, 2)) / std::sqrt(2 * 3.14159265358979323846) / (100 * 0.2);
    // G-10, 100,000 paths, seed 20261109, eps = 1, h = 0.01: reported, not gating (owner decision, low power).
    {
        auto pw = g_digital(mcgreeks::Method::Pathwise, 100000, 20261109ULL);
        pw.smoothing_width = 1.0;
        auto bump = g_digital(mcgreeks::Method::Bump, 100000, 20261109ULL);
        bump.bump_relative = 0.01;
        const auto lr = mcgreeks::greeks(g_digital(mcgreeks::Method::LikelihoodRatio, 100000, 20261109ULL));
        const double vpw = g_moments(mcgreeks::delta_terms(pw)).var, vb = g_moments(mcgreeks::delta_terms(bump)).var;
        std::printf("G-10 (report): closed delta %.7f, LR %.7f +- %.7f (z = %.3f); variance pathwise %.7f, bump %.7f, ratio %.4f\n",
                    closed, lr.delta, lr.delta_se, (lr.delta - closed) / lr.delta_se, vpw, vb, vpw / vb);
    }
    // G-10b: seed 20261110, stream 0 pathwise (eps = 1), stream 1 bump (h = 0.001), 60,000 paths each.
    auto pw = g_digital(mcgreeks::Method::Pathwise, 60000, 20261110ULL, 0);
    pw.smoothing_width = 1.0;
    auto bump = g_digital(mcgreeks::Method::Bump, 60000, 20261110ULL, 1);
    bump.bump_relative = 0.001;
    const Moments a = g_moments(mcgreeks::delta_terms(pw)), b = g_moments(mcgreeks::delta_terms(bump));
    const double n = 60000.0;
    const double se = std::sqrt((a.kurt - 1) / n + (b.kurt - 1) / n);
    const double Z = (std::log(b.var) - std::log(a.var)) / se;
    const double ratio = a.var / b.var;
    std::printf("G-10b: variance pathwise %.7f, bump %.7f, ratio %.4f [%.4f, %.4f], kurtoses %.2f %.2f, Z = %.2f\n", a.var, b.var,
                ratio, ratio * std::exp(-1.96 * se), ratio * std::exp(1.96 * se), a.kurt, b.kurt, Z);
    CHECK(Z > 1.6449);
}

TEST_CASE("Q9 estimators agree with Black-Scholes on a call") {
    mcgreeks::Inputs q{};
    q.spot = 100, q.strike = 100, q.expiry_years = 1, q.rate = 0.03, q.dividend_yield = 0.01, q.vol = 0.2;
    q.payoff = mcgreeks::Payoff::Call;
    q.paths = 200000;
    q.seed = 20261109ULL;
    const double d1 = (0.03 - 0.01 + 0.02) / 0.2, d2 = d1 - 0.2;
    const double price = 100 * std::exp(-0.01) * normal_cdf(d1) - 100 * std::exp(-0.03) * normal_cdf(d2);
    const double delta = std::exp(-0.01) * normal_cdf(d1), vega = 100 * std::exp(-0.01) * std::exp(-d1 * d1 / 2) / std::sqrt(2 * 3.14159265358979323846);
    for (auto m : {mcgreeks::Method::Pathwise, mcgreeks::Method::LikelihoodRatio, mcgreeks::Method::Bump}) {
        q.method = m;
        q.bump_relative = m == mcgreeks::Method::Bump ? 0.01 : 0.0;
        const auto r = mcgreeks::greeks(q);
        CHECK(std::fabs(r.price - price) <= 4 * r.price_se);
        CHECK(std::fabs(r.delta - delta) <= 4 * r.delta_se + 1e-4);
        CHECK(std::fabs(r.vega - vega) <= 4 * r.vega_se + 1e-2);
    }
}

// ---- Wave 4a, exposure ----

TEST_CASE("G5a PAY minus RECEIVE EE equals the forward value of the remaining swap") {
    const sr::Params p = g_hw();
    for (const auto& [T0, pay, times] :
         {std::tuple{0.0, g_years(1, 5, 1), std::vector<double>{1, 2, 3, 4}},
          std::tuple{0.0, g_years(0.5, 10, 0.5), g_years(0.5, 9.5, 0.5)}, std::tuple{2.0, g_years(3, 7, 1), std::vector<double>{2, 4, 6}}}) {
        for (double K : {0.03, 0.045}) {
            const auto a = sr::swap_ee_hw(p, T0, pay, K, true, times, std::pair{0.02, 0.4});
            const auto b = sr::swap_ee_hw(p, T0, pay, K, false, times, std::nullopt);
            CHECK(a.cva.has_value());
            CHECK_FALSE(b.cva.has_value());
            for (std::size_t k = 0; k < times.size(); ++k) {
                const double t = times[k];
                double fwd = p.curve.df(t) - p.curve.df(pay.back()), prev = t;
                for (double T : pay)
                    if (T > t) fwd -= K * (T - prev) * p.curve.df(T), prev = T;
                CHECK(std::fabs(a.discounted_ee[k] - b.discounted_ee[k] - fwd) <= 1e-13);
            }
        }
    }
}
