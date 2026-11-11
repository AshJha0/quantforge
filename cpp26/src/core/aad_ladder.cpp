// Stage G wave 3d (Q3b, rulings G-9, G-35): reverse-mode derivative of the G-18 Bermudan scheme with respect to the
// curve discount factors, the mean reversion and sigma. Hand-written adjoint: the forward pass stores each time step's
// solution; the reverse pass solves the transposed tridiagonal system per step (the adjoint of the Thomas solve) and
// carries the coefficient adjoints back to the parameters through forward-mode gradients of the few scalars that depend
// on them (the grid half-width h, alpha(t), and the exercise values at the knots).
#include <algorithm>
#include <cmath>

#include "quantforge/core/shortrate.hpp"

namespace quantforge::shortrate {

namespace {
using Grad = std::vector<double>;  // d/dP_1..P_m, d/da, d/dsigma

// Coefficients of ln P(x) (resp. the right-hand forward) on the pillar log discount factors, as a gradient on P_k.
void lnp_grad(const Curve& c, const std::vector<double>& P, double x, double scale, Grad& g) {
    const std::size_t n = c.t.size();
    const auto add = [&](std::size_t node, double coef) {
        if (node >= 1) g[node - 1] += scale * coef / P[node - 1];
    };
    if (x >= c.t[n - 1]) {
        const double span = c.t[n - 1] - c.t[n - 2], e = (x - c.t[n - 1]) / span;
        add(n - 1, 1 + e);
        add(n - 2, -e);
        return;
    }
    std::size_t i = 1;
    while (c.t[i] <= x) ++i;
    const double w = (x - c.t[i - 1]) / (c.t[i] - c.t[i - 1]);
    add(i - 1, 1 - w);
    add(i, w);
}
void fwd_grad(const Curve& c, const std::vector<double>& P, double x, double scale, Grad& g) {
    const std::size_t n = c.t.size();
    std::size_t i = 1;
    while (i < n && c.t[i] <= x) ++i;
    if (i >= n) i = n - 1;
    const double span = c.t[i] - c.t[i - 1];
    if (i >= 1) g[i - 1] += scale * (-1 / span) / P[i - 1];
    if (i - 1 >= 1) g[i - 2] += scale * (1 / span) / P[i - 2];
}

struct Step {
    double t, dt, al;
    std::vector<double> y;  // V after the step (full vector)
};
struct Knot {
    double t;
    std::vector<char> chosen;  // exercise branch active
    bool initial;
};
}  // namespace

Ladder bermudan_ladder(const Params& p, const std::vector<double>& P, const std::vector<double>& pay, double K, bool payer,
                       const std::vector<double>& exercise, const Grid& g) {
    const std::size_t m = P.size(), np = m + 2, ia = m, is = m + 1;
    const double a = p.a, sg = p.sigma, s2 = sg * sg, phi = payer ? 1.0 : -1.0;
    std::vector<double> knots{0.0};
    knots.insert(knots.end(), exercise.begin(), exercise.end());
    const double tm = knots.back();
    const double gq = -std::expm1(-2 * a * tm) / (2 * a);
    const double sx = sg * std::sqrt(gq);
    const double h = g.width * sx;
    const std::size_t nx = static_cast<std::size_t>(g.nx);
    const double dx = 2 * h / static_cast<double>(nx - 1);
    std::vector<double> x(nx), xi(nx);
    for (std::size_t i = 0; i < nx; ++i) {
        x[i] = -h + static_cast<double>(i) * dx;
        xi[i] = x[i] / h;
    }
    Grad dh(np, 0.0);
    dh[is] = h / sg;
    dh[ia] = g.width * sg * (tm * std::exp(-2 * a * tm) - gq) / a / (2 * std::sqrt(gq));
    const auto alpha = [&](double t) {
        const double e = -std::expm1(-a * t);
        return p.curve.fwd(t) + s2 / (2 * a * a) * e * e;
    };
    const auto alpha_grad = [&](double t) {
        Grad gr(np, 0.0);
        fwd_grad(p.curve, P, t, 1.0, gr);
        const double ea = std::exp(-a * t), e = 1 - ea;
        gr[is] += sg * e * e / (a * a);
        gr[ia] += s2 * (e * t * ea / (a * a) - e * e / (a * a * a));
        return gr;
    };
    // Exercise values at t on the grid, and optionally their gradients (node-major, np per node).
    const auto exercise_at = [&](double t, double al, std::vector<double>& ex, std::vector<double>* grad) {
        std::vector<double> lnA, B, tau, Tj;
        double prev = t;
        for (double T : pay) {
            if (!(T > t)) continue;
            const auto ab = ln_a_b(p, t, T);
            lnA.push_back(ab.first);
            B.push_back(ab.second);
            tau.push_back(T - prev);
            Tj.push_back(T);
            prev = T;
        }
        const std::size_t nj = lnA.size();
        std::vector<Grad> dlnA, dB;
        Grad dal;
        if (grad) {
            dal = alpha_grad(t);
            const double fw = p.curve.fwd(t), q = -std::expm1(-2 * a * t);
            for (std::size_t j = 0; j < nj; ++j) {
                const double ta = Tj[j] - t, Bj = B[j];
                Grad gl(np, 0.0), gb(np, 0.0);
                gb[ia] = (ta * std::exp(-a * ta) - Bj) / a;
                lnp_grad(p.curve, P, Tj[j], 1.0, gl);
                lnp_grad(p.curve, P, t, -1.0, gl);
                fwd_grad(p.curve, P, t, Bj, gl);
                gl[is] += -sg / (2 * a) * q * Bj * Bj;
                const double dq_da = 2 * t * std::exp(-2 * a * t);
                gl[ia] += gb[ia] * fw - s2 * ((dq_da * Bj * Bj + q * 2 * Bj * gb[ia]) / (4 * a) - q * Bj * Bj / (4 * a * a));
                dlnA.push_back(gl);
                dB.push_back(gb);
            }
            grad->assign(nx * np, 0.0);
        }
        ex.resize(nx);
        for (std::size_t i = 0; i < nx; ++i) {
            const double r = x[i] + al;
            double fixed = 0.0, last = 0.0;
            for (std::size_t j = 0; j < nj; ++j) {
                const double Pj = std::exp(lnA[j] - B[j] * r);
                fixed += tau[j] * Pj;
                last = Pj;
                if (grad) {
                    const double w = -phi * (K * tau[j] + (j + 1 == nj ? 1.0 : 0.0)) * Pj;
                    double* gi = grad->data() + i * np;
                    for (std::size_t k = 0; k < np; ++k)
                        gi[k] += w * (dlnA[j][k] - r * dB[j][k] - B[j] * (xi[i] * dh[k] + dal[k]));
                }
            }
            ex[i] = phi * (1 - last - K * fixed);
        }
    };

    // ---- forward pass (the arithmetic of fd_scheme) ----
    std::vector<double> V(nx), sub(nx), dia(nx), sup(nx), rhs(nx), ex;
    std::vector<Step> steps;
    std::vector<Knot> knot_log;
    const double diff = s2 / (2 * dx * dx);
    {
        exercise_at(tm, alpha(tm), ex, nullptr);
        Knot kn{tm, std::vector<char>(nx), true};
        for (std::size_t i = 0; i < nx; ++i) {
            V[i] = std::max(ex[i], 0.0);
            kn.chosen[i] = !(ex[i] < 0.0);
        }
        knot_log.push_back(std::move(kn));
    }
    const auto build = [&](double dt, double al) {
        for (std::size_t i = 1; i + 1 < nx; ++i) {
            const double conv = a * x[i] / (2 * dx);
            sub[i] = -dt * (diff + conv);
            sup[i] = -dt * (diff - conv);
            dia[i] = 1 + dt * (2 * diff + x[i] + al);
        }
        dia[1] += 2 * sub[1];
        sup[1] -= sub[1];
        dia[nx - 2] += 2 * sup[nx - 2];
        sub[nx - 2] -= sup[nx - 2];
    };
    for (std::size_t k = knots.size() - 1; k >= 1; --k) {
        const double t0 = knots[k - 1], t1 = knots[k];
        const double nsd = std::max(1.0, std::ceil(static_cast<double>(g.steps_per_year) * (t1 - t0)));
        const long long ns = static_cast<long long>(nsd);
        const double dt = (t1 - t0) / nsd;
        for (long long j = ns - 1; j >= 0; --j) {
            const double t = j == 0 ? t0 : t0 + static_cast<double>(j) * dt;
            const double al = alpha(t);
            build(dt, al);
            for (std::size_t i = 1; i + 1 < nx; ++i) rhs[i] = V[i];
            std::vector<double> d2 = dia;
            for (std::size_t i = 2; i + 1 < nx; ++i) {
                const double mm = sub[i] / d2[i - 1];
                d2[i] -= mm * sup[i - 1];
                rhs[i] -= mm * rhs[i - 1];
            }
            V[nx - 2] = rhs[nx - 2] / d2[nx - 2];
            for (std::size_t i = nx - 3; i >= 1; --i) V[i] = (rhs[i] - sup[i] * V[i + 1]) / d2[i];
            V[0] = 2 * V[1] - V[2];
            V[nx - 1] = 2 * V[nx - 2] - V[nx - 3];
            steps.push_back({t, dt, al, V});
        }
        if (k - 1 >= 1) {
            exercise_at(t0, alpha(t0), ex, nullptr);
            Knot kn{t0, std::vector<char>(nx), false};
            for (std::size_t i = 0; i < nx; ++i) {
                kn.chosen[i] = V[i] < ex[i];
                V[i] = std::max(V[i], ex[i]);
            }
            knot_log.push_back(std::move(kn));
        }
    }
    const std::size_t centre = (nx - 1) / 2;
    Ladder out;
    out.price = V[centre];

    // ---- reverse pass ----
    Grad G(np, 0.0);
    double bar_h = 0.0;
    std::vector<double> bar(nx, 0.0), lam(nx), cprime(nx), dprime(nx), grad;
    bar[centre] = 1.0;
    std::size_t si = steps.size(), ki = knot_log.size();
    const auto apply_knot = [&](const Knot& kn) {
        exercise_at(kn.t, alpha(kn.t), ex, &grad);
        for (std::size_t i = 0; i < nx; ++i)
            if (kn.chosen[i]) {
                const double b = bar[i];
                for (std::size_t q = 0; q < np; ++q) G[q] += b * grad[i * np + q];
                bar[i] = 0.0;
            }
    };
    // Walk the forward operations backwards: steps of interval k, then the knot at its start (if logged).
    for (std::size_t k = 1; k < knots.size(); ++k) {
        const double t1 = knots[k];
        const double t0 = knots[k - 1];
        const double nsd = std::max(1.0, std::ceil(static_cast<double>(g.steps_per_year) * (t1 - t0)));
        const long long ns = static_cast<long long>(nsd);
        for (long long j = 0; j < ns; ++j) {
            const Step& st = steps[--si];
            const std::vector<double>& y = st.y;
            const double dt = st.dt;
            // undo the boundary extrapolation
            bar[1] += 2 * bar[0];
            bar[2] -= bar[0];
            bar[nx - 2] += 2 * bar[nx - 1];
            bar[nx - 3] -= bar[nx - 1];
            bar[0] = bar[nx - 1] = 0.0;
            build(dt, st.al);
            // lambda = M^-T bar (rows 1..nx-2); M^T has (i, i-1) = sup[i-1], (i, i+1) = sub[i+1]
            for (std::size_t i = 1; i + 1 < nx; ++i) {
                const double lo = i > 1 ? sup[i - 1] : 0.0, up = i + 2 < nx ? sub[i + 1] : 0.0;
                const double den = dia[i] - (i > 1 ? lo * cprime[i - 1] : 0.0);
                cprime[i] = up / den;
                dprime[i] = (bar[i] - (i > 1 ? lo * dprime[i - 1] : 0.0)) / den;
            }
            lam[nx - 2] = dprime[nx - 2];
            for (std::size_t i = nx - 3; i >= 1; --i) lam[i] = dprime[i] - cprime[i] * lam[i + 1];
            // adjoints of the modified matrix entries
            double bdiff = 0.0, bal = 0.0, ba = 0.0;
            const std::size_t r1 = 1, rn = nx - 2;
            for (std::size_t i = 1; i + 1 < nx; ++i) {
                double bd = -lam[i] * y[i];
                double bs = (i >= 2) ? -lam[i] * y[i - 1] : 0.0;
                double bu = (i + 2 < nx) ? -lam[i] * y[i + 1] : 0.0;
                // back to the unmodified entries
                if (i == r1) {
                    bs = 2 * bd - bu;  // d1' = d1 + 2 s1, u1' = u1 - s1
                }
                if (i == rn) {
                    bu = 2 * bd - bs;  // d' = d + 2u, s' = s - u
                }
                const double conv_x = x[i] / (2 * dx);
                bdiff += -dt * bs - dt * bu + 2 * dt * bd;
                ba += (-dt * bs + dt * bu) * conv_x;
                bar_h += dt * xi[i] * bd;
                bal += dt * bd;
            }
            G[is] += bdiff * sg / (dx * dx);
            bar_h += bdiff * (-s2 / (dx * dx * dx)) * 2 / static_cast<double>(nx - 1);
            G[ia] += ba;
            const Grad dal = alpha_grad(st.t);
            for (std::size_t q = 0; q < np; ++q) G[q] += bal * dal[q];
            for (std::size_t i = 0; i < nx; ++i) bar[i] = (i >= 1 && i + 1 < nx) ? lam[i] : 0.0;
        }
        // the knot at knots[k] (k < last) was applied just before interval k's steps in the forward pass
        if (k + 1 < knots.size()) apply_knot(knot_log[--ki]);
    }
    // the initial knot at t_m
    if (ki > 0) apply_knot(knot_log[--ki]);
    for (std::size_t q = 0; q < np; ++q) G[q] += bar_h * dh[q];
    out.d_discount_factors.assign(G.begin(), G.begin() + static_cast<std::ptrdiff_t>(m));
    out.d_mean_reversion = G[ia];
    out.d_sigma = G[is];
    return out;
}

}  // namespace quantforge::shortrate
