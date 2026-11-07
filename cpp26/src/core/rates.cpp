#include "quantforge/core/rates.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/linalg.hpp"

using namespace std::chrono;

namespace quantforge {
namespace {

constexpr auto modified_following = BusinessDayConvention::ModifiedFollowing;

const RateConvention table[] = {
    {"SONIA", "GBP", Calendar::Gblo, 0, 0, 12, DayCount::Act365F, 0, 365.0},
    {"SOFR", "USD", Calendar::Usgs, 2, 2, 12, DayCount::Act360, 0, 360.0},
    {"ESTR", "EUR", Calendar::Euta, 2, 2, 12, DayCount::Act360, 0, 360.0},
    {"USD-TERM-3M", "USD", Calendar::Usgs, 2, 0, 12, DayCount::Thirty360Bond, 3, 360.0},
};

double sign_of(FixedSide s) { return s == FixedSide::Pay ? 1.0 : -1.0; }

Date spot_of(const RateConvention& c, Date as_of) {
    return add_business_days(c.calendar, as_of, c.spot_lag);
}

Date plus_months(const RateConvention& c, Date d, long long months) {
    return adjust(c.calendar, add_months(d, int(months)), modified_following);
}

constexpr double good_enough = 2e-15;  // about the rounding of a par rate
constexpr double required = 1e-13;

[[noreturn]] void solve_failed() { throw Error("E_NO_CONVERGENCE", "the curve solve did not converge"); }

double max_error(const std::vector<double>& targets, const ModelRate& model, const Curve& c) {
    double worst = 0.0;
    for (std::size_t j = 0; j < targets.size(); ++j) {
        const double e = std::fabs(model(j, c) - targets[j]);
        if (!std::isfinite(e)) solve_failed();
        worst = std::max(worst, e);
    }
    return worst;
}

void solve_one(Curve& c, std::size_t j, double target, const ModelRate& model) {
    constexpr double h = 1e-7;
    double x = c.log_df(j), best_x = x, best = HUGE_VAL;
    for (int i = 0; i < 100; ++i) {
        c.set_log_df(j, x);
        const double g = model(j, c) - target;
        if (!std::isfinite(g)) solve_failed();
        if (std::fabs(g) < best) {
            best = std::fabs(g);
            best_x = x;
        }
        if (best <= good_enough) break;
        c.set_log_df(j, x + h);
        const double up = model(j, c);
        c.set_log_df(j, x - h);
        const double down = model(j, c);
        const double step = g / ((up - down) / (2.0 * h));
        if (!std::isfinite(step)) solve_failed();
        x -= step;
        if (std::fabs(step) < 1e-16) break;
    }
    c.set_log_df(j, best_x);
    if (best >= required) solve_failed();
}

Curve solve_global(Curve c, const std::vector<double>& targets, const ModelRate& model) {
    constexpr double h = 1e-7;
    const std::size_t n = targets.size();
    Curve best_curve = c;
    double best = HUGE_VAL;
    for (int it = 0; it < 50; ++it) {
        std::vector<double> r(n);
        double worst = 0.0;
        for (std::size_t j = 0; j < n; ++j) {
            r[j] = model(j, c) - targets[j];
            if (!std::isfinite(r[j])) solve_failed();
            worst = std::max(worst, std::fabs(r[j]));
        }
        if (worst < best) {
            best = worst;
            best_curve = c;
        }
        if (best <= good_enough) break;
        Matrix jac(n, std::vector<double>(n));
        for (std::size_t k = 0; k < n; ++k) {
            const double x = c.log_df(k);
            std::vector<double> up(n);
            c.set_log_df(k, x + h);
            for (std::size_t j = 0; j < n; ++j) up[j] = model(j, c);
            c.set_log_df(k, x - h);
            for (std::size_t j = 0; j < n; ++j) jac[j][k] = (up[j] - model(j, c)) / (2.0 * h);
            c.set_log_df(k, x);
        }
        std::vector<double> step;
        try {
            step = solve_linear(jac, r);
        } catch (const Error&) {
            solve_failed();
        }
        for (std::size_t k = 0; k < n; ++k) c.set_log_df(k, c.log_df(k) - step[k]);
    }
    if (best >= required) solve_failed();
    return best_curve;
}

Valuation value_of(double pv, const std::string& currency, const char* model, std::optional<std::string> snapshot,
                   const std::string& conventions, Date as_of) {
    return {pv, currency, model, std::move(snapshot), conventions, as_of};
}

struct SwapLegs {
    std::vector<Period> fixed, floating;
};

SwapLegs swap_legs(const RateConvention& index, Date as_of, long long months) {
    const Date spot = spot_of(index, as_of), end = add_months(spot, int(months));
    return {generate_schedule(spot, end, index.fixed_months, index.calendar, false, 0),
            generate_schedule(spot, end, index.months, index.calendar, false, 0)};
}

Legs swap_values(const RateConvention& index, const SwapLegs& legs, const Curve& discount, const Curve& projection) {
    Legs v{0.0, 0.0};
    for (const Period& p : legs.fixed) v.annuity += year_fraction(index.fixed_day_count, p.start, p.end) * discount.discount(p.end);
    for (const Period& p : legs.floating)
        v.floating += (projection.discount(p.start) / projection.discount(p.end) - 1.0) * discount.discount(p.end);
    return v;
}

}  // namespace

const RateConvention* rate_convention(std::string_view id) {
    for (const RateConvention& c : table)
        if (c.id == id) return &c;
    return nullptr;
}

std::vector<Period> generate_schedule(Date start, Date end, long long frequency_months, Calendar c, bool end_of_month,
                                      long long payment_lag) {
    if (end <= start) throw Error("E_DATE_ORDER", "end must be after start", "end");
    if (payment_lag < 0) throw Error("E_INPUT", "payment_lag must not be negative", "payment_lag");
    std::vector<Date> unadjusted{end};
    for (long long k = 1;; ++k) {
        const Date d = add_months(end, -int(k * frequency_months));
        if (d <= start) break;
        unadjusted.push_back(d);
    }
    std::ranges::reverse(unadjusted);
    std::vector<Date> dates{start};
    for (const Date d : unadjusted) {
        const Date a = end_of_month ? last_business_day(c, year_of(d), month_of(d)) : adjust(c, d, modified_following);
        if (a > start) dates.push_back(a);
    }
    std::vector<Period> periods;
    for (std::size_t i = 1; i < dates.size(); ++i)
        periods.push_back({dates[i - 1], dates[i],
                           payment_lag == 0 ? dates[i] : add_business_days(c, dates[i], payment_lag)});
    return periods;
}

Curve::Curve(Date as_of, CurveInterpolation interpolation)
    : as_of_(as_of), interpolation_(interpolation), t_{0.0}, log_df_{0.0} {}

void check_jumps(Date as_of, const std::vector<Jump>& jumps) {
    Date previous = as_of;
    for (const Jump& j : jumps) {
        if (j.date <= previous) throw Error("E_INPUT", "jump dates must increase and follow as_of", "jumps");
        previous = j.date;
    }
    for (const Jump& j : jumps)
        if (!(j.factor > 0.0)) throw Error("E_DOMAIN", "a jump factor is not positive", "jumps");
}

double jump_product(const std::vector<Jump>& jumps, Date d) {
    double p = 1.0;
    for (const Jump& j : jumps)
        if (j.date < d) p *= j.factor;
    return p;
}

void Curve::set_jumps(const std::vector<Jump>& jumps) {
    check_jumps(as_of_, jumps);
    jumps_ = jumps;
}

Curve::Curve(Date as_of, CurveInterpolation interpolation, const std::vector<Pillar>& pillars,
             const std::vector<Jump>& jumps)
    : Curve(as_of, interpolation) {
    if (pillars.empty()) throw Error("E_INPUT", "no pillars", "pillars");
    Date previous = as_of;
    for (const Pillar& p : pillars) {
        if (p.date <= previous) throw Error("E_INPUT", "pillars must increase and follow as_of", "pillars");
        previous = p.date;
    }
    for (const Pillar& p : pillars) {
        if (p.discount_factor <= 0.0) throw Error("E_DOMAIN", "a discount factor is not positive", "pillars");
    }
    set_jumps(jumps);  // after the pillar checks (ruling D46)
    for (const Pillar& p : pillars) push(p.date, std::log(p.discount_factor / jump_product(jumps_, p.date)));
}

void Curve::push(Date d, double log_df) {
    dates_.push_back(d);
    t_.push_back(time(d));
    log_df_.push_back(log_df);
}

std::vector<Pillar> Curve::pillars() const {
    std::vector<Pillar> out;
    for (std::size_t i = 0; i < dates_.size(); ++i) out.push_back({dates_[i], std::exp(log_df_[i + 1]) * jump_product(jumps_, dates_[i])});
    return out;
}

double Curve::discount(Date d) const {
    const double t = time(d);
    if (t < 0.0) throw Error("E_OUT_OF_RANGE", "the date is before as_of");
    if (t == 0.0) return 1.0;
    const double s = plain_discount(t);
    return jumps_.empty() ? s : s * jump_product(jumps_, d);
}

double Curve::plain_discount(double t) const {
    const std::size_t n = t_.size() - 1;
    if (t >= t_[n]) {
        if (t == t_[n]) return std::exp(log_df_[n]);
        const double f = -(log_df_[n] - log_df_[n - 1]) / (t_[n] - t_[n - 1]);
        return std::exp(log_df_[n] - f * (t - t_[n]));
    }
    const auto i = std::size_t(std::upper_bound(t_.begin(), t_.end(), t) - t_.begin()) - 1;
    const double u = (t - t_[i]) / (t_[i + 1] - t_[i]);
    if (interpolation_ == CurveInterpolation::LogLinearDf) return std::exp((1.0 - u) * log_df_[i] + u * log_df_[i + 1]);
    const double z1 = -log_df_[i + 1] / t_[i + 1];
    const double z0 = i == 0 ? z1 : -log_df_[i] / t_[i];
    return std::exp(-((1.0 - u) * z0 + u * z1) * t);
}

double simple_forward(const Curve& c, Date start, Date end, DayCount day_count) {
    if (end <= start) throw Error("E_DATE_ORDER", "end must be after start", "end");
    return (c.discount(start) / c.discount(end) - 1.0) / year_fraction(day_count, start, end);
}

SolvedCurve solve_curve(Date as_of, CurveInterpolation interpolation, const std::vector<Date>& dates,
                        const std::vector<double>& targets, const ModelRate& model, SolveMethod method,
                        const std::vector<Jump>& jumps) {
    Curve c(as_of, interpolation);
    c.set_jumps(jumps);
    double previous_t = 0.0, previous_x = 0.0;
    for (std::size_t j = 0; j < dates.size(); ++j) {
        const double t = c.time(dates[j]);
        // Start from the quote as a flat forward beyond the last pillar.
        const double x = previous_x - targets[j] * (t - previous_t);
        c.push(dates[j], x);
        if (method == SolveMethod::Sequential) solve_one(c, j, targets[j], model);
        previous_t = t;
        previous_x = c.log_df(j);
    }
    if (method == SolveMethod::Global) c = solve_global(std::move(c), targets, model);
    const double error = max_error(targets, model, c);
    if (error >= required) solve_failed();
    return {std::move(c), error};
}

std::vector<Period> ois_periods(const RateConvention& c, Date as_of, Tenor tenor) {
    const Date spot = spot_of(c, as_of);
    const long long months = tenor.unit == 'Y' ? 12LL * tenor.count : tenor.count;
    const bool by_days = tenor.unit == 'D' || tenor.unit == 'W';
    if (by_days || months <= c.fixed_months) {
        const Date e = add_tenor(c.calendar, spot, tenor, modified_following, true);
        return {{spot, e, c.payment_lag == 0 ? e : add_business_days(c.calendar, e, c.payment_lag)}};
    }
    const bool eom = spot >= last_business_day(c.calendar, year_of(spot), month_of(spot));
    return generate_schedule(spot, add_months(spot, int(months)), c.fixed_months, c.calendar, eom, c.payment_lag);
}

Legs ois_legs(const RateConvention& c, const std::vector<Period>& periods, const std::function<double(Date)>& discount) {
    Legs v{0.0, 0.0};
    for (const Period& p : periods) {
        const double pay = discount(p.payment);
        v.annuity += year_fraction(c.fixed_day_count, p.start, p.end) * pay;
        v.floating += (discount(p.start) / discount(p.end) - 1.0) * pay;
    }
    return v;
}

Legs ois_legs(const RateConvention& c, const std::vector<Period>& periods, const Curve& curve) {
    return ois_legs(c, periods, [&](Date d) { return curve.discount(d); });
}

SolvedCurve ois_bootstrap(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                          CurveInterpolation interpolation, SolveMethod method, const std::vector<Jump>& jumps) {
    check_jumps(as_of, jumps);
    if (quotes.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    std::vector<std::vector<Period>> swaps;
    std::vector<Date> dates;
    std::vector<double> targets;
    for (const OisQuote& q : quotes) {
        swaps.push_back(ois_periods(c, as_of, q.tenor));
        dates.push_back(swaps.back().back().payment);
        targets.push_back(q.rate);
        if (dates.size() > 1 && dates.back() <= dates[dates.size() - 2])
            throw Error("E_INPUT", "pillars must strictly increase", "quotes");
    }
    return solve_curve(as_of, interpolation, dates, targets,
                       [&](std::size_t j, const Curve& curve) { return ois_legs(c, swaps[j], curve).par(); }, method, jumps);
}

double ois_compound(const std::vector<double>& rates, const std::vector<long long>& days, double denominator) {
    if (rates.empty() || rates.size() != days.size()) throw Error("E_INPUT", "rates and days must match");
    double product = 1.0, total = 0.0;
    for (std::size_t i = 0; i < rates.size(); ++i) {
        if (days[i] < 1) throw Error("E_INPUT", "days must be at least 1", "days");
        product *= 1.0 + rates[i] * double(days[i]) / denominator;
        total += double(days[i]);
    }
    return (product - 1.0) * denominator / total;
}

OisPrice ois_price(const OisTrade& trade, const Curve& curve, std::optional<std::string> snapshot_id) {
    const RateConvention& c = *trade.convention;
    const Legs legs = ois_legs(c, ois_periods(c, curve.as_of(), trade.tenor), curve);
    const double pv = sign_of(trade.side) * trade.notional * (legs.floating - trade.fixed_rate * legs.annuity);
    return {value_of(pv, c.currency, "OIS_DISCOUNTING", std::move(snapshot_id), c.id, curve.as_of()), legs.par(), legs.annuity};
}

Curve projection_bootstrap(const Curve& discount, const RateConvention& index, Date as_of,
                           const std::vector<ProjectionQuote>& quotes, CurveInterpolation interpolation,
                           double* max_repricing_error) {
    if (quotes.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    struct Instrument {
        Date start, end;
        double alpha;
        SwapLegs legs;
    };
    const Date spot = spot_of(index, as_of);
    std::vector<Instrument> instruments;
    std::vector<Date> dates;
    std::vector<double> targets;
    for (const ProjectionQuote& q : quotes) {
        Instrument it{};
        if (q.type == ProjectionQuoteType::Swap) {
            it.legs = swap_legs(index, as_of, q.months);
            it.end = it.legs.fixed.back().end;
        } else {
            it.start = q.type == ProjectionQuoteType::Deposit ? spot : plus_months(index, spot, q.months);
            it.end = plus_months(index, q.type == ProjectionQuoteType::Deposit ? spot : it.start,
                                 q.type == ProjectionQuoteType::Deposit ? q.months : index.months);
            it.alpha = year_fraction(DayCount::Act360, it.start, it.end);
        }
        if (!dates.empty() && it.end <= dates.back()) throw Error("E_INPUT", "quotes must be in pillar order", "quotes");
        dates.push_back(it.end);
        targets.push_back(q.rate);
        instruments.push_back(std::move(it));
    }
    SolvedCurve s = solve_curve(
        as_of, interpolation, dates, targets,
        [&](std::size_t j, const Curve& p) {
            const Instrument& it = instruments[j];
            if (!it.legs.fixed.empty()) return swap_values(index, it.legs, discount, p).par();
            return (p.discount(it.start) / p.discount(it.end) - 1.0) / it.alpha;
        },
        SolveMethod::Sequential);
    if (max_repricing_error) *max_repricing_error = s.max_repricing_error;
    return std::move(s.curve);
}

SwapPrice swap_price(const SwapTrade& trade, const Curve& discount, const Curve& projection,
                     std::optional<std::string> snapshot_id) {
    const RateConvention& c = *trade.index;
    const Legs v = swap_values(c, swap_legs(c, discount.as_of(), trade.tenor_months), discount, projection);
    const double pv = sign_of(trade.side) * trade.notional * (v.floating - trade.fixed_rate * v.annuity);
    return {value_of(pv, c.currency, "SWAP_DISCOUNTING", std::move(snapshot_id), c.id, discount.as_of()), v.par()};
}

FraPrice fra_price(const FraTrade& trade, const Curve& discount, const Curve& projection,
                   std::optional<std::string> snapshot_id) {
    const RateConvention& c = *trade.index;
    const Date e = plus_months(c, trade.start, c.months);
    const double alpha = year_fraction(DayCount::Act360, trade.start, e);
    const double f = (projection.discount(trade.start) / projection.discount(e) - 1.0) / alpha;
    const double pv = sign_of(trade.side) * trade.notional * alpha * (f - trade.fixed_rate) / (1.0 + alpha * f) *
                      discount.discount(trade.start);
    return {value_of(pv, c.currency, "FRA_DISCOUNTING", std::move(snapshot_id), c.id, discount.as_of()), f};
}

double basis_spread(const Curve& discount, const Curve& projection, const RateConvention& index, long long tenor_months) {
    double top = 0.0, bottom = 0.0;
    for (const Period& p : swap_legs(index, discount.as_of(), tenor_months).floating) {
        const double de = discount.discount(p.end);
        top += (projection.discount(p.start) / projection.discount(p.end) - discount.discount(p.start) / de) * de;
        bottom += year_fraction(DayCount::Act360, p.start, p.end) * de;
    }
    return top / bottom;
}

BumpedCurves bumped_curves(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                           CurveInterpolation interpolation) {
    constexpr double bp = 1e-4;
    const auto build = [&](const std::vector<OisQuote>& q) {
        return ois_bootstrap(c, as_of, q, interpolation, SolveMethod::Sequential).curve;
    };
    BumpedCurves out;
    std::vector<OisQuote> q = quotes;
    for (std::size_t j = 0; j < q.size(); ++j) {
        q[j].rate = quotes[j].rate + bp;
        out.up.push_back(build(q));
        q[j].rate = quotes[j].rate - bp;
        out.down.push_back(build(q));
        q[j].rate = quotes[j].rate;
    }
    for (std::size_t j = 0; j < q.size(); ++j) q[j].rate = quotes[j].rate + bp;
    out.all_up = build(q);
    for (std::size_t j = 0; j < q.size(); ++j) q[j].rate = quotes[j].rate - bp;
    out.all_down = build(q);
    return out;
}

RateRisk rate_risk(const OisTrade& trade, const BumpedCurves& curves) {
    const auto pv = [&](const Curve& c) { return ois_price(trade, c).valuation.pv; };
    RateRisk r{(pv(*curves.all_up) - pv(*curves.all_down)) / 2.0, {}};
    for (std::size_t j = 0; j < curves.up.size(); ++j) r.key_rate.push_back((pv(curves.up[j]) - pv(curves.down[j])) / 2.0);
    return r;
}

CashflowRisk cashflow_risk(const std::vector<Cashflow>& cashflows, double yield) {
    if (cashflows.empty()) throw Error("E_INPUT", "at least 1 cashflow is needed", "cashflows");
    for (const Cashflow& c : cashflows)
        if (c.t < 0.0) throw Error("E_DOMAIN", "t is negative", "cashflows");
    double pv = 0.0, first = 0.0, second = 0.0;
    for (const Cashflow& c : cashflows) {
        const double v = c.amount * std::exp(-yield * c.t);
        pv += v;
        first += c.t * v;
        second += c.t * c.t * v;
    }
    if (pv == 0.0) throw Error("E_DOMAIN", "pv is zero", "cashflows");
    return {pv, first / pv, second / pv};
}

}  // namespace quantforge
