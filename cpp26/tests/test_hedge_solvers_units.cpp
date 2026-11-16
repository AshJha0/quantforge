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

TEST_CASE("hsu integer ties of equal total lots go to the lexicographically smallest", "[hedging][hsu]") {
    // Two instruments, lot 1, one row A = (1, 1), b = -1, ridge 1/4: f(n) = (n0 + n1 - 1)^2 + (n0^2 + n1^2) / 4.
    // (1, 0) and (0, 1): residual 0, f = 1/4 each (exact in binary). (0, 0): f = 1. (1, 1): 1 + 1/2. Any other
    // integer point has n0 + n1 != 1 (f >= 1) or n0^2 + n1^2 >= 5 (f >= 5/4). So two candidates tie at 1/4, both of
    // total lots 1; I-7 then takes the lexicographically smaller, (0, 1), whatever order the search finds them in.
    hg::IntegerProblem p;
    p.a = {{1.0, 1.0}};
    p.b = {-1.0};
    p.weights = {1.0};
    p.ridge = 0.25;
    p.lot_sizes = {1.0, 1.0};
    const hg::IntegerResult r = hg::solve_integer(p);
    REQUIRE(r.lots == std::vector<long long>{0, 1});
    REQUIRE(r.objective == 0.25);
    // The mirror b = 1: (-1, 0) and (0, -1) tie at 1/4; (-1, 0) is the lexicographically smaller.
    p.b = {1.0};
    const hg::IntegerResult m = hg::solve_integer(p);
    REQUIRE(m.lots == std::vector<long long>{-1, 0});
    REQUIRE(m.objective == 0.25);
}

TEST_CASE("hsu orthant oracle: equalities that fix x are checked against the margin row", "[hedging][hsu]") {
    // n = 1, the equality x = 2 fixes x (k = n), margin rate 1. The margin is 1 * |2| = 2.
    // Limit 1: the orthant x >= 0 has row -x >= -1, broken at x = 2; the orthant x <= 0 excludes x = 2 by its bound.
    // No orthant is feasible: E_INFEASIBLE. Limit 3: margin 2 <= 3, x = 2 is the answer.
    hg::QpProblem p;
    p.a = {{1.0}};
    p.b = {0.0};
    p.weights = {1.0};
    p.eq_matrix = quantforge::Matrix{{1.0}};
    p.eq_rhs = hg::Vec{2.0};
    p.margin_rates = hg::Vec{1.0};
    p.margin_limit = 1.0;
    REQUIRE(code_of([&] { hg::detail::solve_qp_by_orthants(p); }) == "E_INFEASIBLE");
    REQUIRE(code_of([&] { hg::solve_qp(p); }) == "E_INFEASIBLE");
    // Limit 2 is exactly the margin: feasible (the row holds with equality).
    p.margin_limit = 2.0;
    REQUIRE(hg::detail::solve_qp_by_orthants(p).x == hg::Vec{2.0});
    p.margin_limit = 3.0;
    REQUIRE(hg::detail::solve_qp_by_orthants(p).x == hg::Vec{2.0});
    REQUIRE(hg::solve_qp(p).x == hg::Vec{2.0});
}

TEST_CASE("hsu integer ties: a lighter candidate beats a heavier lexicographically smaller one found later", "[hedging][hsu]") {
    // Two instruments, lot 1, rows (1, 1) and (1, -1), b = (0, 1), weights 1, ridge 0: with s = n0 + n1 and
    // d = n0 - n1 (same parity), f = s^2 + (d + 1)^2. f < 1 needs s = 0 and d = -1, of different parity: impossible.
    // f = 1 exactly at (0, 0) and (-1, 1) (s = 0, d = 0 or -2) and at (-1, 0) and (0, 1) (s = -1 or 1, d = -1).
    // I-7: smallest sum |n| first, so (0, 0) (sum 0) wins over (-1, 1) (sum 2), although (-1, 1) < (0, 0)
    // lexicographically, and over the two of sum 1.
    hg::IntegerProblem p;
    p.a = {{1.0, 1.0}, {1.0, -1.0}};
    p.b = {0.0, 1.0};
    p.weights = {1.0, 1.0};
    p.lot_sizes = {1.0, 1.0};
    const hg::IntegerResult r = hg::solve_integer(p);
    REQUIRE(r.lots == std::vector<long long>{0, 0});
    REQUIRE(r.objective == 1.0);
}

TEST_CASE("hsu min variance: a scaled pivot of exactly -1e-12 is indefinite, not singular", "[hedging][hsu]") {
    // Hedge block [[1, c], [c, s]] with c = 1.0002664593962909 and s = 1.000532989792191: l10 = c (l00 = 1),
    // d = s - c * c = -1.000532989792191e-12 in doubles (c * c is exact to the last bit chosen), and
    // d / s == -1e-12 exactly. The band is "scaled pivot <= -1e-12 is E_NOT_POSITIVE_DEFINITE".
    const double c = 1.0002664593962909, s = 1.000532989792191;
    REQUIRE((s - c * c) / s == -1e-12);
    const quantforge::Matrix cov{{1.0, 0.0, 0.0}, {0.0, 1.0, c}, {0.0, c, s}};
    REQUIRE(code_of([&] { hg::min_variance(cov); }) == "E_NOT_POSITIVE_DEFINITE");
}

TEST_CASE("hsu equalities that fix x at a bound of exactly 0 are feasible", "[hedging][hsu]") {
    // k = n: x = 0 is fixed by the equality and the lower bound is 0. The gap is 0 and the allowance is
    // -1e-12 * (|0| + |0|) = -0, and 0 < -0 is false: feasible, x = 0 (the boundary itself).
    hg::QpProblem p;
    p.a = {{1.0}};
    p.b = {-1.0};
    p.weights = {1.0};
    p.eq_matrix = quantforge::Matrix{{1.0}};
    p.eq_rhs = hg::Vec{0.0};
    p.lower = std::vector<hg::Bound>{0.0};
    REQUIRE(hg::solve_qp(p).x == hg::Vec{0.0});
    p.lower.reset();
    p.upper = std::vector<hg::Bound>{0.0};
    REQUIRE(hg::solve_qp(p).x == hg::Vec{0.0});
}

TEST_CASE("hsu margin with an equality: the margin row is shifted by the particular point", "[hedging][hsu]") {
    // min (x0 - 3)^2 + (x1 + 2)^2 with x0 + x1 = 1/2 and |x0| + |x1| <= 1. On the equality x1 = 1/2 - x0 and
    // f = (x0 - 3)^2 + (5/2 - x0)^2 falls until x0 = 11/4; the margin |x0| + |1/2 - x0| is 1/2 on [0, 1/2] and
    // 2 x0 - 1/2 above, so it binds at x0 = 3/4: x = (3/4, -1/4), margin 1.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {-3.0, 2.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = quantforge::Matrix{{1.0, 1.0}};
    p.eq_rhs = hg::Vec{0.5};
    p.margin_rates = hg::Vec{1.0, 1.0};
    p.margin_limit = 1.0;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0] - 0.75) <= 1e-14);
    REQUIRE(std::fabs(r.x[1] + 0.25) <= 1e-14);
    REQUIRE(std::fabs(r.margin - 1.0) <= 1e-14);
}

TEST_CASE("hsu least-margin start weights the expensive instrument, not the cheap one", "[hedging][hsu]") {
    // x0 + x1 = 1 with rates (1, 4) and limit 1: |x0| + 4 |1 - x0| <= 1 holds only at x0 = 1 (the margin is
    // 1 + 5 t at x0 = 1 + t and 1 + 3 t at x0 = 1 - t), so x = (1, 0) is the only feasible point.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {1.0, -1.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = quantforge::Matrix{{1.0, 1.0}};
    p.eq_rhs = hg::Vec{1.0};
    p.margin_rates = hg::Vec{1.0, 4.0};
    p.margin_limit = 1.0;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0] - 1.0) <= 1e-12);
    REQUIRE(std::fabs(r.x[1]) <= 1e-12);
}

TEST_CASE("hsu a margin limit of 0 is allowed and forces the rated positions to 0", "[hedging][hsu]") {
    // A = I, b = (-1, -1): unconstrained x = (1, 1). Rate (1, 0), limit 0: x0 = 0, x1 = 1, margin 0.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {-1.0, -1.0};
    p.weights = {1.0, 1.0};
    p.margin_rates = hg::Vec{1.0, 0.0};
    p.margin_limit = 0.0;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0]) <= 1e-15);
    REQUIRE(std::fabs(r.x[1] - 1.0) <= 1e-15);
    REQUIRE(r.margin <= 1e-15);
    p.margin_limit = -1e-300;
    REQUIRE(code_of([&] { hg::solve_qp(p); }) == "E_DOMAIN");
}

TEST_CASE("hsu equality rank is judged on unit rows of E D", "[hedging][hsu]") {
    // H = diag(1, 1e30): D = diag(1, 1e-15). E = I, so E D = diag(1, 1e-15); with each row scaled to unit norm it is
    // I again (singular values 1, 1): not dependent. Unscaled row norms would leave 1e-15 and a false E_SINGULAR.
    // k = n: x is fixed by the equalities, x = (2, 3).
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1e15}};
    p.b = {1.0, 1.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = quantforge::Matrix{{1.0, 0.0}, {0.0, 1.0}};
    p.eq_rhs = hg::Vec{2.0, 3.0};
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(r.x == hg::Vec{2.0, 3.0});
}

TEST_CASE("hsu integer tie tolerance is 1e-12 relative to the objective scale", "[hedging][hsu]") {
    // One instrument, lot 1, A = 1000, b = -(500 + d) with d = 1e-11: f(0) = (500 + d)^2 and f(1) = (500 - d)^2
    // differ by 2000 d = 2e-8, inside 1e-12 * 2.5e5 = 2.5e-7: a tie (I-7), so the lighter n = 0 wins although
    // n = 1 is lower by 2e-8.
    hg::IntegerProblem p;
    p.a = {{1000.0}};
    p.b = {-(500.0 + 1e-11)};
    p.weights = {1.0};
    p.lot_sizes = {1.0};
    REQUIRE(hg::solve_integer(p).lots == std::vector<long long>{0});
    // d = 1e-9: 2e-6 apart, beyond the tolerance: n = 1.
    p.b = {-(500.0 + 1e-9)};
    REQUIRE(hg::solve_integer(p).lots == std::vector<long long>{1});
}

TEST_CASE("hsu residual report symmetry is relative to the largest entry", "[hedging][hsu]") {
    const quantforge::Matrix a{{1.0}, {1.0}};
    const hg::Vec b{1.0, 0.0}, x{-0.5};
    // |1 - (1 + 1e-9)| = 1e-9 <= 1e-12 * 1e6: symmetric enough.
    REQUIRE(code_of([&] { hg::residual_report(a, b, x, {{1e6, 1.0}, {1.0 + 1e-9, 1.0}}); }) == "ok");
    REQUIRE(code_of([&] { hg::residual_report(a, b, x, {{1.0, 1.0}, {1.0 + 1e-9, 1.0}}); }) == "E_INPUT");
    // An all-zero covariance is symmetric (0 > 0 is false); it fails later, on b' S b = 0.
    REQUIRE(code_of([&] { hg::residual_report(a, b, x, {{0.0, 0.0}, {0.0, 0.0}}); }) == "E_DOMAIN");
}
