// K-8 CN_RANNACHER_SMOOTHED; see bermudan_k8.hpp. Same arithmetic in the same order as BermudanK8.java: divisions by
// 3, 6 and 12 stay divisions, and adding a constant to a dual touches the value only (program/K8_PORT_NOTE.md).
#include "quantforge/core/bermudan_k8.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>

namespace quantforge::bermudan_k8 {

using std::size_t;

// ---- dual arithmetic: entry 0 is the value, 1.. the tangents ----

Dual mul(const Dual& u, const Dual& v) {
    Dual o(u.size());
    o[0] = u[0] * v[0];
    for (size_t c = 1; c < o.size(); ++c) o[c] = u[0] * v[c] + v[0] * u[c];
    return o;
}

Dual div(const Dual& u, const Dual& v) {
    Dual o(u.size());
    const double q = u[0] / v[0];
    o[0] = q;
    for (size_t c = 1; c < o.size(); ++c) o[c] = (u[c] - q * v[c]) / v[0];
    return o;
}

Dual add(const Dual& u, const Dual& v) {
    Dual o(u.size());
    for (size_t c = 0; c < o.size(); ++c) o[c] = u[c] + v[c];
    return o;
}

Dual sub(const Dual& u, const Dual& v) {
    Dual o(u.size());
    for (size_t c = 0; c < o.size(); ++c) o[c] = u[c] - v[c];
    return o;
}

Dual scale(double k, const Dual& u) {
    Dual o(u.size());
    for (size_t c = 0; c < o.size(); ++c) o[c] = k * u[c];
    return o;
}

namespace {

Dual func(const Dual& u, double value, double slope) {
    Dual o(u.size());
    o[0] = value;
    for (size_t c = 1; c < o.size(); ++c) o[c] = slope * u[c];
    return o;
}

Dual dexp(const Dual& u) {
    const double e = std::exp(u[0]);
    return func(u, e, e);
}

Dual dexpm1(const Dual& u) { return func(u, std::expm1(u[0]), std::exp(u[0])); }

Dual dsqrt(const Dual& u) {
    const double s = std::sqrt(u[0]);
    return func(u, s, 0.5 / s);
}

Dual neg(const Dual& u) { return scale(-1.0, u); }

Dual div_scalar(const Dual& u, double den) {
    Dual o(u.size());
    for (size_t c = 0; c < o.size(); ++c) o[c] = u[c] / den;
    return o;
}

/// `u + c` for a dual `u` and a constant `c`.
Dual plus(const Dual& u, double c) {
    Dual o = u;
    o[0] += c;
    return o;
}

size_t bisect_right(const std::vector<double>& arr, double x) {
    size_t lo = 0, hi = arr.size();
    while (lo < hi) {
        const size_t mid = (lo + hi) / 2;
        if (x < arr[mid])
            hi = mid;
        else
            lo = mid + 1;
    }
    return lo;
}

/// Log-linear curve on dual logs (G-3).
struct Curve {
    std::vector<double> nodes;
    Duals logs;

    Dual log_discount(double t) const {
        if (t <= 0) return Dual(logs[0].size(), 0.0);
        const size_t j = std::min(bisect_right(nodes, t) - 1, nodes.size() - 2);
        const double w = (t - nodes[j]) / (nodes[j + 1] - nodes[j]);
        Dual o(logs[0].size());
        for (size_t c = 0; c < o.size(); ++c) o[c] = logs[j][c] + (logs[j + 1][c] - logs[j][c]) * w;
        return o;
    }
};

struct Model {
    Curve curve;
    Dual a, s2;

    Dual big_b(double tau) const { return neg(div(dexpm1(scale(tau, neg(a))), a)); }
};

/// Exercise value at `t` times `D(t) = exp(-int_0^t alpha)` (spec step 3); no forward rate.
Duals exercise(const Model& m, double t, const Duals& xs, const std::vector<double>& times, double k, double phi) {
    std::vector<double> after;
    for (double s : times)
        if (s > t) after.push_back(s);
    const size_t n = xs.size(), w = xs[0].size();
    const Dual e1 = dexpm1(scale(t, neg(m.a)));
    const Dual e2 = dexpm1(scale(t, scale(-2, m.a)));
    const Dual big_i = plus(sub(scale(2, div(e1, m.a)), div(e2, scale(2, m.a))), t);
    const Dual c2 = div(m.s2, scale(2, mul(m.a, m.a)));
    const Dual c4 = div(m.s2, scale(4, m.a));
    const Dual lead = dexp(sub(m.curve.log_discount(t), mul(c2, big_i)));
    Duals fixed(n, Dual(w, 0.0));
    Duals last = fixed;
    for (size_t q = 0; q < after.size(); ++q) {
        const double s = after[q];
        const double tau = q == 0 ? s - t : s - after[q - 1];
        const Dual b = m.big_b(s - t);
        const Dual drift = sub(mul(c2, add(big_i, mul(b, mul(e1, e1)))), mul(c4, mul(e2, mul(b, b))));
        const Dual head = sub(m.curve.log_discount(s), drift);
        Duals p(n);
        for (size_t i = 0; i < n; ++i) {
            p[i] = dexp(sub(head, mul(b, xs[i])));
            fixed[i] = add(fixed[i], scale(tau, p[i]));
        }
        last = std::move(p);
    }
    Duals out(n);
    for (size_t i = 0; i < n; ++i) out[i] = scale(phi, sub(sub(lead, last[i]), scale(k, fixed[i])));
    return out;
}

/// Value-only elimination, then every column with the same multipliers and pivots; returns rows x columns.
Duals solve(const Duals& lower, const Duals& diag, const Duals& upper, const Duals& rhs) {
    const size_t n = diag.size(), w = rhs[0].size();
    std::vector<double> cc(n), den(n);
    den[0] = diag[0][0];
    cc[0] = upper[0][0] / den[0];
    for (size_t i = 1; i < n; ++i) {
        den[i] = diag[i][0] - lower[i][0] * cc[i - 1];
        cc[i] = upper[i][0] / den[i];
    }
    std::vector<double> y0(n);
    y0[0] = rhs[0][0] / den[0];
    for (size_t i = 1; i < n; ++i) y0[i] = (rhs[i][0] - lower[i][0] * y0[i - 1]) / den[i];
    for (size_t i = n - 1; i-- > 0;) y0[i] -= cc[i] * y0[i + 1];
    Duals full = rhs;
    for (size_t i = 0; i < n; ++i)
        for (size_t k = 1; k < w; ++k) full[i][k] -= diag[i][k] * y0[i];
    for (size_t i = 1; i < n; ++i)
        for (size_t k = 1; k < w; ++k) full[i][k] -= lower[i][k] * y0[i - 1];
    for (size_t i = 0; i + 1 < n; ++i)
        for (size_t k = 1; k < w; ++k) full[i][k] -= upper[i][k] * y0[i + 1];
    Duals out(n, Dual(w, 0.0));
    for (size_t k = 1; k < w; ++k) out[0][k] = full[0][k] / den[0];
    for (size_t i = 1; i < n; ++i)
        for (size_t k = 1; k < w; ++k) out[i][k] = (full[i][k] - lower[i][0] * out[i - 1][k]) / den[i];
    for (size_t i = n - 1; i-- > 0;)
        for (size_t k = 1; k < w; ++k) out[i][k] -= cc[i] * out[i + 1][k];
    for (size_t i = 0; i < n; ++i) out[i][0] = y0[i];
    return out;
}

/// Rows of `A = -L` at the interior nodes, before the boundary substitution; constant in time (KR-18 a).
struct Operator {
    Duals lower, upper, diag;

    Operator(const Model& m, const Duals& xs, const Dual& dx) {
        const size_t n = xs.size() - 2;
        const Dual diff = div(m.s2, scale(2, mul(dx, dx)));
        const Dual two_dx = scale(2, dx);
        lower.resize(n);
        upper.resize(n);
        diag.resize(n);
        for (size_t i = 0; i < n; ++i) {
            const Dual& inner = xs[i + 1];
            const Dual conv = div(mul(m.a, inner), two_dx);
            lower[i] = neg(add(diff, conv));
            upper[i] = neg(sub(diff, conv));
            diag[i] = add(scale(2, diff), inner);
        }
    }
};

/// Solves `(I + w A) y = rhs` on the interior with linear extrapolation at both ends.
Duals implicit_step(const Operator& op, double w, const Duals& rhs) {
    const size_t n = rhs.size();
    Duals lower(n), upper(n), diag(n);
    for (size_t i = 0; i < n; ++i) {
        lower[i] = scale(w, op.lower[i]);
        upper[i] = scale(w, op.upper[i]);
        diag[i] = plus(scale(w, op.diag[i]), 1.0);
    }
    diag[0] = add(diag[0], scale(2, lower[0]));
    upper[0] = sub(upper[0], lower[0]);
    lower[n - 1] = sub(lower[n - 1], upper[n - 1]);
    diag[n - 1] = add(diag[n - 1], scale(2, upper[n - 1]));
    Duals y = solve(lower, diag, upper, rhs);
    Duals out(n + 2);
    out[0] = sub(scale(2, y[0]), y[1]);
    for (size_t i = 0; i < n; ++i) out[i + 1] = std::move(y[i]);
    out[n + 1] = sub(scale(2, out[n]), out[n - 1]);
    return out;
}

/// `(I - w A) v` at the interior nodes.
Duals explicit_part(const Operator& op, double w, const Duals& v) {
    const size_t n = v.size() - 2;
    Duals out(n);
    for (size_t i = 0; i < n; ++i) {
        const Dual lv = add(add(mul(op.lower[i], v[i]), mul(op.diag[i], v[i + 1])), mul(op.upper[i], v[i + 2]));
        out[i] = sub(v[i + 1], scale(w, lv));
    }
    return out;
}

Duals interior(const Duals& v) { return Duals(v.begin() + 1, v.end() - 1); }

}  // namespace

Dual hat_part(const Dual& p, const Dual& q) {
    const double pa = p[0], qb = q[0];
    if (pa >= 0 && qb >= 0) return add(div_scalar(p, 3), div_scalar(q, 6));
    if (pa > 0 && qb < 0) {
        const Dual dd = sub(p, q);
        const Dual tt = div(mul(p, p), scale(2, dd));
        return sub(tt, div_scalar(mul(tt, div(p, dd)), 3));
    }
    if (pa < 0 && qb > 0) {
        const Dual r = div(q, sub(q, p));
        return div_scalar(mul(q, mul(r, r)), 6);
    }
    return Dual(p.size(), 0.0);
}

Duals smoothed_max(const Duals& v, const Duals& e) {
    const size_t n = v.size(), w = v[0].size();
    Duals f(n);
    for (size_t i = 0; i < n; ++i) f[i] = sub(v[i], e[i]);
    Duals hh(n), d2(n, Dual(w, 0.0));
    for (size_t i = 0; i < n; ++i) {
        const Dual before = i > 0 ? f[i - 1] : sub(scale(2, f[0]), f[1]);
        const Dual after = i < n - 1 ? f[i + 1] : sub(scale(2, f[n - 1]), f[n - 2]);
        hh[i] = add(hat_part(f[i], before), hat_part(f[i], after));
        if (i > 0 && i < n - 1) d2[i] = add(sub(f[i - 1], scale(2, f[i])), f[i + 1]);
    }
    for (size_t j = 0; j + 1 < n; ++j) {
        const double fa = f[j][0], fb = f[j + 1][0];
        if (!((fa > 0 && fb < 0) || (fa < 0 && fb > 0))) continue;
        const size_t pos = fa > 0 ? j : j + 1;
        const size_t ng = fa > 0 ? j + 1 : j;
        const Dual rho = div(f[pos], sub(f[pos], f[ng]));  // the part of the cell where V > E
        const Dual rest = plus(neg(rho), 1.0);
        const Dual gg = div_scalar(mul(mul(rho, rest), plus(scale(2, rho), -1.0)), 12);
        const Dual corr = mul(gg, scale(0.5, add(d2[j], d2[j + 1])));
        hh[pos] = sub(hh[pos], mul(rest, corr));
        hh[ng] = sub(hh[ng], mul(rho, corr));
    }
    Duals out(n);
    for (size_t i = 0; i < n; ++i) {
        Dual o = hh[i];
        if (i > 0 && i < n - 1) o = sub(o, div_scalar(add(sub(hh[i - 1], scale(2, hh[i])), hh[i + 1]), 6));
        out[i] = add(e[i], o);
    }
    return out;
}

Dual scheme(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
            const std::vector<double>& payment_times, double k, bool payer, const std::vector<double>& exercise_times,
            long long nx, long long steps_per_year, double width, bool tangents) {
    const size_t n = times.size();
    const size_t w = tangents ? n + 3 : 1;
    Duals logs(n + 1, Dual(w, 0.0));
    for (size_t j = 0; j < n; ++j) logs[j + 1][0] = std::log(dfs[j]);
    Dual ad(w, 0.0), sd(w, 0.0);
    ad[0] = a;
    sd[0] = sigma;
    if (tangents) {
        for (size_t j = 0; j < n; ++j) logs[j + 1][j + 1] = 1.0;
        ad[n + 1] = 1.0;
        sd[n + 2] = 1.0;
    }
    std::vector<double> nodes(n + 1, 0.0);
    std::copy(times.begin(), times.end(), nodes.begin() + 1);
    const Model m{Curve{nodes, logs}, ad, mul(sd, sd)};
    const double phi = payer ? 1.0 : -1.0;
    const double tm = exercise_times.back();
    const Dual gq = neg(div(dexpm1(scale(-2 * tm, ad)), scale(2, ad)));
    const Dual sx = mul(sd, dsqrt(gq));
    const Dual half_width = scale(width, sx);
    const Dual dx = div_scalar(scale(2, half_width), static_cast<double>(nx - 1));
    const size_t nodes_x = static_cast<size_t>(nx);
    Duals xs(nodes_x);
    for (size_t i = 0; i < nodes_x; ++i) xs[i] = add(neg(half_width), scale(static_cast<double>(i), dx));
    const Operator op(m, xs, dx);
    Duals v = smoothed_max(Duals(nodes_x, Dual(w, 0.0)), exercise(m, tm, xs, payment_times, k, phi));
    std::vector<double> knots(exercise_times.size() + 1, 0.0);
    std::copy(exercise_times.begin(), exercise_times.end(), knots.begin() + 1);
    for (size_t kk = knots.size() - 1; kk > 0; --kk) {
        const double t_hi = knots[kk], t_lo = knots[kk - 1];
        const long long steps =
            std::max<long long>(1, static_cast<long long>(std::ceil(static_cast<double>(steps_per_year) * (t_hi - t_lo))));
        const double half = (t_hi - t_lo) / static_cast<double>(steps) / 2;
        for (long long j = steps - 1; j >= 0; --j) {
            if (j >= steps - start_up_steps) {  // Rannacher start-up: two implicit half steps
                v = implicit_step(op, half, interior(v));
                v = implicit_step(op, half, interior(v));
            } else {
                v = implicit_step(op, half, explicit_part(op, half, v));
            }
        }
        if (kk - 1 > 0) v = smoothed_max(v, exercise(m, t_lo, xs, payment_times, k, phi));
    }
    return v[nodes_x / 2];
}

double price(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
             const std::vector<double>& payment_times, double k, bool payer, double notional,
             const std::vector<double>& exercise_times, long long nx, long long steps_per_year, double width) {
    const Dual r =
        scheme(times, dfs, a, sigma, payment_times, k, payer, exercise_times, nx, steps_per_year, width, false);
    return notional * r[0];
}

Ladder ladder(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
              const std::vector<double>& payment_times, double k, bool payer, double notional,
              const std::vector<double>& exercise_times, long long nx, long long steps_per_year, double width) {
    const Dual r =
        scheme(times, dfs, a, sigma, payment_times, k, payer, exercise_times, nx, steps_per_year, width, true);
    const size_t n = times.size();
    std::vector<double> d(n);
    for (size_t j = 0; j < n; ++j) d[j] = notional * r[1 + j] / dfs[j];
    return {notional * r[0], d, notional * r[n + 1], notional * r[n + 2]};
}

}  // namespace quantforge::bermudan_k8
