#include "quantforge/core/black.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

double density(double x) { return std::exp(-x * x / 2) / std::sqrt(2 * std::numbers::pi); }

[[noreturn]] void domain(const char* why) { throw Error("E_DOMAIN", why); }

}  // namespace

double OptionInput::model_forward() const {
    return model == VolModel::BlackScholes ? spot * std::exp((rate - yield) * expiry_years) : forward;
}
double OptionInput::model_discount() const {
    return model == VolModel::BlackScholes ? std::exp(-rate * expiry_years) : discount_factor;
}

double black_price(double f, double k, double vol, double t, double d, double phi) {
    if (t == 0 || vol == 0) return d * std::max(phi * (f - k), 0.0);
    const double s = vol * std::sqrt(t);
    const double d1 = (std::log(f / k) + s * s / 2) / s, d2 = d1 - s;
    return d * phi * (f * normal_cdf(phi * d1) - k * normal_cdf(phi * d2));
}

double bachelier_price(double f, double k, double vol, double t, double d, double phi) {
    if (t == 0 || vol == 0) return d * std::max(phi * (f - k), 0.0);
    const double s = vol * std::sqrt(t), x = (f - k) / s;
    return d * (phi * (f - k) * normal_cdf(phi * x) + s * density(x));
}

void check_option(const OptionInput& in) {
    if (in.model != VolModel::BlackScholes && in.discount_factor <= 0) domain("discount_factor is not above 0");
    if (in.model == VolModel::BlackScholes && in.spot <= 0) domain("spot is not above 0");
    if (in.model == VolModel::Black76 && in.forward + in.shift <= 0) domain("forward + shift is not above 0");
    if (in.model != VolModel::Bachelier && in.strike + in.shift <= 0) domain("strike + shift is not above 0");
}

double option_price(const OptionInput& in, double vol) {
    const double f = in.model_forward(), d = in.model_discount(), t = in.expiry_years;
    if (in.model == VolModel::Bachelier) return bachelier_price(f, in.strike, vol, t, d, in.phi());
    return black_price(f + in.shift, in.strike + in.shift, vol, t, d, in.phi());
}

double checked_option_price(const OptionInput& in, double vol) {
    if (in.expiry_years < 0) domain("expiry_years below 0");
    if (vol < 0) domain("vol below 0");
    check_option(in);
    return option_price(in, vol);
}

double implied_vol(const OptionInput& in, double price) {
    if (in.expiry_years < 0) domain("expiry_years below 0");
    check_option(in);
    if (in.expiry_years == 0) domain("expiry_years is 0");
    const double t = in.expiry_years, root_t = std::sqrt(t), phi = in.phi(), d = in.model_discount();
    const bool normal = in.model == VolModel::Bachelier;
    const double f = in.model_forward() + in.shift, k = in.strike + in.shift;
    const double intrinsic = d * std::max(phi * (f - k), 0.0);
    if (price < intrinsic) domain("price is below intrinsic");
    if (!normal && price >= d * (phi > 0 ? f : k)) domain("price is at or above the upper bound");
    if (price == intrinsic) return 0.0;

    const auto gap = [&](double v) { return option_price(in, v) - price; };
    const auto vega = [&](double v) {
        if (normal) return d * root_t * density((f - k) / (v * root_t));
        const double s = v * root_t;
        return d * f * root_t * density((std::log(f / k) + s * s / 2) / s);
    };
    double lo = 0.0, hi = normal ? std::max(std::fabs(f - k), 1.0) / root_t : 1.0 / root_t;
    const double top = normal ? 1e300 : 1e8 / root_t;
    while (gap(hi) < 0) {
        lo = hi;
        hi *= 2;
        if (hi > top) throw Error("E_NO_CONVERGENCE", "no upper bracket");
    }
    double v = (lo + hi) / 2, best = v, best_gap = INFINITY;
    for (int i = 0; i < 300; ++i) {
        const double g = gap(v);
        if (std::fabs(g) < best_gap) {
            best_gap = std::fabs(g);
            best = v;
        }
        if (g == 0) break;
        (g > 0 ? hi : lo) = v;
        const double slope = vega(v);
        double next = slope > 0 ? v - g / slope : lo;
        if (!(next > lo && next < hi)) next = (lo + hi) / 2;
        if (std::fabs(next - v) <= 1e-16 * v) break;
        v = next;
    }
    if (best_gap > 1e-13 * std::max(1.0, price)) throw Error("E_NO_CONVERGENCE", "implied vol did not converge");
    return best;
}

Greeks option_greeks(const OptionInput& in, double vol) {
    if (in.expiry_years < 0) domain("expiry_years below 0");
    if (vol < 0) domain("vol below 0");
    check_option(in);
    if (vol <= 0 || in.expiry_years <= 0) domain("vol and expiry_years must be above 0");
    const double t = in.expiry_years, root_t = std::sqrt(t), phi = in.phi(), v = vol, d = in.model_discount();
    const double price = option_price(in, v);
    if (in.model == VolModel::Bachelier) {
        const double x = (in.forward - in.strike) / (v * root_t), n = density(x);
        return {price, d * phi * normal_cdf(phi * x), d * n / (v * root_t), d * root_t * n, -d * v * n / (2 * root_t),
                -t * price, -d * n * x / v, d * root_t * n * x * x / v};
    }
    const double f = in.model_forward() + in.shift, k = in.strike + in.shift;
    const double d1 = (std::log(f / k) + v * v * t / 2) / (v * root_t), d2 = d1 - v * root_t, n = density(d1);
    if (in.model == VolModel::Black76) {
        const double vega = d * f * n * root_t;
        return {price, d * phi * normal_cdf(phi * d1), d * n / (f * v * root_t), vega, -d * f * n * v / (2 * root_t),
                -t * price, -d * n * d2 / v, vega * d1 * d2 / v};
    }
    const double q = std::exp(-in.yield * t), s = in.spot, r = in.rate;
    const double vega = s * q * n * root_t;
    return {price,
            q * phi * normal_cdf(phi * d1),
            q * n / (s * v * root_t),
            vega,
            -s * q * n * v / (2 * root_t) - phi * r * in.strike * d * normal_cdf(phi * d2) + phi * in.yield * s * q * normal_cdf(phi * d1),
            phi * in.strike * t * d * normal_cdf(phi * d2),
            -q * n * d2 / v,
            vega * d1 * d2 / v};
}

BumpGreeks bump_greeks(const OptionInput& in, double vol) {
    if (in.expiry_years < 0) domain("expiry_years below 0");
    if (vol < 0) domain("vol below 0");
    check_option(in);
    if (vol <= 0 || in.expiry_years <= 0) domain("vol and expiry_years must be above 0");
    const bool spot = in.model == VolModel::BlackScholes;
    const double u = spot ? in.spot : in.forward;
    const double hu = in.model == VolModel::Bachelier ? 1e-4 * std::max(std::fabs(u), 1.0)
                      : in.model == VolModel::Black76 ? 1e-4 * (u + in.shift)
                                                      : 1e-4 * u;
    const double hv = 1e-3 * vol;
    const auto value = [&](double du, double dv) {
        OptionInput moved = in;
        (spot ? moved.spot : moved.forward) = u + du;
        return option_price(moved, vol + dv);
    };
    const double v0 = value(0, 0), up = value(hu, 0), down = value(-hu, 0), vup = value(0, hv), vdown = value(0, -hv);
    return {(up - down) / (2 * hu),
            (up - 2 * v0 + down) / (hu * hu),
            (vup - vdown) / (2 * hv),
            (vup - 2 * v0 + vdown) / (hv * hv),
            (value(hu, hv) - value(hu, -hv) - value(-hu, hv) + value(-hu, -hv)) / (4 * hu * hv)};
}

}  // namespace quantforge
