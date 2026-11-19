#include "quantforge/core/adaptive_exec.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <string>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge::execution {
namespace {

[[noreturn]] void input(const std::string& field, const std::string& why) {
    throw Error("E_INPUT", field + ": " + why, field);
}
[[noreturn]] void domain(const std::string& field, const std::string& why) {
    throw Error("E_DOMAIN", field + ": " + why, field);
}

double sign(Side s) { return s == Side::Buy ? 1.0 : -1.0; }

// HR-59, HR-62: floor(x + 1/2). HR-121: x + 1/2 within 1e-12 relative of an integer is that integer, so an
// exact half that binary64 lands just below still rounds up.
double half_up(double x) {
    const double t = x + 0.5;
    const double near = std::rint(t);
    return std::fabs(t - near) <= 1e-12 * std::fabs(near) ? near : std::floor(t);
}

void buckets(long long n) {
    if (n < 1) input("n_buckets", "must be at least 1");
}

// HR-2, HR-3: the order is positive, and a whole number of units in UNITS mode.
void quantity(double x, Mode mode) {
    if (!(x > 0)) input("quantity", "must be positive");
    if (mode == Mode::Units && x != std::floor(x)) input("quantity", "must be a whole number of units in UNITS mode");
}

// cosh(a) / sinh(b) for 0 <= a <= b, b > 0, without overflow.
double cosh_over_sinh(double a, double b) {
    if (b <= 700.0) return std::cosh(a) / std::sinh(b);
    return std::exp(a - b) * (1.0 + std::exp(-2.0 * a)) / (-std::expm1(-2.0 * b));
}

Vec cumulative(const Vec& xs) {
    Vec out(xs.size());
    double c = 0;
    for (std::size_t i = 0; i < xs.size(); ++i) out[i] = c += xs[i];
    return out;
}

bool inside(bool buy, double price, double limit) { return buy ? price <= limit : price >= limit; }

}  // namespace

Vec largest_remainder(double x, const Vec& exact) {
    const std::size_t n = exact.size();
    Vec floors(n), rem(n);
    long long sum = 0;
    for (std::size_t i = 0; i < n; ++i) {
        floors[i] = std::floor(exact[i]);
        rem[i] = exact[i] - floors[i];
        sum += (long long)floors[i];
    }
    const long long short_by = (long long)x - sum;
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::ranges::stable_sort(order, [&](std::size_t a, std::size_t b) { return rem[a] > rem[b]; });
    for (long long k = 0; k < short_by && (std::size_t)k < n; ++k) floors[order[(std::size_t)k]] += 1;
    for (long long k = 0; k < -short_by && (std::size_t)k < n; ++k) floors[order[n - 1 - (std::size_t)k]] -= 1;
    return floors;
}

// ---- adaptive-algos.md ----

// x_j = X sinh(k (N - j)) / sinh(k N) ([AC00] eq. (17)); kappa = 0 is TWAP in both modes (HR-59, HR-67).
Vec algo_arrival(double x, long long n, double k, Mode mode) {
    buckets(n);
    quantity(x, mode);
    if (k < 0) domain("urgency", "must be non-negative");
    if (k == 0) return twap(x, n, mode);
    // n_j = x_{j-1} - x_j = X 2 sinh(k/2) cosh(k (N - j + 1/2)) / sinh(k N): strictly decreasing, no cancellation.
    const double h = 2.0 * std::sinh(0.5 * k);
    Vec exact((std::size_t)n);
    for (long long j = 1; j <= n; ++j)
        exact[(std::size_t)(j - 1)] = x * h * cosh_over_sinh(k * ((double)(n - j) + 0.5), k * (double)n);
    return mode == Mode::Units ? largest_remainder(x, exact) : exact;
}

// Auction min(X, p_c V_c) (UNITS floors p_c V_c); the rest as exec.schedule.vwap (HR-60).
Close algo_close(double x, double v, double p, const Vec& w, Mode mode) {
    quantity(x, mode);
    if (w.empty()) input("profile", "must not be empty");
    if (!(p >= 0 && p <= 1)) domain("auction_participation", "must lie in [0, 1]");
    if (v < 0) domain("close_volume", "must be non-negative");
    double total = 0;
    for (const double wi : w) {
        if (wi < 0) domain("profile", "weights must be non-negative");
        total += wi;
    }
    double cap = p * v;
    if (mode == Mode::Units) {
        const double near = std::rint(cap);  // within 1e-12 relative of an integer: snap before flooring
        cap = std::fabs(cap - near) <= 1e-12 * std::fabs(near) ? near : std::floor(cap);
    }
    const double auction = std::min(x, cap);
    const double rest = x - auction;
    if (rest <= 0) return {auction, Vec(w.size(), 0.0)};
    if (total == 0) domain("profile", "is all zero with a remainder to place");
    return {auction, vwap(rest, w, mode)};
}

// Child min(R, alpha A_i), walking the levels inside the limit best first (HR-61).
Seek algo_liquidity_seek(Side side, double x, double limit, double alpha, const std::vector<Book>& books) {
    const bool buy = side == Side::Buy;
    if (books.empty()) input("books", "must not be empty");
    if (!(x > 0)) input("quantity", "must be positive");
    for (std::size_t i = 0; i < books.size(); ++i) {
        const Book& b = books[i];
        for (std::size_t k = 0; k < b.size(); ++k) {
            const std::string path = "books/" + std::to_string(i) + "/" + std::to_string(k);
            if (!(b[k][1] > 0)) input(path, "level sizes must be positive");
            if (k > 0 && !(buy ? b[k][0] > b[k - 1][0] : b[k][0] < b[k - 1][0]))
                input(path, "levels must be strictly ordered best first (asks ascending, bids descending)");
        }
    }
    if (!(alpha > 0 && alpha <= 1)) domain("take_fraction", "must lie in (0, 1]");
    if (!(limit > 0)) domain("limit_price", "must be positive");
    for (std::size_t i = 0; i < books.size(); ++i)
        for (std::size_t k = 0; k < books[i].size(); ++k)
            if (!(books[i][k][0] > 0))
                domain("books/" + std::to_string(i) + "/" + std::to_string(k), "level prices must be positive");
    Seek r{Vec(books.size()), std::vector<std::optional<double>>(books.size()), 0.0, x, 0.0, std::nullopt};
    for (std::size_t i = 0; i < books.size(); ++i) {
        double depth = 0;
        for (const Level& l : books[i])
            if (inside(buy, l[0], limit)) depth += l[1];
        const double child = std::min(r.residual, alpha * depth);
        double left = child, paid = 0;
        for (const Level& l : books[i]) {
            if (!inside(buy, l[0], limit)) continue;
            if (left <= 0) break;
            const double take = std::min(left, l[1]);
            paid += take * l[0];
            left -= take;
        }
        r.slices[i] = child;
        if (child > 0) r.avg_prices[i] = paid / child;
        r.residual -= child;
        r.filled += child;
        r.notional += paid;
    }
    if (r.filled > 0) r.avg_fill_price = r.notional / r.filled;
    return r;
}

// Leg A TWAP; leg B follows r C^A_j, rounded half up in UNITS (HR-62).
Pair algo_pair(Side sa, double qa, double pa, Side sb, double pb, PairMode pm, std::optional<double> h, long long n,
               Mode mode) {
    buckets(n);
    quantity(qa, mode);
    if (pm == PairMode::CashBalanced && sa == sb) input("leg_b", "a cash-balanced pair needs opposite sides");
    if (pm == PairMode::Hedged && !h) input("hedge_ratio", "HEDGED needs hedge_ratio");
    if (!(pa > 0) || !(pb > 0)) domain(pa > 0 ? "leg_b" : "leg_a", "prices must be positive");
    if (pm == PairMode::Hedged && !(*h > 0)) domain("hedge_ratio", "must be positive");
    Pair r{twap(qa, n, mode), {}, 0.0, {}};
    const Vec cum_a = cumulative(r.slices_a);
    const std::size_t m = cum_a.size();
    r.slices_b.resize(m);
    r.cash_imbalance.resize(m);
    double prev = 0;
    for (std::size_t j = 0; j < m; ++j) {
        // P_A C first: C_B P_B stays within ulps of C_A P_A
        const double target = pm == PairMode::Hedged ? *h * cum_a[j] : cum_a[j] * pa / pb;
        const double cb = mode == Mode::Units ? half_up(target) : target;
        r.slices_b[j] = cb - prev;
        prev = cb;
        r.cash_imbalance[j] = sign(sa) * cum_a[j] * pa + sign(sb) * cb * pb;
    }
    r.quantity_b = prev;
    return r;
}

// Every leg TWAP-sliced (HR-3); per-bucket cash imbalance and gross notional, no re-balancing (HR-63).
Basket algo_basket(const std::vector<Leg>& legs, long long n, Mode mode) {
    if (legs.empty()) input("legs", "must not be empty");
    buckets(n);
    for (const Leg& g : legs) quantity(g.quantity, mode);
    for (const Leg& g : legs)
        if (!(g.price > 0)) domain("legs", "prices must be positive");
    Basket r{{}, Vec((std::size_t)n, 0.0), 0.0};
    std::vector<Vec> cums;
    for (const Leg& g : legs) {
        r.slices.push_back(twap(g.quantity, n, mode));
        cums.push_back(cumulative(r.slices.back()));
        r.gross_notional += g.quantity * g.price;
    }
    for (std::size_t j = 0; j < (std::size_t)n; ++j) {
        double c = 0;
        for (std::size_t k = 0; k < legs.size(); ++k) c += sign(legs[k].side) * cums[k][j] * legs[k].price;
        r.cash_imbalance[j] = c;
    }
    return r;
}

// ---- tca-pretrade.md ----

// I* = a1 (X/adv)^a2 sigma^a3; impact = b1 I* p^a4 + (1 - b1) I*; timing risk beside the cost, never added (HR-64).
Pretrade tca_pretrade(double x, double adv, double sigma, double p, double hs, const PretradeParams& k,
                      std::optional<double> price) {
    if (!(x > 0)) input("quantity", "must be positive");
    if (!(adv > 0)) domain("adv", "must be positive");
    if (sigma < 0) domain("daily_vol", "must be non-negative");
    if (!(p > 0 && p < 1)) domain("participation", "must lie in (0, 1)");
    if (hs < 0) domain("half_spread_bps", "must be non-negative");
    if (!(k.a1 > 0)) domain("params", "a1 must be positive");
    if (!(k.b1 >= 0 && k.b1 <= 1)) domain("params", "b1 must lie in [0, 1]");
    if (price && !(*price > 0)) domain("price", "must be positive");
    if (sigma == 0 && k.a3 <= 0) domain("daily_vol", "0 to a non-positive power");
    const double istar = k.a1 * std::pow(x / adv, k.a2) * std::pow(sigma, k.a3);
    const double impact = k.b1 * istar * std::pow(p, k.a4) + (1.0 - k.b1) * istar;
    const double cost = hs + impact;
    const double duration = x / (p * adv);
    const double timing = 1e4 * sigma * std::sqrt(duration / 3.0);
    Pretrade r{istar, impact, hs, cost, duration, timing, std::nullopt, std::nullopt};
    if (price) {
        r.expected_cost = cost * x * *price / 1e4;
        r.timing_risk = timing * x * *price / 1e4;
    }
    return r;
}

// Delay, impact and spread on executed quantity; opportunity and fees as HR-8 (HR-65).
Attribution tca_attribution(Side side, double pd, double m0, double pc, double x, const std::vector<AttrFill>& fills,
                            double fees) {
    const double s = sign(side);
    if (!(x > 0)) input("order_quantity", "must be positive");
    for (const AttrFill& f : fills)
        if (!(f.quantity > 0)) input("fills", "fill quantities must be positive");
    double filled = 0;
    for (const AttrFill& f : fills) filled += f.quantity;
    if (filled > x) input("fills", "fills add up to more than the order");
    if (!(pd > 0)) domain("decision_price", "prices and mids must be positive");
    if (!(m0 > 0)) domain("arrival_mid", "prices and mids must be positive");
    if (!(pc > 0)) domain("end_price", "prices and mids must be positive");
    for (const AttrFill& f : fills)
        if (!(f.price > 0) || !(f.mid > 0)) domain("fills", "prices and mids must be positive");
    double imp = 0, spr = 0;
    for (const AttrFill& f : fills) {
        imp += f.quantity * (f.mid - m0);
        spr += f.quantity * (f.price - f.mid);
    }
    // + 0.0 turns the -0 of a SELL into +0
    const double delay = s * filled * (m0 - pd) + 0.0;
    const double impact = s * imp + 0.0;
    const double spread = s * spr + 0.0;
    const double opportunity = s * (x - filled) * (pc - pd) + 0.0;
    const double total = delay + impact + spread + opportunity + fees;
    return {delay, impact, spread, impact + spread, opportunity, fees, total, total / (x * pd) * 1e4};
}

}  // namespace quantforge::execution
