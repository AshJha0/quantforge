#pragma once
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge {

enum class Calendar { Gblo, Euta, Usgs };
enum class BusinessDayConvention { Unadjusted, Following, Preceding, ModifiedFollowing, ModifiedPreceding };

struct Tenor {
    int count;
    char unit;  // D, W, M or Y
};

/// Valid for 2000 to 2099; anything else throws E_DATE_RANGE.
void check_calendar_range(Date d);
Date easter_sunday(int year);
std::vector<Date> holidays(Calendar c, int year);
bool is_business_day(Calendar c, Date d);
Date adjust(Calendar c, Date d, BusinessDayConvention conv);
Date add_business_days(Calendar c, Date d, long long days);
long long business_days_between(Calendar c, Date start, Date end);
/// Calendar months, with the day clipped to the target month.
Date add_months(Date d, int months);
Date last_business_day(Calendar c, int year, unsigned month);
Date add_tenor(Calendar c, Date d, Tenor tenor, BusinessDayConvention conv, bool end_of_month);

}  // namespace quantforge
