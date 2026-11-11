// Stage G wave 4c (06-risk/xva-exposure-portfolio.md, ruling G-42): exposure of a swap netting set under Hull-White in
// LGM coordinates. At each date the deflated set value is a sum of exponentials in the one Gaussian state x, so EE, ENE
// and the PFE quantiles are exact Gaussian integrals between the zeros of f; the zeros are found on monotone segments
// bounded by the critical points of f.
#include <algorithm>
#include <cmath>
#include <map>

#include "quantforge/core/shortrate.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::shortrate {

namespace {
// Stand-in for an infinite end: normal_cdf is exact there (it is not defined at +-inf).
constexpr double kBig = 1e300;
bool fin(double x) { return std::fabs(x) < 1e299; }

struct Expo {
    std::vector<double> c, b;  // f(x) = sum c_k exp(-b_k x)
    double eval(double x) const {
        double s = 0.0;
        for (std::size_t k = 0; k < c.size(); ++k) s += c[k] * std::exp(-b[k] * x);
        return s;
    }
    double deriv(double x) const {
        double s = 0.0;
        for (std::size_t k = 0; k < c.size(); ++k) s -= b[k] * c[k] * std::exp(-b[k] * x);
        return s;
    }
};

// Root of g on [lo, hi] with a sign change, by bisection to adjacent doubles.
template <class G>
double bisect(G g, double lo, double hi) {
    double glo = g(lo);
    for (int it = 0; it < 200; ++it) {
        const double mid = 0.5 * (lo + hi);
        if (mid <= lo || mid >= hi) break;
        const double gm = g(mid);
        if (gm == 0.0) return mid;
        if ((gm < 0) == (glo < 0)) lo = mid, glo = gm;
        else hi = mid;
    }
    return 0.5 * (lo + hi);
}

// P(a < Z < b) for a standard normal Z, accurate in either tail.
double phi_between(double a, double b) {
    if (a >= b) return 0.0;
    if (a > 0) return normal_cdf(-a) - normal_cdf(-b);
    return normal_cdf(b) - normal_cdf(a);
}

struct Profile {
    Expo f;
    double s;                       // sqrt(zeta)
    std::vector<double> seg;        // segment ends in x, monotone f on each; -inf and +inf at the ends
    // Intervals (in x) where f > y, as a list of [l, u].
    std::vector<std::pair<double, double>> above(double y) const {
        std::vector<double> cuts{-kBig};
        for (std::size_t i = 0; i + 1 < seg.size(); ++i) {
            const double l = fin(seg[i]) ? seg[i] : -60 * s;
            const double u = fin(seg[i + 1]) ? seg[i + 1] : 60 * s;
            const double gl = f.eval(l) - y, gu = f.eval(u) - y;
            if ((gl < 0 && gu > 0) || (gl > 0 && gu < 0))
                cuts.push_back(bisect([&](double x) { return f.eval(x) - y; }, l, u));
        }
        cuts.push_back(kBig);
        std::vector<std::pair<double, double>> out;
        for (std::size_t i = 0; i + 1 < cuts.size(); ++i) {
            const double l = cuts[i], u = cuts[i + 1];
            double probe;
            if (fin(l) && fin(u)) probe = 0.5 * (l + u);
            else if (fin(l)) probe = l + s;
            else if (fin(u)) probe = u - s;
            else probe = 0.0;
            if (f.eval(probe) > y) out.push_back({l, u});
        }
        return out;
    }
};
}  // namespace

namespace {
// The deflated set value at t as a sum of exponentials in x, with its monotone segments: the critical points of f are
// found by a sign scan of f' at 0.01 standard deviations (finer than any feature of a swap portfolio's f), then bisection.
Profile make_profile(const Params& p, const std::vector<SwapTrade>& trades, double t) {
    const double a = p.a, sg = p.sigma;
    const double Ht = -std::expm1(-a * t) / a;
    const double zeta = sg * sg * std::expm1(2 * a * t) / (2 * a);
    const auto deflated_bond = [&](double T, double scale, std::map<double, double>& terms) {
        const double HT = -std::expm1(-a * T) / a;
        // P(t, T, x) / N(t, x) = P(0, T) exp(-H(T) x - H(T)^2 zeta / 2)
        terms[HT] += scale * p.curve.df(T) * std::exp(-HT * HT * zeta / 2);
    };
    std::map<double, double> terms;  // exponent b -> coefficient
    for (const SwapTrade& tr : trades) {
        if (!(tr.payment_times.back() > t)) continue;  // matured
        const double sgn = (tr.pay ? 1.0 : -1.0) * tr.notional;
        const double T0 = std::max(t, tr.start);
        if (T0 == t) terms[Ht] += sgn * p.curve.df(t) * std::exp(-Ht * Ht * zeta / 2);
        else deflated_bond(T0, sgn, terms);
        deflated_bond(tr.payment_times.back(), -sgn, terms);
        double prev = tr.start;
        for (double T : tr.payment_times) {
            if (T > t) deflated_bond(T, -sgn * tr.fixed_rate * (T - prev), terms);
            prev = T;
        }
    }
    Profile pr;
    pr.s = std::sqrt(zeta);
    for (const auto& [b, c] : terms)
        if (c != 0.0) pr.f.b.push_back(b), pr.f.c.push_back(c);
    // Critical points of f on [-L, L] by a fine scan of f' and bisection.
    const double L = 40 * pr.s;
    const int n = 8000;
    pr.seg.push_back(-kBig);
    double xprev = -L, dprev = pr.f.deriv(xprev);
    for (int i = 1; i <= n; ++i) {
        const double x = -L + 2 * L * i / n, d = pr.f.deriv(x);
        if ((dprev < 0 && d > 0) || (dprev > 0 && d < 0))
            pr.seg.push_back(bisect([&](double z) { return pr.f.deriv(z); }, xprev, x));
        xprev = x, dprev = d;
    }
    pr.seg.push_back(kBig);
    return pr;
}
}  // namespace

double portfolio_prob_above_hw(const Params& p, const std::vector<SwapTrade>& trades, double t, double y) {
    const Profile pr = make_profile(p, trades, t);
    double s = 0.0;
    for (const auto& [l, u] : pr.above(y)) s += phi_between(l / pr.s, u / pr.s);
    return s;
}

PortfolioExposure portfolio_exposure_hw(const Params& p, const std::vector<SwapTrade>& trades, const std::vector<double>& times,
                                        const std::vector<double>& quantiles, double hazard, double recovery) {
    const double a = p.a, sg = p.sigma;
    PortfolioExposure out;
    out.pfe.assign(quantiles.size(), {});
    for (double t : times) {
        const double zeta = sg * sg * std::expm1(2 * a * t) / (2 * a);
        const Profile pr = make_profile(p, trades, t);
        // EE and ENE: integrals of f over the intervals where f > 0 and the rest.
        const auto integral = [&](double l, double u) {
            double v = 0.0;
            for (std::size_t k = 0; k < pr.f.c.size(); ++k) {
                const double b = pr.f.b[k], shift = b * zeta;
                v += pr.f.c[k] * std::exp(b * b * zeta / 2) * phi_between((l + shift) / pr.s, (u + shift) / pr.s);
            }
            return v;
        };
        const auto pos = pr.above(0.0);
        double ee = 0.0, total = integral(-kBig, kBig);
        for (const auto& [l, u] : pos) ee += integral(l, u);
        out.discounted_ee.push_back(ee);
        out.discounted_ene.push_back(total - ee);
        // PFE: smallest y >= 0 with P(f <= y) >= q.
        const auto prob_above = [&](double y) {
            double s = 0.0;
            for (const auto& [l, u] : pr.above(y)) s += phi_between(l / pr.s, u / pr.s);
            return s;
        };
        double fmax = 0.0;
        for (double x : pr.seg)
            if (fin(x)) fmax = std::max(fmax, pr.f.eval(x));
        fmax = std::max({fmax, pr.f.eval(-40 * pr.s), pr.f.eval(40 * pr.s)});
        for (std::size_t qi = 0; qi < quantiles.size(); ++qi) {
            const double q = quantiles[qi];
            if (1.0 - prob_above(0.0) >= q) {
                out.pfe[qi].push_back(0.0);
                continue;
            }
            double lo = 0.0, hi = std::max(fmax, 1e-300);
            while (1.0 - prob_above(hi) < q) hi *= 2;
            for (int it = 0; it < 200; ++it) {
                const double mid = 0.5 * (lo + hi);
                if (mid <= lo || mid >= hi) break;
                if (1.0 - prob_above(mid) >= q) hi = mid;
                else lo = mid;
            }
            out.pfe[qi].push_back(hi);
        }
    }
    double epe = 0.0, cva = 0.0, prev = 0.0;
    for (std::size_t i = 0; i < times.size(); ++i) {
        epe += out.discounted_ee[i] * (times[i] - prev);
        cva += out.discounted_ee[i] * (std::exp(-hazard * prev) - std::exp(-hazard * times[i]));
        prev = times[i];
    }
    out.epe = epe / times.back();
    out.cva = (1 - recovery) * cva;
    return out;
}

}  // namespace quantforge::shortrate
