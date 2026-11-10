#include "quantforge/core/finite.hpp"
#include "quantforge/core/interp.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

bool strictly_increasing(const Vec& x) {
    for (std::size_t i = 1; i < x.size(); ++i)
        if (!(x[i - 1] < x[i])) return false;
    return true;
}

std::size_t min_knots(InterpMethod m) {
    using enum InterpMethod;
    switch (m) {
        case CubicNatural: case Tension: return 3;
        case CubicNotAKnot: return 4;
        default: return 2;
    }
}

// The interval for t: the one to the right of a knot, and the last on x_n.
std::size_t interval(const Vec& x, double t) {
    const auto it = std::upper_bound(x.begin(), x.end(), t);
    const auto i = std::size_t(it - x.begin()) - 1;
    return std::min(i, x.size() - 2);
}

struct Point {
    double value, derivative;
};

// Solves rows first..last of a tridiagonal system, in a vector of the full length.
Vec thomas(const Vec& lo, Vec mid, const Vec& up, Vec rhs, std::size_t first, std::size_t last) {
    for (std::size_t i = first + 1; i <= last; ++i) {
        const double w = lo[i] / mid[i - 1];
        mid[i] -= w * up[i - 1];
        rhs[i] -= w * rhs[i - 1];
    }
    Vec x(mid.size(), 0.0);
    x[last] = rhs[last] / mid[last];
    for (std::size_t i = last; i-- > first;) x[i] = (rhs[i] - up[i] * x[i + 1]) / mid[i];
    return x;
}

// Second derivatives M of the cubic spline, from its end conditions.
Vec spline_moments(InterpMethod method, const Vec& x, const Vec& y, const InterpParams& p) {
    const std::size_t n = x.size() - 1;
    Vec h(n), d(n);
    for (std::size_t i = 0; i < n; ++i) {
        h[i] = x[i + 1] - x[i];
        d[i] = (y[i + 1] - y[i]) / h[i];
    }
    Vec lo(n + 1, 0.0), mid(n + 1, 1.0), up(n + 1, 0.0), rhs(n + 1, 0.0);
    for (std::size_t i = 1; i < n; ++i) {
        lo[i] = h[i - 1];
        mid[i] = 2.0 * (h[i - 1] + h[i]);
        up[i] = h[i];
        rhs[i] = 6.0 * (d[i] - d[i - 1]);
    }
    if (method == InterpMethod::CubicClamped) {
        mid[0] = 2.0 * h[0];
        up[0] = h[0];
        rhs[0] = 6.0 * (d[0] - p.slope_start);
        lo[n] = h[n - 1];
        mid[n] = 2.0 * h[n - 1];
        rhs[n] = 6.0 * (p.slope_end - d[n - 1]);
    }
    if (method != InterpMethod::CubicNotAKnot) return thomas(lo, mid, up, rhs, 0, n);
    // Not-a-knot: the third derivative agrees across x_1 and x_{n-1}. That gives M_0 and M_n from their neighbours;
    // putting those into the first and last interior rows keeps the system tridiagonal and dominant.
    const double h0 = h[0], h1 = h[1], f = h[n - 2], g = h[n - 1];
    mid[1] += h0 * (h0 + h1) / h1;
    up[1] -= h0 * h0 / h1;
    mid[n - 1] += g * (f + g) / f;
    lo[n - 1] -= g * g / f;
    Vec m = thomas(lo, mid, up, rhs, 1, n - 1);
    m[0] = ((h0 + h1) * m[1] - h0 * m[2]) / h1;
    m[n] = ((f + g) * m[n - 1] - g * m[n - 2]) / f;
    return m;
}

Point spline_at(const Vec& x, const Vec& y, const Vec& m, double t) {
    const std::size_t i = interval(x, t);
    const double h = x[i + 1] - x[i], l = x[i + 1] - t, r = t - x[i];
    const double value = m[i] * l * l * l / (6.0 * h) + m[i + 1] * r * r * r / (6.0 * h) +
                         (y[i] / h - m[i] * h / 6.0) * l + (y[i + 1] / h - m[i + 1] * h / 6.0) * r;
    const double slope = -m[i] * l * l / (2.0 * h) + m[i + 1] * r * r / (2.0 * h) - (y[i] / h - m[i] * h / 6.0) +
                         (y[i + 1] / h - m[i + 1] * h / 6.0);
    return {value, slope};
}

Vec pchip_slopes(const Vec& x, const Vec& y) {
    const std::size_t n = x.size() - 1;
    Vec h(n), d(n), m(n + 1);
    for (std::size_t i = 0; i < n; ++i) {
        h[i] = x[i + 1] - x[i];
        d[i] = (y[i + 1] - y[i]) / h[i];
    }
    if (n == 1) return {d[0], d[0]};
    for (std::size_t i = 1; i < n; ++i) {
        if (d[i - 1] == 0.0 || d[i] == 0.0 || (d[i - 1] > 0.0) != (d[i] > 0.0)) {
            m[i] = 0.0;
        } else {
            const double w1 = 2.0 * h[i] + h[i - 1], w2 = h[i] + 2.0 * h[i - 1];
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]);
        }
    }
    const auto end = [](double h0, double h1, double d0, double d1) {
        double s = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
        // Three-valued signs: 0 differs from a non-zero value.
        const auto sign = [](double v) { return (v > 0.0) - (v < 0.0); };
        if (sign(s) != sign(d0)) s = 0.0;
        else if (sign(d0) != sign(d1) && std::fabs(s) > 3.0 * std::fabs(d0)) s = 3.0 * d0;
        return s;
    };
    m[0] = end(h[0], h[1], d[0], d[1]);
    m[n] = end(h[n - 1], h[n - 2], d[n - 1], d[n - 2]);
    return m;
}

Point hermite_at(const Vec& x, const Vec& y, const Vec& m, double t) {
    const std::size_t i = interval(x, t);
    const double h = x[i + 1] - x[i], u = (t - x[i]) / h;
    const double u2 = u * u, u3 = u2 * u;
    const double value = (2 * u3 - 3 * u2 + 1) * y[i] + (u3 - 2 * u2 + u) * h * m[i] + (-2 * u3 + 3 * u2) * y[i + 1] +
                         (u3 - u2) * h * m[i + 1];
    const double slope = (6 * u2 - 6 * u) / h * y[i] + (3 * u2 - 4 * u + 1) * m[i] + (-6 * u2 + 6 * u) / h * y[i + 1] +
                         (3 * u2 - 2 * u) * m[i + 1];
    return {value, slope};
}

Vec tension_moments(const Vec& x, const Vec& y, double p) {
    const std::size_t n = x.size() - 1;
    Vec e(n), c(n), d(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double h = x[i + 1] - x[i], s = std::sinh(p * h);
        e[i] = 1.0 / h - p / s;
        c[i] = p * std::cosh(p * h) / s - 1.0 / h;
        d[i] = (y[i + 1] - y[i]) / h;
    }
    // Thomas algorithm on the interior knots 1..n-1.
    const std::size_t k = n - 1;
    Vec diag(k), rhs(k), m(n + 1, 0.0);
    for (std::size_t j = 0; j < k; ++j) {
        diag[j] = c[j] + c[j + 1];
        rhs[j] = p * p * (d[j + 1] - d[j]);
    }
    for (std::size_t j = 1; j < k; ++j) {
        const double w = e[j] / diag[j - 1];
        diag[j] -= w * e[j];
        rhs[j] -= w * rhs[j - 1];
    }
    m[k] = rhs[k - 1] / diag[k - 1];
    for (std::size_t j = k - 1; j-- > 0;) m[j + 1] = (rhs[j] - e[j + 1] * m[j + 2]) / diag[j];
    return m;
}

Point tension_at(const Vec& x, const Vec& y, const Vec& m, double p, double t) {
    const std::size_t i = interval(x, t);
    const double h = x[i + 1] - x[i], l = x[i + 1] - t, r = t - x[i], p2 = p * p, s = std::sinh(p * h);
    const double a = y[i] - m[i] / p2, b = y[i + 1] - m[i + 1] / p2;
    const double value = (m[i] * std::sinh(p * l) + m[i + 1] * std::sinh(p * r)) / (p2 * s) + a * l / h + b * r / h;
    const double slope = (-m[i] * std::cosh(p * l) + m[i + 1] * std::cosh(p * r)) / (p * s) + (b - a) / h;
    return {value, slope};
}

// g and its integral G on [0, 1] for one interval of the monotone-convex forward.
struct Shape {
    double g0, g1;

    bool region_i() const {
        return (g0 < 0.0 && -g0 / 2.0 <= g1 && g1 <= -2.0 * g0) || (g0 > 0.0 && -g0 / 2.0 >= g1 && g1 >= -2.0 * g0);
    }
    bool region_ii() const { return (g0 < 0.0 && g1 > -2.0 * g0) || (g0 > 0.0 && g1 < -2.0 * g0); }
    bool region_iii() const { return (g0 > 0.0 && -g0 / 2.0 < g1 && g1 < 0.0) || (g0 < 0.0 && 0.0 < g1 && g1 < -g0 / 2.0); }

    double g(double x) const {
        if (g0 == 0.0 && g1 == 0.0) return 0.0;
        if (region_i()) return g0 * (1.0 - 4.0 * x + 3.0 * x * x) + g1 * (-2.0 * x + 3.0 * x * x);
        if (region_ii()) {
            const double eta = (g1 + 2.0 * g0) / (g1 - g0);
            if (x <= eta) return g0;
            const double v = (x - eta) / (1.0 - eta);
            return g0 + (g1 - g0) * v * v;
        }
        if (region_iii()) {
            const double eta = 3.0 * g1 / (g1 - g0);
            if (x >= eta) return g1;
            const double v = (eta - x) / eta;
            return g1 + (g0 - g1) * v * v;
        }
        const double eta = g1 / (g1 + g0), a = -g0 * g1 / (g0 + g1);
        if (x < eta) {
            const double v = (eta - x) / eta;
            return a + (g0 - a) * v * v;
        }
        // g0 = 0 puts eta at 1, where the table's fraction is 0/0: the node forward is g1.
        if (eta >= 1.0) return g1;
        const double v = (x - eta) / (1.0 - eta);
        return a + (g1 - a) * v * v;
    }

    double integral(double x) const {
        if (g0 == 0.0 && g1 == 0.0) return 0.0;
        const auto falling = [](double eta, double upto) {  // integral of ((eta - s)/eta)^2 on [0, upto]
            const double rest = eta - upto;
            return (eta * eta * eta - rest * rest * rest) / (3.0 * eta * eta);
        };
        const auto rising = [](double eta, double x_) {  // integral of ((s - eta)/(1 - eta))^2 on [eta, x]
            const double v = x_ - eta, w = 1.0 - eta;
            return v * v * v / (3.0 * w * w);
        };
        if (region_i()) return g0 * (x - 2.0 * x * x + x * x * x) + g1 * (-x * x + x * x * x);
        if (region_ii()) {
            const double eta = (g1 + 2.0 * g0) / (g1 - g0);
            return x <= eta ? g0 * x : g0 * x + (g1 - g0) * rising(eta, x);
        }
        if (region_iii()) {
            const double eta = 3.0 * g1 / (g1 - g0);
            return g1 * x + (g0 - g1) * falling(eta, std::min(x, eta));
        }
        const double eta = g1 / (g1 + g0), a = -g0 * g1 / (g0 + g1);
        double total = a * x;
        if (eta > 0.0) total += (g0 - a) * falling(eta, std::min(x, eta));
        if (x > eta && eta < 1.0) total += (g1 - a) * rising(eta, x);
        return total;
    }
};

}  // namespace

InterpResult interpolate(InterpMethod method, const Vec& x, const Vec& y, const Vec& at, const InterpParams& params) {
    require_finite(x, "x");
    require_finite(y, "y");
    require_finite(at, "at");
    require_finite(params.slope_start, "slope_start");
    require_finite(params.slope_end, "slope_end");
    require_finite(params.tension, "tension");
    using enum InterpMethod;
    if (x.size() != y.size()) throw Error("E_INPUT", "x and y differ in length");
    if (x.size() < min_knots(method)) throw Error("E_INPUT", "too few knots", "x");
    if (!strictly_increasing(x)) throw Error("E_INPUT", "x must be strictly increasing", "x");

    if (method == LogLinear && std::ranges::any_of(y, [](double v) { return v <= 0.0; }))
        throw Error("E_DOMAIN", "log_linear needs positive y", "y");
    const double p = params.tension;
    const bool tension = method == Tension && p != 0.0;
    if (method == Tension) {
        if (p < 0.0) throw Error("E_DOMAIN", "tension must not be negative", "tension");
        for (std::size_t i = 0; tension && i + 1 < x.size(); ++i) {
            const double ph = p * (x[i + 1] - x[i]);
            if (ph < 0.01 || ph > 500.0) throw Error("E_DOMAIN", "p h must lie in [0.01, 500]", "tension");
        }
    }
    for (const double t : at)
        if (t < x.front() || t > x.back()) throw Error("E_OUT_OF_RANGE", "a query lies outside the knots", "at");

    InterpResult r;
    r.values.reserve(at.size());
    if (method == Linear || method == LogLinear) {
        for (const double t : at) {
            const std::size_t i = interval(x, t);
            const double u = (t - x[i]) / (x[i + 1] - x[i]);
            r.values.push_back(method == Linear ? y[i] + u * (y[i + 1] - y[i])
                                                : std::exp((1.0 - u) * std::log(y[i]) + u * std::log(y[i + 1])));
        }
        return r;
    }
    Vec m;
    if (method == MonotonePchip) m = pchip_slopes(x, y);
    else if (tension) m = tension_moments(x, y, p);
    else m = spline_moments(method == Tension ? CubicNatural : method, x, y, params);
    for (const double t : at) {
        const Point v = method == MonotonePchip ? hermite_at(x, y, m, t)
                        : tension               ? tension_at(x, y, m, p, t)
                                                : spline_at(x, y, m, t);
        r.values.push_back(v.value);
        r.derivatives.push_back(v.derivative);
    }
    return r;
}

MonotoneConvexResult monotone_convex(const Vec& t_in, const Vec& r_in, const Vec& at, bool positive) {
    require_finite(t_in, "t");
    require_finite(r_in, "r");
    require_finite(at, "at");
    if (t_in.size() != r_in.size()) throw Error("E_INPUT", "t and r differ in length");
    if (t_in.size() < 2) throw Error("E_INPUT", "at least 2 points are needed", "t");
    if (!strictly_increasing(t_in) || t_in.front() <= 0.0) throw Error("E_INPUT", "t must be positive and increasing", "t");
    for (const double s : at)
        if (s <= 0.0 || s > t_in.back()) throw Error("E_OUT_OF_RANGE", "a query lies outside (0, t_n]", "at");

    const std::size_t n = t_in.size();
    Vec t(n + 1, 0.0), rt(n + 1, 0.0), fd(n + 1, 0.0), f(n + 1, 0.0);
    for (std::size_t i = 1; i <= n; ++i) {
        t[i] = t_in[i - 1];
        rt[i] = r_in[i - 1] * t[i];
        fd[i] = (rt[i] - rt[i - 1]) / (t[i] - t[i - 1]);
    }
    for (std::size_t i = 1; i < n; ++i) {
        const double span = t[i + 1] - t[i - 1];
        f[i] = (t[i] - t[i - 1]) / span * fd[i + 1] + (t[i + 1] - t[i]) / span * fd[i];
    }
    f[0] = fd[1] - (f[1] - fd[1]) / 2.0;
    f[n] = fd[n] - (f[n - 1] - fd[n]) / 2.0;
    if (positive) {
        for (std::size_t i = 1; i <= n; ++i)
            if (fd[i] < 0.0) throw Error("E_DOMAIN", "positive needs non-negative discrete forwards", "r");
        f[0] = std::clamp(f[0], 0.0, 2.0 * fd[1]);
        for (std::size_t i = 1; i < n; ++i) f[i] = std::clamp(f[i], 0.0, 2.0 * std::min(fd[i], fd[i + 1]));
        f[n] = std::clamp(f[n], 0.0, 2.0 * fd[n]);
    }

    MonotoneConvexResult out;
    for (const double s : at) {
        const auto i = std::size_t(std::lower_bound(t.begin() + 1, t.end(), s) - t.begin());
        const double width = t[i] - t[i - 1], x = (s - t[i - 1]) / width;
        const Shape shape{f[i - 1] - fd[i], f[i] - fd[i]};
        out.forwards.push_back(fd[i] + shape.g(x));
        out.zero_rates.push_back((rt[i - 1] + width * (fd[i] * x + shape.integral(x))) / s);
    }
    return out;
}


namespace {

struct Piece {
    double integral, value;  // integral of f over [0, x] in units of x, and f(x)
};

// Section of the convex monotone forward (curve-framework.md "MONOTONE_CONVEX", rules (a) to (e) in order).
Piece convex_monotone_piece(double fl, double fr, double y, double x) {
    const double g0 = fl - y, g1 = fr - y;
    if (std::fabs(g0) < 1e-14 && std::fabs(g1) < 1e-14) return {fl * x + (fr - fl) * x * x / 2.0, fl + (fr - fl) * x};
    if ((g0 > 0.0 && -2.0 * g0 <= g1 && g1 <= -0.5 * g0) || (g0 < 0.0 && -0.5 * g0 <= g1 && g1 <= -2.0 * g0)) {
        const double a = 3.0 * fl + 3.0 * fr - 6.0 * y, b = -(4.0 * fl + 2.0 * fr - 6.0 * y), c = fl;
        return {((a * x / 3.0 + b / 2.0) * x + c) * x, (a * x + b) * x + c};
    }
    const auto falling = [](double eta, double x_) {  // integral of ((eta - s)/eta)^2 on [0, min(x, eta)]
        const double rest = eta - std::min(x_, eta);
        return (eta * eta * eta - rest * rest * rest) / (3.0 * eta * eta);
    };
    const auto rule_e = [&](double eta) {
        const double a = -(eta * g0 + (1.0 - eta) * g1) / 2.0;
        double integral = (y + a) * x, value = 0.0;
        if (eta > 0.0) integral += (g0 - a) * falling(eta, x);
        if (x > eta) {
            const double w = x - eta, d = 1.0 - eta;
            integral += (g1 - a) * w * w * w / (3.0 * d * d);
            value = y + a + (g1 - a) * (w / d) * (w / d);
        } else if (eta > 0.0) {
            const double q = (eta - x) / eta;
            value = y + a + (g0 - a) * q * q;
        } else {
            value = fl;  // eta = 0 and x = 0: the point piece (ruling F-19)
        }
        return Piece{integral, value};
    };
    if ((g0 < 0.0 && g1 > -2.0 * g0) || (g0 > 0.0 && g1 < -2.0 * g0)) {
        const double eta = (g1 + 2.0 * g0) / (g1 - g0);
        if (eta >= 1.0) return rule_e(1.0);
        double integral = (y + g0) * x, value = y + g0;
        if (x > eta) {
            const double w = x - eta, d = 1.0 - eta;
            integral += (g1 - g0) * w * w * w / (3.0 * d * d);
            value += (g1 - g0) * (w / d) * (w / d);
        }
        return {integral, value};
    }
    if ((g0 > 0.0 && g1 < 0.0 && g1 > -0.5 * g0) || (g0 < 0.0 && g1 > 0.0 && g1 < -0.5 * g0)) {
        const double eta = 3.0 * g1 / (g1 - g0);
        if (eta <= 0.0) return rule_e(0.0);
        double value = y + g1;
        if (x <= eta) {
            const double q = (eta - x) / eta;
            value += (g0 - g1) * q * q;
        }
        return {(y + g1) * x + (g0 - g1) * falling(eta, x), value};
    }
    return rule_e(std::clamp(g1 / (g0 + g1), 0.0, 1.0));
}

// sinh(sigma u)/sinh(sigma h) and cosh(sigma u)/sinh(sigma h) in the stable forms.
double sinh_ratio(double sigma, double u, double h) {
    return std::exp(-sigma * (h - u)) * (-std::expm1(-2.0 * sigma * u)) / (-std::expm1(-2.0 * sigma * h));
}
double cosh_ratio(double sigma, double u, double h) {
    return std::exp(-sigma * (h - u)) * (1.0 + std::exp(-2.0 * sigma * u)) / (-std::expm1(-2.0 * sigma * h));
}

constexpr double small_z = 1e-3;

}  // namespace

NodeLogCurve::NodeLogCurve(NodeCurveMethod method, Vec t, Vec ln_s, double tension)
    : method_(method), t_(std::move(t)), y_(std::move(ln_s)), sigma_(tension) {
    const std::size_t n = t_.size() - 1;
    Vec h(n), s(n);
    for (std::size_t i = 0; i < n; ++i) {
        h[i] = t_[i + 1] - t_[i];
        s[i] = (y_[i + 1] - y_[i]) / h[i];
    }
    switch (method_) {
        case NodeCurveMethod::MonotoneConvex: {
            c_.assign(n + 1, 0.0);
            fn_.assign(n + 1, 0.0);
            for (std::size_t i = 1; i <= n; ++i) c_[i] = (y_[i - 1] - y_[i]) / (t_[i] - t_[i - 1]);
            if (n == 1) {
                fn_[0] = fn_[1] = c_[1];
                break;
            }
            for (std::size_t i = 1; i < n; ++i) {
                const double dl = t_[i] - t_[i - 1], dr = t_[i + 1] - t_[i];
                fn_[i] = (dr * c_[i] + dl * c_[i + 1]) / (dl + dr);
            }
            fn_[0] = 1.5 * c_[1] - 0.5 * fn_[1];
            fn_[n] = 1.5 * c_[n] - 0.5 * fn_[n - 1];
            break;
        }
        case NodeCurveMethod::MonotonicLogCubic: {
            Vec lo(n + 1, 0.0), mid(n + 1, 2.0), up(n + 1, 0.0), rhs(n + 1, 0.0);
            up[0] = 1.0;
            rhs[0] = 3.0 * s[0];
            for (std::size_t i = 1; i < n; ++i) {
                lo[i] = h[i];
                mid[i] = 2.0 * (h[i - 1] + h[i]);
                up[i] = h[i - 1];
                rhs[i] = 3.0 * (h[i] * s[i - 1] + h[i - 1] * s[i]);
            }
            lo[n] = 1.0;
            rhs[n] = 3.0 * s[n - 1];
            const Vec raw = thomas(lo, mid, up, rhs, 0, n);
            c_ = raw;
            const auto sign = [](double v) { return v < 0.0 ? -1.0 : 1.0; };
            const auto end = [&](double m, double chord) {
                return m * chord > 0.0 ? sign(m) * std::min(std::fabs(m), 3.0 * std::fabs(chord)) : 0.0;
            };
            c_[0] = end(raw[0], s[0]);
            c_[n] = end(raw[n], s[n - 1]);
            for (std::size_t i = 1; i < n; ++i) {
                const double p = (s[i - 1] * h[i] + s[i] * h[i - 1]) / (h[i - 1] + h[i]);
                double big = 3.0 * std::min({std::fabs(s[i - 1]), std::fabs(s[i]), std::fabs(p)});
                if (i > 1 && (s[i - 1] - s[i - 2]) * (s[i] - s[i - 1]) > 0.0) {
                    const double pd = (s[i - 1] * (2.0 * h[i - 1] + h[i - 2]) - s[i - 2] * h[i - 1]) / (h[i - 2] + h[i - 1]);
                    if (p * pd > 0.0 && p * (s[i - 1] - s[i - 2]) > 0.0)
                        big = std::max(big, 1.5 * std::min(std::fabs(p), std::fabs(pd)));
                }
                if (i + 1 < n && (s[i] - s[i - 1]) * (s[i + 1] - s[i]) > 0.0) {
                    const double pu = (s[i] * (2.0 * h[i] + h[i + 1]) - s[i + 1] * h[i]) / (h[i] + h[i + 1]);
                    if (p * pu > 0.0 && -p * (s[i] - s[i - 1]) > 0.0)
                        big = std::max(big, 1.5 * std::min(std::fabs(p), std::fabs(pu)));
                }
                c_[i] = raw[i] * p > 0.0 ? sign(raw[i]) * std::min(std::fabs(raw[i]), big) : 0.0;
            }
            break;
        }
        case NodeCurveMethod::TensionSpline: {
            c_.assign(n + 1, 0.0);
            if (n < 2) break;
            const double sg = sigma_;
            Vec alpha(n), beta(n);
            for (std::size_t i = 0; i < n; ++i) {
                const double z = sg * h[i];
                if (z < small_z) {
                    alpha[i] = h[i] / 6.0 * (1.0 - 7.0 * z * z / 60.0);  // ruling F-35
                    beta[i] = h[i] / 3.0 * (1.0 - z * z / 15.0);
                } else {
                    const double e2 = -std::expm1(-2.0 * z);
                    alpha[i] = 1.0 / (sg * sg * h[i]) - 2.0 * std::exp(-z) / e2 / sg;
                    beta[i] = (1.0 + std::exp(-2.0 * z)) / e2 / sg - 1.0 / (sg * sg * h[i]);
                }
            }
            Vec lo(n + 1, 0.0), mid(n + 1, 1.0), up(n + 1, 0.0), rhs(n + 1, 0.0);
            for (std::size_t i = 1; i < n; ++i) {
                lo[i] = alpha[i - 1];
                mid[i] = beta[i - 1] + beta[i];
                up[i] = alpha[i];
                rhs[i] = s[i] - s[i - 1];
            }
            c_ = thomas(lo, mid, up, rhs, 1, n - 1);
            c_[0] = c_[n] = 0.0;
            break;
        }
    }
}

NodeLogCurve::Value NodeLogCurve::section(std::size_t i, double t) const {
    const double h = t_[i + 1] - t_[i];
    switch (method_) {
        case NodeCurveMethod::MonotoneConvex: {
            const Piece p = convex_monotone_piece(fn_[i], fn_[i + 1], c_[i + 1], (t - t_[i]) / h);
            return {y_[i] - h * p.integral, p.value};
        }
        case NodeCurveMethod::MonotonicLogCubic: {
            const double d = t - t_[i], s = (y_[i + 1] - y_[i]) / h;
            const double m0 = c_[i], m1 = c_[i + 1];
            const double b = (3.0 * s - m1 - 2.0 * m0) / h, c = (m1 + m0 - 2.0 * s) / (h * h);
            return {y_[i] + d * (m0 + d * (b + d * c)), -(m0 + 2.0 * b * d + 3.0 * c * d * d)};
        }
        case NodeCurveMethod::TensionSpline:
        default: {
            const double a = t - t_[i], b = t_[i + 1] - t, sg = sigma_;
            double ra = 0.0, rb = 0.0, da = 0.0, db = 0.0;  // R(a), R(b), R'(a), R'(b)
            if (sg * h < small_z) {
                // Ruling F-35: R(u) = (u/h)(u^2 - h^2)/6 (1 + sigma^2 (3 u^2 - 7 h^2)/60), and its derivative.
                const double s2 = sg * sg;
                const auto r = [&](double u) { return (u / h) * (u * u - h * h) / 6.0 * (1.0 + s2 * (3.0 * u * u - 7.0 * h * h) / 60.0); };
                const auto dr = [&](double u) {
                    return (3.0 * u * u - h * h) / (6.0 * h) * (1.0 + s2 * (3.0 * u * u - 7.0 * h * h) / 60.0) +
                           (u / h) * (u * u - h * h) / 6.0 * (s2 * u / 10.0);
                };
                ra = r(a);
                rb = r(b);
                da = dr(a);
                db = dr(b);
            } else {
                const double s2 = sg * sg;
                ra = (sinh_ratio(sg, a, h) - a / h) / s2;
                rb = (sinh_ratio(sg, b, h) - b / h) / s2;
                da = cosh_ratio(sg, a, h) / sg - 1.0 / (s2 * h);
                db = cosh_ratio(sg, b, h) / sg - 1.0 / (s2 * h);
            }
            const double value = y_[i] * b / h + y_[i + 1] * a / h + c_[i] * rb + c_[i + 1] * ra;
            const double slope = (y_[i + 1] - y_[i]) / h - c_[i] * db + c_[i + 1] * da;
            return {value, -slope};
        }
    }
}

double NodeLogCurve::left_forward_at_end() const {
    const std::size_t n = t_.size() - 1;
    return section(n - 1, t_[n]).forward;
}

double NodeLogCurve::ln_s(double t) const {
    const std::size_t n = t_.size() - 1;
    if (t >= t_[n]) return t == t_[n] ? y_[n] : y_[n] - left_forward_at_end() * (t - t_[n]);
    const auto i = std::size_t(std::upper_bound(t_.begin(), t_.end(), t) - t_.begin()) - 1;
    if (t == t_[i]) return y_[i];
    return section(i, t).ln_s;
}

double NodeLogCurve::forward(double t) const {
    const std::size_t n = t_.size() - 1;
    if (t >= t_[n]) return left_forward_at_end();
    const auto i = std::size_t(std::upper_bound(t_.begin(), t_.end(), t) - t_.begin()) - 1;
    return section(i, t).forward;
}

}  // namespace quantforge
