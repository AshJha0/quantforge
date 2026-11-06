#pragma once
// Dates are days since 1970-01-01 in the proleptic Gregorian calendar.
#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace quantforge {

using Date = std::chrono::sys_days;

Date make_date(int y, unsigned m, unsigned d);
int year_of(Date d);
unsigned month_of(Date d);
unsigned day_of(Date d);
bool is_leap(int y);
int days_in_year(int y);
Date last_of_month(int y, unsigned m);
/// 0 = Sunday .. 6 = Saturday.
unsigned weekday_of(Date d);
int days_between(Date a, Date b);

std::optional<Date> parse_date(std::string_view text);
std::string format_date(Date d);

/// Seconds since 1970-01-01T00:00:00Z.
using Instant = std::int64_t;
std::optional<Instant> parse_instant(std::string_view rfc3339);
/// Wall-clock seconds, read as if UTC.
std::optional<std::int64_t> parse_local(std::string_view text);
std::string format_local(std::int64_t seconds);
Date date_of_seconds(std::int64_t seconds);

}  // namespace quantforge
