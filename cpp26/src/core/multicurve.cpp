#include "quantforge/core/multicurve.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>

#include "quantforge/core/error.hpp"
#include "quantforge/core/linalg.hpp"

namespace quantforge {
namespace {

[[noreturn]] void input(const char* message, const char* field = nullptr) {
    if (field) throw Error("E_INPUT", message, field);
    throw Error("E_INPUT", message);
}

double days(Date a, Date b) { return double(days_between(a, b)); }

}  // namespace

// ---- dated compounding ----

namespace {
// Ruling R1-6: no SOFR is published on any Good Friday, even in a USGS early-close year.
bool fixing_day(const RateConvention& c, Date x) {
    if (!is_business_day(c.calendar, x)) return false;
    return c.id != "SOFR" || x != Date(easter_sunday(year_of(x)) - std::chrono::days(2));
}
Date fixing_days_back(const RateConvention& c, Date x, long long k) {
    while (k > 0) {
        x = Date(x - std::chrono::days(1));
        if (fixing_day(c, x)) --k;
    }
    return x;
}
}  // namespace

DatedCompound compound_dated(const RateConvention& c, Date start, Date end, ShiftMethod method, long long k,
                             const std::vector<Fixing>& fixings) {
    if (c.months != 0) input("the convention is not overnight", "convention");
    if (end <= start) throw Error("E_DATE_ORDER", "end must be after start", "end");
    std::vector<Date> d;
    for (Date x = start; x <= end; x = Date(x + std::chrono::days(1)))
        if (fixing_day(c, x)) d.push_back(x);
    const long long n = d.empty() ? 0 : (long long)d.size() - 1;
    if (k < 0) input("shift_days is negative", "shift_days");
    if (method == ShiftMethod::None && k != 0) input("NONE takes shift_days 0", "shift_days");
    if (method == ShiftMethod::Lockout && (k < 1 || k > n - 1)) input("LOCKOUT needs 1 <= shift_days <= n-1", "shift_days");
    if (!fixing_day(c, start) || !fixing_day(c, end)) input("start and end must be business days", "start");

    std::map<Date, double> by_date;
    for (const Fixing& f : fixings)
        if (!by_date.emplace(f.date, f.rate).second) input("two fixings share a date", "fixings");
    const auto r = [&](Date x) {
        const auto it = by_date.find(x);
        if (it == by_date.end()) input("a needed fixing is missing", "fixings");
        return it->second;
    };
    const auto back = [&](Date x) { return k == 0 ? x : fixing_days_back(c, x, k); };

    const double b = c.denominator;
    double growth = 1.0, total = 0.0;
    for (long long i = 0; i < n; ++i) {
        double rate = 0.0, w = 0.0;
        switch (method) {
            case ShiftMethod::None: rate = r(d[i]); w = days(d[i], d[i + 1]); break;
            case ShiftMethod::Lookback: rate = r(back(d[i])); w = days(d[i], d[i + 1]); break;
            case ShiftMethod::ObservationShift: rate = r(back(d[i])); w = days(back(d[i]), back(d[i + 1])); break;
            case ShiftMethod::Lockout: rate = r(d[i < n - k ? i : n - k]); w = days(d[i], d[i + 1]); break;
        }
        growth *= 1.0 + rate * w / b;
        total += w;
    }
    const double rate = (growth - 1.0) * b / total;
    const double accrual = days(start, end) / b;
    return {rate, accrual, rate * accrual};
}

FallbackRate fallback_rate(std::string_view ibor, Date start, Date end, const std::vector<Fixing>& fixings) {
    struct Row {
        std::string_view ibor, index;
        double spread;
    };
    static constexpr Row rows[] = {
        {"USD-LIBOR-1M", "SOFR", 0.0011448},  {"USD-LIBOR-3M", "SOFR", 0.0026161},
        {"USD-LIBOR-6M", "SOFR", 0.0042826},  {"USD-LIBOR-12M", "SOFR", 0.0071513},
        {"GBP-LIBOR-1M", "SONIA", 0.0003260}, {"GBP-LIBOR-3M", "SONIA", 0.0011930},
        {"GBP-LIBOR-6M", "SONIA", 0.0027660}, {"GBP-LIBOR-12M", "SONIA", 0.0046440},
    };
    for (const Row& row : rows) {
        if (row.ibor != ibor) continue;
        const double cr =
            compound_dated(*rate_convention(row.index), start, end, ShiftMethod::ObservationShift, 2, fixings).compounded_rate;
        return {cr, row.spread, cr + row.spread};
    }
    throw Error("E_SCHEMA", "ibor is not listed", "ibor");
}

// ---- step curves ----

void StepCurve::check() const {
    Date previous = as_of;
    for (const Step& s : steps) {
        if (s.date <= previous) input("step dates must increase and follow as_of", "steps");
        previous = s.date;
    }
    check_jumps(as_of, jumps);
}

double StepCurve::discount(Date d) const {
    if (d < as_of) throw Error("E_OUT_OF_RANGE", "the date is before as_of");
    const double t = days(as_of, d) / 365.0;
    double integral = 0.0, from = 0.0, rate = base_rate;
    for (const Step& s : steps) {
        const double ts = days(as_of, s.date) / 365.0;
        if (ts >= t) break;
        integral += rate * (ts - from);
        from = ts;
        rate = s.rate;
    }
    integral += rate * (t - from);
    return std::exp(-integral) * jump_product(jumps, d);
}

double StepCurve::forward(Date d) const {
    double rate = base_rate;
    for (const Step& s : steps)
        if (s.date <= d) rate = s.rate;
    return rate;
}

StepFit fit_steps(const RateConvention& c, Date as_of, const std::vector<Date>& step_dates,
                  const std::vector<OisQuote>& quotes, const std::vector<Jump>& jumps) {
    if (c.months != 0) input("the convention is not overnight", "convention");
    const std::size_t m = step_dates.size();
    if (m == 0) input("no step dates", "step_dates");
    if (quotes.size() != m + 1) input("quotes must number step dates plus 1", "quotes");
    StepCurve curve{as_of, 0.0, {}, {}};
    for (const Date d : step_dates) curve.steps.push_back({d, 0.0});
    curve.check();
    std::vector<std::vector<Period>> swaps;
    for (std::size_t j = 0; j <= m; ++j) {
        swaps.push_back(ois_periods(c, as_of, quotes[j].tenor));
        const Date p = swaps.back().back().payment;
        const Date lo = j == 0 ? as_of : step_dates[j - 1];
        if (!(lo < p) || (j < m && p > step_dates[j])) input("quote payment dates break the pillar rule", "quotes");
    }
    check_jumps(as_of, jumps);
    curve.jumps = jumps;

    const auto par = [&](std::size_t j) {
        return ois_legs(c, swaps[j], [&](Date d) { return curve.discount(d); }).par();
    };
    const auto set = [&](std::size_t j, double x) {
        if (j == 0) curve.base_rate = x;
        else curve.steps[j - 1].rate = x;
    };
    for (std::size_t j = 0; j <= m; ++j) {
        const double target = quotes[j].rate;
        double x = target, best_x = x, best = HUGE_VAL;
        for (std::size_t i = j; i <= m; ++i) set(i, x);  // later rates do not reach quote j
        for (int it = 0; it < 100; ++it) {
            set(j, x);
            const double g = par(j) - target;
            if (!std::isfinite(g)) throw Error("E_NO_CONVERGENCE", "the step fit did not converge");
            if (std::fabs(g) < best) {
                best = std::fabs(g);
                best_x = x;
            }
            if (best <= 2e-16) break;
            constexpr double h = 1e-6;
            set(j, x + h);
            const double up = par(j);
            set(j, x - h);
            const double slope = (up - par(j)) / (2.0 * h);
            const double step = g / slope;
            if (!std::isfinite(step)) throw Error("E_NO_CONVERGENCE", "the step fit did not converge");
            x -= step;
            if (std::fabs(step) < 1e-18) break;
        }
        set(j, best_x);
        if (best >= 1e-13) throw Error("E_NO_CONVERGENCE", "the step fit did not converge");
    }
    StepFit out{curve.base_rate, {}, 0.0};
    for (const Step& s : curve.steps) out.step_rates.push_back(s.rate);
    for (std::size_t j = 0; j <= m; ++j) out.max_repricing_error = std::max(out.max_repricing_error, std::fabs(par(j) - quotes[j].rate));
    if (out.max_repricing_error >= 1e-13) throw Error("E_NO_CONVERGENCE", "the step fit did not converge");
    return out;
}

// ---- futures ----

Convexity futures_convexity(double price, double t, double big_t, double sigma, double a) {
    if (big_t <= t) input("end_years must be after start_years", "end_years");
    if (t < 0.0) throw Error("E_DOMAIN", "start_years is negative", "start_years");
    if (sigma < 0.0) throw Error("E_DOMAIN", "sigma is negative", "sigma");
    if (a < 0.0) throw Error("E_DOMAIN", "mean_reversion is negative", "mean_reversion");
    const double d = big_t - t;
    double bd = d, l = 2.0 * t, bt = t;
    if (a > 0.0) {
        bd = -std::expm1(-a * d) / a;
        l = -std::expm1(-2.0 * a * t) / a;
        bt = -std::expm1(-a * t) / a;
    }
    const double futures = (100.0 - price) / 100.0;
    const double z = sigma * sigma / 2.0 * (l * bd * bd + bd * bt * bt);
    const double cv = -std::expm1(-z) * (futures + 1.0 / d);
    return {futures, cv, futures - cv};
}

// ---- CSA, basis, joint ----

std::vector<double> csa_discount(const Curve& curve, double spread, const std::optional<CsaFx>& fx,
                                 const std::vector<Date>& dates) {
    std::map<Date, double> forwards;
    if (fx) {
        if (!(fx->spot > 0.0)) throw Error("E_DOMAIN", "spot is not positive", "fx");
        for (const FxForwardPoint& f : fx->forwards)
            if (!(f.forward > 0.0)) throw Error("E_DOMAIN", "a forward is not positive", "fx");
        for (const FxForwardPoint& f : fx->forwards)
            if (!forwards.emplace(f.date, f.forward).second) input("two forwards share a date", "fx");
        for (const Date d : dates)
            if (!forwards.contains(d)) input("a date has no forward", "fx");
    }
    std::vector<double> out;
    for (const Date d : dates) {
        double v = curve.discount(d) * std::exp(-spread * curve.time(d));
        if (fx) v *= fx->spot / forwards.at(d);
        out.push_back(v);
    }
    return out;
}

double ois_index_spread(const RateConvention& c, Tenor tenor, const Curve& discount, const Curve& a, const Curve& b) {
    if (c.months != 0) input("the convention is not overnight", "convention");
    if (a.as_of() != discount.as_of() || b.as_of() != discount.as_of()) input("the curves must share as_of", "discount");
    double fa = 0.0, fb = 0.0, annuity = 0.0;
    for (const Period& p : ois_periods(c, discount.as_of(), tenor)) {
        const double pay = discount.discount(p.payment);
        annuity += year_fraction(c.fixed_day_count, p.start, p.end) * pay;
        fa += (a.discount(p.start) / a.discount(p.end) - 1.0) * pay;
        fb += (b.discount(p.start) / b.discount(p.end) - 1.0) * pay;
    }
    return (fa - fb) / annuity;
}

JointCurves joint_bootstrap(const RateConvention& c, const RateConvention& index, Date as_of,
                            const std::vector<OisQuote>& ois_quotes, const std::vector<ProjectionQuote>& term_quotes,
                            CurveInterpolation interpolation, SolveMethod method) {
    if (ois_quotes.empty()) input("no OIS quotes", "ois_quotes");
    if (term_quotes.empty()) input("no term quotes", "term_quotes");
    // Block triangular: the OIS block does not see the projection curve, so the global Newton solve on
    // the whole system reduces to the discount block's solve followed by the projection block's.
    SolvedCurve d = ois_bootstrap(c, as_of, ois_quotes, interpolation, method);
    double error = 0.0;
    Curve p = projection_bootstrap(d.curve, index, as_of, term_quotes, interpolation, &error);
    return {std::move(d.curve), std::move(p), std::max(error, d.max_repricing_error)};
}

// ---- fits ----

SmoothFit smooth_fit(const std::vector<double>& knots, const std::vector<double>& m, const std::vector<double>& y,
                     double lambda, const std::optional<std::vector<double>>& weights) {
    if (m.empty() || m.size() != y.size() || (weights && weights->size() != m.size()))
        input("maturities, zero_rates and weights must match and not be empty", "maturities");
    if (knots.empty()) input("no knots", "knots");
    for (std::size_t k = 0; k < knots.size(); ++k)
        if (!(knots[k] > (k == 0 ? 0.0 : knots[k - 1]))) input("knots must be positive and increase", "knots");
    if (!(lambda >= 0.0)) throw Error("E_DOMAIN", "lambda is negative", "lambda");
    const std::vector<double> w = weights ? *weights : std::vector<double>(m.size(), 1.0);
    for (const double x : w)
        if (!(x >= 0.0)) throw Error("E_DOMAIN", "a weight is negative", "weights");
    for (const double x : m)
        if (!(x > 0.0)) throw Error("E_DOMAIN", "a maturity is not positive", "maturities");
    for (const double x : m)
        if (x > knots.back()) input("a maturity is past the last knot", "maturities");

    const std::size_t n = knots.size(), rows = m.size();
    Matrix b(rows, std::vector<double>(n, 0.0));
    for (std::size_t j = 0; j < rows; ++j)
        for (std::size_t k = 0; k < n; ++k) {
            const double lo = k == 0 ? 0.0 : knots[k - 1];
            const double len = std::min(knots[k], m[j]) - lo;
            if (len > 0.0) b[j][k] = len / m[j];
        }
    Matrix a(n, std::vector<double>(n, 0.0));
    std::vector<double> rhs(n, 0.0);
    for (std::size_t j = 0; j < rows; ++j)
        for (std::size_t k = 0; k < n; ++k) {
            rhs[k] += b[j][k] * w[j] * y[j];
            for (std::size_t l = 0; l < n; ++l) a[k][l] += b[j][k] * w[j] * b[j][l];
        }
    for (std::size_t k = 0; k + 1 < n; ++k) {
        a[k][k] += lambda;
        a[k + 1][k + 1] += lambda;
        a[k][k + 1] -= lambda;
        a[k + 1][k] -= lambda;
    }
    SmoothFit out{solve_linear(a, rhs), {}, 0.0};
    for (std::size_t j = 0; j < rows; ++j) {
        double z = 0.0;
        for (std::size_t k = 0; k < n; ++k) z += b[j][k] * out.forwards[k];
        out.fitted.push_back(z);
        out.objective += w[j] * (z - y[j]) * (z - y[j]);
    }
    for (std::size_t k = 0; k + 1 < n; ++k)
        out.objective += lambda * (out.forwards[k + 1] - out.forwards[k]) * (out.forwards[k + 1] - out.forwards[k]);
    return out;
}

RobustFit robust_fit(const std::vector<double>& m, const std::vector<double>& y, double tau, double delta) {
    if (m.size() != y.size() || m.size() < 3) input("maturities and zero_rates must match, with at least 3", "maturities");
    if (!(tau > 0.0)) throw Error("E_DOMAIN", "tau is not positive", "tau");
    if (!(delta > 0.0)) throw Error("E_DOMAIN", "delta is not positive", "delta");
    for (const double x : m)
        if (!(x > 0.0)) throw Error("E_DOMAIN", "a maturity is not positive", "maturities");
    const std::size_t n = m.size();
    Matrix x(n, std::vector<double>(3));
    for (std::size_t j = 0; j < n; ++j) {
        const double u = m[j] / tau, e = -std::expm1(-u) / u;
        x[j] = {1.0, e, e - std::exp(-u)};
    }
    const auto residuals = [&](const std::vector<double>& b) {
        std::vector<double> r(n);
        for (std::size_t j = 0; j < n; ++j) r[j] = x[j][0] * b[0] + x[j][1] * b[1] + x[j][2] * b[2] - y[j];
        return r;
    };
    // Weighted normal equations: sum w_j x_j x_j^T b = sum w_j x_j y_j - sum c_j x_j.
    const auto solve = [&](const std::vector<double>& w, const std::vector<double>& c) {
        Matrix a(3, std::vector<double>(3, 0.0));
        std::vector<double> rhs(3, 0.0);
        for (std::size_t j = 0; j < n; ++j)
            for (int k = 0; k < 3; ++k) {
                rhs[k] += x[j][k] * (w[j] * y[j] - c[j]);
                for (int l = 0; l < 3; ++l) a[k][l] += w[j] * x[j][k] * x[j][l];
            }
        return solve_linear(a, rhs);
    };
    // Exact minimiser for a fixed inlier/outlier split; a split that reproduces itself is the minimum.
    const auto split_of = [&](const std::vector<double>& r) {
        std::vector<int> s(n);
        for (std::size_t j = 0; j < n; ++j) s[j] = std::fabs(r[j]) <= delta ? 0 : (r[j] > 0.0 ? 1 : -1);
        return s;
    };
    const auto solve_split = [&](const std::vector<int>& s) {
        std::vector<double> w(n), c(n);
        for (std::size_t j = 0; j < n; ++j) {
            w[j] = s[j] == 0 ? 1.0 : 0.0;
            c[j] = s[j] == 0 ? 0.0 : delta * s[j];
        }
        return solve(w, c);
    };
    std::vector<double> b = solve(std::vector<double>(n, 1.0), std::vector<double>(n, 0.0));
    std::set<std::vector<int>> seen;
    bool done = false;
    for (int it = 0; it < 200 && !done; ++it) {
        const auto s = split_of(residuals(b));
        if (!seen.insert(s).second) break;
        try {
            const auto next = solve_split(s);
            if (split_of(residuals(next)) == s) {
                b = next;
                done = true;
            } else {
                b = next;
            }
        } catch (const Error&) {
            break;
        }
    }
    if (!done) {  // IRLS, then the exact split solve
        for (int it = 0; it < 20000; ++it) {
            const auto r = residuals(b);
            std::vector<double> w(n);
            for (std::size_t j = 0; j < n; ++j) w[j] = std::fabs(r[j]) <= delta ? 1.0 : delta / std::fabs(r[j]);
            const auto next = solve(w, std::vector<double>(n, 0.0));
            double change = 0.0;
            for (int k = 0; k < 3; ++k) change = std::max(change, std::fabs(next[k] - b[k]));
            b = next;
            if (change < 1e-17) break;
        }
        try {
            const auto s = split_of(residuals(b));
            const auto next = solve_split(s);
            if (split_of(residuals(next)) == s) b = next;
        } catch (const Error&) {
        }
    }
    RobustFit out{b, residuals(b), {}, 0.0};
    for (std::size_t j = 0; j < n; ++j) {
        const double a = std::fabs(out.residuals[j]);
        if (a > delta) out.outliers.push_back(j);
        out.objective += a <= delta ? a * a / 2.0 : delta * a - delta * delta / 2.0;
    }
    return out;
}

}  // namespace quantforge

// ---- D3: cross-currency ----

namespace quantforge {
namespace {

bool joint_business(Date d) { return is_business_day(Calendar::Usgs, d) && is_business_day(Calendar::Euta, d); }

Date joint_modified_following(Date d) {
    Date x = d;
    while (!joint_business(x)) x = Date(x + std::chrono::days(1));
    if (month_of(x) != month_of(d)) {
        x = d;
        while (!joint_business(x)) x = Date(x - std::chrono::days(1));
    }
    return x;
}

}  // namespace

std::vector<Date> xccy_schedule(Date start, long long months) {
    if (!joint_business(start)) throw Error("E_INPUT", "start must be a business day on both calendars", "start");
    if (months <= 0 || months % 3 != 0 || months > 1200) throw Error("E_INPUT", "months must be a positive multiple of 3", "months");
    std::vector<Date> out{start};
    for (long long k = 1; k <= months / 3; ++k) out.push_back(joint_modified_following(add_months(start, int(3 * k))));
    return out;
}

double xccy_leg(const std::vector<Date>& dates, double notional, const Curve& projection, const Curve& discount, double spread) {
    double sum = 0.0;
    for (std::size_t i = 1; i < dates.size(); ++i) {
        const double alpha = double(days_between(dates[i - 1], dates[i])) / 360.0;
        sum += ((projection.discount(dates[i - 1]) / projection.discount(dates[i]) - 1.0) + spread * alpha) * discount.discount(dates[i]);
    }
    return notional * (sum + discount.discount(dates.back()) - discount.discount(dates.front()));
}

SolvedCurve xccy_bootstrap(const Curve& foreign_projection, Date start, const std::vector<XccyQuote>& quotes,
                           CurveInterpolation interpolation) {
    if (quotes.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    std::vector<std::vector<Date>> swaps;
    std::vector<Date> dates;
    for (std::size_t j = 0; j < quotes.size(); ++j) {
        if (j > 0 && quotes[j].months <= quotes[j - 1].months) throw Error("E_INPUT", "months must strictly increase", "quotes");
        swaps.push_back(xccy_schedule(start, quotes[j].months));
        dates.push_back(swaps.back().back());
    }
    if (start < foreign_projection.as_of()) throw Error("E_OUT_OF_RANGE", "start is before as_of", "start");
    return solve_curve(foreign_projection.as_of(), interpolation, dates, std::vector<double>(quotes.size(), 0.0),
                       [&](std::size_t j, const Curve& d) { return xccy_leg(swaps[j], 1.0, foreign_projection, d, quotes[j].spread); },
                       SolveMethod::Sequential);
}

NdfPrice ndf_price(const Curve& usd, const Curve& offshore, double spot, Date fixing_date, Date payment_date, double strike,
                   double usd_notional, double sign, std::optional<double> fixing) {
    if (payment_date < fixing_date) throw Error("E_DATE_ORDER", "payment_date is before fixing_date", "trade");
    if (fixing_date <= usd.as_of() && !fixing) throw Error("E_INPUT", "a past fixing must be given", "fixing");
    if (!(spot > 0.0) || (fixing && !(*fixing > 0.0)) || !(strike > 0.0)) throw Error("E_DOMAIN", "spot, fixing and strike must be positive");
    const double du = usd.discount(payment_date);
    const double f = fixing ? *fixing : spot * du / offshore.discount(payment_date);
    return {sign * usd_notional * (1.0 - strike / f) * du, f};
}

}  // namespace quantforge
