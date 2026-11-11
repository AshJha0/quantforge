// Stage G short-rate models, MC Greeks and closed-form swap exposure. See shortrate.hpp for the spec references.
#include "quantforge/core/shortrate.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "quantforge/core/error.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::shortrate {

namespace {
constexpr double kInvSqrt2Pi = 0.39894228040143267794;
double normal_pdf(double x) { return kInvSqrt2Pi * std::exp(-0.5 * x * x); }
}  // namespace

Curve Curve::from(const std::vector<double>& times, const std::vector<double>& dfs) {
    Curve c;
    c.t.push_back(0.0);
    c.lnp.push_back(0.0);
    for (std::size_t i = 0; i < times.size(); ++i) {
        c.t.push_back(times[i]);
        c.lnp.push_back(std::log(dfs[i]));
    }
    return c;
}

double Curve::ln_p(double x) const {
    const std::size_t n = t.size();
    if (x >= t[n - 1]) {
        const double f = (lnp[n - 2] - lnp[n - 1]) / (t[n - 1] - t[n - 2]);
        return lnp[n - 1] - f * (x - t[n - 1]);
    }
    std::size_t i = 1;
    while (t[i] <= x) ++i;  // t[i-1] <= x < t[i]
    const double w = (x - t[i - 1]) / (t[i] - t[i - 1]);
    return lnp[i - 1] + w * (lnp[i] - lnp[i - 1]);
}

double Curve::df(double x) const { return std::exp(ln_p(x)); }

double Curve::fwd(double x) const {
    const std::size_t n = t.size();
    std::size_t i = 1;
    while (i < n && t[i] <= x) ++i;
    if (i >= n) i = n - 1;
    return -(lnp[i] - lnp[i - 1]) / (t[i] - t[i - 1]);
}

double b_factor(double a, double tau) { return -std::expm1(-a * tau) / a; }

double b_minus_tau_over_a2(double a, double tau) {
    const double x = a * tau;
    if (x < 1e-2) {
        // B - tau = sum_{k>=2} (-1)^{k+1} a^{k-1} tau^k / k!, so (B - tau)/a = sum_{k>=2} (-1)^{k+1} x^{k-2} tau^2 / k!.
        double term = -tau * tau / 2.0, sum = 0.0;
        for (int k = 2; k < 30; ++k) {
            sum += term;
            term *= -x / (k + 1);
        }
        return sum / a;
    }
    return (b_factor(a, tau) - tau) / (a * a);
}

std::pair<double, double> ln_a_b(const Params& p, double t, double T) {
    const double tau = T - t, a = p.a, s2 = p.sigma * p.sigma;
    if (p.model == Model::Vasicek) {
        const double B = b_factor(a, tau);
        return {b_minus_tau_over_a2(a, tau) * (a * a * p.b - s2 / 2) - s2 * B * B / (4 * a), B};
    }
    if (p.model == Model::Cir) {
        const double g = std::sqrt(a * a + 2 * s2), em1 = std::expm1(g * tau);
        const double den = (g + a) * em1 + 2 * g;
        return {(2 * a * p.b / s2) * (std::log(2 * g / den) + (a + g) * tau / 2), 2 * em1 / den};
    }
    const double B = b_factor(a, tau);
    const double lnA =
        p.curve.ln_p(T) - p.curve.ln_p(t) + B * p.curve.fwd(t) - s2 / (4 * a) * (-std::expm1(-2 * a * t)) * B * B;
    return {lnA, B};
}

double bond(const Params& p, double t, double T, double r) {
    const auto [lnA, B] = ln_a_b(p, t, T);
    return std::exp(lnA - B * r);
}

double bond0(const Params& p, double T) {
    if (p.model == Model::HullWhite) return p.curve.df(T);
    return bond(p, 0.0, T, p.r0);
}

double gamma_p(double s, double x) {
    if (x <= 0) return 0.0;
    const double lead = s * std::log(x) - x - std::lgamma(s);
    if (x < s + 1) {
        double term = 1.0 / s, sum = term;
        for (int n = 1; n < 100000; ++n) {
            term *= x / (s + n);
            sum += term;
            if (term < sum * 1e-17) break;
        }
        return sum * std::exp(lead);
    }
    const double tiny = 1e-300;
    double bb = x + 1 - s, c = 1 / tiny, d = 1 / bb, h = d;
    for (int i = 1; i < 100000; ++i) {
        const double an = -i * (i - s);
        bb += 2;
        d = an * d + bb;
        if (std::fabs(d) < tiny) d = tiny;
        c = bb + an / c;
        if (std::fabs(c) < tiny) c = tiny;
        d = 1 / d;
        const double del = d * c;
        h *= del;
        if (std::fabs(del - 1) < 1e-17) break;
    }
    return 1.0 - std::exp(lead) * h;
}

// The CDF is 0 for x <= 0 (the support is x >= 0). Each Poisson weight is formed in log space, so
// exp(-lambda/2) never appears alone and cannot underflow at a large noncentrality (low CIR sigma, about 0.005).
double ncx2_cdf(double x, double k, double lambda) {
    if (!(x > 0)) return 0.0;
    const double mu = lambda / 2;
    const long long mode = static_cast<long long>(std::floor(mu));
    const auto weight = [&](long long j) {
        const double dj = static_cast<double>(j);
        return std::exp(-mu + dj * std::log(std::max(mu, 1e-300)) - std::lgamma(dj + 1.0));
    };
    const auto term = [&](long long j) {
        return (mu == 0 && j > 0) ? 0.0 : weight(j) * gamma_p(k / 2 + static_cast<double>(j), x / 2);
    };
    double sum = term(mode);
    for (long long j = mode + 1; j < mode + 100000; ++j) {
        const double t = term(j);
        sum += t;
        if (t < 1e-17 * sum) break;
    }
    for (long long j = mode - 1; j >= 0; --j) {
        const double t = term(j);
        sum += t;
        if (t < 1e-17 * sum) break;
    }
    return sum;
}

namespace {
// Gaussian (Vasicek, Hull-White) bond-option volatility.
double gauss_sigma_p(const Params& p, double T, double S) {
    return p.sigma * b_factor(p.a, S - T) * std::sqrt(-std::expm1(-2 * p.a * T) / (2 * p.a));
}
double gauss_call(double ps, double pt, double K, double sp) {
    const double h = std::log(ps / (K * pt)) / sp + sp / 2;
    return ps * normal_cdf(h) - K * pt * normal_cdf(h - sp);
}
}  // namespace

double bond_option(const Params& p, double T, double S, double K, bool call) {
    const double pt = bond0(p, T), ps = bond0(p, S);
    double c;
    if (p.model == Model::Cir) {
        const double a = p.a, s2 = p.sigma * p.sigma, g = std::sqrt(a * a + 2 * s2);
        const double rho = 2 * g / (s2 * std::expm1(g * T)), psi = (a + g) / s2;
        const auto [lnA, B] = ln_a_b(p, T, S);
        const double rbar = (lnA - std::log(K)) / B, k = 4 * a * p.b / s2;
        const double ee = 2 * rho * rho * p.r0 * std::exp(g * T);
        c = ps * ncx2_cdf(2 * rbar * (rho + psi + B), k, ee / (rho + psi + B)) -
            K * pt * ncx2_cdf(2 * rbar * (rho + psi), k, ee / (rho + psi));
    } else {
        c = gauss_call(ps, pt, K, gauss_sigma_p(p, T, S));
    }
    return call ? c : c - ps + K * pt;
}

namespace {
struct Coupons {
    std::vector<double> c, lnA, B;
};

Coupons coupons_of(const Params& p, double expiry, const std::vector<double>& pay, double K) {
    Coupons cs;
    double prev = expiry;
    for (std::size_t i = 0; i < pay.size(); ++i) {
        double ci = K * (pay[i] - prev);
        if (i + 1 == pay.size()) ci += 1.0;
        prev = pay[i];
        const auto [lnA, B] = ln_a_b(p, expiry, pay[i]);
        cs.c.push_back(ci);
        cs.lnA.push_back(lnA);
        cs.B.push_back(B);
    }
    return cs;
}

// Critical rate r* with sum c_i P(T0, Ti; r*) = 1 (strictly decreasing in r): safeguarded Newton from 0.
double critical_rate(const Coupons& cs, bool cir) {
    const auto g = [&](double r, double& d) {
        double s = 0.0, ds = 0.0;
        for (std::size_t i = 0; i < cs.c.size(); ++i) {
            const double P = std::exp(cs.lnA[i] - cs.B[i] * r);
            s += cs.c[i] * P;
            ds -= cs.c[i] * cs.B[i] * P;
        }
        d = ds;
        return s - 1.0;
    };
    double lo = -std::numeric_limits<double>::infinity(), hi = std::numeric_limits<double>::infinity();
    double r = 0.0, d = 0.0;
    if (cir) {
        const double v0 = g(0.0, d);
        if (v0 < 0) throw Error("E_DOMAIN", "no non-negative critical rate for CIR", "fixed_rate");
        lo = 0.0;
    }
    for (int it = 0; it < 500; ++it) {
        const double v = g(r, d);
        if (std::fabs(v) <= 1e-15) break;
        if (v > 0)
            lo = r;
        else
            hi = r;
        double rn = r - v / d;
        if (!std::isfinite(rn) || !(rn > lo && rn < hi)) {
            if (std::isfinite(lo) && std::isfinite(hi))
                rn = 0.5 * (lo + hi);
            else if (v > 0)
                rn = r + 0.5;
            else
                rn = r - 0.5;
        }
        if (rn == r) break;
        r = rn;
    }
    return r;
}
}  // namespace

Swaption swaption(const Params& p, double expiry, const std::vector<double>& pay, double K, bool payer) {
    const Coupons cs = coupons_of(p, expiry, pay, K);
    const double rs = critical_rate(cs, p.model == Model::Cir);
    double price = 0.0, ann = 0.0, prev = expiry;
    for (std::size_t i = 0; i < pay.size(); ++i) {
        const double X = std::exp(cs.lnA[i] - cs.B[i] * rs);
        price += cs.c[i] * bond_option(p, expiry, pay[i], X, !payer);
        ann += (pay[i] - prev) * bond0(p, pay[i]);
        prev = pay[i];
    }
    const double fwd = (bond0(p, expiry) - bond0(p, pay.back())) / ann;
    return {price, fwd, ann};
}

double swaption_vega(const Params& p, double expiry, const std::vector<double>& pay, double K, bool /*payer*/) {
    const Coupons cs = coupons_of(p, expiry, pay, K);
    const double rs = critical_rate(cs, false);
    const double pt = bond0(p, expiry);
    double v = 0.0;
    for (std::size_t i = 0; i < pay.size(); ++i) {
        const double X = std::exp(cs.lnA[i] - cs.B[i] * rs);
        const double ps = bond0(p, pay[i]), sp = gauss_sigma_p(p, expiry, pay[i]);
        const double h = std::log(ps / (X * pt)) / sp + sp / 2;
        v += cs.c[i] * ps * normal_pdf(h) * sp / p.sigma;
    }
    return v;
}

CapFloor capfloor(const Params& p, const std::vector<double>& times, double K, bool cap) {
    CapFloor r{0.0, {}};
    for (std::size_t i = 1; i < times.size(); ++i) {
        const double tau = times[i] - times[i - 1], f = 1 + K * tau;
        const double v = f * bond_option(p, times[i - 1], times[i], 1 / f, !cap);
        r.caplets.push_back(v);
        r.price += v;
    }
    return r;
}

Calibration hw_calibrate(const Curve& curve, double a, const std::vector<CalSwaption>& strip) {
    Params p;
    p.model = Model::HullWhite;
    p.a = a;
    p.curve = curve;
    const auto objective = [&](double s) {
        p.sigma = s;
        double f = 0.0;
        for (const auto& q : strip) {
            const double e = swaption(p, q.expiry, q.payment_times, q.fixed_rate, q.payer).price - q.target;
            f += e * e;
        }
        return f;
    };
    const auto deriv = [&](double s) {
        p.sigma = s;
        double d = 0.0;
        for (const auto& q : strip) {
            const double e = swaption(p, q.expiry, q.payment_times, q.fixed_rate, q.payer).price - q.target;
            d += 2 * e * swaption_vega(p, q.expiry, q.payment_times, q.fixed_rate, q.payer);
        }
        return d;
    };
    // Scan on a log grid over [1e-4, 1], then bisect F' inside the bracket around the smallest value.
    constexpr int n = 401;
    const auto node = [](int i) { return 1e-4 * std::pow(1e4, static_cast<double>(i) / (n - 1)); };
    int best = 0;
    double fbest = std::numeric_limits<double>::infinity();
    for (int i = 0; i < n; ++i) {
        const double f = objective(node(i));
        if (f < fbest) fbest = f, best = i;
    }
    if (best == 0 || best == n - 1) throw Error("E_NO_CONVERGENCE", "the least-squares minimum is at an end of [1e-4, 1]");
    double lo = node(best - 1), hi = node(best + 1);
    for (int it = 0; it < 200; ++it) {
        const double mid = 0.5 * (lo + hi);
        if (mid <= lo || mid >= hi) break;
        if (deriv(mid) < 0)
            lo = mid;
        else
            hi = mid;
        if (hi - lo <= 1e-15 * mid) break;
    }
    Calibration c;
    c.sigma = 0.5 * (lo + hi);
    p.sigma = c.sigma;
    double f = 0.0;
    for (const auto& q : strip) {
        const double m = swaption(p, q.expiry, q.payment_times, q.fixed_rate, q.payer).price;
        c.fitted.push_back(m);
        f += (m - q.target) * (m - q.target);
    }
    c.rmse = std::sqrt(f / static_cast<double>(strip.size()));
    return c;
}

namespace {
// The G-18 scheme: backward fully implicit steps through the knots, with an action at each knot after 0.
template <class Init, class Knot>
double fd_scheme(const Params& p, const std::vector<double>& knots, const Grid& g, Init init, Knot at_knot) {
    const double a = p.a, s2 = p.sigma * p.sigma;
    const double tm = knots.back();
    const double sx = p.sigma * std::sqrt(-std::expm1(-2 * a * tm) / (2 * a));
    const double h = g.width * sx;
    const std::size_t nx = static_cast<std::size_t>(g.nx);
    const double dx = 2 * h / static_cast<double>(nx - 1);
    std::vector<double> x(nx), V(nx), sub(nx), dia(nx), sup(nx), rhs(nx);
    for (std::size_t i = 0; i < nx; ++i) x[i] = -h + static_cast<double>(i) * dx;
    const auto alpha = [&](double t) {
        const double e = -std::expm1(-a * t);
        return p.curve.fwd(t) + s2 / (2 * a * a) * e * e;
    };
    init(tm, x, alpha(tm), V);
    for (std::size_t k = knots.size() - 1; k >= 1; --k) {
        const double t0 = knots[k - 1], t1 = knots[k];
        const double steps = std::max(1.0, std::ceil(static_cast<double>(g.steps_per_year) * (t1 - t0)));
        const long long ns = static_cast<long long>(steps);
        const double dt = (t1 - t0) / steps;
        for (long long j = ns - 1; j >= 0; --j) {
            const double t = j == 0 ? t0 : t0 + static_cast<double>(j) * dt;
            const double al = alpha(t);
            for (std::size_t i = 1; i + 1 < nx; ++i) {
                const double diff = s2 / (2 * dx * dx), conv = a * x[i] / (2 * dx);
                sub[i] = -dt * (diff + conv);
                sup[i] = -dt * (diff - conv);
                dia[i] = 1 + dt * (2 * diff + x[i] + al);
                rhs[i] = V[i];
            }
            // V_0 = 2 V_1 - V_2 and V_{nx-1} = 2 V_{nx-2} - V_{nx-3}, substituted into the end rows.
            dia[1] += 2 * sub[1];
            sup[1] -= sub[1];
            dia[nx - 2] += 2 * sup[nx - 2];
            sub[nx - 2] -= sup[nx - 2];
            // Thomas algorithm on rows 1 .. nx-2.
            for (std::size_t i = 2; i + 1 < nx; ++i) {
                const double m = sub[i] / dia[i - 1];
                dia[i] -= m * sup[i - 1];
                rhs[i] -= m * rhs[i - 1];
            }
            V[nx - 2] = rhs[nx - 2] / dia[nx - 2];
            for (std::size_t i = nx - 3; i >= 1; --i) V[i] = (rhs[i] - sup[i] * V[i + 1]) / dia[i];
            V[0] = 2 * V[1] - V[2];
            V[nx - 1] = 2 * V[nx - 2] - V[nx - 3];
        }
        if (k - 1 >= 1) at_knot(k - 1, t0, x, alpha(t0), V);
    }
    return V[(nx - 1) / 2];
}
}  // namespace

double bermudan_swaption(const Params& p, const std::vector<double>& pay, double K, bool payer,
                         const std::vector<double>& exercise, const Grid& g) {
    std::vector<double> knots{0.0};
    knots.insert(knots.end(), exercise.begin(), exercise.end());
    const double phi = payer ? 1.0 : -1.0;
    const auto exercise_value = [&](double t, const std::vector<double>& x, double al, std::vector<double>& out) {
        std::vector<double> lnA, B, tau;
        double prev = t;
        for (double T : pay) {
            if (!(T > t)) continue;
            const auto ab = ln_a_b(p, t, T);
            lnA.push_back(ab.first);
            B.push_back(ab.second);
            tau.push_back(T - prev);
            prev = T;
        }
        out.resize(x.size());
        for (std::size_t i = 0; i < x.size(); ++i) {
            const double r = x[i] + al;
            double fixed = 0.0, last = 0.0;
            for (std::size_t j = 0; j < lnA.size(); ++j) {
                const double P = std::exp(lnA[j] - B[j] * r);
                fixed += tau[j] * P;
                last = P;
            }
            out[i] = phi * (1 - last - K * fixed);
        }
    };
    std::vector<double> ex;
    return fd_scheme(
        p, knots, g,
        [&](double t, const std::vector<double>& x, double al, std::vector<double>& V) {
            exercise_value(t, x, al, ex);
            for (std::size_t i = 0; i < V.size(); ++i) V[i] = std::max(ex[i], 0.0);
        },
        [&](std::size_t, double t, const std::vector<double>& x, double al, std::vector<double>& V) {
            exercise_value(t, x, al, ex);
            for (std::size_t i = 0; i < V.size(); ++i) V[i] = std::max(V[i], ex[i]);
        });
}

double callable_bond(const Params& p, const std::vector<double>& pay, double c, const std::vector<double>& calls,
                     double call_price, const Grid& g) {
    std::vector<double> knots{0.0};
    knots.insert(knots.end(), pay.begin(), pay.end());
    const auto tau = [&](std::size_t k) { return knots[k] - knots[k - 1]; };  // knot k = payment k
    return fd_scheme(
        p, knots, g,
        [&](double, const std::vector<double>&, double, std::vector<double>& V) {
            std::fill(V.begin(), V.end(), 1 + c * tau(knots.size() - 1));
        },
        [&](std::size_t k, double t, const std::vector<double>&, double, std::vector<double>& V) {
            const bool callable = std::find(calls.begin(), calls.end(), t) != calls.end();
            for (double& v : V) {
                if (callable) v = std::min(v, call_price);
                v += c * tau(k);
            }
        });
}

namespace {
// (tau - 2 B_a + B_2a) / a^2, the bracket of one G2++ variance term, with a series for small a tau.
double g2_var_term(double a, double tau) {
    const double x = a * tau;
    if (x < 1e-2) {
        // sum_{k>=3} (-1)^{k+1} tau^k / k! a^{k-3} (2^{k-1} - 2)
        double sum = 0.0, pw = tau * tau * tau / 6.0, two = 4.0;  // pw = tau^k a^{k-3} / k!, two = 2^{k-1}
        for (int k = 3; k < 40; ++k) {
            sum += ((k % 2) ? 1.0 : -1.0) * pw * (two - 2.0);
            pw *= x / (k + 1);
            two *= 2.0;
        }
        return sum;
    }
    return (tau - 2 * b_factor(a, tau) + b_factor(2 * a, tau)) / (a * a);
}
double g2_v(const G2& m, double tau) {
    const double cross = tau - b_factor(m.a, tau) - b_factor(m.b, tau) + b_factor(m.a + m.b, tau);
    return m.sigma * m.sigma * g2_var_term(m.a, tau) + m.eta * m.eta * g2_var_term(m.b, tau) +
           2 * m.rho * m.sigma * m.eta / (m.a * m.b) * cross;
}
}  // namespace

double g2_bond(const G2& m, double t, double T, double x, double y) {
    const double tau = T - t;
    const double lnp = m.curve.ln_p(T) - m.curve.ln_p(t) + 0.5 * (g2_v(m, tau) - g2_v(m, T) + g2_v(m, t)) -
                       b_factor(m.a, tau) * x - b_factor(m.b, tau) * y;
    return std::exp(lnp);
}

double g2_bond_option(const G2& m, double T, double S, double K, bool call) {
    const double ba = b_factor(m.a, S - T), bb = b_factor(m.b, S - T);
    // sigma^2/(2a^3) (1 - e^{-a(S-T)})^2 (1 - e^{-2aT}) = sigma^2 B_a(S-T)^2 B_2a(T), and the same in b.
    const double v = m.sigma * m.sigma * ba * ba * b_factor(2 * m.a, T) +
                     m.eta * m.eta * bb * bb * b_factor(2 * m.b, T) +
                     2 * m.rho * m.sigma * m.eta * ba * bb * b_factor(m.a + m.b, T);
    const double pt = m.curve.df(T), ps = m.curve.df(S);
    const double c = gauss_call(ps, pt, K, std::sqrt(v));
    return call ? c : c - ps + K * pt;
}

Exposure swap_ee_hw(const Params& p, double start, const std::vector<double>& pay, double K, bool payer_side,
                    const std::vector<double>& times, std::optional<std::pair<double, double>> hr) {
    Exposure e;
    for (double t : times) {
        std::vector<double> rest;
        for (double T : pay)
            if (T > t) rest.push_back(T);
        (void)start;
        e.discounted_ee.push_back(swaption(p, t, rest, K, payer_side).price);
    }
    if (hr) {
        const auto [lambda, R] = *hr;
        double cva = 0.0, prev = 0.0;
        for (std::size_t k = 0; k < times.size(); ++k) {
            cva += e.discounted_ee[k] * (std::exp(-lambda * prev) - std::exp(-lambda * times[k]));
            prev = times[k];
        }
        e.cva = (1 - R) * cva;
    }
    return e;
}

}  // namespace quantforge::shortrate

namespace quantforge::mcgreeks {

namespace {
struct Terms {
    double price, delta, vega;
};

double payoff_of(Payoff f, double st, double K) {
    switch (f) {
        case Payoff::Call: return std::max(st - K, 0.0);
        case Payoff::Put: return std::max(K - st, 0.0);
        case Payoff::DigitalCall: return st > K ? 1.0 : 0.0;
    }
    return 0.0;
}

Terms terms(const Inputs& in, double z) {
    const double S = in.spot, K = in.strike, T = in.expiry_years, v = in.vol, sT = std::sqrt(T);
    const double D = std::exp(-in.rate * T);
    const auto terminal = [&](double s, double vol) {
        return s * std::exp((in.rate - in.dividend_yield - vol * vol / 2) * T + vol * sT * z);
    };
    const double st = terminal(S, v);
    const double f = payoff_of(in.payoff, st, K);
    Terms t{D * f, 0.0, 0.0};
    const double dst_dv = st * (sT * z - v * T);
    switch (in.method) {
        case Method::Pathwise:
            if (in.payoff == Payoff::Call) {
                const double ind = st > K ? 1.0 : 0.0;
                t.delta = D * ind * st / S;
                t.vega = D * ind * dst_dv;
            } else if (in.payoff == Payoff::Put) {
                const double ind = st < K ? 1.0 : 0.0;
                t.delta = -D * ind * st / S;
                t.vega = -D * ind * dst_dv;
            } else {
                const double eps = in.smoothing_width;
                const double w = std::fabs(st - K) < eps ? 1.0 / (2 * eps) : 0.0;
                t.delta = D * w * st / S;
                t.vega = D * w * dst_dv;
            }
            break;
        case Method::LikelihoodRatio:
            t.delta = D * f * z / (S * v * sT);
            t.vega = D * f * ((z * z - 1) / v - z * sT);
            break;
        case Method::Bump: {
            const double h = in.bump_relative;
            t.delta = (D * payoff_of(in.payoff, terminal(S * (1 + h), v), K) -
                       D * payoff_of(in.payoff, terminal(S * (1 - h), v), K)) /
                      (2 * h * S);
            t.vega = (D * payoff_of(in.payoff, terminal(S, v * (1 + h)), K) -
                      D * payoff_of(in.payoff, terminal(S, v * (1 - h)), K)) /
                     (2 * h * v);
            break;
        }
    }
    return t;
}
}  // namespace

Result greeks(const Inputs& in) {
    const double n = static_cast<double>(in.paths);
    double sp = 0.0, sd = 0.0, sv = 0.0;
    {
        Xoshiro256 rng(in.seed, in.stream);
        for (long long i = 0; i < in.paths; ++i) {
            const Terms t = terms(in, rng.next_normal());
            sp += t.price;
            sd += t.delta;
            sv += t.vega;
        }
    }
    const double mp = sp / n, md = sd / n, mv = sv / n;
    double qp = 0.0, qd = 0.0, qv = 0.0;
    {
        Xoshiro256 rng(in.seed, in.stream);
        for (long long i = 0; i < in.paths; ++i) {
            const Terms t = terms(in, rng.next_normal());
            qp += (t.price - mp) * (t.price - mp);
            qd += (t.delta - md) * (t.delta - md);
            qv += (t.vega - mv) * (t.vega - mv);
        }
    }
    const auto se = [&](double q) { return std::sqrt(q / (n - 1)) / std::sqrt(n); };
    return {mp, se(qp), md, se(qd), mv, se(qv)};
}

std::vector<double> delta_terms(const Inputs& in) {
    std::vector<double> d;
    d.reserve(static_cast<std::size_t>(in.paths));
    Xoshiro256 rng(in.seed, in.stream);
    for (long long i = 0; i < in.paths; ++i) d.push_back(terms(in, rng.next_normal()).delta);
    return d;
}

}  // namespace quantforge::mcgreeks
