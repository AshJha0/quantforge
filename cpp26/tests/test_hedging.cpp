// Stage I wave 1 property and unit tests: the property tests of 08-hedging/hedge-solvers.md ("Property tests"),
// on this file's own random problems, plus the check order, ties, rounding and limit cases.
// No namespace-scope static objects (static-init order has broken ASan before): fixtures are built by functions.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <random>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/hedging.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/linalg.hpp"
#include "quantforge/core/stats.hpp"

using namespace quantforge;
namespace hg = quantforge::hedging;

namespace {

using Vec = std::vector<double>;

std::string i_code(const std::string& case_json) {
    const auto r = cli::run_case(case_json);
    if (r.ok) return "ok";
    const auto at = r.json.find("\"code\":\"");
    return r.json.substr(at + 8, r.json.find('"', at + 8) - at - 8);
}

std::string i_case(const std::string& op, const std::string& inputs) {
    return R"({"schema_version":"1.0","case_id":"t","operation":")" + op + R"(","inputs":)" + inputs + "}";
}

std::string i_error(const auto& run) {
    try {
        run();
    } catch (const Error& e) {
        return e.code();
    }
    return "ok";
}

Matrix i_random(std::mt19937_64& rng, std::size_t rows, std::size_t cols, double lo = -1.0, double hi = 1.0) {
    std::uniform_real_distribution<double> u(lo, hi);
    Matrix m(rows, Vec(cols));
    for (auto& row : m)
        for (double& v : row) v = u(rng);
    return m;
}

Vec i_vector(std::mt19937_64& rng, std::size_t n, double lo = -1.0, double hi = 1.0) { return i_random(rng, 1, n, lo, hi)[0]; }

double i_objective(const Matrix& a, const Vec& b, const Vec& w, double ridge, const Vec& x) {
    double f = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        double r = b[i];
        for (std::size_t j = 0; j < x.size(); ++j) r += a[i][j] * x[j];
        f += w[i] * r * r;
    }
    for (const double v : x) f += ridge * v * v;
    return f;
}

// g = 2 (H x + A^T W b), the gradient of f.
Vec i_gradient(const Matrix& a, const Vec& b, const Vec& w, double ridge, const Vec& x) {
    Vec g(x.size(), 0.0);
    for (std::size_t i = 0; i < a.size(); ++i) {
        double r = b[i];
        for (std::size_t j = 0; j < x.size(); ++j) r += a[i][j] * x[j];
        for (std::size_t j = 0; j < x.size(); ++j) g[j] += 2.0 * w[i] * a[i][j] * r;
    }
    for (std::size_t j = 0; j < x.size(); ++j) g[j] += 2.0 * ridge * x[j];
    return g;
}

// A random bounded, equality-constrained problem that is feasible by construction.
hg::QpProblem i_qp(std::mt19937_64& rng, std::size_t m, std::size_t n, std::size_t k, bool bounds) {
    hg::QpProblem p;
    p.a = i_random(rng, m, n);
    p.b = i_vector(rng, m, -3.0, 3.0);
    p.weights = i_vector(rng, m, 0.5, 2.0);
    p.ridge = 0.01;
    const Vec inside = i_vector(rng, n, -0.5, 0.5);
    if (bounds) {
        p.lower = std::vector<hg::Bound>(n);
        p.upper = std::vector<hg::Bound>(n);
        for (std::size_t j = 0; j < n; ++j) {
            if (j % 3 != 2) (*p.lower)[j] = inside[j] - 0.3;
            if (j % 3 != 1) (*p.upper)[j] = inside[j] + 0.3;
        }
    }
    if (k > 0) {
        p.eq_matrix = i_random(rng, k, n);
        p.eq_rhs = Vec(k, 0.0);
        for (std::size_t i = 0; i < k; ++i)
            for (std::size_t j = 0; j < n; ++j) (*p.eq_rhs)[i] += (*p.eq_matrix)[i][j] * inside[j];
    }
    return p;
}

}  // namespace

TEST_CASE("I1 Jacobi eigen-decomposition reconstructs the matrix with orthonormal vectors") {
    std::mt19937_64 rng(11);
    const Matrix r = i_random(rng, 6, 6);
    Matrix s(6, Vec(6, 0.0));
    for (std::size_t i = 0; i < 6; ++i)
        for (std::size_t j = 0; j < 6; ++j)
            for (std::size_t k = 0; k < 6; ++k) s[i][j] += r[i][k] * r[j][k];
    const hg::Eigen e = hg::jacobi_eigen(s);
    REQUIRE(std::ranges::is_sorted(e.values));
    for (std::size_t i = 0; i < 6; ++i)
        for (std::size_t j = 0; j < 6; ++j) {
            double back = 0.0, gram = 0.0;
            for (std::size_t k = 0; k < 6; ++k) {
                back += e.vectors[i][k] * e.values[k] * e.vectors[j][k];
                gram += e.vectors[k][i] * e.vectors[k][j];
            }
            CHECK(std::fabs(back - s[i][j]) < 1e-12);
            CHECK(std::fabs(gram - (i == j ? 1.0 : 0.0)) < 1e-12);
        }
}

TEST_CASE("I1 QP: KKT residual below 1e-8 of the gradient scale; bounds and equalities hold") {
    std::mt19937_64 rng(20261111);
    int active_seen = 0;
    for (int trial = 0; trial < 60; ++trial) {
        const std::size_t n = 2 + std::size_t(trial % 6), k = std::size_t(trial % 3) % n, m = n + 2;
        const hg::QpProblem p = i_qp(rng, m, n, k, trial % 4 != 0);
        const hg::QpResult r = hg::solve_qp(p);
        const Vec g = i_gradient(p.a, p.b, p.weights, p.ridge, r.x);
        double scale = 1.0;
        for (const double v : g) scale = std::max(scale, std::fabs(v));
        // Free coordinates: not at a bound.
        std::vector<char> at_lower(n, 0), at_upper(n, 0);
        for (std::size_t j = 0; j < n; ++j) {
            if (p.lower && (*p.lower)[j]) {
                REQUIRE(r.x[j] >= *(*p.lower)[j] - 1e-12);
                at_lower[j] = std::fabs(r.x[j] - *(*p.lower)[j]) < 1e-10;
            }
            if (p.upper && (*p.upper)[j]) {
                REQUIRE(r.x[j] <= *(*p.upper)[j] + 1e-12);
                at_upper[j] = std::fabs(r.x[j] - *(*p.upper)[j]) < 1e-10;
            }
            active_seen += at_lower[j] + at_upper[j];
        }
        for (std::size_t i = 0; i < k; ++i) {
            double lhs = 0.0;
            for (std::size_t j = 0; j < n; ++j) lhs += (*p.eq_matrix)[i][j] * r.x[j];
            REQUIRE(std::fabs(lhs - (*p.eq_rhs)[i]) < 1e-12);
        }
        // Equality multipliers by least squares on the free coordinates: (E_F E_F^T) lambda = -E_F g_F.
        Vec lambda(k, 0.0);
        if (k > 0) {
            Matrix m2(k, Vec(k, 0.0));
            Vec rhs(k, 0.0);
            for (std::size_t i = 0; i < k; ++i)
                for (std::size_t j = 0; j < n; ++j) {
                    if (at_lower[j] || at_upper[j]) continue;
                    rhs[i] -= (*p.eq_matrix)[i][j] * g[j];
                    for (std::size_t l = 0; l < k; ++l) m2[i][l] += (*p.eq_matrix)[i][j] * (*p.eq_matrix)[l][j];
                }
            lambda = lu_solve(m2, rhs);
        }
        for (std::size_t j = 0; j < n; ++j) {
            double stat = g[j];
            for (std::size_t i = 0; i < k; ++i) stat += (*p.eq_matrix)[i][j] * lambda[i];
            if (at_lower[j]) CHECK(stat >= -1e-8 * scale);       // mu_L = stat >= 0
            else if (at_upper[j]) CHECK(stat <= 1e-8 * scale);   // mu_U = -stat >= 0
            else CHECK(std::fabs(stat) <= 1e-8 * scale);
        }
        CHECK(r.rank == (long long)(n - k));
    }
    CHECK(active_seen > 20);  // the trials exercise the active set, not only interior minimisers
}

TEST_CASE("I1 QP: the minimum is not above any feasible perturbation") {
    std::mt19937_64 rng(5);
    for (int trial = 0; trial < 20; ++trial) {
        const hg::QpProblem p = i_qp(rng, 7, 4, 0, true);
        const hg::QpResult r = hg::solve_qp(p);
        std::uniform_real_distribution<double> step(-0.05, 0.05);
        for (int probe = 0; probe < 50; ++probe) {
            Vec y = r.x;
            for (std::size_t j = 0; j < y.size(); ++j) {
                y[j] += step(rng);
                if ((*p.lower)[j]) y[j] = std::max(y[j], *(*p.lower)[j]);
                if ((*p.upper)[j]) y[j] = std::min(y[j], *(*p.upper)[j]);
            }
            CHECK(i_objective(p.a, p.b, p.weights, p.ridge, y) >= r.objective - 1e-12 * (1.0 + r.objective));
        }
    }
}

TEST_CASE("I1 QP: MIN_NORM equals the unique solution when rank = n - k") {
    std::mt19937_64 rng(77);
    for (int trial = 0; trial < 20; ++trial) {
        const std::size_t n = 3 + std::size_t(trial % 4), k = std::size_t(trial % 2);
        hg::QpProblem p = i_qp(rng, n + 3, n, k, false);
        p.ridge = 0.0;
        const hg::QpResult regular = hg::solve_qp(p);
        p.singular = hg::Singular::MinNorm;
        const hg::QpResult min_norm = hg::solve_qp(p);
        REQUIRE(min_norm.rank == (long long)(n - k));
        for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(min_norm.x[j] - regular.x[j]) < 1e-10);
    }
}

TEST_CASE("I1 QP: MIN_NORM splits duplicate instruments evenly and keeps a zero column at zero") {
    hg::QpProblem p;
    p.a = {{1.0, 1.0, 0.0}, {0.5, 0.5, 0.0}, {0.2, 0.2, 0.0}};
    p.b = {-2.0, 0.5, 1.0};
    p.weights = {1.0, 1.0, 1.0};
    REQUIRE(i_error([&] { hg::solve_qp(p); }) == "E_SINGULAR");
    p.singular = hg::Singular::MinNorm;
    const hg::QpResult r = hg::solve_qp(p);
    CHECK(r.rank == 1);
    CHECK(std::fabs(r.x[0] - r.x[1]) < 1e-14);
    CHECK(r.x[2] == 0.0);
    // The pair carries the one-instrument least-squares hedge: 2 x0 = -(a.b)/(a.a) for a = (1, 0.5, 0.2).
    CHECK(std::fabs(2.0 * r.x[0] - (2.0 - 0.25 - 0.2) / 1.29) < 1e-13);
}

TEST_CASE("I1 QP: check order and E_INFEASIBLE (I-14)") {
    hg::QpProblem p;
    p.a = {{1.0, 0.0}, {0.0, 1.0}};
    p.b = {-1.0, -1.0};
    p.weights = {1.0, 1.0};
    p.eq_matrix = Matrix{{1.0, 1.0}};
    p.eq_rhs = Vec{3.0};
    p.upper = std::vector<hg::Bound>{1.0, 1.0};
    CHECK(i_error([&] { hg::solve_qp(p); }) == "E_INFEASIBLE");  // budget above the sum of upper bounds
    p.eq_rhs = Vec{2.0};
    CHECK(std::fabs(hg::solve_qp(p).x[0] - 1.0) < 1e-12);         // exactly at the corner: feasible
    p.eq_matrix = Matrix{{1.0, 1.0}, {2.0, 2.0}};
    p.eq_rhs = Vec{3.0, 6.0};
    CHECK(i_error([&] { hg::solve_qp(p); }) == "E_SINGULAR");    // singular before infeasible
    p.eq_matrix = Matrix{{1.0, 0.0}, {0.0, 1.0}};
    p.eq_rhs = Vec{0.5, 2.0};
    CHECK(i_error([&] { hg::solve_qp(p); }) == "E_INFEASIBLE");  // k = n, fixed point outside the box
    p.weights = {0.0, 1.0};
    CHECK(i_error([&] { hg::solve_qp(p); }) == "E_DOMAIN");
    p.singular = hg::Singular::MinNorm;
    CHECK(i_error([&] { hg::solve_qp(p); }) == "E_INPUT");       // MIN_NORM with a bound, before E_DOMAIN
    // A fixed variable (lower = upper) through the dual active set.
    hg::QpProblem f;
    f.a = {{1.0, 0.3}, {0.2, 1.0}, {0.5, 0.5}};
    f.b = {-1.0, 2.0, 0.4};
    f.weights = {1.0, 1.0, 1.0};
    f.lower = std::vector<hg::Bound>{0.25, std::nullopt};
    f.upper = std::vector<hg::Bound>{0.25, std::nullopt};
    CHECK(hg::solve_qp(f).x[0] == 0.25);
}

TEST_CASE("I1 integer lots: objective >= continuous_objective and no better neighbour") {
    std::mt19937_64 rng(31);
    for (int trial = 0; trial < 40; ++trial) {
        const std::size_t n = 1 + std::size_t(trial % 4);
        hg::IntegerProblem p;
        p.a = i_random(rng, n + 2, n);
        p.b = i_vector(rng, n + 2, -20.0, 20.0);
        p.weights = i_vector(rng, n + 2, 0.5, 2.0);
        p.lot_sizes = i_vector(rng, n, 0.5, 3.0);
        if (trial % 3 == 0) {
            p.lower_lots = std::vector<std::optional<long long>>(n, -2);
            p.upper_lots = std::vector<std::optional<long long>>(n, std::nullopt);
        }
        const hg::IntegerResult r = hg::solve_integer(p);
        CHECK(r.objective >= r.continuous_objective - 1e-12 * r.objective);
        CHECK(r.rounding_cost == r.objective - r.continuous_objective);
        for (std::size_t j = 0; j < n; ++j)
            for (const long long step : {-1LL, 1LL}) {
                std::vector<long long> nb = r.lots;
                nb[j] += step;
                if (p.lower_lots && (*p.lower_lots)[j] && nb[j] < *(*p.lower_lots)[j]) continue;
                Vec x(n);
                for (std::size_t i = 0; i < n; ++i) x[i] = p.lot_sizes[i] * double(nb[i]);
                CHECK(i_objective(p.a, p.b, p.weights, p.ridge, x) >= r.objective * (1.0 - 1e-12));
            }
    }
}

TEST_CASE("I1 integer lots: ties go to the smallest sum |n|, then lexicographic (I-7); E_SINGULAR (I-6)") {
    hg::IntegerProblem p;
    p.a = {{1.0}};
    p.b = {-0.5};  // f(0) = f(1) = 0.25
    p.weights = {1.0};
    p.lot_sizes = {1.0};
    CHECK(hg::solve_integer(p).lots == std::vector<long long>{0});
    p.b = {0.5};  // f(0) = f(-1)
    CHECK(hg::solve_integer(p).lots == std::vector<long long>{0});
    p.b = {-1.5};  // f(1) = f(2): smaller |n|
    CHECK(hg::solve_integer(p).lots == std::vector<long long>{1});
    // Equal sum |n|: f = (n0 + n1 + 1)^2 + (n0^2 + n1^2) / 2 is 0.5 at (-1, 0) and (0, -1), 1 at (0, 0);
    // lexicographic order picks (-1, 0).
    hg::IntegerProblem q;
    q.a = {{1.0, 1.0}};
    q.b = {1.0};
    q.weights = {1.0};
    q.ridge = 0.5;
    q.lot_sizes = {1.0, 1.0};
    const hg::IntegerResult r = hg::solve_integer(q);
    CHECK(r.lots == std::vector<long long>{-1, 0});
    CHECK(r.objective == 0.5);
    q.ridge = 0.0;
    q.b = {-1.0};
    q.lower_lots = std::vector<std::optional<long long>>{0, 0};
    q.upper_lots = std::vector<std::optional<long long>>{3, 3};
    CHECK(i_error([&] { hg::solve_integer(q); }) == "E_SINGULAR");  // even with every lot bounded
}

TEST_CASE("I1 minimum variance: effectiveness is the R^2 of OLS with intercept on the series") {
    std::mt19937_64 rng(9);
    std::normal_distribution<double> z(0.0, 0.01);
    for (int trial = 0; trial < 10; ++trial) {
        const std::size_t k = 1 + std::size_t(trial % 3), t = 30;
        Matrix h(k, Vec(t));
        Vec y(t);
        for (std::size_t o = 0; o < t; ++o) {
            y[o] = z(rng);
            for (std::size_t i = 0; i < k; ++i) {
                h[i][o] = z(rng);
                y[o] += 0.7 * double(i + 1) * h[i][o];
            }
        }
        const hg::MinVarResult r = hg::min_variance(hg::sample_covariance(y, h));
        // OLS with intercept: columns 1, h_1..h_k.
        Matrix xtx(k + 1, Vec(k + 1, 0.0));
        Vec xty(k + 1, 0.0);
        for (std::size_t o = 0; o < t; ++o) {
            Vec row{1.0};
            for (std::size_t i = 0; i < k; ++i) row.push_back(h[i][o]);
            for (std::size_t a = 0; a <= k; ++a) {
                xty[a] += row[a] * y[o];
                for (std::size_t b = 0; b <= k; ++b) xtx[a][b] += row[a] * row[b];
            }
        }
        const Vec beta = lu_solve(xtx, xty);
        double mean = 0.0, ssr = 0.0, sst = 0.0;
        for (const double v : y) mean += v / double(t);
        for (std::size_t o = 0; o < t; ++o) {
            double fit = beta[0];
            for (std::size_t i = 0; i < k; ++i) fit += beta[i + 1] * h[i][o];
            ssr += (y[o] - fit) * (y[o] - fit);
            sst += (y[o] - mean) * (y[o] - mean);
        }
        CHECK(std::fabs(r.effectiveness - (1.0 - ssr / sst)) < 1e-12);
        for (std::size_t i = 0; i < k; ++i) CHECK(std::fabs(r.hedge[i] + beta[i + 1]) < 1e-10);  // units held: -slope
    }
}

TEST_CASE("I1 minimum variance: Hull's ratio, a perfect hedge, and the error ladder") {
    const hg::MinVarResult r = hg::min_variance({{0.04, 0.018}, {0.018, 0.0225}});
    CHECK(std::fabs(r.hedge[0] + 0.6 * 0.2 / 0.15) < 1e-15);  // -rho sigma_S / sigma_F
    const hg::MinVarResult perfect = hg::min_variance({{0.04, 0.06}, {0.06, 0.09}});
    CHECK(perfect.variance_after >= 0.0);
    CHECK(perfect.effectiveness > 1.0 - 1e-14);
    CHECK(i_error([] { hg::min_variance({{0.04, 0.05}, {0.05, 0.0225}}); }) == "E_NOT_POSITIVE_DEFINITE");
    CHECK(i_error([] { hg::min_variance({{0.04, 0.0}, {0.0, 0.0}}); }) == "E_SINGULAR");
    CHECK(i_error([] { hg::min_variance({{0.0, 0.0}, {0.0, 0.01}}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::min_variance({{0.04, 0.01}}); }) == "E_INPUT");
    CHECK(i_error([] { hg::sample_covariance({1.0, 2.0}, {{1.0, 3.0}}); }) == "E_INPUT");  // T < k + 2
    CHECK(i_error([] { hg::sample_covariance({1.0, 2.0, 4.0}, {{1.0, 3.0}}); }) == "E_INPUT");
}

TEST_CASE("I1 Greeks: gamma is the spot derivative of delta; neutralised targets are zero") {
    const hg::Market m{100.0, 0.03, 0.01, 0.25};
    for (const hg::Instrument kind : {hg::Instrument::Call, hg::Instrument::Put}) {
        const hg::Position p{kind, 95.0, 0.75, 1.0};
        const double h = 1e-3;
        hg::Market up = m, down = m;
        up.spot += h;
        down.spot -= h;
        const double fd = (hg::unit_greeks(up, p).delta - hg::unit_greeks(down, p).delta) / (2.0 * h);
        CHECK(std::fabs(fd - hg::unit_greeks(m, p).gamma) < 1e-8);
    }
    const hg::Position call{hg::Instrument::Call, 95.0, 0.75, 1.0}, put{hg::Instrument::Put, 95.0, 0.75, 1.0};
    CHECK(std::fabs(hg::unit_greeks(m, call).delta - hg::unit_greeks(m, put).delta - std::exp(-0.01 * 0.75)) < 1e-15);
    const std::vector<hg::Position> book{{hg::Instrument::Call, 100.0, 0.5, -1000.0}, {hg::Instrument::Put, 90.0, 1.0, 500.0}};
    const std::vector<hg::Position> hedges{{hg::Instrument::Underlying, std::nullopt, std::nullopt, 0.0},
                                           {hg::Instrument::Call, 105.0, 0.25, 0.0},
                                           {hg::Instrument::Put, 95.0, 2.0, 0.0}};
    const hg::GreekHedge r = hg::neutralise(m, book, hedges, {hg::Greek::Vega, hg::Greek::Delta, hg::Greek::Gamma});
    CHECK(std::fabs(r.after.delta) < 1e-10 * std::fabs(r.before.vega));
    CHECK(std::fabs(r.after.gamma) < 1e-10 * std::fabs(r.before.vega));
    CHECK(std::fabs(r.after.vega) < 1e-10 * std::fabs(r.before.vega));
    CHECK(i_error([&] { hg::neutralise(m, book, {hedges[0], hedges[0]}, {hg::Greek::Delta, hg::Greek::Gamma}); }) ==
          "E_SINGULAR");
    CHECK(i_error([&] { hg::neutralise(m, book, {hedges[0]}, {hg::Greek::Delta, hg::Greek::Gamma}); }) == "E_INPUT");
    CHECK(i_error([&] { hg::neutralise({100.0, 0.0, 0.0, 0.0}, book, {hedges[0]}, {hg::Greek::Delta}); }) == "E_DOMAIN");
}

TEST_CASE("I1 beta futures: Hull's 30 contracts and half away from zero (I-10)") {
    CHECK(hg::beta_futures(5050000.0, 1.5, 0.0, 1010.0, 250.0, hg::Rounding::Nearest).contracts_held == -30.0);
    const hg::BetaHedge half = hg::beta_futures(1e6, 1.0, 0.0, 4000.0, 100.0, hg::Rounding::Nearest);
    CHECK(half.contracts == -2.5);
    CHECK(half.contracts_held == -3.0);
    CHECK(std::fabs(half.beta_after + 0.2) < 1e-15);
    CHECK(hg::beta_futures(1e6, 1.0, 1.0, 4000.0, 100.0, hg::Rounding::Nearest).contracts_held == 0.0);
    CHECK(!std::signbit(hg::beta_futures(1e6, 1.0, 1.0, 4000.0, 100.0, hg::Rounding::Nearest).contracts));
    CHECK(hg::beta_futures(1e6, 1.0, 0.0, 4000.0, 100.0, hg::Rounding::None).contracts_held == -2.5);
    CHECK(i_error([] { hg::beta_futures(1e6, 1.0, 0.0, 4000.0, 0.0, hg::Rounding::None); }) == "E_DOMAIN");
}

TEST_CASE("I1 residual report: contributions sum to variance_after") {
    std::mt19937_64 rng(3);
    for (int trial = 0; trial < 20; ++trial) {
        const std::size_t m = 2 + std::size_t(trial % 5), n = 1 + std::size_t(trial % 3);
        const Matrix f = i_random(rng, m, m);
        Matrix s(m, Vec(m, 0.0));
        for (std::size_t i = 0; i < m; ++i)
            for (std::size_t j = 0; j < m; ++j)
                for (std::size_t k = 0; k < m; ++k) s[i][j] += f[i][k] * f[j][k];
        const hg::ResidualReport r = hg::residual_report(i_random(rng, m, n), i_vector(rng, m), i_vector(rng, n), s);
        double total = 0.0;
        for (const double c : r.contributions) total += c;
        CHECK(std::fabs(total - r.variance_after) < 1e-12 * std::max(1.0, r.variance_after));
        CHECK(std::fabs(r.effectiveness - (1.0 - r.variance_after / r.variance_before)) < 1e-15);
    }
    CHECK(i_error([] { hg::residual_report({{1.0}}, {1.0}, {0.5}, {{-1.0}}); }) == "E_NOT_POSITIVE_DEFINITE");
    CHECK(i_error([] { hg::residual_report({{1.0}}, {0.0}, {0.5}, {{1.0}}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::residual_report({{1.0}}, {1.0}, {0.5, 1.0}, {{1.0}}); }) == "E_INPUT");
}

TEST_CASE("I1 CLI: null only inside bounds (I-12), limits (I-4) before the finite rule, minvar forms") {
    const std::string base = R"("a":[[1.0,0.5],[0.3,1.2],[0.2,0.1]],"b":[-1.0,0.5,0.2],"weights":[1,1,1])";
    CHECK(i_code(i_case("hedge.qp.solve", "{" + base + R"(,"lower":[null,-1.0]})")) == "ok");
    CHECK(i_code(i_case("hedge.qp.solve", "{" + base + R"(,"ridge":null})")) == "E_SCHEMA");
    CHECK(i_code(i_case("hedge.qp.solve", "{" + base + R"(,"lower":null})")) == "E_SCHEMA");
    CHECK(i_code(i_case("hedge.qp.solve", "{" + base + R"(,"singular":"PSEUDO"})")) == "E_SCHEMA");
    CHECK(i_code(i_case("hedge.integer.solve", "{" + base + R"(,"lot_sizes":[1,1],"upper_lots":[null,2]})")) == "ok");
    CHECK(i_code(i_case("hedge.integer.solve", "{" + base + R"(,"lot_sizes":[1,1],"upper_lots":[0.5,2]})")) ==
          "E_SCHEMA");
    std::string wide = R"({"a":[[)";
    for (int j = 0; j < 201; ++j) wide += j ? ",1" : "1";
    wide += R"(]],"b":["NaN"],"weights":[1]})";
    CHECK(i_code(i_case("hedge.qp.solve", wide)) == "E_LIMIT");
    CHECK(i_code(i_case("hedge.minvar.ratio", R"({})")) == "E_INPUT");
    CHECK(i_code(i_case("hedge.minvar.ratio", R"({"hedge_changes":[[0.1,0.2,0.3]]})")) == "E_INPUT");
    CHECK(i_code(i_case("hedge.minvar.ratio",
                        R"({"exposure_changes":[0.1,0.3,0.2,0.5],"hedge_changes":[[0.1,0.2,0.2,0.6]]})")) == "ok");
    const std::string greeks =
        R"({"spot":100,"rate":0.03,"dividend_yield":0.01,"volatility":0.25,"portfolio":[{"instrument":"CALL","strike":100,"expiry_years":0.5,"quantity":-10}],"targets":["DELTA"],"hedges":[{"instrument":"UNDERLYING")";
    CHECK(i_code(i_case("hedge.greeks.neutralise", greeks + "}]}")) == "ok");
    CHECK(i_code(i_case("hedge.greeks.neutralise", greeks + R"(,"strike":null}]})")) == "E_SCHEMA");
    CHECK(i_code(i_case("hedge.beta.futures",
                        R"({"portfolio_value":1e6,"portfolio_beta":1,"target_beta":0,"futures_price":4000,"multiplier":100,"rounding":"NONE"})")) ==
          "ok");
    CHECK(i_code(i_case("hedge.residual.report",
                        R"({"a":[[1.0]],"b":[1.0],"x":[-0.5],"covariance":[[1.0,0.0]]})")) == "E_INPUT");
}

// ---- wave 2: credit and correlation hedges ----

namespace {

json::Value i_outputs(const std::string& op, const std::string& inputs) {
    const auto r = cli::run_case(i_case(op, inputs));
    REQUIRE(r.ok);
    return *json::parse(r.json).value.find("outputs");
}

double i_num(const json::Value& v, std::initializer_list<std::string_view> path) {
    const json::Value* p = &v;
    for (const std::string_view k : path) p = p->find(k);
    return p->number;
}

// A five-pillar hazard curve and flat discounting, own data in the shape of credit.cds.price inputs.
std::string i_credit(const std::string& book, const std::string& hedges, const std::string& targets) {
    return R"({"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.5}]},)"
           R"("hazard":{"as_of":"2026-11-06","pillars":[{"date":"2027-12-20","survival":0.985},{"date":"2029-12-20","survival":0.95},{"date":"2031-12-20","survival":0.9},{"date":"2033-12-20","survival":0.84},{"date":"2036-12-20","survival":0.76}]},)"
           R"("recovery":0.4,"book":)" +
           book + R"(,"hedges":)" + hedges + R"(,"targets":)" + targets + "}";
}

}  // namespace

TEST_CASE("I2 credit: the book's own contract hedges it with the opposite notional; targets are zero after") {
    const json::Value o = i_outputs(
        "hedge.credit.cds",
        i_credit(R"([{"maturity":"2033-12-20","coupon":0.01,"notional":7.5e6,"side":"SELL_PROTECTION"}])",
                 R"([{"maturity":"2033-12-20","coupon":0.01}])", R"(["CS01"])"));
    CHECK(std::fabs(o.find("notionals")->items[0].number - 7.5e6) < 1e-6);
    const json::Value both = i_outputs(
        "hedge.credit.cds",
        i_credit(R"([{"maturity":"2033-12-20","coupon":0.01,"notional":1e7,"side":"BUY_PROTECTION"},{"maturity":"2029-12-20","coupon":0.05,"notional":4e6,"side":"SELL_PROTECTION"}])",
                 R"([{"maturity":"2028-12-20","coupon":0.01},{"maturity":"2036-12-20","coupon":0.01}])",
                 R"(["CS01","JTD"])"));
    CHECK(std::fabs(i_num(both, {"after", "cs01"})) < 1e-6);
    CHECK(std::fabs(i_num(both, {"after", "jtd"})) < 1e-6);
    // Sum of bucket CS01s against the parallel CS01: equal to first order only.
    double sum = 0.0;
    for (const json::Value& b : both.find("book")->find("buckets")->items) sum += b.number;
    const double parallel = i_num(both, {"book", "cs01"});
    CHECK(std::fabs(sum - parallel) < 1e-3 * std::fabs(parallel));
    CHECK(sum != parallel);
}

TEST_CASE("I2 credit: a section after every maturity has zero risk exactly; the check ladder") {
    const json::Value o = i_outputs(
        "hedge.credit.cds", i_credit(R"([{"maturity":"2028-12-20","coupon":0.01,"notional":1e6,"side":"BUY_PROTECTION"}])",
                                     R"([{"maturity":"2028-06-20","coupon":0.01}])", R"(["BUCKET_2"])"));
    for (std::size_t k = 2; k < 5; ++k) CHECK(o.find("book")->find("buckets")->items[k].number == 0.0);
    const std::string book = R"([{"maturity":"2028-12-20","coupon":0.01,"notional":1e6,"side":"BUY_PROTECTION"}])";
    const std::string hedge = R"([{"maturity":"2028-06-20","coupon":0.01}])";
    CHECK(i_code(i_case("hedge.credit.cds", i_credit(book, hedge, R"(["BUCKET_0"])"))) == "E_INPUT");
    CHECK(i_code(i_case("hedge.credit.cds", i_credit(book, hedge, R"(["BUCKET_01"])"))) == "E_INPUT");
    CHECK(i_code(i_case("hedge.credit.cds", i_credit(book, hedge, R"(["VEGA"])"))) == "E_INPUT");
    CHECK(i_code(i_case("hedge.credit.cds", i_credit(book, hedge, R"(["BUCKET_4"])"))) == "E_SINGULAR");
    CHECK(i_code(i_case("hedge.credit.cds", i_credit("[]", hedge, R"(["CS01"])"))) == "E_INPUT");
    CHECK(i_code(i_case("hedge.credit.cds",
                        i_credit(book, R"([{"maturity":"2028-06-20","coupon":-0.01}])", R"(["CS01"])"))) == "E_DOMAIN");
}

TEST_CASE("I2 correlation: a long exchange option has negative correlation01; a vanilla has none") {
    const hg::TwoAssetMarket m{100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.3, 0.4};
    const hg::TwoAssetPosition exchange{hg::TwoAssetKind::Exchange, 1.0, 1.0, 0.0, 1.0, 1.0};
    const hg::TwoAssetGreeks g = hg::unit_two_asset_greeks(m, exchange);
    CHECK(g[4] < 0.0);
    // I-17: the vega and correlation rows are dV/ds times common factors.
    CHECK(std::fabs(g[2] / g[4] - (0.25 - 0.4 * 0.3) / (-0.01 * 0.25 * 0.3)) < 1e-12 * std::fabs(g[2] / g[4]));
    CHECK(std::fabs(g[3] / g[2] - (0.3 - 0.4 * 0.25) / (0.25 - 0.4 * 0.3)) < 1e-12);
    for (const hg::TwoAssetKind kind : {hg::TwoAssetKind::Call1, hg::TwoAssetKind::Put2}) {
        const hg::TwoAssetGreeks v = hg::unit_two_asset_greeks(m, {kind, 0.0, 0.0, 100.0, 0.5, 1.0});
        CHECK(v[4] == 0.0);
    }
    // Margrabe delta against a central difference of the price F1 N(d1) - F2 N(d2) in spot1.
    const auto price = [&](double s1) {
        hg::TwoAssetMarket b = m;
        b.spot1 = s1;
        const double sp = std::sqrt(b.vol1 * b.vol1 + b.vol2 * b.vol2 - 2.0 * b.correlation * b.vol1 * b.vol2);
        const double f1 = s1 * std::exp(-b.yield1), f2 = b.spot2 * std::exp(-b.yield2);
        const double d1 = (std::log(f1 / f2) + 0.5 * sp * sp) / sp;
        return f1 * normal_cdf(d1) - f2 * normal_cdf(d1 - sp);
    };
    CHECK(std::fabs((price(100.01) - price(99.99)) / 0.02 - g[0]) < 1e-8);
    hg::TwoAssetMarket flat = m;
    flat.correlation = 1.0;
    flat.vol2 = 0.25;
    CHECK(i_error([&] { hg::correlation_hedge(flat, {exchange}, {exchange}, {hg::TwoAssetTarget::Delta1}); }) ==
          "E_DOMAIN");
    CHECK(i_error([&] {
              hg::correlation_hedge(m, {exchange}, {exchange, exchange},
                                    {hg::TwoAssetTarget::Correlation, hg::TwoAssetTarget::Vega1});
          }) == "E_SINGULAR");
}

TEST_CASE("I2 correlation CLI: a key set other than the kind's is E_INPUT, after the finite rule") {
    const std::string head =
        R"({"spot1":100,"spot2":95,"rate":0.03,"yield1":0.01,"yield2":0.02,"vol1":0.25,"vol2":0.3,"correlation":0.4,"targets":["DELTA_1"],"book":[{"instrument":"CALL_1","strike":100,"expiry_years":0.5,"quantity":10}],"hedges":[)";
    CHECK(i_code(i_case("hedge.correlation.neutralise", head + R"({"instrument":"UNDERLYING_1"}]})")) == "ok");
    CHECK(i_code(i_case("hedge.correlation.neutralise", head + R"({"instrument":"UNDERLYING_1","quantity":1}]})")) ==
          "E_INPUT");
    CHECK(i_code(i_case("hedge.correlation.neutralise", head + R"({"instrument":"UNDERLYING_1","note":"x"}]})")) ==
          "E_INPUT");
    CHECK(i_code(i_case("hedge.correlation.neutralise",
                        head + R"({"instrument":"CALL_1","strike":"NaN"}]})")) == "E_DOMAIN");
}

// ---- wave 3: cross-asset hedge ----

namespace {

hg::ZeroCurve i_zero_curve() { return {{1.0, 2.0, 5.0, 10.0}, {0.030, 0.032, 0.035, 0.037}}; }

hg::CrossAssetPosition i_xa(hg::CrossAssetKind kind, double strike, double expiry, double notional, double quantity) {
    hg::CrossAssetPosition p;
    p.kind = kind;
    p.strike = strike;
    p.expiry_years = expiry;
    p.notional = notional;
    p.quantity = quantity;
    return p;
}

}  // namespace

TEST_CASE("I3 cross-asset: a square regular hedge leaves no residual risk; bonds alone have EQ01 = 0") {
    using K = hg::CrossAssetKind;
    const hg::ZeroCurve c = i_zero_curve();
    const std::vector<hg::CrossAssetPosition> book{i_xa(K::Call, 100.0, 3.0, 0.0, -1000.0),
                                                   i_xa(K::Zcb, 0.0, 7.0, 1e5, 10.0)};
    const std::vector<hg::CrossAssetPosition> hedges{
        i_xa(K::Forward, 100.0, 4.0, 0.0, 0.0), i_xa(K::Zcb, 0.0, 1.0, 1e5, 0.0), i_xa(K::Zcb, 0.0, 2.0, 1e5, 0.0),
        i_xa(K::Zcb, 0.0, 5.0, 1e5, 0.0), i_xa(K::Zcb, 0.0, 10.0, 1e5, 0.0)};
    const Vec w(5, 1.0);
    const hg::CrossAssetHedge r = hg::cross_asset_hedge(100.0, 0.01, 0.2, c, book, hedges, w, 0.0);
    double scale = 0.0;
    for (const double v : r.book_risk) scale = std::max(scale, std::fabs(v));
    for (const double v : r.residual_risk) CHECK(std::fabs(v) < 1e-9 * scale);
    const Vec bond = hg::cross_asset_risk(100.0, 0.01, 0.2, c, i_xa(K::Zcb, 0.0, 3.0, 1e5, 0.0));
    CHECK(bond[0] == 0.0);
    // Between pillars 2 and 5 the risk is shared by those two only; before pillar 1 it all sits on pillar 1.
    CHECK(bond[1] == 0.0);
    CHECK(bond[4] == 0.0);
    CHECK(bond[2] < 0.0);
    CHECK(bond[3] < 0.0);
    const Vec early = hg::cross_asset_risk(100.0, 0.01, 0.2, c, i_xa(K::Zcb, 0.0, 0.5, 1e5, 0.0));
    CHECK(early[1] < 0.0);
    for (std::size_t k = 2; k < early.size(); ++k) CHECK(early[k] == 0.0);
    const Vec spot = hg::cross_asset_risk(100.0, 0.01, 0.2, c, i_xa(K::Underlying, 0.0, 0.0, 0.0, 0.0));
    CHECK(std::fabs(spot[0] - 1.0) < 1e-14);
    for (std::size_t k = 1; k < spot.size(); ++k) CHECK(spot[k] == 0.0);
}

TEST_CASE("I3 cross-asset: scaling every weight leaves the positions unchanged when ridge = 0") {
    using K = hg::CrossAssetKind;
    const hg::ZeroCurve c = i_zero_curve();
    const std::vector<hg::CrossAssetPosition> book{i_xa(K::Put, 95.0, 2.5, 0.0, 500.0),
                                                   i_xa(K::Forward, 105.0, 6.0, 0.0, -200.0)};
    const std::vector<hg::CrossAssetPosition> hedges{i_xa(K::Underlying, 0.0, 0.0, 0.0, 0.0),
                                                     i_xa(K::Zcb, 0.0, 2.0, 1e4, 0.0), i_xa(K::Zcb, 0.0, 10.0, 1e4, 0.0)};
    const Vec w{4.0, 1.0, 2.0, 0.5, 3.0};
    Vec w7 = w;
    for (double& v : w7) v *= 7.0;
    const hg::CrossAssetHedge a = hg::cross_asset_hedge(100.0, 0.01, 0.2, c, book, hedges, w, 0.0);
    const hg::CrossAssetHedge b = hg::cross_asset_hedge(100.0, 0.01, 0.2, c, book, hedges, w7, 0.0);
    for (std::size_t j = 0; j < 3; ++j) CHECK(std::fabs(a.positions[j] - b.positions[j]) < 1e-10 * std::fabs(a.positions[j]));
    CHECK(std::fabs(b.objective - 7.0 * a.objective) < 1e-10 * b.objective);
}

TEST_CASE("I3 cross-asset: the check ladder") {
    using K = hg::CrossAssetKind;
    const hg::ZeroCurve c = i_zero_curve();
    const std::vector<hg::CrossAssetPosition> book{i_xa(K::Call, 100.0, 3.0, 0.0, 1.0)};
    const std::vector<hg::CrossAssetPosition> one{i_xa(K::Underlying, 0.0, 0.0, 0.0, 0.0)};
    const Vec w(5, 1.0);
    CHECK(i_error([&] { hg::cross_asset_hedge(100.0, 0.0, 0.2, {{1.0, 1.0}, {0.03, 0.03}}, book, one, Vec(3, 1.0), 0.0); }) ==
          "E_INPUT");
    CHECK(i_error([&] { hg::cross_asset_hedge(100.0, 0.0, 0.2, c, book, one, Vec(4, 1.0), 0.0); }) == "E_INPUT");
    CHECK(i_error([&] {
              hg::cross_asset_hedge(100.0, 0.0, 0.2, c, {i_xa(K::Call, 100.0, 11.0, 0.0, 1.0)}, one, w, 0.0);
          }) == "E_INPUT");
    CHECK(i_error([&] { hg::cross_asset_hedge(100.0, 0.0, 0.0, c, book, one, w, 0.0); }) == "E_DOMAIN");
    CHECK(i_error([&] { hg::cross_asset_hedge(100.0, 0.0, 0.2, c, book, {one[0], one[0]}, w, 0.0); }) == "E_SINGULAR");
    const std::string head =
        R"({"spot":100,"dividend_yield":0.01,"volatility":0.2,"curve":{"times":[1,2],"zero_rates":[0.03,0.032]},"weights":[1,1,1],"book":[{"instrument":"ZCB","expiry_years":1.5,"notional":100,"quantity":1}],"hedges":[)";
    CHECK(i_code(i_case("hedge.crossasset.solve", head + R"({"instrument":"ZCB","expiry_years":2,"notional":100}]})")) ==
          "ok");
    CHECK(i_code(i_case("hedge.crossasset.solve", head + R"({"instrument":"ZCB","expiry_years":2}]})")) == "E_INPUT");
    CHECK(i_code(i_case("hedge.crossasset.solve",
                        R"({"spot":100,"dividend_yield":0.01,"volatility":0.2,"curve":{"times":[2,1],"zero_rates":[0.03,0.032]},"weights":[1,1,1],"book":[{"instrument":"ZCB","quantity":1}],"hedges":[{"instrument":"UNDERLYING"}]})")) ==
          "E_INPUT");
}

// ---- wave 4a: costs, impact and margin; the frontier ----

namespace {

double i_true_objective(const hg::QpProblem& p, const Vec& x) {
    double f = i_objective(p.a, p.b, p.weights, p.ridge, x), c = 0.0;
    for (std::size_t j = 0; j < x.size(); ++j) {
        if (p.half_spreads) c += (*p.half_spreads)[j] * std::fabs(x[j]);
        if (p.impact) c += (*p.impact)[j] * x[j] * x[j];
    }
    return f + p.cost_weight.value_or(1.0) * c;
}

double i_margin(const hg::QpProblem& p, const Vec& x) {
    double m = 0.0;
    for (std::size_t j = 0; j < x.size(); ++j) m += (*p.margin_rates)[j] * std::fabs(x[j]);
    return m;
}

}  // namespace

TEST_CASE("I4a costs: cost_weight = 0 gives the wave 1 answer; no feasible perturbation does better") {
    std::mt19937_64 rng(404);
    for (int trial = 0; trial < 30; ++trial) {
        const std::size_t n = 2 + std::size_t(trial % 4);
        hg::QpProblem p = i_qp(rng, n + 3, n, 0, trial % 2 == 0);
        const hg::QpResult plain = hg::solve_qp(p);
        p.half_spreads = i_vector(rng, n, 0.0, 1.5);
        p.impact = i_vector(rng, n, 0.0, 0.2);
        p.cost_weight = 0.0;
        const hg::QpResult zero = hg::solve_qp(p);
        for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(zero.x[j] - plain.x[j]) < 1e-12 * (1.0 + std::fabs(plain.x[j])));
        CHECK(zero.objective == zero.risk);
        p.cost_weight = 1.0;
        const hg::QpResult r = hg::solve_qp(p);
        CHECK(std::fabs(r.objective - (r.risk + r.cost)) < 1e-14 * (1.0 + r.objective));
        std::uniform_real_distribution<double> step(-0.02, 0.02);
        for (int probe = 0; probe < 40; ++probe) {
            Vec y = r.x;
            for (std::size_t j = 0; j < n; ++j) {
                y[j] += step(rng);
                if (p.lower && (*p.lower)[j]) y[j] = std::max(y[j], *(*p.lower)[j]);
                if (p.upper && (*p.upper)[j]) y[j] = std::min(y[j], *(*p.upper)[j]);
            }
            CHECK(i_true_objective(p, y) >= r.objective - 1e-12 * (1.0 + r.objective));
        }
    }
}

TEST_CASE("I4a costs: a costly instrument is left out exactly; an active margin equals its limit") {
    hg::QpProblem p;
    p.a = {{1.0, 0.2}, {0.3, 1.0}, {0.5, 0.5}};
    p.b = {-1.0, 0.4, -0.2};
    p.weights = {1.0, 1.0, 1.0};
    p.half_spreads = Vec{0.0, 50.0};
    const hg::QpResult r = hg::solve_qp(p);
    CHECK(r.x[1] == 0.0);
    CHECK(!std::signbit(r.x[1]));
    hg::QpProblem m;
    m.a = p.a;
    m.b = p.b;
    m.weights = p.weights;
    m.margin_rates = Vec{0.1, 0.2};
    m.margin_limit = 0.05;
    const hg::QpResult limited = hg::solve_qp(m);
    REQUIRE(limited.margined);
    CHECK(std::fabs(limited.margin - 0.05) < 1e-14);
    CHECK(std::fabs(i_margin(m, limited.x) - 0.05) < 1e-14);
    m.lower = std::vector<hg::Bound>{1.0, std::nullopt};
    CHECK(i_error([&] { hg::solve_qp(m); }) == "E_INFEASIBLE");  // the bound alone needs margin 0.1
    hg::QpProblem s = p;
    s.a = {{1.0, 1.0}, {0.5, 0.5}};
    s.b = {-1.0, 0.5};
    s.weights = {1.0, 1.0};
    s.half_spreads = Vec{0.1, 0.1};
    CHECK(i_error([&] { hg::solve_qp(s); }) == "E_SINGULAR");  // a spread does not regularise (I-26)
    s.impact = Vec{0.0, 0.01};
    CHECK(i_error([&] { hg::solve_qp(s); }) == "ok");          // impact does
    s.singular = hg::Singular::MinNorm;
    CHECK(i_error([&] { hg::solve_qp(s); }) == "E_INPUT");
}

TEST_CASE("I4a frontier: risk non-decreasing and cost non-increasing in the cost weight") {
    const std::string base =
        R"({"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9]],"b":[-2.0,1.5,-0.7,0.9],"weights":[1,2,0.5,1.5],"half_spreads":[0.05,0.3,0.1],"impact":[0.01,0.02,0.0],"cost_weights":[0,0.25,0.5,1,2,4,8,16]})";
    const json::Value o = i_outputs("hedge.frontier.solve", base);
    const auto& points = o.find("points")->items;
    REQUIRE(points.size() == 8);
    for (std::size_t i = 1; i < points.size(); ++i) {
        CHECK(points[i].find("risk")->number >= points[i - 1].find("risk")->number * (1.0 - 1e-12));
        CHECK(points[i].find("cost")->number <= points[i - 1].find("cost")->number * (1.0 + 1e-12));
    }
    CHECK(i_code(i_case("hedge.frontier.solve",
                        R"({"a":[[1.0]],"b":[1.0],"weights":[1],"half_spreads":[0.1],"cost_weights":[1,0.5]})")) ==
          "E_INPUT");
    CHECK(i_code(i_case("hedge.frontier.solve",
                        R"({"a":[[1.0]],"b":[1.0],"weights":[1],"margin_rates":[0.1],"margin_limit":1,"cost_weights":[1]})")) ==
          "E_INPUT");
}

TEST_CASE("I-48 costs: the oracle enumeration keeps its own cap; the operation has none below 200") {
    hg::QpProblem p;
    const std::size_t n = 21;
    p.a = Matrix(n, Vec(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) p.a[i][i] = 1.0;
    p.b = Vec(n, 1.0);
    p.weights = Vec(n, 1.0);
    p.half_spreads = Vec(n, 0.1);
    CHECK(i_error([&] { hg::detail::solve_qp_by_orthants(p); }) == "E_LIMIT");
    const hg::QpResult r = hg::solve_qp(p);
    for (const double v : r.x) CHECK(std::fabs(v + 0.95) < 1e-14);  // 2(x + 1) + 0.1 sign(x) = 0
}

namespace {

// Random problem for the sign-state tests: every instrument has a spread, most have open signs, some have box
// bounds away from 0, and (when `margin` > 0) a margin limit at that fraction of the margin used without it.
hg::QpProblem i_costed(std::mt19937_64& rng, std::size_t n, double margin, bool equality) {
    hg::QpProblem p;
    p.a = i_random(rng, n + 5, n);
    p.b = i_vector(rng, n + 5, -3.0, 3.0);
    p.weights = i_vector(rng, n + 5, 0.5, 2.0);
    p.ridge = 0.01;
    p.half_spreads = i_vector(rng, n, 0.0, 0.6);
    p.impact = i_vector(rng, n, 0.0, 0.05);
    p.lower = std::vector<hg::Bound>(n);
    p.upper = std::vector<hg::Bound>(n);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    for (std::size_t j = 0; j < n; ++j) {
        if (j % 5 == 4) (*p.half_spreads)[j] = 50.0;  // costly: left out exactly, the subgradient branch
        if (u(rng) < 0.3) (*p.lower)[j] = -0.3 - u(rng);
        if (u(rng) < 0.3) (*p.upper)[j] = 0.3 + u(rng);
    }
    if (equality) {
        p.eq_matrix = Matrix{Vec(n, 1.0)};
        p.eq_rhs = Vec{0.1};
    }
    if (margin > 0.0) {
        p.margin_rates = i_vector(rng, n, 0.05, 0.3);
        const hg::QpResult free = hg::solve_qp(p.half_spreads ? [&] {
            hg::QpProblem q = p;
            q.margin_rates.reset();
            return q;
        }() : p);
        double used = 0.0;
        for (std::size_t j = 0; j < n; ++j) used += (*p.margin_rates)[j] * std::fabs(free.x[j]);
        p.margin_limit = margin * used;
    }
    return p;
}

// KKT conditions of the whole problem at x, without equalities: stationarity with the subgradient at zero
// coordinates, feasibility, complementary slackness of the bounds and of the margin. Tolerance 1e-8 of the
// gradient scale.
void i_kkt(const hg::QpProblem& p, const Vec& x) {
    const std::size_t n = x.size();
    const double cw = p.cost_weight.value_or(1.0);
    Vec g = i_gradient(p.a, p.b, p.weights, p.ridge, x);
    double scale = 1.0;
    for (std::size_t j = 0; j < n; ++j) {
        g[j] += 2.0 * cw * (*p.impact)[j] * x[j];
        scale = std::max(scale, std::fabs(g[j]) + cw * (*p.half_spreads)[j]);
    }
    const double tol = 1e-8 * scale;
    double mu = 0.0, used = 0.0;
    if (p.margin_rates) {
        for (std::size_t j = 0; j < n; ++j) used += (*p.margin_rates)[j] * std::fabs(x[j]);
        REQUIRE(used <= *p.margin_limit * (1.0 + 1e-12) + 1e-14);
        // mu from the free nonzero coordinate with the largest |x|: g + (cw hs + mu m) s = 0.
        std::size_t best = n;
        for (std::size_t j = 0; j < n; ++j) {
            const bool at_bound = ((*p.lower)[j] && x[j] == *(*p.lower)[j]) || ((*p.upper)[j] && x[j] == *(*p.upper)[j]);
            if (x[j] != 0.0 && !at_bound && (best == n || std::fabs(x[j]) > std::fabs(x[best]))) best = j;
        }
        if (best < n) {
            const double s = x[best] > 0.0 ? 1.0 : -1.0;
            mu = -(g[best] * s + cw * (*p.half_spreads)[best]) / (*p.margin_rates)[best];
        }
        CHECK(mu >= -tol);
        if (mu > tol) CHECK(std::fabs(used - *p.margin_limit) <= 1e-10 * (1.0 + *p.margin_limit));
    }
    for (std::size_t j = 0; j < n; ++j) {
        const double kj = cw * (*p.half_spreads)[j] + (p.margin_rates ? mu * (*p.margin_rates)[j] : 0.0);
        const bool at_lower = (*p.lower)[j] && x[j] <= *(*p.lower)[j] + 1e-12;
        const bool at_upper = (*p.upper)[j] && x[j] >= *(*p.upper)[j] - 1e-12;
        if ((*p.lower)[j]) REQUIRE(x[j] >= *(*p.lower)[j] - 1e-12);
        if ((*p.upper)[j]) REQUIRE(x[j] <= *(*p.upper)[j] + 1e-12);
        const double s = x[j] > 0.0 ? 1.0 : -1.0;
        if (x[j] == 0.0) CHECK(std::fabs(g[j]) <= kj + tol);         // 0 in g + k [-1, 1]
        else if (at_lower) CHECK(g[j] + kj * s >= -tol);             // bound multiplier >= 0
        else if (at_upper) CHECK(g[j] + kj * s <= tol);
        else CHECK(std::fabs(g[j] + kj * s) <= tol);                 // stationarity
    }
}

}  // namespace

TEST_CASE("I-48 sign states: KKT conditions at 21, 50 and 200 open-sign instruments") {
    std::mt19937_64 rng(4848);
    for (const std::size_t n : {std::size_t{21}, std::size_t{50}, std::size_t{200}}) {
        INFO(n);
        const hg::QpProblem p = i_costed(rng, n, 0.0, false);
        const hg::QpResult r = hg::solve_qp(p);
        i_kkt(p, r.x);
        std::size_t zeros = 0;
        for (const double v : r.x) zeros += v == 0.0;
        CHECK(zeros > 0);  // the spreads leave some instruments out exactly
    }
    for (const std::size_t n : {std::size_t{21}, std::size_t{50}}) {  // a binding margin
        INFO(n);
        const hg::QpProblem p = i_costed(rng, n, 0.6, false);
        const hg::QpResult r = hg::solve_qp(p);
        CHECK(std::fabs(r.margin - *p.margin_limit) <= 1e-10 * (1.0 + *p.margin_limit));
        i_kkt(p, r.x);
    }
}

TEST_CASE("I-48 sign states agree with the orthant enumeration on random problems with k up to 12") {
    std::mt19937_64 rng(1248);
    int agreed = 0;
    for (int trial = 0; trial < 60; ++trial) {
        const std::size_t n = 1 + std::size_t(trial % 12);
        const double margin = trial % 3 == 0 ? 0.0 : (trial % 3 == 1 ? 0.7 : 1.5);
        const hg::QpProblem p = i_costed(rng, n, margin, trial % 4 == 3 && n > 1);
        const std::string a = i_error([&] { hg::detail::solve_qp_by_orthants(p); });
        const std::string b = i_error([&] { hg::solve_qp(p); });
        REQUIRE(a == b);
        if (a != "ok") continue;
        const hg::QpResult oracle = hg::detail::solve_qp_by_orthants(p), r = hg::solve_qp(p);
        CHECK(std::fabs(r.objective - oracle.objective) <= 1e-12 * (1.0 + oracle.objective));
        for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(r.x[j] - oracle.x[j]) <= 1e-9 * (1.0 + std::fabs(oracle.x[j])));
        ++agreed;
    }
    CHECK(agreed > 40);
}

// ---- wave 4b: backtest and effectiveness ----

TEST_CASE("I4b effectiveness: a perfect offset gives 1, -1, 1, 1; the I-31 domain") {
    const hg::Effectiveness e = hg::effectiveness({100.0, -50.0, 30.0, -20.0}, {-100.0, 50.0, -30.0, 20.0});
    CHECK(e.dollar_offset == 1.0);
    CHECK(std::fabs(e.regression_slope + 1.0) < 1e-15);
    CHECK(std::fabs(e.regression_r2 - 1.0) < 1e-15);
    CHECK(e.variance_reduction == 1.0);
    // Sums to 0 exactly, while left-to-right binary64 summation gives -1 (1 + 1e16 rounds to 1e16).
    CHECK(i_error([] { hg::effectiveness({1.0, 1e16, -1e16, -1.0}, {1.0, 2.0, 0.5, 3.0}); }) == "E_DOMAIN");
    // I-43: a sum within 1e-12 of sum |x| is zero (the binary sum here is 2^-55).
    CHECK(i_error([] { hg::effectiveness({0.1, 0.2, -0.3}, {1.0, 2.0, 0.5}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::effectiveness({0.1, 0.2, -0.29}, {1.0, 2.0, 0.5}); }) == "ok");
    // I-43: a variance below 1e-20 times the other's is zero.
    CHECK(i_error([] { hg::effectiveness({1.0, 2.0, 4.0}, {1.0, 1.0 + 1e-12, 1.0}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::effectiveness({1.0, 2.0, 4.0}, {1.0, 1.0 + 1e-6, 1.0}); }) == "ok");
    CHECK(i_error([] { hg::effectiveness({0.1, 0.1, 0.1}, {1.0, 2.0, 0.5}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::effectiveness({0.1, 0.2, 0.4}, {1.0, 1.0, 1.0}); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::effectiveness({0.1, 0.2}, {1.0, 2.0}); }) == "E_INPUT");
}

TEST_CASE("I4b backtest: constant spot, zero carry: portfolio values end at quantity (V_last - V_0)") {
    const hg::BacktestOption call{true, 100.0, 0.5};
    const Vec times{0.0, 0.1, 0.2, 0.3, 0.5}, flat(5, 100.0);
    // The hedge leg has zero variance on a constant path, so the operation itself stops at I-31.
    CHECK(i_error([&] { hg::backtest_delta(call, -10.0, 0.0, 0.0, 0.2, times, flat); }) == "E_DOMAIN");
    // The replay: on a constant path with zero rates and dividends the shares never earn anything, so
    // Pi_{m-1} = quantity (V_{m-1} - V_0). A tiny last move keeps the hedge leg's variance above 0.
    Vec path = flat;
    path.back() = 100.0 + 1e-9;
    const hg::DeltaBacktest r = hg::backtest_delta(call, -10.0, 0.0, 0.0, 0.2, times, path);
    const double expected = -10.0 * (r.option_values.back() - r.option_values.front()) + r.shares.back() * 1e-9;
    CHECK(std::fabs(r.final_pnl - expected) < 1e-12);
    CHECK(r.portfolio_values.front() == 0.0);
    CHECK(r.shares.size() == 4);
}

TEST_CASE("I4b backtest: self-financing and the check ladder") {
    const hg::BacktestOption put{false, 95.0, 0.25};
    const Vec times{0.0, 0.05, 0.1, 0.15, 0.2, 0.25};
    const Vec spots{100.0, 97.0, 99.5, 94.0, 96.0, 93.0};
    const hg::DeltaBacktest r = hg::backtest_delta(put, 50.0, 0.03, 0.01, 0.25, times, spots);
    CHECK(r.option_values.back() == 2.0);  // payoff at expiry
    for (const double h : r.shares) CHECK(h > 0.0);  // long puts are hedged with long shares
    // The P&L of the hedged book against the unhedged option's change: the hedge offsets most of it.
    CHECK(r.stats.regression_slope < 0.0);
    CHECK(i_error([&] { hg::backtest_delta(put, 50.0, 0.03, 0.01, 0.25, {0.0, 0.1, 0.2, 0.3}, {100.0, 97.0, 99.5}); }) ==
          "E_INPUT");
    CHECK(i_error([&] { hg::backtest_delta(put, 50.0, 0.03, 0.01, 0.25, {0.0, 0.05, 0.1, 0.15}, {100.0, 97.0, 0.0, 99.0}); }) ==
          "E_DOMAIN");
    CHECK(i_error([&] { hg::backtest_delta(put, 0.0, 0.03, 0.01, 0.25, times, spots); }) == "E_DOMAIN");
    CHECK(i_error([&] { hg::backtest_delta(put, 50.0, 0.03, 0.01, 0.25, {0.0, 0.05, 0.1, 0.15}, {100.0, 97.0, 99.5, 98.0}); }) ==
          "ok");
    CHECK(i_error([&] { hg::backtest_delta(put, 50.0, 0.03, 0.01, 0.25, {0.0, 0.1, 0.2, 0.3, 0.4}, Vec(5, 100.0)); }) ==
          "E_INPUT");  // the path ends after expiry
}

// ---- wave 4c: instrument selection; wave 4d: slippage ----

TEST_CASE("I4c selection: K = n gives the QP answer; the best objective never rises with K; ties (I-34)") {
    std::mt19937_64 rng(4040);
    for (int trial = 0; trial < 10; ++trial) {
        const std::size_t n = 3 + std::size_t(trial % 3);
        hg::QpProblem p = i_qp(rng, n + 2, n, 0, false);
        const hg::QpResult full = hg::solve_qp(p);
        double previous = std::numeric_limits<double>::infinity();
        for (long long k = 1; k <= (long long)n; ++k) {
            const hg::SelectResult r = hg::select_instruments(p, k, false);
            CHECK(r.objective <= previous * (1.0 + 1e-12));
            CHECK((long long)r.selected.size() <= k);
            CHECK(std::ranges::is_sorted(r.selected));
            previous = r.objective;
            if (k == (long long)n) {
                CHECK(std::fabs(r.objective - full.objective) <= 1e-12 * full.objective);
                for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(r.x[j] - full.x[j]) < 1e-10);
            }
        }
    }
    // Two symmetric instruments: an exact tie, index 0 wins.
    hg::QpProblem s;
    s.a = {{1.0, 0.0}, {0.0, 1.0}};
    s.b = {-1.0, -1.0};
    s.weights = {1.0, 1.0};
    CHECK(hg::select_instruments(s, 1, false).selected == std::vector<long long>{0});
    CHECK(i_error([&] { hg::select_instruments(s, 3, false); }) == "E_INPUT");
    CHECK(i_error([&] { hg::select_instruments(s, 1, true); }) == "E_INPUT");
    s.lower = std::vector<hg::Bound>{0.5, std::nullopt};
    CHECK(i_error([&] { hg::select_instruments(s, 1, false); }) == "E_DOMAIN");
}

TEST_CASE("I4d slippage: shortfall = execution + opportunity; slippage = execution - model; totals add") {
    std::vector<hg::Order> orders{{1000.0, 100.0, 101.5, 0.02, 1e-4, {{400.0, 100.05}, {600.0, 100.12}}},
                                  {-500.0, 50.0, 49.2, 0.01, 2e-4, {{-300.0, 49.97}}},
                                  {200.0, 20.0, 21.0, 0.0, 0.0, {}}};
    const hg::SlippageReport r = hg::slippage_report(orders);
    double e = 0.0, o = 0.0, m = 0.0;
    for (const hg::Slippage& s : r.orders) {
        CHECK(std::fabs(s.shortfall - (s.execution_cost + s.opportunity_cost)) < 1e-12);
        CHECK(std::fabs(s.slippage - (s.execution_cost - s.model_cost)) < 1e-12);
        e += s.execution_cost;
        o += s.opportunity_cost;
        m += s.model_cost;
    }
    CHECK(r.total.execution_cost == e);
    CHECK(r.total.opportunity_cost == o);
    CHECK(r.total.model_cost == m);
    CHECK(!r.orders[2].average_price.has_value());  // I-37
    CHECK(r.orders[2].opportunity_cost == 200.0);
    CHECK(r.orders[1].execution_cost > 0.0);  // selling below the decision price is a cost
    orders[0].fills.push_back({1.0, 100.0});
    CHECK(i_error([&] { hg::slippage_report(orders); }) == "E_INPUT");  // overfilled
    orders[0].fills.pop_back();
    orders[1].impact = -1.0;
    CHECK(i_error([&] { hg::slippage_report(orders); }) == "E_DOMAIN");
    CHECK(i_error([] { hg::slippage_report({}); }) == "E_INPUT");
}

// ---- wave 4e: costs in the backtest ----

TEST_CASE("I4e backtest costs: zero costs equal the replay; without carry the P&L falls by the costs paid") {
    const hg::BacktestOption call{true, 100.0, 0.25};
    const Vec times{0.0, 0.05, 0.1, 0.15, 0.2, 0.25};
    const Vec spots{100.0, 101.0, 99.0, 102.5, 101.5, 103.0};
    const hg::DeltaBacktest free = hg::backtest_delta(call, -100.0, 0.0, 0.0, 0.2, times, spots);
    CHECK(!free.costed);
    const hg::DeltaBacktest zero = hg::backtest_delta(call, -100.0, 0.0, 0.0, 0.2, times, spots, {0.0, 0.0});
    CHECK(zero.costed);
    CHECK(zero.trading_cost == 0.0);
    CHECK(zero.final_pnl == free.final_pnl);
    const hg::DeltaBacktest paid = hg::backtest_delta(call, -100.0, 0.0, 0.0, 0.2, times, spots, {0.02, 0.001});
    CHECK(paid.trading_cost > 0.0);
    CHECK(std::fabs(paid.final_pnl - (free.final_pnl - paid.trading_cost)) < 1e-10);
    CHECK(paid.portfolio_values.front() < 0.0);  // Pi_0 = -cost(h_0)
    // The opening trade alone: half_spread |h_0| + impact h_0^2.
    const double h0 = paid.shares.front();
    CHECK(std::fabs(-paid.portfolio_values.front() - (0.02 * std::fabs(h0) + 0.001 * h0 * h0)) < 1e-12);
    CHECK(i_error([&] { hg::backtest_delta(call, -100.0, 0.0, 0.0, 0.2, times, spots, {-0.01, std::nullopt}); }) ==
          "E_DOMAIN");
}

// ---- the stage I example inputs (examples/hedge_*_i.json; follow-up note to waves 1 to 4d) ----

#ifdef QF_REPO_DIR
#include <fstream>
#include <sstream>

namespace {

std::string i_read(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    return s.str();
}

// Every number in `expected` within 1e-9 relative (1e-9 absolute below 1) of `actual`; same shape otherwise.
void i_same(const json::Value& actual, const json::Value& expected, const std::string& where) {
    INFO(where);
    REQUIRE(actual.kind == expected.kind);
    switch (expected.kind) {
        case json::Kind::Number:
            CHECK(std::fabs(actual.number - expected.number) <= 1e-9 * std::max(1.0, std::fabs(expected.number)));
            break;
        case json::Kind::Array:
            REQUIRE(actual.items.size() == expected.items.size());
            for (std::size_t i = 0; i < expected.items.size(); ++i) i_same(actual.items[i], expected.items[i], where);
            break;
        case json::Kind::Object:
            REQUIRE(actual.members.size() == expected.members.size());
            for (const json::Member& m : expected.members) {
                REQUIRE(actual.find(m.first) != nullptr);
                i_same(*actual.find(m.first), m.second, where + "." + m.first);
            }
            break;
        default: CHECK(actual.text == expected.text); break;
    }
}

}  // namespace

TEST_CASE("Stage I examples run through the CLI and give the outputs of their golden cases") {
    struct Example {
        const char* file;
        const char* suite;
        const char* case_id;
    };
    const Example examples[] = {
        {"hedge_greeks_i", "hedgegreeks_i", "hedgegreeks_i-0003"}, {"hedge_minvar_i", "hedgemv_i", "hedgemv_i-0006"},
        {"hedge_beta_i", "hedgebeta_i", "hedgebeta_i-0001"},       {"hedge_qp_keyrate_i", "hedgeqp_i", "hedgeqp_i-0009"},
        {"hedge_qp_minnorm_i", "hedgeqp_i", "hedgeqp_i-0018"},     {"hedge_integer_i", "hedgeint_i", "hedgeint_i-0010"},
        {"hedge_residual_i", "hedgeres_i", "hedgeres_i-0002"},     {"hedge_credit_i", "hedgecredit_i", "hedgecredit_i-0004"},
        {"hedge_correlation_i", "hedgecorr_i", "hedgecorr_i-0003"}, {"hedge_crossasset_i", "hedgexa_i", "hedgexa_i-0002"},
        {"hedge_cost_i", "hedgecost_i", "hedgecost_i-0002"},       {"hedge_frontier_i", "hedgefrontier_i", "hedgefrontier_i-0001"},
        {"hedge_backtest_i", "hedgebt_i", "hedgebt_i-0001"},       {"hedge_effectiveness_i", "hedgeeff_i", "hedgeeff_i-0001"},
        {"hedge_select_i", "hedgeselect_i", "hedgeselect_i-0009"}, {"hedge_slippage_i", "hedgeslip_i", "hedgeslip_i-0003"},
    };
    const std::string root = QF_REPO_DIR;
    for (const Example& e : examples) {
        INFO(e.file);
        const auto r = cli::run_case(i_read(root + "/examples/" + e.file + ".json"));
        REQUIRE(r.ok);
        const json::Parsed got = json::parse(r.json);
        const json::Parsed golden = json::parse(i_read(root + "/datasets/golden/stage_i/" + e.suite + ".json"));
        const json::Value* expected = nullptr;
        for (const json::Value& c : golden.value.find("cases")->items)
            if (c.find("case_id")->text == e.case_id) expected = c.find("expected")->find("outputs");
        REQUIRE(expected != nullptr);
        i_same(*got.value.find("outputs"), *expected, e.file);
    }
}
#endif

// ---- rulings after the builds (I-41 to I-52) ----

TEST_CASE("I-44 minimum variance: a hedged variance a rounding step below 0 reads as 0; below -1e-12 S_00 it is an error") {
    // S_00 - S_he^2 / S_hh = 1 - 1 / (1 - 1e-15), about -1e-15 S_00: rounding by I-44.
    const hg::MinVarResult r = hg::min_variance({{1.0, 1.0}, {1.0, 1.0 - 1e-15}});
    CHECK(r.variance_after == 0.0);
    CHECK(r.effectiveness == 1.0);
    CHECK(i_error([] { hg::min_variance({{1.0, 1.0}, {1.0, 1.0 - 1e-9}}); }) == "E_NOT_POSITIVE_DEFINITE");
}

TEST_CASE("I-41 Greek instruments have fixed key sets; I-49 lot counts above 2^52") {
    const std::string head =
        R"({"spot":100,"rate":0.03,"dividend_yield":0.01,"volatility":0.25,"targets":["DELTA"],"portfolio":[)";
    const std::string book = R"({"instrument":"CALL","strike":100,"expiry_years":0.5,"quantity":-10}],"hedges":[)";
    CHECK(i_code(i_case("hedge.greeks.neutralise", head + book + R"({"instrument":"UNDERLYING"}]})")) == "ok");
    CHECK(i_code(i_case("hedge.greeks.neutralise", head + book + R"({"instrument":"UNDERLYING","quantity":1}]})")) ==
          "E_INPUT");
    CHECK(i_code(i_case("hedge.greeks.neutralise", head + book + R"({"instrument":"UNDERLYING","note":1}]})")) ==
          "E_INPUT");
    CHECK(i_code(i_case("hedge.greeks.neutralise",
                        head + R"({"instrument":"CALL","strike":100,"expiry_years":0.5}],"hedges":[{"instrument":"UNDERLYING"}]})")) ==
          "E_INPUT");  // a portfolio position without quantity
    CHECK(i_code(i_case("hedge.greeks.neutralise",
                        R"({"spot":100,"rate":0.03,"dividend_yield":0.01,"volatility":0.25,"targets":["THETA"],"portfolio":[)" + book +
                            R"({"instrument":"UNDERLYING"}]})")) == "E_SCHEMA");  // I-42
    hg::IntegerProblem p;
    p.a = {{1.0}};
    p.b = {-1e16};
    p.weights = {1.0};
    p.lot_sizes = {1.0};
    CHECK(i_error([&] { hg::solve_integer(p); }) == "E_LIMIT");
    p.b = {-1e15};
    CHECK(i_error([&] { hg::solve_integer(p); }) == "ok");
}

// ---- R6 wave 3 ----

namespace {
std::string r6_code(auto&& f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "ok";
}
struct CapGuard {  // restores the ruled caps even when a CHECK throws
    explicit CapGuard(long long cap) { hg::detail::effort_cap_override = cap; }
    ~CapGuard() { hg::detail::effort_cap_override = 0; }
};
}  // namespace

TEST_CASE("R6-6.1: a planted cap of 1 makes the QP and integer searches return E_NO_CONVERGENCE", "[r6]") {
    // min (x1 - 2)^2 + (x2 - 2)^2 with x <= 1: both bounds bind, so the active set needs two steps.
    hg::QpProblem qp;
    qp.a = {{1, 0}, {0, 1}};
    qp.b = {-2, -2};
    qp.weights = {1, 1};
    qp.upper = std::vector<hg::Bound>{1.0, 1.0};
    const hg::QpResult ok = hg::solve_qp(qp);
    CHECK(ok.x[0] == 1.0);  // hand value: the bound
    CHECK(ok.x[1] == 1.0);
    hg::IntegerProblem ip;
    ip.a = {{1, 0}, {0, 1}};
    ip.b = {-2.4, 1.6};
    ip.weights = {1, 1};
    ip.lot_sizes = {1, 1};
    const hg::IntegerResult lots = hg::solve_integer(ip);
    CHECK(lots.lots == std::vector<long long>{2, -2});  // hand value: nearest integers to 2.4 and -1.6
    {
        const CapGuard cap(1);
        CHECK(r6_code([&] { hg::solve_qp(qp); }) == "E_NO_CONVERGENCE");
        CHECK(r6_code([&] { hg::solve_integer(ip); }) == "E_NO_CONVERGENCE");
    }
    CHECK(r6_code([&] { hg::solve_qp(qp); }) == "ok");
}

TEST_CASE("R6-6.2: a regular problem in mixed units is not E_SINGULAR (hand-built, scale 1e9)", "[r6]") {
    // Two instruments, one priced in units 1e9 larger: H = diag(1e18, 1) unscaled (ratio 1e-18), identity scaled.
    hg::QpProblem qp;
    qp.a = {{1e9, 0}, {0, 1}};
    qp.b = {-1e9, -3};
    qp.weights = {1, 1};
    const hg::QpResult r = hg::solve_qp(qp);
    CHECK(std::fabs(r.x[0] - 1.0) <= 1e-12);  // hand value: x = (1, 3)
    CHECK(std::fabs(r.x[1] - 3.0) <= 1e-12);
    CHECK(r.rank == 2);
}

TEST_CASE("R6-11.7: min variance codes a negative pivot E_NOT_POSITIVE_DEFINITE and a dependent pair E_SINGULAR", "[r6]") {
    CHECK(r6_code([] { hg::min_variance({{1, 0.1, 0.1}, {0.1, 1, 2}, {0.1, 2, 1}}); }) == "E_NOT_POSITIVE_DEFINITE");
    CHECK(r6_code([] { hg::min_variance({{1, 0.1, 0.1}, {0.1, 1, 1}, {0.1, 1, 1}}); }) == "E_SINGULAR");
    // Hand value: one hedge, h = -S_he / S_hh = -0.5 / 2.
    CHECK(std::fabs(hg::min_variance({{1, 0.5}, {0.5, 2}}).hedge[0] + 0.25) <= 1e-15);
}

TEST_CASE("R6-11.20: use case 6 with the underlying alone hedges delta to the nearest lot (hand value)", "[r6]") {
    const std::string j = cli::run_case(
        R"({"schema_version":"1.0","case_id":"u","operation":"usecase.option_hedge_lots","inputs":{"spot":100,"rate":0,"dividend_yield":0,"volatility":0.2,)"
        R"("portfolio":[{"instrument":"UNDERLYING","quantity":-237}],"hedges":[{"instrument":"UNDERLYING","lot_size":100,"half_spread":0.01}],)"
        R"("targets":["DELTA"],"max_lots":10}})")
                              .json;
    INFO(j);
    // Book delta -237; lots of 100: the best is 2 lots (residual -37), hedge cost 2 * 100 * 0.01 = 2.
    CHECK(j.find(R"("lots":[2])") != std::string::npos);
    CHECK(j.find(R"("hedge_cost":2)") != std::string::npos);
    CHECK(j.find(R"("greeks_after":{"delta":-37)") != std::string::npos);
}
