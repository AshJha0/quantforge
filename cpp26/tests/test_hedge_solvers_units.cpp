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
    // x0 + x1 = 1 with rates (1, 4) and limit 3/2: the margin is 1 + 5 t at x0 = 1 + t and 1 + 3 t at x0 = 1 - t,
    // so x0 is in [5/6, 11/10]. f = (x0 + 1)^2 + (x1 - 1)^2 = (x0 + 1)^2 + x0^2 falls towards x0 = -1/2, so
    // x = (5/6, 1/6). A start that loads the expensive instrument (x1 = 1, margin 4) would be refused.
    // (With limit 1 the only feasible point is (1, 0); both this solver and the Python one fail to find it,
    // reported separately, so that degenerate case is not pinned here.)
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {1.0, -1.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = quantforge::Matrix{{1.0, 1.0}};
    p.eq_rhs = hg::Vec{1.0};
    p.margin_rates = hg::Vec{1.0, 4.0};
    p.margin_limit = 1.5;
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0] - 5.0 / 6.0) <= 1e-12);
    REQUIRE(std::fabs(r.x[1] - 1.0 / 6.0) <= 1e-12);
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

TEST_CASE("hsu sample covariance centres each series on its own mean", "[hedging][hsu]") {
    // x = (1, 2, 4, 7), mean 3.5; y = (0, 1, 1, 2), mean 1. Deviations (-2.5, -1.5, 0.5, 3.5) and (-1, 0, 0, 1):
    // S_xx = 21 / 3 = 7, S_xy = 6 / 3 = 2, S_yy = 2 / 3 (divisor T - 1 = 3, I-8).
    const quantforge::Matrix s = hg::sample_covariance({1.0, 2.0, 4.0, 7.0}, {{0.0, 1.0, 1.0, 2.0}});
    REQUIRE(s[0][0] == 7.0);
    REQUIRE(s[0][1] == 2.0);
    REQUIRE(s[1][0] == 2.0);
    REQUIRE(s[1][1] == 2.0 / 3.0);
}

TEST_CASE("hsu min variance symmetry is relative to the largest entry; a zero hedge is +0", "[hedging][hsu]") {
    // |1 - (1 + 1e-9)| = 1e-9 <= 1e-12 * 1e6: accepted. Hedge = -S_he / S_hh = -(1 + 1e-9) (S_he from row 1).
    const hg::MinVarResult r = hg::min_variance({{1e6, 1.0}, {1.0 + 1e-9, 1.0}});
    REQUIRE(std::fabs(r.hedge[0] + (1.0 + 1e-9)) <= 1e-15);
    REQUIRE(code_of([] { hg::min_variance({{1.0, 1.0}, {1.0 + 1e-9, 1.0}}); }) == "E_INPUT");
    // Uncorrelated hedge: h = 0, reported as +0.0, not -0.0.
    const hg::MinVarResult z = hg::min_variance({{2.0, 0.0}, {0.0, 1.0}});
    REQUIRE(z.hedge[0] == 0.0);
    REQUIRE(!std::signbit(z.hedge[0]));
    REQUIRE(z.variance_after == 2.0);
}

TEST_CASE("hsu equalities that fix x at 0 meet a margin limit of exactly 0", "[hedging][hsu]") {
    // k = n, x = 0 fixed; margin 1 * |0| = 0 <= 0. The margin row check is 0 - (-0) < -1e-12 * 0: false.
    hg::QpProblem p;
    p.a = {{1.0}};
    p.b = {-1.0};
    p.weights = {1.0};
    p.eq_matrix = quantforge::Matrix{{1.0}};
    p.eq_rhs = hg::Vec{0.0};
    p.margin_rates = hg::Vec{1.0};
    p.margin_limit = 0.0;
    REQUIRE(hg::solve_qp(p).x == hg::Vec{0.0});
    REQUIRE(hg::detail::solve_qp_by_orthants(p).x == hg::Vec{0.0});
}

TEST_CASE("hsu orthant oracle: a position fixed by equal bounds is not an empty orthant", "[hedging][hsu]") {
    // A = I, b = (-1, -1), spreads 0.1 each. x0 is fixed at 0.5 by lower = upper = 0.5 (its orthant is x0 >= 0,
    // bound 0.5 <= 0.5, not empty). x1 minimises (x1 - 1)^2 + 0.1 |x1|: x1 = 1 - 0.05 = 0.95.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {-1.0, -1.0};
    p.weights = {1.0, 1.0};
    p.half_spreads = hg::Vec{0.1, 0.1};
    p.lower = std::vector<hg::Bound>{0.5, std::nullopt};
    p.upper = std::vector<hg::Bound>{0.5, std::nullopt};
    const hg::QpResult o = hg::detail::solve_qp_by_orthants(p);
    REQUIRE(o.x[0] == 0.5);
    REQUIRE(std::fabs(o.x[1] - 0.95) <= 1e-14);
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(r.x[0] == 0.5);
    REQUIRE(std::fabs(r.x[1] - 0.95) <= 1e-14);
}

TEST_CASE("hsu sign search flips a position when a tiny margin rate makes the margin bind", "[hedging][hsu]") {
    // min (x0 - 3)^2 + (x1 + 2)^2 with x0 + x1 = 1 and |x0| + 1e-8 |x1| <= 1/2. The smooth minimiser (3, -2) puts
    // x1 in the negative orthant, where x0 = 1 - x1 >= 1 breaks the margin, so x1 must flip to x1 > 0. On x1 > 0
    // the objective falls with x0 up to 3, so the margin binds: x0 + 1e-8 (1 - x0) = 1/2,
    // x0 = (1/2 - 1e-8) / (1 - 1e-8), x1 = 1 - x0.
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {-3.0, 2.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = quantforge::Matrix{{1.0, 1.0}};
    p.eq_rhs = hg::Vec{1.0};
    p.margin_rates = hg::Vec{1.0, 1e-8};
    p.margin_limit = 0.5;
    const double x0 = (0.5 - 1e-8) / (1.0 - 1e-8);
    const hg::QpResult r = hg::solve_qp(p);
    REQUIRE(std::fabs(r.x[0] - x0) <= 1e-14);
    REQUIRE(std::fabs(r.x[1] - (1.0 - x0)) <= 1e-14);
}

// ---- Degenerate but feasible problems (v0.9.0 kill-round failures and their neighbours) ----
// Each feasible set is one point, or the margin is tight at a vertex, so more constraints are active than the
// dimension allows. C++ refused the margin case with E_INFEASIBLE: Goldfarb-Idnani's certificate fired on a 1e-16
// rounding gap. Answers are worked by hand; the same cases are in the Python, Java and Rust unit tests.
namespace {
hg::QpProblem degenerate(Matrix a, hg::Vec b) {
    hg::QpProblem p;
    p.weights = hg::Vec(a.size(), 1.0);
    p.a = std::move(a);
    p.b = std::move(b);
    return p;
}
hg::QpProblem c1_problem(double x2_cap) {
    hg::QpProblem p = degenerate({{1, 0, -1}, {-1, 2, -1}, {1, 1, 2}}, {-1, -1, -3});
    p.eq_matrix = Matrix{{-1, 0, 1}, {-1, -1, 0}};
    p.eq_rhs = hg::Vec{-2, -1};
    p.lower = std::vector<hg::Bound>{1.0, 0.0, -2.0};
    p.upper = std::vector<hg::Bound>{std::nullopt, 1.0, x2_cap};
    return p;
}
hg::QpProblem margin_problem(double limit) {
    hg::QpProblem p = degenerate({{1, 0}, {0, 1}}, {0, 0});
    p.eq_matrix = Matrix{{1, 1}};
    p.eq_rhs = hg::Vec{1};
    p.margin_rates = hg::Vec{1, 4};
    p.margin_limit = limit;
    return p;
}
void require_x(const hg::QpResult& r, const hg::Vec& want) {
    REQUIRE(r.x.size() == want.size());
    for (std::size_t j = 0; j < want.size(); ++j) REQUIRE(std::fabs(r.x[j] - want[j]) <= 1e-12);
}
bool near(double got, double want, double rel = 1e-12) { return std::fabs(got - want) <= rel * std::fabs(want); }
}  // namespace

TEST_CASE("hsu degenerate: equalities and bounds leave one point", "[hedging][hsu][degenerate]") {
    // The equalities leave (t, 1 - t, t - 2); x0 >= 1, x1 >= 0, x2 <= -1 meet only at t = 1. A x + b = (1, -1, -4).
    const hg::QpResult r = hg::solve_qp(c1_problem(-1.0));
    require_x(r, {1, 0, -1});
    REQUIRE(near(r.objective, 18.0));
    REQUIRE(r.rank == 1);
    REQUIRE(code_of([] { hg::solve_qp(c1_problem(-1.000001)); }) == "E_INFEASIBLE");
}

TEST_CASE("hsu degenerate: margin tight at the only feasible point", "[hedging][hsu][degenerate]") {
    // x0 + x1 = 1 and |x0| + 4 |x1| <= 1 meet only at (1, 0).
    const hg::QpResult r = hg::solve_qp(margin_problem(1.0));
    require_x(r, {1, 0});
    REQUIRE(near(r.objective, 1.0));
    REQUIRE(near(r.margin, 1.0));
    hg::QpProblem c = margin_problem(1.0);
    c.half_spreads = hg::Vec{0.5, 0.5};
    const hg::QpResult rc = hg::solve_qp(c);
    require_x(rc, {1, 0});
    REQUIRE(near(rc.risk, 1.0));
    REQUIRE(near(rc.cost, 0.5));
    REQUIRE(near(rc.objective, 1.5));
    REQUIRE(code_of([] { hg::solve_qp(margin_problem(0.999999)); }) == "E_INFEASIBLE");
}

TEST_CASE("hsu degenerate: costed problem with two equalities and a margin", "[hedging][hsu][degenerate]") {
    // x = (t, 0, 1 + t), f(t) = (t + 4)^2 + (1 - 4t)^2 + 2 (t + 1)^2 + |t|, minimised at t = -3/38.
    hg::QpProblem p = degenerate({{-1, 1, 2}, {-2, -2, -2}, {-2, -1, 1}, {1, -1, 0}}, {2, 3, -2, 1});
    p.eq_matrix = Matrix{{-1, -1, 1}, {0, 1, 0}};
    p.eq_rhs = hg::Vec{1, 0};
    p.half_spreads = hg::Vec{1, 1, 0};
    p.margin_rates = hg::Vec{1, 2, 0};
    p.margin_limit = 1.0;
    const hg::QpResult r = hg::solve_qp(p);
    require_x(r, {-3.0 / 38, 0, 35.0 / 38});
    REQUIRE(near(r.cost, 3.0 / 38));
    REQUIRE(near(r.risk, 27151.0 / 1444, 1e-11));
    REQUIRE(near(r.objective, 27265.0 / 1444, 1e-11));
    REQUIRE(near(r.margin, 3.0 / 38));
}

TEST_CASE("hsu degenerate: an equality repeats a fixed bound; every bound fixed", "[hedging][hsu][degenerate]") {
    hg::QpProblem p = degenerate({{1, 0}, {0, 1}}, {0, 0});
    p.eq_matrix = Matrix{{1, 0}};
    p.eq_rhs = hg::Vec{1};
    p.lower = std::vector<hg::Bound>{1.0, std::nullopt};
    p.upper = std::vector<hg::Bound>{1.0, std::nullopt};
    const hg::QpResult r = hg::solve_qp(p);
    require_x(r, {1, 0});
    REQUIRE(near(r.objective, 1.0));
    hg::QpProblem f = degenerate({{1, 0}, {0, 1}}, {1, 1});
    f.lower = std::vector<hg::Bound>{0.5, -2.0};
    f.upper = std::vector<hg::Bound>{0.5, -2.0};
    const hg::QpResult rf = hg::solve_qp(f);
    REQUIRE(rf.x == hg::Vec{0.5, -2.0});
    REQUIRE(near(rf.objective, 3.25));
}

TEST_CASE("hsu degenerate: a single vertex of the box, with redundant equalities", "[hedging][hsu][degenerate]") {
    // sum x = 3 with x <= 1 is met only at (1, 1, 1); x0 = x1 is redundant there too.
    for (const bool second : {false, true}) {
        hg::QpProblem p = degenerate({{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}, {0, 0, 0});
        p.eq_matrix = second ? Matrix{{1, 1, 1}, {1, -1, 0}} : Matrix{{1, 1, 1}};
        p.eq_rhs = second ? hg::Vec{3, 0} : hg::Vec{3};
        p.upper = std::vector<hg::Bound>{1.0, 1.0, 1.0};
        const hg::QpResult r = hg::solve_qp(p);
        require_x(r, {1, 1, 1});
        REQUIRE(near(r.objective, 3.0));
    }
    hg::QpProblem bad = degenerate({{1, 0}, {0, 1}}, {0, 0});
    bad.eq_matrix = Matrix{{1, 1}};
    bad.eq_rhs = hg::Vec{2.000001};
    bad.upper = std::vector<hg::Bound>{1.0, 1.0};
    REQUIRE(code_of([&] { hg::solve_qp(bad); }) == "E_INFEASIBLE");
}

namespace {
// Exact comparison: the least-margin LP lands on vertices made of the data, as in Python's test_least_margin_points.
void require_point(const std::optional<hg::Vec>& got, const hg::Vec& want) {
    REQUIRE(got.has_value());
    REQUIRE(got->size() == want.size());
    for (std::size_t j = 0; j < want.size(); ++j) REQUIRE((*got)[j] == want[j]);
}
}  // namespace

TEST_CASE("hsu least margin: the points of python test_least_margin_points", "[hedging][hsu][least_margin]") {
    namespace d = hg::detail;
    const hg::Matrix e{{1, 1}};
    const hg::Vec rates{1, 3};
    using B = std::vector<hg::Bound>;
    // min |x0| + 3 |x1| with x0 + x1 = 3: x0 = 3 unless a bound stops it.
    require_point(d::least_margin(e, {3}, B{{}, {}}, B{{}, {}}, rates), {3, 0});
    require_point(d::least_margin(e, {3}, B{{}, {}}, B{2.0, {}}, rates), {2, 1});
    require_point(d::least_margin(e, {3}, B{{}, 1.5}, B{2.0, {}}, rates), {1.5, 1.5});
    require_point(d::least_margin(e, {-3}, B{-2.0, {}}, B{{}, {}}, rates), {-2, -1});
    // Bounds alone: the point nearest 0 in each box; no rows at all: the origin.
    require_point(d::least_margin({}, {}, B{1.0, {}, -4.0}, B{2.0, -0.5, {}}, {1, 1, 1}), {1, -0.5, 0});
    require_point(d::least_margin({}, {}, B{{}, {}}, B{{}, {}}, {1, 1}), {0, 0});
    REQUIRE_FALSE(d::least_margin(e, {3}, B{{}, {}}, B{1.0, 1.0}, rates).has_value());
}

TEST_CASE("hsu least margin: feasibility is judged at 1e-9 of the data scale", "[hedging][hsu][least_margin]") {
    namespace d = hg::detail;
    using B = std::vector<hg::Bound>;
    // 100 x = 100 + 1e-8 with 0 <= x <= 1 misses by 1e-8, inside 1e-9 x 100; by 1e-6 it is infeasible.
    const auto inside = d::least_margin({{100}}, {100 + 1e-8}, B{0.0}, B{1.0}, {1});
    REQUIRE(inside.has_value());
    REQUIRE(std::fabs((*inside)[0] - 1.0) <= 1e-9);
    REQUIRE_FALSE(d::least_margin({{100}}, {100 + 1e-6}, B{0.0}, B{1.0}, {1}).has_value());
}

TEST_CASE("hsu least margin: a repeated equality row leaves a degenerate artificial", "[hedging][hsu][least_margin]") {
    using B = std::vector<hg::Bound>;
    require_point(hg::detail::least_margin({{1, 1}, {1, 1}}, {3, 3}, B{}, B{}, {1, 3}), {3, 0});
    require_point(hg::detail::least_margin({{1, 1}, {2, 2}}, {-3, -6}, B{}, B{}, {3, 1}), {0, -3});
}
