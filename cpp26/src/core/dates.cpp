#include "quantforge/core/dates.hpp"

#include <cstdio>

using namespace std::chrono;

namespace quantforge {
namespace {

year_month_day ymd(Date d) { return year_month_day{d}; }

// Reads exactly n digits at pos; -1 if any is not a digit.
int digits(std::string_view s, std::size_t pos, std::size_t n) {
    int v = 0;
    for (std::size_t i = pos; i < pos + n; ++i) {
        if (s[i] < '0' || s[i] > '9') return -1;
        v = v * 10 + (s[i] - '0');
    }
    return v;
}

// The fixed form YYYY-MM-DDTHH:MM:SS, as seconds.
std::optional<std::int64_t> parse_date_time(std::string_view s) {
    if (s.size() != 19 || s[10] != 'T' || s[13] != ':' || s[16] != ':') return std::nullopt;
    const auto d = parse_date(s.substr(0, 10));
    const int h = digits(s, 11, 2), m = digits(s, 14, 2), sec = digits(s, 17, 2);
    if (!d || h < 0 || h > 23 || m < 0 || m > 59 || sec < 0 || sec > 59) return std::nullopt;
    return std::int64_t{d->time_since_epoch().count()} * 86400 + h * 3600 + m * 60 + sec;
}

}  // namespace

Date make_date(int y, unsigned m, unsigned d) { return Date{year{y} / month{m} / day{d}}; }
int year_of(Date d) { return int(ymd(d).year()); }
unsigned month_of(Date d) { return unsigned(ymd(d).month()); }
unsigned day_of(Date d) { return unsigned(ymd(d).day()); }
bool is_leap(int y) { return year{y}.is_leap(); }
int days_in_year(int y) { return is_leap(y) ? 366 : 365; }
Date last_of_month(int y, unsigned m) { return Date{year{y} / month{m} / last}; }
unsigned weekday_of(Date d) { return weekday{d}.c_encoding(); }
int days_between(Date a, Date b) { return static_cast<int>((b - a).count()); }

std::optional<Date> parse_date(std::string_view s) {
    if (s.size() != 10 || s[4] != '-' || s[7] != '-') return std::nullopt;
    const int y = digits(s, 0, 4), m = digits(s, 5, 2), d = digits(s, 8, 2);
    if (y < 0 || m < 0 || d < 0) return std::nullopt;
    const year_month_day v{year{y}, month{unsigned(m)}, day{unsigned(d)}};
    if (!v.ok()) return std::nullopt;
    return Date{v};
}

std::string format_date(Date d) {
    char b[32];
    std::snprintf(b, sizeof b, "%04d-%02u-%02u", year_of(d), month_of(d), day_of(d));
    return b;
}

std::optional<Instant> parse_instant(std::string_view s) {
    if (s.size() < 20) return std::nullopt;
    const auto base = parse_date_time(s.substr(0, 19));
    if (!base) return std::nullopt;
    const auto zone = s.substr(19);
    if (zone == "Z") return base;
    if (zone.size() != 6 || (zone[0] != '+' && zone[0] != '-') || zone[3] != ':') return std::nullopt;
    const int h = digits(zone, 1, 2), m = digits(zone, 4, 2);
    if (h < 0 || h > 23 || m < 0 || m > 59) return std::nullopt;
    const std::int64_t offset = h * 3600 + m * 60;
    return zone[0] == '+' ? *base - offset : *base + offset;
}

std::optional<std::int64_t> parse_local(std::string_view s) { return parse_date_time(s); }

Date date_of_seconds(std::int64_t s) {
    std::int64_t n = s / 86400;
    if (s % 86400 < 0) --n;
    return Date{days{n}};
}

std::string format_local(std::int64_t s) {
    const Date d = date_of_seconds(s);
    const std::int64_t tod = s - std::int64_t{d.time_since_epoch().count()} * 86400;
    char b[48];
    std::snprintf(b, sizeof b, "%sT%02d:%02d:%02d", format_date(d).c_str(), int(tod / 3600), int(tod / 60 % 60),
                  int(tod % 60));
    return b;
}

}  // namespace quantforge
