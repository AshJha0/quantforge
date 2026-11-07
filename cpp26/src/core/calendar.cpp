#include "quantforge/core/calendar.hpp"

#include <algorithm>
#include <cstdlib>

#include "quantforge/core/error.hpp"

using namespace std::chrono;

namespace quantforge {
namespace {

constexpr unsigned sun = 0, mon = 1, thu = 4, fri = 5, sat = 6;

bool weekend(Date d) {
    const unsigned w = weekday_of(d);
    return w == sat || w == sun;
}

// The n-th given weekday of a month, n from 1.
Date nth_weekday(int y, unsigned m, unsigned wd, int n) {
    const Date first = make_date(y, m, 1);
    const int ahead = int((wd + 7 - weekday_of(first)) % 7);
    return first + days{ahead + 7 * (n - 1)};
}

Date last_weekday(int y, unsigned m, unsigned wd) {
    const Date end = last_of_month(y, m);
    return end - days{int((weekday_of(end) + 7 - wd) % 7)};
}

// Friday if a Saturday, Monday if a Sunday.
Date nearest_weekday(Date d) {
    const unsigned w = weekday_of(d);
    if (w == sat) return d - days{1};
    if (w == sun) return d + days{1};
    return d;
}

std::vector<Date> gblo(int y) {
    std::vector<Date> h;
    const Date easter = easter_sunday(y);
    Date ny = make_date(y, 1, 1);
    while (weekend(ny)) ny += days{1};
    h.push_back(ny);
    h.push_back(easter - days{2});
    h.push_back(easter + days{1});
    h.push_back(y == 2020 ? make_date(2020, 5, 8) : nth_weekday(y, 5, mon, 1));
    if (y == 2002) h.push_back(make_date(2002, 6, 4));
    else if (y == 2012) h.push_back(make_date(2012, 6, 4));
    else if (y == 2022) h.push_back(make_date(2022, 6, 2));
    else h.push_back(last_weekday(y, 5, mon));
    h.push_back(last_weekday(y, 8, mon));
    const unsigned xmas = weekday_of(make_date(y, 12, 25));
    unsigned first = 25, second = 26;
    if (xmas == sat) { first = 27; second = 28; }
    else if (xmas == sun) { first = 26; second = 27; }
    else if (xmas == fri) { first = 25; second = 28; }
    h.push_back(make_date(y, 12, first));
    h.push_back(make_date(y, 12, second));
    for (const Date d : {make_date(2002, 6, 3), make_date(2011, 4, 29), make_date(2012, 6, 5), make_date(2022, 6, 3),
                         make_date(2022, 9, 19), make_date(2023, 5, 8)})
        if (year_of(d) == y) h.push_back(d);
    return h;
}

std::vector<Date> euta(int y) {
    const Date easter = easter_sunday(y);
    std::vector<Date> h{make_date(y, 1, 1), easter - days{2}, easter + days{1}, make_date(y, 5, 1),
                        make_date(y, 12, 25), make_date(y, 12, 26)};
    if (y == 2001) h.push_back(make_date(2001, 12, 31));
    return h;
}

std::vector<Date> usgs(int y) {
    std::vector<Date> h;
    const Date ny = make_date(y, 1, 1);
    h.push_back(weekday_of(ny) == sun ? ny + days{1} : ny);
    h.push_back(nth_weekday(y, 1, mon, 3));
    h.push_back(nth_weekday(y, 2, mon, 3));
    // Ruling R1-6: in SIFMA early-close years Good Friday is a business day.
    constexpr int early_close[] = {2007, 2010, 2012, 2015, 2021, 2023, 2026};
    if (std::ranges::find(early_close, y) == std::end(early_close)) h.push_back(easter_sunday(y) - days{2});
    h.push_back(last_weekday(y, 5, mon));
    if (y >= 2022) h.push_back(nearest_weekday(make_date(y, 6, 19)));
    h.push_back(nearest_weekday(make_date(y, 7, 4)));
    h.push_back(nth_weekday(y, 9, mon, 1));
    h.push_back(nth_weekday(y, 10, mon, 2));
    const Date veterans = make_date(y, 11, 11);
    h.push_back(weekday_of(veterans) == sun ? veterans + days{1} : veterans);
    h.push_back(nth_weekday(y, 11, thu, 4));
    h.push_back(nearest_weekday(make_date(y, 12, 25)));
    for (const Date d : {make_date(2004, 6, 11), make_date(2012, 10, 30), make_date(2018, 12, 5)})
        if (year_of(d) == y) h.push_back(d);
    return h;
}

Date plain_following(Calendar c, Date d) {
    while (!is_business_day(c, d)) d += days{1};
    return d;
}

Date plain_preceding(Calendar c, Date d) {
    while (!is_business_day(c, d)) d -= days{1};
    return d;
}

}  // namespace

Date last_business_day(Calendar c, int y, unsigned m) { return plain_preceding(c, last_of_month(y, m)); }

Date add_months(Date d, int months) {
    const int total = year_of(d) * 12 + int(month_of(d)) - 1 + months;
    const int y = total / 12;
    const unsigned m = unsigned(total % 12) + 1;
    return make_date(y, m, std::min(day_of(d), day_of(last_of_month(y, m))));
}

void check_calendar_range(Date d) {
    const int y = year_of(d);
    if (y < 2000 || y > 2099) throw Error("E_DATE_RANGE", "calendars cover 2000 to 2099");
}

Date easter_sunday(int y) {
    const int a = y % 19, b = y / 100, c = y % 100, d = b / 4, e = b % 4, f = (b + 8) / 25, g = (b - f + 1) / 3;
    const int h = (19 * a + b - d - g + 15) % 30, i = c / 4, k = c % 4;
    const int l = (32 + 2 * e + 2 * i - h - k) % 7, m = (a + 11 * h + 22 * l) / 451;
    const int month = (h + l - 7 * m + 114) / 31, day = (h + l - 7 * m + 114) % 31 + 1;
    return make_date(y, unsigned(month), unsigned(day));
}

std::vector<Date> holidays(Calendar c, int y) {
    if (y < 2000 || y > 2099) throw Error("E_DATE_RANGE", "calendars cover 2000 to 2099", "year");
    std::vector<Date> h = c == Calendar::Gblo ? gblo(y) : c == Calendar::Euta ? euta(y) : usgs(y);
    std::erase_if(h, weekend);
    std::ranges::sort(h);
    h.erase(std::unique(h.begin(), h.end()), h.end());
    return h;
}

bool is_business_day(Calendar c, Date d) {
    check_calendar_range(d);
    if (weekend(d)) return false;
    return !std::ranges::binary_search(holidays(c, year_of(d)), d);
}

Date adjust(Calendar c, Date d, BusinessDayConvention conv) {
    check_calendar_range(d);
    using enum BusinessDayConvention;
    switch (conv) {
        case Unadjusted: return d;
        case Following: return plain_following(c, d);
        case Preceding: return plain_preceding(c, d);
        case ModifiedFollowing: {
            const Date r = plain_following(c, d);
            return month_of(r) == month_of(d) ? r : plain_preceding(c, d);
        }
        case ModifiedPreceding: {
            const Date r = plain_preceding(c, d);
            return month_of(r) == month_of(d) ? r : plain_following(c, d);
        }
    }
    return d;
}

Date add_business_days(Calendar c, Date d, long long n) {
    check_calendar_range(d);
    if (n == 0) return plain_following(c, d);
    const days step{n > 0 ? 1 : -1};
    for (long long left = std::llabs(n); left > 0;) {
        d += step;
        if (is_business_day(c, d)) --left;
    }
    return d;
}

long long business_days_between(Calendar c, Date start, Date end) {
    check_calendar_range(start);
    check_calendar_range(end);
    if (end < start) throw Error("E_DATE_ORDER", "end is before start", "end");
    long long n = 0;
    for (Date d = start; d < end; d += days{1})
        if (is_business_day(c, d)) ++n;
    return n;
}

Date add_tenor(Calendar c, Date d, Tenor tenor, BusinessDayConvention conv, bool end_of_month) {
    check_calendar_range(d);
    if (tenor.unit == 'D' || tenor.unit == 'W') {
        const Date r = d + days{tenor.count * (tenor.unit == 'W' ? 7 : 1)};
        return adjust(c, r, conv);
    }
    const int months = tenor.count * (tenor.unit == 'Y' ? 12 : 1);
    const int total = year_of(d) * 12 + int(month_of(d)) - 1 + months;
    const int y = total / 12;
    const unsigned m = unsigned(total % 12) + 1;
    if (y > 2099) throw Error("E_DATE_RANGE", "calendars cover 2000 to 2099");
    if (end_of_month && conv != BusinessDayConvention::Unadjusted && d >= last_business_day(c, year_of(d), month_of(d)))
        return last_business_day(c, y, m);
    if (end_of_month && conv == BusinessDayConvention::Unadjusted && d == last_of_month(year_of(d), month_of(d)))
        return last_of_month(y, m);
    return adjust(c, make_date(y, m, std::min(day_of(d), day_of(last_of_month(y, m)))), conv);
}

}  // namespace quantforge
