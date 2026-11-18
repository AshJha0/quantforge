#include "quantforge/core/exact_decimal.hpp"

#include <algorithm>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

using Int = ExactDecimal::Int;
constexpr int max_scale = 36;

[[noreturn]] void out_of_range() { throw Error("E_DOMAIN", "decimal outside the exact range (30 digits, 36 decimals)"); }

Int mul(Int a, Int b) {
    Int r;
    if (__builtin_mul_overflow(a, b, &r)) out_of_range();
    return r;
}

Int pow10(int n) {
    Int r = 1;
    for (int i = 0; i < n; ++i) r = mul(r, 10);
    return r;
}

// Both mantissas at the larger scale.
void align(Int& a, int sa, Int& b, int sb, int& s) {
    s = std::max(sa, sb);
    a = mul(a, pow10(s - sa));
    b = mul(b, pow10(s - sb));
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
    if (s_ > max_scale) out_of_range();
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
    const std::string_view frac = dot == std::string_view::npos ? std::string_view{} : t.substr(dot + 1);
    std::string all(t.substr(0, dot));
    all += frac;
    const auto first = all.find_first_not_of('0');
    if (frac.size() > 18 || (first != std::string::npos && all.size() - first > 30))
        throw Error("E_DOMAIN", "decimal string above 30 significant digits or 18 decimals");
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

ExactDecimal operator*(ExactDecimal a, ExactDecimal b) { return ExactDecimal(mul(a.m_, b.m_), a.s_ + b.s_); }

std::strong_ordering operator<=>(ExactDecimal a, ExactDecimal b) {
    if (a.sign() != b.sign()) return a.sign() <=> b.sign();
    int s;
    align(a.m_, a.s_, b.m_, b.s_, s);
    return a.m_ < b.m_ ? std::strong_ordering::less : (a.m_ > b.m_ ? std::strong_ordering::greater : std::strong_ordering::equal);
}

bool ExactDecimal::multiple_of(ExactDecimal unit) const {
    Int a = m_, b = unit.m_;
    int s;
    align(a, s_, b, unit.s_, s);
    return a % b == 0;
}

ExactDecimal ExactDecimal::divide_integral(ExactDecimal d, bool up) const {
    Int a = m_, b = d.m_;
    int s;
    align(a, s_, b, d.s_, s);
    Int q = a / b;  // truncates toward zero; b > 0
    const Int r = a % b;
    if (r != 0 && up && a > 0) ++q;
    if (r != 0 && !up && a < 0) --q;
    return ExactDecimal(q, 0);
}

bool ExactDecimal::fixed(int places, std::string& out) const {
    Int m = m_;
    if (s_ > places) {
        const Int p = pow10(s_ - places);
        if (m % p != 0) return false;
        m /= p;
    } else {
        m = mul(m, pow10(places - s_));
    }
    std::string d = digits(m < 0 ? -m : m);
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
