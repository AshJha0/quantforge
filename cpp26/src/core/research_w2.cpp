// Stage J wave 2 (rulings J-W2-1 to J-W2-15): mean-variance, risk parity, Euler contributions
// (07-portfolio/optimisation.md), Ledoit-Wolf and Black-Litterman (07-portfolio/estimation.md),
// the Acerbi-Szekely Z2 statistic (06-risk/es-backtest.md) and Baum-Welch (11-research/baum-welch.md).
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::research {
namespace {

using Vec = std::vector<double>;
using Mat = std::vector<std::vector<double>>;

[[noreturn]] void input(const std::string& why, const std::string& field = {}) { throw Error("E_INPUT", why, field); }
[[noreturn]] void domain(const std::string& why, const std::string& field = {}) { throw Error("E_DOMAIN", why, field); }

double pz(double x) { return x + 0.0; }  // ruling F-3
Vec pz(Vec x) {
    for (double& v : x) v = pz(v);
    return x;
}
Mat pz(Mat m) {
    for (Vec& r : m) r = pz(std::move(r));
    return m;
}

void square(const Mat& s, std::size_t n, const char* field) {
    if (s.size() != n) input(std::string(field) + " must be N x N", field);
    for (const Vec& r : s)
        if (r.size() != n) input(std::string(field) + " must be N x N", field);
}

// J-W2-3: symmetric within 1e-12 max|S|; the result is built from the upper triangle.
Mat symmetric(const Mat& s, const char* field) {
    const std::size_t n = s.size();
    double big = 0;
    for (const Vec& r : s)
        for (const double v : r) big = std::max(big, std::fabs(v));
    Mat u(n, Vec(n));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = i; j < n; ++j) {
            if (std::fabs(s[i][j] - s[j][i]) > 1e-12 * big) domain(std::string(field) + " is not symmetric", field);
            u[i][j] = u[j][i] = s[i][j];
        }
    return u;
}

// Lower Cholesky factor; any pivot <= 0 is E_DOMAIN (J-W2-3).
Mat cholesky(const Mat& a, const char* field) {
    const std::size_t n = a.size();
    Mat l(n, Vec(n, 0.0));
    for (std::size_t j = 0; j < n; ++j) {
        double d = a[j][j];
        for (std::size_t k = 0; k < j; ++k) d -= l[j][k] * l[j][k];
        if (!(d > 0)) domain(std::string(field) + " is not positive definite", field);
        l[j][j] = std::sqrt(d);
        for (std::size_t i = j + 1; i < n; ++i) {
            double s = a[i][j];
            for (std::size_t k = 0; k < j; ++k) s -= l[i][k] * l[j][k];
            l[i][j] = s / l[j][j];
        }
    }
    return l;
}

Vec chol_solve(const Mat& l, Vec b) {
    const std::size_t n = l.size();
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t k = 0; k < i; ++k) b[i] -= l[i][k] * b[k];
        b[i] /= l[i][i];
    }
    for (std::size_t i = n; i-- > 0;) {
        for (std::size_t k = i + 1; k < n; ++k) b[i] -= l[k][i] * b[k];
        b[i] /= l[i][i];
    }
    return b;
}

Vec mul(const Mat& a, const Vec& x) {
    Vec y(a.size(), 0.0);
    for (std::size_t i = 0; i < a.size(); ++i)
        for (std::size_t j = 0; j < x.size(); ++j) y[i] += a[i][j] * x[j];
    return y;
}

double dot(const Vec& a, const Vec& b) {
    double s = 0;
    for (std::size_t i = 0; i < a.size(); ++i) s += a[i] * b[i];
    return s;
}

double norm(const Vec& a) { return std::sqrt(dot(a, a)); }

}  // namespace

// ---- mean-variance: primal active set [NW06, 16.5] from a feasible start ----
MeanVariance mean_variance(const Vec& mu, const Mat& sigma_in, double gamma, Vec lower, Vec upper) {
    const std::size_t n = mu.size();
    if (n < 1) input("expected_returns is empty", "expected_returns");
    square(sigma_in, n, "covariance");
    if (lower.empty()) lower.assign(n, 0.0);
    if (upper.empty()) upper.assign(n, 1.0);
    if (lower.size() != n || upper.size() != n) input("bounds must have length N", "lower");
    if (!(gamma > 0)) domain("risk_aversion must be positive", "risk_aversion");
    double sl = 0, su = 0;
    for (std::size_t i = 0; i < n; ++i) {
        if (lower[i] > upper[i]) domain("lower above upper", "lower");
        sl += lower[i];
        su += upper[i];
    }
    if (sl > 1) domain("lower bounds sum above 1", "lower");
    if (su < 1) domain("upper bounds sum below 1", "upper");
    const Mat sigma = symmetric(sigma_in, "covariance");
    (void)cholesky(sigma, "covariance");

    // Feasible start: lower bounds, then fill in index order; the asset where the fill stops stays free.
    Vec w = lower;
    std::vector<int> state(n, -1);  // -1 at lower, +1 at upper, 0 free (working set = nonzero)
    double rest = 1 - sl;
    std::size_t free_one = n - 1;
    for (std::size_t i = 0; i < n; ++i) {
        const double room = upper[i] - lower[i];
        if (rest > room) {
            w[i] = upper[i];
            state[i] = 1;
            rest -= room;
        } else {
            w[i] = lower[i] + rest;
            free_one = i;
            break;
        }
    }
    state[free_one] = 0;

    const std::size_t max_iter = 50 * n + 100;
    bool solved = false;
    double nu = 0;
    for (std::size_t iter = 0; iter < max_iter && !solved; ++iter) {
        std::vector<std::size_t> f;
        for (std::size_t i = 0; i < n; ++i)
            if (state[i] == 0) f.push_back(i);
        const std::size_t m = f.size();
        Mat sff(m, Vec(m));
        Vec rhs(m), ones(m, 1.0);
        double fixed = 0;
        for (std::size_t i = 0; i < n; ++i)
            if (state[i] != 0) fixed += w[i];
        for (std::size_t a = 0; a < m; ++a) {
            for (std::size_t b = 0; b < m; ++b) sff[a][b] = sigma[f[a]][f[b]];
            double cross = 0;
            for (std::size_t j = 0; j < n; ++j)
                if (state[j] != 0) cross += sigma[f[a]][j] * w[j];
            rhs[a] = (mu[f[a]] - gamma * cross) / gamma;
        }
        const Mat l = cholesky(sff, "covariance");
        const Vec av = chol_solve(l, rhs);
        Vec cv = chol_solve(l, ones);
        for (double& v : cv) v /= gamma;
        double sa = 0, sc = 0;
        for (std::size_t a = 0; a < m; ++a) {
            sa += av[a];
            sc += cv[a];
        }
        nu = (sa - (1 - fixed)) / sc;
        Vec target(m), p(m);
        for (std::size_t a = 0; a < m; ++a) {
            target[a] = av[a] - nu * cv[a];
            p[a] = target[a] - w[f[a]];
        }
        double step = 1;
        std::size_t block = n;
        int block_side = 0;
        for (std::size_t a = 0; a < m; ++a) {
            const std::size_t i = f[a];
            if (p[a] < 0 && target[a] < lower[i]) {
                const double t = (lower[i] - w[i]) / p[a];
                if (t < step) step = t, block = i, block_side = -1;
            } else if (p[a] > 0 && target[a] > upper[i]) {
                const double t = (upper[i] - w[i]) / p[a];
                if (t < step) step = t, block = i, block_side = 1;
            }
        }
        if (block == n) {
            for (std::size_t a = 0; a < m; ++a) w[f[a]] = target[a];
            // Multipliers of the working set: g_i = mu_i - gamma (Sigma w)_i - nu.
            const Vec sw = mul(sigma, w);
            std::size_t worst = n;
            double worst_v = 0;
            for (std::size_t i = 0; i < n; ++i) {
                if (state[i] == 0) continue;
                const double g = mu[i] - gamma * sw[i] - nu;
                const double viol = state[i] < 0 ? g : -g;  // positive = wrong sign
                if (viol > worst_v) worst_v = viol, worst = i;
            }
            if (worst == n) solved = true;
            else state[worst] = 0;
        } else {
            for (std::size_t a = 0; a < m; ++a) w[f[a]] += step * p[a];
            state[block] = block_side;
        }
        for (std::size_t i = 0; i < n; ++i)
            if (state[i] != 0) w[i] = state[i] < 0 ? lower[i] : upper[i];
    }
    if (!solved) domain("the active-set iteration did not finish", "covariance");
    (void)nu;
    MeanVariance out;
    const Vec sw = mul(sigma, w);
    const double var = dot(w, sw);
    out.weights = pz(w);
    out.expected_return = pz(dot(mu, w));
    out.volatility = std::sqrt(var);
    out.objective = pz(dot(mu, w) - gamma / 2 * var);
    for (std::size_t i = 0; i < n; ++i)
        out.at_bound.push_back(w[i] == lower[i] ? -1 : w[i] == upper[i] ? 1 : 0);
    return out;
}

// ---- risk parity: Newton on Sigma y = b / y [Spinu13] ----
RiskParity risk_parity(const Mat& sigma_in, Vec b) {
    const std::size_t n = sigma_in.size();
    if (n < 1) input("covariance is empty", "covariance");
    square(sigma_in, n, "covariance");
    if (b.empty()) b.assign(n, 1.0 / static_cast<double>(n));
    if (b.size() != n) input("budgets must have length N", "budgets");
    double sb = 0;
    for (const double v : b) {
        if (!(v > 0)) domain("budgets must be positive", "budgets");
        sb += v;
    }
    if (std::fabs(sb - 1) > 1e-12) domain("budgets must sum to 1", "budgets");
    const Mat sigma = symmetric(sigma_in, "covariance");
    (void)cholesky(sigma, "covariance");
    for (double& v : b) v /= sb;
    const double bn = norm(b);
    Vec y(n);
    for (std::size_t i = 0; i < n; ++i) y[i] = std::sqrt(b[i] / sigma[i][i]);
    for (int iter = 0; iter < 500; ++iter) {
        Vec f = mul(sigma, y);
        for (std::size_t i = 0; i < n; ++i) f[i] -= b[i] / y[i];
        if (norm(f) < 1e-14 * bn) break;
        Mat j = sigma;
        for (std::size_t i = 0; i < n; ++i) j[i][i] += b[i] / (y[i] * y[i]);
        Vec step = chol_solve(cholesky(j, "covariance"), f);
        for (double& v : step) v = -v;
        double t = 1;
        for (int h = 0; h < 200; ++h) {
            bool ok = true;
            for (std::size_t i = 0; i < n; ++i) ok = ok && y[i] + t * step[i] > 0;
            if (ok) break;
            t /= 2;
        }
        for (std::size_t i = 0; i < n; ++i) y[i] += t * step[i];
        if (t * norm(step) < 1e-15) break;
    }
    double sy = 0;
    for (const double v : y) sy += v;
    RiskParity out;
    for (const double v : y) out.weights.push_back(v / sy);
    const Vec sw = mul(sigma, out.weights);
    out.volatility = std::sqrt(dot(out.weights, sw));
    for (std::size_t i = 0; i < n; ++i) out.contributions.push_back(pz(out.weights[i] * sw[i] / out.volatility));
    return out;
}

// ---- Euler contributions (J-W2-6) ----
Euler euler(const Vec& w, const Mat& sigma_in) {
    const std::size_t n = w.size();
    if (n < 1) input("weights is empty", "weights");
    square(sigma_in, n, "covariance");
    const Mat sigma = symmetric(sigma_in, "covariance");
    const Vec sw = mul(sigma, w);
    const double var = dot(w, sw);
    if (!(var > 0)) domain("w' Sigma w must be positive", "covariance");
    Euler out;
    out.volatility = std::sqrt(var);
    for (std::size_t i = 0; i < n; ++i) {
        const double m = sw[i] / out.volatility, c = w[i] * m;
        out.marginal.push_back(pz(m));
        out.contributions.push_back(pz(c));
        out.shares.push_back(pz(c / out.volatility));
    }
    return out;
}

// ---- Ledoit-Wolf, scaled-identity target (J-W2-7) ----
LedoitWolf ledoit_wolf(const Mat& r) {
    const std::size_t t = r.size();
    if (t < 2) input("returns needs at least 2 rows", "returns");
    const std::size_t n = r[0].size();
    if (n < 1) input("returns rows are empty", "returns");
    for (const Vec& row : r)
        if (row.size() != n) input("returns rows must have equal length", "returns");
    const double tt = static_cast<double>(t), nn = static_cast<double>(n);
    Vec mean(n, 0.0);
    for (const Vec& row : r)
        for (std::size_t j = 0; j < n; ++j) mean[j] += row[j];
    for (double& v : mean) v /= tt;
    Mat x(t, Vec(n));
    for (std::size_t s = 0; s < t; ++s)
        for (std::size_t j = 0; j < n; ++j) x[s][j] = r[s][j] - mean[j];
    Mat s(n, Vec(n, 0.0));
    for (std::size_t k = 0; k < t; ++k)
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) s[i][j] += x[k][i] * x[k][j];
    for (Vec& row : s)
        for (double& v : row) v /= tt;
    double m = 0;
    for (std::size_t i = 0; i < n; ++i) m += s[i][i];
    m /= nn;
    double d2 = 0;
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j) {
            const double e = s[i][j] - (i == j ? m : 0.0);
            d2 += e * e;
        }
    d2 /= nn;
    double bsum = 0;
    for (std::size_t k = 0; k < t; ++k)
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) {
                const double e = x[k][i] * x[k][j] - s[i][j];
                bsum += e * e;
            }
    const double bbar2 = bsum / (tt * tt) / nn;
    const double b2 = std::min(bbar2, d2);
    const double delta = b2 == 0 ? 0.0 : b2 / d2;
    LedoitWolf out;
    out.covariance.assign(n, Vec(n));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j)
            out.covariance[i][j] = pz((i == j ? delta * m : 0.0) + (1 - delta) * s[i][j]);
    out.shrinkage = pz(delta);
    out.mu = pz(m);
    return out;
}

// ---- Black-Litterman (J-W2-8): K x K Cholesky, Sigma never inverted ----
BlackLitterman black_litterman(const Mat& sigma_in, const Vec& pi, const Mat& pick, const Vec& q, const Mat& omega_in,
                               double tau) {
    const std::size_t n = sigma_in.size(), k = pick.size();
    if (n < 1) input("covariance is empty", "covariance");
    square(sigma_in, n, "covariance");
    if (pi.size() != n) input("prior_returns must have length N", "prior_returns");
    if (k < 1) input("at least one view is required", "pick");
    for (const Vec& r : pick)
        if (r.size() != n) input("pick must be K x N", "pick");
    if (q.size() != k) input("views must have length K", "views");
    square(omega_in, k, "view_covariance");
    if (!(tau > 0)) domain("tau must be positive", "tau");
    const Mat sigma = symmetric(sigma_in, "covariance");
    (void)cholesky(sigma, "covariance");
    const Mat omega = symmetric(omega_in, "view_covariance");
    (void)cholesky(omega, "view_covariance");
    Mat ts = sigma;
    for (Vec& r : ts)
        for (double& v : r) v *= tau;
    // ps = P tau Sigma (K x N); m = ps P' + Omega.
    Mat ps(k, Vec(n, 0.0));
    for (std::size_t a = 0; a < k; ++a)
        for (std::size_t j = 0; j < n; ++j)
            for (std::size_t i = 0; i < n; ++i) ps[a][j] += pick[a][i] * ts[i][j];
    Mat m(k, Vec(k));
    for (std::size_t a = 0; a < k; ++a)
        for (std::size_t c = 0; c < k; ++c) {
            double s = 0;
            for (std::size_t j = 0; j < n; ++j) s += ps[a][j] * pick[c][j];
            m[a][c] = s + omega[a][c];
        }
    const Mat l = cholesky(m, "view_covariance");
    Vec resid(k);
    for (std::size_t a = 0; a < k; ++a) resid[a] = q[a] - dot(pick[a], pi);
    const Vec z = chol_solve(l, resid);
    // x = m^-1 ps, column by column.
    Mat x(k, Vec(n));
    for (std::size_t j = 0; j < n; ++j) {
        Vec col(k);
        for (std::size_t a = 0; a < k; ++a) col[a] = ps[a][j];
        col = chol_solve(l, col);
        for (std::size_t a = 0; a < k; ++a) x[a][j] = col[a];
    }
    BlackLitterman out;
    out.posterior_returns = pi;
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t a = 0; a < k; ++a) out.posterior_returns[i] += ps[a][i] * z[a];
    out.posterior_covariance.assign(n, Vec(n));
    out.predictive_covariance.assign(n, Vec(n));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j) {
            double s = 0;
            for (std::size_t a = 0; a < k; ++a) s += ps[a][i] * x[a][j];
            out.posterior_covariance[i][j] = ts[i][j] - s;
            out.predictive_covariance[i][j] = sigma[i][j] + out.posterior_covariance[i][j];
        }
    out.posterior_returns = pz(out.posterior_returns);
    out.posterior_covariance = pz(out.posterior_covariance);
    out.predictive_covariance = pz(out.predictive_covariance);
    return out;
}

// ---- Acerbi-Szekely Z2 (J-W2-10) ----
EsZ2 es_z2(const Vec& losses, const Vec& var, const Vec& es, double alpha) {
    const std::size_t t = losses.size();
    if (t < 1 || var.size() != t || es.size() != t) input("losses, var and es must have one equal length >= 1", "losses");
    if (!(alpha > 0 && alpha < 1)) domain("alpha must be in (0, 1)", "alpha");
    for (const double e : es)
        if (!(e > 0)) domain("es must be positive", "es");
    const double ta = static_cast<double>(t) * alpha;
    double s = 0;
    long long count = 0;
    for (std::size_t i = 0; i < t; ++i)
        if (losses[i] > var[i]) {
            s += losses[i] / (ta * es[i]);
            ++count;
        }
    return {pz(1 - s), count, ta};
}

// ---- Baum-Welch (baum-welch.md, J-W2-11, J-W2-13) ----
namespace {

struct Theta {
    Vec pi;
    Mat a;
    Vec mu, sd;
};

struct EStep {
    Mat gamma;   // T x K
    Mat xi_sum;  // K x K, summed over t < T-1
    double loglik;
};

EStep e_step(const Vec& y, const Theta& th) {
    const std::size_t t = y.size(), k = th.pi.size();
    const double root = std::sqrt(2 * std::numbers::pi);
    Mat b(t, Vec(k));
    for (std::size_t s = 0; s < t; ++s)
        for (std::size_t j = 0; j < k; ++j) {
            const double z = (y[s] - th.mu[j]) / th.sd[j];
            b[s][j] = std::exp(-0.5 * z * z) / (root * th.sd[j]);
        }
    Mat al(t, Vec(k));
    Vec c(t);
    double ll = 0;
    for (std::size_t s = 0; s < t; ++s) {
        double cs = 0;
        for (std::size_t j = 0; j < k; ++j) {
            double v;
            if (s == 0) {
                v = th.pi[j] * b[0][j];
            } else {
                double acc = 0;
                for (std::size_t i = 0; i < k; ++i) acc += al[s - 1][i] * th.a[i][j];
                v = acc * b[s][j];
            }
            al[s][j] = v;
            cs += v;
        }
        if (!(cs > 0)) domain("an observation has zero density under every state (J-W2-13)", "observations");
        c[s] = cs;
        for (std::size_t j = 0; j < k; ++j) al[s][j] /= cs;
        ll += std::log(cs);
    }
    Mat be(t, Vec(k, 1.0));
    for (std::size_t s = t - 1; s-- > 0;)
        for (std::size_t i = 0; i < k; ++i) {
            double acc = 0;
            for (std::size_t j = 0; j < k; ++j) acc += th.a[i][j] * b[s + 1][j] * be[s + 1][j] / c[s + 1];
            be[s][i] = acc;
        }
    EStep e;
    e.loglik = ll;
    e.gamma.assign(t, Vec(k));
    for (std::size_t s = 0; s < t; ++s)
        for (std::size_t i = 0; i < k; ++i) e.gamma[s][i] = al[s][i] * be[s][i];
    e.xi_sum.assign(k, Vec(k, 0.0));
    for (std::size_t s = 0; s + 1 < t; ++s)
        for (std::size_t i = 0; i < k; ++i)
            for (std::size_t j = 0; j < k; ++j)
                e.xi_sum[i][j] += al[s][i] * th.a[i][j] * b[s + 1][j] * be[s + 1][j] / c[s + 1];
    return e;
}

Theta m_step(const Vec& y, const EStep& e) {
    const std::size_t t = y.size(), k = e.xi_sum.size();
    Theta th;
    th.pi = e.gamma[0];
    th.a.assign(k, Vec(k));
    th.mu.assign(k, 0.0);
    th.sd.assign(k, 0.0);
    for (std::size_t i = 0; i < k; ++i) {
        double g = 0;
        for (std::size_t s = 0; s + 1 < t; ++s) g += e.gamma[s][i];
        if (!(g > 0)) domain("zero denominator in the transition update (J-W2-13)", "transition");
        for (std::size_t j = 0; j < k; ++j) th.a[i][j] = e.xi_sum[i][j] / g;
        double ga = 0, gy = 0;
        for (std::size_t s = 0; s < t; ++s) {
            ga += e.gamma[s][i];
            gy += e.gamma[s][i] * y[s];
        }
        const double m = gy / ga;
        double gv = 0;
        for (std::size_t s = 0; s < t; ++s) gv += e.gamma[s][i] * (y[s] - m) * (y[s] - m);
        const double v = gv / ga;
        if (!(v > 0)) domain("a variance update is not positive (J-W2-13)", "sds");
        th.mu[i] = m;
        th.sd[i] = std::sqrt(v);
    }
    return th;
}

void check_prob_row(const Vec& r, const char* field) {
    double s = 0;
    for (const double v : r) {
        if (v < 0) domain("negative probability", field);
        s += v;
    }
    if (std::fabs(s - 1.0) > 1e-9) domain("probabilities do not sum to 1", field);
}

}  // namespace

BaumWelch baum_welch(const Vec& y, const Vec& initial, const Mat& transition, const Vec& means, const Vec& sds,
                     double tolerance, long long max_iterations) {
    const std::size_t k = initial.size();
    if (k < 1) input("initial is empty", "initial");
    square(transition, k, "transition");
    if (means.size() != k || sds.size() != k) input("means and sds must have length K", "means");
    if (y.size() < 2) input("at least 2 observations are required", "observations");
    if (max_iterations < 1) input("max_iterations must be at least 1", "max_iterations");
    check_prob_row(initial, "initial");
    for (const Vec& r : transition) check_prob_row(r, "transition");
    for (const double s : sds)
        if (!(s > 0)) domain("sd must be positive", "sds");
    if (!(tolerance > 0)) domain("tolerance must be positive", "tolerance");

    Theta th{initial, transition, means, sds};
    EStep e = e_step(y, th);
    BaumWelch out;
    out.trace.push_back(e.loglik);
    double prev = e.loglik;
    long long it = 0;
    bool conv = false;
    while (it < max_iterations) {
        ++it;
        th = m_step(y, e);
        e = e_step(y, th);
        out.trace.push_back(e.loglik);
        if (e.loglik - prev < tolerance) {
            conv = true;
            break;
        }
        prev = e.loglik;
    }
    out.initial = pz(th.pi);
    out.transition = pz(th.a);
    out.means = pz(th.mu);
    out.sds = th.sd;
    out.log_likelihood = pz(e.loglik);
    out.iterations = it;
    out.converged = conv;
    return out;
}

}  // namespace quantforge::research
