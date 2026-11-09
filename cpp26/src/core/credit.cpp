#include "quantforge/core/credit.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

Date add_days(Date d, int n) { return Date(d + std::chrono::days(n)); }
bool weekday(Date d) { return weekday_of(d) != 0 && weekday_of(d) != 6; }
Date next_weekday(Date d) {
    while (!weekday(d)) d = add_days(d, 1);
    return d;
}
Date add_weekdays(Date d, int n) {
    for (int i = 0; i < n; ++i) {
        d = add_days(d, 1);
        while (!weekday(d)) d = add_days(d, 1);
    }
    return d;
}

struct CdsSchedule {
    std::vector<Date> start, end, pay;
    std::vector<double> alpha;
};

CdsSchedule cds_schedule(Date t, Date maturity) {
    if (maturity <= t) throw Error("E_INPUT", "maturity must follow trade_date (ruling D52)", "maturity");
    const int y = year_of(t);
    const unsigned q = month_of(t) / 3 * 3;  // 0, 3, 6, 9 or 12
    Date u = q == 0 ? make_date(y - 1, 12, 20) : make_date(y, q, 20);
    if (u > t) u = add_months(u, -3);
    std::vector<Date> dates{u};
    while (dates.back() < maturity) dates.push_back(std::min(add_months(dates.back(), 3), maturity));
    for (std::size_t i = 0; i + 1 < dates.size(); ++i)
        if (next_weekday(dates[i]) == t) throw Error("E_INPUT", "trade_date is on a coupon date (ruling D19)", "trade_date");
    CdsSchedule s;
    for (std::size_t i = 1; i < dates.size(); ++i) {
        const bool last = i + 1 == dates.size();
        const Date st = next_weekday(dates[i - 1]), en = last ? maturity : next_weekday(dates[i]);
        s.start.push_back(st);
        s.end.push_back(en);
        s.pay.push_back(next_weekday(dates[i]));
        s.alpha.push_back((double(days_between(st, en)) + (last ? 1.0 : 0.0)) / 360.0);
    }
    return s;
}

struct CdsLegs {
    double protection, rpv01, accrued_fraction, pcs;
};

CdsLegs cds_legs(Date t, const Curve& p, const HazardCurve& h, Date maturity) {
    const CdsSchedule s = cds_schedule(t, maturity);
    std::vector<Date> nodes;
    for (const Pillar& x : p.pillars()) nodes.push_back(x.date);
    for (const Date x : h.dates) nodes.push_back(x);
    std::ranges::sort(nodes);
    const auto time = [&](Date d) { return double(days_between(t, d)) / 365.0; };
    const auto pieces = [&](Date a, Date b, auto&& body) {
        Date lo = a;
        for (const Date n : nodes) {
            if (n <= lo || n >= b) continue;
            body(lo, n);
            lo = n;
        }
        if (b > lo) body(lo, b);
    };
    struct Piece {
        double h, k, qp0, dt, t0;
    };
    const auto piece = [&](Date a, Date b) {
        const double t0 = time(a), t1 = time(b), q0 = h.q(a), q1 = h.q(b), p0 = p.discount(a), p1 = p.discount(b);
        const double dt = t1 - t0, hz = std::log(q0 / q1) / dt;
        return Piece{hz, std::log(p0 / p1) / dt + hz, q0 * p0, dt, t0};
    };
    CdsLegs out{0.0, 0.0, 0.0, p.discount(add_weekdays(t, 3))};
    pieces(t, maturity, [&](Date a, Date b) {
        const Piece x = piece(a, b);
        const double kd = x.k * x.dt;
        out.protection += x.h * x.qp0 * (kd == 0.0 ? x.dt : -std::expm1(-kd) / x.k);
    });
    for (std::size_t i = 0; i < s.pay.size(); ++i) {
        const Date obs = add_days(s.pay[i], -1);
        out.rpv01 += s.alpha[i] * h.q(obs) * p.discount(s.pay[i]);
        const Date acc_start = add_days(s.start[i], -1);
        const double tacc = time(acc_start);
        double aod = 0.0;
        pieces(std::max(acc_start, t), obs, [&](Date a, Date b) {
            const Piece x = piece(a, b);
            const double kd = x.k * x.dt;
            double first, second;
            if (std::fabs(kd) < 1e-4) {
                first = x.dt * (1 - kd / 2 + kd * kd / 6 - kd * kd * kd / 24 + kd * kd * kd * kd / 120);
                second = x.dt * x.dt * (0.5 - kd / 3 + kd * kd / 8 - kd * kd * kd / 30 + kd * kd * kd * kd / 144);
            } else {
                first = -std::expm1(-kd) / x.k;
                second = (1 - std::exp(-kd) * (1 + kd)) / (x.k * x.k);
            }
            aod += x.h * x.qp0 * ((x.t0 - tacc) * first + second);
        });
        out.rpv01 += 365.0 / 360.0 * aod;
    }
    out.accrued_fraction = double(days_between(s.start[0], add_days(t, 1))) / 360.0;
    return out;
}

void check_recovery(double r) {
    if (!(r >= 0.0 && r < 1.0)) throw Error("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
}

}  // namespace

void HazardCurve::check() const {
    require_finite(survival, "hazard");
    if (dates.empty() || dates.size() != survival.size()) throw Error("E_INPUT", "no hazard pillars", "hazard");
    Date previous = as_of;
    for (const Date d : dates) {
        if (d <= previous) throw Error("E_INPUT", "hazard pillars must increase and follow as_of", "hazard");
        previous = d;
    }
    for (const double s : survival)
        if (!(s > 0.0 && s <= 1.0)) throw Error("E_DOMAIN", "survival must be in (0, 1] (ruling D52)", "hazard");
}

double HazardCurve::q(Date d) const {
    const auto time = [&](Date x) { return double(days_between(as_of, x)) / 365.0; };
    const double t = time(d);
    if (t <= 0.0) return 1.0;
    double t0 = 0.0, l0 = 0.0;
    for (std::size_t i = 0; i < dates.size(); ++i) {
        const double t1 = time(dates[i]), l1 = -std::log(survival[i]);
        if (t <= t1 || i + 1 == dates.size()) return std::exp(-(l0 + (l1 - l0) * (t - t0) / (t1 - t0)));
        t0 = t1;
        l0 = l1;
    }
    return 1.0;
}

Date cds_maturity(Date t, Tenor tenor) {
    const int y = year_of(t);
    Date roll;
    if (t >= make_date(y, 9, 20)) roll = make_date(y, 12, 20);
    else if (t >= make_date(y, 3, 20)) roll = make_date(y, 6, 20);
    else roll = make_date(y - 1, 12, 20);
    if ((tenor.unit != 'M' && tenor.unit != 'Y') || tenor.count < 1) throw Error("E_INPUT", "CDS tenors are months or years", "tenor");
    return add_months(roll, int(tenor.unit == 'Y' ? 12 * tenor.count : tenor.count));
}

CdsPrice cds_price(Date t, const Curve& discount, const HazardCurve& hazard, double recovery, Date maturity, double coupon,
                   double notional, CdsSide side, CdsPayout payout) {
    require_finite(recovery, "recovery");
    require_finite(coupon, "coupon");
    require_finite(notional, "notional");
    require_finite(hazard.survival, "hazard");
    check_recovery(recovery);
    hazard.check();
    if (hazard.as_of != t || discount.as_of() != t) throw Error("E_INPUT", "curves must be as of trade_date", "trade_date");
    const CdsLegs l = cds_legs(t, discount, hazard, maturity);
    const double prot = (payout == CdsPayout::Digital ? 1.0 : 1.0 - recovery) * l.protection;
    const double accrued = coupon * l.accrued_fraction;
    const double sign = side == CdsSide::Buy ? 1.0 : -1.0;
    return {prot,
            l.rpv01,
            accrued,
            prot / (l.rpv01 - l.accrued_fraction * l.pcs),
            (prot - coupon * l.rpv01) / l.pcs + accrued,
            sign * notional * (prot - coupon * l.rpv01 + accrued * l.pcs)};
}

HazardCurve cds_bootstrap(Date t, const Curve& discount, double recovery, const std::vector<CdsQuote>& quotes) {
    require_finite(recovery, "recovery");
    for (const CdsQuote& q : quotes) require_finite(q.spread, "quotes");
    check_recovery(recovery);
    if (quotes.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    std::vector<Date> mats;
    for (const CdsQuote& q : quotes) {
        mats.push_back(cds_maturity(t, q.tenor));
        if (mats.size() > 1 && mats.back() <= mats[mats.size() - 2]) throw Error("E_INPUT", "maturities must strictly increase", "quotes");
    }
    for (const CdsQuote& q : quotes)
        if (!(q.spread > 0.0)) throw Error("E_DOMAIN", "a spread is not positive", "quotes");
    if (mats[0] <= t) throw Error("E_INPUT", "a maturity is not after trade_date", "quotes");
    (void)cds_schedule(t, mats.back());  // the coupon-date check
    if (discount.as_of() != t) throw Error("E_INPUT", "the discount curve must be as of trade_date", "discount");
    HazardCurve h{t, {}, {}};
    for (std::size_t j = 0; j < quotes.size(); ++j) {
        const double tj = double(days_between(t, mats[j])) / 365.0;
        const double l_prev = j == 0 ? 0.0 : -std::log(h.survival.back());
        const double t_prev = j == 0 ? 0.0 : double(days_between(t, h.dates.back())) / 365.0;
        h.dates.push_back(mats[j]);
        h.survival.push_back(1.0);
        const auto par = [&](double hz) {
            h.survival[j] = std::exp(-(l_prev + hz * (tj - t_prev)));
            const CdsLegs l = cds_legs(t, discount, h, mats[j]);
            return (1.0 - recovery) * l.protection / (l.rpv01 - l.accrued_fraction * l.pcs) - quotes[j].spread;
        };
        double x = quotes[j].spread / (1.0 - recovery), best_x = x, best = HUGE_VAL;
        for (int it = 0; it < 100; ++it) {
            const double g = par(x);
            if (!std::isfinite(g)) throw Error("E_NO_CONVERGENCE", "the hazard solve did not converge");
            if (std::fabs(g) < best) {
                best = std::fabs(g);
                best_x = x;
            }
            if (best <= 1e-17) break;
            const double hh = 1e-7 * std::max(1e-3, std::fabs(x));
            const double step = g / ((par(x + hh) - par(x - hh)) / (2 * hh));
            if (!std::isfinite(step)) break;
            x -= step;
            if (std::fabs(step) < 1e-18) break;
        }
        par(best_x);
        if (best >= 1e-13) throw Error("E_NO_CONVERGENCE", "the hazard solve did not converge");
    }
    return h;
}

}  // namespace quantforge
