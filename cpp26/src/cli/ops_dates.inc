// CLI handlers, dates, calendars, day counts, time zones and compounding.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_year_fraction(const In& in, Out& out) {
    using enum DayCount;
    const DayCount c = in.choice<DayCount>(
        "convention", {{"ACT_360", Act360}, {"ACT_365F", Act365F}, {"ACT_364", Act364}, {"ACT_365_25", Act365_25},
                       {"NL_365", Nl365}, {"ONE_ONE", OneOne}, {"BUS_252", Bus252}, {"ACT_365L", Act365L},
                       {"ACT_ACT_ISDA", ActActIsda}, {"ACT_ACT_ICMA", ActActIcma}, {"ACT_ACT_AFB", ActActAfb},
                       {"THIRTY_360_BOND", Thirty360Bond}, {"THIRTY_360_US", Thirty360Us}, {"THIRTY_E_360", ThirtyE360},
                       {"THIRTY_E_360_ISDA", ThirtyE360Isda}, {"THIRTY_E_PLUS_360", ThirtyEPlus360}});
    const Date start = in.date("start"), end = in.date("end");
    DayCountInputs extra;
    // Only what the convention needs is read: the others may carry anything.
    if (c == ActActIcma || c == Act365L)
        if (in.find("frequency")) extra.frequency = in.integer("frequency");
    if (c == ActActIcma) {
        extra.ref_start = in.maybe_date("ref_start");
        extra.ref_end = in.maybe_date("ref_end");
    }
    if (c == ThirtyE360Isda) extra.termination = in.maybe_date("termination");
    if (c == Bus252 && in.find("calendar")) extra.calendar = in.choice("calendar", calendars);
    check_day_count_inputs(c, extra);
    in.ready();
    out.key_real("year_fraction", year_fraction(c, start, end, extra));
}

void op_is_business_day(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const Date date = in.date("date");
    in.ready();
    const bool b = is_business_day(c, date);
    out.values.key("is_business_day");
    out.values.boolean(b);
}

void op_holidays(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const long long year = in.integer("year");
    in.ready();
    const auto list = holidays(c, int(std::clamp(year, -1LL, 100000LL)));
    out.values.key("dates");
    out.values.begin_array();
    for (const Date d : list) out.values.string(format_date(d));
    out.values.end_array();
}

void op_adjust(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const Date date = in.date("date");
    const auto conv = in.choice("convention", business_conventions);
    in.ready();
    const Date r = adjust(c, date, conv);
    out.key_string("date", format_date(r));
}

void op_add_business_days(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const Date d = in.date("date");
    const long long days = in.integer("days");
    in.ready();
    limit_if(days > 30000 || days < -30000, "days");
    out.key_string("date", format_date(add_business_days(c, d, days)));
}

void op_business_days_between(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const Date start = in.date("start"), end = in.date("end");
    in.ready();
    const long long n = business_days_between(c, start, end);
    out.values.key("count");
    out.values.integer(n);
}

void op_add_tenor(const In& in, Out& out) {
    const Calendar c = in.choice("calendar", calendars);
    const Date d = in.date("date");
    const Tenor t = parse_tenor(in.text("tenor"));
    const auto conv = in.choice("convention", business_conventions);
    const bool eom = in.boolean("end_of_month");
    in.ready();
    out.key_string("date", format_date(add_tenor(c, d, t, conv, eom)));
}

void op_discount_factor(const In& in, Out& out) {
    const double rate = in.real("rate"), t = in.real("t");
    const Compounding c = compounding_of(in.raw(), "compounding");
    check_frequency(c);
    in.ready();
    out.key_real("discount_factor", discount_factor(rate, t, c));
}

void op_convert(const In& in, Out& out) {
    const double rate = in.real("rate"), t = in.real("t");
    const Compounding from = compounding_of(in.need("from"), "from"), to = compounding_of(in.need("to"), "to");
    check_frequency(from);
    check_frequency(to);
    in.ready();
    out.key_real("rate", convert_rate(rate, t, from, to));
}

void op_utc_offset(const In& in, Out& out) {
    const Zone z = in.choice("zone", zones);
    const Instant i = in.instant("instant");
    in.ready();
    const long long v = utc_offset(z, i);
    out.values.key("offset_seconds");
    out.values.integer(v);
}

void op_to_local(const In& in, Out& out) {
    const Zone z = in.choice("zone", zones);
    const Instant i = in.instant("instant");
    in.ready();
    out.key_string("local", to_local(z, i));
}

void op_to_instant(const In& in, Out& out) {
    const Zone z = in.choice("zone", zones);
    const auto local = parse_local(in.text("local"));
    if (!local) schema("local", "bad local time");
    std::optional<Overlap> overlap;
    if (in.find("overlap")) overlap = in.choice<Overlap>("overlap", {{"EARLIER", Overlap::Earlier}, {"LATER", Overlap::Later}});
    in.ready();
    out.key_string("instant", format_local(to_instant(z, *local, overlap)) + "Z");
}

void op_business_date(const In& in, Out& out) {
    const Instant i = in.instant("instant");
    const Zone z = in.choice("zone", zones);
    const Cutoff c = parse_cutoff(in.text("cutoff"));
    const Calendar calendar = in.choice("calendar", calendars);
    in.ready();
    out.key_string("date", format_date(business_date(i, z, c, calendar)));
}

void op_conventions_lookup(const In& in, Out& out) {
    const string& id = in.text("id");
    const auto rate = [&](const char* kind, const char* currency, const char* dc, const char* cal, int spot) {
        out.key_string("kind", kind);
        out.key_string("currency", currency);
        out.key_string("day_count", dc);
        out.key_string("calendar", cal);
        key_int(out, "spot_lag", spot);
    };
    const auto tail = [&](const char* fixed_dc) {
        key_int(out, "fixed_months", 12);
        out.key_string("fixed_day_count", fixed_dc);
        out.key_string("business_day_convention", "MODIFIED_FOLLOWING");
    };
    if (id == "SONIA") {
        rate("OVERNIGHT", "GBP", "ACT_365F", "GBLO", 0);
        key_int(out, "payment_lag", 0);
        tail("ACT_365F");
    } else if (id == "SOFR") {
        rate("OVERNIGHT", "USD", "ACT_360", "USGS", 2);
        key_int(out, "payment_lag", 2);
        tail("ACT_360");
    } else if (id == "ESTR") {
        rate("OVERNIGHT", "EUR", "ACT_360", "EUTA", 2);
        key_int(out, "payment_lag", 2);
        tail("ACT_360");
    } else if (id == "USD-TERM-3M") {
        rate("TERM", "USD", "ACT_360", "USGS", 2);
        key_int(out, "months", 3);
        tail("THIRTY_360_BOND");
    } else if (id == "GBPUSD" || id == "EURUSD") {
        out.key_string("kind", "FX");
        out.key_string("base", id == "GBPUSD" ? "GBP" : "EUR");
        out.key_string("quote", "USD");
        key_int(out, "spot_lag", 2);
        write_strings(out, "calendars", {id == "GBPUSD" ? "GBLO" : "EUTA", "USGS"});
        out.key_real("pip", 0.0001);
    } else {
        schema("id", "not listed");
    }
}

constexpr Entry dates_ops[] = {
    {"core.calendar.add_business_days", op_add_business_days},
    {"core.calendar.add_tenor", op_add_tenor},
    {"core.calendar.adjust", op_adjust},
    {"core.calendar.business_days_between", op_business_days_between},
    {"core.calendar.holidays", op_holidays},
    {"core.calendar.is_business_day", op_is_business_day},
    {"core.compounding.convert", op_convert},
    {"core.compounding.discount_factor", op_discount_factor},
    {"core.conventions.lookup", op_conventions_lookup},
    {"core.daycount.year_fraction", op_year_fraction},
    {"core.time.business_date", op_business_date},
    {"core.time.to_instant", op_to_instant},
    {"core.time.to_local", op_to_local},
    {"core.time.utc_offset", op_utc_offset},
};
