#pragma once
// Exact money and the unit conversions of specifications/01-core/units-and-money.md.
#include <string>
#include <string_view>

namespace quantforge {

enum class RateUnit { Decimal, Percent, Bp };

double convert_unit(double value, RateUnit from, RateUnit to);

/// 128-bit fixed point, in units of 1e-8. 18 + 8 digits use under 2^90.
__extension__ using Fixed = __int128;

enum class AmountForm { Valid, TooManyDigits, Malformed };
AmountForm classify_amount(std::string_view text);
/// The text must be Valid.
Fixed parse_amount(std::string_view text);

/// Minor-unit places, or -1 for an unknown currency.
int minor_units(std::string_view currency);

/// Shortest form: no trailing zeros, no -0.
std::string format_shortest(Fixed v);
/// Rounds half to even and writes exactly `places` decimals.
std::string round_to_places(Fixed v, int places);

}  // namespace quantforge
