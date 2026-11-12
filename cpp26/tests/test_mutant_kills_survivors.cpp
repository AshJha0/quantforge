// Stage G carry-over: unit tests that kill the C++ mutation survivors left in stage F (PR #29 CI report).
// No namespace-scope static objects (static-init order has broken ASan before): helpers are functions only.
#include <catch2/catch_test_macros.hpp>
#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/multicurve.hpp"
#include "quantforge/core/vol_stats.hpp"

using namespace quantforge;

namespace {
std::string g_code_of(auto&& f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "none";
}

// Deterministic GARCH(1,1) series with Student-t innovations of unit variance (LCG, Box-Muller).
std::vector<double> garch_t_series(std::size_t n, double omega, double alpha, double beta, int nu) {
    unsigned long long s = 20261110ULL;
    const auto u = [&] {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        return (double((s >> 11) & ((1ULL << 53) - 1)) + 0.5) / 9007199254740992.0;
    };
    const auto normal = [&] { return std::sqrt(-2 * std::log(u())) * std::cos(6.283185307179586 * u()); };
    std::vector<double> r;
    double v = omega / (1 - alpha - beta);
    for (std::size_t i = 0; i < n; ++i) {
        double chi = 0.0;
        for (int j = 0; j < nu; ++j) {
            const double g = normal();
            chi += g * g;
        }
        const double z = normal() / std::sqrt(chi / nu) * std::sqrt((nu - 2.0) / nu);
        const double x = std::sqrt(v) * z;
        r.push_back(x);
        v = omega + alpha * x * x + beta * v;
    }
    return r;
}

double t_loglik(const std::vector<double>& r, const std::array<double, 4>& p) {
    GarchLaw law;
    law.distribution = GarchDistribution::StudentT;
    law.degrees_of_freedom = p[3];
    return garch_loglik(r, p[0], p[1], p[2], std::nullopt, law).loglik;
}

// Inverse of a 4x4 matrix by Gauss-Jordan with partial pivoting.
std::array<std::array<double, 4>, 4> inverse4(std::array<std::array<double, 4>, 4> a) {
    std::array<std::array<double, 4>, 4> b{};
    for (int i = 0; i < 4; ++i) b[i][i] = 1.0;
    for (int c = 0; c < 4; ++c) {
        int piv = c;
        for (int i = c + 1; i < 4; ++i)
            if (std::fabs(a[i][c]) > std::fabs(a[piv][c])) piv = i;
        std::swap(a[c], a[piv]);
        std::swap(b[c], b[piv]);
        const double d = a[c][c];
        for (int j = 0; j < 4; ++j) a[c][j] /= d, b[c][j] /= d;
        for (int i = 0; i < 4; ++i) {
            if (i == c) continue;
            const double f = a[i][c];
            for (int j = 0; j < 4; ++j) a[i][j] -= f * a[c][j], b[i][j] -= f * b[c][j];
        }
    }
    return b;
}
}  // namespace

// Kills vol_stats.cpp survivors in the Student-t nu derivatives: c1 (digamma(nu / 2)) moves the polished
// optimum off the true maximum in nu; lnn (sign of the last term) changes the observed information.
TEST_CASE("garch estimate student-t: maximum in nu and errors from a finite-difference Hessian") {
    const std::vector<double> r = garch_t_series(1500, 2e-6, 0.08, 0.90, 5);
    const GarchEstimate e = garch_estimate(r, std::nullopt, GarchDistribution::StudentT, false);
    REQUIRE(e.degrees_of_freedom);
    REQUIRE(e.se_degrees_of_freedom);
    const std::array<double, 4> p{e.omega, e.alpha, e.beta, *e.degrees_of_freedom};
    const double f0 = t_loglik(r, p);
    CHECK(std::fabs(f0 - e.loglik) <= 1e-12 * std::fabs(f0));
    // Zero gradient in nu: central difference relative to the curvature scale.
    const double hn = 1e-3 * p[3];
    auto up = p, dn = p;
    up[3] += hn;
    dn[3] -= hn;
    const double fu = t_loglik(r, up), fd = t_loglik(r, dn);
    CHECK(fu <= f0);
    CHECK(fd <= f0);
    const double grad = (fu - fd) / (2 * hn), curv = (fu - 2 * f0 + fd) / (hn * hn);
    CHECK(std::fabs(grad) <= 1e-4 * std::fabs(curv) * p[3]);
    // Observed information by finite differences, inverted: matches the reported standard errors.
    std::array<double, 4> h{};
    for (int i = 0; i < 4; ++i) h[i] = 1e-4 * p[i];
    std::array<std::array<double, 4>, 4> info{};
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            const auto at = [&](double si, double sj) {
                auto q = p;
                q[i] += si * h[i];
                q[j] += sj * h[j];
                return t_loglik(r, q);
            };
            info[i][j] = -(at(1, 1) - at(1, -1) - at(-1, 1) + at(-1, -1)) / (4 * h[i] * h[j]);
        }
    const auto cov = inverse4(info);
    const std::array<double, 4> se{e.se_omega, e.se_alpha, e.se_beta, *e.se_degrees_of_freedom};
    for (int i = 0; i < 4; ++i) {
        INFO("parameter " << i);
        CHECK(std::fabs(se[i] - std::sqrt(cov[i][i])) <= 1e-3 * se[i]);
    }
}

// garch_fit restarts Nelder-Mead until a restart gains at most 1e-12 relative, so its loglik reaches the
// Newton-polished garch_estimate maximum to about 1e-13. Returns of variance near 1 give a negative loglik (a positive
// objective): that kills vol_stats.cpp:209 (gain = fbest + fx never meets the stop rule, and the fit fails).
TEST_CASE("garch fit: restarts reach the polished maximum") {
    for (const double omega : {2e-6, 0.05})
        for (const int nu : {4, 5})
            for (const std::size_t n : {300, 1000, 2000}) {
                const std::vector<double> r = garch_t_series(n, omega, 0.08, 0.90, nu);
                const GarchFit f = garch_fit(r, std::nullopt);
                const GarchEstimate e = garch_estimate(r, std::nullopt, GarchDistribution::Normal, false);
                INFO("omega " << omega << " nu " << nu << " n " << n);
                CHECK(std::fabs(f.loglik - e.loglik) <= 1e-13 * std::fabs(e.loglik));
                CHECK(std::fabs(f.alpha - e.alpha) <= 1e-5 * e.alpha);
                CHECK(std::fabs(f.beta - e.beta) <= 1e-5 * e.beta);
            }
}

// multicurve.cpp solve_split loop (`j < n` to `j <= n`, second-reviewer audit): the mutant writes w[n] and c[n] out of
// bounds. The exact split solve runs on a fit with one outlier; with _GLIBCXX_ASSERTIONS (test builds) or ASan the
// out-of-range write aborts, so the mutant is killed.
TEST_CASE("robust_fit split solve with an outlier stays in bounds") {
    const std::vector<double> m{0.5, 1, 2, 3, 5, 7, 10, 20};
    std::vector<double> y;
    for (const double x : m) {
        const double u = x / 2.0, e = -std::expm1(-u) / u;
        y.push_back(0.04 - 0.01 * e + 0.005 * (e - std::exp(-u)));
    }
    y[3] += 0.01;
    const auto r = robust_fit(m, y, 2.0, 5e-4);
    REQUIRE(r.outliers.size() == 1);
    CHECK(r.outliers[0] == 3);
}
