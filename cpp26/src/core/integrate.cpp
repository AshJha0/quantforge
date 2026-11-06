#include "quantforge/core/integrate.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>
#include <vector>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

void check_range(double a, double b) {
    if (!(a < b)) throw Error("E_INPUT", "a must be below b");
}

// For the adaptive rules, whose tests would otherwise spin on NaN.
double finite(const Fn& f, double x) {
    const double v = f(x);
    if (!std::isfinite(v)) throw Error("E_NON_FINITE", "f is not finite");
    return v;
}

struct Nodes {
    std::vector<double> t, w;
};

Nodes legendre_nodes(int n) {
    Nodes r{std::vector<double>(std::size_t(n)), std::vector<double>(std::size_t(n))};
    // P_n at t, and P_n' through deriv, by the three-term recurrence.
    const auto legendre = [n](double t, double& deriv) {
        double p0 = 1.0, p1 = t;
        for (int k = 2; k <= n; ++k) {
            const double p2 = ((2 * k - 1) * t * p1 - (k - 1) * p0) / k;
            p0 = p1;
            p1 = p2;
        }
        deriv = n * (t * p1 - p0) / (t * t - 1.0);
        return p1;
    };
    for (int i = 1; i <= (n + 1) / 2; ++i) {
        double t = std::cos(std::numbers::pi * (i - 0.25) / (n + 0.5));
        double dp = 0.0;
        for (int it = 0; it < 100; ++it) {
            const double step = legendre(t, dp) / dp;
            t -= step;
            if (std::fabs(step) < 1e-16) break;
        }
        legendre(t, dp);
        const double w = 2.0 / ((1.0 - t * t) * dp * dp);
        // Root i counts down from the top, so it mirrors onto both ends.
        const auto hi = std::size_t(n - i), lo = std::size_t(i - 1);
        r.t[hi] = hi == lo ? 0.0 : t;
        r.t[lo] = hi == lo ? 0.0 : -t;
        r.w[hi] = r.w[lo] = w;
    }
    return r;
}

struct AdaptiveSimpson {
    const Fn& f;
    long long max_depth;

    double run(double l, double r, double fl, double fm, double fr, double whole, double tol, long long depth) const {
        const double m = l + (r - l) / 2.0;
        const double flm = finite(f, l + (m - l) / 2.0), frm = finite(f, m + (r - m) / 2.0);
        const double s1 = (m - l) / 6.0 * (fl + 4.0 * flm + fm);
        const double s2 = (r - m) / 6.0 * (fm + 4.0 * frm + fr);
        const double delta = s1 + s2 - whole;
        if (std::fabs(delta) <= 15.0 * tol) return s1 + s2 + delta / 15.0;
        if (depth >= max_depth) throw Error("E_NO_CONVERGENCE", "max_depth reached");
        return run(l, m, fl, flm, fm, s1, tol / 2.0, depth + 1) + run(m, r, fm, frm, fr, s2, tol / 2.0, depth + 1);
    }
};

constexpr double kx[8] = {0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
                          0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
                          0.586087235467691130294144838258730, 0.405845151377397166906606412076961,
                          0.207784955007898467600689403773244, 0.0};
constexpr double wk[8] = {0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
                          0.104790010322250183839876322541518, 0.140653259715525918998541745705333,
                          0.169004726639267902826583426140209, 0.190350578064785409913256402421014,
                          0.204432940075298892414161999234649, 0.209482141084727828012999174351914};
constexpr double wg[4] = {0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
                          0.381830050505118944950369775488975, 0.417959183673469387755102040816327};

struct Piece {
    double l, r, value, error;
};

Piece kronrod(const Fn& f, double l, double r) {
    const double c = (l + r) / 2.0, h = (r - l) / 2.0;
    const double fc = finite(f, c);
    double k = wk[7] * fc, g = wg[3] * fc;
    for (int i = 0; i < 7; ++i) {
        const double pair = finite(f, c - h * kx[i]) + finite(f, c + h * kx[i]);
        k += wk[i] * pair;
        if (i % 2 == 1) g += wg[i / 2] * pair;
    }
    return {l, r, k * h, std::fabs(k - g) * h};
}

}  // namespace

double trapezoid(const Fn& f, double a, double b, long long n) {
    check_range(a, b);
    if (n < 1) throw Error("E_INPUT", "n must be at least 1", "n");
    const double h = (b - a) / double(n);
    double sum = f(a) / 2.0;
    for (long long i = 1; i < n; ++i) sum += f(a + double(i) * h);
    sum += f(a + double(n) * h) / 2.0;
    return h * sum;
}

double simpson(const Fn& f, double a, double b, long long n) {
    check_range(a, b);
    if (n < 2 || n % 2 != 0) throw Error("E_INPUT", "n must be even and at least 2", "n");
    const double h = (b - a) / double(n);
    double sum = f(a);
    for (long long i = 1; i < n; ++i) sum += (i % 2 == 1 ? 4.0 : 2.0) * f(a + double(i) * h);
    sum += f(a + double(n) * h);
    return h / 3.0 * sum;
}

double gauss_legendre(const Fn& f, double a, double b, long long n) {
    check_range(a, b);
    if (n < 1 || n > 64) throw Error("E_INPUT", "n must be 1 to 64", "n");
    const Nodes nodes = legendre_nodes(int(n));
    const double half = (b - a) / 2.0, mid = (a + b) / 2.0;
    double sum = 0.0;
    for (std::size_t i = 0; i < nodes.t.size(); ++i) sum += nodes.w[i] * f(mid + half * nodes.t[i]);
    return half * sum;
}

double adaptive_simpson(const Fn& f, double a, double b, double tol, long long max_depth) {
    check_range(a, b);
    if (tol <= 0.0) throw Error("E_INPUT", "tol must be positive", "tol");
    if (max_depth < 1) throw Error("E_INPUT", "max_depth must be at least 1", "max_depth");
    const double fa = finite(f, a), fb = finite(f, b), fm = finite(f, a + (b - a) / 2.0);
    const double whole = (b - a) / 6.0 * (fa + 4.0 * fm + fb);
    return AdaptiveSimpson{f, max_depth}.run(a, b, fa, fm, fb, whole, tol, 0);
}

KronrodResult gauss_kronrod(const Fn& f, double a, double b, double tol, long long max_intervals) {
    check_range(a, b);
    if (tol <= 0.0) throw Error("E_INPUT", "tol must be positive", "tol");
    if (max_intervals < 1) throw Error("E_INPUT", "max_intervals must be at least 1", "max_intervals");
    std::vector<Piece> pieces{kronrod(f, a, b)};
    for (;;) {
        double value = 0.0, error = 0.0;
        for (const Piece& p : pieces) {
            value += p.value;
            error += p.error;
        }
        if (error <= std::max(tol, 1e-14 * std::fabs(value))) return {value, error};
        if (std::ssize(pieces) >= max_intervals) throw Error("E_NO_CONVERGENCE", "max_intervals reached");
        const auto worst = std::ranges::max_element(pieces, {}, &Piece::error);
        const double l = worst->l, r = worst->r, m = l + (r - l) / 2.0;
        *worst = kronrod(f, l, m);
        pieces.push_back(kronrod(f, m, r));
    }
}

double central_difference(const Fn& f, double x, double h, long long order) {
    if (h <= 0.0) throw Error("E_INPUT", "h must be positive", "h");
    if (order == 1) return (f(x + h) - f(x - h)) / (2.0 * h);
    if (order == 2) return (f(x + h) - 2.0 * f(x) + f(x - h)) / (h * h);
    throw Error("E_INPUT", "order must be 1 or 2", "order");
}

}  // namespace quantforge
