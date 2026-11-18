// Stage H H-4b microstructure estimators and H-16 venue analytics; see micro_est.hpp. Ports of the Python build's
// micro_est.py and venue_analytics.py (as the Java build ports them).
#include "quantforge/core/micro_est.hpp"

#include <algorithm>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <set>
#include <stdexcept>

#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::micro_est {
namespace {

using Vec = std::vector<double>;
using research::fsum;

[[noreturn]] void fail(const char* code, const std::string& message, const std::string& field) {
    throw Error(code, message, field);
}

double dn(std::size_t n) { return static_cast<double>(n); }

// OLS with intercept: the slope and its SE with n - 2 degrees of freedom.
Estimate ols_slope(const Vec& t, const Vec& y, const char* field) {
    const std::size_t n = t.size();
    const double tm = fsum(t) / dn(n), ym = fsum(y) / dn(n);
    Vec w(n);
    for (std::size_t i = 0; i < n; ++i) w[i] = (t[i] - tm) * (t[i] - tm);
    const double stt = fsum(w);
    if (stt == 0) fail("E_INPUT", "all abscissae are equal", field);
    for (std::size_t i = 0; i < n; ++i) w[i] = (t[i] - tm) * (y[i] - ym);
    const double slope = fsum(w) / stt;
    const double icpt = ym - slope * tm;
    for (std::size_t i = 0; i < n; ++i) {
        const double r = y[i] - icpt - slope * t[i];
        w[i] = r * r;
    }
    return {slope, std::sqrt(fsum(w) / dn(n - 2) / stt)};
}

std::pair<double, double> mean_var(const Vec& v) {
    const double m = fsum(v) / dn(v.size());
    Vec d(v.size());
    for (std::size_t i = 0; i < v.size(); ++i) d[i] = (v[i] - m) * (v[i] - m);
    return {m, fsum(d) / dn(v.size() - 1)};
}

}  // namespace

bool CodePointLess::operator()(std::string_view a, std::string_view b) const {
    // UTF-8 byte order is code-point order.
    return std::lexicographical_compare(a.begin(), a.end(), b.begin(), b.end(), [](char x, char y) {
        return static_cast<unsigned char>(x) < static_cast<unsigned char>(y);
    });
}

Estimate ols_origin(const Vec& x, const Vec& y, const std::string& field) {
    if (x.size() != y.size() || x.size() < 2) fail("E_INPUT", "x and y need equal lengths of at least 2", field);
    const std::size_t n = x.size();
    Vec t(n);
    for (std::size_t i = 0; i < n; ++i) t[i] = x[i] * x[i];
    const double sxx = fsum(t);
    if (sxx == 0) fail("E_INPUT", "the sum of x^2 is 0", field);
    for (std::size_t i = 0; i < n; ++i) t[i] = x[i] * y[i];
    const double beta = fsum(t) / sxx;
    for (std::size_t i = 0; i < n; ++i) {
        const double r = y[i] - beta * x[i];
        t[i] = r * r;
    }
    return {beta, std::sqrt(fsum(t) / dn(n - 1) / sxx)};
}

Estimate arrival_rate(long long count, double window) {
    if (count < 0) fail("E_DOMAIN", "count must be non-negative", "count");
    if (window <= 0) fail("E_DOMAIN", "window must be positive", "window");
    const double lam = static_cast<double>(count) / window;
    return {lam, std::sqrt(lam / window)};
}

Estimate cancel_rate(const std::vector<Order>& orders) {
    Vec life;
    long long c = 0;
    for (const Order& o : orders) {
        if (o.lifetime <= 0) fail("E_DOMAIN", "lifetimes must be positive", "orders");
        life.push_back(o.lifetime);
        c += o.cancelled ? 1 : 0;
    }
    if (c == 0) fail("E_INPUT", "no cancelled order", "orders");
    const double theta = static_cast<double>(c) / fsum(life);
    return {theta, theta / std::sqrt(static_cast<double>(c))};
}

Estimate resilience(double s_inf, const std::vector<std::pair<double, double>>& points) {
    if (points.size() < 3) fail("E_INPUT", "need at least 3 points", "points");
    for (const auto& p : points)
        if (p.second <= s_inf) fail("E_DOMAIN", "every spread must exceed s_inf", "points");
    Vec t, y;
    for (const auto& [ti, s] : points) {
        t.push_back(ti);
        y.push_back(std::log(s - s_inf));
    }
    const Estimate e = ols_slope(t, y, "points");
    return {-e.value, e.se};
}

Estimate liquidity_decay(const std::vector<std::pair<double, double>>& levels) {
    if (levels.size() < 3) fail("E_INPUT", "need at least 3 levels", "levels");
    for (const auto& p : levels)
        if (p.second <= 0) fail("E_DOMAIN", "every depth must be positive", "levels");
    Vec k, y;
    for (const auto& [ki, d] : levels) {
        k.push_back(ki);
        y.push_back(std::log(d));
    }
    const Estimate e = ols_slope(k, y, "levels");
    return {-e.value, e.se};
}

Estimate adverse_selection(const Vec& x, const Vec& y) { return ols_origin(x, y, "x"); }

RegimeImpact regime_impact(const std::map<std::string, Sample, CodePointLess>& regimes) {
    for (const char* need : {"calm", "stressed"})
        if (!regimes.contains(need)) fail("E_INPUT", std::string("regime '") + need + "' is missing", "regimes");
    for (const auto& [label, s] : regimes)
        if (s.x.size() != s.y.size() || s.x.size() < 2)
            fail("E_INPUT", "x and y need equal lengths of at least 2", "regimes." + label);
    RegimeImpact out{{}, 0.0};
    double calm = 0, stressed = 0;
    for (const auto& [label, s] : regimes) {
        const Estimate e = ols_origin(s.x, s.y, "regimes." + label);
        if (label == "calm") calm = e.value;
        if (label == "stressed") stressed = e.value;
        out.regimes.emplace_back(label, e);
    }
    if (calm == 0) fail("E_DOMAIN", "calm lambda_as is 0; the ratio is undefined", "regimes");
    out.ratio = stressed / calm;
    return out;
}

Estimate passive_vs_aggressive(const Vec& passive, const Vec& aggressive) {
    if (passive.size() < 2) fail("E_INPUT", "need at least 2 fills per class", "passive");
    if (aggressive.size() < 2) fail("E_INPUT", "need at least 2 fills per class", "aggressive");
    const auto [mp, vp] = mean_var(passive);
    const auto [ma, va] = mean_var(aggressive);
    return {ma - mp, std::sqrt(va / dn(aggressive.size()) + vp / dn(passive.size()))};
}

namespace venue {
namespace {

// A non-negative integer of any size, little-endian 32-bit limbs, no leading zero limbs.
class Nat {
public:
    Nat() = default;
    explicit Nat(std::uint64_t v) {
        while (v) {
            d_.push_back(static_cast<std::uint32_t>(v));
            v >>= 32;
        }
    }
    bool zero() const { return d_.empty(); }
    std::size_t bits() const {
        return d_.empty() ? 0 : 32 * (d_.size() - 1) + static_cast<std::size_t>(32 - std::countl_zero(d_.back()));
    }
    std::uint64_t low64() const {
        std::uint64_t v = d_.empty() ? 0 : d_[0];
        if (d_.size() > 1) v |= std::uint64_t(d_[1]) << 32;
        return v;
    }
    friend int cmp(const Nat& a, const Nat& b) {
        if (a.d_.size() != b.d_.size()) return a.d_.size() < b.d_.size() ? -1 : 1;
        for (std::size_t i = a.d_.size(); i-- > 0;)
            if (a.d_[i] != b.d_[i]) return a.d_[i] < b.d_[i] ? -1 : 1;
        return 0;
    }
    friend Nat operator+(const Nat& a, const Nat& b) {
        Nat r;
        std::uint64_t carry = 0;
        for (std::size_t i = 0; i < std::max(a.d_.size(), b.d_.size()) || carry; ++i) {
            const std::uint64_t s = carry + (i < a.d_.size() ? a.d_[i] : 0U) + (i < b.d_.size() ? b.d_[i] : 0U);
            r.d_.push_back(static_cast<std::uint32_t>(s));
            carry = s >> 32;
        }
        return r;
    }
    // a - b for a >= b.
    friend Nat operator-(const Nat& a, const Nat& b) {
        Nat r;
        std::int64_t borrow = 0;
        for (std::size_t i = 0; i < a.d_.size(); ++i) {
            std::int64_t s = std::int64_t(a.d_[i]) - borrow - (i < b.d_.size() ? std::int64_t(b.d_[i]) : 0);
            borrow = s < 0 ? 1 : 0;
            if (s < 0) s += std::int64_t(1) << 32;
            r.d_.push_back(static_cast<std::uint32_t>(s));
        }
        r.trim();
        return r;
    }
    friend Nat operator*(const Nat& a, const Nat& b) {
        if (a.zero() || b.zero()) return {};
        Nat r;
        r.d_.assign(a.d_.size() + b.d_.size(), 0);
        for (std::size_t i = 0; i < a.d_.size(); ++i) {
            std::uint64_t carry = 0;
            for (std::size_t j = 0; j < b.d_.size() || carry; ++j) {
                const std::uint64_t cur =
                    r.d_[i + j] + carry + (j < b.d_.size() ? std::uint64_t(a.d_[i]) * b.d_[j] : 0U);
                r.d_[i + j] = static_cast<std::uint32_t>(cur);
                carry = cur >> 32;
            }
        }
        r.trim();
        return r;
    }
    Nat shl(std::size_t k) const {
        if (zero()) return {};
        Nat r;
        r.d_.assign(k / 32, 0);
        const auto s = static_cast<unsigned>(k % 32);
        std::uint32_t carry = 0;
        for (const std::uint32_t x : d_) {
            r.d_.push_back(s ? (x << s) | carry : x);
            carry = s ? x >> (32 - s) : 0;
        }
        if (carry) r.d_.push_back(carry);
        return r;
    }
    static Nat pow10(std::size_t k) {
        Nat r(1), ten(10);
        for (std::size_t i = 0; i < k; ++i) r = r * ten;
        return r;
    }

private:
    void trim() {
        while (!d_.empty() && d_.back() == 0) d_.pop_back();
    }
    std::vector<std::uint32_t> d_;
};

// sign * mag * 10^exp, exactly.
struct Dec {
    int sign = 0;
    Nat mag;
    int exp = 0;
};

Dec from_digits(std::string_view text) {
    Dec d;
    bool neg = false;
    std::size_t i = 0;
    if (i < text.size() && (text[i] == '-' || text[i] == '+')) neg = text[i++] == '-';
    Nat ten(10);
    int frac = 0;
    bool point = false;
    for (; i < text.size() && text[i] != 'e' && text[i] != 'E'; ++i) {
        if (text[i] == '.') {
            point = true;
            continue;
        }
        d.mag = d.mag * ten + Nat(static_cast<std::uint64_t>(text[i] - '0'));
        if (point) ++frac;
    }
    int e = 0;
    if (i < text.size()) {
        const char* b = text.data() + i + 1;
        if (*b == '+') ++b;
        std::from_chars(b, text.data() + text.size(), e);
    }
    d.exp = e - frac;
    d.sign = d.mag.zero() ? 0 : (neg ? -1 : 1);
    return d;
}

// The decimal x prints as (shortest round trip, as Python's repr).
Dec dec(double x) {
    char buf[64];
    const auto r = std::to_chars(buf, buf + sizeof buf, x);
    return from_digits(std::string_view(buf, static_cast<std::size_t>(r.ptr - buf)));
}

// Both mantissas at the smaller exponent.
std::pair<Nat, Nat> align(const Dec& a, const Dec& b, int& e) {
    e = std::min(a.exp, b.exp);
    return {a.mag * Nat::pow10(static_cast<std::size_t>(a.exp - e)), b.mag * Nat::pow10(static_cast<std::size_t>(b.exp - e))};
}

Dec operator+(const Dec& a, const Dec& b) {
    if (a.sign == 0) return b;
    if (b.sign == 0) return a;
    Dec r;
    auto [x, y] = align(a, b, r.exp);
    if (a.sign == b.sign) {
        r.mag = x + y;
        r.sign = a.sign;
        return r;
    }
    const int c = cmp(x, y);
    if (c == 0) return {};
    r.mag = c > 0 ? x - y : y - x;
    r.sign = c > 0 ? a.sign : b.sign;
    return r;
}

Dec neg(Dec a) {
    a.sign = -a.sign;
    return a;
}

Dec operator*(const Dec& a, const Dec& b) {
    if (a.sign == 0 || b.sign == 0) return {};
    return {a.sign * b.sign, a.mag * b.mag, a.exp + b.exp};
}

int compare(const Dec& a, const Dec& b) { return (a + neg(b)).sign; }

// p / q correctly rounded to binary64, p and q positive.
double nat_ratio(const Nat& p, const Nat& q) {
    const long shift = 55 - (static_cast<long>(p.bits()) - static_cast<long>(q.bits()));
    Nat n = shift >= 0 ? p.shl(static_cast<std::size_t>(shift)) : p;
    const Nat d = shift >= 0 ? q : q.shl(static_cast<std::size_t>(-shift));
    // The quotient is below 2^56: long division bit by bit.
    std::uint64_t m = 0;
    for (int bit = 56; bit >= 0; --bit) {
        const Nat t = d.shl(static_cast<std::size_t>(bit));
        if (cmp(t, n) <= 0) {
            n = n - t;
            m |= std::uint64_t(1) << bit;
        }
    }
    if (!n.zero()) m |= 1U;  // sticky bit: the one rounding to 53 bits below is then correct
    return std::scalbn(static_cast<double>(m), static_cast<int>(-shift));
}

// a / b correctly rounded to binary64 (b non-zero), as Python's float(Fraction).
double ratio(const Dec& a, const Dec& b) {
    if (a.sign == 0) return 0.0;
    Nat p = a.mag, q = b.mag;
    if (a.exp > b.exp) p = p * Nat::pow10(static_cast<std::size_t>(a.exp - b.exp));
    else if (b.exp > a.exp) q = q * Nat::pow10(static_cast<std::size_t>(b.exp - a.exp));
    const double v = nat_ratio(p, q);
    return a.sign * b.sign < 0 ? -v : v;
}

// The last mid stamped at or before u (bisect_right).
const Dec& mid_at(const std::vector<Dec>& times, const std::vector<Dec>& values, const Dec& u) {
    std::size_t lo = 0, hi = times.size();
    while (lo < hi) {
        const std::size_t mid = (lo + hi) / 2;
        if (compare(u, times[mid]) < 0) hi = mid;
        else lo = mid + 1;
    }
    if (lo == 0) fail("E_INPUT", "no mid at or before a fill time plus horizon", "fills");
    return values[lo - 1];
}

}  // namespace

double exact_ratio(const std::string& a, const std::string& b) { return ratio(from_digits(a), from_digits(b)); }

Result analytics(const std::vector<std::pair<double, double>>& mids, const std::vector<Fill>& fills,
                 const std::vector<Order>& orders, const std::vector<double>& horizons) {
    // HR-75 as amended (HR-66): structural E_INPUT first, then E_DOMAIN, then the mid lookups
    for (const Order& o : orders)
        if (o.filled > o.sent) fail("E_INPUT", "filled exceeds sent", "orders");
    std::vector<Dec> times;
    for (const auto& m : mids) {
        times.push_back(dec(m.first));
        if (times.size() > 1 && compare(times.back(), times[times.size() - 2]) <= 0)
            fail("E_INPUT", "mid times must be strictly increasing", "mids");
    }
    for (const auto& m : mids)
        if (m.second <= 0) fail("E_DOMAIN", "mids must be positive", "mids");
    for (const Fill& f : fills)
        if (f.price <= 0) fail("E_DOMAIN", "fill prices must be positive", "fills");
    for (const Fill& f : fills)
        if (f.quantity <= 0) fail("E_DOMAIN", "fill quantities must be positive", "fills");
    for (const Order& o : orders)
        if (o.sent <= 0) fail("E_DOMAIN", "sent must be positive", "orders");
    for (const Order& o : orders)
        if (o.filled < 0) fail("E_DOMAIN", "filled must be non-negative", "orders");
    for (const double h : horizons)
        if (h < 0) fail("E_DOMAIN", "horizons must be non-negative", "horizons");
    std::vector<Dec> values, hs;
    for (const auto& m : mids) values.push_back(dec(m.second));
    for (const double h : horizons) hs.push_back(dec(h));
    const Dec one{1, Nat(1), 0}, bps{1, Nat(10000), 0};

    Result out;
    std::set<std::string, CodePointLess> venues;
    for (const Fill& f : fills) venues.insert(f.venue);
    struct Row {
        Dec side, q, p, t;
    };
    for (const std::string& v : venues) {
        std::vector<Row> mine;
        Dec sq, sqp;
        for (const Fill& f : fills) {
            if (f.venue != v) continue;
            const Row r{f.buy ? one : neg(one), dec(f.quantity), dec(f.price), dec(f.t)};
            sq = sq + r.q;
            sqp = sqp + r.q * r.p;
            mine.push_back(r);
        }
        for (std::size_t k = 0; k < horizons.size(); ++k) {
            Dec num, toxic;
            for (const Row& r : mine) {
                const Dec move = r.side * (mid_at(times, values, r.t + hs[k]) + neg(r.p));
                num = num + r.q * move;
                if (move.sign < 0) toxic = toxic + r.q;
            }
            out.markouts.push_back({v, horizons[k], ratio(num, sq), ratio(num * bps, sqp), ratio(toxic, sq)});
        }
    }
    std::set<std::string, CodePointLess> order_venues;
    for (const Order& o : orders) order_venues.insert(o.venue);
    for (const std::string& v : order_venues) {
        Dec sent, got;
        for (const Order& o : orders) {
            if (o.venue != v) continue;
            sent = sent + dec(o.sent);
            got = got + dec(o.filled);
        }
        out.fill_rates.emplace_back(v, ratio(got, sent));
    }
    return out;
}

}  // namespace venue

}  // namespace quantforge::micro_est
