#include "quantforge/core/money.hpp"

#include <algorithm>

namespace quantforge {
namespace {

constexpr int scale_digits = 8;

double per_decimal(RateUnit u) {
    switch (u) {
        case RateUnit::Decimal: return 1.0;
        case RateUnit::Percent: return 100.0;
        case RateUnit::Bp: return 10000.0;
    }
    return 1.0;
}

bool digit(char c) { return c >= '0' && c <= '9'; }

Fixed power10(int n) {
    Fixed p = 1;
    for (int i = 0; i < n; ++i) p *= 10;
    return p;
}

std::string digits_of(Fixed v) {
    std::string s;
    do {
        s += char('0' + int(v % 10));
        v /= 10;
    } while (v != 0);
    std::ranges::reverse(s);
    return s;
}

}  // namespace

double convert_unit(double value, RateUnit from, RateUnit to) {
    if (from == to) return value;
    return value / per_decimal(from) * per_decimal(to);
}

AmountForm classify_amount(std::string_view s) {
    if (!s.empty() && s[0] == '-') s.remove_prefix(1);
    const auto dot = s.find('.');
    const auto whole = s.substr(0, dot);
    const auto fraction = dot == std::string_view::npos ? std::string_view{} : s.substr(dot + 1);
    if (whole.empty() || !std::ranges::all_of(whole, digit) || !std::ranges::all_of(fraction, digit) ||
        (dot != std::string_view::npos && fraction.empty()))
        return AmountForm::Malformed;
    return whole.size() > 18 || fraction.size() > 8 ? AmountForm::TooManyDigits : AmountForm::Valid;
}

Fixed parse_amount(std::string_view s) {
    const bool negative = !s.empty() && s[0] == '-';
    if (negative) s.remove_prefix(1);
    Fixed v = 0;
    int fraction = -1;
    for (const char c : s) {
        if (c == '.') {
            fraction = 0;
            continue;
        }
        v = v * 10 + (c - '0');
        if (fraction >= 0) ++fraction;
    }
    v *= power10(scale_digits - std::max(fraction, 0));
    return negative ? -v : v;
}

int minor_units(std::string_view c) {
    if (c == "GBP" || c == "USD" || c == "EUR") return 2;
    if (c == "JPY") return 0;
    return -1;
}

std::string format_shortest(Fixed v) {
    const bool negative = v < 0;
    const Fixed a = negative ? -v : v;
    std::string s = digits_of(a / power10(scale_digits));
    std::string fraction = digits_of(a % power10(scale_digits));
    fraction.insert(0, std::size_t(scale_digits) - fraction.size(), '0');
    while (!fraction.empty() && fraction.back() == '0') fraction.pop_back();
    if (!fraction.empty()) s += "." + fraction;
    return negative ? "-" + s : s;
}

std::string round_to_places(Fixed v, int places) {
    const bool negative = v < 0;
    const Fixed a = negative ? -v : v, unit = power10(scale_digits - places);
    Fixed q = a / unit;
    const Fixed rest = a % unit;
    if (rest * 2 > unit || (rest * 2 == unit && q % 2 == 1)) ++q;
    std::string s = digits_of(q / power10(places));
    if (places > 0) {
        std::string fraction = digits_of(q % power10(places));
        fraction.insert(0, std::size_t(places) - fraction.size(), '0');
        s += "." + fraction;
    }
    return negative && q != 0 ? "-" + s : s;
}

}  // namespace quantforge
