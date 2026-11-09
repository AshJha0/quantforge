#include "quantforge/core/credit_options.hpp"

#include <algorithm>
#include <array>
#include <utility>
#include <cmath>
#include <numbers>
#include <string>

#include "quantforge/core/black.hpp"
#include "quantforge/core/calendar.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/integrate.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

constexpr double pi = std::numbers::pi;

// 20-point Gauss-Legendre rule on [-1, 1].
struct Rule20 {
    std::array<double, 20> x, w;
};
const Rule20& gl20() {
    static const Rule20 rule = [] {
        Rule20 r{};
        constexpr int n = 20;
        for (int i = 0; i < n / 2; ++i) {
            double x = std::cos(pi * (i + 0.75) / (n + 0.5)), dp = 0.0;
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
            r.x[i] = -x, r.w[i] = w;
            r.x[n - 1 - i] = x, r.w[n - 1 - i] = w;
        }
        return r;
    }();
    return rule;
}

// Genz's bvnu: P(X > h, Y > k) with correlation r.
double bvnu(double h, double k, double r) {
    const Rule20& g = gl20();
    double hk = h * k, bvn = 0.0;
    if (std::fabs(r) < 0.925) {
        const double hs = (h * h + k * k) / 2, asr = std::asin(r);
        for (int i = 0; i < 20; ++i) {
            const double sn = std::sin(asr * (1 + g.x[i]) / 2);
            bvn += g.w[i] * std::exp((sn * hk - hs) / (1 - sn * sn));
        }
        return bvn * asr / (4 * pi) + normal_cdf(-h) * normal_cdf(-k);
    }
    if (r < 0) k = -k, hk = -hk;
    if (std::fabs(r) < 1) {
        const double as = (1 - r) * (1 + r);
        double a = std::sqrt(as);
        const double bs = (h - k) * (h - k), c = (4 - hk) / 8, d = (12 - hk) / 16;
        bvn = a * std::exp(-(bs / as + hk) / 2) * (1 - c * (bs - as) * (1 - d * bs / 5) / 3 + c * d * as * as / 5);
        if (hk > -160) {
            const double b = std::sqrt(bs);
            bvn -= std::exp(-hk / 2) * std::sqrt(2 * pi) * normal_cdf(-b / a) * b * (1 - c * bs * (1 - d * bs / 5) / 3);
        }
        a /= 2;
        for (int i = 0; i < 20; ++i) {
            const double xs = (a * (1 + g.x[i])) * (a * (1 + g.x[i])), rs = std::sqrt(1 - xs);
            bvn += a * g.w[i] *
                   (std::exp(-bs / (2 * xs) - hk / (1 + rs)) / rs - std::exp(-(bs / xs + hk) / 2) * (1 + c * xs * (1 + d * xs)));
        }
        bvn = -bvn / (2 * pi);
    }
    if (r > 0) return bvn + normal_cdf(-std::max(h, k));
    bvn = -bvn;
    if (k > h) bvn += normal_cdf(k) - normal_cdf(h);
    return bvn;
}

// Regularised incomplete beta I_x(a, b) by Lentz's continued fraction.
double betacf(double a, double b, double x) {
    constexpr double tiny = 1e-300;
    const double qab = a + b, qap = a + 1, qam = a - 1;
    double c = 1, d = 1 - qab * x / qap;
    if (std::fabs(d) < tiny) d = tiny;
    d = 1 / d;
    double h = d;
    for (int m = 1; m <= 10000; ++m) {
        const double m2 = 2.0 * m;
        double aa = m * (b - m) * x / ((qam + m2) * (a + m2));
        d = 1 + aa * d;
        if (std::fabs(d) < tiny) d = tiny;
        c = 1 + aa / c;
        if (std::fabs(c) < tiny) c = tiny;
        d = 1 / d;
        h *= d * c;
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
        d = 1 + aa * d;
        if (std::fabs(d) < tiny) d = tiny;
        c = 1 + aa / c;
        if (std::fabs(c) < tiny) c = tiny;
        d = 1 / d;
        const double del = d * c;
        h *= del;
        if (std::fabs(del - 1) < 1e-16) break;
    }
    return h;
}
double incomplete_beta(double a, double b, double x) {
    if (x <= 0) return 0.0;
    if (x >= 1) return 1.0;
    const double front = std::exp(std::lgamma(a + b) - std::lgamma(a) - std::lgamma(b) + a * std::log(x) + b * std::log1p(-x));
    if (x < (a + 1) / (a + b + 2)) return front * betacf(a, b, x) / a;
    return 1 - front * betacf(b, a, 1 - x) / b;
}

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

void prob(double p, const char* key) {
    if (!(p > 0 && p < 1)) throw Error("E_DOMAIN", std::string(key) + " must be in (0, 1)", key);
}

struct Legs {
    double protection, annuity, t_expiry, s_expiry, p_expiry;
};
Legs cds_legs(const CdsOptionInputs& in) {
    if (!(in.expiry > in.as_of) || !(in.maturity > in.expiry)) throw Error("E_INPUT", "as_of < expiry < maturity is needed");
    if (!(in.recovery >= 0 && in.recovery < 1)) throw Error("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
    if (!(in.hazard_rate >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", "hazard_rate");
    if (!(in.strike > 0)) throw Error("E_DOMAIN", "strike is not above 0", "strike");
    const auto t = [&](Date d) { return double(days_between(in.as_of, d)) / 365.0; };
    const auto s = [&](Date d) { return std::exp(-in.hazard_rate * t(d)); };
    const auto p = [&](Date d) { return std::exp(-in.rate * t(d)); };
    std::vector<Date> dates{in.expiry};
    for (int k = 1;; ++k) {
        const Date d = add_months(in.expiry, 3 * k);
        if (d >= in.maturity) break;
        dates.push_back(d);
    }
    dates.push_back(in.maturity);
    Legs l{0.0, 0.0, t(in.expiry), s(in.expiry), p(in.expiry)};
    for (std::size_t i = 0; i + 1 < dates.size(); ++i) {
        const Date a = dates[i], b = dates[i + 1];
        const int len = days_between(a, b);
        const Date m = a + std::chrono::days{len / 2};
        const double ds = s(a) - s(b);
        l.protection += (1 - in.recovery) * p(m) * ds;
        l.annuity += double(len) / 360.0 * p(b) * s(b) + double(days_between(a, m)) / 360.0 * p(m) * ds;
    }
    return l;
}

}  // namespace

double bivariate_normal_cdf(double a, double b, double rho) { return bvnu(-a, -b, rho); }

double student_t_cdf(double x, double nu) {
    const double tail = 0.5 * incomplete_beta(nu / 2, 0.5, nu / (nu + x * x));
    return x >= 0 ? 1 - tail : tail;
}

double student_t_inverse(double p, double nu) {
    return bisect([&](double x) { return student_t_cdf(x, nu) - p; }, -1e8, 1e8);
}

double bivariate_t_cdf(double a, double b, double rho, double nu) {
    // T = Z / sqrt(W/nu), W ~ chi^2_nu: average Phi_2(a s, b s) over s = sqrt(W/nu), density 2 nu s f_chi2(nu s^2).
    const double lc = std::lgamma(nu / 2) + (nu / 2) * std::log(2.0);
    const auto f = [&](double s) {
        if (s <= 0) return 0.0;
        const double w = nu * s * s;
        const double dens = 2 * nu * s * std::exp((nu / 2 - 1) * std::log(w) - w / 2 - lc);
        return dens * bivariate_normal_cdf(a * s, b * s, rho);
    };
    const double smax = std::sqrt((nu + 40 * std::sqrt(2 * nu) + 200) / nu);
    // Split at the mode region so the adaptive rule sees the peak.
    return gauss_kronrod(f, 0.0, 1.0, 1e-15, 2000).value + gauss_kronrod(f, 1.0, smax, 1e-15, 2000).value;
}

namespace {
void finite_cds(const CdsOptionInputs& in) {
    require_finite(in.rate, "rate");
    require_finite(in.hazard_rate, "hazard_rate");
    require_finite(in.recovery, "recovery");
    require_finite(in.strike, "strike");
    require_finite(in.notional, "notional");
}
}  // namespace

CdsOptionPrice cds_option_price(const CdsOptionInputs& in, double vol) {
    finite_cds(in);
    require_finite(vol, "vol");
    const Legs l = cds_legs(in);
    if (!(vol >= 0)) throw Error("E_DOMAIN", "vol is negative", "vol");
    const double f = l.protection / l.annuity, phi = in.payer ? 1.0 : -1.0;
    const double fep = in.notional * (1 - in.recovery) * (1 - l.s_expiry) * l.p_expiry;
    double price = in.notional * l.annuity * black_price(f, in.strike, vol, l.t_expiry, 1.0, phi);
    if (in.payer && !in.knock_out) price += fep;
    return {price, f, l.annuity, fep};
}

double cds_option_implied_vol(const CdsOptionInputs& in, double premium) {
    finite_cds(in);
    require_finite(premium, "premium");
    if (!in.knock_out) throw Error("E_INPUT", "implied vol is for knock-out options only", "knock_out");
    const Legs l = cds_legs(in);
    const double f = l.protection / l.annuity, phi = in.payer ? 1.0 : -1.0, scale = in.notional * l.annuity;
    const double lower = scale * std::max(phi * (f - in.strike), 0.0), upper = scale * (in.payer ? f : in.strike);
    if (!(premium > lower) || !(premium < upper)) throw Error("E_DOMAIN", "premium is outside the no-arbitrage bounds", "premium");
    const auto gap = [&](double v) { return scale * black_price(f, in.strike, v, l.t_expiry, 1.0, phi) - premium; };
    double hi = 1.0;
    for (int i = 0; gap(hi) < 0 && i < 200; ++i) hi *= 2;
    return bisect(gap, 0.0, hi);
}

namespace {
// Strike legs measured from expiry on a flat hazard x (ruling F-8): returns {prot', A'}.
struct StrikeLegs {
    std::vector<Date> dates;
    Date expiry;
    double rate, recovery;
    std::pair<double, double> at(double x) const {
        const auto t = [&](Date d) { return double(days_between(expiry, d)) / 365.0; };
        double prot = 0.0, ann = 0.0;
        for (std::size_t i = 0; i + 1 < dates.size(); ++i) {
            const Date a = dates[i], b = dates[i + 1];
            const int len = days_between(a, b);
            const Date m = a + std::chrono::days{len / 2};
            const double sa = std::exp(-x * t(a)), sb = std::exp(-x * t(b)), pm = std::exp(-rate * t(m));
            const double pb = std::exp(-rate * t(b));
            prot += (1 - recovery) * pm * (sa - sb);
            ann += double(len) / 360.0 * pb * sb + double(days_between(a, m)) / 360.0 * pm * (sa - sb);
        }
        return {prot, ann};
    }
};
}  // namespace

CdsIndexOptionPrice cds_index_option_price(const CdsIndexOptionInputs& in) {
    require_finite(in.rate, "rate");
    require_finite(in.hazard_rate, "hazard_rate");
    require_finite(in.recovery, "recovery");
    require_finite(in.strike, "strike");
    require_finite(in.coupon, "coupon");
    require_finite(in.notional, "notional");
    require_finite(in.vol, "vol");
    const CdsOptionInputs base{in.as_of, in.expiry, in.maturity, in.rate, in.hazard_rate, in.recovery, in.payer, in.strike, in.notional, false};
    const Legs l = cds_legs(base);  // dates, recovery, hazard_rate, strike checks
    if (!(in.coupon >= 0)) throw Error("E_DOMAIN", "coupon is negative", "coupon");
    if (!(in.vol >= 0)) throw Error("E_DOMAIN", "vol is negative", "vol");
    if (!(in.notional > 0)) throw Error("E_DOMAIN", "notional is not above 0", "notional");
    const double a = l.annuity, f = l.protection / a;
    const double fep = (1 - in.recovery) * (1 - l.s_expiry) * l.p_expiry;
    // Strike hazard h_K: prot'/A' = K, bisection on [0, x_hi] to the last representable step.
    StrikeLegs sl{{in.expiry}, in.expiry, in.rate, in.recovery};
    for (int k = 1;; ++k) {
        const Date d = add_months(in.expiry, 3 * k);
        if (d >= in.maturity) break;
        sl.dates.push_back(d);
    }
    sl.dates.push_back(in.maturity);
    const auto gap = [&](double x) {
        const auto [p, an] = sl.at(x);
        return p / an - in.strike;
    };
    double lo = 0.0, hi = 2 * in.strike / (1 - in.recovery);
    for (int i = 0; gap(hi) <= 0 && i < 2000; ++i) lo = hi, hi *= 2;
    for (int i = 0; i < 2000; ++i) {
        const double mid = 0.5 * (lo + hi);
        if (mid <= lo || mid >= hi) break;
        if (gap(mid) < 0) lo = mid;
        else hi = mid;
    }
    const double hk = std::fabs(gap(lo)) <= std::fabs(gap(hi)) ? lo : hi;
    const double ak = sl.at(hk).second;
    const double g = (in.strike - in.coupon) * ak;
    const double fadj = f + fep / a, kadj = in.coupon + g * l.p_expiry / a;
    if (!(fadj > 0)) throw Error("E_DOMAIN", "adjusted forward is not above 0", "hazard_rate");
    if (!(kadj > 0)) throw Error("E_DOMAIN", "adjusted strike is not above 0", "strike");
    const double phi = in.payer ? 1.0 : -1.0;
    const double unit = in.vol > 0 ? black_price(fadj, kadj, in.vol, l.t_expiry, 1.0, phi) : std::max(phi * (fadj - kadj), 0.0);
    return {in.notional * a * unit, f, fadj, kadj, a, ak, hk, in.notional * g, in.notional * fep};
}

JointDefault copula_joint_default(CopulaKind kind, const std::vector<double>& p, double rho, std::optional<double> nu) {
    require_finite(p, "default_probabilities");
    require_finite(rho, "correlation");
    require_finite(nu, "degrees_of_freedom");
    if (p.size() != 2) throw Error("E_INPUT", "two default probabilities are needed", "default_probabilities");
    if (kind == CopulaKind::StudentT && !nu) throw Error("E_INPUT", "STUDENT_T needs degrees_of_freedom", "degrees_of_freedom");
    prob(p[0], "default_probabilities");
    prob(p[1], "default_probabilities");
    if (!(std::fabs(rho) < 1)) throw Error("E_DOMAIN", "|correlation| must be below 1", "correlation");
    if (kind == CopulaKind::StudentT && !(*nu > 0)) throw Error("E_DOMAIN", "degrees_of_freedom is not above 0", "degrees_of_freedom");
    const double joint = kind == CopulaKind::Gaussian
                             ? bivariate_normal_cdf(normal_inverse(p[0]), normal_inverse(p[1]), rho)
                             : bivariate_t_cdf(student_t_inverse(p[0], *nu), student_t_inverse(p[1], *nu), rho, *nu);
    return {joint, (joint - p[0] * p[1]) / std::sqrt(p[0] * (1 - p[0]) * p[1] * (1 - p[1]))};
}

namespace {
void check_pool(double p, double rho, double r) {
    prob(p, "default_probability");
    prob(rho, "correlation");
    if (!(r >= 0 && r < 1)) throw Error("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
}
// E[min(P(M), k)] (ruling E-B25).
double expected_min(double c, double rho, double p, double k) {
    if (k >= 1) return p;
    if (k <= 0) return 0.0;
    const double ms = (c - std::sqrt(1 - rho) * normal_inverse(k)) / std::sqrt(rho);
    return p - (bivariate_normal_cdf(c, ms, std::sqrt(rho)) - k * normal_cdf(ms));
}
}  // namespace

double lhp_tranche_loss(double p, double rho, double r, double a, double d) {
    require_finite(p, "default_probability");
    require_finite(rho, "correlation");
    require_finite(r, "recovery");
    require_finite(a, "attachment");
    require_finite(d, "detachment");
    if (!(d > a) || a < 0 || d > 1) throw Error("E_INPUT", "0 <= attachment < detachment <= 1 is needed");
    check_pool(p, rho, r);
    const double c = normal_inverse(p);
    const double hi = expected_min(c, rho, p, std::min(d / (1 - r), 1.0));
    const double lo = a == 0 ? 0.0 : expected_min(c, rho, p, std::min(a / (1 - r), 1.0));
    return (1 - r) * (hi - lo) / (d - a);
}

std::vector<double> lhp_loss_cdf(double p, double rho, double r, const std::vector<double>& x) {
    require_finite(p, "default_probability");
    require_finite(rho, "correlation");
    require_finite(r, "recovery");
    require_finite(x, "losses");
    if (x.empty()) throw Error("E_INPUT", "losses is empty", "losses");
    check_pool(p, rho, r);
    for (const double v : x)
        if (!(v > 0 && v < 1 - r)) throw Error("E_DOMAIN", "a loss is outside (0, 1 - R)", "losses");
    const double c = normal_inverse(p);
    std::vector<double> out;
    for (const double v : x) out.push_back(normal_cdf((std::sqrt(1 - rho) * normal_inverse(v / (1 - r)) - c) / std::sqrt(rho)));
    return out;
}

}  // namespace quantforge
