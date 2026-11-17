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
