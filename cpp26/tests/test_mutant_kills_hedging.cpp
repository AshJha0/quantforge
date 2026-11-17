// Unit tests aimed at the stage I hedging mutants the goldens left alive (PR #35 mutation gate): each check pins
// one boundary of a comparison exactly, so flipping < and <= changes the answer. The exact-boundary inputs were
// found by search in IEEE double arithmetic and are noted where they are used.
// No namespace-scope static objects (static-init order has broken ASan before): fixtures are built by functions.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/credit.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/hedging.hpp"

using namespace quantforge;
namespace hg = quantforge::hedging;

namespace {

struct Caught {
    std::string code = "ok", field, message;
};

Caught catch_error(auto&& run) {
    Caught c;
    try {
        run();
    } catch (const Error& e) {
        c.code = e.code();
        c.field = e.field();
        c.message = e.what();
    }
    return c;
}

Curve flat_discount(Date as_of, double r) {
    std::vector<Pillar> p;
    for (int y = 1; y <= 12; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}

hg::TwoAssetMarket two_asset_market() { return {100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.3, 0.4}; }
hg::TwoAssetPosition exchange_option(double q1, double q2) { return {hg::TwoAssetKind::Exchange, q1, q2, 0.0, 1.0, 1.0}; }

}  // namespace

TEST_CASE("hedge credit: a hazard bumped to exactly 0 is allowed; below 0 is E_DOMAIN (R6-11.9)", "[mutants]") {
    const Date as_of = make_date(2026, 11, 6);
    // 2605 days and this survival give -ln(Q) / t == 1e-4 exactly, the bump size at recovery 0, so the downward
    // bump leaves a hazard of exactly 0.
    const HazardCurve exact{as_of, {make_date(2033, 12, 24)}, {0.9992865559921522}};
    REQUIRE(-std::log(exact.survival[0]) / (2605.0 / 365.0) == 1e-4);
    const Curve disc = flat_discount(as_of, 0.03);
    const Caught at_zero = catch_error(
        [&] { (void)hg::unit_credit_risk(as_of, disc, exact, 0.0, make_date(2031, 12, 20), 0.01); });
    CHECK(at_zero.code == "ok");
    const hg::CreditRisk r = hg::unit_credit_risk(as_of, disc, exact, 0.0, make_date(2031, 12, 20), 0.01);
    REQUIRE(r.buckets.size() == 1);
    CHECK(r.cs01 > 0.0);
    CHECK(r.buckets[0] == r.cs01);  // one section: the bucket bump is the parallel bump
    CHECK(r.jtd == 1.0 - r.pv);
    // A slightly higher survival makes the bumped hazard negative.
    const HazardCurve below{as_of, {make_date(2033, 12, 24)}, {0.99929}};
    const Caught neg = catch_error([&] { (void)hg::unit_credit_risk(as_of, disc, below, 0.0, make_date(2031, 12, 20), 0.01); });
    CHECK(neg.code == "E_DOMAIN");
    CHECK(neg.field == "hazard");
}

TEST_CASE("hedge correlation: exchange quantities of exactly 0 are E_DOMAIN in book and hedges", "[mutants]") {
    const hg::TwoAssetMarket m = two_asset_market();
    const hg::TwoAssetPosition good = exchange_option(1.0, 1.0);
    for (const auto& bad : {exchange_option(0.0, 1.0), exchange_option(1.0, 0.0), exchange_option(-1.0, 1.0)}) {
        const Caught b = catch_error([&] { hg::correlation_hedge(m, {bad}, {good}, {hg::TwoAssetTarget::Delta1}); });
        CHECK(b.code == "E_DOMAIN");
        CHECK(b.field == "book");
        const Caught h = catch_error([&] { hg::correlation_hedge(m, {good}, {bad}, {hg::TwoAssetTarget::Delta1}); });
        CHECK(h.code == "E_DOMAIN");
        CHECK(h.field == "hedges");
    }
    // A tiny positive quantity passes the check.
    CHECK(catch_error([&] { hg::correlation_hedge(m, {exchange_option(1e-300, 1.0)}, {good}, {hg::TwoAssetTarget::Delta1}); })
              .code != "E_DOMAIN");
}

TEST_CASE("hedge correlation: a spread volatility of exactly 0 is E_DOMAIN on correlation; vanillas skip it", "[mutants]") {
    hg::TwoAssetMarket flat = two_asset_market();
    flat.vol1 = flat.vol2 = 0.25;
    flat.correlation = 1.0;  // 0.0625 + 0.0625 - 2 * 0.0625 == 0 exactly
    const hg::TwoAssetPosition ex = exchange_option(1.0, 1.0);
    const Caught e = catch_error([&] { hg::correlation_hedge(flat, {ex}, {ex}, {hg::TwoAssetTarget::Delta1}); });
    CHECK(e.code == "E_DOMAIN");
    CHECK(e.field == "correlation");
    CHECK(e.message == "correlation: the spread volatility is 0");
    // Without an exchange option the zero spread volatility does not matter.
    const hg::TwoAssetPosition u1{hg::TwoAssetKind::Underlying1, 0.0, 0.0, 0.0, 0.0, 2.0};
    const hg::CorrelationHedge h = hg::correlation_hedge(flat, {u1}, {u1}, {hg::TwoAssetTarget::Delta1});
    REQUIRE(h.quantities.size() == 1);
    CHECK(h.quantities[0] == -2.0);
    CHECK(h.after[0] == 0.0);
}

TEST_CASE("hedge effectiveness: item changes summing to exactly 0 are E_DOMAIN (I-31, I-43)", "[mutants]") {
    const Caught z = catch_error([] { (void)hg::effectiveness({1.0, -1.0, 0.0}, {1.0, 2.0, 4.0}); });
    CHECK(z.code == "E_DOMAIN");
    CHECK(z.field == "item_changes");
    CHECK(z.message == "item_changes: sum to zero (I-31, I-43)");
    CHECK(catch_error([] { (void)hg::effectiveness({1.0, -1.0, 0.5}, {1.0, 2.0, 4.0}); }).code == "ok");
    CHECK(catch_error([] { (void)hg::effectiveness({1.0, 2.0}, {1.0, 2.0, 4.0}); }).code == "E_INPUT");
}

TEST_CASE("option hedge lots: half_spread 0 is allowed and costs nothing; negative is E_DOMAIN", "[mutants]") {
    const hg::Market m{100.0, 0.0, 0.0, 0.2};
    const std::vector<hg::Position> book{{hg::Instrument::Underlying, std::nullopt, std::nullopt, -237.0}};
    const hg::Position u{hg::Instrument::Underlying, std::nullopt, std::nullopt, 0.0};
    const hg::LotHedgeResult r = hg::option_hedge_lots(m, book, {{u, 100.0, 0.0}}, {hg::Greek::Delta}, 10);
    REQUIRE(r.lots.size() == 1);
    CHECK(r.lots[0] == 2);
    CHECK(r.hedge_cost == 0.0);
    CHECK(r.after.delta == -37.0);
    const Caught neg = catch_error([&] { hg::option_hedge_lots(m, book, {{u, 100.0, -0.01}}, {hg::Greek::Delta}, 10); });
    CHECK(neg.code == "E_DOMAIN");
    CHECK(neg.field == "hedges");
    CHECK(neg.message == "hedges: half_spread must be at least 0");
    CHECK(catch_error([&] { hg::option_hedge_lots(m, book, {{u, 0.0, 0.0}}, {hg::Greek::Delta}, 10); }).code == "E_DOMAIN");
    CHECK(catch_error([&] { hg::option_hedge_lots(m, book, {{u, 100.0, 0.0}}, {hg::Greek::Delta}, 0); }).field == "max_lots");
    // max_lots = 1 is the smallest valid cap (kills `max_lots < 1` -> `<= 1`): one lot is allowed, not two.
    const hg::LotHedgeResult one = hg::option_hedge_lots(m, book, {{u, 100.0, 0.0}}, {hg::Greek::Delta}, 1);
    REQUIRE(one.lots.size() == 1);
    CHECK(one.lots[0] == 1);
}

TEST_CASE("minimum variance: a hedged variance of exactly -1e-12 S_00 reads as 0 (I-44 boundary)", "[mutants]") {
    // S_00 - S_he^2 / S_hh == -1e-12 * S_00 exactly in doubles for this pair (S_hh = 1).
    const double s00 = 0.9094947017729282, she = 0.9536743164067268;
    REQUIRE(s00 - she * she == -1e-12 * s00);
    const hg::MinVarResult r = hg::min_variance({{s00, she}, {she, 1.0}});
    CHECK(r.variance_after == 0.0);
    CHECK(r.effectiveness == 1.0);
    CHECK(r.variance_before == s00);
    REQUIRE(r.hedge.size() == 1);
    CHECK(r.hedge[0] == -she);
    // One step further below is an error.
    const double further = std::nextafter(she, 2.0);
    CHECK(catch_error([&] { hg::min_variance({{s00, further}, {further, 1.0}}); }).code == "E_NOT_POSITIVE_DEFINITE");
}

TEST_CASE("sample covariance: k + 1 observations are one too few, and the message says k + 2", "[mutants]") {
    // One hedge series (k = 1): 3 observations is the least allowed; 2 is refused with the spec's wording.
    REQUIRE(hg::sample_covariance({0.1, 0.3, 0.2}, {{0.1, 0.2, 0.4}}).size() == 2);
    const Caught c = catch_error([] { hg::sample_covariance({0.1, 0.3}, {{0.1, 0.2}}); });
    CHECK(c.code == "E_INPUT");
    CHECK(c.field == "exposure_changes");
    CHECK(c.message == "exposure_changes: needs at least k + 2 observations");
}

// ---- j2 seed 7/11/54 survivors (2026-11-17). Expected values by hand; the simplex ones also from a line-by-line
// Python port of detail::simplex (orig and mutant run side by side). ----

TEST_CASE("sample covariance: a constant series has variance exactly 0 even when sum / t rounds (J-I.4)", "[mutants]") {
    // 0.1 + 0.1 + 0.1 = 0.30000000000000004 and / 3 = 0.10000000000000002, so the sum-based mean leaves deviations of
    // -1.4e-17. The constant-series rule takes the value itself as the mean (kills `v == first` -> `v != first`).
    const Matrix cov = hg::sample_covariance({0.1, 0.1, 0.1}, {{0.1, 0.2, 0.4}});
    REQUIRE(cov.size() == 2);
    CHECK(cov[0][0] == 0.0);
    CHECK(cov[0][1] == 0.0);
    CHECK(cov[1][0] == 0.0);
}

TEST_CASE("beta futures: no negative zero in contracts or contracts held (F-3)", "[mutants]") {
    // contracts = (0.997 - 1) * 100 / 10 = -0.03; std::round gives -0.0, and the + 0.0 must make it +0.0.
    const hg::BetaHedge held = hg::beta_futures(100.0, 1.0, 0.997, 10.0, 1.0, hg::Rounding::Nearest);
    CHECK(held.contracts_held == 0.0);
    CHECK_FALSE(std::signbit(held.contracts_held));
    // target -0.0, beta +0.0: (-0) - (+0) = -0, times and over positives stays -0 until the + 0.0.
    const hg::BetaHedge zero = hg::beta_futures(100.0, 0.0, -0.0, 10.0, 1.0, hg::Rounding::None);
    CHECK(zero.contracts == 0.0);
    CHECK_FALSE(std::signbit(zero.contracts));
    CHECK_FALSE(std::signbit(zero.contracts_held));
}

TEST_CASE("jacobi eigen: an off-diagonal below 1e-34 of the squared norm stops before any rotation", "[mutants]") {
    // total = 1e20 + 4e20 + 2e-16, off = 1e-16 <= 1e-34 * total: no sweep, vectors stay exactly the identity.
    // Kills `total += x / x` (total = 4) and `off <= .. && off == 0.0` (needs off == 0): both rotate by t ~ 1e-18.
    const hg::Eigen ev = hg::jacobi_eigen({{1e10, 1e-8}, {1e-8, 2e10}});
    REQUIRE(ev.values.size() == 2);
    CHECK(ev.values[0] == 1e10);
    CHECK(ev.values[1] == 2e10);
    CHECK(ev.vectors[0][0] == 1.0);
    CHECK(ev.vectors[0][1] == 0.0);
    CHECK(ev.vectors[1][0] == 0.0);
    CHECK(ev.vectors[1][1] == 1.0);
}

TEST_CASE("select: smallest eigenvalue 1e-12 against 1e-12 times the largest (about 2) is singular", "[mutants]") {
    // a = [1 1], ridge 1e-12: the scaled H has eigenvalues r / (1 + r) ~ 1e-12 and ~2. The threshold is
    // 1e-12 * 2 = 2e-12, so E_SINGULAR; `singular_threshold / largest` (5e-13) would accept it.
    hg::QpProblem prob;
    prob.a = {{1.0, 1.0}};
    prob.b = {1.0};
    prob.weights = {1.0};
    prob.ridge = 1e-12;
    const Caught got = catch_error([&] { hg::select_instruments(prob, 1, false); });
    CHECK(got.code == "E_SINGULAR");
    CHECK(got.field == "a");
}

TEST_CASE("qp: a bound broken by less than its 1e-12 relative tolerance is not made active", "[mutants]") {
    // min (x - 1)^2 with x <= 1 - 2^-46: slack -1.4e-14 against a tolerance of 1e-12 * (|rhs| + |n y|) ~ 2e-12, so
    // the unconstrained minimiser x = 1 is returned. `s < -tol || s < worst` would activate the bound (x = 1 - 2^-46).
    const double cap = 1.0 - std::ldexp(1.0, -46);
    hg::QpProblem prob;
    prob.a = {{1.0}};
    prob.b = {-1.0};
    prob.weights = {1.0};
    prob.upper = std::vector<hg::Bound>{cap};
    const hg::QpResult res = hg::solve_qp(prob);
    REQUIRE(res.x.size() == 1);
    CHECK(res.x[0] == 1.0);
}

TEST_CASE("qp: an infeasibility gap of 2e-6 on bounds near 1e6 is rounding, judged on |bound| + |x_p|", "[mutants]") {
    // x0 + x1 = 2e6 (x_p = (1e6, 1e6)), x0, x1 >= 1e6 + 1e-6. The Goldfarb-Idnani certificate gap is 2e-6 against
    // 1e-9 * (size_0 + size_1), size = max(1, |bound| + |x_p|) ~ 2e6, so 4e-3: not a certificate, the solve returns.
    // With size = max(1, |bound| - |x_p|) = 1 the threshold is 2e-9 and the mutant throws E_INFEASIBLE.
    const double lo = 1e6 + 1e-6;
    hg::QpProblem prob;
    prob.a = {{1.0, 0.0}, {0.0, 1.0}};
    prob.b = {-1e6, -1e6};
    prob.weights = {1.0, 1.0};
    prob.eq_matrix = Matrix{{1.0, 1.0}};
    prob.eq_rhs = hg::Vec{2e6};
    prob.lower = std::vector<hg::Bound>{lo, lo};
    CHECK(catch_error([&] { hg::solve_qp(prob); }).code == "ok");
}

TEST_CASE("simplex: a column entry below 1e-11 times the tableau scale is not a pivot", "[mutants]") {
    // 1e-9 z0 + 1e4 z1 = 1e4, minimise -z0. scale = 1e4, tol = 1e-7: z0's phase-one cost -1e-9 and its entry 1e-13
    // after the z1 pivot are both below tol, so phase two finds no ratio row: E_NO_CONVERGENCE (unbounded).
    // With tol = 1e-11 / scale = 1e-15 the mutant pivots on 1e-9 and returns z0 = 1e13.
    const Caught got = catch_error([] { (void)hg::detail::simplex({{1e-9, 1e4}}, {1e4}, {-1.0, 0.0}); });
    CHECK(got.code == "E_NO_CONVERGENCE");
}

TEST_CASE("simplex: a ratio tie goes to the row whose basic column is smaller (Bland)", "[mutants]") {
    // Two optimal vertices, cost 1 each; Bland's tie-break reaches (0, 2, 0, 3). Taking the later tied row
    // (`ratio <= best_ratio`) ends at (0, 0, 1, 1). Traced with a Python port of the tableau.
    const std::optional<hg::Vec> z =
        hg::detail::simplex({{2.0, 1.0, 2.0, 0.0}, {0.0, -1.0, 0.0, 1.0}, {1.0, -1.0, 0.0, 1.0}}, {2.0, 1.0, 1.0},
                            {1.0, 2.0, 2.0, -1.0});
    REQUIRE(z.has_value());
    REQUIRE(z->size() == 4);
    CHECK(std::fabs((*z)[0]) < 1e-12);
    CHECK(std::fabs((*z)[1] - 2.0) < 1e-12);
    CHECK(std::fabs((*z)[2]) < 1e-12);
    CHECK(std::fabs((*z)[3] - 3.0) < 1e-12);
}

// ---- j2 seed 58/3/99 survivors (2026-11-17, round 2). The sign-state cases (813, 740) were traced with a Python
// model of SignStates::run (exact orthant QPs, the same flip test); the others by hand, as noted. ----

namespace {

// f = |A x + b|^2 + 2e3 |x0| + 2e4 |x1| with H = A'A = [[2, 1], [1, 2]], c = A'b = (-496000.0000001, -1e6).
// The smooth minimiser is (-2666.7, 501333.3), so the sign states start at (-, +). In that orthant x0 is held at 0
// by its sign row, x1 = 495000, and the flip excess nu - 2 k0 is 1e-7 (gradient units of x'Hx/2 + c'x). The KKT
// scale is max_j |c_j + (Hx)_j| + k_j = 2e4, so the original's threshold 1e-10 * scale = 2e-6 keeps x0 = 0, while
// 1e-10 / scale = 5e-15 flips it and lands on x0 = 1e-7 / 1.5 = 6.7e-8.
hg::QpProblem tolerance_window_problem() {
    hg::QpProblem prob;
    prob.a = {{1.0, 1.0}, {1.0, 0.0}, {0.0, 1.0}};
    prob.b = {0.0, -496000.0000001, -1e6};
    prob.weights = {1.0, 1.0, 1.0};
    prob.half_spreads = hg::Vec{2e3, 2e4};
    return prob;
}

}  // namespace

TEST_CASE("costed qp: a sign-flip excess of 1e-7 is inside 1e-10 times the KKT scale (2e4), so x0 stays 0", "[mutants]") {
    // Kills `excess = 1e-10 / scale` (hedging.cpp:813).
    const hg::QpResult res = hg::solve_qp(tolerance_window_problem());
    REQUIRE(res.x.size() == 2);
    CHECK(res.x[0] == 0.0);
    CHECK(std::fabs(res.x[1] - 495000.0) < 1e-6);
}

TEST_CASE("costed qp: an unconstrained point within 1e-12 relative of the margin limit is returned as is", "[mutants]") {
    // Same problem with margin rates (0, 1) and limit 495000 - 1e-7: margin(x) = x1 ~ 495000 is within
    // 1e-12 (limit + margin) ~ 9.9e-7 of the limit, so the first solve is returned (x0 = 0). Both hedging.cpp:740
    // mutants, `1e-12 * (limit - margin)` (absorbed: the test reads margin <= limit) and `!margined_ && ...`, take
    // the binding path instead; it starts from the least-margin point 0, signs (+, +), where x0 = 6.7e-8 is interior.
    hg::QpProblem prob = tolerance_window_problem();
    prob.margin_rates = hg::Vec{0.0, 1.0};
    prob.margin_limit = 494999.9999999;
    const hg::QpResult res = hg::solve_qp(prob);
    REQUIRE(res.x.size() == 2);
    CHECK(res.x[0] == 0.0);
    CHECK(std::fabs(res.x[1] - 495000.0) < 1e-6);
}

TEST_CASE("orthant oracle: an instrument with half_spread 0 has no sign and no bound at 0", "[mutants]") {
    // min (x0 + 1)^2 + (x1 - 1)^2 + 0.5 |x1|: x = (-1, 0.75). Kills `sign[j] >= 0` (hedging.cpp:883: clamps x0 to
    // >= 0) and `hs / double(sign[j])` (hedging.cpp:886: 0 / 0 is NaN for the signless x0).
    hg::QpProblem prob;
    prob.a = {{1.0, 0.0}, {0.0, 1.0}};
    prob.b = {1.0, -1.0};
    prob.weights = {1.0, 1.0};
    prob.half_spreads = hg::Vec{0.0, 0.5};
    hg::QpResult res;
    CHECK(catch_error([&] { res = hg::detail::solve_qp_by_orthants(prob); }).code == "ok");
    REQUIRE(res.x.size() == 2);
    CHECK(std::fabs(res.x[0] + 1.0) < 1e-12);
    CHECK(std::fabs(res.x[1] - 0.75) < 1e-12);
}

TEST_CASE("orthant oracle: 21 zero half_spreads, or 21 lower bounds of exactly 0, open no sign (no E_LIMIT)", "[mutants]") {
    // The oracle enumerates at most 20 open signs. A zero half_spread is no cost term (kills `hs >= 0.0`,
    // hedging.cpp:864); a lower bound of exactly 0 fixes the sign at + (kills `*lower[j] > 0.0`, hedging.cpp:866).
    // Either mutant opens all 21 signs and throws E_LIMIT.
    const std::size_t n = 21;
    hg::QpProblem prob;
    prob.a.assign(n, hg::Vec(n, 0.0));
    for (std::size_t j = 0; j < n; ++j) prob.a[j][j] = 1.0;
    prob.b.assign(n, -1.0);
    prob.weights.assign(n, 1.0);
    prob.half_spreads = hg::Vec(n, 0.0);
    hg::QpResult free_res;
    CHECK(catch_error([&] { free_res = hg::detail::solve_qp_by_orthants(prob); }).code == "ok");
    REQUIRE(free_res.x.size() == n);
    CHECK(std::fabs(free_res.x[0] - 1.0) < 1e-12);
    // (x - 1)^2 + |x| with x >= 0: x = 0.5.
    prob.half_spreads = hg::Vec(n, 1.0);
    prob.lower = std::vector<hg::Bound>(n, 0.0);
    hg::QpResult bound_res;
    CHECK(catch_error([&] { bound_res = hg::detail::solve_qp_by_orthants(prob); }).code == "ok");
    REQUIRE(bound_res.x.size() == n);
    CHECK(std::fabs(bound_res.x[n - 1] - 0.5) < 1e-12);
}

TEST_CASE("simplex: 101 phase-one pivots are within the 50 (rows + cols) + 100 cap", "[mutants]") {
    // I z = 1 with 101 rows: Bland's rule brings in one structural column per pivot (each has phase-one reduced
    // cost -1 until it enters), so phase one takes exactly 101 pivots. Kills `50 / (rows + cols) + 100` (100).
    const std::size_t n = 101;
    Matrix a(n, hg::Vec(n, 0.0));
    for (std::size_t j = 0; j < n; ++j) a[j][j] = 1.0;
    std::optional<hg::Vec> z;
    CHECK(catch_error([&] { z = hg::detail::simplex(a, hg::Vec(n, 1.0), hg::Vec(n, 0.0)); }).code == "ok");
    REQUIRE(z.has_value());
    REQUIRE(z->size() == n);
    CHECK((*z)[0] == 1.0);
    CHECK((*z)[n - 1] == 1.0);
}

TEST_CASE("integer solve: a tie found second is kept, within 1e-9 (distance + scale) of the radius", "[mutants]") {
    // f(n) = (n + 0.5)^2 + 9: n = -1 and n = 0 tie at 9.25. The search visits -1 first; the radius then stays
    // 0.25 + 1e-9 * (0.25 + 9), so 0 is found too and wins the tie on sum |n| (I-7). With
    // `1e-9 * (distance - scale)` the radius drops to 0.25 - 8.75e-9 and only -1 is found (hedging.cpp:1098).
    hg::IntegerProblem prob;
    prob.a = {{1.0}, {0.0}};
    prob.b = {0.5, 3.0};
    prob.weights = {1.0, 1.0};
    prob.lot_sizes = {1.0};
    const hg::IntegerResult res = hg::solve_integer(prob);
    REQUIRE(res.lots.size() == 1);
    CHECK(res.lots[0] == 0);
    CHECK(res.objective == 9.25);
}

TEST_CASE("integer solve: a relaxed lot count of exactly 2^52 is allowed (I-49)", "[mutants]") {
    // Kills `fabs(v) >= 2^52` (hedging.cpp:1143). min (n - 2^52)^2: the relaxed and integer answers are 2^52.
    const double big = 4503599627370496.0;
    hg::IntegerProblem prob;
    prob.a = {{1.0}};
    prob.b = {-big};
    prob.weights = {1.0};
    prob.lot_sizes = {1.0};
    hg::IntegerResult res;
    CHECK(catch_error([&] { res = hg::solve_integer(prob); }).code == "ok");
    REQUIRE(res.lots.size() == 1);
    CHECK(res.lots[0] == 4503599627370496LL);
    CHECK(res.objective == 0.0);
}

TEST_CASE("sample covariance: deviations from an inexact mean near 1e8 give variance 7/3, not 3.82", "[mutants]") {
    // Kills `(x + mean_i) * (y - mean_j)` (hedging.cpp:1213): the extra 2 mean sum(x - mean) term is 0 only in exact
    // arithmetic; with the mean of (1e8, 1e8 + 1, 1e8 + 3) rounded it adds about 1.49 (Python, same IEEE operations).
    const Matrix cov = hg::sample_covariance({1e8, 1e8 + 1.0, 1e8 + 3.0}, {{0.0, 1.0, 4.0}});
    REQUIRE(cov.size() == 2);
    CHECK(std::fabs(cov[0][0] - 7.0 / 3.0) < 1e-6);
}

TEST_CASE("neutralise: spot exactly 0 is E_DOMAIN on spot", "[mutants]") {
    // Kills `m.spot < 0.0` (hedging.cpp:1320).
    const hg::Market m{0.0, 0.03, 0.0, 0.2};
    const hg::Position u{hg::Instrument::Underlying, std::nullopt, std::nullopt, 1.0};
    const Caught got = catch_error([&] { (void)hg::neutralise(m, {u}, {u}, {hg::Greek::Delta}); });
    CHECK(got.code == "E_DOMAIN");
    CHECK(got.field == "spot");
}

TEST_CASE("select: upper bounds without lower bounds (the pair check reads only common indices)", "[mutants]") {
    // Kills `j <= lower.size() && j < upper.size()` (hedging.cpp:1481): with no lower vector it reads lower[0] of an
    // empty vector (a null dereference). min (x0 - 1)^2 + (x1 - 2)^2 with one instrument: x1 = 2 is chosen.
    hg::QpProblem prob;
    prob.a = {{1.0, 0.0}, {0.0, 1.0}};
    prob.b = {-1.0, -2.0};
    prob.weights = {1.0, 1.0};
    prob.upper = std::vector<hg::Bound>{std::nullopt, 5.0};
    hg::SelectResult res;
    CHECK(catch_error([&] { res = hg::select_instruments(prob, 1, false); }).code == "ok");
    REQUIRE(res.selected.size() == 1);
    CHECK(res.selected[0] == 1);
}

// ---- j2 full-run batch 1 survivors (2026-11-17, round 3). Values by hand unless noted; the 288 case was traced
// step by step in Python (same IEEE operations as DualActiveSet for this diagonal 2 x 2 case). ----

TEST_CASE("qp: with Z = I an active upper bound is returned exactly (0.1, not 2 - 1.9)", "[mutants]") {
    // min (x - 2)^2 with x <= 0.1: the dual step gives y = 2 + 1.9 * (-1) = 0.10000000000000009; Z = I, so the
    // active bound is written back exactly. Kills `if (r != n)` (hedging.cpp:497), which keeps the rounded y.
    hg::QpProblem prob;
    prob.a = {{1.0}};
    prob.b = {-2.0};
    prob.weights = {1.0};
    prob.upper = std::vector<hg::Bound>{0.1};
    const hg::QpResult res = hg::solve_qp(prob);
    REQUIRE(res.x.size() == 1);
    CHECK(res.x[0] == 0.1);
}

TEST_CASE("orthant oracle: equalities that fix x within 1e-12 relative of the margin limit are feasible", "[mutants]") {
    // x = 1 fixed by x = 1, margin |x| <= 1 - 1e-12. In the + orthant the margin row gives lhs - rhs = -1e-12
    // against -1e-12 * scale, scale = |rhs| + |x| ~ 2: feasible, x = 1. Kills `< -1e-12 / scale` (hedging.cpp:467:
    // -5e-13), which makes both orthants infeasible (the - orthant breaks x <= 0) and throws E_INFEASIBLE.
    hg::QpProblem prob;
    prob.a = {{1.0}};
    prob.b = {-1.0};
    prob.weights = {1.0};
    prob.eq_matrix = Matrix{{1.0}};
    prob.eq_rhs = hg::Vec{1.0};
    prob.margin_rates = hg::Vec{1.0};
    prob.margin_limit = 1.0 - 1e-12;
    hg::QpResult res;
    CHECK(catch_error([&] { res = hg::detail::solve_qp_by_orthants(prob); }).code == "ok");
    REQUIRE(res.x.size() == 1);
    CHECK(std::fabs(res.x[0] - 1.0) < 1e-12);
}

TEST_CASE("simplex: a phase-one residual of exactly 1e-9 times the scale is still feasible", "[mutants]") {
    // z = 0 and z = 1e-9: phase one ends with artificial sum exactly 1e-9 (one pivot on row 0), scale = 1, and the
    // test is `> 1e-9 * scale`: phase two returns z = 0. Kills `>= 1e-9 * scale` (hedging.cpp:640: nullopt).
    const std::optional<hg::Vec> z = hg::detail::simplex({{1.0}, {1.0}}, {0.0, 1e-9}, {1.0});
    REQUIRE(z.has_value());
    REQUIRE(z->size() == 1);
    CHECK((*z)[0] == 0.0);
}

TEST_CASE("costed qp: a margin row almost parallel to an active bound still takes its primal step", "[mutants]") {
    // H = 1e10 I, smooth minimiser (0, 2), x0 >= 1, margin |x0| + 1e-6 |x1| <= 1 + 1e-6. With x0 >= 1 active the
    // margin row's d = J'n is (-1e-5, 1e-11): d2 = 1e-22, dall = 1e-10. The original's 1e-24 * dall = 1e-34 takes
    // the primal step to x = (1, 1); `d2 > 1e-24 / dall` (hedging.cpp:288, threshold 1e-14) judges the row
    // dependent, finds no certificate (gap -1e-6), skips it as implied and returns (1, 2), above the limit.
    hg::QpProblem prob;
    prob.a = {{1e5, 0.0}, {0.0, 1e5}};
    prob.b = {0.0, -2e5};
    prob.weights = {1.0, 1.0};
    prob.lower = std::vector<hg::Bound>{1.0, std::nullopt};
    prob.margin_rates = hg::Vec{1.0, 1e-6};
    prob.margin_limit = 1.0 + 1e-6;
    const hg::QpResult res = hg::solve_qp(prob);
    REQUIRE(res.x.size() == 2);
    CHECK(std::fabs(res.x[0] - 1.0) < 1e-9);
    CHECK(std::fabs(res.x[1] - 1.0) < 1e-6);
    CHECK(res.margin <= 1.0 + 1e-6 + 1e-12);
}

TEST_CASE("minimum variance: an all-zero covariance is E_DOMAIN on the position, not E_INPUT (symmetry 0 > 0)", "[mutants]") {
    // biggest = 0, so the symmetry test is 0 > 0 (false). Kills `>= singular_threshold * biggest`
    // (hedging.cpp:1229), for which 0 >= 0 throws E_INPUT "not symmetric".
    const Caught got = catch_error([] { (void)hg::min_variance({{0.0, 0.0}, {0.0, 0.0}}); });
    CHECK(got.code == "E_DOMAIN");
    CHECK(got.field == "covariance");
}

TEST_CASE("minimum variance: a hedge variance of 1e-7 is judged on d / S_jj = 1, not d * S_jj", "[mutants]") {
    // cov = diag(1, 1e-7): the scaled pivot is 1 (well conditioned), hedge 0. Kills `d * sjj < singular_threshold`
    // (hedging.cpp:1242: 1e-14 < 1e-12 throws E_SINGULAR).
    hg::MinVarResult res;
    CHECK(catch_error([&] { res = hg::min_variance({{1.0, 0.0}, {0.0, 1e-7}}); }).code == "ok");
    REQUIRE(res.hedge.size() == 1);
    CHECK(res.hedge[0] == 0.0);
}

TEST_CASE("neutralise: one hedge with delta 5e-12 is not singular (relative test, one singular value)", "[mutants]") {
    // A call struck at 200 on spot 100, vol 0.2, 3 months: delta ~ 5.0e-12 (d1 = -6.81). With one singular value
    // s the test is s <= 1e-12 s, false for s > 0. Kills `sv.back() <= singular_threshold / sv.front()`
    // (hedging.cpp:1341), true when s^2 <= 1e-12.
    const hg::Market m{100.0, 0.03, 0.0, 0.2};
    const hg::Position u{hg::Instrument::Underlying, std::nullopt, std::nullopt, 1.0};
    const hg::Position call{hg::Instrument::Call, 200.0, 0.25, 1.0};
    const Caught got = catch_error([&] { (void)hg::neutralise(m, {u}, {call}, {hg::Greek::Delta}); });
    CHECK(got.code == "ok");
}
