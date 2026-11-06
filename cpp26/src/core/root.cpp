#include "quantforge/core/root.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

double eval(const Fn& f, double x) {
    const double v = f(x);
    if (!std::isfinite(v)) throw Error("E_NON_FINITE", "f is not finite");
    return v;
}

void check_options(const RootOptions& o) {
    if (o.x_tol <= 0.0) throw Error("E_INPUT", "x_tol must be positive", "x_tol");
    if (o.f_tol < 0.0) throw Error("E_INPUT", "f_tol must not be negative", "f_tol");
    if (o.max_iter < 1) throw Error("E_INPUT", "max_iter must be at least 1", "max_iter");
}

bool same_sign(double a, double b) { return (a > 0.0) == (b > 0.0); }

[[noreturn]] void no_convergence() { throw Error("E_NO_CONVERGENCE", "max_iter reached"); }
[[noreturn]] void not_bracketed() { throw Error("E_NOT_BRACKETED", "no sign change on the interval"); }

}  // namespace

RootResult bisection(const Fn& f, double a, double b, const RootOptions& opt) {
    check_options(opt);
    if (!(a < b)) throw Error("E_INPUT", "a must be below b");
    double fa = eval(f, a);
    const double fb = eval(f, b);
    if (fa == 0.0) return {a, 0, 0.0, "EXACT"};
    if (fb == 0.0) return {b, 0, 0.0, "EXACT"};
    if (same_sign(fa, fb)) not_bracketed();
    for (long long i = 1; i <= opt.max_iter; ++i) {
        const double m = a + (b - a) / 2.0;
        const double fm = eval(f, m);
        if (fm == 0.0) return {m, i, 0.0, "EXACT"};
        if (same_sign(fa, fm)) {
            a = m;
            fa = fm;
        } else {
            b = m;
        }
        if ((b - a) / 2.0 <= opt.x_tol) return {m, i, fm, "X_TOL"};
        if (std::fabs(fm) <= opt.f_tol) return {m, i, fm, "F_TOL"};
    }
    no_convergence();
}

RootResult brent(const Fn& f, double a0, double b0, const RootOptions& opt) {
    check_options(opt);
    if (!(a0 < b0)) throw Error("E_INPUT", "a must be below b");
    constexpr double eps = 0x1p-52;
    double a = a0, b = b0, fa = eval(f, a), fb = eval(f, b);
    if (fa == 0.0) return {a, 0, 0.0, "EXACT"};
    if (fb == 0.0) return {b, 0, 0.0, "EXACT"};
    if (same_sign(fa, fb)) not_bracketed();
    double c = a, fc = fa, d = b - a, e = d;
    for (long long i = 1; i <= opt.max_iter; ++i) {
        if (std::fabs(fc) < std::fabs(fb)) {
            a = b; b = c; c = a;
            fa = fb; fb = fc; fc = fa;
        }
        const double tol1 = 2.0 * eps * std::fabs(b) + opt.x_tol / 2.0;
        const double xm = (c - b) / 2.0;
        if (std::fabs(xm) <= tol1) return {b, i, fb, "X_TOL"};
        if (fb == 0.0) return {b, i, fb, "EXACT"};
        if (std::fabs(fb) <= opt.f_tol) return {b, i, fb, "F_TOL"};
        if (std::fabs(e) >= tol1 && std::fabs(fa) > std::fabs(fb)) {
            const double s = fb / fa;
            double p, q;
            if (a == c) {
                p = 2.0 * xm * s;
                q = 1.0 - s;
            } else {
                const double qq = fa / fc, r = fb / fc;
                p = s * (2.0 * xm * qq * (qq - r) - (b - a) * (r - 1.0));
                q = (qq - 1.0) * (r - 1.0) * (s - 1.0);
            }
            if (p > 0.0) q = -q;
            p = std::fabs(p);
            if (2.0 * p < std::min(3.0 * xm * q - std::fabs(tol1 * q), std::fabs(e * q))) {
                e = d;
                d = p / q;
            } else {
                d = xm;
                e = d;
            }
        } else {
            d = xm;
            e = d;
        }
        a = b;
        fa = fb;
        b += std::fabs(d) > tol1 ? d : std::copysign(tol1, xm);
        fb = eval(f, b);
        if (fb != 0.0 && same_sign(fb, fc)) {
            c = a;
            fc = fa;
            d = b - a;
            e = d;
        }
    }
    no_convergence();
}

RootResult newton(const Fn& f, const Fn& df, double x0, std::optional<Bracket> bracket, const RootOptions& opt) {
    check_options(opt);
    double lo = 0.0, hi = 0.0, flo = 0.0;
    if (bracket) {
        lo = bracket->a;
        hi = bracket->b;
        if (!(lo < hi)) throw Error("E_INPUT", "a must be below b");
        flo = eval(f, lo);
        const double fhi = eval(f, hi);
        if (flo != 0.0 && fhi != 0.0 && same_sign(flo, fhi)) not_bracketed();
        if (x0 < lo || x0 > hi) throw Error("E_INPUT", "x0 must lie in [a, b]", "x0");
    }
    double x = x0, fx = eval(f, x);
    for (long long i = 1; i <= opt.max_iter; ++i) {
        if (fx == 0.0) return {x, i - 1, 0.0, "EXACT"};
        const double dfx = eval(df, x);
        if (dfx == 0.0) throw Error("E_ZERO_DERIVATIVE", "the derivative is zero");
        if (bracket) {
            // A zero at a stays bracketed: only a strict match of signs moves lo.
            if ((flo > 0.0 && fx > 0.0) || (flo < 0.0 && fx < 0.0)) {
                lo = x;
                flo = fx;
            } else {
                hi = x;
            }
        }
        double next = x - fx / dfx;
        if (bracket && !(next >= lo && next <= hi)) next = lo + (hi - lo) / 2.0;
        const double fnext = eval(f, next);
        if (std::fabs(next - x) <= opt.x_tol * (1.0 + std::fabs(next))) return {next, i, fnext, "X_TOL"};
        if (std::fabs(fnext) <= opt.f_tol) return {next, i, fnext, "F_TOL"};
        x = next;
        fx = fnext;
    }
    no_convergence();
}

}  // namespace quantforge
