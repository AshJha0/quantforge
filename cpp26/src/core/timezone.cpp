#include "quantforge/core/timezone.hpp"

#include "quantforge/core/error.hpp"

using namespace std::chrono;

namespace quantforge {
namespace {

constexpr long long hour = 3600;

long long seconds_at(Date d, long long hours) { return (long long)d.time_since_epoch().count() * 86400 + hours * hour; }

Date last_sunday(int y, unsigned m) {
    const Date end = last_of_month(y, m);
    return end - days{int(weekday_of(end))};
}

Date nth_sunday(int y, unsigned m, int n) {
    const Date first = make_date(y, m, 1);
    return first + days{int((7 - weekday_of(first)) % 7) + 7 * (n - 1)};
}

long long standard_offset(Zone z) {
    switch (z) {
        case Zone::Utc: case Zone::London: return 0;
        case Zone::Berlin: return hour;
        case Zone::NewYork: return -5 * hour;
        case Zone::Tokyo: return 9 * hour;
    }
    return 0;
}

bool has_summer(Zone z) { return z == Zone::London || z == Zone::Berlin || z == Zone::NewYork; }

bool in_summer(Zone z, Instant i) {
    if (!has_summer(z)) return false;
    const int y = year_of(date_of_seconds(i));
    if (z == Zone::NewYork) return i >= seconds_at(nth_sunday(y, 3, 2), 7) && i < seconds_at(nth_sunday(y, 11, 1), 6);
    return i >= seconds_at(last_sunday(y, 3), 1) && i < seconds_at(last_sunday(y, 10), 1);
}

long long offset_at(Zone z, Instant i) { return standard_offset(z) + (in_summer(z, i) ? hour : 0); }

void check_instant(Instant i) {
    const int y = year_of(date_of_seconds(i));
    if (y < 2007 || y > 2037) throw Error("E_DATE_RANGE", "instants must lie in 2007 to 2037", "instant");
}

}  // namespace

long long utc_offset(Zone z, Instant i) {
    check_instant(i);
    return offset_at(z, i);
}

std::string to_local(Zone z, Instant i) {
    check_instant(i);
    return format_local(i + offset_at(z, i));
}

Instant to_instant(Zone z, std::int64_t local, std::optional<Overlap> overlap) {
    const int y = year_of(date_of_seconds(local));
    if (y < 2007 || y > 2037) throw Error("E_DATE_RANGE", "local times must lie in 2007 to 2037", "local");
    const long long standard = standard_offset(z), summer = standard + hour;
    const Instant as_summer = local - summer, as_standard = local - standard;
    const bool summer_fits = has_summer(z) && offset_at(z, as_summer) == summer;
    const bool standard_fits = offset_at(z, as_standard) == standard;
    if (summer_fits && standard_fits) {
        if (!overlap) throw Error("E_AMBIGUOUS_LOCAL_TIME", "the local time occurs twice", "local");
        return *overlap == Overlap::Earlier ? as_summer : as_standard;
    }
    if (summer_fits) return as_summer;
    if (standard_fits) return as_standard;
    throw Error("E_NONEXISTENT_LOCAL_TIME", "the local time falls in a gap", "local");
}

Date business_date(Instant i, Zone z, Cutoff cutoff, Calendar c) {
    check_instant(i);
    const std::int64_t local = i + offset_at(z, i);
    Date d = date_of_seconds(local);
    const long long tod = local - seconds_at(d, 0);
    if (tod >= cutoff.hour * hour + cutoff.minute * 60LL) d += days{1};
    return adjust(c, d, BusinessDayConvention::Following);
}

}  // namespace quantforge
