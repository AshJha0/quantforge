#include "quantforge/core/risk.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"

namespace quantforge {

namespace {

constexpr double bp = 1e-4;

// Applies the scheme to a value that depends on a signed bump in bp.
double bumped(BumpScheme scheme, double bump_bp, double v0, const std::function<double(double)>& value_at) {
    if (scheme == BumpScheme::Central) return (value_at(bump_bp) - value_at(-bump_bp)) / (2.0 * bump_bp);
    return (value_at(bump_bp) - v0) / bump_bp;
}

Curve build(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes, CurveInterpolation interpolation) {
    return ois_bootstrap(c, as_of, quotes, interpolation, SolveMethod::Sequential).curve;
}

// Quotes with quote j (or every quote, j == npos) moved by h bp.
std::vector<OisQuote> moved(std::vector<OisQuote> q, std::size_t j, double h) {
    for (std::size_t i = 0; i < q.size(); ++i)
        if (j == std::size_t(-1) || i == j) q[i].rate += h * bp;
    return q;
}

double zero_rate(const Curve& curve, Date d) { return -std::log(curve.discount(d)) / curve.time(d); }

}  // namespace

void check_bump(double bump_bp) {
    if (!(bump_bp > 0.0 && bump_bp <= 100.0)) throw Error("E_DOMAIN", "bump_bp must be in (0, 100]", "bump_bp");
}

ParRisk par_risk(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                 CurveInterpolation interpolation, const CurvePricer& price, double bump_bp, BumpScheme scheme) {
    const double v0 = price(build(c, as_of, quotes, interpolation));
    const auto risk_of = [&](std::size_t j) {
        return bumped(scheme, bump_bp, v0, [&](double h) { return price(build(c, as_of, moved(quotes, j, h), interpolation)); });
    };
    ParRisk out{v0, risk_of(std::size_t(-1)), {}};
    for (std::size_t j = 0; j < quotes.size(); ++j) out.buckets.push_back(risk_of(j));
    return out;
}

PnlExplain pnl_explain(const RateConvention& c, Date as_of, const std::vector<OisQuote>& start,
                       const std::vector<OisQuote>& end, CurveInterpolation interpolation, const CurvePricer& price,
                       double bump_bp, double notional) {
    bool same = start.size() == end.size();
    for (std::size_t j = 0; same && j < start.size(); ++j)
        same = start[j].tenor.count == end[j].tenor.count && start[j].tenor.unit == end[j].tenor.unit;
    if (!same) throw Error("E_INPUT", "quotes_start and quotes_end must have the same tenors", "quotes_end");
    const ParRisk par = par_risk(c, as_of, start, interpolation, price, bump_bp, BumpScheme::Central);
    PnlExplain out{par.value, price(build(c, as_of, end, interpolation)), 0, 0, 0, 0, 0, par.buckets, false};
    out.full_pnl = out.value_end - out.value_start;
    for (std::size_t j = 0; j < start.size(); ++j) {
        const double move = (end[j].rate - start[j].rate) / bp;
        out.risk_pnl += par.buckets[j] * move;
        out.gross_risk_pnl += std::fabs(par.buckets[j]) * std::fabs(move);
    }
    out.unexplained = out.full_pnl - out.risk_pnl;
    // Ruling R2-A3: scales with the move, plus a numerical floor equal to the golden tolerance.
    out.threshold = 0.05 * std::max(std::fabs(out.full_pnl), out.gross_risk_pnl) + 1e-8 * notional;
    out.explained = std::fabs(out.unexplained) <= out.threshold;
    return out;
}

void check_key_dates(const Curve& curve, const std::vector<Date>& key_dates) {
    if (key_dates.empty()) throw Error("E_INPUT", "TRIANGULAR needs at least one key date", "key_dates");
    Date previous = curve.as_of();
    for (const Date d : key_dates) {
        if (d <= previous) throw Error("E_INPUT", "key dates must increase and follow as_of", "key_dates");
        previous = d;
    }
}

double triangular_weight(const std::vector<double>& k, std::size_t i, double t) {
    const std::size_t n = k.size();
    if (t <= k[0]) return i == 0 ? 1.0 : 0.0;
    if (t >= k[n - 1]) return i == n - 1 ? 1.0 : 0.0;
    if (i > 0 && t > k[i - 1] && t <= k[i]) return (t - k[i - 1]) / (k[i] - k[i - 1]);
    if (i + 1 < n && t >= k[i] && t < k[i + 1]) return (k[i + 1] - t) / (k[i + 1] - k[i]);
    return 0.0;
}

KeyRateRisk key_rate_risk(const Curve& curve, KeyRateMode mode, const std::vector<Date>& key_dates,
                          const CurvePricer& price, double bump_bp, BumpScheme scheme) {
    const double v0 = price(curve);
    KeyRateRisk out{v0, 0.0, {}};
    out.zero_dv01 = bumped(scheme, bump_bp, v0, [&](double h) {
        return price(curve.with_zero_shift([h](double) { return h * bp; }));
    });
    if (mode == KeyRateMode::Triangular) {
        std::vector<double> k;
        for (const Date d : key_dates) k.push_back(curve.time(d));
        for (std::size_t i = 0; i < k.size(); ++i)
            out.buckets.push_back(bumped(scheme, bump_bp, v0, [&](double h) {
                return price(curve.with_zero_shift([&k, i, h](double t) { return h * bp * triangular_weight(k, i, t); }));
            }));
    } else {
        const auto pillars = curve.pillars();
        for (std::size_t i = 0; i < pillars.size(); ++i) {
            const double t = curve.time(pillars[i].date);
            out.buckets.push_back(bumped(scheme, bump_bp, v0, [&](double h) {
                Curve c = curve;  // the jump-free log factor moves by the same amount as ln D
                c.set_log_df(i, curve.log_df(i) - h * bp * t);
                return price(c);
            }));
        }
    }
    return out;
}

ZeroJacobian zero_jacobian(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                           CurveInterpolation interpolation, double bump_bp) {
    const Curve base = build(c, as_of, quotes, interpolation);
    ZeroJacobian out;
    for (const Pillar& p : base.pillars()) {
        out.pillar_dates.push_back(p.date);
        out.zero_rates.push_back(zero_rate(base, p.date));
    }
    const std::size_t n = out.pillar_dates.size();
    out.jacobian.assign(n, std::vector<double>(quotes.size(), 0.0));
    for (std::size_t j = 0; j < quotes.size(); ++j) {
        const Curve up = build(c, as_of, moved(quotes, j, bump_bp), interpolation);
        const Curve down = build(c, as_of, moved(quotes, j, -bump_bp), interpolation);
        // Pillar i depends only on quotes up to its own, so entries above the diagonal stay exactly 0.
        for (std::size_t i = j; i < n; ++i)
            out.jacobian[i][j] = (zero_rate(up, out.pillar_dates[i]) - zero_rate(down, out.pillar_dates[i])) / (2.0 * bump_bp * bp);
    }
    return out;
}

}  // namespace quantforge
