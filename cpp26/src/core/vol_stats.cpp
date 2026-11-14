#include "quantforge/core/vol_stats.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>
#include <set>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

constexpr double ln_2pi = 1.8378770664093454835606594728112;  // ln(2 pi)

double sample_variance(const std::vector<double>& r) {
    double s = 0.0;
    for (const double x : r) s += x * x;
    return s / double(r.size());
}

// The recursion and likelihood, without checks; fills variances when asked.
double loglik_raw(const std::vector<double>& r, double omega, double alpha, double beta, double v1,
                  std::vector<double>* variances, double* next) {
    double v = v1, sum = 0.0;
    for (const double x : r) {
        if (variances) variances->push_back(v);
        sum += ln_2pi + std::log(v) + x * x / v;
        v = omega + alpha * x * x + beta * v;
    }
    if (next) *next = v;
    return -0.5 * sum;
}

double start_variance(const std::vector<double>& r, std::optional<double> initial) {
    if (initial) {
        if (*initial <= 0.0) throw Error("E_DOMAIN", "initial_variance must be positive", "initial_variance");
        return *initial;
    }
    const double v = sample_variance(r);
    if (v <= 0.0) throw Error("E_DOMAIN", "SAMPLE initial variance is zero", "initial_variance");
    return v;
}

void check_params(double omega, double alpha, double beta) {
    if (omega <= 0.0) throw Error("E_DOMAIN", "omega must be positive", "omega");
    if (alpha < 0.0) throw Error("E_DOMAIN", "alpha must not be negative", "alpha");
    if (beta < 0.0) throw Error("E_DOMAIN", "beta must not be negative", "beta");
}

// Unconstrained coordinates: omega = e^u0, alpha and beta a softmax share with a slack term, so alpha + beta < 1.
std::array<double, 3> params_of(const std::array<double, 3>& u) {
    const double m = std::max({0.0, u[1], u[2]});
    const double e0 = std::exp(-m), e1 = std::exp(u[1] - m), e2 = std::exp(u[2] - m), s = e0 + e1 + e2;
    return {std::exp(u[0]), e1 / s, e2 / s};
}

std::array<double, 3> coords_of(double omega, double alpha, double beta) {
    const double slack = 1.0 - alpha - beta;
    return {std::log(omega), std::log(alpha / slack), std::log(beta / slack)};
}

using Point = std::array<double, 3>;

// Nelder-Mead minimiser (standard coefficients) from a start and a step; returns the best point.
Point nelder_mead(auto&& f, Point x0, double step, int max_iter, bool& converged) {
    std::array<Point, 4> s;
    std::array<double, 4> fs;
    for (int i = 0; i < 4; ++i) {
        s[i] = x0;
        if (i > 0) s[i][i - 1] += step;
        fs[i] = f(s[i]);
    }
    converged = false;
    for (int it = 0; it < max_iter; ++it) {
        std::array<int, 4> o = {0, 1, 2, 3};
        std::sort(o.begin(), o.end(), [&](int a, int b) { return fs[a] < fs[b]; });
        const int best = o[0], worst = o[3], second = o[2];
        if (std::fabs(fs[worst] - fs[best]) <= 1e-15 * (1.0 + std::fabs(fs[best]))) {
            converged = true;
            return s[best];
        }
        Point c{};
        for (int i = 0; i < 4; ++i)
            if (i != worst)
                for (int k = 0; k < 3; ++k) c[k] += s[i][k] / 3.0;
        const auto along = [&](double t) {
            Point p;
            for (int k = 0; k < 3; ++k) p[k] = c[k] + t * (s[worst][k] - c[k]);
            return p;
        };
        const Point xr = along(-1.0);
        const double fr = f(xr);
        if (fr < fs[best]) {
            const Point xe = along(-2.0);
            const double fe = f(xe);
            if (fe < fr) s[worst] = xe, fs[worst] = fe;
            else s[worst] = xr, fs[worst] = fr;
        } else if (fr < fs[second]) {
            s[worst] = xr, fs[worst] = fr;
        } else {
            const Point xc = fr < fs[worst] ? along(-0.5) : along(0.5);
            const double fc = f(xc);
            if (fc < std::min(fr, fs[worst])) {
                s[worst] = xc, fs[worst] = fc;
            } else {
                for (int i = 0; i < 4; ++i) {
                    if (i == best) continue;
                    for (int k = 0; k < 3; ++k) s[i][k] = s[best][k] + 0.5 * (s[i][k] - s[best][k]);
                    fs[i] = f(s[i]);
                }
            }
        }
    }
    return s[std::min_element(fs.begin(), fs.end()) - fs.begin()];
}

void check_strikes(const std::vector<double>& k, const char* key) {
    if (k.empty()) throw Error("E_INPUT", std::string(key) + " is empty", key);
    if (std::set<double>(k.begin(), k.end()).size() != k.size())
        throw Error("E_INPUT", std::string(key) + " repeats a strike", key);
}

// DDKZ weights along a walk of strikes (ruling E-B3): the last entry is the extension, with no option.
std::vector<double> walk_weights(const std::vector<double>& k, auto&& f) {
    std::vector<double> w;
    double prev = 0.0;
    for (std::size_t j = 0; j + 1 < k.size(); ++j) {
        const double s = std::fabs(f(k[j + 1]) - f(k[j])) / std::fabs(k[j + 1] - k[j]);
        w.push_back(s - prev);
        prev = s;
    }
    return w;
}

}  // namespace

// ---- GARCH ----

GarchLoglik garch_loglik(const std::vector<double>& r, double omega, double alpha, double beta,
                         std::optional<double> initial) {
    require_finite(r, "returns");
    require_finite(omega, "omega");
    require_finite(alpha, "alpha");
    require_finite(beta, "beta");
    require_finite(initial, "initial_variance");
    if (r.size() < 2) throw Error("E_INPUT", "at least 2 returns are needed", "returns");
    check_params(omega, alpha, beta);
    const double v1 = start_variance(r, initial);
    GarchLoglik out;
    out.loglik = loglik_raw(r, omega, alpha, beta, v1, &out.variances, &out.next_variance);
    return out;
}

GarchForecast garch_forecast(double omega, double alpha, double beta, double next, long long h, double ppy) {
    require_finite(omega, "omega");
    require_finite(alpha, "alpha");
    require_finite(beta, "beta");
    require_finite(next, "next_variance");
    require_finite(ppy, "periods_per_year");
    if (h < 1) throw Error("E_INPUT", "horizon must be at least 1", "horizon");
    if (ppy <= 0.0) throw Error("E_INPUT", "periods_per_year must be positive", "periods_per_year");
    check_params(omega, alpha, beta);
    if (next <= 0.0) throw Error("E_DOMAIN", "next_variance must be positive", "next_variance");
    const double p = alpha + beta;
    if (p >= 1.0) throw Error("E_DOMAIN", "alpha + beta >= 1 has no long-run variance");
    GarchForecast out;
    out.long_run_variance = omega / (1.0 - p);
    out.total_variance = 0.0;
    double pk = 1.0;  // p^(h-1)
    for (long long i = 1; i <= h; ++i) {
        const double v = out.long_run_variance + pk * (next - out.long_run_variance);
        out.variances.push_back(v);
        out.total_variance += v;
        pk *= p;
    }
    out.annualized_vol = std::sqrt(out.total_variance * ppy / double(h));
    return out;
}

GarchFit garch_fit(const std::vector<double>& r, std::optional<double> initial) {
    require_finite(r, "returns");
    require_finite(initial, "initial_variance");
    if (r.size() < 30) throw Error("E_INPUT", "at least 30 returns are needed", "returns");
    const double v1 = start_variance(r, initial);
    const double var = sample_variance(r);
    const auto objective = [&](const Point& u) {
        const auto [o, a, b] = params_of(u);
        const double ll = loglik_raw(r, o, a, b, v1, nullptr, nullptr);
        return std::isfinite(ll) ? -ll : 1e300;
    };
    // Several starts, then restarts from the best point until a restart no longer improves it.
    Point best{};
    double fbest = 1e300;
    constexpr std::array<std::array<double, 2>, 5> starts = {
        {{0.05, 0.90}, {0.10, 0.80}, {0.20, 0.60}, {0.05, 0.50}, {0.30, 0.30}}};
    for (const auto& [a, b] : starts) {
        bool ok = false;
        const Point x = nelder_mead(objective, coords_of(std::max(var, 1e-300) * (1.0 - a - b), a, b), 0.5, 5000, ok);
        const double fx = objective(x);
        if (fx < fbest) best = x, fbest = fx;
    }
    bool converged = false;
    for (int round = 0; round < 50; ++round) {
        const Point x = nelder_mead(objective, best, 0.05, 20000, converged);
        const double fx = objective(x);
        const double gain = fbest - fx;
        if (fx < fbest) best = x, fbest = fx;
        if (converged && gain <= 1e-12 * (1.0 + std::fabs(fbest))) break;
        converged = false;
    }
    if (!converged || fbest >= 1e300) throw Error("E_NO_CONVERGENCE", "the GARCH fit did not converge");
    const auto [o, a, b] = params_of(best);
    return {-fbest, o, a, b};
}

// ---- GARCH, stage F (R8) ----

namespace {

// digamma and trigamma: recurrence up to x >= 10, then the asymptotic series.
double digamma(double x) {
    double acc = 0.0;
    while (x < 10.0) acc -= 1.0 / x, x += 1.0;
    const double r = 1.0 / (x * x);
    return acc + std::log(x) - 0.5 / x -
           r * (1.0 / 12 - r * (1.0 / 120 - r * (1.0 / 252 - r * (1.0 / 240 - r * (1.0 / 132)))));
}
double trigamma(double x) {
    double acc = 0.0;
    while (x < 10.0) acc += 1.0 / (x * x), x += 1.0;
    const double r = 1.0 / (x * x);
    return acc + 1.0 / x + 0.5 * r +
           (r / x) * (1.0 / 6 - r * (1.0 / 30 - r * (1.0 / 42 - r * (1.0 / 30 - r * (5.0 / 66)))));
}

double student_const(double nu) {
    return std::lgamma((nu + 1) / 2) - std::lgamma(nu / 2) - 0.5 * std::log(std::numbers::pi * (nu - 2));
}

// Log-likelihood on demeaned returns e, with optional variances; no checks.
double loglik_law(const std::vector<double>& e, double omega, double alpha, double beta, double v1, bool t,
                  double nu, std::vector<double>* variances, double* next) {
    if (!t) return loglik_raw(e, omega, alpha, beta, v1, variances, next);
    const double c = student_const(nu);
    double v = v1, sum = 0.0;
    for (const double x : e) {
        if (variances) variances->push_back(v);
        sum += c - 0.5 * std::log(v) - 0.5 * (nu + 1) * std::log1p(x * x / ((nu - 2) * v));
        v = omega + alpha * x * x + beta * v;
    }
    if (next) *next = v;
    return sum;
}

constexpr int max_k = 4;
using Vec4 = std::array<double, max_k>;
using Mat4 = std::array<Vec4, max_k>;

// Value, exact gradient and exact Hessian in (omega, alpha, beta[, nu]); v1 is held fixed.
double loglik_derivs(const std::vector<double>& e, const Vec4& p, int k, double v1, Vec4& g, Mat4& h) {
    const bool t = k == 4;
    const double omega = p[0], alpha = p[1], beta = p[2], nu = t ? p[3] : 0.0;
    g = {};
    h = {};
    std::array<double, 3> dv{0, 0, 0};
    std::array<std::array<double, 3>, 3> d2v{};
    double v = v1, sum = 0.0;
    const double c = t ? student_const(nu) : 0.0;
    const double c1 = t ? 0.5 * digamma((nu + 1) / 2) - 0.5 * digamma(nu / 2) - 0.5 / (nu - 2) : 0.0;
    const double c2 = t ? 0.25 * trigamma((nu + 1) / 2) - 0.25 * trigamma(nu / 2) + 0.5 / ((nu - 2) * (nu - 2)) : 0.0;
    for (const double x : e) {
        const double x2 = x * x;
        double lv, lvv, ln = 0, lnn = 0, lvn = 0;
        if (!t) {
            sum += -0.5 * (ln_2pi + std::log(v) + x2 / v);
            lv = -0.5 * (1.0 / v - x2 / (v * v));
            lvv = -0.5 * (-1.0 / (v * v) + 2.0 * x2 / (v * v * v));
        } else {
            const double z = x2 / ((nu - 2) * v), s = x2 / (x2 + (nu - 2) * v);
            sum += c - 0.5 * std::log(v) - 0.5 * (nu + 1) * std::log1p(z);
            lv = -0.5 / v + 0.5 * (nu + 1) * s / v;
            lvv = 0.5 / (v * v) - 0.5 * (nu + 1) * s * (2 - s) / (v * v);
            ln = c1 - 0.5 * std::log1p(z) + (nu + 1) * s / (2 * (nu - 2));
            lnn = c2 + s / (nu - 2) - (nu + 1) * s * (2 - s) / (2 * (nu - 2) * (nu - 2));
            lvn = s / (2 * v) - (nu + 1) * s * (1 - s) / (2 * v * (nu - 2));
        }
        for (int i = 0; i < 3; ++i) {
            g[i] += lv * dv[i];
            for (int j = 0; j < 3; ++j) h[i][j] += lvv * dv[i] * dv[j] + lv * d2v[i][j];
        }
        if (t) {
            g[3] += ln;
            h[3][3] += lnn;
            for (int i = 0; i < 3; ++i) h[i][3] += lvn * dv[i];
        }
        std::array<std::array<double, 3>, 3> d2n{};
        for (int i = 0; i < 3; ++i)
            for (int j = 0; j < 3; ++j)
                d2n[i][j] = (j == 2 ? dv[i] : 0.0) + (i == 2 ? dv[j] : 0.0) + beta * d2v[i][j];
        const std::array<double, 3> dn{1.0 + beta * dv[0], x2 + beta * dv[1], v + beta * dv[2]};
        d2v = d2n;
        dv = dn;
        v = omega + alpha * x2 + beta * v;
    }
    if (t)
        for (int i = 0; i < 3; ++i) h[3][i] = h[i][3];
    return sum;
}

// Solves A x = b by Gaussian elimination with partial pivoting; false if singular.
bool solve(Mat4 a, Vec4 b, int k, Vec4& x) {
    for (int c = 0; c < k; ++c) {
        int piv = c;
        for (int r = c + 1; r < k; ++r)
            if (std::fabs(a[r][c]) > std::fabs(a[piv][c])) piv = r;
        if (!(std::fabs(a[piv][c]) > 0.0)) return false;
        std::swap(a[c], a[piv]);
        std::swap(b[c], b[piv]);
        for (int r = c + 1; r < k; ++r) {
            const double f = a[r][c] / a[c][c];
            for (int j = c; j < k; ++j) a[r][j] -= f * a[c][j];
            b[r] -= f * b[c];
        }
    }
    for (int r = k - 1; r >= 0; --r) {
        double s = b[r];
        for (int j = r + 1; j < k; ++j) s -= a[r][j] * x[j];
        x[r] = s / a[r][r];
    }
    return true;
}

bool feasible(const Vec4& p, int k) {
    if (!(p[0] > 0.0 && p[1] >= 0.0 && p[2] >= 0.0 && p[1] + p[2] < 1.0)) return false;
    return k == 3 || (p[3] > 2.0 && p[3] <= 500.0);
}

// Marquardt-damped Newton ascent from p; returns the final log-likelihood (or -inf).
double ascend(const std::vector<double>& e, Vec4& p, int k, double v1) {
    Vec4 g;
    Mat4 h;
    double f = loglik_derivs(e, p, k, v1, g, h);
    if (!std::isfinite(f)) return -HUGE_VAL;
    double lambda = 1e-3;
    for (int it = 0; it < 2000; ++it) {
        Mat4 a{};
        for (int i = 0; i < k; ++i)
            for (int j = 0; j < k; ++j) a[i][j] = -h[i][j];
        for (int i = 0; i < k; ++i) a[i][i] += lambda * std::max(std::fabs(h[i][i]), 1e-300);
        Vec4 d{};
        bool moved = false;
        if (solve(a, g, k, d)) {
            Vec4 q = p;
            double rel = 0.0;
            for (int i = 0; i < k; ++i) q[i] += d[i], rel = std::max(rel, std::fabs(d[i]) / std::fabs(p[i]));
            if (feasible(q, k)) {
                Vec4 gq;
                Mat4 hq;
                const double fq = loglik_derivs(e, q, k, v1, gq, hq);
                if (std::isfinite(fq) && fq >= f) {
                    p = q, f = fq, g = gq, h = hq, moved = true;
                    lambda = std::max(lambda / 10.0, 1e-12);
                    if (rel < 1e-13) break;
                }
            }
        }
        if (!moved) {
            lambda *= 10.0;
            if (lambda > 1e20) break;
        }
    }
    return f;
}

}  // namespace

GarchLoglik garch_loglik(const std::vector<double>& r, double omega, double alpha, double beta,
                         std::optional<double> initial, const GarchLaw& law) {
    require_finite(r, "returns");
    require_finite(omega, "omega");
    require_finite(alpha, "alpha");
    require_finite(beta, "beta");
    require_finite(initial, "initial_variance");
    require_finite(law.mean, "mean");
    const bool t = law.distribution == GarchDistribution::StudentT;
    if (t) require_finite(law.degrees_of_freedom, "degrees_of_freedom");
    if (r.size() < 2) throw Error("E_INPUT", "at least 2 returns are needed", "returns");
    check_params(omega, alpha, beta);
    std::vector<double> e = r;
    for (double& x : e) x -= law.mean;
    const double v1 = start_variance(e, initial);
    if (t && !law.degrees_of_freedom)
        throw Error("E_INPUT", "STUDENT_T needs degrees_of_freedom", "degrees_of_freedom");
    const double nu = t ? *law.degrees_of_freedom : 0.0;
    if (t && nu <= 2.0) throw Error("E_DOMAIN", "degrees_of_freedom must be above 2", "degrees_of_freedom");
    GarchLoglik out;
    out.loglik = loglik_law(e, omega, alpha, beta, v1, t, nu, &out.variances, &out.next_variance);
    return out;
}

GarchEstimate garch_estimate(const std::vector<double>& r, std::optional<double> initial,
                             GarchDistribution distribution, bool demean) {
    require_finite(r, "returns");
    require_finite(initial, "initial_variance");
    const bool t = distribution == GarchDistribution::StudentT;
    if (r.size() < 30) throw Error("E_INPUT", "at least 30 returns are needed", "returns");
    if (t && r.size() < 100) throw Error("E_INPUT", "STUDENT_T needs at least 100 returns", "returns");
    double mu = 0.0;
    if (demean) {
        for (const double x : r) mu += x;
        mu /= double(r.size());
    }
    std::vector<double> e = r;
    for (double& x : e) x -= mu;
    const double v1 = start_variance(e, initial);
    const double var = sample_variance(e);
    // Rulings R6-8.1, J-0b.2: finite returns whose squares overflow binary64.
    if (!std::isfinite(var) || !std::isfinite(v1))
        throw Error("E_NON_FINITE", "the sample variance of the returns overflows", "returns");
    const int k = t ? 4 : 3;

    Vec4 best{};
    double fbest = -HUGE_VAL;
    constexpr std::array<std::array<double, 2>, 5> starts = {
        {{0.05, 0.90}, {0.10, 0.80}, {0.20, 0.60}, {0.05, 0.50}, {0.30, 0.30}}};
    for (const auto& [a, b] : starts)
        for (const double nu0 : {8.0, 20.0}) {
            if (!t && nu0 != 8.0) continue;
            Vec4 p{std::max(var, 1e-300) * (1.0 - a - b), a, b, nu0};
            const double f = ascend(e, p, k, v1);
            if (f > fbest) fbest = f, best = p;
        }
    if (!std::isfinite(fbest)) throw Error("E_NO_CONVERGENCE", "the GARCH estimate did not converge");

    // Polish: plain Newton steps until the largest relative step is below 1e-12.
    Vec4 g;
    Mat4 h;
    bool done = false;
    for (int it = 0; it < 50 && !done; ++it) {
        loglik_derivs(e, best, k, v1, g, h);
        Mat4 a{};
        for (int i = 0; i < k; ++i)
            for (int j = 0; j < k; ++j) a[i][j] = -h[i][j];
        Vec4 d{};
        if (!solve(a, g, k, d)) break;
        double rel = 0.0;
        for (int i = 0; i < k; ++i) rel = std::max(rel, std::fabs(d[i]) / std::fabs(best[i]));
        Vec4 q = best;
        for (int i = 0; i < k; ++i) q[i] += d[i];
        if (!feasible(q, k)) break;
        best = q;
        if (rel < 1e-12) done = true;
    }
    const double f = loglik_derivs(e, best, k, v1, g, h);
    // Interior check (ruling F-11), negative definiteness by Cholesky of -H, then V = (-H)^{-1}.
    const double tol = 1e-6;
    bool interior = done && std::isfinite(f) && best[0] >= tol * var && best[1] >= tol && best[2] >= tol &&
                    1.0 - best[1] - best[2] >= tol;
    if (t) interior = interior && best[3] - 2.0 >= tol * 2.0 && 500.0 - best[3] >= tol * 500.0;
    Mat4 l{};
    for (int i = 0; i < k && interior; ++i)
        for (int j = 0; j <= i; ++j) {
            double s = -h[i][j];
            for (int m = 0; m < j; ++m) s -= l[i][m] * l[j][m];
            if (i == j) {
                if (!(s > 0.0)) interior = false;
                else l[i][i] = std::sqrt(s);
            } else {
                l[i][j] = s / l[j][j];
            }
        }
    if (!interior) throw Error("E_NO_CONVERGENCE", "no interior maximum of the GARCH likelihood");
    Vec4 se{};
    Mat4 neg{};
    for (int i = 0; i < k; ++i)
        for (int j = 0; j < k; ++j) neg[i][j] = -h[i][j];
    for (int c = 0; c < k; ++c) {
        Vec4 unit{}, col{};
        unit[c] = 1.0;
        if (!solve(neg, unit, k, col) || !(col[c] > 0.0))
            throw Error("E_NO_CONVERGENCE", "the information matrix is singular");
        se[c] = std::sqrt(col[c]);
    }
    GarchEstimate out;
    out.omega = best[0];
    out.alpha = best[1];
    out.beta = best[2];
    out.degrees_of_freedom = t ? std::optional<double>(best[3]) : std::nullopt;
    out.mean = mu;
    out.loglik = f;
    out.persistence = best[1] + best[2];
    out.se_omega = se[0];
    out.se_alpha = se[1];
    out.se_beta = se[2];
    out.se_degrees_of_freedom = t ? std::optional<double>(se[3]) : std::nullopt;
    return out;
}

// ---- variance swaps ----

VarSwapFair varswap_fair_strike(const VarSwapInputs& in) {
    require_finite(in.spot, "spot");
    require_finite(in.rate, "rate");
    require_finite(in.dividend_yield, "dividend_yield");
    require_finite(in.put_strikes, "put_strikes");
    require_finite(in.call_strikes, "call_strikes");
    for (const StrikeVol& v : in.vols) {
        require_finite(v.strike, "vols");
        require_finite(v.vol, "vols");
    }
    require_finite(in.extension_step, "extension_step");
    require_finite(in.variance_strike, "variance_strike");
    require_finite(in.variance_notional, "variance_notional");
    if (in.maturity <= in.as_of) throw Error("E_INPUT", "maturity must be after as_of", "maturity");
    check_strikes(in.put_strikes, "put_strikes");
    check_strikes(in.call_strikes, "call_strikes");
    for (const double k : in.put_strikes)
        if (k > in.spot) throw Error("E_INPUT", "a put strike is above spot", "put_strikes");
    for (const double k : in.call_strikes)
        if (k < in.spot) throw Error("E_INPUT", "a call strike is below spot", "call_strikes");
    std::set<double> all(in.put_strikes.begin(), in.put_strikes.end());
    all.insert(in.call_strikes.begin(), in.call_strikes.end());
    std::set<double> listed;
    for (const StrikeVol& v : in.vols)
        if (!all.contains(v.strike) || !listed.insert(v.strike).second)
            throw Error("E_INPUT", "vols must list each strike exactly once", "vols");
    if (listed.size() != all.size()) throw Error("E_INPUT", "vols must list each strike exactly once", "vols");
    if (in.spot <= 0.0) throw Error("E_DOMAIN", "spot must be positive", "spot");
    for (const StrikeVol& v : in.vols)
        if (v.vol <= 0.0) throw Error("E_DOMAIN", "a vol is not positive", "vols");
    if (in.extension_step <= 0.0) throw Error("E_DOMAIN", "extension_step must be positive", "extension_step");
    const double kmin = *std::min_element(in.put_strikes.begin(), in.put_strikes.end());
    if (kmin - in.extension_step <= 0.0) throw Error("E_DOMAIN", "the put extension strike is not positive");

    const double t = days_between(in.as_of, in.maturity) / 365.0, s0 = in.spot;
    const double d = std::exp(-in.rate * t), fwd = s0 * std::exp((in.rate - in.dividend_yield) * t);
    const auto f = [&](double k) { return (2.0 / t) * ((k - s0) / s0 - std::log(k / s0)); };
    const auto vol_of = [&](double k) {
        for (const StrikeVol& v : in.vols)
            if (v.strike == k) return v.vol;
        return 0.0;  // unreachable: every strike is listed
    };
    std::vector<double> calls = in.call_strikes, puts = in.put_strikes;
    std::ranges::sort(calls);
    std::ranges::sort(puts, std::greater<>{});
    calls.push_back(calls.back() + in.extension_step);
    puts.push_back(puts.back() - in.extension_step);
    double pi = 0.0;
    const std::vector<double> wc = walk_weights(calls, f), wp = walk_weights(puts, f);
    for (std::size_t j = 0; j < wc.size(); ++j) pi += wc[j] * black_price(fwd, calls[j], vol_of(calls[j]), t, d, 1.0);
    for (std::size_t j = 0; j < wp.size(); ++j) pi += wp[j] * black_price(fwd, puts[j], vol_of(puts[j]), t, d, -1.0);
    VarSwapFair out;
    out.fair_variance = (2.0 / t) * ((in.rate - in.dividend_yield) * t - (fwd / s0 - 1.0)) + pi / d;
    if (!(out.fair_variance >= 0.0)) throw Error("E_DOMAIN", "the replicated variance is below 0");  // ruling E-B36
    out.fair_vol = std::sqrt(out.fair_variance);
    out.pv = in.variance_notional * d * (out.fair_variance - in.variance_strike);
    return out;
}

VarSwapRealized varswap_realized(const std::vector<double>& p, double a, double k_var, double n_var) {
    require_finite(p, "prices");
    require_finite(a, "periods_per_year");
    require_finite(k_var, "variance_strike");
    require_finite(n_var, "variance_notional");
    if (p.size() < 2) throw Error("E_INPUT", "at least 2 prices are needed", "prices");
    for (const double x : p)
        if (x <= 0.0) throw Error("E_DOMAIN", "a price is not positive", "prices");
    double s = 0.0;
    for (std::size_t i = 1; i < p.size(); ++i) {
        const double x = std::log(p[i] / p[i - 1]);
        s += x * x;
    }
    VarSwapRealized out;
    out.realized_variance = a / double(p.size() - 1) * s;
    out.realized_vol = std::sqrt(out.realized_variance);
    out.payoff = n_var * (out.realized_variance - k_var);
    return out;
}

// ---- VIX ----

namespace {
void require_finite_term(const VixTerm& term) {
    require_finite(term.rate, "rate");
    for (const VixQuote& x : term.strip) {
        require_finite(x.strike, "strip");
        for (const auto& v : {x.call_bid, x.call_ask, x.put_bid, x.put_ask}) require_finite(v, "strip");
    }
}
bool call_ok(const VixQuote& x) { return x.call_bid && x.call_ask; }
bool put_ok(const VixQuote& x) { return x.put_bid && x.put_ask; }
}  // namespace

VixTermResult vix_term_variance(const VixTerm& term) {
    require_finite_term(term);
    if (term.minutes < 1) throw Error("E_INPUT", "minutes_to_expiry must be at least 1", "minutes_to_expiry");
    std::vector<VixQuote> q = term.strip;
    std::ranges::sort(q, {}, &VixQuote::strike);
    if (q.size() < 3) throw Error("E_INPUT", "at least 3 strikes are needed", "strip");
    for (std::size_t i = 1; i < q.size(); ++i)
        if (q[i].strike == q[i - 1].strike) throw Error("E_INPUT", "the strip repeats a strike", "strip");
    for (const VixQuote& x : q)
        if ((call_ok(x) && *x.call_bid > *x.call_ask) || (put_ok(x) && *x.put_bid > *x.put_ask))
            throw Error("E_INPUT", "a bid is above its ask", "strip");
    for (const VixQuote& x : q)
        for (const auto& v : {x.call_bid, x.call_ask, x.put_bid, x.put_ask})
            if (v && *v < 0.0) throw Error("E_DOMAIN", "a quote is negative", "strip");

    const double t = double(term.minutes) / 525600.0, growth = std::exp(term.rate * t);
    const auto cmid = [&](std::size_t i) { return (*q[i].call_bid + *q[i].call_ask) / 2.0; };
    const auto pmid = [&](std::size_t i) { return (*q[i].put_bid + *q[i].put_ask) / 2.0; };
    // Forward: only strikes with both sides quoted are candidates for K* (ruling F-15).
    std::ptrdiff_t star = -1;
    for (std::size_t i = 0; i < q.size(); ++i) {
        if (!call_ok(q[i]) || !put_ok(q[i])) continue;
        if (star < 0 || std::fabs(cmid(i) - pmid(i)) < std::fabs(cmid(std::size_t(star)) - pmid(std::size_t(star))))
            star = std::ptrdiff_t(i);  // ties keep the lowest
    }
    if (star < 0) throw Error("E_INPUT", "no strike has both a call and a put quote", "strip");
    const std::size_t ks = std::size_t(star);
    const double fwd = q[ks].strike + growth * (cmid(ks) - pmid(ks));
    std::ptrdiff_t i0 = -1;
    for (std::size_t i = 0; i < q.size(); ++i)
        if (q[i].strike <= fwd) i0 = std::ptrdiff_t(i);
    if (i0 < 0) throw Error("E_INPUT", "no strike is at or below the forward", "strip");
    if (!call_ok(q[std::size_t(i0)]) || !put_ok(q[std::size_t(i0)]))
        throw Error("E_INPUT", "the K0 strike has a null quote", "strip");

    // Selected strikes with their prices Q, ascending. Null series are skipped as if not listed on that side.
    std::vector<std::pair<double, double>> sel;
    int zeros = 0;
    for (std::ptrdiff_t i = i0 - 1; i >= 0; --i) {
        if (!put_ok(q[std::size_t(i)])) continue;
        if (*q[std::size_t(i)].put_bid == 0.0) {
            if (++zeros == 2) break;
            continue;
        }
        zeros = 0;
        sel.emplace_back(q[std::size_t(i)].strike, pmid(std::size_t(i)));
    }
    if (sel.empty()) throw Error("E_INPUT", "every out-of-the-money put is excluded", "strip");
    std::ranges::reverse(sel);
    sel.emplace_back(q[std::size_t(i0)].strike, (cmid(std::size_t(i0)) + pmid(std::size_t(i0))) / 2.0);
    zeros = 0;
    for (std::size_t i = std::size_t(i0) + 1; i < q.size(); ++i) {
        if (!call_ok(q[i])) continue;
        if (*q[i].call_bid == 0.0) {
            if (++zeros == 2) break;
            continue;
        }
        zeros = 0;
        sel.emplace_back(q[i].strike, cmid(i));
    }
    if (sel.back().first == q[std::size_t(i0)].strike)
        throw Error("E_INPUT", "every out-of-the-money call is excluded", "strip");

    VixTermResult out;
    out.forward = fwd;
    out.k0 = q[i0].strike;
    out.t = t;
    double sum = 0.0;
    const std::size_t n = sel.size();
    for (std::size_t i = 0; i < n; ++i) {
        const double lo = sel[i == 0 ? 0 : i - 1].first, hi = sel[i + 1 == n ? i : i + 1].first;
        const double dk = (i == 0 || i + 1 == n) ? hi - lo : (hi - lo) / 2.0;
        sum += dk / (sel[i].first * sel[i].first) * sel[i].second;
        out.strikes_used.push_back(sel[i].first);
    }
    const double c = fwd / out.k0 - 1.0;
    out.variance = (2.0 / t) * growth * sum - c * c / t;
    return out;
}

VixIndex vix_index(const VixTerm& near, const VixTerm& next) {
    require_finite_term(near);
    require_finite_term(next);
    constexpr double n30 = 43200.0, n365 = 525600.0;
    const double n1 = double(near.minutes), n2 = double(next.minutes);
    if (!(n1 < n2 && n1 <= n30 && n30 <= n2))
        throw Error("E_INPUT", "the terms must bracket 30 days with near before next");
    const VixTermResult a = vix_term_variance(near), b = vix_term_variance(next);
    const double bracket = a.t * a.variance * (n2 - n30) / (n2 - n1) + b.t * b.variance * (n30 - n1) / (n2 - n1);
    if (bracket < 0.0) throw Error("E_DOMAIN", "the interpolated variance is negative");
    return {100.0 * std::sqrt(bracket * n365 / n30), a.variance, b.variance};
}

}  // namespace quantforge
