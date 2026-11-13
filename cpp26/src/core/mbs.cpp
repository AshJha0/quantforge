#include "quantforge/core/mbs.hpp"

#include <algorithm>
#include <cmath>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {

namespace {

void require_finite_pool(const MbsPool& p) {
    require_finite(p.balance, "pool");
    require_finite(p.wac, "pool");
    require_finite(p.net_coupon, "pool");
    require_finite(p.rate_or_speed, "pool");
}

}  // namespace

MbsCashflows mbs_cashflows(const MbsPool& p) {
    require_finite_pool(p);
    if (p.wam < 1 || p.wam > 1200 || p.age < 0 || p.age > 1200) throw Error("E_INPUT", "wam or age is out of range", "pool");
    // wac <= 0 is reported before net_coupon > wac, which presumes a valid wac (mbs_d-0011; SPEC_QUESTIONS 18).
    if (!(p.wac > 0.0)) throw Error("E_DOMAIN", "wac must be positive", "pool");
    if (p.net_coupon > p.wac) throw Error("E_INPUT", "net_coupon is above wac", "pool");
    if (!(p.balance > 0.0)) throw Error("E_DOMAIN", "wac and balance must be positive", "pool");
    if (!p.psa && !(p.rate_or_speed >= 0.0 && p.rate_or_speed < 1.0)) throw Error("E_DOMAIN", "rate must be in [0, 1)", "pool");
    if (p.psa && !(p.rate_or_speed >= 0.0)) throw Error("E_DOMAIN", "speed is negative", "pool");
    // R6-7.1: a PSA speed whose monthly CPR reaches 1 has no SMM; checked for every month before any cash flow.
    if (p.psa)
        for (long long k = 1; k <= p.wam; ++k)
            if (!(std::min(double(p.age + k) / 30.0, 1.0) * 0.06 * p.rate_or_speed / 100.0 < 1.0))
                throw Error("E_DOMAIN", "a PSA monthly CPR reaches 1", "pool");
    MbsCashflows out{{}, {}, {}, {}, 0.0};
    const double r = p.wac / 12.0;
    double b = p.balance;
    for (long long k = 1; k <= p.wam; ++k) {
        const double cpr = p.psa ? std::min(double(p.age + k) / 30.0, 1.0) * 0.06 * p.rate_or_speed / 100.0 : p.rate_or_speed;
        const double smm = 1.0 - std::pow(1.0 - cpr, 1.0 / 12.0);
        const double n = double(p.wam - k + 1);
        const double sched = k == p.wam ? b : b * r / (1.0 - std::pow(1.0 + r, -n)) - b * r;
        const double prepay = smm * (b - sched);
        out.balance.push_back(b);
        out.interest.push_back(b * p.net_coupon / 12.0);
        out.scheduled_principal.push_back(sched);
        out.prepayment.push_back(prepay);
        out.wal += double(k) / 12.0 * (sched + prepay);
        b = b - sched - prepay;
    }
    out.wal /= p.balance;
    return out;
}

MbsPrice mbs_price(const MbsPool& pool, double y, long long delay_days) {
    require_finite_pool(pool);
    require_finite(y, "yield");
    const MbsCashflows c = mbs_cashflows(pool);
    if (delay_days < 0 || delay_days > 3650) throw Error("E_INPUT", "delay_days must be at least 0", "delay_days");
    if (!(1.0 + y / 12.0 > 0.0)) throw Error("E_DOMAIN", "1 + yield/12 must be positive", "yield");
    const double v = 1.0 / (1.0 + y / 12.0);
    double pv = 0.0, dur = 0.0;
    for (std::size_t i = 0; i < c.balance.size(); ++i) {
        const double t = double(i + 1) + double(delay_days) / 30.0;
        const double cf = c.interest[i] + c.scheduled_principal[i] + c.prepayment[i], x = cf * std::pow(v, t);
        pv += x;
        dur += t / 12.0 * x * v;
    }
    return {100.0 * pv / pool.balance, dur / pv, c.wal};
}

}  // namespace quantforge
