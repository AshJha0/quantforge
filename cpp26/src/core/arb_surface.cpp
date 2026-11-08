#include "quantforge/core/arb_surface.hpp"

#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

constexpr std::size_t max_slices = 100, max_points = 10000;

// w and its first two k-derivatives of one raw SVI slice.
struct W3 {
    double w, wk, wkk;
};
W3 svi_w3(const Svi& s, double k) {
    const double x = k - s.m, r = std::sqrt(x * x + s.sigma * s.sigma);
    return {s.w(k), s.b * (s.rho + x / r), s.b * s.sigma * s.sigma / (r * r * r)};
}

// w, w_k, w_kk and w_T between slices (ruling E-A4).
struct WSurface {
    double w, wk, wkk, wt;
};
WSurface surface_at(const std::vector<SviSlice>& sl, double t, double k) {
    const std::size_t n = sl.size();
    if (n == 1 || t < sl.front().expiry_years || t >= sl.back().expiry_years) {
        const SviSlice& s = t < sl.front().expiry_years ? sl.front() : sl.back();
        const W3 v = svi_w3(s.svi, k);
        const double f = t / s.expiry_years;
        return {v.w * f, v.wk * f, v.wkk * f, v.w / s.expiry_years};
    }
    std::size_t j = 0;
    while (!(sl[j].expiry_years <= t && t < sl[j + 1].expiry_years)) ++j;
    const double t0 = sl[j].expiry_years, t1 = sl[j + 1].expiry_years, lam = (t - t0) / (t1 - t0);
    const W3 a = svi_w3(sl[j].svi, k), b = svi_w3(sl[j + 1].svi, k);
    return {(1 - lam) * a.w + lam * b.w, (1 - lam) * a.wk + lam * b.wk, (1 - lam) * a.wkk + lam * b.wkk,
            (b.w - a.w) / (t1 - t0)};
}

void check_increasing(const std::vector<double>& x, const char* key, std::size_t at_least) {
    if (x.size() < at_least) throw Error("E_INPUT", std::string(key) + " has too few points", key);
    for (std::size_t i = 1; i < x.size(); ++i)
        if (!(x[i - 1] < x[i])) throw Error("E_INPUT", std::string(key) + " is not strictly increasing", key);
}

double black_forward(double f, double k, double v, double t, double d, OptionType type) {
    const double sd = v * std::sqrt(t), d1 = std::log(f / k) / sd + sd / 2, d2 = d1 - sd;
    return type == OptionType::Call ? d * (f * normal_cdf(d1) - k * normal_cdf(d2))
                                    : d * (k * normal_cdf(-d2) - f * normal_cdf(-d1));
}

}  // namespace

void check_slices(const std::vector<SviSlice>& sl) {
    if (sl.empty()) throw Error("E_INPUT", "slices is empty", "slices");
    for (std::size_t j = 1; j < sl.size(); ++j)
        if (!(sl[j - 1].expiry_years < sl[j].expiry_years))
            throw Error("E_INPUT", "expiry_years is not strictly increasing", "slices");
    for (const SviSlice& s : sl)
        if (s.expiry_years <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0", "slices");
    for (const SviSlice& s : sl) check_svi(s.svi);
    if (sl.size() > max_slices) throw Error("E_LIMIT", "slices is above its limit", "slices");
}

SviSurfaceCheck svi_surface_check(const std::vector<SviSlice>& sl, const std::vector<double>& k, bool reject) {
    check_slices(sl);
    check_increasing(k, "log_moneyness", 1);
    if (k.size() > max_points) throw Error("E_LIMIT", "log_moneyness is above its limit", "log_moneyness");
    SviSurfaceCheck c;
    for (std::size_t j = 0; j < sl.size(); ++j)
        for (std::size_t i = 0; i < k.size(); ++i)
            if (sl[j].svi.g(k[i]) < 0) c.butterfly.push_back({j, i});
    for (std::size_t j = 1; j < sl.size(); ++j)
        for (std::size_t i = 0; i < k.size(); ++i)
            if (sl[j].svi.w(k[i]) < sl[j - 1].svi.w(k[i])) c.calendar.push_back({j, i});
    // Wing asymptotes in binary64 exactly as written (ruling E-A2).
    const auto left = [](const Svi& p) { return std::pair{p.b * (1 - p.rho), p.a + p.b * (1 - p.rho) * p.m}; };
    const auto right = [](const Svi& p) { return std::pair{p.b * (1 + p.rho), p.a - p.b * (1 + p.rho) * p.m}; };
    for (std::size_t j = 0; j < sl.size(); ++j) {
        const Svi& p = sl[j].svi;
        if (left(p).first >= 2) c.wings.push_back({j, "LEFT", "LEE"});
        if (right(p).first >= 2) c.wings.push_back({j, "RIGHT", "LEE"});
        if (j == 0) continue;
        const Svi& q = sl[j - 1].svi;
        const auto crosses = [](std::pair<double, double> now, std::pair<double, double> before) {
            return now.first < before.first || (now.first == before.first && now.second < before.second);
        };
        if (crosses(left(p), left(q))) c.wings.push_back({j, "LEFT", "CALENDAR"});
        if (crosses(right(p), right(q))) c.wings.push_back({j, "RIGHT", "CALENDAR"});
    }
    if (reject && !c.arbitrage_free()) throw Error("E_ARBITRAGE", "the surface has arbitrage");
    return c;
}

Svi ssvi_to_svi(double rho, double eta, double gamma, double theta) {
    const Ssvi s{rho, eta, gamma};
    check_ssvi(s, {theta});
    const double phi = s.phi(theta);
    return {theta * (1 - rho * rho) / 2, theta * phi / 2, rho, -rho / phi, std::sqrt(1 - rho * rho) / phi};
}

SurfaceFit svi_fit_surface(const std::vector<double>& t, const std::vector<double>& k,
                           const std::vector<std::vector<double>>& w, bool reject) {
    check_increasing(t, "expiry_years", 1);
    if (w.size() != t.size()) throw Error("E_INPUT", "total_variance needs one row per expiry", "total_variance");
    SurfaceFit out;
    for (std::size_t j = 0; j < t.size(); ++j) {
        const SviFit f = svi_calibrate(k, w[j], std::nullopt);
        out.slices.push_back({t[j], f.svi});
        out.rmse.push_back(f.rmse);
    }
    out.check = svi_surface_check(out.slices, k, reject);
    return out;
}

LocalVol local_vol_dupire(const std::vector<SviSlice>& sl, const std::vector<LocalVolPoint>& pts) {
    check_slices(sl);
    if (pts.empty()) throw Error("E_INPUT", "points is empty", "points");
    if (pts.size() > max_points) throw Error("E_LIMIT", "points is above its limit", "points");
    for (const LocalVolPoint& p : pts)
        if (p.expiry_years <= 0) throw Error("E_DOMAIN", "a point's expiry_years is not above 0", "points");
    LocalVol out;
    for (const LocalVolPoint& p : pts) {
        const double k = p.log_moneyness;
        const WSurface s = surface_at(sl, p.expiry_years, k);
        const double lead = 1 - k * s.wk / (2 * s.w);
        const double g = lead * lead - (s.wk * s.wk / 4) * (1 / s.w + 0.25) + s.wkk / 2;
        if (s.wt <= 0) throw Error("E_ARBITRAGE", "w_T is not above 0: calendar arbitrage");
        if (g <= 0) throw Error("E_ARBITRAGE", "g is not above 0: butterfly arbitrage");
        out.total_variance.push_back(s.w);
        out.implied_vol.push_back(std::sqrt(s.w / p.expiry_years));
        out.local_vol.push_back(std::sqrt(s.wt / g));
    }
    return out;
}

std::vector<double> forward_vols(const std::vector<double>& t, const std::vector<double>& v) {
    check_increasing(t, "expiry_years", 1);
    if (v.size() != t.size()) throw Error("E_INPUT", "vols and expiry_years differ in length", "vols");
    for (const double x : v)
        if (x <= 0) throw Error("E_DOMAIN", "a vol is not above 0", "vols");
    std::vector<double> out{v[0]};
    for (std::size_t i = 1; i < t.size(); ++i) {
        const double r = (v[i] * v[i] * t[i] - v[i - 1] * v[i - 1] * t[i - 1]) / (t[i] - t[i - 1]);
        if (r < 0) throw Error("E_ARBITRAGE", "negative forward variance: calendar arbitrage");
        out.push_back(std::sqrt(r));
    }
    return out;
}

SmileDynamics smile_dynamics(const SmileDynamicsInputs& in) {
    if (in.strikes.empty()) throw Error("E_INPUT", "strikes is empty", "strikes");
    check_svi(in.svi);
    if (in.expiry_years <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0", "expiry_years");
    if (in.spot <= 0) throw Error("E_DOMAIN", "spot is not above 0", "spot");
    if (in.spot_shifted <= 0) throw Error("E_DOMAIN", "spot_shifted is not above 0", "spot_shifted");
    for (const double k : in.strikes)
        if (k <= 0) throw Error("E_DOMAIN", "a strike is not above 0", "strikes");
    const double t = in.expiry_years, carry = std::exp((in.rate - in.dividend_yield) * t);
    const double d = std::exp(-in.rate * t), dq = std::exp(-in.dividend_yield * t);
    const double f0 = in.spot * carry, f1 = in.spot_shifted * carry;
    const bool call = in.type == OptionType::Call;
    SmileDynamics out;
    for (const double K : in.strikes) {
        const double k0 = std::log(K / f0);
        const W3 base = svi_w3(in.svi, k0);
        const double v0 = std::sqrt(base.w / t);
        const double v1 = in.rule == SmileRule::StickyStrike ? v0 : std::sqrt(in.svi.w(std::log(K / f1)) / t);
        out.vols_base.push_back(v0);
        out.vols_shifted.push_back(v1);
        out.prices_base.push_back(black_forward(f0, K, v0, t, d, in.type));
        out.prices_shifted.push_back(black_forward(f1, K, v1, t, d, in.type));
        const double sd = v0 * std::sqrt(t), d1 = std::log(f0 / K) / sd + sd / 2;
        const double delta_bs = call ? dq * normal_cdf(d1) : -dq * normal_cdf(-d1);
        const double vega = in.spot * dq * normal_pdf(d1) * std::sqrt(t);
        const double dv_ds = in.rule == SmileRule::StickyStrike ? 0.0 : -(base.wk / (2 * v0 * t)) / in.spot;
        out.deltas.push_back(delta_bs + vega * dv_ds);
    }
    return out;
}

VolOfVol vol_of_vol(const std::vector<double>& v, double ppy, VolChange method) {
    if (v.size() < 3) throw Error("E_INPUT", "at least 3 vols are needed", "vols");
    for (const double x : v)
        if (x <= 0) throw Error("E_DOMAIN", "a vol is not above 0", "vols");
    if (ppy <= 0) throw Error("E_DOMAIN", "periods_per_year is not above 0", "periods_per_year");
    std::vector<double> x;
    for (std::size_t i = 1; i < v.size(); ++i)
        x.push_back(method == VolChange::Log ? std::log(v[i] / v[i - 1]) : v[i] - v[i - 1]);
    double mean = 0;
    for (const double c : x) mean += c;
    mean /= double(x.size());
    double ss = 0;
    for (const double c : x) ss += (c - mean) * (c - mean);
    return {mean, std::sqrt(ppy) * std::sqrt(ss / double(x.size() - 1))};
}

}  // namespace quantforge
