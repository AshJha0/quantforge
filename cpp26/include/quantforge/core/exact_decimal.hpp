#pragma once
// Exact decimals for the stage H wave 2 decimal-string operations (HR-12): a 128-bit integer mantissa and a
// base-10 scale, value = mantissa * 10^-scale. No floating point touches a price, a quantity or a fee.
// Arithmetic is checked: a value outside the HR-57 range (36 digits, 36 decimals) throws E_LIMIT, never rounds.
#include <compare>
#include <string>
#include <string_view>

namespace quantforge {

class ExactDecimal {
public:
    __extension__ using Int = __int128;

    ExactDecimal() = default;
    static ExactDecimal integer(long long v) { return ExactDecimal(Int(v), 0); }
    /// True when `text` matches -?[0-9]+(\.[0-9]+)? (the contract's decimal-string form).
    static bool well_formed(std::string_view text);
    /// The text must be well formed. Throws E_LIMIT above 36 digits or 18 decimals (HR-57).
    static ExactDecimal parse(std::string_view text);

    friend ExactDecimal operator+(ExactDecimal a, ExactDecimal b);
    friend ExactDecimal operator-(ExactDecimal a, ExactDecimal b);
    friend ExactDecimal operator*(ExactDecimal a, ExactDecimal b);
    ExactDecimal operator-() const { return ExactDecimal(-m_, s_); }
    ExactDecimal& operator+=(ExactDecimal b) { return *this = *this + b; }
    ExactDecimal& operator-=(ExactDecimal b) { return *this = *this - b; }
    friend std::strong_ordering operator<=>(ExactDecimal a, ExactDecimal b);
    friend bool operator==(ExactDecimal a, ExactDecimal b) { return (a <=> b) == 0; }

    int sign() const { return m_ > 0 ? 1 : (m_ < 0 ? -1 : 0); }
    /// Is this an integer multiple of `unit` (unit != 0)?
    bool multiple_of(ExactDecimal unit) const;
    /// floor(this / d) (down) or ceil(this / d) (up) as an exact integer; d > 0.
    ExactDecimal divide_integral(ExactDecimal d, bool up) const;
    /// Exactly `places` decimals, or nullopt-like failure: returns false when digits beyond `places` are non-zero.
    bool fixed(int places, std::string& out) const;
    /// No exponent, no trailing zeros, "0" for zero (HR-12).
    std::string str() const;

private:
    ExactDecimal(Int m, int s);
    Int m_ = 0;
    int s_ = 0;  // 0..36 after normalisation
};

}  // namespace quantforge
