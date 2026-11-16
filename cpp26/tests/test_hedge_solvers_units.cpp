// Unit tests for hedge solver boundaries the goldens leave open (j2 unit-test lane). Every expected value is
// derived by hand in the comment next to it; none is copied from the program's output.
// No namespace-scope static objects (static-init order has broken ASan before).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/hedging.hpp"

using namespace quantforge;
namespace hg = quantforge::hedging;

namespace {
std::string code_of(auto&& run) {
    try {
        run();
    } catch (const Error& e) {
        return e.code();
    }
    return "ok";
}
hg::QpProblem zero_problem() {
    hg::QpProblem p;
    p.a = {{0.0, 0.0}, {0.0, 0.0}};
    p.b = {1.0, 1.0};
    p.weights = {1.0, 1.0};
    return p;
}
}  // namespace

TEST_CASE("hsu all-zero hedge matrix: selection is singular, MIN_NORM gives x = 0", "[hedging][hsu]") {
    // A = 0, ridge 0: H = A'WA = 0, every eigenvalue is exactly 0 and the largest is 0, so the relative test
    // 0 <= 1e-12 * 0 holds: no unique minimiser.
    REQUIRE(code_of([] { hg::select_instruments(zero_problem(), 1, false); }) == "E_SINGULAR");
    REQUIRE(code_of([] { hg::solve_qp(zero_problem()); }) == "E_SINGULAR");
    // MIN_NORM: the objective does not depend on x, every x minimises it, the minimum-norm one is 0, and the
    // residual is b itself.
    hg::QpProblem p = zero_problem();
    p.singular = hg::Singular::MinNorm;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(r.x == hg::Vec{0.0, 0.0});
    REQUIRE(r.residual == hg::Vec{1.0, 1.0});
    REQUIRE(r.rank == 0);
}

TEST_CASE("hsu selection accepts finite lower and upper bounds that are ordered", "[hedging][hsu]") {
    // The hedged residual is r = b + A x (spec convention). A = I, b = (1, 2), |x| <= 1, one instrument.
    // Instrument 0 alone: x0 = max(-1, -1) = -1, r = (0, 2), squared 4. Instrument 1 alone: x1 = max(-2, -1) = -1,
    // r = (1, 1), squared 2. Instrument 1 wins.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {1.0, 2.0};
    p.weights = {1.0, 1.0};
    p.lower = std::vector<hg::Bound>{-1.0, -1.0};
    p.upper = std::vector<hg::Bound>{1.0, 1.0};
    const hg::SelectResult r = hg::select_instruments(p, 1, false);
    REQUIRE(r.selected == std::vector<long long>{1});
    REQUIRE(r.x == hg::Vec{0.0, -1.0});
    REQUIRE(r.residual == hg::Vec{1.0, 1.0});
    // A lower bound above its upper bound is still refused.
    p.lower = std::vector<hg::Bound>{-1.0, 0.0};
    p.upper = std::vector<hg::Bound>{1.0, -0.5};
    REQUIRE(code_of([&] { hg::select_instruments(p, 1, false); }) == "E_DOMAIN");
}

TEST_CASE("hsu residual report: a zero residual contributes +0, not -0", "[hedging][hsu]") {
    // r = b + A x with A = (1, 0)', b = (1, 1), x = -1: residual (0, 1). S = [[2, -1], [-1, 2]] (positive definite).
    // S r = (-1, 2); contributions r_i (S r)_i = (0 * -1, 2) = (-0.0 normalised to +0.0, 2).
    // b'Sb = 2 - 2 + 2 = 2, r'Sr = 2, effectiveness 1 - 2/2 = 0.
    const hg::ResidualReport r = hg::residual_report({{1.0}, {0.0}}, {1.0, 1.0}, {-1.0}, {{2.0, -1.0}, {-1.0, 2.0}});
    REQUIRE(r.residual == hg::Vec{0.0, 1.0});
    REQUIRE(r.contributions == hg::Vec{0.0, 2.0});
    REQUIRE_FALSE(std::signbit(r.contributions[0]));
    REQUIRE(r.variance_before == 2.0);
    REQUIRE(r.variance_after == 2.0);
    REQUIRE(r.effectiveness == 0.0);
}

TEST_CASE("hsu option strike exactly 0 is refused", "[hedging][hsu]") {
    const hg::Market m{100.0, 0.0, 0.0, 0.2};
    const auto with_strike = [](double k) {
        hg::Position p;
        p.instrument = hg::Instrument::Call;
        p.strike = k;
        p.expiry_years = 1.0;
        p.quantity = 1.0;
        return p;
    };
    hg::Position under;
    under.quantity = 1.0;
    REQUIRE(code_of([&] { hg::neutralise(m, {with_strike(0.0)}, {under}, {hg::Greek::Delta}); }) == "E_DOMAIN");
    REQUIRE(code_of([&] { hg::neutralise(m, {with_strike(100.0)}, {under}, {hg::Greek::Delta}); }) == "ok");
}

TEST_CASE("hsu near-singular hedge judged on the scaled form against the largest scaled eigenvalue", "[hedging][hsu]") {
    // A = [[1, 1], [0, e]]: H = A'A = [[1, 1], [1, 1 + e^2]]. Jacobi-scaled, H is a correlation matrix with
    // rho = 1 / sqrt(1 + e^2) ~ 1 - e^2 / 2, eigenvalues 1 - rho ~ e^2 / 2 and 1 + rho ~ 2. The reduced form is all
    // of it (no equalities), so the test is e^2 / 2 > 1e-12 * 2.
    const auto solve_with = [](double e2) {
        hg::QpProblem p;
        p.a = {{1.0, 1.0}, {0.0, std::sqrt(e2)}};
        p.b = {1.0, 1.0};
        p.weights = {1.0, 1.0};
        return code_of([&] { hg::solve_qp(p); });
    };
    REQUIRE(solve_with(2e-12) == "E_SINGULAR");  // smallest 1e-12 < 2e-12 (and > 5e-13: the factor matters)
    REQUIRE(solve_with(2e-11) == "ok");          // smallest 1e-11 > 2e-12
}

TEST_CASE("hsu margin limit: tolerance is relative to the limit, small and large limits", "[hedging][hsu]") {
    // One instrument, A = 1, b = -1.1e-6: the free minimiser of (b + x)^2 is x = 1.1e-6, margin |x| = 1.1e-6 above
    // the limit 1e-6 by 1e-7, far beyond any 1e-12 relative tolerance, so the limit binds: x = 1e-6.
    hg::QpProblem p;
    p.a = {{1.0}};
    p.b = {-1.1e-6};
    p.weights = {1.0};
    p.margin_rates = hg::Vec{1.0};
    p.margin_limit = 1e-6;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0] - 1e-6) <= 1e-15);
    // k = n: the equality fixes x = 1000 + 1e-7 against limit 1000. The I-46 tolerance 1e-9 * max(1, 1000) = 1e-6
    // covers the 1e-7 excess, so it is feasible and x is the fixed point.
    hg::QpProblem f;
    f.a = {{1.0}};
    f.b = {0.0};
    f.weights = {1.0};
    f.eq_matrix = quantforge::Matrix{{1.0}};
    f.eq_rhs = hg::Vec{1000.0000001};
    f.margin_rates = hg::Vec{1.0};
    f.margin_limit = 1000.0;
    const hg::QpResult rf = hg::solve_qp(f);
    REQUIRE(std::fabs(rf.x[0] - 1000.0000001) <= 1e-9);
    // An excess of 1e-5 is beyond the tolerance.
    f.eq_rhs = hg::Vec{1000.00001};
    REQUIRE(code_of([&] { hg::solve_qp(f); }) == "E_INFEASIBLE");
}

TEST_CASE("hsu integer ties: the smallest total lots wins over the lexicographically smaller", "[hedging][hsu]") {
    // One instrument, lot 1, A = 1, b = 0.5: (0.5 + n)^2 is 0.25 at n = 0 and at n = -1 (an exact tie in binary).
    // I-7: smallest sum |n| first, so n = 0 (sum 0) beats n = -1 (sum 1) although (-1) < (0) lexicographically.
    hg::IntegerProblem p;
    p.a = {{1.0}};
    p.b = {0.5};
    p.weights = {1.0};
    p.lot_sizes = {1.0};
    const hg::IntegerResult r = hg::solve_integer(p);
    REQUIRE(r.lots == std::vector<long long>{0});
    REQUIRE(r.objective == 0.25);
    // The mirror b = -0.5: n = 0 and n = 1 tie; n = 0 is both lighter and lexicographically smaller.
    p.b = {-0.5};
    REQUIRE(hg::solve_integer(p).lots == std::vector<long long>{0});
}
