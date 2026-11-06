#pragma once
#include <optional>

#include "quantforge/core/calendar.hpp"
#include "quantforge/core/dates.hpp"

namespace quantforge {

enum class DayCount {
    Act360, Act365F, Act364, Act365_25, Nl365, OneOne, Bus252, Act365L, ActActIsda, ActActIcma,
    ActActAfb, Thirty360Bond, Thirty360Us, ThirtyE360, ThirtyE360Isda, ThirtyEPlus360
};

/// Conditional inputs; which are needed depends on the convention.
struct DayCountInputs {
    std::optional<long long> frequency;
    std::optional<Date> ref_start;
    std::optional<Date> ref_end;
    std::optional<Date> termination;
    std::optional<Calendar> calendar;
};

double year_fraction(DayCount convention, Date start, Date end, const DayCountInputs& in = {});

}  // namespace quantforge
