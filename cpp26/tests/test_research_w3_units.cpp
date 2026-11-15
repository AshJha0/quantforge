// Stage J wave 3 unit tests (rulings J-W3-2 to J-W3-13): hand-derived expected values for the scenario replay,
// the interpolation backtests and the drift detectors, plus every error path. Each expected value is worked
// out in the comment next to it, not copied from an implementation run.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <functional>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace rs = quantforge::research;
using Vec = std::vector<double>;
using LL = std::vector<long long>;

namespace {
std::string code_of(const std::function<void()>& f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code() + ":" + e.field();
    }
    return "none";
}
bool near(double a, double b, double tol = 1e-12) { return std::fabs(a - b) <= tol; }
}  // namespace

TEST_CASE("w3u historical shock: shifts, level and slope", "[research][w3u]") {
    // Shifts in bp: (2-1)*100 = 100, (4-2)*100 = 200; level = mean = 150; slope = last - first = 100.
    const rs::Shock s = rs::historical_shock({10, 20, 30}, {1, 2}, {{1, 2}, {1.5, 2.5}, {2, 4}}, 10, 30);
    REQUIRE(s.start_yields == Vec{1, 2});
    REQUIRE(s.end_yields == Vec{2, 4});
    REQUIRE(s.shift_bp == Vec{100, 200});
    REQUIRE(s.level_bp == 150.0);
    REQUIRE(s.slope_bp == 100.0);
    // Middle dates: 20 -> 30 gives (0.5, 1.5) -> 50 and 150 bp.
    const rs::Shock m = rs::historical_shock({10, 20, 30}, {1, 2}, {{1, 2}, {1.5, 2.5}, {2, 4}}, 20, 30);
    REQUIRE(m.shift_bp == Vec{50, 150});
    REQUIRE(m.level_bp == 100.0);
}

TEST_CASE("w3u historical shock error paths", "[research][w3u]") {
    const Vec t{1, 2};
    const rs::Matrix2 y{{1, 2}, {1.5, 2.5}, {2, 4}};
    REQUIRE(code_of([&] { rs::historical_shock({}, t, {}, 1, 2); }) == "E_INPUT:yields");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20}, t, y, 10, 20); }) == "E_INPUT:yields");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, {{1, 2}, {1}, {2, 4}}, 10, 30); }) == "E_INPUT:yields");
    REQUIRE(code_of([&] { rs::historical_shock({10, 10, 30}, t, y, 10, 30); }) == "E_DATE_ORDER:dates");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, {2, 1}, y, 10, 30); }) == "E_DOMAIN:tenors");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, {0, 1}, y, 10, 30); }) == "E_DOMAIN:tenors");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, y, 20, 20); }) == "E_DATE_ORDER:end_date");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, y, 30, 20); }) == "E_DATE_ORDER:end_date");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, y, 15, 30); }) == "E_DOMAIN:start_date");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, y, 10, 35); }) == "E_DOMAIN:end_date");
    REQUIRE(code_of([&] { rs::historical_shock({10, 20, 30}, t, y, 10, 25); }) == "E_DOMAIN:end_date");
}

TEST_CASE("w3u replay: interior interpolation, scale and P&L", "[research][w3u]") {
    // Shock curve (1, 0), (2, 10), (4, 30). At 3: segment 2..4, u = 0.5, 10 + 0.5 * 20 = 20; scale 2 -> 40 bp.
    // At 1.5: 0 + 0.5 * 10 = 5 -> 10 bp. At 2 (a knot): 10 -> 20 bp. Yields move by bp / 100.
    // P&L = -(dv01 . applied) = -(1 * 10 + 2 * 20 + 3 * 40) = -170.
    const rs::Replay r = rs::replay({1.5, 2, 3}, {1, 2, 3}, {1, 2, 4}, {0, 10, 30}, 2.0, Vec{1, 2, 3});
    REQUIRE(r.applied_bp == Vec{10, 20, 40});
    REQUIRE(near(r.shocked_yields[0], 1.1));
    REQUIRE(near(r.shocked_yields[1], 2.2));
    REQUIRE(near(r.shocked_yields[2], 3.4));
    REQUIRE(r.pnl.has_value());
    REQUIRE(*r.pnl == -170.0);
    // Exactly at the ends and beyond: flat.
    const rs::Replay f = rs::replay({1, 4, 9}, {0, 0, 0}, {1, 2, 4}, {0, 10, 30}, 1.0, std::nullopt);
    REQUIRE(f.applied_bp == Vec{0, 30, 30});
    REQUIRE_FALSE(f.pnl.has_value());
    // Uneven segment: (1, 0) to (5, 40) at 2 gives u = 0.25 -> 10.
    REQUIRE(rs::replay({2}, {0}, {1, 5}, {0, 40}, 1.0, std::nullopt).applied_bp == Vec{10});
}

TEST_CASE("w3u replay error paths", "[research][w3u]") {
    const Vec bt{1, 2}, by{1, 1}, st{1, 2}, sb{1, 1};
    REQUIRE(code_of([&] { rs::replay({}, {}, st, sb, 1, std::nullopt); }) == "E_INPUT:base_yields");
    REQUIRE(code_of([&] { rs::replay(bt, {1}, st, sb, 1, std::nullopt); }) == "E_INPUT:base_yields");
    REQUIRE(code_of([&] { rs::replay(bt, by, {}, {}, 1, std::nullopt); }) == "E_INPUT:shock_bp");
    REQUIRE(code_of([&] { rs::replay(bt, by, st, {1}, 1, std::nullopt); }) == "E_INPUT:shock_bp");
    REQUIRE(code_of([&] { rs::replay(bt, by, st, sb, 1, Vec{1}); }) == "E_INPUT:dv01");
    REQUIRE(code_of([&] { rs::replay({2, 1}, by, st, sb, 1, std::nullopt); }) == "E_DOMAIN:base_tenors");
    REQUIRE(code_of([&] { rs::replay({1, 1}, by, st, sb, 1, std::nullopt); }) == "E_DOMAIN:base_tenors");
    REQUIRE(code_of([&] { rs::replay({-1, 1}, by, st, sb, 1, std::nullopt); }) == "E_DOMAIN:base_tenors");
    REQUIRE(code_of([&] { rs::replay(bt, by, {0, 1}, sb, 1, std::nullopt); }) == "E_DOMAIN:shock_tenors");
    REQUIRE(code_of([&] { rs::replay(bt, by, {3, 1}, sb, 1, std::nullopt); }) == "E_DOMAIN:shock_tenors");
}

TEST_CASE("w3u interp LOO backtest, linear", "[research][w3u]") {
    // y = (0, 1, 4, 10) on x = 0..3. Drop 1: line 0 -> 4 at 1 gives 2, error +1. Drop 2: line 1 -> 10 at 2 gives
    // 5.5, error +1.5. max 1.5, rmse sqrt((1 + 2.25) / 2).
    const rs::LooBacktest r = rs::interp_loo(0, {0, 1, 2, 3}, {0, 1, 4, 10});
    REQUIRE(r.errors.size() == 2);
    REQUIRE(near(r.errors[0], 1.0));
    REQUIRE(near(r.errors[1], 1.5));
    REQUIRE(near(r.max_abs_error, 1.5));
    REQUIRE(near(r.rmse, std::sqrt(1.625)));
    // Negative errors: the max is of absolute values. y = (0, -1, -4, -10) mirrors the errors.
    const rs::LooBacktest n = rs::interp_loo(0, {0, 1, 2, 3}, {0, -1, -4, -10});
    REQUIRE(near(n.errors[1], -1.5));
    REQUIRE(near(n.max_abs_error, 1.5));
    // Uneven knots: x = (0, 1, 4), y = (0, 0, 8): drop 1, line 0 -> 8 over 0..4 at 1 gives 2, error 2.
    REQUIRE(near(rs::interp_loo(0, {0, 1, 4}, {0, 0, 8}).errors[0], 2.0));
    // Cubic needs n - 1 >= 3: n = 4 runs, n = 3 refuses. A straight line is reproduced exactly.
    const rs::LooBacktest c = rs::interp_loo(2, {0, 1, 2, 3}, {0, 1, 2, 3});
    REQUIRE(near(c.max_abs_error, 0.0, 1e-12));
    const rs::LooBacktest p = rs::interp_loo(3, {0, 1, 2, 3}, {0, 1, 2, 3});
    REQUIRE(near(p.rmse, 0.0, 1e-12));
}

TEST_CASE("w3u interp LOO error paths", "[research][w3u]") {
    REQUIRE(code_of([] { rs::interp_loo(0, {0, 1}, {0, 1}); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::interp_loo(0, {0, 1, 2}, {0, 1}); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::interp_loo(2, {0, 1, 2}, {0, 1, 2}); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::interp_loo(0, {0, 2, 1}, {0, 1, 2}); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::interp_loo(0, {0, 1, 1}, {0, 1, 2}); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::interp_loo(0, {0, 1, 2}, {0, 1, 2}); }) == "none");
}

TEST_CASE("w3u surface holdout, linear in total variance", "[research][w3u]") {
    // Expiry 4, vols (0.1, 0.2, 0.3) on strikes 1..3, hold out strike 2. Total variances at 1 and 3:
    // 0.01 * 4 = 0.04, 0.09 * 4 = 0.36; linear at 2: 0.2; vol sqrt(0.2 / 4) = sqrt(0.05); error sqrt(0.05) - 0.2.
    // Expiry 1, flat 0.2: error 0. max = e, rmse = sqrt(e^2 / 2).
    const double e = std::sqrt(0.05) - 0.2;
    const rs::SurfaceBacktest r = rs::surface_holdout(0, {4, 1}, {1, 2, 3}, {{0.1, 0.2, 0.3}, {0.2, 0.2, 0.2}}, {1});
    REQUIRE(r.errors.size() == 2);
    REQUIRE(near(r.errors[0][0], e));
    REQUIRE(near(r.errors[1][0], 0.0));
    REQUIRE(near(r.max_abs_error, e));
    REQUIRE(near(r.rmse, e / std::sqrt(2.0)));
    // Two held strikes: strikes 1..4, hold 1 and 2, kept 1 and 4 (w = v^2 t with t = 1): w = 0.01, 0.16;
    // at 2: 0.06, at 3: 0.11. Vols at 2 and 3 set to sqrt of those -> zero errors.
    const rs::SurfaceBacktest z =
        rs::surface_holdout(0, {1}, {1, 2, 3, 4}, {{0.1, std::sqrt(0.06), std::sqrt(0.11), 0.4}}, {1, 2});
    REQUIRE(z.errors[0].size() == 2);
    REQUIRE(near(z.max_abs_error, 0.0, 1e-12));
}

TEST_CASE("w3u surface holdout error paths", "[research][w3u]") {
    const Vec k{1, 2, 3};
    const rs::Matrix2 v{{0.1, 0.2, 0.3}};
    REQUIRE(code_of([&] { rs::surface_holdout(0, {}, k, {}, {1}); }) == "E_INPUT:vols");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1, 2}, k, v, {1}); }) == "E_INPUT:vols");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, k, {{0.1, 0.2}}, {1}); }) == "E_INPUT:vols");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, {1, 3, 2}, v, {1}); }) == "E_INPUT:strikes");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, k, v, {}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, k, v, {0}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, k, v, {2}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, {1, 2, 3, 4}, {{.1, .2, .3, .4}}, {2, 1}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, {1, 2, 3, 4}, {{.1, .2, .3, .4}}, {1, 1}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, {1, 2, 3, 4}, {{.1, .2, .3, .4}}, {1, 2}); }) == "none");
    REQUIRE(code_of([&] { rs::surface_holdout(2, {1}, {1, 2, 3, 4}, {{.1, .2, .3, .4}}, {1, 2}); }) == "E_INPUT:holdout");
    REQUIRE(code_of([&] { rs::surface_holdout(2, {1}, {1, 2, 3, 4}, {{.1, .2, .3, .4}}, {1}); }) == "none");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {0}, k, v, {1}); }) == "E_DOMAIN:expiries");
    REQUIRE(code_of([&] { rs::surface_holdout(0, {1}, k, {{0.1, 0.2, 0.0}}, {1}); }) == "E_DOMAIN:vols");
}

TEST_CASE("w3u cusum: scaling, direction, reset and boundaries", "[research][w3u]") {
    // sigma 2 halves the z-scores: x = (0, 6, 6) -> z = (0, 3, 3); s+ = 0, 2.5, 5 > 4 at t = 2.
    REQUIRE(rs::cusum({0, 6, 6}, 0.5, 4, 0, 2, true).alarms == LL{2});
    // mu0 10: x = 11 -> z = 1, s+ = 0.5 > 0.4.
    REQUIRE(rs::cusum({11}, 0.5, 0.4, 10, 1, true).alarms == LL{0});
    // Downward: z = -3, -3: s- = 2.5, 5 > 4 at t = 1, direction -1.
    const rs::Alarms d = rs::cusum({-3, -3}, 0.5, 4, 0, 1, false);
    REQUIRE(d.alarms == LL{1});
    REQUIRE(d.directions == LL{-1});
    REQUIRE(d.s_minus == 5.0);
    REQUIRE(d.s_plus == 0.0);
    // No reset stops at the first alarm and keeps the statistic; reset alarms every step.
    const rs::Alarms n = rs::cusum({5, 5, 5}, 0.5, 4, 0, 1, false);
    REQUIRE(n.alarms == LL{0});
    REQUIRE(n.s_plus == 4.5);
    REQUIRE(rs::cusum({5, 5, 5}, 0.5, 4, 0, 1, true).alarms == LL{0, 1, 2});
    // Exactly h does not alarm: z = 4.5, s+ = 4.
    const rs::Alarms b = rs::cusum({4.5}, 0.5, 4, 0, 1, true);
    REQUIRE(b.alarms.empty());
    REQUIRE(b.s_plus == 4.0);
    // s- after one small negative step: 1 - 0.5.
    REQUIRE(rs::cusum({-1}, 0.5, 4, 0, 1, true).s_minus == 0.5);
    REQUIRE(code_of([] { rs::cusum({1}, 0, 1, 0, 1, true); }) == "E_DOMAIN:k");
    REQUIRE(code_of([] { rs::cusum({1}, 1, 0, 0, 1, true); }) == "E_DOMAIN:k");
    REQUIRE(code_of([] { rs::cusum({1}, 1, 1, 0, 0, true); }) == "E_DOMAIN:k");
    REQUIRE(code_of([] { rs::cusum({}, 1, 1, 0, 1, true); }) == "E_INPUT:x");
}

TEST_CASE("w3u page-hinkley: directions, delta and reset", "[research][w3u]") {
    // x = (0, 0, 10): at t = 2 the running mean is 10/3, the up sum gains 20/3 ~ 6.67 > 5.
    const rs::Alarms u = rs::page_hinkley({0, 0, 10}, 0, 5, 0, false);
    REQUIRE(u.alarms == LL{2});
    REQUIRE(u.directions == LL{1});
    REQUIRE(rs::page_hinkley({0, 0, 10}, 0, 5, 1, false).alarms == LL{2});
    REQUIRE(rs::page_hinkley({0, 0, 10}, 0, 5, -1, false).alarms.empty());
    const rs::Alarms dn = rs::page_hinkley({0, 0, -10}, 0, 5, -1, false);
    REQUIRE(dn.alarms == LL{2});
    REQUIRE(dn.directions == LL{-1});
    REQUIRE(rs::page_hinkley({0, 0, -10}, 0, 5, 0, false).directions == LL{-1});
    REQUIRE(rs::page_hinkley({0, 0, -10}, 0, 5, 1, false).alarms.empty());
    // lambda 6.6 still alarms (6.67), 6.7 does not.
    REQUIRE(rs::page_hinkley({0, 0, 10}, 0, 6.6, 0, false).alarms == LL{2});
    REQUIRE(rs::page_hinkley({0, 0, 10}, 0, 6.7, 0, false).alarms.empty());
    // delta 2: up = -2, -4 (min -4), then -4 + 20/3 - 2 = 2/3; rise 14/3 ~ 4.67 < 5: no alarm. 4.6 alarms.
    REQUIRE(rs::page_hinkley({0, 0, 10}, 2, 5, 0, false).alarms.empty());
    REQUIRE(rs::page_hinkley({0, 0, 10}, 2, 4.6, 0, false).alarms == LL{2});
    // Reset restarts the mean: the same pattern again alarms at t = 5; without reset only t = 2.
    REQUIRE(rs::page_hinkley({0, 0, 10, 0, 0, 10}, 0, 5, 0, true).alarms == LL{2, 5});
    REQUIRE(rs::page_hinkley({0, 0, 10, 0, 0, 10}, 0, 5, 0, false).alarms == LL{2});
    REQUIRE(code_of([] { rs::page_hinkley({1}, -1, 1, 0, true); }) == "E_DOMAIN:delta");
    REQUIRE(code_of([] { rs::page_hinkley({1}, 0, 0, 0, true); }) == "E_DOMAIN:delta");
    REQUIRE(code_of([] { rs::page_hinkley({}, 0, 1, 0, true); }) == "E_INPUT:x");
    REQUIRE(code_of([] { rs::page_hinkley({1}, 0, 1, 0, true); }) == "none");
}

TEST_CASE("w3u psi: quantile edges, floor and alarm", "[research][w3u]") {
    Vec ref;
    for (int i = 0; i < 10; ++i) ref.push_back(i);
    // bins 2: edge r[(10 + 1) / 2 - 1] = r[4] = 4; values <= 4 go to bin 0. Reference shares 0.5, 0.5.
    // Test (0, 0, 0, 9): 0.75, 0.25. PSI = 0.25 ln 1.5 + (-0.25) ln 0.5 = 0.25 ln 3.
    const rs::Psi p = rs::psi(ref, {0, 0, 0, 9}, 2, 0.25);
    REQUIRE(p.reference_shares == Vec{0.5, 0.5});
    REQUIRE(p.test_shares == Vec{0.75, 0.25});
    REQUIRE(near(p.psi, 0.25 * std::log(3.0)));
    REQUIRE(p.alarm);
    REQUIRE_FALSE(rs::psi(ref, {0, 0, 0, 9}, 2, 0.3).alarm);
    // bins 3: edges r[3] = 3 and r[6] = 6. Reference: {0..3} 0.4, {4..6} 0.3, {7..9} 0.3.
    // Test (3, 3, 3): all on the first edge (inclusive), the empty bins floor at 1e-4.
    const rs::Psi q = rs::psi(ref, {3, 3, 3}, 3, 0.1);
    REQUIRE(q.reference_shares == Vec{0.4, 0.3, 0.3});
    REQUIRE(q.test_shares == Vec{1.0, 1e-4, 1e-4});
    const double want = 0.6 * std::log(1.0 / 0.4) + 2 * (1e-4 - 0.3) * std::log(1e-4 / 0.3);
    REQUIRE(near(q.psi, want, 1e-12));
    REQUIRE(rs::psi(ref, {3.5, 6, 7}, 3, 0.1).test_shares[1] == 2.0 / 3.0);
    // PSI 0 against a tiny positive threshold does not alarm (strict >).
    REQUIRE_FALSE(rs::psi(ref, ref, 2, 1e-300).alarm);
    REQUIRE(code_of([&] { rs::psi(ref, ref, 1, 0.1); }) == "E_INPUT:bins");
    REQUIRE(code_of([&] { rs::psi({1, 2}, ref, 3, 0.1); }) == "E_INPUT:reference");
    REQUIRE(code_of([&] { rs::psi(ref, {1, 2}, 3, 0.1); }) == "E_INPUT:reference");
    REQUIRE(code_of([&] { rs::psi(ref, {1, 2, 3}, 3, 0.1); }) == "none");
    REQUIRE(code_of([&] { rs::psi(ref, ref, 2, 0); }) == "E_DOMAIN:threshold");
}

TEST_CASE("w3u ks: ties, unequal sizes, levels and errors", "[research][w3u]") {
    // a = (1, 2), b = (2, 3): after 1, |1*2 - 0| = 2; after the tie at 2, |2*2 - 1*2| = 2; D = 2 / 4.
    // p for n = m = 2, d = 2: no path stays strictly inside |2i - 2j| < 2 (i == j), so p = 1.
    const rs::Ks t = rs::ks({2, 1}, {3, 2}, 0.05);
    REQUIRE(t.statistic == 0.5);
    REQUIRE(t.p_value == 1.0);
    REQUIRE_FALSE(t.reject);
    // a = (1, 2, 3), b = (4, 5): D = 1; only the two extreme paths leave the band: p = 2 / C(5, 2) = 0.2.
    const rs::Ks u = rs::ks({3, 1, 2}, {5, 4}, 0.2);
    REQUIRE(u.statistic == 1.0);
    REQUIRE(near(u.p_value, 0.2, 1e-15));
    REQUIRE(u.reject);
    REQUIRE_FALSE(rs::ks({3, 1, 2}, {5, 4}, 0.19).reject);
    // Identical samples: D = 0, p = 1.
    const rs::Ks s = rs::ks({1, 2, 3}, {1, 2, 3}, 0.5);
    REQUIRE(s.statistic == 0.0);
    REQUIRE(s.p_value == 1.0);
    REQUIRE(rs::ks_p_count(3, 3, 0) == 1.0);
    REQUIRE(rs::ks_p_walk(3, 3, 0) == 1.0);
    REQUIRE(rs::ks_p_walk(3, 3, -1) == 1.0);
    // n = m = 1, d = 1: both paths leave |i - j| < 1 at once: p = 1.
    REQUIRE(rs::ks_p_count(1, 1, 1) == 1.0);
    // n = 2, m = 1, d = 2 (out when |i - 2j| >= 2): aab passes (2, 0), baa passes (0, 1), aba stays in: p = 2/3.
    REQUIRE(near(rs::ks_p_count(2, 1, 2), 2.0 / 3.0, 1e-15));
    REQUIRE(near(rs::ks_p_walk(2, 1, 2), 2.0 / 3.0, 1e-15));
    REQUIRE(code_of([] { rs::ks({}, {1}, 0.05); }) == "E_INPUT:a");
    REQUIRE(code_of([] { rs::ks({1}, {}, 0.05); }) == "E_INPUT:a");
    REQUIRE(code_of([] { rs::ks({1}, {2}, 0.0); }) == "E_DOMAIN:level");
    REQUIRE(code_of([] { rs::ks({1}, {2}, 1.0); }) == "E_DOMAIN:level");
}

TEST_CASE("w3u ks exact count and the 128-bit overflow fallback against closed forms", "[research][w3u]") {
    // d = n m (complete separation): p = 2 / C(n + m, n), from log-gamma.
    const auto extreme = [](double n, double m) {
        return 2.0 * std::exp(std::lgamma(n + 1.0) + std::lgamma(m + 1.0) - std::lgamma(n + m + 1.0));
    };
    // C(120, 60) ~ 9.7e34 fits 128 bits: the exact count path.
    REQUIRE(std::fabs(rs::ks_p_count(60, 60, 3600) / extreme(60, 60) - 1) < 1e-9);
    // C(140, 70) ~ 9.4e40 does not: the walk fallback, which keeps the tiny tail's relative accuracy.
    REQUIRE(std::fabs(rs::ks_p_count(70, 70, 4900) / extreme(70, 70) - 1) < 1e-9);
    REQUIRE(std::fabs(rs::ks_p_walk(70, 70, 4900) / extreme(70, 70) - 1) < 1e-9);
    // Unequal sizes: C(100, 30) ~ 2.9e25 exact path.
    REQUIRE(std::fabs(rs::ks_p_count(30, 70, 2100) / extreme(30, 70) - 1) < 1e-9);
    // Monotone in d through the fallback.
    double last = 1.0;
    for (long long d = 70; d <= 4900; d += 70) {
        const double p = rs::ks_p_count(70, 70, d);
        REQUIRE(p <= last);
        REQUIRE(p > 0.0);
        last = p;
    }
}

TEST_CASE("w3u fsum exact rounding cases", "[research][w3u]") {
    REQUIRE(rs::fsum({}) == 0.0);
    REQUIRE(rs::fsum({1e16, 1.0, 1.0}) == 10000000000000002.0);
    REQUIRE(rs::fsum({1.0, 1e-16, 1e-16}) == 1.0000000000000002);
    // Half an ulp plus a hair rounds up (the final correction step).
    REQUIRE(rs::fsum({1.0, 1.1102230246251565e-16, 1e-30}) == 1.0000000000000002);
    REQUIRE(rs::fsum({1.0, -1.1102230246251565e-16, -1e-30}) == 0.99999999999999989);
    REQUIRE(rs::fsum({-3.0, 1.0, 2.5}) == 0.5);
}
