#include "quantforge/core/vol_stats.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>
#include <set>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

constexpr double ln_2pi = 1.8378770664093454835606594728112;  // ln(2 pi)

double sample_variance(const std::vector<double>& r) {
    double s = 0.0;
    for (const double x : r) s += x * x;
    return s / double(r.size());
}

// The recursion and likelihood, without checks; fills variances when asked.
double loglik_raw(const std::vector<double>& r, double omega, double alpha, double beta, double v1,
                  std::vector<double>* variances, double* next) {
    double v = v1, sum = 0.0;
    for (const double x : r) {
        if (variances) variances->push_back(v);
        sum += ln_2pi + std::log(v) + x * x / v;
        v = omega + alpha * x * x + beta * v;
    }
    if (next) *next = v;
    return -0.5 * sum;
}

double start_variance(const std::vector<double>& r, std::optional<double> initial) {
    if (initial) {
        if (*initial <= 0.0) throw Error("E_DOMAIN", "initial_variance must be positive", "initial_variance");
        return *initial;
    }
    const double v = sample_variance(r);
    if (v <= 0.0) throw Error("E_DOMAIN", "SAMPLE initial variance is zero", "initial_variance");
    return v;
}

void check_params(double omega, double alpha, double beta) {
    if (omega <= 0.0) throw Error("E_DOMAIN", "omega must be positive", "omega");
    if (alpha < 0.0) throw Error("E_DOMAIN", "alpha must not be negative", "alpha");
    if (beta < 0.0) throw Error("E_DOMAIN", "beta must not be negative", "beta");
}

// Unconstrained coordinates: omega = e^u0, alpha and beta a softmax share with a slack term, so alpha + beta < 1.
std::array<double, 3> params_of(const std::array<double, 3>& u) {
    const double m = std::max({0.0, u[1], u[2]});
    const double e0 = std::exp(-m), e1 = std::exp(u[1] - m), e2 = std::exp(u[2] - m), s = e0 + e1 + e2;
    return {std::exp(u[0]), e1 / s, e2 / s};
}

std::array<double, 3> coords_of(double omega, double alpha, double beta) {
    const double slack = 1.0 - alpha - beta;
    return {std::log(omega), std::log(alpha / slack), std::log(beta / slack)};
}

using Point = std::array<double, 3>;

// Nelder-Mead minimiser (standard coefficients) from a start and a step; returns the best point.
Point nelder_mead(auto&& f, Point x0, double step, int max_iter, bool& converged) {
    std::array<Point, 4> s;
    std::array<double, 4> fs;
    for (int i = 0; i < 4; ++i) {
        s[i] = x0;
        if (i > 0) s[i][i - 1] += step;
        fs[i] = f(s[i]);
    }
    converged = false;
    for (int it = 0; it < max_iter; ++it) {
        std::array<int, 4> o = {0, 1, 2, 3};
        std::sort(o.begin(), o.end(), [&](int a, int b) { return fs[a] < fs[b]; });
        const int best = o[0], worst = o[3], second = o[2];
        if (std::fabs(fs[worst] - fs[best]) <= 1e-15 * (1.0 + std::fabs(fs[best]))) {
            converged = true;
            return s[best];
        }
        Point c{};
        for (int i = 0; i < 4; ++i)
            if (i != worst)
                for (int k = 0; k < 3; ++k) c[k] += s[i][k] / 3.0;
        const auto along = [&](double t) {
            Point p;
            for (int k = 0; k < 3; ++k) p[k] = c[k] + t * (s[worst][k] - c[k]);
            return p;
        };
        const Point xr = along(-1.0);
        const double fr = f(xr);
        if (fr < fs[best]) {
            const Point xe = along(-2.0);
            const double fe = f(xe);
            if (fe < fr) s[worst] = xe, fs[worst] = fe;
            else s[worst] = xr, fs[worst] = fr;
        } else if (fr < fs[second]) {
            s[worst] = xr, fs[worst] = fr;
        } else {
            const Point xc = fr < fs[worst] ? along(-0.5) : along(0.5);
            const double fc = f(xc);
            if (fc < std::min(fr, fs[worst])) {
                s[worst] = xc, fs[worst] = fc;
            } else {
                for (int i = 0; i < 4; ++i) {
                    if (i == best) continue;
                    for (int k = 0; k < 3; ++k) s[i][k] = s[best][k] + 0.5 * (s[i][k] - s[best][k]);
                    fs[i] = f(s[i]);
                }
            }
        }
    }
    return s[std::min_element(fs.begin(), fs.end()) - fs.begin()];
}

void check_strikes(const std::vector<double>& k, const char* key) {
    if (k.empty()) throw Error("E_INPUT", std::string(key) + " is empty", key);
    if (std::set<double>(k.begin(), k.end()).size() != k.size())
        throw Error("E_INPUT", std::string(key) + " repeats a strike", key);
}

// DDKZ weights along a walk of strikes (ruling E-B3): the last entry is the extension, with no option.
std::vector<double> walk_weights(const std::vector<double>& k, auto&& f) {
    std::vector<double> w;
    double prev = 0.0;
    for (std::size_t j = 0; j + 1 < k.size(); ++j) {
        const double s = std::fabs(f(k[j + 1]) - f(k[j])) / std::fabs(k[j + 1] - k[j]);
        w.push_back(s - prev);
        prev = s;
    }
    return w;
}

}  // namespace

// ---- GARCH ----

GarchLoglik garch_loglik(const std::vector<double>& r, double omega, double alpha, double beta,
                         std::optional<double> initial) {
    if (r.size() < 2) throw Error("E_INPUT", "at least 2 returns are needed", "returns");
    check_params(omega, alpha, beta);
    const double v1 = start_variance(r, initial);
    GarchLoglik out;
    out.loglik = loglik_raw(r, omega, alpha, beta, v1, &out.variances, &out.next_variance);
    return out;
}

GarchForecast garch_forecast(double omega, double alpha, double beta, double next, long long h, double ppy) {
    if (h < 1) throw Error("E_INPUT", "horizon must be at least 1", "horizon");
    if (ppy <= 0.0) throw Error("E_INPUT", "periods_per_year must be positive", "periods_per_year");
    check_params(omega, alpha, beta);
    if (next <= 0.0) throw Error("E_DOMAIN", "next_variance must be positive", "next_variance");
    const double p = alpha + beta;
    if (p >= 1.0) throw Error("E_DOMAIN", "alpha + beta >= 1 has no long-run variance");
    GarchForecast out;
    out.long_run_variance = omega / (1.0 - p);
    out.total_variance = 0.0;
    double pk = 1.0;  // p^(h-1)
    for (long long i = 1; i <= h; ++i) {
        const double v = out.long_run_variance + pk * (next - out.long_run_variance);
        out.variances.push_back(v);
        out.total_variance += v;
        pk *= p;
    }
    out.annualized_vol = std::sqrt(out.total_variance * ppy / double(h));
    return out;
}

GarchFit garch_fit(const std::vector<double>& r, std::optional<double> initial) {
    if (r.size() < 30) throw Error("E_INPUT", "at least 30 returns are needed", "returns");
    const double v1 = start_variance(r, initial);
    const double var = sample_variance(r);
    const auto objective = [&](const Point& u) {
        const auto [o, a, b] = params_of(u);
        const double ll = loglik_raw(r, o, a, b, v1, nullptr, nullptr);
        return std::isfinite(ll) ? -ll : 1e300;
    };
    // Several starts, then restarts from the best point until a restart no longer improves it.
    Point best{};
    double fbest = 1e300;
    constexpr std::array<std::array<double, 2>, 5> starts = {
        {{0.05, 0.90}, {0.10, 0.80}, {0.20, 0.60}, {0.05, 0.50}, {0.30, 0.30}}};
    for (const auto& [a, b] : starts) {
        bool ok = false;
        const Point x = nelder_mead(objective, coords_of(std::max(var, 1e-300) * (1.0 - a - b), a, b), 0.5, 5000, ok);
        const double fx = objective(x);
        if (fx < fbest) best = x, fbest = fx;
    }
    bool converged = false;
    for (int round = 0; round < 50; ++round) {
        const Point x = nelder_mead(objective, best, 0.05, 20000, converged);
        const double fx = objective(x);
        const double gain = fbest - fx;
        if (fx < fbest) best = x, fbest = fx;
        if (converged && gain <= 1e-12 * (1.0 + std::fabs(fbest))) break;
        converged = false;
    }
    if (!converged || fbest >= 1e300) throw Error("E_NO_CONVERGENCE", "the GARCH fit did not converge");
    const auto [o, a, b] = params_of(best);
    return {-fbest, o, a, b};
}

// ---- variance swaps ----

VarSwapFair varswap_fair_strike(const VarSwapInputs& in) {
    if (in.maturity <= in.as_of) throw Error("E_INPUT", "maturity must be after as_of", "maturity");
    check_strikes(in.put_strikes, "put_strikes");
    check_strikes(in.call_strikes, "call_strikes");
    for (const double k : in.put_strikes)
        if (k > in.spot) throw Error("E_INPUT", "a put strike is above spot", "put_strikes");
    for (const double k : in.call_strikes)
        if (k < in.spot) throw Error("E_INPUT", "a call strike is below spot", "call_strikes");
    std::set<double> all(in.put_strikes.begin(), in.put_strikes.end());
    all.insert(in.call_strikes.begin(), in.call_strikes.end());
    std::set<double> listed;
    for (const StrikeVol& v : in.vols)
        if (!all.contains(v.strike) || !listed.insert(v.strike).second)
            throw Error("E_INPUT", "vols must list each strike exactly once", "vols");
    if (listed.size() != all.size()) throw Error("E_INPUT", "vols must list each strike exactly once", "vols");
    if (in.spot <= 0.0) throw Error("E_DOMAIN", "spot must be positive", "spot");
    for (const StrikeVol& v : in.vols)
        if (v.vol <= 0.0) throw Error("E_DOMAIN", "a vol is not positive", "vols");
    if (in.extension_step <= 0.0) throw Error("E_DOMAIN", "extension_step must be positive", "extension_step");
    const double kmin = *std::min_element(in.put_strikes.begin(), in.put_strikes.end());
    if (kmin - in.extension_step <= 0.0) throw Error("E_DOMAIN", "the put extension strike is not positive");

    const double t = days_between(in.as_of, in.maturity) / 365.0, s0 = in.spot;
    const double d = std::exp(-in.rate * t), fwd = s0 * std::exp((in.rate - in.dividend_yield) * t);
    const auto f = [&](double k) { return (2.0 / t) * ((k - s0) / s0 - std::log(k / s0)); };
    const auto vol_of = [&](double k) {
        for (const StrikeVol& v : in.vols)
            if (v.strike == k) return v.vol;
        return 0.0;  // unreachable: every strike is listed
    };
    std::vector<double> calls = in.call_strikes, puts = in.put_strikes;
    std::ranges::sort(calls);
    std::ranges::sort(puts, std::greater<>{});
    calls.push_back(calls.back() + in.extension_step);
    puts.push_back(puts.back() - in.extension_step);
    double pi = 0.0;
    const std::vector<double> wc = walk_weights(calls, f), wp = walk_weights(puts, f);
    for (std::size_t j = 0; j < wc.size(); ++j) pi += wc[j] * black_price(fwd, calls[j], vol_of(calls[j]), t, d, 1.0);
    for (std::size_t j = 0; j < wp.size(); ++j) pi += wp[j] * black_price(fwd, puts[j], vol_of(puts[j]), t, d, -1.0);
    VarSwapFair out;
    out.fair_variance = (2.0 / t) * ((in.rate - in.dividend_yield) * t - (fwd / s0 - 1.0)) + pi / d;
    out.fair_vol = std::sqrt(out.fair_variance);
    out.pv = in.variance_notional * d * (out.fair_variance - in.variance_strike);
    return out;
}

VarSwapRealized varswap_realized(const std::vector<double>& p, double a, double k_var, double n_var) {
    if (p.size() < 2) throw Error("E_INPUT", "at least 2 prices are needed", "prices");
    for (const double x : p)
        if (x <= 0.0) throw Error("E_DOMAIN", "a price is not positive", "prices");
    double s = 0.0;
    for (std::size_t i = 1; i < p.size(); ++i) {
        const double x = std::log(p[i] / p[i - 1]);
        s += x * x;
    }
    VarSwapRealized out;
    out.realized_variance = a / double(p.size() - 1) * s;
    out.realized_vol = std::sqrt(out.realized_variance);
    out.payoff = n_var * (out.realized_variance - k_var);
    return out;
}

// ---- VIX ----

VixTermResult vix_term_variance(const VixTerm& term) {
    if (term.minutes < 1) throw Error("E_INPUT", "minutes_to_expiry must be at least 1", "minutes_to_expiry");
    std::vector<VixQuote> q = term.strip;
    std::ranges::sort(q, {}, &VixQuote::strike);
    if (q.size() < 3) throw Error("E_INPUT", "at least 3 strikes are needed", "strip");
    for (std::size_t i = 1; i < q.size(); ++i)
        if (q[i].strike == q[i - 1].strike) throw Error("E_INPUT", "the strip repeats a strike", "strip");
    for (const VixQuote& x : q)
        if (x.call_bid > x.call_ask || x.put_bid > x.put_ask) throw Error("E_INPUT", "a bid is above its ask", "strip");
    for (const VixQuote& x : q)
        if (x.call_bid < 0.0 || x.call_ask < 0.0 || x.put_bid < 0.0 || x.put_ask < 0.0)
            throw Error("E_DOMAIN", "a quote is negative", "strip");

    const double t = double(term.minutes) / 525600.0, growth = std::exp(term.rate * t);
    const auto cmid = [&](std::size_t i) { return (q[i].call_bid + q[i].call_ask) / 2.0; };
    const auto pmid = [&](std::size_t i) { return (q[i].put_bid + q[i].put_ask) / 2.0; };
    std::size_t star = 0;
    for (std::size_t i = 1; i < q.size(); ++i)
        if (std::fabs(cmid(i) - pmid(i)) < std::fabs(cmid(star) - pmid(star))) star = i;  // ties keep the lowest
    const double fwd = q[star].strike + growth * (cmid(star) - pmid(star));
    std::ptrdiff_t i0 = -1;
    for (std::size_t i = 0; i < q.size(); ++i)
        if (q[i].strike <= fwd) i0 = std::ptrdiff_t(i);
    if (i0 < 0) throw Error("E_INPUT", "no strike is at or below the forward", "strip");

    // Selected strikes with their prices Q, ascending.
    std::vector<std::pair<double, double>> sel;
    int zeros = 0;
    for (std::ptrdiff_t i = i0 - 1; i >= 0; --i) {
        if (q[i].put_bid == 0.0) {
            if (++zeros == 2) break;
            continue;
        }
        zeros = 0;
        sel.emplace_back(q[i].strike, pmid(std::size_t(i)));
    }
    std::ranges::reverse(sel);
    sel.emplace_back(q[i0].strike, (cmid(std::size_t(i0)) + pmid(std::size_t(i0))) / 2.0);
    zeros = 0;
    for (std::size_t i = std::size_t(i0) + 1; i < q.size(); ++i) {
        if (q[i].call_bid == 0.0) {
            if (++zeros == 2) break;
            continue;
        }
        zeros = 0;
        sel.emplace_back(q[i].strike, cmid(i));
    }
    if (sel.size() < 2) throw Error("E_INPUT", "fewer than 2 strikes are selected", "strip");

    VixTermResult out;
    out.forward = fwd;
    out.k0 = q[i0].strike;
    out.t = t;
    double sum = 0.0;
    const std::size_t n = sel.size();
    for (std::size_t i = 0; i < n; ++i) {
        const double lo = sel[i == 0 ? 0 : i - 1].first, hi = sel[i + 1 == n ? i : i + 1].first;
        const double dk = (i == 0 || i + 1 == n) ? hi - lo : (hi - lo) / 2.0;
        sum += dk / (sel[i].first * sel[i].first) * sel[i].second;
        out.strikes_used.push_back(sel[i].first);
    }
    const double c = fwd / out.k0 - 1.0;
    out.variance = (2.0 / t) * growth * sum - c * c / t;
    return out;
}

VixIndex vix_index(const VixTerm& near, const VixTerm& next) {
    constexpr double n30 = 43200.0, n365 = 525600.0;
    const double n1 = double(near.minutes), n2 = double(next.minutes);
    if (!(n1 < n2 && n1 <= n30 && n30 <= n2))
        throw Error("E_INPUT", "the terms must bracket 30 days with near before next");
    const VixTermResult a = vix_term_variance(near), b = vix_term_variance(next);
    const double bracket = a.t * a.variance * (n2 - n30) / (n2 - n1) + b.t * b.variance * (n30 - n1) / (n2 - n1);
    if (bracket < 0.0) throw Error("E_DOMAIN", "the interpolated variance is negative");
    return {100.0 * std::sqrt(bracket * n365 / n30), a.variance, b.variance};
}

}  // namespace quantforge
