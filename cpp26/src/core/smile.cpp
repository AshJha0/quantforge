#include "quantforge/core/smile.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

[[noreturn]] void domain(const char* why) { throw Error("E_DOMAIN", why); }

double sum_squares(const Vec& r) {
    double s = 0.0;
    for (const double x : r) s += x * x;
    return std::isfinite(s) ? s : INFINITY;
}

// Gaussian elimination with pivoting, for the few parameters of a fit. False if singular.
bool solve_small(Matrix a, Vec b, Vec& x) {
    const std::size_t n = b.size();
    for (std::size_t c = 0; c < n; ++c) {
        std::size_t p = c;
        for (std::size_t r = c + 1; r < n; ++r)
            if (std::fabs(a[r][c]) > std::fabs(a[p][c])) p = r;
        if (a[p][c] == 0) return false;
        std::swap(a[p], a[c]);
        std::swap(b[p], b[c]);
        for (std::size_t r = c + 1; r < n; ++r) {
            const double f = a[r][c] / a[c][c];
            for (std::size_t j = c; j < n; ++j) a[r][j] -= f * a[c][j];
            b[r] -= f * b[c];
        }
    }
    x.assign(n, 0.0);
    for (std::size_t c = n; c-- > 0;) {
        double s = b[c];
        for (std::size_t j = c + 1; j < n; ++j) s -= a[c][j] * x[j];
        x[c] = s / a[c][c];
    }
    return true;
}

Vec descend(const Residuals& residuals, Vec p, double& cost) {
    const std::size_t n = p.size();
    Vec r = residuals(p);
    cost = sum_squares(r);
    if (!std::isfinite(cost)) return p;
    double lambda = 1e-3;
    int flat = 0;
    for (int iteration = 0; iteration < 400 && flat < 4 && cost > 1e-30; ++iteration) {
        Matrix jac(n);
        for (std::size_t i = 0; i < n; ++i) {
            const double h = 1e-6 * std::max(std::fabs(p[i]), 1e-2);
            Vec up = p, down = p;
            up[i] += h;
            down[i] -= h;
            const Vec ru = residuals(up), rd = residuals(down);
            jac[i].resize(r.size());
            for (std::size_t e = 0; e < r.size(); ++e) jac[i][e] = (ru[e] - rd[e]) / (2 * h);
        }
        Matrix a(n, Vec(n, 0.0));
        Vec g(n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j)
                for (std::size_t e = 0; e < r.size(); ++e) a[i][j] += jac[i][e] * jac[j][e];
            for (std::size_t e = 0; e < r.size(); ++e) g[i] -= jac[i][e] * r[e];
        }
        bool moved = false;
        for (int attempt = 0; attempt < 40 && !moved; ++attempt) {
            Matrix damped = a;
            for (std::size_t i = 0; i < n; ++i) damped[i][i] += lambda * std::max(a[i][i], 1e-30);
            Vec step;
            if (solve_small(damped, g, step)) {
                Vec next = p;
                for (std::size_t i = 0; i < n; ++i) next[i] += step[i];
                Vec rn = residuals(next);
                const double c = sum_squares(rn);
                if (c < cost) {
                    flat = cost - c <= 1e-13 * cost ? flat + 1 : 0;
                    p = std::move(next);
                    r = std::move(rn);
                    cost = c;
                    lambda = std::max(lambda / 5, 1e-14);
                    moved = true;
                    continue;
                }
            }
            lambda *= 4;
        }
        if (!moved) break;
    }
    return p;
}

double logistic(double x) { return 1.0 / (1.0 + std::exp(-x)); }

}  // namespace

Vec best_fit(const Residuals& r, const std::vector<Vec>& starts) {
    Vec best;
    double best_cost = INFINITY;
    for (const Vec& s : starts) {
        double cost = INFINITY;
        Vec p = descend(r, s, cost);
        if (cost < best_cost) {
            best_cost = cost;
            best = std::move(p);
        }
    }
    if (best.empty()) throw Error("E_NO_CONVERGENCE", "no start gave a finite fit");
    return best;
}

double normal_inverse(double p) {
    // Acklam's rational start, then Halley steps on the accurate normal_cdf.
    static constexpr double a[] = {-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
                                   1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00};
    static constexpr double b[] = {-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
                                   6.680131188771972e+01, -1.328068155288572e+01};
    static constexpr double c[] = {-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
                                   -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00};
    static constexpr double d[] = {7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00};
    double x;
    if (p < 0.02425 || p > 1 - 0.02425) {
        const double q = std::sqrt(-2 * std::log(p < 0.5 ? p : 1 - p));
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
        if (p > 0.5) x = -x;
    } else {
        const double q = p - 0.5, r = q * q;
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
    }
    for (int i = 0; i < 3; ++i) {
        const double e = p < 0.5 ? normal_cdf(x) - p : (1 - p) - normal_cdf(-x);
        const double u = e * std::sqrt(2 * std::numbers::pi) * std::exp(x * x / 2);
        x -= u / (1 + x * u / 2);
    }
    return x;
}

double delta_to_strike(double forward, double vol, double t, OptionType type, double delta, double scale) {
    require_finite(forward, "forward");
    require_finite(vol, "vol");
    require_finite(t, "expiry_years");
    require_finite(delta, "delta");
    require_finite(scale, "scale");
    if (forward <= 0 || vol <= 0 || t <= 0) domain("forward, vol and expiry_years must be above 0");
    const double phi = type == OptionType::Call ? 1.0 : -1.0, p = phi * delta / scale;
    if (!(p > 0 && p < 1)) domain("delta is out of range");
    const double d1 = phi * normal_inverse(p);
    return forward * std::exp(-d1 * vol * std::sqrt(t) + vol * vol * t / 2);
}

double delta_from_strike(double forward, double vol, double t, OptionType type, double strike, double scale) {
    require_finite(forward, "forward");
    require_finite(vol, "vol");
    require_finite(t, "expiry_years");
    require_finite(strike, "strike");
    require_finite(scale, "scale");
    if (forward <= 0 || vol <= 0 || t <= 0 || strike <= 0) domain("forward, vol, expiry_years and strike must be above 0");
    const double phi = type == OptionType::Call ? 1.0 : -1.0, s = vol * std::sqrt(t);
    return phi * scale * normal_cdf(phi * (std::log(forward / strike) + s * s / 2) / s);
}

double Svi::w(double k) const {
    const double x = k - m;
    return a + b * (rho * x + std::sqrt(x * x + sigma * sigma));
}

double Svi::g(double k) const {
    const double x = k - m, r = std::sqrt(x * x + sigma * sigma), v = w(k);
    const double w1 = b * (rho + x / r), w2 = b * sigma * sigma / (r * r * r);
    const double lead = 1 - k * w1 / (2 * v);
    return lead * lead - (w1 * w1 / 4) * (1 / v + 0.25) + w2 / 2;
}

void require_finite(const Svi& s, std::string_view field) {
    for (const double x : {s.a, s.b, s.rho, s.m, s.sigma}) require_finite(x, field);
}

void check_svi(const Svi& s) {
    require_finite(s, "svi");
    if (s.b < 0 || std::fabs(s.rho) >= 1 || s.sigma <= 0 || s.a + s.b * s.sigma * std::sqrt(1 - s.rho * s.rho) <= 0)
        domain("svi parameters are out of domain");
}

SviFit svi_calibrate(const Vec& k, const Vec& w, const std::optional<Vec>& weights) {
    require_finite(k, "log_moneyness");
    require_finite(w, "total_variance");
    require_finite(weights, "weights");
    const std::size_t n = k.size();
    if (n != w.size() || (weights && weights->size() != n) || n < 5) throw Error("E_INPUT", "too few points, or lengths differ");
    for (std::size_t i = 1; i < n; ++i)
        if (!(k[i - 1] < k[i])) throw Error("E_INPUT", "log_moneyness not strictly increasing");
    for (const double x : w)
        if (x <= 0) domain("total_variance is not above 0");
    if (weights)
        for (const double x : *weights)
            if (x <= 0) domain("weight is not above 0");
    const auto weight = [&](std::size_t i) { return weights ? (*weights)[i] : 1.0; };

    // p = (log excess over the floor of a, log b, atanh rho, m, log sigma): the domain holds by construction.
    const auto unpack = [](const Vec& p) {
        const double b = std::exp(p[1]), rho = std::tanh(p[2]), sigma = std::exp(p[4]);
        return Svi{std::exp(p[0]) - b * sigma * std::sqrt(1 - rho * rho), b, rho, p[3], sigma};
    };
    const Residuals residuals = [&](const Vec& p) {
        const Svi s = unpack(p);
        Vec r(n);
        for (std::size_t i = 0; i < n; ++i) r[i] = std::sqrt(weight(i)) * (s.w(k[i]) - w[i]);
        return r;
    };

    // Each start fixes rho, m, sigma; a and b then come from the linear fit they leave.
    std::vector<Vec> starts;
    const double span = k.back() - k.front(), mid = (k.back() + k.front()) / 2;
    double mean_w = 0.0;
    for (const double x : w) mean_w += x / double(n);
    for (const double rho : {-0.7, -0.3, 0.0, 0.3, 0.7})
        for (const double m : {mid - 0.25 * span, mid, mid + 0.25 * span, 0.0})
            for (const double sigma : {0.03 * span, 0.1 * span, 0.3 * span, span}) {
                double s0 = 0, s1 = 0, s2 = 0, t0 = 0, t1 = 0;
                for (std::size_t i = 0; i < n; ++i) {
                    const double x = k[i] - m, f = rho * x + std::sqrt(x * x + sigma * sigma), c = weight(i);
                    s0 += c;
                    s1 += c * f;
                    s2 += c * f * f;
                    t0 += c * w[i];
                    t1 += c * f * w[i];
                }
                const double det = s0 * s2 - s1 * s1;
                double b = det != 0 ? (s0 * t1 - s1 * t0) / det : 0.0;
                if (b <= 1e-6) b = 0.1 * mean_w / std::max(span, 1e-6);
                const double a = (t0 - b * s1) / s0;
                const double excess = std::max(a + b * sigma * std::sqrt(1 - rho * rho), 1e-3 * mean_w);
                starts.push_back({std::log(excess), std::log(b), std::atanh(rho), m, std::log(sigma)});
            }
    const Vec p = best_fit(residuals, starts);
    double total = 0.0, sum_weight = 0.0;
    const Vec r = residuals(p);
    for (std::size_t i = 0; i < n; ++i) {
        total += r[i] * r[i];
        sum_weight += weight(i);
    }
    return {unpack(p), std::sqrt(total / sum_weight)};
}

double Ssvi::phi(double theta) const { return eta * std::pow(theta, -gamma) * std::pow(1 + theta, gamma - 1); }

double Ssvi::w(double k, double theta) const {
    const double x = phi(theta) * k;
    return theta / 2 * (1 + rho * x + std::sqrt((x + rho) * (x + rho) + 1 - rho * rho));
}

namespace {
void require_finite_ssvi(const Ssvi& s, const Vec& thetas) {
    for (const double x : {s.rho, s.eta, s.gamma}) require_finite(x, "ssvi");
    require_finite(thetas, "thetas");
}
}  // namespace

void check_ssvi(const Ssvi& s, const Vec& thetas) {
    require_finite_ssvi(s, thetas);
    if (std::fabs(s.rho) >= 1 || s.eta <= 0 || s.gamma <= 0 || s.gamma > 1) domain("ssvi parameters are out of domain");
    for (const double t : thetas)
        if (t <= 0) domain("theta is not above 0");
    for (std::size_t i = 1; i < thetas.size(); ++i)
        if (!(thetas[i - 1] < thetas[i])) throw Error("E_INPUT", "thetas not strictly increasing");
}

bool ssvi_butterfly_free(const Ssvi& s, const Vec& thetas) {
    require_finite_ssvi(s, thetas);
    const double lift = 1 + std::fabs(s.rho);
    return std::ranges::all_of(thetas, [&](double t) {
        const double p = s.phi(t);
        return t * p * lift < 4 && t * p * p * lift <= 4;
    });
}

bool ssvi_calendar_free(const Ssvi& s, const Vec& thetas) {
    require_finite_ssvi(s, thetas);
    const double bound = 1 + std::sqrt(1 - s.rho * s.rho);
    return std::ranges::all_of(thetas, [&](double t) { return s.rho * s.rho * (1 - s.gamma) / (1 + t) <= bound; });
}

SsviFit ssvi_calibrate(const Vec& thetas, const Vec& k, const Matrix& w) {
    require_finite(thetas, "thetas");
    require_finite(k, "log_moneyness");
    require_finite(w, "total_variance");
    if (w.size() != thetas.size()) throw Error("E_INPUT", "rows do not match thetas");
    for (const Vec& row : w)
        if (row.size() != k.size()) throw Error("E_INPUT", "ragged rows");
    if (thetas.size() * k.size() < 3) throw Error("E_INPUT", "fewer than 3 points");
    check_ssvi({0.0, 1.0, 0.5}, thetas);

    const auto unpack = [](const Vec& p) { return Ssvi{std::tanh(p[0]), std::exp(p[1]), logistic(p[2])}; };
    const Residuals residuals = [&](const Vec& p) {
        const Ssvi s = unpack(p);
        Vec r;
        r.reserve(thetas.size() * k.size());
        for (std::size_t j = 0; j < thetas.size(); ++j)
            for (std::size_t i = 0; i < k.size(); ++i) r.push_back(s.w(k[i], thetas[j]) - w[j][i]);
        return r;
    };
    std::vector<Vec> starts;
    for (const double rho : {-0.6, -0.2, 0.2, 0.6})
        for (const double eta : {0.3, 1.0, 3.0})
            for (const double gamma : {0.25, 0.5, 0.75}) starts.push_back({std::atanh(rho), std::log(eta), std::log(gamma / (1 - gamma))});
    const Vec p = best_fit(residuals, starts);
    const Vec r = residuals(p);
    return {unpack(p), std::sqrt(sum_squares(r) / double(r.size()))};
}

}  // namespace quantforge
