#pragma once
#include <optional>
#include <string>

#include "quantforge/core/calendar.hpp"
#include "quantforge/core/dates.hpp"

namespace quantforge {

enum class Zone { Utc, London, Berlin, NewYork, Tokyo };
enum class Overlap { Earlier, Later };

struct Cutoff {
    int hour, minute;
};

long long utc_offset(Zone z, Instant i);
std::string to_local(Zone z, Instant i);
/// Returns the instant for a wall-clock time in the zone.
Instant to_instant(Zone z, std::int64_t local, std::optional<Overlap> overlap);
Date business_date(Instant i, Zone z, Cutoff cutoff, Calendar c);

}  // namespace quantforge
