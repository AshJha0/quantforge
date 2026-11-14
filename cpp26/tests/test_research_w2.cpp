// Stage J wave 2 property tests (program/STAGE_J_HANDOVER.md "WAVE 2 READY", "Property tests"), own data.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace rs = quantforge::research;
using Vec = std::vector<double>;
using Mat = std::vector<Vec>;

namespace {

// A random symmetric positive definite matrix A A' + 0.01 I.
Mat random_spd(std::size_t n, std::mt19937_64& g) {
    std::normal_distribution<double> z(0, 0.1);
    Mat a(n, Vec(n));
    for (auto& r : a)
        for (double& v : r) v = z(g);
    Mat s(n, Vec(n, 0.0));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j) {
            for (std::size_t k = 0; k < n; ++k) s[i][j] += a[i][k] * a[j][k];
            if (i == j) s[i][j] += 0.01;
        }
    return s;
}

Vec mul(const Mat& a, const Vec& x) {
    Vec y(a.size(), 0.0);
    for (std::size_t i = 0; i < a.size(); ++i)
        for (std::size_t j = 0; j < x.size(); ++j) y[i] += a[i][j] * x[j];
    return y;
}

Vec solve(Mat a, Vec b) {  // Gaussian elimination with partial pivoting, test use only
    const std::size_t n = b.size();
    for (std::size_t c = 0; c < n; ++c) {
        std::size_t p = c;
        for (std::size_t r = c + 1; r < n; ++r)
            if (std::fabs(a[r][c]) > std::fabs(a[p][c])) p = r;
        std::swap(a[c], a[p]);
        std::swap(b[c], b[p]);
        for (std::size_t r = c + 1; r < n; ++r) {
            const double f = a[r][c] / a[c][c];
            for (std::size_t k = c; k < n; ++k) a[r][k] -= f * a[c][k];
            b[r] -= f * b[c];
        }
    }
    for (std::size_t i = n; i-- > 0;) {
        for (std::size_t k = i + 1; k < n; ++k) b[i] -= a[i][k] * b[k];
        b[i] /= a[i][i];
    }
    return b;
}

Mat inverse(const Mat& a) {
    const std::size_t n = a.size();
    Mat inv(n, Vec(n));
    for (std::size_t j = 0; j < n; ++j) {
        Vec e(n, 0.0);
        e[j] = 1;
        const Vec c = solve(a, e);
        for (std::size_t i = 0; i < n; ++i) inv[i][j] = c[i];
    }
    return inv;
}

}  // namespace

TEST_CASE("mean-variance: KKT residual, closed form with wide bounds, loosening a binding bound") {
    std::mt19937_64 g(20261114);
    std::normal_distribution<double> z(0.05, 0.05);
    for (int trial = 0; trial < 25; ++trial) {
        const std::size_t n = 2 + trial % 6;
        const Mat s = random_spd(n, g);
        Vec mu(n);
        for (double& v : mu) v = z(g);
        const double gamma = 3.0;
        const rs::MeanVariance r = rs::mean_variance(mu, s, gamma, {}, {});
        const Vec sw = mul(s, r.weights);
        // nu from the free assets (at least one is free because the budget is 1 with bounds [0, 1]).
        double nu = 0;
        int nf = 0;
        for (std::size_t i = 0; i < n; ++i)
            if (r.at_bound[i] == 0) nu += mu[i] - gamma * sw[i], ++nf;
        if (nf > 0) nu /= nf;
        double sum = 0;
        for (std::size_t i = 0; i < n; ++i) {
            sum += r.weights[i];
            const double gi = mu[i] - gamma * sw[i] - nu;
            if (r.at_bound[i] == 0) CHECK(std::fabs(gi) < 1e-9);
            if (r.at_bound[i] == -1) CHECK(gi <= 1e-9);
            if (r.at_bound[i] == 1) CHECK(gi >= -1e-9);
        }
        CHECK(std::fabs(sum - 1) < 1e-12);
        // Loosening every binding upper bound never lowers the objective.
        Vec up(n, 1.0);
        for (std::size_t i = 0; i < n; ++i)
            if (r.at_bound[i] == 1) up[i] = 2.0;
        const rs::MeanVariance r2 = rs::mean_variance(mu, s, gamma, Vec(n, 0.0), up);
        CHECK(r2.objective >= r.objective - 1e-12);
        // Wide bounds: w = Sigma^-1 (mu - nu 1) / gamma.
        const rs::MeanVariance wide = rs::mean_variance(mu, s, gamma, Vec(n, -1e6), Vec(n, 1e6));
        const Mat inv = inverse(s);
        const Vec a = mul(inv, mu), c = mul(inv, Vec(n, 1.0));
        double sa = 0, sc = 0;
        for (std::size_t i = 0; i < n; ++i) sa += a[i], sc += c[i];
        const double nu_w = (sa - gamma) / sc;
        for (std::size_t i = 0; i < n; ++i) CHECK(std::fabs(wide.weights[i] - (a[i] - nu_w * c[i]) / gamma) < 1e-8);
    }
    const rs::MeanVariance one = rs::mean_variance({0.1}, {{0.04}}, 2.0, {}, {});
    CHECK(one.weights[0] == 1.0);
    CHECK(one.at_bound[0] == 1);
}

TEST_CASE("risk parity: shares equal budgets, scale invariance; Euler sums and homogeneity") {
    std::mt19937_64 g(7);
    std::uniform_real_distribution<double> u(0.1, 1.0);
    for (int trial = 0; trial < 25; ++trial) {
        const std::size_t n = 1 + trial % 8;
        const Mat s = random_spd(n, g);
        Vec b(n);
        double sb = 0;
        for (double& v : b) sb += v = u(g);
        for (double& v : b) v /= sb;
        double check = 0;
        for (const double v : b) check += v;
        if (std::fabs(check - 1) > 1e-12) continue;
        const rs::RiskParity r = rs::risk_parity(s, b);
        double csum = 0;
        for (std::size_t i = 0; i < n; ++i) {
            CHECK(std::fabs(r.contributions[i] / r.volatility - b[i] / check) < 1e-10);
            csum += r.contributions[i];
        }
        CHECK(std::fabs(csum - r.volatility) < 1e-10 * r.volatility);
        Mat s5 = s;
        for (auto& row : s5)
            for (double& v : row) v *= 5;
        const rs::RiskParity r5 = rs::risk_parity(s5, b);
        for (std::size_t i = 0; i < n; ++i) CHECK(std::fabs(r5.weights[i] - r.weights[i]) < 1e-10);

        Vec w(n);
        for (double& v : w) v = u(g) - 0.4;
        const rs::Euler e = rs::euler(w, s);
        double es = 0;
        for (const double c : e.contributions) es += c;
        CHECK(std::fabs(es - e.volatility) <= 1e-10 * e.volatility);
        Vec w3 = w;
        for (double& v : w3) v *= 3;
        const rs::Euler e3 = rs::euler(w3, s);
        for (std::size_t i = 0; i < n; ++i)
            CHECK(std::fabs(e3.contributions[i] - 3 * e.contributions[i]) <= 1e-12 + 1e-10 * std::fabs(e.contributions[i]));
    }
}

TEST_CASE("Ledoit-Wolf: 0 <= delta <= 1, column shift invariance") {
    std::mt19937_64 g(11);
    std::normal_distribution<double> z(0, 0.02);
    for (int trial = 0; trial < 20; ++trial) {
        const std::size_t t = 3 + trial * 2, n = 1 + trial % 6;
        Mat x(t, Vec(n));
        for (auto& r : x)
            for (double& v : r) v = z(g);
        const rs::LedoitWolf a = rs::ledoit_wolf(x);
        CHECK(a.shrinkage >= 0);
        CHECK(a.shrinkage <= 1);
        for (auto& r : x) r[0] += 0.5;
        const rs::LedoitWolf b = rs::ledoit_wolf(x);
        CHECK(std::fabs(a.shrinkage - b.shrinkage) < 1e-9);
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(a.covariance[i][j] - b.covariance[i][j]) < 1e-12);
    }
}

TEST_CASE("Black-Litterman: update form equals precision form; large Omega returns the prior") {
    std::mt19937_64 g(13);
    std::normal_distribution<double> z(0, 0.05);
    for (int trial = 0; trial < 20; ++trial) {
        const std::size_t n = 1 + trial % 5, k = 1 + trial % 3;
        const Mat s = random_spd(n, g), om = random_spd(k, g);
        Vec pi(n), q(k);
        for (double& v : pi) v = z(g);
        for (double& v : q) v = z(g);
        Mat p(k, Vec(n));
        for (auto& r : p)
            for (double& v : r) v = z(g) * 10;
        const double tau = 0.05;
        const rs::BlackLitterman r = rs::black_litterman(s, pi, p, q, om, tau);
        // Precision form: [(tau S)^-1 + P' Om^-1 P]^-1 [(tau S)^-1 pi + P' Om^-1 q].
        Mat ts = s;
        for (auto& row : ts)
            for (double& v : row) v *= tau;
        const Mat tsi = inverse(ts), omi = inverse(om);
        Mat h = tsi;
        Vec rhs = mul(tsi, pi);
        const Vec omq = mul(omi, q);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j)
                for (std::size_t a = 0; a < k; ++a)
                    for (std::size_t c = 0; c < k; ++c) h[i][j] += p[a][i] * omi[a][c] * p[c][j];
            for (std::size_t a = 0; a < k; ++a) rhs[i] += p[a][i] * omq[a];
        }
        const Mat hi = inverse(h);
        const Vec mu = mul(hi, rhs);
        for (std::size_t i = 0; i < n; ++i) {
            CHECK(std::fabs(mu[i] - r.posterior_returns[i]) < 1e-10);
            for (std::size_t j = 0; j < n; ++j) CHECK(std::fabs(hi[i][j] - r.posterior_covariance[i][j]) < 1e-10);
        }
        Mat big = om;
        for (auto& row : big)
            for (double& v : row) v *= 1e14;
        const rs::BlackLitterman pr = rs::black_litterman(s, pi, p, q, big, tau);
        for (std::size_t i = 0; i < n; ++i) CHECK(std::fabs(pr.posterior_returns[i] - pi[i]) < 1e-10);
    }
}

TEST_CASE("Z2: no exceptions gives 1, scale invariance, higher ES raises Z2") {
    const Vec l{1, 3, 0.5, 4, 2.5}, v{2, 2, 2, 2, 2}, e{2.5, 2.6, 2.4, 2.5, 3};
    CHECK(rs::es_z2({0.1, 0.2}, {1, 1}, {2, 2}, 0.1).z2 == 1.0);
    CHECK(rs::es_z2({0.1, 0.2}, {1, 1}, {2, 2}, 0.1).exceptions == 0);
    const rs::EsZ2 a = rs::es_z2(l, v, e, 0.2);
    Vec l7 = l, v7 = v, e7 = e, eh = e;
    for (double& x : l7) x *= 7;
    for (double& x : v7) x *= 7;
    for (double& x : e7) x *= 7;
    for (double& x : eh) x *= 1.5;
    CHECK(std::fabs(rs::es_z2(l7, v7, e7, 0.2).z2 - a.z2) < 1e-14);
    CHECK(rs::es_z2(l, v, eh, 0.2).z2 > a.z2);
    CHECK(a.exceptions == 3);
}

TEST_CASE("Baum-Welch: monotone likelihood, K = 1, bit reproducible, permutation equivariant") {
    std::mt19937_64 g(17);
    std::normal_distribution<double> lo(-1, 0.5), hi(1.5, 0.8);
    Vec y;
    bool state = false;
    std::uniform_real_distribution<double> u(0, 1);
    for (int t = 0; t < 300; ++t) {
        if (u(g) < 0.05) state = !state;
        y.push_back(state ? hi(g) : lo(g));
    }
    const rs::BaumWelch r = rs::baum_welch(y, {0.6, 0.4}, {{0.9, 0.1}, {0.2, 0.8}}, {-0.5, 1.0}, {1.0, 1.0}, 1e-10, 500);
    for (std::size_t i = 1; i < r.trace.size(); ++i)
        CHECK(r.trace[i] - r.trace[i - 1] >= -1e-9 * std::fabs(r.trace[i - 1]));
    const rs::BaumWelch r2 = rs::baum_welch(y, {0.6, 0.4}, {{0.9, 0.1}, {0.2, 0.8}}, {-0.5, 1.0}, {1.0, 1.0}, 1e-10, 500);
    CHECK(std::memcmp(&r.log_likelihood, &r2.log_likelihood, sizeof(double)) == 0);
    for (std::size_t i = 0; i < 2; ++i) {
        CHECK(std::memcmp(&r.means[i], &r2.means[i], sizeof(double)) == 0);
        CHECK(std::memcmp(&r.sds[i], &r2.sds[i], sizeof(double)) == 0);
        CHECK(std::memcmp(r.transition[i].data(), r2.transition[i].data(), 2 * sizeof(double)) == 0);
    }
    const rs::BaumWelch p = rs::baum_welch(y, {0.4, 0.6}, {{0.8, 0.2}, {0.1, 0.9}}, {1.0, -0.5}, {1.0, 1.0}, 1e-10, 500);
    CHECK(p.iterations == r.iterations);
    for (std::size_t i = 0; i < 2; ++i) {
        CHECK(std::fabs(p.means[1 - i] - r.means[i]) < 1e-9);
        CHECK(std::fabs(p.sds[1 - i] - r.sds[i]) < 1e-9);
        for (std::size_t j = 0; j < 2; ++j) CHECK(std::fabs(p.transition[1 - i][1 - j] - r.transition[i][j]) < 1e-9);
    }
    const Vec z{0.5, -1.0, 2.0, 0.25, 1.5};
    const rs::BaumWelch one = rs::baum_welch(z, {1.0}, {{1.0}}, {3.0}, {0.2}, 1e-10, 100);
    CHECK(one.iterations == 2);
    CHECK(one.converged);
    double m = 0, v = 0;
    for (const double x : z) m += x;
    m /= 5;
    for (const double x : z) v += (x - m) * (x - m);
    CHECK(std::fabs(one.means[0] - m) < 1e-14);
    CHECK(std::fabs(one.sds[0] - std::sqrt(v / 5)) < 1e-14);
    CHECK_THROWS_AS(rs::baum_welch({1, 1, 1}, {0.5, 0.5}, {{0.5, 0.5}, {0.5, 0.5}}, {0, 2}, {1, 1}, 1e-10, 10),
                    quantforge::Error);
}
