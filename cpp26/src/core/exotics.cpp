#include "quantforge/core/exotics.hpp"

#include <algorithm>
#include <cmath>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

void positive(double x, const char* key) {
    if (!(x > 0)) throw Error("E_DOMAIN", std::string(key) + " is not above 0", key);
}

void check_common(const ExoticMarket& m, bool with_strike = true) {
    positive(m.spot, "spot");
    if (with_strike) positive(m.strike, "strike");
    positive(m.expiry_years, "expiry_years");
    positive(m.vol, "vol");
}

double phi_of(OptionType t) { return t == OptionType::Call ? 1.0 : -1.0; }
double N(double x) { return normal_cdf(x); }

// Bisection to the last representable step; f(lo) and f(hi) of opposite signs.
double bisect(auto&& f, double lo, double hi) {
    const bool rising = f(hi) > f(lo);
    for (int i = 0; i < 400; ++i) {
        const double mid = 0.5 * (lo + hi);
        if (mid <= lo || mid >= hi) break;
        if ((f(mid) < 0) == rising) lo = mid;
        else hi = mid;
    }
    return 0.5 * (lo + hi);
}

void thomas(const std::vector<double>& a, std::vector<double> b, const std::vector<double>& c, std::vector<double>& d) {
    const std::size_t n = d.size();
    for (std::size_t k = 1; k < n; ++k) {
        const double w = a[k] / b[k - 1];
        b[k] -= w * c[k - 1];
        d[k] -= w * d[k - 1];
    }
    d[n - 1] /= b[n - 1];
    for (std::size_t k = n - 1; k-- > 0;) d[k] = (d[k] - c[k] * d[k + 1]) / b[k];
}

}  // namespace

double gbs(OptionType type, double s, double k, double t, double r, double b, double v) {
    const double sd = v * std::sqrt(t), d1 = (std::log(s / k) + (b + v * v / 2) * t) / sd, d2 = d1 - sd;
    const double carry = s * std::exp((b - r) * t), disc = k * std::exp(-r * t);
    return type == OptionType::Call ? carry * N(d1) - disc * N(d2) : disc * N(-d2) - carry * N(-d1);
}

double digital_price(const ExoticMarket& m, DigitalPayoff payoff, double cash) {
    check_common(m);
    positive(cash, "cash");
    const double t = m.expiry_years, sd = m.vol * std::sqrt(t), b = m.rate - m.dividend_yield, phi = phi_of(m.type);
    const double d1 = (std::log(m.spot / m.strike) + (b + m.vol * m.vol / 2) * t) / sd, d2 = d1 - sd;
    return payoff == DigitalPayoff::CashOrNothing ? cash * std::exp(-m.rate * t) * N(phi * d2)
                                                  : m.spot * std::exp(-m.dividend_yield * t) * N(phi * d1);
}

double barrier_price(const ExoticMarket& m, double h, double rebate, BarrierType type) {
    check_common(m);
    positive(h, "barrier");
    if (!(rebate >= 0)) throw Error("E_DOMAIN", "rebate is negative", "rebate");
    const bool down = type == BarrierType::DownIn || type == BarrierType::DownOut;
    if (down ? m.spot <= h : m.spot >= h) throw Error("E_DOMAIN", "spot is on or beyond the barrier", "barrier");
    const double s = m.spot, k = m.strike, t = m.expiry_years, r = m.rate, v = m.vol, b = r - m.dividend_yield;
    const double sd = v * std::sqrt(t), mu = (b - v * v / 2) / (v * v), lam = std::sqrt(mu * mu + 2 * r / (v * v));
    const double phi = phi_of(m.type), eta = down ? 1.0 : -1.0;
    const double x1 = std::log(s / k) / sd + (1 + mu) * sd, x2 = std::log(s / h) / sd + (1 + mu) * sd;
    const double y1 = std::log(h * h / (s * k)) / sd + (1 + mu) * sd, y2 = std::log(h / s) / sd + (1 + mu) * sd;
    const double z = std::log(h / s) / sd + lam * sd;
    const double carry = s * std::exp((b - r) * t), disc = k * std::exp(-r * t), hs = h / s;
    const double A = phi * carry * N(phi * x1) - phi * disc * N(phi * x1 - phi * sd);
    const double B = phi * carry * N(phi * x2) - phi * disc * N(phi * x2 - phi * sd);
    const double C = phi * carry * std::pow(hs, 2 * (mu + 1)) * N(eta * y1) - phi * disc * std::pow(hs, 2 * mu) * N(eta * y1 - eta * sd);
    const double D = phi * carry * std::pow(hs, 2 * (mu + 1)) * N(eta * y2) - phi * disc * std::pow(hs, 2 * mu) * N(eta * y2 - eta * sd);
    const double E = rebate * std::exp(-r * t) * (N(eta * x2 - eta * sd) - std::pow(hs, 2 * mu) * N(eta * y2 - eta * sd));
    const double F = rebate * (std::pow(hs, mu + lam) * N(eta * z) + std::pow(hs, mu - lam) * N(eta * z - 2 * eta * lam * sd));
    const bool call = m.type == OptionType::Call, above = k > h;
    switch (type) {
        case BarrierType::DownIn:
            if (call) return above ? C + E : A - B + D + E;
            return above ? B - C + D + E : A + E;
        case BarrierType::UpIn:
            if (call) return above ? A + E : B - C + D + E;
            return above ? A - B + D + E : C + E;
        case BarrierType::DownOut:
            if (call) return above ? A - C + F : B - D + F;
            return above ? A - B + C - D + F : F;
        case BarrierType::UpOut:
            if (call) return above ? F : A - B + C - D + F;
            return above ? B - D + F : A - C + F;
    }
    return 0.0;
}

double asian_geometric(const ExoticMarket& m, bool continuous, const std::vector<double>& fix) {
    if (continuous) {
        if (!fix.empty()) throw Error("E_INPUT", "CONTINUOUS takes no fixing_years", "fixing_years");
    } else {
        if (fix.empty()) throw Error("E_INPUT", "DISCRETE needs fixing_years", "fixing_years");
        for (std::size_t i = 1; i < fix.size(); ++i)
            if (!(fix[i - 1] < fix[i])) throw Error("E_INPUT", "fixing_years must increase", "fixing_years");
    }
    check_common(m);
    const double t = m.expiry_years, v = m.vol, b = m.rate - m.dividend_yield;
    if (!continuous)
        for (const double f : fix)
            if (!(f > 0 && f <= t)) throw Error("E_INPUT", "a fixing is outside (0, T]", "fixing_years");
    if (continuous) return gbs(m.type, m.spot, m.strike, t, m.rate, (b - v * v / 6) / 2, v / std::sqrt(3.0));
    const double n = double(fix.size());
    double mean = 0.0, sum = 0.0;
    for (const double a : fix) {
        mean += a / n;
        for (const double c : fix) sum += std::min(a, c);
    }
    const double mm = std::log(m.spot) + (b - v * v / 2) * mean, var = v * v * sum / (n * n);
    const double d1 = (mm - std::log(m.strike) + var) / std::sqrt(var), d2 = d1 - std::sqrt(var);
    const double fwd = std::exp(mm + var / 2), disc = std::exp(-m.rate * t);
    return m.type == OptionType::Call ? disc * (fwd * N(d1) - m.strike * N(d2)) : disc * (m.strike * N(-d2) - fwd * N(-d1));
}

double lookback_floating(const ExoticMarket& m, double ext) {
    check_common(m, false);
    const bool call = m.type == OptionType::Call;
    if (call ? !(ext > 0 && ext <= m.spot) : !(ext >= m.spot))
        throw Error("E_DOMAIN", "running_extreme is on the wrong side of spot", "running_extreme");
    const double s = m.spot, t = m.expiry_years, r = m.rate, v = m.vol, b = r - m.dividend_yield;
    if (std::fabs(b) <= 1e-8 * v * v) throw Error("E_DOMAIN", "cost of carry too near 0 (ruling E-A28)", "dividend_yield");
    const double sd = v * std::sqrt(t), a1 = (std::log(s / ext) + (b + v * v / 2) * t) / sd, a2 = a1 - sd;
    const double scale = s * std::exp(-r * t) * v * v / (2 * b), pw = std::pow(s / ext, -2 * b / (v * v));
    const double reflect = 2 * b * std::sqrt(t) / v;
    if (call)
        return s * std::exp((b - r) * t) * N(a1) - ext * std::exp(-r * t) * N(a2) +
               scale * (pw * N(-a1 + reflect) - std::exp(b * t) * N(-a1));
    return -s * std::exp((b - r) * t) * N(-a1) + ext * std::exp(-r * t) * N(-a2) +
           scale * (-pw * N(a1 - reflect) + std::exp(b * t) * N(a1));
}

double quanto_price(const QuantoInputs& q) {
    positive(q.spot, "spot");
    positive(q.strike, "strike");
    positive(q.expiry_years, "expiry_years");
    positive(q.vol, "vol");
    positive(q.fx_vol, "fx_vol");
    if (!(q.correlation >= -1 && q.correlation <= 1)) throw Error("E_DOMAIN", "correlation is outside [-1, 1]", "correlation");
    return gbs(q.type, q.spot, q.strike, q.expiry_years, q.domestic_rate,
               q.foreign_rate - q.dividend_yield - q.correlation * q.vol * q.fx_vol, q.vol);
}

double chooser_price(const ExoticMarket& m, double tc) {
    check_common(m);
    if (!(tc > 0 && tc <= m.expiry_years)) throw Error("E_INPUT", "choose_years must be in (0, T]", "choose_years");
    const double s = m.spot, k = m.strike, t = m.expiry_years, r = m.rate, v = m.vol, b = r - m.dividend_yield;
    const double d = (std::log(s / k) + (b + v * v / 2) * t) / (v * std::sqrt(t));
    const double y = (std::log(s / k) + b * t + v * v * tc / 2) / (v * std::sqrt(tc));
    const double carry = s * std::exp((b - r) * t), disc = k * std::exp(-r * t);
    return carry * N(d) - disc * N(d - v * std::sqrt(t)) - carry * N(-y) + disc * N(-y + v * std::sqrt(tc));
}

double kirk_spread(double f1, double f2, double k, double t, double r, double v1, double v2, double rho) {
    positive(f1, "forward_1");
    positive(f2, "forward_2");
    if (!(f2 + k > 0)) throw Error("E_DOMAIN", "forward_2 + strike is not above 0", "strike");
    positive(t, "expiry_years");
    positive(v1, "vol_1");
    positive(v2, "vol_2");
    if (!(rho >= -1 && rho <= 1)) throw Error("E_DOMAIN", "correlation is outside [-1, 1]", "correlation");
    const double f = f2 / (f2 + k), s = std::sqrt(v1 * v1 - 2 * rho * v1 * v2 * f + v2 * v2 * f * f);
    const double d1 = (std::log(f1 / (f2 + k)) + s * s * t / 2) / (s * std::sqrt(t));
    return std::exp(-r * t) * (f1 * N(d1) - (f2 + k) * N(d1 - s * std::sqrt(t)));
}

BasketPrice basket_moment(const std::vector<double>& f, const std::vector<double>& w, const std::vector<double>& v,
                          const Matrix& c, double k, double t, double r, OptionType type) {
    const std::size_t n = f.size();
    if (n == 0 || w.size() != n || v.size() != n) throw Error("E_INPUT", "forwards, weights and vols differ in length");
    if (c.size() != n) throw Error("E_INPUT", "correlation is not n x n", "correlation");
    for (std::size_t i = 0; i < n; ++i) {
        if (c[i].size() != n) throw Error("E_INPUT", "correlation is not n x n", "correlation");
        if (c[i][i] != 1.0) throw Error("E_INPUT", "correlation needs a unit diagonal", "correlation");
    }
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j)
            if (c[i][j] != c[j][i] || !(c[i][j] >= -1 && c[i][j] <= 1))
                throw Error("E_INPUT", "correlation must be symmetric with entries in [-1, 1]", "correlation");
    for (const double x : f) positive(x, "forwards");
    bool any = false;
    for (const double x : w) {
        if (!(x >= 0)) throw Error("E_DOMAIN", "a weight is negative", "weights");
        any = any || x > 0;
    }
    if (!any) throw Error("E_DOMAIN", "all weights are 0", "weights");
    for (const double x : v) positive(x, "vols");
    positive(k, "strike");
    positive(t, "expiry_years");
    double m1 = 0.0, m2 = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        m1 += w[i] * f[i];
        for (std::size_t j = 0; j < n; ++j) m2 += w[i] * w[j] * f[i] * f[j] * std::exp(c[i][j] * v[i] * v[j] * t);
    }
    const double vb = std::sqrt(std::log(m2 / (m1 * m1)) / t);
    return {gbs(type, m1, k, t, r, 0.0, vb), m1, vb};
}

AmericanTree american_crr(const ExoticMarket& m, long long steps) {
    if (steps < 1) throw Error("E_INPUT", "steps must be at least 1", "steps");
    if (steps > 20000) throw Error("E_LIMIT", "steps is above its limit", "steps");
    check_common(m);
    const std::size_t n = std::size_t(steps);
    const double dt = m.expiry_years / double(n), u = std::exp(m.vol * std::sqrt(dt)), d = 1 / u;
    const double p = (std::exp((m.rate - m.dividend_yield) * dt) - d) / (u - d);
    if (!(p > 0 && p < 1)) throw Error("E_DOMAIN", "the tree probability is outside (0, 1)");
    const double disc = std::exp(-m.rate * dt), phi = phi_of(m.type);
    std::vector<double> am(n + 1), eu(n + 1);
    for (std::size_t j = 0; j <= n; ++j) {
        const double s = m.spot * std::pow(u, double(n) - 2.0 * double(j));
        am[j] = eu[j] = std::max(phi * (s - m.strike), 0.0);
    }
    for (std::size_t i = n; i-- > 0;)
        for (std::size_t j = 0; j <= i; ++j) {
            const double s = m.spot * std::pow(u, double(i) - 2.0 * double(j));
            eu[j] = disc * (p * eu[j] + (1 - p) * eu[j + 1]);
            am[j] = std::max(disc * (p * am[j] + (1 - p) * am[j + 1]), phi * (s - m.strike));
        }
    return {am[0], eu[0], am[0] - eu[0]};
}

double american_baw(const ExoticMarket& m) {
    check_common(m);
    const double s = m.spot, k = m.strike, t = m.expiry_years, r = m.rate, v = m.vol, b = r - m.dividend_yield;
    if (!(r > 0)) throw Error("E_DOMAIN", "BAW needs a positive rate (ruling E-A30)", "rate");
    const bool call = m.type == OptionType::Call;
    if (call && b >= r) return gbs(m.type, s, k, t, r, b, v);
    const double mm = 2 * r / (v * v), nn = 2 * b / (v * v), kt = 1 - std::exp(-r * t);
    const auto d1 = [&](double x) { return (std::log(x / k) + (b + v * v / 2) * t) / (v * std::sqrt(t)); };
    const double carry = std::exp((b - r) * t);
    if (call) {
        const double q2 = (-(nn - 1) + std::sqrt((nn - 1) * (nn - 1) + 4 * mm / kt)) / 2;
        const auto g = [&](double x) {
            return x - k - gbs(OptionType::Call, x, k, t, r, b, v) - (1 - carry * N(d1(x))) * x / q2;
        };
        double hi = 2 * k;
        for (int i = 0; g(hi) < 0 && i < 200; ++i) hi *= 2;
        const double sc = bisect(g, k, hi);
        if (s >= sc) return s - k;
        const double a2 = (sc / q2) * (1 - carry * N(d1(sc)));
        return gbs(OptionType::Call, s, k, t, r, b, v) + a2 * std::pow(s / sc, q2);
    }
    const double q1 = (-(nn - 1) - std::sqrt((nn - 1) * (nn - 1) + 4 * mm / kt)) / 2;
    const auto h = [&](double x) {
        return k - x - gbs(OptionType::Put, x, k, t, r, b, v) + (1 - carry * N(-d1(x))) * x / q1;
    };
    const double sc = bisect(h, k * 1e-12, k);
    if (s <= sc) return k - s;
    const double a1 = -(sc / q1) * (1 - carry * N(-d1(sc)));
    return gbs(OptionType::Put, s, k, t, r, b, v) + a1 * std::pow(s / sc, q1);
}

FdResult american_fd(const ExoticMarket& m, bool american, const FdGrid& g) {
    if (g.nx < 5 || g.nx % 2 == 0) throw Error("E_INPUT", "nx must be odd and at least 5", "grid");
    if (g.nx > 1001) throw Error("E_LIMIT", "nx is above its limit", "grid");
    if (g.nt < 1) throw Error("E_INPUT", "nt must be at least 1", "grid");
    if (g.nt > 10000) throw Error("E_LIMIT", "nt is above its limit", "grid");
    check_common(m);
    positive(g.width, "width");
    const std::size_t nx = std::size_t(g.nx), c = (nx - 1) / 2;
    const double t = m.expiry_years, v = m.vol, r = m.rate, q = m.dividend_yield, phi = phi_of(m.type);
    const double h = g.width * v * std::sqrt(t), dx = 2 * h / double(nx - 1), dt = t / double(g.nt), mu = r - q - v * v / 2;
    std::vector<double> x(nx), pay(nx), val(nx);
    for (std::size_t i = 0; i < nx; ++i) {
        x[i] = std::log(m.spot) - h + double(i) * dx;
        pay[i] = std::max(phi * (std::exp(x[i]) - m.strike), 0.0);
    }
    val = pay;
    const double lo = -dt * (v * v / (2 * dx * dx) - mu / (2 * dx)), di = 1 + dt * (v * v / (dx * dx) + r);
    const double up = -dt * (v * v / (2 * dx * dx) + mu / (2 * dx));
    std::vector<double> a(nx, lo), b(nx, di), cc(nx, up);
    a[0] = cc[0] = 0, b[0] = 1;
    a[nx - 1] = cc[nx - 1] = 0, b[nx - 1] = 1;
    for (long long n = 0; n < g.nt; ++n) {
        const double tau = double(n + 1) * dt;
        const auto edge = [&](std::size_t i) {
            return american ? pay[i]
                            : std::max(phi * (std::exp(x[i]) * std::exp(-q * tau) - m.strike * std::exp(-r * tau)), 0.0);
        };
        val[0] = edge(0);
        val[nx - 1] = edge(nx - 1);
        thomas(a, b, cc, val);
        if (american)
            for (std::size_t i = 0; i < nx; ++i) val[i] = std::max(val[i], pay[i]);
    }
    const double s = m.spot, vm = val[c - 1], v0 = val[c], vp = val[c + 1];
    return {v0, (vp - vm) / (2 * dx * s), ((vp - 2 * v0 + vm) / (dx * dx) - (vp - vm) / (2 * dx)) / (s * s)};
}

}  // namespace quantforge
