#include "quantforge/core/research.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <numbers>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::research {
namespace {

using Vec = std::vector<double>;
using Mat = std::vector<std::vector<double>>;

[[noreturn]] void input(const std::string& why, const std::string& field = {}) { throw Error("E_INPUT", why, field); }
[[noreturn]] void domain(const std::string& why, const std::string& field = {}) { throw Error("E_DOMAIN", why, field); }

// Ruling F-3: no negative zero in any output.
double pz(double x) { return x + 0.0; }

void clean(Vec& x) {
    for (double& v : x) v = pz(v);
}

double sum(const Vec& x) {
    double a = 0;
    for (const double v : x) a += v;
    return a;
}

// Running peak from a starting equity of 0 (J-6).
double drawdown(const Vec& equity) {
    double peak = 0, dd = 0;
    for (const double e : equity) {
        peak = std::max(peak, e);
        dd = std::max(dd, peak - e);
    }
    return dd;
}

Backtest event_loop(const BacktestInput& in) {
    const std::size_t n = in.prices.size();
    const auto lag = static_cast<std::size_t>(in.lag);
    const Vec& p = in.prices;
    const double m = in.multiplier, hs = in.half_spread_bps / 1e4;
    Backtest b;
    double prev = 0, e = 0;
    for (std::size_t t = 0; t < n; ++t) {
        const double qt = t >= lag ? in.targets[t - lag] : 0.0;
        const double dt = qt - prev;
        const double gt = t >= 1 ? prev * (p[t] - p[t - 1]) * m : 0.0;
        const double s = std::fabs(dt) * p[t] * hs * m;
        const double c = std::fabs(dt) * in.commission_per_unit;
        const double f = dt != 0 ? in.fixed_per_trade : 0.0;
        const double kt = s + c + f, nt = gt - kt;
        e += nt;
        b.positions.push_back(qt);
        b.trades.push_back(dt);
        b.pnl_gross.push_back(gt);
        b.cost.push_back(kt);
        b.pnl_net.push_back(nt);
        b.equity.push_back(e);
        b.total_gross += gt;
        b.total_spread += s;
        b.total_commission += c;
        b.total_fixed += f;
        b.turnover += std::fabs(dt) * p[t] * m;
        if (dt != 0) ++b.trade_count;
        prev = qt;
    }
    return b;
}

// Whole arrays: shift, diff, multiply, cumsum (J-3).
Backtest vector_engine(const BacktestInput& in) {
    const std::size_t n = in.prices.size();
    const auto lag = static_cast<std::size_t>(in.lag);
    const Vec& p = in.prices;
    const double m = in.multiplier, hs = in.half_spread_bps / 1e4;
    Vec q(n, 0.0), q_prev(n, 0.0), dp(n, 0.0);
    for (std::size_t t = lag; t < n; ++t) q[t] = in.targets[t - lag];
    for (std::size_t t = 1; t < n; ++t) q_prev[t] = q[t - 1];
    for (std::size_t t = 1; t < n; ++t) dp[t] = p[t] - p[t - 1];
    Vec d(n), g(n), s(n), c(n), f(n), k(n), net(n), eq(n);
    for (std::size_t t = 0; t < n; ++t) d[t] = q[t] - q_prev[t];
    for (std::size_t t = 0; t < n; ++t) g[t] = t >= 1 ? q_prev[t] * dp[t] * m : 0.0;
    for (std::size_t t = 0; t < n; ++t) s[t] = std::fabs(d[t]) * p[t] * hs * m;
    for (std::size_t t = 0; t < n; ++t) c[t] = std::fabs(d[t]) * in.commission_per_unit;
    for (std::size_t t = 0; t < n; ++t) f[t] = d[t] != 0 ? in.fixed_per_trade : 0.0;
    for (std::size_t t = 0; t < n; ++t) k[t] = s[t] + c[t] + f[t];
    for (std::size_t t = 0; t < n; ++t) net[t] = g[t] - k[t];
    double a = 0;
    for (std::size_t t = 0; t < n; ++t) eq[t] = a += net[t];
    Backtest b;
    for (std::size_t t = 0; t < n; ++t) {
        b.turnover += std::fabs(d[t]) * p[t] * m;
        if (d[t] != 0) ++b.trade_count;
    }
    b.total_gross = sum(g);
    b.total_spread = sum(s);
    b.total_commission = sum(c);
    b.total_fixed = sum(f);
    b.positions = std::move(q);
    b.trades = std::move(d);
    b.pnl_gross = std::move(g);
    b.cost = std::move(k);
    b.pnl_net = std::move(net);
    b.equity = std::move(eq);
    return b;
}

void check_row(const Vec& r) {
    double s = 0;
    for (const double v : r) {
        if (v < 0) domain("negative probability");
        s += v;
    }
    if (std::fabs(s - 1.0) > 1e-9) domain("probabilities do not sum to 1");
}

void check_sharpe(long long n_obs, double kurtosis) {
    if (n_obs < 2) input("n_obs below 2", "n_obs");
    if (kurtosis < 1) domain("kurtosis below 1", "kurtosis");
}

double sharpe_z(double sr, long long n_obs, double skew, double kurtosis, double benchmark) {
    const double v = 1 - skew * sr + (kurtosis - 1) / 4 * sr * sr;
    if (v <= 0) domain("variance term 1 - skew sr + (kurtosis - 1)/4 sr^2 is not positive");  // J-14
    return (sr - benchmark) * std::sqrt(static_cast<double>(n_obs) - 1.0) / std::sqrt(v);
}

double mean(const Vec& x) { return sum(x) / static_cast<double>(x.size()); }

double sample_sd(const Vec& x) {
    const double mu = mean(x);
    double a = 0;
    for (const double v : x) a += (v - mu) * (v - mu);
    return std::sqrt(a / static_cast<double>(x.size() - 1));
}

}  // namespace

void check_backtest(const BacktestInput& in) {
    const auto t = static_cast<long long>(in.prices.size());
    if (static_cast<long long>(in.targets.size()) != t || t < 2 || in.lag < 0 || in.lag >= t)
        input("prices, targets and lag do not fit");
    for (const double p : in.prices)
        if (p <= 0) domain("a price is not positive", "prices");
    if (in.half_spread_bps < 0 || in.commission_per_unit < 0 || in.fixed_per_trade < 0)
        domain("a cost input is negative");
    if (in.multiplier <= 0) domain("multiplier must be positive", "multiplier");
}

Backtest backtest(const BacktestInput& in, Engine engine) {
    check_backtest(in);
    Backtest b = engine == Engine::Event ? event_loop(in) : vector_engine(in);
    b.max_drawdown = pz(drawdown(b.equity));
    b.total_net = pz(b.total_gross - b.total_spread - b.total_commission - b.total_fixed);
    b.total_gross = pz(b.total_gross);
    b.total_spread = pz(b.total_spread);
    b.total_commission = pz(b.total_commission);
    b.total_fixed = pz(b.total_fixed);
    b.turnover = pz(b.turnover);
    for (Vec* v : {&b.positions, &b.trades, &b.pnl_gross, &b.cost, &b.pnl_net, &b.equity}) clean(*v);
    return b;
}

PurgedKFold purged_kfold(const Vec& t0, const Vec& t1, long long k, double embargo_pct) {
    const std::size_t n = t0.size();
    if (t1.size() != n || k < 2 || k > static_cast<long long>(n)) input("lengths differ or n_splits out of range");
    for (std::size_t i = 1; i < n; ++i)
        if (t0[i] < t0[i - 1]) input("t0 must be non-decreasing", "t0");
    for (std::size_t i = 0; i < n; ++i)
        if (t1[i] < t0[i]) domain("t1 before t0", "t1");
    if (embargo_pct < 0 || embargo_pct >= 1) domain("embargo_pct outside [0, 1)", "embargo_pct");
    const auto h = static_cast<std::size_t>(std::floor(embargo_pct * static_cast<double>(n)));  // J-8
    const auto kk = static_cast<std::size_t>(k);
    PurgedKFold out;
    out.embargo_count = static_cast<long long>(h);
    std::size_t a = 0;
    for (std::size_t f = 0; f < kk; ++f) {
        const std::size_t b = a + n / kk + (f < n % kk ? 1 : 0);
        const double lo = t0[a];
        double hi = -std::numeric_limits<double>::infinity();
        for (std::size_t i = a; i < b; ++i) hi = std::max(hi, t1[i]);
        Fold fold;
        for (std::size_t j = 0; j < n; ++j) {
            if (j >= a && j < b) fold.test.push_back(static_cast<long long>(j));
            else if (!(t0[j] <= hi && t1[j] >= lo) && !(j >= b && j < b + h)) fold.train.push_back(static_cast<long long>(j));
        }
        out.folds.push_back(std::move(fold));
        a = b;
    }
    return out;
}

CpcvCounts cpcv_paths(long long n_groups, long long n_test_groups) {
    if (n_groups > 64) throw Error("E_LIMIT", "n_groups above 64", "n_groups");
    if (n_groups < 2 || n_test_groups < 1 || n_test_groups >= n_groups) input("n_groups or n_test_groups out of range");
    // C(N, i) grows through exact integer steps; C(64, 32) < 2^63 and c * (N - i) fits in unsigned 128 bits.
    unsigned __int128 c = 1;
    for (long long i = 0; i < n_test_groups; ++i)
        c = c * static_cast<unsigned __int128>(n_groups - i) / static_cast<unsigned __int128>(i + 1);
    const unsigned __int128 paths = c * static_cast<unsigned __int128>(n_test_groups) / static_cast<unsigned __int128>(n_groups);
    return {static_cast<long long>(c), static_cast<long long>(paths)};
}

void check_model(const Vec& initial, const Mat& transition) {
    check_row(initial);
    for (const Vec& r : transition) check_row(r);
}

Mat log_emission(const Mat& e) {
    Mat out(e.size());
    for (std::size_t t = 0; t < e.size(); ++t)
        for (const double v : e[t]) {
            if (v < 0) domain("negative emission", "emission");
            out[t].push_back(std::log(v));
        }
    return out;
}

Mat gaussian_log_emission(const Vec& y, const Vec& means, const Vec& sds) {
    for (const double s : sds)
        if (s <= 0) domain("sd must be positive", "sds");
    const double c = std::log(2 * std::numbers::pi) / 2;
    Mat out(y.size(), Vec(means.size()));
    for (std::size_t t = 0; t < y.size(); ++t)
        for (std::size_t j = 0; j < means.size(); ++j) {
            const double z = y[t] - means[j];
            out[t][j] = -std::log(sds[j]) - c - z * z / (2 * sds[j] * sds[j]);
        }
    return out;
}

ViterbiResult viterbi(const Vec& initial, const Mat& transition, const Mat& log_e) {
    const std::size_t k = initial.size(), n = log_e.size();
    Mat la(k, Vec(k));
    for (std::size_t i = 0; i < k; ++i)
        for (std::size_t j = 0; j < k; ++j) la[i][j] = std::log(transition[i][j]);
    Vec delta(k), next(k);
    for (std::size_t j = 0; j < k; ++j) delta[j] = std::log(initial[j]) + log_e[0][j];
    std::vector<std::vector<std::size_t>> back(n, std::vector<std::size_t>(k, 0));
    for (std::size_t t = 1; t < n; ++t) {
        for (std::size_t j = 0; j < k; ++j) {
            std::size_t best = 0;
            double bv = delta[0] + la[0][j];
            for (std::size_t i = 1; i < k; ++i) {
                const double v = delta[i] + la[i][j];
                if (v > bv) {  // strict: ties keep the smallest index (J-11)
                    bv = v;
                    best = i;
                }
            }
            back[t][j] = best;
            next[j] = bv + log_e[t][j];
        }
        delta.swap(next);
    }
    std::size_t end = 0;
    for (std::size_t j = 1; j < k; ++j)
        if (delta[j] > delta[end]) end = j;
    if (!(delta[end] > -std::numeric_limits<double>::infinity())) domain("every path has probability zero");
    ViterbiResult r{std::vector<long long>(n), pz(delta[end])};
    std::size_t s = end;
    for (std::size_t t = n; t-- > 0;) {
        r.states[t] = static_cast<long long>(s);
        s = back[t][s];
    }
    return r;
}

Psr psr(double sr, long long n_obs, double skew, double kurtosis, double sr_benchmark) {
    check_sharpe(n_obs, kurtosis);
    const double z = sharpe_z(sr, n_obs, skew, kurtosis, sr_benchmark);
    return {pz(z), normal_cdf(z)};
}

Dsr dsr(double sr, long long n_obs, double skew, double kurtosis, long long n_trials, double sr_variance) {
    check_sharpe(n_obs, kurtosis);
    if (n_trials < 1) input("n_trials below 1", "n_trials");
    if (sr_variance < 0) domain("sr_variance negative", "sr_variance");
    double sr0 = 0.0;  // J-13
    if (n_trials > 1) {
        const auto nn = static_cast<double>(n_trials);
        sr0 = std::sqrt(sr_variance) * ((1 - euler_gamma) * normal_inverse(1 - 1 / nn) +
                                        euler_gamma * normal_inverse(1 - 1 / (nn * std::numbers::e)));
    }
    const double z = sharpe_z(sr, n_obs, skew, kurtosis, sr0);
    return {pz(sr0), pz(z), normal_cdf(z)};
}

Power power(double years, double alpha, double pw, std::optional<double> sr_target) {
    if (years <= 0 || alpha <= 0 || alpha >= 1 || pw <= 0 || pw >= 1 || alpha >= pw)
        domain("years, alpha or power out of range");
    if (sr_target && *sr_target <= 0) domain("sr_target must be positive", "sr_target");
    const double zs = normal_inverse(1 - alpha) + normal_inverse(pw);
    Power r{zs, zs / std::sqrt(years), 1 / std::sqrt(years), std::nullopt, std::nullopt};
    if (sr_target) {
        const double q = zs / *sr_target;
        r.years_required = q * q;
        r.se_at_target = std::sqrt((1 + *sr_target * *sr_target / 2) / years);
    }
    return r;
}

void check_pbo_shape(const Mat& perf, long long s) {
    const auto t = static_cast<long long>(perf.size());
    if (s < 2 || s % 2 != 0 || t == 0 || t % s != 0 || t / s < 2) input("n_partitions does not fit the rows", "n_partitions");
    const std::size_t n = perf[0].size();
    for (const Vec& r : perf)
        if (r.size() != n) input("ragged performance", "performance");
    if (n < 2) input("fewer than two strategies", "performance");
}

Pbo pbo(const Mat& perf, long long s_in, Metric metric) {
    check_pbo_shape(perf, s_in);
    const auto s = static_cast<std::size_t>(s_in);
    const std::size_t n = perf[0].size(), block = perf.size() / s, half = s / 2;
    const auto column = [&](std::size_t j, const std::vector<bool>& pick, bool want) {
        Vec x;
        for (std::size_t b = 0; b < s; ++b)
            if (pick[b] == want)
                for (std::size_t i = 0; i < block; ++i) x.push_back(perf[b * block + i][j]);
        return x;
    };
    if (metric == Metric::Sharpe)  // J-17, per block
        for (std::size_t b = 0; b < s; ++b) {
            std::vector<bool> one(s, false);
            one[b] = true;
            for (std::size_t j = 0; j < n; ++j)
                if (sample_sd(column(j, one, true)) == 0) domain("zero standard deviation in a block", "performance");
        }
    const auto score = [&](const Vec& x) { return metric == Metric::Mean ? mean(x) : mean(x) / sample_sd(x); };
    Pbo out{0.0, {}, 0};
    std::vector<std::size_t> combo(half);
    for (std::size_t i = 0; i < half; ++i) combo[i] = i;
    long long bad = 0;
    while (true) {
        std::vector<bool> train(s, false);
        for (const std::size_t b : combo) train[b] = true;
        Vec tr(n), te(n);
        for (std::size_t j = 0; j < n; ++j) {
            tr[j] = score(column(j, train, true));
            te[j] = score(column(j, train, false));
        }
        std::size_t star = 0;
        for (std::size_t j = 1; j < n; ++j)
            if (tr[j] > tr[star]) star = j;  // J-16: lowest index among ties
        double less = 0, equal = 0;
        for (std::size_t j = 0; j < n; ++j) {
            if (te[j] < te[star]) less += 1;
            else if (te[j] == te[star]) equal += 1;
        }
        const double omega = (less + (equal + 1) / 2.0) / (static_cast<double>(n) + 1);
        const double lambda = pz(std::log(omega / (1 - omega)));
        out.logits.push_back(lambda);
        if (lambda <= 0) ++bad;
        // next combination in lexicographic order
        std::size_t i = half;
        while (i > 0 && combo[i - 1] == s - half + i - 1) --i;
        if (i == 0) break;
        ++combo[i - 1];
        for (std::size_t j = i; j < half; ++j) combo[j] = combo[j - 1] + 1;
    }
    out.n_combinations = static_cast<long long>(out.logits.size());
    out.pbo = static_cast<double>(bad) / static_cast<double>(out.n_combinations);
    return out;
}

}  // namespace quantforge::research
