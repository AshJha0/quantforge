#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "quantforge/core/calendar.hpp"
#include "quantforge/core/daycount.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/timezone.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
}  // namespace

TEST_CASE("day count worked examples from the spec") {
    CHECK(year_fraction(DayCount::Act360, d("2024-01-01"), d("2024-07-01")) == Approx(182.0 / 360));
    CHECK(year_fraction(DayCount::ActActIsda, d("2003-11-01"), d("2004-05-01")) == Approx(0.497724380567));
    DayCountInputs icma{2, d("2003-11-01"), d("2004-05-01"), {}, {}};
    CHECK(year_fraction(DayCount::ActActIcma, d("2003-11-01"), d("2004-05-01"), icma) == Approx(0.5));
    CHECK(year_fraction(DayCount::ActActAfb, d("1994-02-10"), d("1997-06-30")) == Approx(3 + 140.0 / 365));
    CHECK(year_fraction(DayCount::Thirty360Bond, d("2024-01-31"), d("2024-03-31")) == Approx(60.0 / 360));
    CHECK(year_fraction(DayCount::ThirtyEPlus360, d("2024-01-30"), d("2024-03-31")) == Approx(61.0 / 360));
}

TEST_CASE("day count edges") {
    CHECK(year_fraction(DayCount::OneOne, d("2024-01-01"), d("2024-01-01")) == 0.0);
    const DayCountInputs term{{}, {}, {}, d("2024-02-29"), {}};
    CHECK(year_fraction(DayCount::ThirtyE360Isda, d("2024-02-29"), d("2024-02-29"), term) == 0.0);
    CHECK(year_fraction(DayCount::ThirtyEPlus360, d("2024-01-31"), d("2024-01-31")) == 0.0);
    CHECK(year_fraction(DayCount::Nl365, d("2024-02-28"), d("2024-03-01")) == Approx(1.0 / 365));
    CHECK(code_of([] { year_fraction(DayCount::Act360, d("2024-01-02"), d("2024-01-01")); }) == "E_DATE_ORDER");
    CHECK(code_of([] { year_fraction(DayCount::Act365L, d("2024-01-01"), d("2024-01-02")); }) == "E_SCHEMA");
}

TEST_CASE("calendar rules") {
    CHECK(easter_sunday(2024) == d("2024-03-31"));
    CHECK_FALSE(is_business_day(Calendar::Gblo, d("2020-05-08")));
    CHECK(is_business_day(Calendar::Gblo, d("2020-05-04")));
    CHECK_FALSE(is_business_day(Calendar::Usgs, d("2021-12-24")));  // Christmas on a Saturday
    CHECK(is_business_day(Calendar::Usgs, d("2021-12-31")));        // New Year on a Saturday: none in lieu
    CHECK(code_of([] { is_business_day(Calendar::Euta, d("1999-12-31")); }) == "E_DATE_RANGE");
    using enum BusinessDayConvention;
    CHECK(adjust(Calendar::Euta, d("2024-03-30"), ModifiedFollowing) == d("2024-03-28"));
    CHECK(add_business_days(Calendar::Gblo, d("2024-03-28"), 1) == d("2024-04-02"));
    CHECK(business_days_between(Calendar::Gblo, d("2024-03-25"), d("2024-04-03")) == 5);
    CHECK(add_tenor(Calendar::Gblo, d("2024-01-31"), {1, 'M'}, Unadjusted, false) == d("2024-02-29"));
    CHECK(add_tenor(Calendar::Gblo, d("2024-02-29"), {1, 'M'}, Following, true) == d("2024-03-28"));
    CHECK(add_tenor(Calendar::Gblo, d("2024-03-30"), {1, 'M'}, Following, true) == d("2024-04-30"));
    CHECK(add_tenor(Calendar::Gblo, d("2024-03-27"), {1, 'M'}, Following, true) == d("2024-04-29"));
    CHECK(add_tenor(Calendar::Gblo, d("2024-06-30"), {2, 'M'}, Unadjusted, true) == d("2024-08-31"));
    CHECK(add_tenor(Calendar::Gblo, d("2024-03-29"), {1, 'M'}, Unadjusted, true) == d("2024-04-29"));
}

TEST_CASE("zones and cut-off") {
    const Instant before = *parse_instant("2024-03-31T00:59:59Z");
    CHECK(utc_offset(Zone::London, before) == 0);
    CHECK(utc_offset(Zone::London, before + 1) == 3600);
    CHECK(utc_offset(Zone::NewYork, *parse_instant("2024-03-10T07:00:00Z")) == -4 * 3600);
    CHECK(to_local(Zone::Tokyo, *parse_instant("2024-01-01T00:00:00+09:00")) == "2024-01-01T00:00:00");
    const auto local = *parse_local("2024-10-27T01:30:00");
    CHECK(code_of([&] { to_instant(Zone::London, local, {}); }) == "E_AMBIGUOUS_LOCAL_TIME");
    CHECK(to_instant(Zone::London, local, Overlap::Later) - to_instant(Zone::London, local, Overlap::Earlier) == 3600);
    CHECK(code_of([] { to_instant(Zone::London, *parse_local("2024-03-31T01:30:00"), {}); }) == "E_NONEXISTENT_LOCAL_TIME");
    const Cutoff c{16, 0};
    CHECK(business_date(*parse_instant("2024-07-01T14:59:59Z"), Zone::London, c, Calendar::Gblo) == d("2024-07-01"));
    CHECK(business_date(*parse_instant("2024-07-01T15:00:00Z"), Zone::London, c, Calendar::Gblo) == d("2024-07-02"));
    CHECK(business_date(*parse_instant("2024-07-06T10:00:00Z"), Zone::London, c, Calendar::Gblo) == d("2024-07-08"));
}

TEST_CASE("USGS Good Friday early closes are business days (ruling R1-6)") {
    using namespace quantforge;
    for (const char* s : {"2007-04-06", "2010-04-02", "2012-04-06", "2015-04-03", "2021-04-02", "2023-04-07", "2026-04-03"})
        CHECK(is_business_day(Calendar::Usgs, *parse_date(s)));
    for (const char* s : {"2008-03-21", "2022-04-15", "2024-03-29", "2027-03-26"})
        CHECK_FALSE(is_business_day(Calendar::Usgs, *parse_date(s)));
}
