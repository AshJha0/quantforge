#include "quantforge/core/fx_smile.hpp"

#include <cmath>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

void positive(double x, const char* key) {
    if (!(x > 0)) throw Error("E_DOMAIN", std::string(key) + " is not above 0", key);
}

void check_market(const GkMarket& m) {
    positive(m.spot, "spot");
    positive(m.expiry_years, "expiry_years");
}

double phi_of(OptionType t) { return t == OptionType::Call ? 1.0 : -1.0; }

// Bisection on a function that changes sign over [lo, hi], to the last representable step.
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

}  // namespace

double GkMarket::forward() const { return spot * std::exp((domestic_rate - foreign_rate) * expiry_years); }

GkPrice fx_option_price(const GkMarket& m, double k, double v, OptionType type, double notional) {
    require_finite(m.spot, "spot");
    require_finite(m.expiry_years, "expiry_years");
    require_finite(m.domestic_rate, "domestic_rate");
    require_finite(m.foreign_rate, "foreign_rate");
    require_finite(k, "strike");
    require_finite(v, "vol");
    require_finite(notional, "notional");
    positive(m.spot, "spot");
    positive(k, "strike");
    positive(m.expiry_years, "expiry_years");
    positive(v, "vol");
    positive(notional, "notional");
    const double t = m.expiry_years, f = m.forward(), sd = v * std::sqrt(t);
    const double dd = std::exp(-m.domestic_rate * t), df = std::exp(-m.foreign_rate * t), phi = phi_of(type);
    const double d1 = std::log(f / k) / sd + sd / 2, d2 = d1 - sd;
    const double p = phi * dd * (f * normal_cdf(phi * d1) - k * normal_cdf(phi * d2));
    return {notional * p,
            p / m.spot,
            f,
            notional * phi * df * normal_cdf(phi * d1),
            notional * df * normal_pdf(d1) / (m.spot * sd),
            notional * m.spot * df * normal_pdf(d1) * std::sqrt(t)};
}

double fx_delta(const GkMarket& m, double k, double v, OptionType type, FxDeltaType dt) {
    const double t = m.expiry_years, f = m.forward(), sd = v * std::sqrt(t), phi = phi_of(type);
    const double df = std::exp(-m.foreign_rate * t);
    const double d1 = std::log(f / k) / sd + sd / 2, d2 = d1 - sd;
    switch (dt) {
        case FxDeltaType::Spot: return phi * df * normal_cdf(phi * d1);
        case FxDeltaType::Forward: return phi * normal_cdf(phi * d1);
        case FxDeltaType::SpotPa: return phi * df * (k / f) * normal_cdf(phi * d2);
        case FxDeltaType::ForwardPa: return phi * (k / f) * normal_cdf(phi * d2);
    }
    return 0.0;
}

FxDeltas fx_deltas_from_strike(const GkMarket& m, double k, double v, OptionType type) {
    require_finite(m.spot, "spot");
    require_finite(m.expiry_years, "expiry_years");
    require_finite(m.domestic_rate, "domestic_rate");
    require_finite(m.foreign_rate, "foreign_rate");
    require_finite(k, "strike");
    require_finite(v, "vol");
    positive(m.spot, "spot");
    positive(k, "strike");
    positive(m.expiry_years, "expiry_years");
    positive(v, "vol");
    using enum FxDeltaType;
    return {fx_delta(m, k, v, type, Spot), fx_delta(m, k, v, type, Forward), fx_delta(m, k, v, type, SpotPa),
            fx_delta(m, k, v, type, ForwardPa)};
}

double fx_delta_to_strike(const GkMarket& m, double v, OptionType type, double delta, FxDeltaType dt) {
    require_finite(m.spot, "spot");
    require_finite(m.expiry_years, "expiry_years");
    require_finite(m.domestic_rate, "domestic_rate");
    require_finite(m.foreign_rate, "foreign_rate");
    require_finite(v, "vol");
    require_finite(delta, "delta");
    check_market(m);
    positive(v, "vol");
    const bool call = type == OptionType::Call;
    if (call ? !(delta > 0) : !(delta < 0)) throw Error("E_DOMAIN", "delta has the wrong sign", "delta");
    const double t = m.expiry_years, f = m.forward(), sd = v * std::sqrt(t), phi = phi_of(type);
    const double df = std::exp(-m.foreign_rate * t);
    const bool pa = dt == FxDeltaType::SpotPa || dt == FxDeltaType::ForwardPa;
    const double scale = dt == FxDeltaType::Spot || dt == FxDeltaType::SpotPa ? df : 1.0;
    if (!pa) {
        if (!(std::fabs(delta) < scale)) throw Error("E_DOMAIN", "delta is outside the reachable range", "delta");
        const double d1 = phi * normal_inverse(phi * delta / scale);
        return f * std::exp(-d1 * sd + sd * sd / 2);
    }
    // PA: solve in x = ln K.
    const auto g = [&](double x) { return fx_delta(m, std::exp(x), v, type, dt) - delta; };
    const double lf = std::log(f), wide = 40 * sd + 2;
    if (!call) return std::exp(bisect(g, lf - wide, lf + wide + std::log(1 + std::fabs(delta) / scale)));
    // PA call: maximum at K*, where sd N(d2) = n(d2); the root is on the branch above K* (ruling E-A10).
    const double d2s = bisect([&](double d2) { return sd * normal_cdf(d2) - normal_pdf(d2); }, -40.0, 40.0);
    const double xs = lf - sd * d2s - sd * sd / 2;
    if (!(delta < fx_delta(m, std::exp(xs), v, type, dt)))
        throw Error("E_DOMAIN", "delta is at or above the premium-adjusted maximum", "delta");
    return std::exp(bisect(g, xs, lf + wide));
}

double fx_atm_strike(const GkMarket& m, double v, FxAtmType atm, FxDeltaType dt) {
    require_finite(m.spot, "spot");
    require_finite(m.expiry_years, "expiry_years");
    require_finite(m.domestic_rate, "domestic_rate");
    require_finite(m.foreign_rate, "foreign_rate");
    require_finite(v, "vol");
    check_market(m);
    positive(v, "vol");
    const double f = m.forward(), half = v * v * m.expiry_years / 2;
    switch (atm) {
        case FxAtmType::Spot: return m.spot;
        case FxAtmType::Forward: return f;
        case FxAtmType::Dns:
            return dt == FxDeltaType::SpotPa || dt == FxDeltaType::ForwardPa ? f * std::exp(-half) : f * std::exp(half);
    }
    return 0.0;
}

FxSmile fx_smile_from_quotes(const GkMarket& m, double atm_vol, double rr, double bf, double delta, FxDeltaType dt,
                             FxAtmType atm) {
    require_finite(m.spot, "spot");
    require_finite(m.expiry_years, "expiry_years");
    require_finite(m.domestic_rate, "domestic_rate");
    require_finite(m.foreign_rate, "foreign_rate");
    require_finite(atm_vol, "atm_vol");
    require_finite(rr, "rr");
    require_finite(bf, "bf");
    require_finite(delta, "delta");
    check_market(m);
    positive(atm_vol, "atm_vol");
    if (!(delta > 0 && delta < 0.5)) throw Error("E_DOMAIN", "delta must be in (0, 0.5)", "delta");
    FxSmile s;
    s.call_vol = atm_vol + bf + rr / 2;
    s.put_vol = atm_vol + bf - rr / 2;
    positive(s.call_vol, "call_vol");
    positive(s.put_vol, "put_vol");
    s.atm_strike = fx_atm_strike(m, atm_vol, atm, dt);
    s.call_strike = fx_delta_to_strike(m, s.call_vol, OptionType::Call, delta, dt);
    s.put_strike = fx_delta_to_strike(m, s.put_vol, OptionType::Put, -delta, dt);
    return s;
}

}  // namespace quantforge
