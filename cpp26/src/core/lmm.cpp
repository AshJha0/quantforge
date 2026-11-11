// Stage G wave 3b/3c: LIBOR market model closed forms and the simulated acceptance scheme. See lmm.hpp.
#include "quantforge/core/lmm.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::lmm {

namespace {
struct GaussLegendre {
    std::vector<double> x, w;
};
GaussLegendre make_gl(int n) {
    GaussLegendre g;
    g.x.resize(static_cast<std::size_t>(n));
    g.w.resize(static_cast<std::size_t>(n));
    const double pi = 3.14159265358979323846;
    for (int i = 0; i < n; ++i) {
        double z = std::cos(pi * (i + 0.75) / (n + 0.5)), dp = 1.0;
        for (int it = 0; it < 100; ++it) {
            double p0 = 1.0, p1 = z;
            for (int k = 2; k <= n; ++k) {
                const double p2 = ((2 * k - 1) * z * p1 - (k - 1) * p0) / k;
                p0 = p1;
                p1 = p2;
            }
            dp = n * (z * p1 - p0) / (z * z - 1);
            const double dz = p1 / dp;
            z -= dz;
            if (std::fabs(dz) < 1e-16) break;
        }
        g.x[static_cast<std::size_t>(i)] = z;
        g.w[static_cast<std::size_t>(i)] = 2 / ((1 - z * z) * dp * dp);
    }
    return g;
}
const GaussLegendre& gl20() {
    static const GaussLegendre g = make_gl(20);  // function-local static: no static-init order issue
    return g;
}
}  // namespace

double vol_at(const Abcd& v, double T, double t) {
    const double s = T - t;
    return (v.a + v.b * s) * std::exp(-v.c * s) + v.d;
}

double covariance(const Abcd& v, double Ti, double Tj, double u) {
    if (!(u > 0)) return 0.0;
    const GaussLegendre& g = gl20();
    const int pieces = std::max(4, static_cast<int>(std::ceil(u * 2)));
    const double h = u / pieces, half = h / 2;
    double sum = 0.0;
    for (int k = 0; k < pieces; ++k) {
        const double mid = (k + 0.5) * h;
        double part = 0.0;
        for (std::size_t i = 0; i < g.x.size(); ++i) {
            const double t = mid + half * g.x[i];
            part += g.w[i] * vol_at(v, Ti, t) * vol_at(v, Tj, t);
        }
        sum += part * half;
    }
    return sum;
}

double black(double F, double K, double v, bool call) {
    const double d1 = (std::log(F / K) + v * v / 2) / v, d2 = d1 - v;
    return call ? F * normal_cdf(d1) - K * normal_cdf(d2) : K * normal_cdf(-d2) - F * normal_cdf(-d1);
}

double forward(const shortrate::Curve& c, double s, double t) {
    const double F = (c.df(s) / c.df(t) - 1) / (t - s);
    if (!(F > 0)) throw Error("E_DOMAIN", "a forward rate is not positive (lognormal LMM)", "curve");
    return F;
}

CapFloor capfloor(const shortrate::Curve& c, const Abcd& v, const std::vector<double>& t, double K, bool cap) {
    CapFloor r{0.0, {}, {}, {}};
    for (std::size_t i = 1; i < t.size(); ++i) {
        const double F = forward(c, t[i - 1], t[i]);
        const double sd = std::sqrt(covariance(v, t[i - 1], t[i - 1], t[i - 1]));
        const double x = (t[i] - t[i - 1]) * c.df(t[i]) * black(F, K, sd, cap);
        r.caplets.push_back(x);
        r.forwards.push_back(F);
        r.black_vols.push_back(sd / std::sqrt(t[i - 1]));
        r.price += x;
    }
    return r;
}

Swaption swaption_rebonato(const shortrate::Curve& c, const Abcd& v, double beta, double T0, const std::vector<double>& pay,
                           double K, bool payer) {
    const std::size_t n = pay.size();
    std::vector<double> F(n), w(n), fix(n);
    double A = 0.0, prev = T0;
    for (std::size_t i = 0; i < n; ++i) {
        fix[i] = prev;
        F[i] = forward(c, prev, pay[i]);
        w[i] = (pay[i] - prev) * c.df(pay[i]);
        A += w[i];
        prev = pay[i];
    }
    double S = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        w[i] /= A;
        S += w[i] * F[i];
    }
    double var = 0.0;
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j)
            var += w[i] * w[j] * F[i] * F[j] * std::exp(-beta * std::fabs(fix[i] - fix[j])) * covariance(v, fix[i], fix[j], T0);
    const double vol = std::sqrt(var) / S;
    return {A * black(S, K, vol, payer), S, A, vol / std::sqrt(T0)};
}

McCaplets simulate_caplets(const shortrate::Curve& c, const Abcd& v, double beta, const std::vector<double>& grid, double K,
                           long long paths, long long steps_per_year, std::uint64_t seed) {
    // Forwards F_k on [grid[k], grid[k+1]], k = 0..N-1, fixing at grid[k]; F_0 fixes at 0 and is not simulated.
    const std::size_t N = grid.size() - 1;
    std::vector<double> F0(N), tau(N);
    for (std::size_t k = 0; k < N; ++k) {
        F0[k] = forward(c, grid[k], grid[k + 1]);
        tau[k] = grid[k + 1] - grid[k];
    }
    // Cholesky of rho_ij = exp(-beta |T_i - T_j|) on fixing times.
    std::vector<std::vector<double>> L(N, std::vector<double>(N, 0.0));
    for (std::size_t i = 0; i < N; ++i)
        for (std::size_t j = 0; j <= i; ++j) {
            double s = std::exp(-beta * std::fabs(grid[i] - grid[j]));
            for (std::size_t k = 0; k < j; ++k) s -= L[i][k] * L[j][k];
            L[i][j] = i == j ? std::sqrt(std::max(s, 0.0)) : s / L[j][j];
        }
    std::vector<double> rho_flat(N * N);
    for (std::size_t i = 0; i < N; ++i)
        for (std::size_t j = 0; j < N; ++j) rho_flat[i * N + j] = std::exp(-beta * std::fabs(grid[i] - grid[j]));
    // Step boundaries: each interval [grid[k], grid[k+1]] in ceil(steps_per_year tau) equal steps, up to grid[N-1].
    std::vector<double> tb{0.0};
    for (std::size_t k = 0; k + 1 < N; ++k) {
        const long long m = std::max(1LL, static_cast<long long>(std::ceil(static_cast<double>(steps_per_year) * tau[k])));
        for (long long j = 1; j <= m; ++j) tb.push_back(j == m ? grid[k + 1] : grid[k] + tau[k] * static_cast<double>(j) / static_cast<double>(m));
    }
    const double PN = c.df(grid[N]);
    std::vector<double> sum(N, 0.0), sum2(N, 0.0), payoff(N, 0.0), value(N, 0.0);
    Xoshiro256 rng(seed, 0);
    std::vector<double> lnF(N), z(N), dw(N), sig(N, 0.0), mu0(N, 0.0), lp(N), mu1(N, 0.0);
    const auto drift = [&](std::size_t from, const std::vector<double>& lf, std::vector<double>& mu) {
        for (std::size_t k = from; k < N; ++k) {
            double m = 0.0;
            for (std::size_t j = k + 1; j < N; ++j) {
                const double Fj = std::exp(lf[j]);
                m += rho_flat[k * N + j] * tau[j] * sig[j] * Fj / (1 + tau[j] * Fj);
            }
            mu[k] = -sig[k] * m;
        }
    };
    // At the fixing of F_m (time grid[m]): F_m's payoff is set, and caplet m-1, paid at grid[m], is deflated by
    // 1/P(grid[m], T_N) = prod_(j >= m) (1 + tau_j F_j(grid[m])).
    const auto at_fixing = [&](std::size_t m) {
        payoff[m] = tau[m] * std::max(std::exp(lnF[m]) - K, 0.0);
        double f = 1.0;
        for (std::size_t j = m; j < N; ++j) f *= 1 + tau[j] * std::exp(lnF[j]);
        if (m >= 2) value[m - 1] = payoff[m - 1] * f;
    };
    for (long long p = 0; p < paths; ++p) {
        for (std::size_t k = 0; k < N; ++k) lnF[k] = std::log(F0[k]);
        std::size_t alive = 1;  // F_0 fixed at 0
        for (std::size_t s = 1; s < tb.size(); ++s) {
            const double t0 = tb[s - 1], t1 = tb[s], dt = t1 - t0, tm = 0.5 * (t0 + t1), sq = std::sqrt(dt);
            for (std::size_t k = 0; k < N; ++k) z[k] = rng.next_normal();
            for (std::size_t i = 0; i < N; ++i) {
                double x = 0.0;
                for (std::size_t j = 0; j <= i; ++j) x += L[i][j] * z[j];
                dw[i] = x * sq;
            }
            for (std::size_t k = alive; k < N; ++k) sig[k] = vol_at(v, grid[k], tm);
            drift(alive, lnF, mu0);
            lp = lnF;
            for (std::size_t k = alive; k < N; ++k) lp[k] = lnF[k] + (mu0[k] - sig[k] * sig[k] / 2) * dt + sig[k] * dw[k];
            drift(alive, lp, mu1);
            for (std::size_t k = alive; k < N; ++k)
                lnF[k] += (0.5 * (mu0[k] + mu1[k]) - sig[k] * sig[k] / 2) * dt + sig[k] * dw[k];
            while (alive < N && t1 >= grid[alive]) at_fixing(alive++);
        }
        value[N - 1] = payoff[N - 1];  // paid at T_N: numeraire 1
        for (std::size_t k = 1; k < N; ++k) {
            sum[k] += value[k];
            sum2[k] += value[k] * value[k];
        }
    }
    McCaplets r;
    const double n = static_cast<double>(paths);
    for (std::size_t k = 1; k < N; ++k) {
        const double m = sum[k] / n, var = (sum2[k] - n * m * m) / (n - 1);
        r.price.push_back(PN * m);
        r.se.push_back(PN * std::sqrt(std::max(var, 0.0) / n));
    }
    return r;
}

}  // namespace quantforge::lmm
