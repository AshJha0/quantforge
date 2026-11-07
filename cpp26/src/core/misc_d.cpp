#include "quantforge/core/misc_d.hpp"

#include <cmath>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

constexpr auto mf = BusinessDayConvention::ModifiedFollowing;

Date spot_plus(const Curve& c, long long months) {
    const Date spot = add_business_days(Calendar::Usgs, c.as_of(), 2);
    return adjust(Calendar::Usgs, add_months(spot, int(months)), mf);
}

double option(RateVolModel m, double f, double k, double vol, double t, double phi) {
    return m == RateVolModel::Black76 ? black_price(f, k, vol, t, 1.0, phi) : bachelier_price(f, k, vol, t, 1.0, phi);
}

void check_months(long long tenor) {
    if (tenor < 1 || tenor > 1200) throw Error("E_INPUT", "tenor_months is out of range", "trade");
}

}  // namespace

CapPrice cap_price(const Curve& discount, const Curve& projection, RateVolModel model, const std::vector<double>& vols, bool flat,
                   double phi, long long start_months, long long tenor_months, double strike, double notional) {
    if (start_months < 1 || start_months > 1200) throw Error("E_INPUT", "start_months must be at least 1", "trade");
    check_months(tenor_months);
    const Date start = spot_plus(discount, start_months);
    const auto periods = generate_schedule(start, add_months(start, int(tenor_months)), 3, Calendar::Usgs, false, 0);
    if (!flat && vols.size() != periods.size()) throw Error("E_INPUT", "one vol per caplet is needed", "vol");
    for (const double v : vols)
        if (!(v >= 0.0)) throw Error("E_DOMAIN", "a vol is negative", "vol");
    std::vector<double> fwd;
    for (const Period& p : periods)
        fwd.push_back((projection.discount(p.start) / projection.discount(p.end) - 1.0) / year_fraction(DayCount::Act360, p.start, p.end));
    if (model == RateVolModel::Black76) {
        if (!(strike > 0.0)) throw Error("E_DOMAIN", "BLACK_76 needs a positive strike", "trade");
        for (const double f : fwd)
            if (!(f > 0.0)) throw Error("E_DOMAIN", "BLACK_76 needs positive forwards", "projection");
    }
    CapPrice out{{}, 0.0};
    for (std::size_t i = 0; i < periods.size(); ++i) {
        const Period& p = periods[i];
        const double alpha = year_fraction(DayCount::Act360, p.start, p.end);
        const double v = notional * alpha * discount.discount(p.end) *
                         option(model, fwd[i], strike, flat ? vols[0] : vols[i], discount.time(p.start), phi);
        out.caplets.push_back(v);
        out.price += v;
    }
    return out;
}

SwaptionPrice swaption_price(const Curve& discount, const Curve& projection, RateVolModel model, double vol, double phi,
                             long long expiry_months, long long tenor_months, double strike, double notional) {
    if (expiry_months < 1 || expiry_months > 1200) throw Error("E_INPUT", "expiry_months must be at least 1", "trade");
    check_months(tenor_months);
    if (!(vol >= 0.0)) throw Error("E_DOMAIN", "vol is negative", "vol");
    const RateConvention& index = *rate_convention("USD-TERM-3M");
    const Date s = spot_plus(discount, expiry_months), end = add_months(s, int(tenor_months));
    double annuity = 0.0, floating = 0.0;
    for (const Period& p : generate_schedule(s, end, index.fixed_months, Calendar::Usgs, false, 0))
        annuity += year_fraction(index.fixed_day_count, p.start, p.end) * discount.discount(p.end);
    for (const Period& p : generate_schedule(s, end, index.months, Calendar::Usgs, false, 0))
        floating += (projection.discount(p.start) / projection.discount(p.end) - 1.0) * discount.discount(p.end);
    const double f = floating / annuity;
    if (model == RateVolModel::Black76 && (!(strike > 0.0) || !(f > 0.0)))
        throw Error("E_DOMAIN", "BLACK_76 needs a positive strike and forward", "trade");
    return {notional * annuity * option(model, f, strike, vol, discount.time(s), phi), f, annuity};
}

std::vector<double> commodity_forwards(const std::vector<CommodityQuote>& q, const std::optional<std::vector<double>>& seasonality,
                                       const std::vector<long long>& months) {
    if (q.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    for (std::size_t j = 1; j < q.size(); ++j)
        if (q[j].month <= q[j - 1].month) throw Error("E_INPUT", "quote months must strictly increase", "quotes");
    for (const CommodityQuote& x : q)
        if (!(x.price > 0.0)) throw Error("E_DOMAIN", "a price is not positive", "quotes");
    if (seasonality && seasonality->size() != 12) throw Error("E_INPUT", "seasonality needs 12 terms", "seasonality");
    const auto sigma = [&](long long k) { return seasonality ? (*seasonality)[std::size_t(((k % 12) + 12) % 12)] : 0.0; };
    std::vector<double> out;
    for (const long long k : months) {
        if (k < q.front().month || k > q.back().month) throw Error("E_OUT_OF_RANGE", "the month is outside the quotes", "months");
        std::size_t j = 0;
        while (j + 1 < q.size() && q[j + 1].month < k) ++j;
        double l;
        if (k == q[j].month) l = std::log(q[j].price) - sigma(q[j].month);
        else {
            const double l0 = std::log(q[j].price) - sigma(q[j].month), l1 = std::log(q[j + 1].price) - sigma(q[j + 1].month);
            l = l0 + (l1 - l0) * double(k - q[j].month) / double(q[j + 1].month - q[j].month);
        }
        out.push_back(std::exp(l + sigma(k)));
    }
    return out;
}

StorageCarry storage_carry(const Curve& funding, const std::vector<DatedPrice>& f, double u) {
    if (f.size() < 2) throw Error("E_INPUT", "at least two forwards are needed", "forwards");
    Date previous = funding.as_of();
    for (const DatedPrice& x : f) {
        if (x.date <= previous) throw Error("E_INPUT", "forward dates must increase and follow as_of", "forwards");
        previous = x.date;
    }
    if (!(u >= 0.0)) throw Error("E_DOMAIN", "storage_cost is negative", "storage_cost");
    for (const DatedPrice& x : f)
        if (!(x.price > 0.0)) throw Error("E_DOMAIN", "a forward price is not positive", "forwards");
    StorageCarry out;
    for (std::size_t i = 1; i < f.size(); ++i) {
        const double dt = double(days_between(f[i - 1].date, f[i].date)) / 365.0;
        const double d0 = funding.discount(f[i - 1].date), d1 = funding.discount(f[i].date);
        const double r = std::log(d0 / d1) / dt;
        out.convenience_yields.push_back(r + u - std::log(f[i].price / f[i - 1].price) / dt);
        const double carry = d1 * f[i].price - d0 * f[i - 1].price * std::exp(u * dt);
        out.carry_values.push_back(carry);
        out.arbitrage.push_back(carry > 0.0);
    }
    return out;
}

MbsCashflows mbs_cashflows(const MbsPool& p) {
    if (p.wam < 1 || p.wam > 1200 || p.age < 0 || p.age > 1200) throw Error("E_INPUT", "wam or age is out of range", "pool");
    // wac <= 0 is reported before net_coupon > wac, which presumes a valid wac (mbs_d-0011; SPEC_QUESTIONS 18).
    if (!(p.wac > 0.0)) throw Error("E_DOMAIN", "wac must be positive", "pool");
    if (p.net_coupon > p.wac) throw Error("E_INPUT", "net_coupon is above wac", "pool");
    if (!(p.balance > 0.0)) throw Error("E_DOMAIN", "wac and balance must be positive", "pool");
    if (!p.psa && !(p.rate_or_speed >= 0.0 && p.rate_or_speed < 1.0)) throw Error("E_DOMAIN", "rate must be in [0, 1)", "pool");
    if (p.psa && !(p.rate_or_speed >= 0.0)) throw Error("E_DOMAIN", "speed is negative", "pool");
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
