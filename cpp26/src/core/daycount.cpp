#include "quantforge/core/daycount.hpp"

#include "quantforge/core/error.hpp"

using namespace std::chrono;

namespace quantforge {
namespace {

// 29 Februaries in [from, to], both ends included.
int count_feb29(Date from, Date to) {
    int n = 0;
    for (int y = year_of(from); y <= year_of(to); ++y)
        if (is_leap(y) && make_date(y, 2, 29) >= from && make_date(y, 2, 29) <= to) ++n;
    return n;
}

bool end_of_feb(Date d) { return month_of(d) == 2 && d == last_of_month(year_of(d), 2); }

Date back_years(Date end, int n) {
    if (n == 0) return end;
    const int y = year_of(end) - n;
    const unsigned m = month_of(end), d = day_of(end);
    if (m == 2 && d == 28 && is_leap(y)) return make_date(y, 2, 29);
    if (m == 2 && d == 29 && !is_leap(y)) return make_date(y, 2, 28);
    return make_date(y, m, d);
}

double act_act_afb(Date start, Date end) {
    int n = 0;
    while (back_years(end, n + 1) >= start) ++n;
    const Date e = back_years(end, n);
    const int d = e > start && count_feb29(start, e - days{1}) > 0 ? 366 : 365;
    return n + double(days_between(start, e)) / d;
}

double act_act_isda(Date start, Date end) {
    const int y1 = year_of(start), y2 = year_of(end);
    if (y1 == y2) return double(days_between(start, end)) / days_in_year(y1);
    return double(days_between(start, make_date(y1 + 1, 1, 1))) / days_in_year(y1) + (y2 - y1 - 1) +
           double(days_between(make_date(y2, 1, 1), end)) / days_in_year(y2);
}

double thirty_360(DayCount c, Date start, Date end, const DayCountInputs& in) {
    const int y1 = year_of(start), y2 = year_of(end);
    const int m1 = int(month_of(start));
    int m2 = int(month_of(end));
    int d1 = int(day_of(start)), d2 = int(day_of(end));
    switch (c) {
        case DayCount::Thirty360Bond:
            if (d1 == 31) d1 = 30;
            if (d2 == 31 && d1 == 30) d2 = 30;
            break;
        case DayCount::Thirty360Us:
            if (end_of_feb(start) && end_of_feb(end)) d2 = 30;
            if (end_of_feb(start)) d1 = 30;
            if (d2 == 31 && d1 >= 30) d2 = 30;
            if (d1 == 31) d1 = 30;
            break;
        case DayCount::ThirtyE360:
            if (d1 == 31) d1 = 30;
            if (d2 == 31) d2 = 30;
            break;
        case DayCount::ThirtyE360Isda:
            if (d1 == 31 || end_of_feb(start)) d1 = 30;
            if (d2 == 31 || (end_of_feb(end) && end != *in.termination)) d2 = 30;
            break;
        default:  // ThirtyEPlus360
            if (d1 == 31) d1 = 30;
            if (d2 == 31) {
                d2 = 1;
                m2 += 1;
            }
    }
    return double(360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)) / 360.0;
}

void check_needed(DayCount c, const DayCountInputs& in) {
    const auto missing = [](const char* name) { throw Error("E_SCHEMA", std::string(name) + " is needed", name); };
    if (c == DayCount::ActActIcma || c == DayCount::Act365L) {
        if (!in.frequency) missing("frequency");
        const long long f = *in.frequency;
        if (f != 1 && f != 2 && f != 3 && f != 4 && f != 6 && f != 12)
            throw Error("E_SCHEMA", "frequency is not listed", "frequency");
    }
    if (c == DayCount::ActActIcma) {
        if (!in.ref_start) missing("ref_start");
        if (!in.ref_end) missing("ref_end");
    }
    if (c == DayCount::ThirtyE360Isda && !in.termination) missing("termination");
    if (c == DayCount::Bus252 && !in.calendar) missing("calendar");
}

}  // namespace

double year_fraction(DayCount c, Date start, Date end, const DayCountInputs& in) {
    check_needed(c, in);
    if (end < start) throw Error("E_DATE_ORDER", "end is before start", "end");
    if (c == DayCount::ActActIcma && (*in.ref_end <= *in.ref_start || start < *in.ref_start || end > *in.ref_end))
        throw Error("E_INPUT", "the accrual must lie inside the reference period");
    if (c == DayCount::Bus252) {
        check_calendar_range(start);
        check_calendar_range(end);
    }
    if (start == end) return 0.0;  // before any day-number adjustment
    const double d = days_between(start, end);
    switch (c) {
        case DayCount::Act360: return d / 360.0;
        case DayCount::Act365F: return d / 365.0;
        case DayCount::Act364: return d / 364.0;
        case DayCount::Act365_25: return d / 365.25;
        case DayCount::Nl365: return end > start ? (d - count_feb29(start + days{1}, end)) / 365.0 : 0.0;
        case DayCount::OneOne: return end > start ? 1.0 : 0.0;
        case DayCount::Bus252: return double(business_days_between(*in.calendar, start, end)) / 252.0;
        case DayCount::Act365L:
            if (*in.frequency == 1) return d / (end > start && count_feb29(start + days{1}, end) > 0 ? 366.0 : 365.0);
            return d / days_in_year(year_of(end));
        case DayCount::ActActIsda: return act_act_isda(start, end);
        case DayCount::ActActIcma: return d / (double(*in.frequency) * days_between(*in.ref_start, *in.ref_end));
        case DayCount::ActActAfb: return act_act_afb(start, end);
        default: return thirty_360(c, start, end, in);
    }
}

}  // namespace quantforge
