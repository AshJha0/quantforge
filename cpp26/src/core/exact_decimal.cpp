#include "quantforge/core/exact_decimal.hpp"

#include <algorithm>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

using Int = ExactDecimal::Int;
// HR-57: a value c * 10^-s (s >= 0 and minimal) is in range when |c| < 10^36 and s <= 36; an input
// string also needs s <= 18. Anything else is E_LIMIT (HR-58), never a rounded or wrapped result.
constexpr int max_digits = 36;
constexpr int max_scale = 36;
constexpr int max_input_scale = 18;

[[noreturn]] void out_of_range() {
    throw Error("E_LIMIT", "decimal outside the exact range (36 digits, 36 decimals; HR-57)");
}

bool mul_ok(Int a, Int b, Int& r) { return !__builtin_mul_overflow(a, b, &r); }

Int mul(Int a, Int b) {
    Int r;
    if (!mul_ok(a, b, r)) out_of_range();
    return r;
}

Int pow10(int n) {
    Int r = 1;
    for (int i = 0; i < n; ++i) r = mul(r, 10);
    return r;
}

const Int limit = pow10(max_digits);

// Both mantissas at the larger scale. An overflow here means the exact result is out of range too: the
// side scaled up is then at least 1.7e38 at the common scale while the other is below 10^36 with a
// non-zero last digit, so the sum has more than 36 digits (HR-58).
void align(Int& a, int sa, Int& b, int sb, int& s) {
    s = std::max(sa, sb);
    a = mul(a, pow10(s - sa));
    b = mul(b, pow10(s - sb));
}

// |num| * 10^up / (den * 10^down) for den > 0, up or down zero: the integer quotient of the magnitudes
// (or `q_ok` false when it reaches 10^36) and whether the remainder is non-zero. Long division keeps
// every intermediate below 10^37, so in-range operands never overflow.
bool div_mag(Int num, int up, Int den, int down, Int& q, bool& q_ok) {
    if (num < 0) num = -num;
    Int d = den;
    for (int i = 0; i < down; ++i) {
        if (!mul_ok(d, 10, d)) {  // the divisor exceeds |num|: quotient 0
            q = 0;
            q_ok = true;
            return num != 0;
        }
    }
    q = num / d;
    Int r = num % d;
    q_ok = q < limit;
    for (int i = 0; i < up; ++i) {
        r *= 10;
        if (q_ok) {
            q = q * 10 + r / d;
            q_ok = q < limit;
        }
        r %= d;
    }
    return r != 0;
}

std::string digits(Int v) {  // v >= 0
    std::string s;
    do {
        s.push_back(char('0' + int(v % 10)));
        v /= 10;
    } while (v != 0);
    std::reverse(s.begin(), s.end());
    return s;
}

}  // namespace

ExactDecimal::ExactDecimal(Int m, int s) : m_(m), s_(s) {
    while (s_ > 0 && m_ % 10 == 0) {
        m_ /= 10;
        --s_;
    }
    if (s_ > max_scale || m_ >= limit || m_ <= -limit) out_of_range();
}

bool ExactDecimal::well_formed(std::string_view t) {
    std::size_t i = 0;
    if (i < t.size() && t[i] == '-') ++i;
    const auto run = [&] {
        const std::size_t start = i;
        while (i < t.size() && t[i] >= '0' && t[i] <= '9') ++i;
        return i > start;
    };
    if (!run()) return false;
    if (i == t.size()) return true;
    if (t[i] != '.') return false;
    ++i;
    return run() && i == t.size();
}

ExactDecimal ExactDecimal::parse(std::string_view t) {
    const bool negative = !t.empty() && t[0] == '-';
    if (negative) t.remove_prefix(1);
    const auto dot = t.find('.');
    std::string_view ip = t.substr(0, dot);
    std::string_view frac = dot == std::string_view::npos ? std::string_view{} : t.substr(dot + 1);
    while (!frac.empty() && frac.back() == '0') frac.remove_suffix(1);
    while (!ip.empty() && ip.front() == '0') ip.remove_prefix(1);
    std::string all(ip);
    all += frac;
    const auto first = all.find_first_not_of('0');
    if (frac.size() > max_input_scale || (first != std::string::npos && all.size() - first > max_digits))
        throw Error("E_LIMIT", "decimal string outside the input range (36 digits, 18 decimals; HR-57)");
    Int m = 0;
    for (const char c : all) m = m * 10 + (c - '0');
    return ExactDecimal(negative ? -m : m, int(frac.size()));
}

ExactDecimal operator+(ExactDecimal a, ExactDecimal b) {
    int s;
    align(a.m_, a.s_, b.m_, b.s_, s);
    Int r;
    if (__builtin_add_overflow(a.m_, b.m_, &r)) out_of_range();
    return ExactDecimal(r, s);
}

ExactDecimal operator-(ExactDecimal a, ExactDecimal b) { return a + (-b); }

ExactDecimal operator*(ExactDecimal a, ExactDecimal b) {
    Int x = a.m_, y = b.m_, r;
    int s = a.s_ + b.s_;
    // A product that overflows may still be in range once its trailing zeros go: cancel factors of ten
    // (a 5 from one side with a 2 from the other) while the scale allows (HR-58).
    while (!mul_ok(x, y, r) && s > 0) {
        if (x % 10 == 0) x /= 10;
        else if (y % 10 == 0) y /= 10;
        else if (x % 5 == 0 && y % 2 == 0) x /= 5, y /= 2;
        else if (x % 2 == 0 && y % 5 == 0) x /= 2, y /= 5;
        else out_of_range();
        --s;
    }
    return ExactDecimal(mul(x, y), s);
}

std::strong_ordering operator<=>(ExactDecimal a, ExactDecimal b) {
    if (a.sign() != b.sign()) return a.sign() <=> b.sign();
    const int s = std::max(a.s_, b.s_);
    Int x, y;
    const bool okx = mul_ok(a.m_, pow10(s - a.s_), x);
    const bool oky = mul_ok(b.m_, pow10(s - b.s_), y);
    // Only the side scaled up can overflow, and it then dominates in magnitude.
    if (!okx) return a.sign() > 0 ? std::strong_ordering::greater : std::strong_ordering::less;
    if (!oky) return b.sign() > 0 ? std::strong_ordering::less : std::strong_ordering::greater;
    return x < y ? std::strong_ordering::less : (x > y ? std::strong_ordering::greater : std::strong_ordering::equal);
}

bool ExactDecimal::multiple_of(ExactDecimal unit) const {
    Int q;
    bool q_ok;
    const Int den = unit.m_ < 0 ? -unit.m_ : unit.m_;
    return !div_mag(m_, std::max(unit.s_ - s_, 0), den, std::max(s_ - unit.s_, 0), q, q_ok);
}

ExactDecimal ExactDecimal::divide_integral(ExactDecimal d, bool up) const {
    Int q;
    bool q_ok;
    const bool rem = div_mag(m_, std::max(d.s_ - s_, 0), d.m_, std::max(s_ - d.s_, 0), q, q_ok);
    if (!q_ok) out_of_range();
    if (m_ < 0) q = -q;
    if (rem && up && m_ > 0) ++q;
    if (rem && !up && m_ < 0) --q;
    return ExactDecimal(q, 0);
}

bool ExactDecimal::fixed(int places, std::string& out) const {
    Int m = m_;
    int s = s_;
    if (s > places) {
        const Int p = pow10(s - places);
        if (m % p != 0) return false;
        m /= p;
        s = places;
    }
    std::string d = digits(m < 0 ? -m : m) + std::string(std::size_t(places - s), '0');
    if ((int)d.size() <= places) d.insert(0, std::size_t(places + 1) - d.size(), '0');
    out = m < 0 ? "-" : "";
    out += d.substr(0, d.size() - std::size_t(places));
    if (places > 0) out += "." + d.substr(d.size() - std::size_t(places));
    return true;
}

std::string ExactDecimal::str() const {
    std::string out;
    fixed(s_, out);
    return out;
}

}  // namespace quantforge
