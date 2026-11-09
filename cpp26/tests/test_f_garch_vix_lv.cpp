// Stage F wave 1a unit tests (garch_vix_lv). No namespace-scope static objects.
// R8: vol.garch.loglik options and vol.garch.estimate (garch.md "Stage F additions").
// R10: VIX null quotes (vix-index.md, ruling F-15) and local vol at slice expiries (local-and-forward-vol.md, F-17).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/arb_surface.hpp"
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

// A deterministic GARCH(1,1) series (LCG uniforms, Box-Muller normals).
std::vector<double> garch_series(std::size_t n, double omega, double alpha, double beta) {
    unsigned long long s = 20261109ULL;
    const auto u = [&] {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        return (double((s >> 11) & ((1ULL << 53) - 1)) + 0.5) / 9007199254740992.0;
    };
    std::vector<double> r;
    double v = omega / (1 - alpha - beta);
    for (std::size_t i = 0; i < n; ++i) {
        const double z = std::sqrt(-2 * std::log(u())) * std::cos(6.283185307179586 * u());
        const double x = std::sqrt(v) * z;
        r.push_back(x);
        v = omega + alpha * x * x + beta * v;
    }
    return r;
}

bool rel_close(double a, double b, double tol) { return std::fabs(a - b) <= tol * std::fabs(b); }
}  // namespace

TEST_CASE("garch loglik: stage F options at the edges of every check") {
    const std::vector<double> r = garch_series(50, 4e-6, 0.09, 0.88);
    GarchLaw normal;
    // No new keys: identical to the stage E function.
    CHECK(garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, normal).loglik ==
          garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt).loglik);
    // NORMAL ignores degrees_of_freedom, even an invalid one.
    GarchLaw n2 = normal;
    n2.degrees_of_freedom = 1.5;
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, n2); }) == "none");
    GarchLaw t;
    t.distribution = GarchDistribution::StudentT;
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, t); }) == "E_INPUT");
    t.degrees_of_freedom = 2.0;
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, t); }) == "E_DOMAIN");
    t.degrees_of_freedom = std::nextafter(2.0, 3.0);
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, t); }) == "none");
    t.degrees_of_freedom = std::numeric_limits<double>::quiet_NaN();
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, t); }) == "E_DOMAIN");
    GarchLaw m;
    m.mean = std::numeric_limits<double>::infinity();
    CHECK(code_of([&] { garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, m); }) == "E_DOMAIN");
    // A mean equal to every return: SAMPLE on all-zero e is E_DOMAIN.
    const std::vector<double> flat(10, 0.01);
    m.mean = 0.01;
    CHECK(code_of([&] { garch_loglik(flat, 4e-6, 0.09, 0.88, std::nullopt, m); }) == "E_DOMAIN");
    // nu -> infinity: the Student-t loglik tends to the Gaussian one.
    t.degrees_of_freedom = 1e6;
    const double lt = garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, t).loglik;
    const double ln = garch_loglik(r, 4e-6, 0.09, 0.88, std::nullopt, normal).loglik;
    CHECK(std::fabs(lt - ln) < 1e-3);
}

TEST_CASE("garch estimate: input checks at their edges") {
    const std::vector<double> r = garch_series(200, 2e-6, 0.08, 0.90);
    const std::vector<double> r29(r.begin(), r.begin() + 29), r99(r.begin(), r.begin() + 99);
    CHECK(code_of([&] { garch_estimate(r29, std::nullopt, GarchDistribution::Normal, false); }) == "E_INPUT");
    CHECK(code_of([&] { garch_estimate(r99, std::nullopt, GarchDistribution::StudentT, false); }) == "E_INPUT");
    CHECK(code_of([&] { garch_estimate(r, 0.0, GarchDistribution::Normal, false); }) == "E_DOMAIN");
    CHECK(code_of([&] { garch_estimate(r, -1e-4, GarchDistribution::Normal, false); }) == "E_DOMAIN");
    const std::vector<double> flat(40, 0.5);  // exact in binary: the demeaned series is exactly zero
    CHECK(code_of([&] { garch_estimate(flat, std::nullopt, GarchDistribution::Normal, true); }) == "E_DOMAIN");
    std::vector<double> bad = r;
    bad[3] = std::numeric_limits<double>::quiet_NaN();
    CHECK(code_of([&] { garch_estimate(bad, std::nullopt, GarchDistribution::Normal, false); }) == "E_DOMAIN");
}

TEST_CASE("garch estimate: interior maximum, zero gradient, observed-information errors") {
    const std::vector<double> r = garch_series(2000, 2e-6, 0.08, 0.90);
    const GarchEstimate e = garch_estimate(r, std::nullopt, GarchDistribution::Normal, false);
    CHECK(e.alpha > 0.0);
    CHECK(e.persistence < 1.0);
    CHECK(!e.degrees_of_freedom);
    CHECK(e.mean == 0.0);
    // Optimum: small moves in any parameter do not raise the loglik.
    GarchLaw law;
    const double f0 = garch_loglik(r, e.omega, e.alpha, e.beta, std::nullopt, law).loglik;
    CHECK(rel_close(f0, e.loglik, 1e-13));
    for (const double s : {1e-4, -1e-4}) {
        CHECK(garch_loglik(r, e.omega * (1 + s), e.alpha, e.beta, std::nullopt, law).loglik <= f0);
        CHECK(garch_loglik(r, e.omega, e.alpha * (1 + s), e.beta, std::nullopt, law).loglik <= f0);
        CHECK(garch_loglik(r, e.omega, e.alpha, e.beta * (1 + s), std::nullopt, law).loglik <= f0);
    }
    // Curvature: -d2L/dalpha2 by differences gives 1/se^2 only if the others are fixed; it bounds 1/se^2 from above.
    const double h = 1e-4 * e.alpha;
    const double d2 = (garch_loglik(r, e.omega, e.alpha + h, e.beta, std::nullopt, law).loglik - 2 * f0 +
                       garch_loglik(r, e.omega, e.alpha - h, e.beta, std::nullopt, law).loglik) /
                      (h * h);
    CHECK(-d2 > 0.0);
    CHECK(1.0 / (e.se_alpha * e.se_alpha) <= -d2 * (1 + 1e-4));
    // Demeaned: mu is the sample mean.
    const GarchEstimate d = garch_estimate(r, std::nullopt, GarchDistribution::Normal, true);
    double mu = 0.0;
    for (const double x : r) mu += x;
    CHECK(rel_close(d.mean, mu / double(r.size()), 1e-12));
}

TEST_CASE("vix: null quotes (ruling F-15)") {
    const auto none = std::optional<double>();
    const std::vector<VixQuote> base{{80, 20, 20, 0.1, 0.1}, {90, 10.5, 10.5, 0.5, 0.5}, {100, 2, 2, 2, 2},
                                     {110, 0.5, 0.5, 10.5, 10.5}, {120, 0.1, 0.1, 20, 20}};
    const VixTermResult b = vix_term_variance({43200, 0.0, base});
    // A null on a series that is not selected changes nothing; a null deep put drops only that put.
    std::vector<VixQuote> s = base;
    s[0].put_bid = none;
    const VixTermResult a = vix_term_variance({43200, 0.0, s});
    CHECK(a.strikes_used.size() + 1 == b.strikes_used.size());
    CHECK(a.forward == b.forward);
    // A null call at strike 80 does not remove the put at 80.
    s = base;
    s[0].call_ask = none;
    CHECK(vix_term_variance({43200, 0.0, s}).strikes_used == b.strikes_used);
    // K0 with a null side: E_INPUT.
    s = base;
    s[2].call_bid = none;
    CHECK(code_of([&] { vix_term_variance({43200, 0.0, s}); }) == "E_INPUT");
    // No strike with both sides quoted: E_INPUT.
    s = base;
    for (auto& x : s) x.put_ask = none;
    CHECK(code_of([&] { vix_term_variance({43200, 0.0, s}); }) == "E_INPUT");
    // A null put between two zero bids neither counts as a zero nor breaks the run.
    std::vector<VixQuote> z{{60, 40, 40, 0.1, 0.1}, {65, 35, 35, 0, 0.05}, {70, 30, 30, 0.2, 0.2},
                            {75, 25, 25, 0, 0.05},   {80, 20, 20, 0.3, 0.3}, {90, 10.5, 10.5, 0.5, 0.5},
                            {100, 2, 2, 2, 2},       {110, 0.5, 0.5, 10.5, 10.5}, {120, 0.1, 0.1, 20, 20}};
    z[2].put_bid = none;  // 70: removed; 75 and 65 are then two consecutive zero bids, so 60 is not used
    const VixTermResult zr = vix_term_variance({43200, 0.0, z});
    CHECK(zr.strikes_used.front() == 80.0);
    // A crossed quote stays E_INPUT; a negative present quote stays E_DOMAIN; a NaN stays E_DOMAIN.
    s = base;
    s[1].put_bid = 0.6;
    CHECK(code_of([&] { vix_term_variance({43200, 0.0, s}); }) == "E_INPUT");
    s = base;
    s[0].put_ask = none;
    s[0].put_bid = -0.1;
    CHECK(code_of([&] { vix_term_variance({43200, 0.0, s}); }) == "E_DOMAIN");
    s = base;
    s[4].call_bid = std::numeric_limits<double>::quiet_NaN();
    CHECK(code_of([&] { vix_term_variance({43200, 0.0, s}); }) == "E_DOMAIN");
}

namespace {
// SVI total variance and its k derivatives.
struct W {
    double w, wk, wkk;
};
W svi_w(const Svi& s, double k) {
    const double x = k - s.m, r = std::sqrt(x * x + s.sigma * s.sigma);
    return {s.a + s.b * (s.rho * x + r), s.b * (s.rho + x / r), s.b * s.sigma * s.sigma / (r * r * r)};
}
double g_of(const W& v, double k) {
    const double a = 1 - k * v.wk / (2 * v.w);
    return a * a - v.wk * v.wk / 4 * (1 / v.w + 0.25) + v.wkk / 2;
}
}  // namespace

TEST_CASE("local vol: continuity and jumps at slice expiries (ruling F-17)") {
    const std::vector<std::vector<SviSlice>> surfaces{
        {{0.25, {0.02, 0.1, -0.4, 0.02, 0.2}}, {1.0, {0.035, 0.11, -0.35, 0.03, 0.25}}},
        {{0.25, {0.02, 0.1, -0.4, 0.02, 0.2}}, {1.0, {0.035, 0.11, -0.35, 0.03, 0.25}},
         {2.0, {0.06, 0.12, -0.3, 0.04, 0.3}}}};
    for (const auto& sl : surfaces) {
        for (const double k : {-0.4, 0.0, 0.3}) {
            for (std::size_t j = 0; j < sl.size(); ++j) {
                const double tj = sl[j].expiry_years;
                const LocalVol lv = local_vol_dupire(sl, {{tj * (1 - 1e-9), k}, {tj, k}, {tj * (1 + 1e-9), k}});
                INFO("n=" << sl.size() << " k=" << k << " j=" << j);
                CHECK(std::fabs(lv.total_variance[0] - lv.total_variance[1]) <= 1e-9 * lv.total_variance[1]);
                CHECK(std::fabs(lv.implied_vol[0] - lv.implied_vol[1]) <= 1e-9 * lv.implied_vol[1]);
                const W wj = svi_w(sl[j].svi, k);
                const double g = g_of(wj, k);
                const double left = j == 0 ? wj.w / tj
                                           : (wj.w - svi_w(sl[j - 1].svi, k).w) / (tj - sl[j - 1].expiry_years);
                CHECK(rel_close(lv.local_vol[0], std::sqrt(left / g), 1e-8));
                if (j + 1 < sl.size()) {
                    const double right = (svi_w(sl[j + 1].svi, k).w - wj.w) / (sl[j + 1].expiry_years - tj);
                    CHECK(rel_close(lv.local_vol[2], std::sqrt(right / g), 1e-8));
                    CHECK(rel_close(lv.local_vol[1], std::sqrt(right / g), 1e-8));  // a node takes the right limit
                }
            }
            // Inside each interval local vol is continuous.
            double lo = 0.0;
            for (std::size_t j = 0; j <= sl.size(); ++j) {
                const double hi = j < sl.size() ? sl[j].expiry_years : lo * 2;
                for (int i = 1; i <= 5; ++i) {
                    const double t = lo + (hi - lo) * (i - 0.5) / 5;
                    const LocalVol lv = local_vol_dupire(sl, {{t, k}, {t * (1 + 1e-9), k}});
                    CHECK(rel_close(lv.local_vol[1], lv.local_vol[0], 1e-6));
                }
                lo = hi;
            }
        }
    }
    // One slice: no jump at all.
    const std::vector<SviSlice> one{{0.5, {0.02, 0.1, -0.4, 0.02, 0.2}}};
    const LocalVol lv = local_vol_dupire(one, {{0.5 * (1 - 1e-9), 0.1}, {0.5, 0.1}});
    CHECK(rel_close(lv.local_vol[0], lv.local_vol[1], 1e-8));
}
