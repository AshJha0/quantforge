#include "quantforge/core/heston.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

using cd = std::complex<double>;
constexpr std::size_t max_grid = 1000, max_steps = 10000;

void domain(const char* why, const char* key) { throw Error("E_DOMAIN", why, key); }

// 1024-point Gauss-Legendre nodes and weights on [-1, 1], by Newton on the Legendre recurrence.
struct Rule {
    std::array<double, 1024> t, w;
};
const Rule& legendre_1024() {
    static const Rule rule = [] {
        Rule r{};
        constexpr int n = 1024;
        for (int i = 0; i < n / 2; ++i) {
            double x = std::cos(std::numbers::pi * (i + 0.75) / (n + 0.5)), dp = 0.0;
            for (int it = 0; it < 100; ++it) {
                double p0 = 1.0, p1 = x;
                for (int k = 2; k <= n; ++k) {
                    const double p2 = ((2.0 * k - 1.0) * x * p1 - (k - 1.0) * p0) / k;
                    p0 = p1;
                    p1 = p2;
                }
                dp = n * (x * p1 - p0) / (x * x - 1.0);
                const double dx = p1 / dp;
                x -= dx;
                if (std::fabs(dx) < 1e-16) break;
            }
            const double w = 2.0 / ((1.0 - x * x) * dp * dp);
            r.t[i] = -x, r.w[i] = w;
            r.t[n - 1 - i] = x, r.w[n - 1 - i] = w;
        }
        return r;
    }();
    return rule;
}

void check_option(const EquityOption& o) {
    if (o.strikes.empty()) throw Error("E_INPUT", "strikes is empty", "strikes");
    if (!(o.spot > 0)) domain("spot is not above 0", "spot");
    if (!(o.expiry_years > 0)) domain("expiry_years is not above 0", "expiry_years");
    for (const double k : o.strikes)
        if (!(k > 0)) domain("a strike is not above 0", "strikes");
}

// Lewis's single integral [Lew01] for a characteristic function of ln(S_T/F): Gauss-Legendre 1024 on
// [0, 200/sqrt(min(T, 1))] (ruling E-A26).
std::vector<double> lewis(const EquityOption& o, auto&& phi) {
    const double t = o.expiry_years, f = o.spot * std::exp((o.rate - o.dividend_yield) * t);
    const double d = std::exp(-o.rate * t);
    const Rule& r = legendre_1024();
    const double half = 100.0 / std::sqrt(std::min(t, 1.0));
    std::vector<cd> ph(1024);
    for (int i = 0; i < 1024; ++i) ph[i] = phi(cd(half + half * r.t[i], -0.5));
    std::vector<double> out;
    for (const double strike : o.strikes) {
        const double k = std::log(f / strike);
        double sum = 0.0;
        for (int i = 0; i < 1024; ++i) {
            const double u = half + half * r.t[i];
            sum += r.w[i] * (std::exp(cd(0.0, u * k)) * ph[i]).real() / (u * u + 0.25);
        }
        const double call = d * (f - std::sqrt(f * strike) / std::numbers::pi * half * sum);
        out.push_back(o.type == OptionType::Call ? call : call - d * (f - strike));
    }
    return out;
}

cd jump_cf(double t, const Jumps& j, cd u) {
    const double kbar = std::exp(j.mean_log_jump + j.log_jump_vol * j.log_jump_vol / 2) - 1;
    const cd i(0.0, 1.0);
    return std::exp(j.intensity * t *
                    (std::exp(i * u * j.mean_log_jump - j.log_jump_vol * j.log_jump_vol * u * u / 2.0) - 1.0 - i * u * kbar));
}

// Thomas algorithm, no pivoting: a lower, b diagonal, c upper; solves in place into d.
void thomas(const std::vector<double>& a, std::vector<double> b, const std::vector<double>& c, std::vector<double>& d) {
    const std::size_t n = d.size();
    for (std::size_t k = 0; k < n; ++k) {
        if (k > 0) {
            const double m = a[k] / b[k - 1];
            b[k] -= m * c[k - 1];
            d[k] -= m * d[k - 1];
        }
    }
    d[n - 1] /= b[n - 1];
    for (std::size_t k = n - 1; k-- > 0;) d[k] = (d[k] - c[k] * d[k + 1]) / b[k];
}

// Rows of (I - dt A) for one line (heston-family.md, "Operator rows").
void operator_rows(const std::vector<double>& mu, const std::vector<double>& s, double h, double dt, bool no_flux,
                   std::vector<double>& lo, std::vector<double>& di, std::vector<double>& up) {
    const std::size_t n = mu.size();
    std::vector<double> face(n + 1);
    face[0] = no_flux ? 0.0 : mu[0];
    face[n] = no_flux ? 0.0 : mu[n - 1];
    for (std::size_t k = 1; k < n; ++k) face[k] = (mu[k - 1] + mu[k]) / 2;
    const auto pos = [](double x) { return std::max(x, 0.0); };
    const auto neg = [](double x) { return std::min(x, 0.0); };
    lo.assign(n, 0.0), di.assign(n, 0.0), up.assign(n, 0.0);
    for (std::size_t k = 0; k < n; ++k) {
        const bool end = k == 0 || k + 1 == n;
        di[k] = 1.0 + dt * s[k] / (h * h) * (no_flux && end ? 0.5 : 1.0) + dt * (pos(face[k + 1]) - neg(face[k])) / h;
        if (k + 1 < n) up[k] = -dt * s[k + 1] / (2 * h * h) + dt * neg(face[k + 1]) / h;
        if (k > 0) lo[k] = -dt * s[k - 1] / (2 * h * h) - dt * pos(face[k]) / h;
    }
}

}  // namespace

void check_heston(const HestonParams& h) {
    require_finite(h.v0, "heston");
    require_finite(h.kappa, "heston");
    require_finite(h.theta, "heston");
    require_finite(h.xi, "heston");
    require_finite(h.rho, "heston");
    if (!(h.v0 > 0)) domain("v0 is not above 0", "heston");
    if (!(h.kappa > 0)) domain("kappa is not above 0", "heston");
    if (!(h.theta > 0)) domain("theta is not above 0", "heston");
    if (!(h.xi > 0)) domain("xi is not above 0", "heston");
    if (!(std::fabs(h.rho) < 1)) domain("|rho| is not below 1", "heston");
}

void check_jumps(const Jumps& j) {
    require_finite(j.intensity, "jumps");
    require_finite(j.mean_log_jump, "jumps");
    require_finite(j.log_jump_vol, "jumps");
    if (!(j.intensity >= 0)) domain("intensity is negative", "jumps");
    if (!(j.log_jump_vol >= 0)) domain("log_jump_vol is negative", "jumps");
}

cd heston_cf(double t, const HestonParams& h, cd u) {
    const cd i(0.0, 1.0);
    const double x2 = h.xi * h.xi;
    const cd b = h.kappa - h.rho * h.xi * i * u;
    const cd d = std::sqrt(b * b + x2 * (i * u + u * u));
    const cd g = (b - d) / (b + d), e = std::exp(-d * t);
    const cd c = (h.kappa / x2) * ((b - d) * t - 2.0 * std::log((1.0 - g * e) / (1.0 - g)));
    const cd dd = ((b - d) / x2) * (1.0 - e) / (1.0 - g * e);
    return std::exp(c * h.theta + dd * h.v0);
}

std::vector<double> heston_price(const EquityOption& o, const HestonParams& h) {
    require_finite(o.spot, "spot");
    require_finite(o.expiry_years, "expiry_years");
    require_finite(o.rate, "rate");
    require_finite(o.dividend_yield, "dividend_yield");
    require_finite(o.strikes, "strikes");
    require_finite(h.v0, "heston");
    require_finite(h.kappa, "heston");
    require_finite(h.theta, "heston");
    require_finite(h.xi, "heston");
    require_finite(h.rho, "heston");
    check_option(o);
    check_heston(h);
    return lewis(o, [&](cd u) { return heston_cf(o.expiry_years, h, u); });
}

std::vector<double> bates_price(const EquityOption& o, const HestonParams& h, const Jumps& j) {
    require_finite(o.spot, "spot");
    require_finite(o.expiry_years, "expiry_years");
    require_finite(o.rate, "rate");
    require_finite(o.dividend_yield, "dividend_yield");
    require_finite(o.strikes, "strikes");
    require_finite(h.v0, "heston");
    require_finite(h.kappa, "heston");
    require_finite(h.theta, "heston");
    require_finite(h.xi, "heston");
    require_finite(h.rho, "heston");
    require_finite(j.intensity, "jumps");
    require_finite(j.mean_log_jump, "jumps");
    require_finite(j.log_jump_vol, "jumps");
    check_option(o);
    check_heston(h);
    check_jumps(j);
    return lewis(o, [&](cd u) { return heston_cf(o.expiry_years, h, u) * jump_cf(o.expiry_years, j, u); });
}

std::vector<double> merton_price(const EquityOption& o, double vol, const Jumps& j) {
    require_finite(o.spot, "spot");
    require_finite(o.expiry_years, "expiry_years");
    require_finite(o.rate, "rate");
    require_finite(o.dividend_yield, "dividend_yield");
    require_finite(o.strikes, "strikes");
    require_finite(vol, "vol");
    require_finite(j.intensity, "jumps");
    require_finite(j.mean_log_jump, "jumps");
    require_finite(j.log_jump_vol, "jumps");
    check_option(o);
    if (!(vol > 0)) domain("vol is not above 0", "vol");
    check_jumps(j);
    const double t = o.expiry_years, delta2 = j.log_jump_vol * j.log_jump_vol;
    const double kbar = std::exp(j.mean_log_jump + delta2 / 2) - 1, lt = j.intensity * (1 + kbar) * t;
    const double phi = o.type == OptionType::Call ? 1.0 : -1.0;
    std::vector<double> out(o.strikes.size(), 0.0);
    double weight = std::exp(-lt), total = 0.0;
    for (int n = 0; n < 200; ++n) {
        if (n > 0) weight *= lt / n;
        const double vn = std::sqrt(vol * vol + n * delta2 / t);
        const double rn = o.rate - j.intensity * kbar + n * std::log(1 + kbar) / t;
        const double f = o.spot * std::exp((rn - o.dividend_yield) * t), d = std::exp(-rn * t);
        for (std::size_t i = 0; i < o.strikes.size(); ++i) out[i] += weight * black_price(f, o.strikes[i], vn, t, d, phi);
        total += weight;
        if (total >= 1 - 1e-16) break;
    }
    return out;
}

SlvLeverage slv_leverage(double spot, double t, double r, double q, const HestonParams& h,
                         const std::vector<SviSlice>& slices, const SlvGrid& g) {
    // E_LIMIT right after schema (ruling E-A34), then every E_INPUT rule, then E_DOMAIN, each in input order (E-A37).
    if (slices.size() > 100) throw Error("E_LIMIT", "slices is above its limit", "slices");
    if (g.nx > (long long)max_grid || g.nv > (long long)max_grid || g.nt > (long long)max_steps)
        throw Error("E_LIMIT", "the grid is above its limit", "grid");
    require_finite(spot, "spot");
    require_finite(t, "expiry_years");
    require_finite(r, "rate");
    require_finite(q, "dividend_yield");
    require_finite(h.v0, "heston");
    require_finite(h.kappa, "heston");
    require_finite(h.theta, "heston");
    require_finite(h.xi, "heston");
    require_finite(h.rho, "heston");
    require_finite(slices, "slices");
    require_finite(g.x_min, "grid");
    require_finite(g.x_max, "grid");
    require_finite(g.v_max, "grid");
    check_slices_input(slices);
    if (g.nx < 5 || g.nv < 5 || g.nt < 2) throw Error("E_INPUT", "nx and nv need 5, nt needs 2", "grid");
    if (!(g.x_min < std::log(spot) && std::log(spot) < g.x_max))
        throw Error("E_INPUT", "x_min < ln(spot) < x_max is needed", "grid");
    if (!(spot > 0)) domain("spot is not above 0", "spot");
    if (!(t > 0)) domain("expiry_years is not above 0", "expiry_years");
    check_heston(h);
    check_slices_domain(slices);
    if (!(g.v_max > 0)) domain("v_max is not above 0", "grid");

    const std::size_t nx = std::size_t(g.nx), nv = std::size_t(g.nv);
    const double dx = (g.x_max - g.x_min) / double(nx - 1), dv = g.v_max / double(nv + 1), dt = t / double(g.nt);
    std::vector<double> x(nx), v(nv);
    for (std::size_t i = 0; i < nx; ++i) x[i] = g.x_min + double(i) * dx;
    for (std::size_t j = 0; j < nv; ++j) v[j] = double(j + 1) * dv;
    const double ls = std::log(spot);
    // Local variance at time tt on the x grid (k = x - ln F(tt)).
    const auto local_var = [&](double tt, const std::vector<double>& xs) {
        std::vector<LocalVolPoint> pts;
        for (const double xx : xs) pts.push_back({tt, xx - ls - (r - q) * tt});
        std::vector<double> lv = local_vol_dupire(slices, pts).local_vol;
        for (double& s : lv) s *= s;
        return lv;
    };
    using Grid = std::vector<std::vector<double>>;  // p[i][j]
    const auto leverage2 = [&](double tt, const Grid& p) {
        std::vector<double> m(nx, 0.0), e(nx, 0.0);
        for (std::size_t i = 0; i < nx; ++i)
            for (std::size_t j = 0; j < nv; ++j) m[i] += p[i][j], e[i] += v[j] * p[i][j];
        const double eps = 1e-10 * *std::max_element(m.begin(), m.end());
        double se = 0.0, sm = 0.0;
        for (std::size_t i = 0; i < nx; ++i) se += e[i], sm += m[i];
        const double ebar = se / sm;
        std::vector<double> l2 = local_var(tt, x);
        for (std::size_t i = 0; i < nx; ++i) l2[i] /= (e[i] + eps * ebar) / (m[i] + eps);
        return l2;
    };

    // Start density at t_1 = dt.
    const double l0 = local_var(dt, {ls + (r - q) * dt})[0] / h.v0;
    const double mx = ls + (r - q - l0 * h.v0 / 2) * dt, mv = h.v0 + h.kappa * (h.theta - h.v0) * dt;
    const double sx = std::max(std::sqrt(l0 * h.v0 * dt), 2 * dx), sv = std::max(h.xi * std::sqrt(h.v0 * dt), 2 * dv);
    const double c = 1 - h.rho * h.rho;
    Grid p(nx, std::vector<double>(nv));
    double total = 0.0;
    for (std::size_t i = 0; i < nx; ++i)
        for (std::size_t j = 0; j < nv; ++j) {
            const double a = (x[i] - mx) / sx, b = (v[j] - mv) / sv;
            p[i][j] = std::exp(-(a * a - 2 * h.rho * a * b + b * b) / (2 * c)) / (2 * std::numbers::pi * sx * sv * std::sqrt(c));
            total += p[i][j];
        }
    for (auto& row : p)
        for (double& y : row) y /= total * dx * dv;

    std::vector<double> lo, di, up, rhs;
    for (long long n = 1; n < g.nt; ++n) {
        const std::vector<double> l2 = leverage2(double(n) * dt, p);
        // 1. Mixed term, explicit, interior nodes.
        Grid ps = p;
        const auto f = [&](std::size_t i, std::size_t j) { return h.rho * h.xi * std::sqrt(l2[i]) * v[j] * p[i][j]; };
        for (std::size_t i = 1; i + 1 < nx; ++i)
            for (std::size_t j = 1; j + 1 < nv; ++j)
                ps[i][j] = p[i][j] + dt * (f(i + 1, j + 1) - f(i + 1, j - 1) - f(i - 1, j + 1) + f(i - 1, j - 1)) / (4 * dx * dv);
        // 2. x, implicit, Dirichlet ends.
        std::vector<double> mu(nx), s(nx);
        for (std::size_t j = 0; j < nv; ++j) {
            for (std::size_t i = 0; i < nx; ++i) mu[i] = r - q - l2[i] * v[j] / 2, s[i] = l2[i] * v[j];
            operator_rows(mu, s, dx, dt, false, lo, di, up);
            lo[nx - 1] = 0, di[0] = di[nx - 1] = 1, up[0] = 0;
            rhs.resize(nx);
            for (std::size_t i = 0; i < nx; ++i) rhs[i] = ps[i][j];
            rhs[0] = rhs[nx - 1] = 0;
            thomas(lo, di, up, rhs);
            for (std::size_t i = 0; i < nx; ++i) ps[i][j] = rhs[i];
        }
        // 3. v, implicit, no-flux.
        std::vector<double> muv(nv), sv2(nv);
        for (std::size_t j = 0; j < nv; ++j) muv[j] = h.kappa * (h.theta - v[j]), sv2[j] = h.xi * h.xi * v[j];
        operator_rows(muv, sv2, dv, dt, true, lo, di, up);
        for (std::size_t i = 0; i < nx; ++i) {
            rhs = ps[i];
            thomas(lo, di, up, rhs);
            // 4. Floor.
            for (std::size_t j = 0; j < nv; ++j) p[i][j] = std::max(rhs[j], 0.0);
        }
    }
    SlvLeverage out;
    out.x = x;
    for (const double l : leverage2(t, p)) out.leverage.push_back(std::sqrt(l));
    out.mass = 0.0;
    for (const auto& row : p)
        for (const double y : row) out.mass += y * dx * dv;
    return out;
}

}  // namespace quantforge
