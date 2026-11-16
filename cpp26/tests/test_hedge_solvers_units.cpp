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
