#include "quantforge/core/misc_d.hpp"

#include <algorithm>
#include <cmath>
#include <string>

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

// ---- Stage E, E4 ----

namespace {

// Bisection to the last representable step on an increasing function with f(lo) < 0 < f(hi).
double bisect_up(auto&& f, double lo, double hi) {
    for (int i = 0; i < 400; ++i) {
        const double mid = 0.5 * (lo + hi);
        if (mid <= lo || mid >= hi) break;
        if (f(mid) < 0) lo = mid;
        else hi = mid;
    }
    return 0.5 * (lo + hi);
}

// (i, lambda) on a strictly increasing axis; x outside it is E_INPUT (ruling E-B8: no extrapolation).
std::pair<std::size_t, double> locate(const std::vector<double>& axis, double x, const char* what) {
    if (axis.size() == 1) {
        if (x != axis[0]) throw Error("E_INPUT", std::string(what) + " is outside the cube", "trade");
        return {0, 0.0};
    }
    if (x < axis.front() || x > axis.back()) throw Error("E_INPUT", std::string(what) + " is outside the cube", "trade");
    std::size_t i = 0;
    while (i + 2 < axis.size() && x > axis[i + 1]) ++i;
    return {i, (x - axis[i]) / (axis[i + 1] - axis[i])};
}

void check_bondfut(double futures, double strike, double t, double discount) {
    if (!(t > 0)) throw Error("E_DOMAIN", "expiry_years is not above 0", "expiry_years");
    if (!(futures > 0)) throw Error("E_DOMAIN", "futures_price is not above 0", "futures_price");
    if (!(strike > 0)) throw Error("E_DOMAIN", "strike is not above 0", "strike");
    if (!(discount > 0)) throw Error("E_DOMAIN", "discount_factor is not above 0", "discount_factor");
}

}  // namespace

CubeSwaption swaption_price_cube(const Curve& discount, const Curve& projection, const SabrCube& c, double phi,
                                 long long expiry_months, long long tenor_months, double strike, double notional) {
    const std::size_t ne = c.expiries_months.size(), nt = c.tenors_months.size();
    const auto shaped = [&](const std::vector<std::vector<double>>& m) {
        return m.size() == ne && std::ranges::all_of(m, [&](const std::vector<double>& r) { return r.size() == nt; });
    };
    if (ne == 0 || nt == 0 || !shaped(c.alpha) || !shaped(c.beta) || !shaped(c.rho) || !shaped(c.nu))
        throw Error("E_INPUT", "cube matrices must be expiries x tenors", "cube");
    for (std::size_t i = 1; i < ne; ++i)
        if (c.expiries_months[i] <= c.expiries_months[i - 1]) throw Error("E_INPUT", "expiries_months must increase", "cube");
    for (std::size_t j = 1; j < nt; ++j)
        if (c.tenors_months[j] <= c.tenors_months[j - 1]) throw Error("E_INPUT", "tenors_months must increase", "cube");
    if (expiry_months < 1 || expiry_months > 1200) throw Error("E_INPUT", "expiry_months must be at least 1", "trade");
    check_months(tenor_months);
    for (const long long m : c.expiries_months)
        if (m < 1 || m > 1200) throw Error("E_INPUT", "a node expiry is out of range", "cube");
    std::vector<double> times, tenors;
    for (const long long m : c.expiries_months) times.push_back(discount.time(spot_plus(discount, m)));
    for (const long long m : c.tenors_months) tenors.push_back(double(m) / 12.0);
    const Date s = spot_plus(discount, expiry_months);
    const double t = discount.time(s), len = double(tenor_months) / 12.0;
    const auto [i, u] = locate(times, t, "expiry");
    const auto [j, w] = locate(tenors, len, "tenor");
    const auto bilinear = [&](const std::vector<std::vector<double>>& m) {
        const std::size_t i1 = std::min(i + 1, ne - 1), j1 = std::min(j + 1, nt - 1);
        return (1 - u) * ((1 - w) * m[i][j] + w * m[i][j1]) + u * ((1 - w) * m[i1][j] + w * m[i1][j1]);
    };
    for (std::size_t a = 0; a < ne; ++a)
        for (std::size_t b = 0; b < nt; ++b) {
            if (!(c.alpha[a][b] > 0)) throw Error("E_DOMAIN", "a node alpha is not above 0", "cube");
            if (!(c.beta[a][b] >= 0 && c.beta[a][b] <= 1)) throw Error("E_DOMAIN", "a node beta is outside [0, 1]", "cube");
            if (!(std::fabs(c.rho[a][b]) < 1)) throw Error("E_DOMAIN", "a node |rho| is not below 1", "cube");
            if (!(c.nu[a][b] >= 0)) throw Error("E_DOMAIN", "a node nu is below 0", "cube");
        }
    const SabrParameters p{bilinear(c.alpha), bilinear(c.beta), bilinear(c.rho), bilinear(c.nu)};
    const RateConvention& index = *rate_convention("USD-TERM-3M");
    const Date end = add_months(s, int(tenor_months));
    double annuity = 0.0, floating = 0.0;
    for (const Period& q : generate_schedule(s, end, index.fixed_months, Calendar::Usgs, false, 0))
        annuity += year_fraction(index.fixed_day_count, q.start, q.end) * discount.discount(q.end);
    for (const Period& q : generate_schedule(s, end, index.months, Calendar::Usgs, false, 0))
        floating += (projection.discount(q.start) / projection.discount(q.end) - 1.0) * discount.discount(q.end);
    const double f = floating / annuity;
    check_sabr(t, p, f, {strike});
    const double vol = hagan_vol(f, strike, t, p);
    return {notional * annuity * black_price(f, strike, vol, t, 1.0, phi), f, annuity, vol, p};
}

CapStrip cap_strip(const Curve& discount, const Curve& projection, RateVolModel model, long long start_months, double strike,
                   const std::vector<long long>& tenors, const std::vector<double>& flat, double notional) {
    if (tenors.empty()) throw Error("E_INPUT", "cap_tenors_months is empty", "cap_tenors_months");
    for (std::size_t k = 0; k < tenors.size(); ++k)
        if (tenors[k] <= 0 || tenors[k] % 3 != 0 || (k > 0 && tenors[k] <= tenors[k - 1]))
            throw Error("E_INPUT", "cap tenors must be increasing multiples of 3", "cap_tenors_months");
    if (flat.size() != tenors.size()) throw Error("E_INPUT", "one flat vol per cap is needed", "flat_vols");
    for (const double v : flat)
        if (!(v > 0.0)) throw Error("E_DOMAIN", "a flat vol is not positive", "flat_vols");
    if (start_months < 1 || start_months > 1200) throw Error("E_INPUT", "start_months must be at least 1", "start_months");
    check_months(tenors.back());
    const Date start = spot_plus(discount, start_months);
    const auto periods = generate_schedule(start, add_months(start, int(tenors.back())), 3, Calendar::Usgs, false, 0);
    std::vector<double> fwd, scale, time;
    for (const Period& q : periods) {
        const double a = year_fraction(DayCount::Act360, q.start, q.end);
        fwd.push_back((projection.discount(q.start) / projection.discount(q.end) - 1.0) / a);
        scale.push_back(notional * a * discount.discount(q.end));
        time.push_back(discount.time(q.start));
    }
    if (model == RateVolModel::Black76) {
        if (!(strike > 0.0)) throw Error("E_DOMAIN", "BLACK_76 needs a positive strike", "strike");
        for (const double f : fwd)
            if (!(f > 0.0)) throw Error("E_DOMAIN", "BLACK_76 needs positive forwards", "projection");
    }
    const auto caplet = [&](std::size_t i, double v) { return scale[i] * option(model, fwd[i], strike, v, time[i], 1.0); };
    // Search interval, ruling E-B32: below it is E_ARBITRAGE, above it E_DOMAIN.
    const double lower = 1e-10, upper = model == RateVolModel::Black76 ? 5.0 : 0.5;
    CapStrip out;
    double known = 0.0;
    std::size_t done = 0;
    for (std::size_t k = 0; k < tenors.size(); ++k) {
        const std::size_t n = std::min(periods.size(), std::size_t(tenors[k] / 3));
        double target = 0.0;
        for (std::size_t i = 0; i < n; ++i) target += caplet(i, flat[k]);
        out.cap_prices.push_back(target);
        const auto gap = [&](double v) {
            double sum = known;
            for (std::size_t i = done; i < n; ++i) sum += caplet(i, v);
            return sum - target;
        };
        if (gap(lower) > 0) throw Error("E_ARBITRAGE", "a cap segment has no positive caplet vol");
        if (gap(upper) < 0) throw Error("E_DOMAIN", "a cap segment needs a caplet vol above the search interval");
        const double v = bisect_up(gap, lower, upper);
        for (std::size_t i = done; i < n; ++i) {
            out.caplet_vols.push_back(v);
            known += caplet(i, v);
        }
        done = n;
    }
    return out;
}

BondFutOption bondfut_option_price(double phi, double futures, double strike, double t, double discount, double vol,
                                   double contract_size) {
    check_bondfut(futures, strike, t, discount);
    if (!(vol >= 0)) throw Error("E_DOMAIN", "vol is negative", "vol");
    const double p = black_price(futures, strike, vol, t, discount, phi);
    return {p, p * contract_size / 100.0};
}

BondFutVol bondfut_implied_vol(double phi, double futures, double strike, double t, double discount, double premium,
                               double y, double dm) {
    check_bondfut(futures, strike, t, discount);
    const double intrinsic = discount * std::max(phi * (futures - strike), 0.0);
    const double bound = discount * (phi > 0 ? futures : strike);
    if (!(premium > intrinsic) || !(premium < bound))
        throw Error("E_DOMAIN", "premium is outside the no-arbitrage bounds", "premium");
    if (!(y > 0) || !(dm > 0)) throw Error("E_DOMAIN", "ctd_yield and ctd_modified_duration must be positive");
    const auto gap = [&](double v) { return black_price(futures, strike, v, t, discount, phi) - premium; };
    double hi = 1.0;
    for (int g = 0; gap(hi) < 0 && g < 200; ++g) hi *= 2;
    const double v = bisect_up(gap, 0.0, hi);
    return {v, v / (dm * y)};
}

CapPrice yoy_cap_price(RateVolModel model, double phi, double strike, double notional, const std::vector<YoyPeriod>& periods) {
    if (periods.empty()) throw Error("E_INPUT", "periods is empty", "periods");
    if (model == RateVolModel::Black76) {
        if (!(strike > 0)) throw Error("E_DOMAIN", "BLACK_76 needs a positive strike", "strike");
        for (const YoyPeriod& p : periods)
            if (!(p.yoy_forward > 0)) throw Error("E_DOMAIN", "BLACK_76 needs positive forwards", "periods");
    }
    for (const YoyPeriod& p : periods)
        if (!(p.expiry_years > 0)) throw Error("E_DOMAIN", "an expiry_years is not above 0", "periods");
    for (const YoyPeriod& p : periods)
        if (!(p.vol >= 0)) throw Error("E_DOMAIN", "a vol is negative", "periods");
    CapPrice out{{}, 0.0};
    for (const YoyPeriod& p : periods) {
        const double v =
            notional * p.accrual * option(model, p.yoy_forward, strike, p.vol, p.expiry_years, phi) * p.discount_factor;
        out.caplets.push_back(v);
        out.price += v;
    }
    return out;
}

ZcCap zc_cap_price(RateVolModel model, double phi, double fi, double years, double strike, double discount, double vol,
                   double notional) {
    if (model == RateVolModel::Black76 && !(fi > 0))
        throw Error("E_DOMAIN", "BLACK_76 needs a positive forward", "forward_index_ratio");
    if (!(years > 0)) throw Error("E_DOMAIN", "years is not above 0", "years");
    if (!(vol >= 0)) throw Error("E_DOMAIN", "vol is negative", "vol");
    const double ratio = std::pow(1.0 + strike, years);
    if (model == RateVolModel::Black76 && !(ratio > 0)) throw Error("E_DOMAIN", "the strike ratio is not positive", "strike");
    return {notional * discount * option(model, fi, ratio, vol, years, phi), ratio};
}

}  // namespace quantforge
