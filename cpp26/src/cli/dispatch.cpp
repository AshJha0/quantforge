#include "dispatch.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <initializer_list>
#include <map>
#include <optional>
#include <utility>

#include "quantforge/core/calendar.hpp"
#include "quantforge/core/calibration.hpp"
#include "quantforge/core/compounding.hpp"
#include "quantforge/core/data_checks.hpp"
#include "quantforge/core/dates.hpp"
#include "quantforge/core/daycount.hpp"
#include "quantforge/core/equity.hpp"
#include "quantforge/core/black.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/surface.hpp"
#include "quantforge/core/sabr.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/fx.hpp"
#include "quantforge/core/integrate.hpp"
#include "quantforge/core/interp.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/linalg.hpp"
#include "quantforge/core/models.hpp"
#include "quantforge/core/money.hpp"
#include "quantforge/core/rates.hpp"
#include "quantforge/core/rates_d.hpp"
#include "quantforge/core/bonds.hpp"
#include "quantforge/core/misc_d.hpp"
#include "quantforge/core/inflation.hpp"
#include "quantforge/core/equity_d.hpp"
#include "quantforge/core/credit.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/snapshot.hpp"
#include "quantforge/core/sobol.hpp"
#include "quantforge/core/stats.hpp"
#include "quantforge/core/risk.hpp"
#include "quantforge/core/store.hpp"
#include "quantforge/core/timeseries.hpp"
#include "quantforge/core/timezone.hpp"
#include "quantforge/core/arb_surface.hpp"
#include "quantforge/core/fx_smile.hpp"
#include "quantforge/core/vol_stats.hpp"
#include "test_functions.hpp"

namespace quantforge::cli {
namespace {

using json::Kind;
using json::Value;
using Vec = std::vector<double>;
using std::string;
using std::string_view;

[[noreturn]] void schema(string_view key, const string& why) {
    throw Error("E_SCHEMA", string(key) + ": " + why, string(key));
}

void limit_if(bool above, string_view key) {
    if (above) throw Error("E_LIMIT", string(key) + " is above its limit", string(key));
}

// Is a * b above the limit? Only for sizes both at their minimum or more: below it, the spec's code stands.
bool product_above(long long a, long long b, double limit) {
    return a >= 1 && b >= 1 && double(a) * double(b) > limit;
}

template <class T>
using EnumTable = std::initializer_list<std::pair<string_view, T>>;

double to_real(const Value& v, string_view key) {
    if (v.kind != Kind::Number) schema(key, "expected a number");
    return v.number;
}

long long to_integer(const Value& v, string_view key) {
    if (v.kind != Kind::Number || !v.integral) schema(key, "expected an integer");
    if (std::fabs(v.number) > 9007199254740992.0) schema(key, "integer above 2^53");
    return (long long)v.number;
}

const string& to_string(const Value& v, string_view key) {
    if (v.kind != Kind::String) schema(key, "expected a string");
    return v.text;
}

Date to_date(const Value& v, string_view key) {
    const auto d = parse_date(to_string(v, key));
    if (!d) schema(key, "bad date");
    return *d;
}

Instant to_instant_value(const Value& v, string_view key) {
    const auto i = parse_instant(to_string(v, key));
    if (!i) schema(key, "bad instant");
    return *i;
}

std::optional<double> to_maybe_real(const Value& v, string_view key) {
    if (v.kind == Kind::Null) return std::nullopt;
    return to_real(v, key);
}

Vec to_reals(const Value& v, string_view key) {
    if (v.kind != Kind::Array) schema(key, "expected an array");
    Vec out;
    out.reserve(v.items.size());
    for (const Value& item : v.items) out.push_back(to_real(item, key));
    return out;
}

std::uint64_t to_u64(const Value& v, string_view key) {
    const string& s = to_string(v, key);
    std::uint64_t out = 0;
    const auto r = std::from_chars(s.data(), s.data() + s.size(), out);
    if (s.empty() || r.ec != std::errc{} || r.ptr != s.data() + s.size()) schema(key, "expected a decimal u64 string");
    return out;
}

template <class T>
T to_enum(const Value& v, string_view key, EnumTable<T> table) {
    const string& s = to_string(v, key);
    for (const auto& [name, value] : table)
        if (name == s) return value;
    schema(key, "value is not listed");
}

constexpr EnumTable<Calendar> calendars = {{"GBLO", Calendar::Gblo}, {"EUTA", Calendar::Euta}, {"USGS", Calendar::Usgs}};
constexpr EnumTable<OptionType> option_types = {{"CALL", OptionType::Call}, {"PUT", OptionType::Put}};
constexpr EnumTable<BusinessDayConvention> business_conventions = {
    {"UNADJUSTED", BusinessDayConvention::Unadjusted},
    {"FOLLOWING", BusinessDayConvention::Following},
    {"PRECEDING", BusinessDayConvention::Preceding},
    {"MODIFIED_FOLLOWING", BusinessDayConvention::ModifiedFollowing},
    {"MODIFIED_PRECEDING", BusinessDayConvention::ModifiedPreceding}};
constexpr EnumTable<Zone> zones = {{"UTC", Zone::Utc},
                                   {"Europe/London", Zone::London},
                                   {"Europe/Berlin", Zone::Berlin},
                                   {"America/New_York", Zone::NewYork},
                                   {"Asia/Tokyo", Zone::Tokyo}};

// Typed access to the inputs of a case. Every miss is E_SCHEMA, which outranks all rule checks,
// so handlers read all their inputs before they call the library.
class In {
public:
    explicit In(const Value& v, bool oversized = false) : v_(v), oversized_(oversized) {}

    // Every handler calls this once its inputs are read, before any work: E_SCHEMA has had its
    // turn by then, so the array limit can stop the case (ruling B24).
    void ready() const {
        if (oversized_) throw Error("E_LIMIT", "an array in inputs is above its limit");
    }

    const Value* find(string_view key) const {
        const Value* p = v_.find(key);
        return p && p->kind != Kind::Null ? p : nullptr;
    }
    const Value& need(string_view key) const {
        const Value* p = find(key);
        if (!p) schema(key, "missing");
        return *p;
    }
    double real(string_view k) const { return to_real(need(k), k); }
    double real(string_view k, double fallback) const { return find(k) ? to_real(*find(k), k) : fallback; }
    long long integer(string_view k) const { return to_integer(need(k), k); }
    long long integer(string_view k, long long fallback) const { return find(k) ? to_integer(*find(k), k) : fallback; }
    bool boolean(string_view k, std::optional<bool> fallback = {}) const {
        if (!find(k)) {
            if (fallback) return *fallback;
            schema(k, "missing");
        }
        if (find(k)->kind != Kind::Bool) schema(k, "expected a boolean");
        return find(k)->boolean;
    }
    const string& text(string_view k) const { return to_string(need(k), k); }
    Date date(string_view k) const { return to_date(need(k), k); }
    std::optional<Date> maybe_date(string_view k) const {
        if (!find(k)) return std::nullopt;
        return to_date(*find(k), k);
    }
    Instant instant(string_view k) const { return to_instant_value(need(k), k); }
    Vec reals(string_view k) const { return to_reals(need(k), k); }
    std::vector<MaybeReal> maybe_reals(string_view k) const {
        const Value& a = need(k);
        if (a.kind != Kind::Array) schema(k, "expected an array");
        std::vector<MaybeReal> out;
        for (const Value& item : a.items) out.push_back(to_maybe_real(item, k));
        return out;
    }
    Matrix matrix(string_view k) const {
        const Value& a = need(k);
        if (a.kind != Kind::Array) schema(k, "expected an array of rows");
        Matrix m;
        for (const Value& row : a.items) m.push_back(to_reals(row, k));
        return m;
    }
    template <class T>
    T choice(string_view k, EnumTable<T> table) const {
        return to_enum(need(k), k, table);
    }
    std::uint64_t u64(string_view k) const { return to_u64(need(k), k); }
    const Value& raw() const { return v_; }

private:
    const Value& v_;
    bool oversized_;
};

struct Out {
    json::Writer values;
    json::Writer diagnostics;

    void key_real(string_view k, double v) {
        values.key(k);
        values.real(v);
    }
    void key_reals(string_view k, const Vec& v) {
        values.key(k);
        values.begin_array();
        for (const double x : v) values.real(x);
        values.end_array();
    }
    void key_maybe(string_view k, const std::optional<double>& v) {
        values.key(k);
        maybe(v);
    }
    void maybe(const std::optional<double>& v) {
        if (v) values.real(*v);
        else values.null();
    }
    void key_maybes(string_view k, const std::vector<MaybeReal>& v) {
        values.key(k);
        values.begin_array();
        for (const auto& x : v) maybe(x);
        values.end_array();
    }
    void key_string(string_view k, string_view v) {
        values.key(k);
        values.string(v);
    }
    void diagnostic(string_view k, double v) {
        if (!std::isfinite(v)) return;
        diagnostics.key(k);
        diagnostics.real(v);
    }
};

// ---- dates ----

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

Tenor parse_tenor(const string& s) {
    const bool shape = s.size() >= 2 && s.size() <= 5 && s[0] >= '1' && s[0] <= '9' &&
                       std::all_of(s.begin(), s.end() - 1, [](char c) { return c >= '0' && c <= '9'; }) &&
                       string_view("DWMY").find(s.back()) != string_view::npos;
    if (!shape) schema("tenor", "bad tenor");
    return {std::stoi(s.substr(0, s.size() - 1)), s.back()};
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

// ---- compounding ----

Compounding compounding_of(const Value& v, string_view key) {
    static constexpr EnumTable<CompoundingKind> kinds = {{"SIMPLE", CompoundingKind::Simple},
                                                         {"PERIODIC", CompoundingKind::Periodic},
                                                         {"CONTINUOUS", CompoundingKind::Continuous}};
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In in(v);
    Compounding c{in.choice("compounding", kinds), std::nullopt};
    if (c.kind == CompoundingKind::Periodic && in.find("frequency")) c.frequency = in.integer("frequency");
    return c;
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

// ---- snapshot ----

void op_snapshot_hash(const In& in, Out& out) {
    const string& text = in.text("document_text");
    const SnapshotHash h = snapshot_hash(text);  // one linear pass, and its E_SCHEMA comes first
    in.ready();
    out.key_string("canonical", h.canonical);
    out.key_string("snapshot_id", h.snapshot_id);
}

// ---- random numbers ----

struct DrawRequest {
    Xoshiro256 rng;
    long long count;
};

long long draw_count(const In& in) {
    const long long count = in.integer("count");
    if (count < 1) schema("count", "must be at least 1");
    return count;
}

int stream_of(long long stream) {
    if (stream < 0 || stream > 1023) schema("stream", "must be 0 to 1023");
    return int(stream);
}

DrawRequest draws(const In& in) {
    const std::uint64_t seed = in.u64("seed");
    const int stream = stream_of(in.integer("stream"));
    const long long count = draw_count(in), skip = in.integer("skip", 0);
    if (skip < 0) schema("skip", "must not be negative");
    in.ready();
    limit_if(count > 100000, "count");
    limit_if(skip > 10000000, "skip");
    Xoshiro256 rng(seed, stream);
    for (long long i = 0; i < skip; ++i) rng.next();
    return {rng, count};
}

void write_u64s(Out& out, Xoshiro256& rng, long long count) {
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < count; ++i) out.values.string(std::to_string(rng.next()));
    out.values.end_array();
}

void op_next_u64(const In& in, Out& out) {
    auto d = draws(in);
    write_u64s(out, d.rng, d.count);
}

void op_uniforms(const In& in, Out& out) {
    auto d = draws(in);
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < d.count; ++i) out.values.real(d.rng.next_uniform());
    out.values.end_array();
}

void op_normals(const In& in, Out& out) {
    auto d = draws(in);
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < d.count; ++i) out.values.real(d.rng.next_normal());
    out.values.end_array();
}

void op_inverse_normal(const In& in, Out& out) {
    const Vec p = in.reals("p");
    in.ready();
    Vec z;
    z.reserve(p.size());
    for (const double v : p) {
        if (v <= 0.0 || v >= 1.0) throw Error("E_DOMAIN", "p must lie in (0, 1)", "p");
        z.push_back(ppnd16(v));
    }
    out.key_reals("z", z);
}

void op_set_state(const In& in, Out& out) {
    const Value& a = in.need("state");
    if (a.kind != Kind::Array || a.items.size() != 4) schema("state", "expected four u64 strings");
    Xoshiro256::State s{};
    for (std::size_t i = 0; i < 4; ++i) s[i] = to_u64(a.items[i], "state");
    const long long count = draw_count(in);
    in.ready();
    limit_if(count > 100000, "count");
    if (s == Xoshiro256::State{}) throw Error("E_INPUT", "the state is all zero", "state");
    Xoshiro256 rng(s);
    write_u64s(out, rng, count);
}

void op_sobol(const In& in, Out& out) {
    const long long dimensions = in.integer("dimensions"), count = in.integer("count"), skip = in.integer("skip", 0);
    in.ready();
    limit_if(product_above(count, dimensions, 100000), "count");
    limit_if(skip > 10000000, "skip");
    check_sobol_request(dimensions, count, skip);
    Sobol sobol{int(dimensions), std::uint64_t(skip)};
    Vec point(std::size_t(dimensions), 0.0);
    out.values.key("points");
    out.values.begin_array();
    for (long long i = 0; i < count; ++i) {
        sobol.next(point.data());
        out.values.begin_array();
        for (const double v : point) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
}

// ---- roots, integrals, differences ----

RootOptions root_options(const In& in) {
    const RootOptions o{in.real("x_tol", 1e-12), in.real("f_tol", 0.0), in.integer("max_iter", 200)};
    in.ready();
    limit_if(o.max_iter > 100000, "max_iter");
    return o;
}

void write_root(Out& out, const RootResult& r) {
    out.key_real("root", r.root);
    out.diagnostics.key("iterations");
    out.diagnostics.integer(r.iterations);
    out.diagnostic("residual", r.residual);
    out.diagnostics.key("termination");
    out.diagnostics.string(r.termination);
}

void op_bisection(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    write_root(out, bisection(fn.f, a, b, root_options(in)));
}

void op_brent(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    write_root(out, brent(fn.f, a, b, root_options(in)));
}

void op_newton(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double x0 = in.real("x0");
    if (bool(in.find("a")) != bool(in.find("b"))) schema("a", "a and b must both be given or both absent");
    std::optional<Bracket> bracket;
    if (in.find("a")) bracket = Bracket{in.real("a"), in.real("b")};
    write_root(out, newton(fn.f, fn.df, x0, bracket, root_options(in)));
}

void op_trapezoid(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    limit_if(n > 10000000, "n");
    out.key_real("value", trapezoid(f, a, b, n));
}

void op_simpson(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    limit_if(n > 10000000, "n");
    out.key_real("value", simpson(f, a, b, n));
}

void op_gauss_legendre(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    out.key_real("value", gauss_legendre(f, a, b, n));
}

void op_adaptive_simpson(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b"), tol = in.real("tol", 1e-10);
    const long long max_depth = in.integer("max_depth", 50);
    in.ready();
    limit_if(max_depth > 60, "max_depth");
    out.key_real("value", adaptive_simpson(f, a, b, tol, max_depth));
}

void op_gauss_kronrod(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b"), tol = in.real("tol", 1e-10);
    const long long max_intervals = in.integer("max_intervals", 500);
    in.ready();
    limit_if(max_intervals > 10000, "max_intervals");
    const auto r = gauss_kronrod(f, a, b, tol, max_intervals);
    out.key_real("value", r.value);
    out.diagnostics.key("error_estimate");
    out.diagnostics.real(r.error_estimate);
}

void op_central(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double x = in.real("x"), h = in.real("h");
    const long long order = in.integer("order");
    if (order != 1 && order != 2) schema("order", "must be 1 or 2");
    in.ready();
    out.key_real("value", central_difference(f, x, h, order));
}

// ---- interpolation and linear algebra ----

void op_interp(const In& in, Out& out) {
    using enum InterpMethod;
    const InterpMethod method = in.choice<InterpMethod>(
        "method", {{"linear", Linear}, {"log_linear", LogLinear}, {"cubic_natural", CubicNatural},
                   {"cubic_clamped", CubicClamped}, {"cubic_not_a_knot", CubicNotAKnot},
                   {"monotone_pchip", MonotonePchip}, {"tension", Tension}});
    const Vec x = in.reals("x"), y = in.reals("y"), at = in.reals("at");
    InterpParams p;
    if (method == CubicClamped) {
        p.slope_start = in.real("slope_start");
        p.slope_end = in.real("slope_end");
    }
    if (method == Tension) p.tension = in.real("tension");
    in.ready();
    const auto r = interpolate(method, x, y, at, p);
    out.key_reals("values", r.values);
    if (method != Linear && method != LogLinear) out.key_reals("derivatives", r.derivatives);
}

void op_monotone_convex(const In& in, Out& out) {
    const Vec t = in.reals("t"), r = in.reals("r"), at = in.reals("at");
    const bool positive = in.boolean("positive", false);
    in.ready();
    const auto v = monotone_convex(t, r, at, positive);
    out.key_reals("forwards", v.forwards);
    out.key_reals("zero_rates", v.zero_rates);
}

void op_solve(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    const Vec b = in.reals("b");
    in.ready();
    limit_if(a.size() > 200, "a");
    out.key_reals("x", solve_linear(a, b));
}

void op_cholesky(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    in.ready();
    limit_if(a.size() > 200, "a");
    const Matrix l = cholesky(a);
    out.values.key("l");
    out.values.begin_array();
    for (const Vec& row : l) {
        out.values.begin_array();
        for (const double v : row) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
}

void op_eigen(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    in.ready();
    limit_if(a.size() > 200, "a");
    out.key_reals("values", eigen_symmetric(a));
}

// ---- statistics and time series ----

void op_normal(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    Vec pdf, cdf;
    for (const double v : x) {
        pdf.push_back(normal_pdf(v));
        cdf.push_back(normal_cdf(v));
    }
    out.key_reals("pdf", pdf);
    out.key_reals("cdf", cdf);
}

void op_summary(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    const Summary s = summary(x);
    out.values.key("count");
    out.values.integer((long long)s.count);
    out.key_real("mean", s.mean);
    out.key_real("variance", s.variance);
    out.key_real("stdev", s.stdev);
    out.key_maybe("skewness", s.skewness);
    out.key_maybe("excess_kurtosis", s.excess_kurtosis);
    out.key_real("min", s.min);
    out.key_real("max", s.max);
}

void op_quantile(const In& in, Out& out) {
    const Vec x = in.reals("x"), p = in.reals("p");
    in.ready();
    out.key_reals("values", quantiles(x, p));
}

void op_covariance(const In& in, Out& out) {
    const Vec x = in.reals("x"), y = in.reals("y");
    in.ready();
    const Covariance c = covariance(x, y);
    out.key_real("covariance", c.covariance);
    out.key_maybe("correlation", c.correlation);
}

void op_ols(const In& in, Out& out) {
    const Vec x = in.reals("x"), y = in.reals("y");
    in.ready();
    const Ols r = ols(x, y);
    out.key_real("alpha", r.alpha);
    out.key_real("beta", r.beta);
    out.key_maybe("r_squared", r.r_squared);
    out.key_real("se_alpha", r.se_alpha);
    out.key_real("se_beta", r.se_beta);
}

void op_returns(const In& in, Out& out) {
    const Vec p = in.reals("prices");
    const auto kind = in.choice<ReturnKind>("kind", {{"SIMPLE", ReturnKind::Simple}, {"LOG", ReturnKind::Log}});
    in.ready();
    out.key_reals("returns", returns(p, kind));
}

void op_rolling(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long window = in.integer("window");
    const auto s = in.choice<RollingStatistic>("statistic", {{"MEAN", RollingStatistic::Mean}, {"STDEV", RollingStatistic::Stdev}});
    in.ready();
    limit_if(window > 1000, "window");
    out.key_maybes("values", rolling(x, window, s));
}

void op_ewma(const In& in, Out& out) {
    const Vec r = in.reals("returns");
    const double lambda = in.real("lambda");
    in.ready();
    out.key_reals("variance", ewma_variance(r, lambda));
}

void op_autocorrelation(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long max_lag = in.integer("max_lag");
    in.ready();
    limit_if(max_lag > 1000, "max_lag");
    out.key_reals("acf", autocorrelation(x, max_lag));
}

void op_ljung_box(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long max_lag = in.integer("max_lag");
    in.ready();
    limit_if(max_lag > 1000, "max_lag");
    out.key_real("statistic", ljung_box(x, max_lag));
}

void op_ar1(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    const Ar1 r = ar1(x);
    out.key_real("constant", r.constant);
    out.key_real("phi", r.phi);
    out.key_real("sigma", r.sigma);
}

void op_resample_last(const In& in, Out& out) {
    const Value& a = in.need("dates");
    if (a.kind != Kind::Array) schema("dates", "expected an array");
    std::vector<Date> dates;
    for (const Value& v : a.items) dates.push_back(to_date(v, "dates"));
    const auto values = in.maybe_reals("values");
    const auto f = in.choice<ResampleFrequency>("frequency", {{"WEEK", ResampleFrequency::Week}, {"MONTH", ResampleFrequency::Month}});
    in.ready();
    const Resampled r = resample_last(dates, values, f);
    out.values.key("dates");
    out.values.begin_array();
    for (const Date d : r.dates) out.values.string(format_date(d));
    out.values.end_array();
    out.key_reals("values", r.values);
}

void op_forward_fill(const In& in, Out& out) {
    const auto values = in.maybe_reals("values");
    const long long limit = in.integer("limit");
    in.ready();
    out.key_maybes("values", forward_fill(values, limit));
}

// ---- engines ----

void op_pde(const In& in, Out& out) {
    PdeInputs p{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
                in.real("sigma"), in.real("t"), in.integer("space_steps"), in.integer("time_steps"),
                in.real("width", 6.0), in.integer("rannacher_steps", 2)};
    in.ready();
    limit_if(product_above(p.space_steps, p.time_steps, 10000000), "space_steps");
    const PdeResult r = pde_bs_european(p);
    out.key_real("price", r.price);
    out.key_real("delta", r.delta);
    out.key_real("gamma", r.gamma);
    out.diagnostic("grid_h", r.grid_h);
}

void op_mc(const In& in, Out& out) {
    using enum McMethod;
    McInputs m{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
               in.real("sigma"), in.real("t"), in.integer("paths"), in.integer("steps", 1), in.u64("seed"),
               stream_of(in.integer("stream", 0)),
               in.choice<McMethod>("method", {{"PLAIN", Plain}, {"ANTITHETIC", Antithetic},
                                              {"CONTROL_VARIATE", ControlVariate}, {"SOBOL", Sobol}})};
    in.ready();
    limit_if(product_above(m.paths, m.steps, 1000000), "paths");
    const McResult r = mc_gbm_european(m);
    out.key_real("price", r.price);
    out.key_real("stderr", r.standard_error);
}

void op_cos(const In& in, Out& out) {
    const Value& mv = in.need("model");
    if (mv.kind != Kind::Object) schema("model", "expected an object");
    const In model(mv);
    CosModel m{model.choice<CosModelName>("name", {{"BLACK_SCHOLES", CosModelName::BlackScholes}, {"HESTON", CosModelName::Heston}})};
    m.sigma = model.real("sigma");
    if (m.name == CosModelName::Heston) {
        m.v0 = model.real("v0");
        m.kappa = model.real("kappa");
        m.theta = model.real("theta");
        m.rho = model.real("rho");
    }
    const CosInputs c{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
                      in.real("t"), m, in.integer("terms"), in.real("truncation")};
    in.ready();
    limit_if(c.terms > 100000, "terms");
    const CosResult r = cos_european(c);
    out.key_real("price", r.price);
    out.diagnostic("a", r.a);
    out.diagnostic("b", r.b);
}

// ---- market data checks ----

Quote quote_of(const Value& v) {
    if (v.kind != Kind::Object) schema("quotes", "expected an object");
    const In q(v);
    if (!v.find("bid")) schema("bid", "missing");
    if (!v.find("ask")) schema("ask", "missing");
    const string& status = q.text("quote_status");
    if (status != "FIRM" && status != "INDICATIVE") schema("quote_status", "must be FIRM or INDICATIVE");
    return {q.text("instrument_id"), q.instant("event_time"), to_maybe_real(*v.find("bid"), "bid"),
            to_maybe_real(*v.find("ask"), "ask"), status};
}

void op_check_quotes(const In& in, Out& out) {
    QuoteCheckInputs c;
    c.as_of = in.instant("as_of");
    const Value& quotes = in.need("quotes");
    if (quotes.kind != Kind::Array) schema("quotes", "expected an array");
    for (const Value& q : quotes.items) c.quotes.push_back(quote_of(q));
    c.stale_after_seconds = in.integer("stale_after_seconds");
    if (in.find("max_relative_spread")) c.max_relative_spread = in.real("max_relative_spread");
    c.positive_only = in.boolean("positive_only", false);
    c.outlier_threshold = in.real("outlier_threshold", 5.0);
    c.outlier_min_history = in.integer("outlier_min_history", 5);
    if (const Value* h = in.find("history")) {
        if (h->kind != Kind::Object) schema("history", "expected an object");
        for (const auto& [id, mids] : h->members) c.history[id] = to_reals(mids, "history");
    }
    in.ready();
    const auto results = check_quotes(c);
    out.values.key("results");
    out.values.begin_array();
    for (const QuoteCheckResult& r : results) {
        out.values.begin_object();
        out.key_string("instrument_id", r.instrument_id);
        out.key_string("quote_status", r.quote_status);
        out.values.key("quality_flags");
        out.values.begin_array();
        for (const string& f : r.quality_flags) out.values.string(f);
        out.values.end_array();
        out.values.end_object();
    }
    out.values.end_array();
}

// ---- time ----

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

Cutoff parse_cutoff(const string& s) {
    const auto digit = [&](std::size_t i) { return s[i] >= '0' && s[i] <= '9'; };
    if (s.size() != 5 || s[2] != ':' || !digit(0) || !digit(1) || !digit(3) || !digit(4)) schema("cutoff", "expected HH:MM");
    const Cutoff c{(s[0] - '0') * 10 + (s[1] - '0'), (s[3] - '0') * 10 + (s[4] - '0')};
    if (c.hour > 23 || c.minute > 59) schema("cutoff", "expected HH:MM");
    return c;
}

void op_business_date(const In& in, Out& out) {
    const Instant i = in.instant("instant");
    const Zone z = in.choice("zone", zones);
    const Cutoff c = parse_cutoff(in.text("cutoff"));
    const Calendar calendar = in.choice("calendar", calendars);
    in.ready();
    out.key_string("date", format_date(business_date(i, z, c, calendar)));
}

// ---- as-of store ----

StoreRecord record_of(const Value& v) {
    if (v.kind != Kind::Object) schema("records", "expected an object");
    const In r(v);
    if (!v.find("value")) schema("value", "missing");
    const long long sequence = r.integer("sequence");
    if (sequence < 1) schema("sequence", "must be at least 1");
    const string& series = r.text("series_id");
    if (series.empty()) schema("series_id", "empty");
    return {sequence, series, r.instant("event_time"), r.instant("knowledge_time"), *v.find("value"),
            r.boolean("deleted", false), v};
}

std::vector<StoreRecord> log_of(const In& in) {
    const Value& a = in.need("records");
    if (a.kind != Kind::Array) schema("records", "expected an array");
    std::vector<StoreRecord> log;
    log.reserve(a.items.size());
    for (const Value& v : a.items) log.push_back(record_of(v));
    return log;
}

int nesting(const Value& v) {
    int deepest = 0;
    for (const Value& item : v.items) deepest = std::max(deepest, nesting(item));
    for (const auto& m : v.members) deepest = std::max(deepest, nesting(m.second));
    return v.kind == Kind::Array || v.kind == Kind::Object ? deepest + 1 : 0;
}

// Runs once all schema checks are done: limits, then log checks 2 and 3, then the range of
// instants, records first (rulings A2 and A5).
void check_store_nesting(const std::vector<StoreRecord>& log) {
    for (const StoreRecord& r : log)
        for (const auto& m : r.raw.members) limit_if(nesting(m.second) > 64, m.first);
}

void check_store(const std::vector<StoreRecord>& log, const std::vector<std::optional<Instant>>& others) {
    check_log(log);
    for (const StoreRecord& r : log) {
        check_store_instant(r.event_time);
        check_store_instant(r.knowledge_time);
    }
    for (const auto& i : others)
        if (i) check_store_instant(*i);
}

void write_row(Out& out, const StoreRow& r) {
    out.values.begin_object();
    out.key_string("series_id", r.series_id);
    out.key_string("event_time", format_instant(r.event_time));
    out.key_string("knowledge_time", format_instant(r.knowledge_time));
    out.values.key("sequence");
    out.values.integer(r.sequence);
    out.values.key("value");
    out.values.value(r.value);
    out.values.end_object();
}

std::optional<Instant> maybe_instant(const In& in, string_view k) {
    if (!in.find(k)) return std::nullopt;
    return in.instant(k);
}

void op_store_query(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    const string* series = in.find("series_id") ? &in.text("series_id") : nullptr;
    const auto from = maybe_instant(in, "event_from"), to = maybe_instant(in, "event_to");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of, from, to});
    if (from && to && *from > *to) throw Error("E_DATE_ORDER", "event_from is after event_to", "event_from");
    out.values.key("rows");
    out.values.begin_array();
    for (const StoreRow& r : store_view(log, as_of)) {
        if (series && r.series_id != *series) continue;
        if ((from && r.event_time < *from) || (to && r.event_time > *to)) continue;
        write_row(out, r);
    }
    out.values.end_array();
}

void op_store_latest(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    const string& series = in.text("series_id");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of});
    std::optional<StoreRow> best;
    for (StoreRow& r : store_view(log, as_of))
        if (r.series_id == series) best = std::move(r);  // the view ascends by event_time
    out.values.key("row");
    if (best) write_row(out, *best);
    else out.values.null();
}

void op_store_snapshot(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of});
    const SnapshotHash h = store_snapshot(log, as_of);
    out.key_string("canonical", h.canonical);
    out.key_string("snapshot_id", h.snapshot_id);
}

void op_store_replay(const In& in, Out& out) {
    const auto log = log_of(in);
    const Value& a = in.need("checkpoints");
    if (a.kind != Kind::Array) schema("checkpoints", "expected an array");
    std::vector<Instant> points;
    for (const Value& v : a.items) points.push_back(to_instant_value(v, "checkpoints"));
    in.ready();
    limit_if(points.size() > 1000, "checkpoints");
    limit_if(product_above((long long)log.size(), (long long)points.size(), 10000000), "checkpoints");
    check_store_nesting(log);
    check_store(log, std::vector<std::optional<Instant>>(points.begin(), points.end()));
    const auto replay = store_replay(log, points);
    out.values.key("snapshots");
    out.values.begin_array();
    for (const ReplayPoint& p : replay) {
        out.values.begin_object();
        out.key_string("as_of", format_instant(p.as_of));
        out.values.key("row_count");
        out.values.integer((long long)p.row_count);
        out.key_string("snapshot_id", p.snapshot_id);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_string("head", store_chain(log).head);
}

void op_store_chain(const In& in, Out& out) {
    const auto log = log_of(in);
    in.ready();
    check_store_nesting(log);
    check_store(log, {});
    const Chain c = store_chain(log);
    out.key_string("head", c.head);
    out.values.key("hashes");
    out.values.begin_array();
    for (const string& h : c.hashes) out.values.string(h);
    out.values.end_array();
}

#include "ops_stage_b.inc"
#include "ops_c_all.inc"
#include "ops_stage_d.inc"
#include "ops_bonds.inc"
#include "ops_inflation.inc"
#include "ops_misc_d.inc"
#include "ops_equity_d.inc"
#include "ops_credit.inc"
#include "ops_r2.inc"
#include "ops_e1.inc"
#include "ops_e3.inc"
#include "ops_e7.inc"

// ---- dispatch ----

using Handler = void (*)(const In&, Out&);

const std::map<string, Handler, std::less<>>& table() {
    static const std::map<string, Handler, std::less<>> t = {
#include "ops_c_table.inc"
#include "ops_d_table.inc"
        {"fx.atm.strike", op_fx_atm_strike},
        {"fx.delta.from_strike", op_fx_delta_from_strike},
        {"fx.delta.to_strike", op_fx_delta_to_strike},
        {"fx.option.price", op_fx_option_price},
        {"fx.smile.from_quotes", op_fx_smile_from_quotes},
        {"vol.forward.vol", op_forward_vol},
        {"vol.local.dupire", op_local_dupire},
        {"vol.smile.dynamics", op_smile_dynamics},
        {"vol.ssvi.to_svi", op_ssvi_to_svi},
        {"vol.svi.fit_surface", op_svi_fit_surface},
        {"vol.svi.surface_check", op_svi_surface_check},
        {"vol.volofvol.measure", op_volofvol},
        {"vol.garch.fit", op_garch_fit},
        {"vol.garch.forecast", op_garch_forecast},
        {"vol.garch.loglik", op_garch_loglik},
        {"vol.varswap.fair_strike", op_varswap_fair},
        {"vol.varswap.realized", op_varswap_realized},
        {"vol.vix.index", op_vix_index},
        {"vol.vix.term_variance", op_vix_term},
        {"calib.check_bid_ask", op_check_bid_ask},
        {"calib.curve_report", op_curve_report},
        {"calib.fit", op_calib_fit},
        {"core.conventions.lookup", op_conventions_lookup},
        {"core.units.add_money", op_add_money},
        {"core.units.convert", op_units_convert},
        {"core.units.round_money", op_round_money},
        {"fx.curve.implied", op_fx_implied},
        {"fx.forward.outright", op_fx_outright},
        {"fx.forward.pv", op_fx_forward_pv},
        {"fx.spot_date", op_fx_spot_date},
        {"fx.swap.pv", op_fx_swap_pv},
        {"hedge.solve", op_hedge_solve},
        {"risk.curve.jacobian", op_risk_jacobian},
        {"risk.curve.key_rate", op_risk_key_rate},
        {"risk.curve.par", op_risk_par},
        {"risk.pnl.explain", op_pnl_explain},
        {"hedge.spread_cost", op_spread_cost},
        {"rates.basis.spread", op_basis_spread},
        {"rates.curve.discount", op_curve_discount},
        {"rates.curve.forward", op_curve_forward},
        {"rates.fra.pv", op_fra_pv},
        {"rates.ois.bootstrap", op_ois_bootstrap},
        {"rates.ois.compound", op_ois_compound},
        {"rates.ois.pv", op_ois_pv},
        {"rates.projection.bootstrap", op_projection_bootstrap},
        {"rates.schedule.generate", op_schedule},
        {"rates.swap.pv", op_swap_pv},
        {"risk.cashflows", op_cashflows},
        {"risk.ois.dv01", op_ois_dv01},
        {"usecase.fx_hedge", op_usecase_fx},
        {"usecase.rates_hedge", op_usecase_rates},
        {"core.calendar.add_business_days", op_add_business_days},
        {"core.calendar.add_tenor", op_add_tenor},
        {"core.calendar.adjust", op_adjust},
        {"core.calendar.business_days_between", op_business_days_between},
        {"core.calendar.holidays", op_holidays},
        {"core.calendar.is_business_day", op_is_business_day},
        {"core.compounding.convert", op_convert},
        {"core.compounding.discount_factor", op_discount_factor},
        {"core.cos.european", op_cos},
        {"core.data.check_quotes", op_check_quotes},
        {"core.daycount.year_fraction", op_year_fraction},
        {"core.diff.central", op_central},
        {"core.integrate.adaptive_simpson", op_adaptive_simpson},
        {"core.integrate.gauss_kronrod", op_gauss_kronrod},
        {"core.integrate.gauss_legendre", op_gauss_legendre},
        {"core.integrate.simpson", op_simpson},
        {"core.integrate.trapezoid", op_trapezoid},
        {"core.interp.evaluate", op_interp},
        {"core.interp.monotone_convex", op_monotone_convex},
        {"core.linalg.cholesky", op_cholesky},
        {"core.linalg.eigen_symmetric", op_eigen},
        {"core.linalg.solve", op_solve},
        {"core.mc.gbm_european", op_mc},
        {"core.pde.bs_european", op_pde},
        {"core.rng.inverse_normal", op_inverse_normal},
        {"core.rng.next_u64", op_next_u64},
        {"core.rng.normals", op_normals},
        {"core.rng.set_state_next_u64", op_set_state},
        {"core.rng.uniforms", op_uniforms},
        {"core.root.bisection", op_bisection},
        {"core.root.brent", op_brent},
        {"core.root.newton", op_newton},
        {"core.snapshot.hash", op_snapshot_hash},
        {"core.sobol.points", op_sobol},
        {"core.stats.covariance", op_covariance},
        {"core.stats.normal", op_normal},
        {"core.stats.ols", op_ols},
        {"core.stats.quantile", op_quantile},
        {"core.stats.summary", op_summary},
        {"core.store.chain", op_store_chain},
        {"core.store.latest", op_store_latest},
        {"core.store.query_as_of", op_store_query},
        {"core.store.replay", op_store_replay},
        {"core.store.snapshot", op_store_snapshot},
        {"core.time.business_date", op_business_date},
        {"core.time.to_instant", op_to_instant},
        {"core.time.to_local", op_to_local},
        {"core.time.utc_offset", op_utc_offset},
        {"core.ts.ar1", op_ar1},
        {"core.ts.autocorrelation", op_autocorrelation},
        {"core.ts.ewma_variance", op_ewma},
        {"core.ts.forward_fill", op_forward_fill},
        {"core.ts.ljung_box", op_ljung_box},
        {"core.ts.resample_last", op_resample_last},
        {"core.ts.returns", op_returns},
        {"core.ts.rolling", op_rolling},
    };
    return t;
}

bool valid_version(string_view s) {
    const auto dot = s.find('.');
    const auto digits = [](string_view p) {
        return !p.empty() && std::all_of(p.begin(), p.end(), [](char c) { return c >= '0' && c <= '9'; });
    };
    return dot != string_view::npos && digits(s.substr(0, dot)) && digits(s.substr(dot + 1));
}

bool valid_operation(string_view s) {
    bool any_dot = false;
    char previous = '.';
    for (const char c : s) {
        if (c == '.') {
            if (previous == '.') return false;
            any_dot = true;
        } else if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) {
            return false;
        }
        previous = c;
    }
    return any_dot && previous != '.';
}

bool oversized(const Value& v) {
    if (v.items.size() > 100000) return true;
    return std::ranges::any_of(v.items, oversized) ||
           std::ranges::any_of(v.members, [](const json::Member& m) { return oversized(m.second); });
}

string error_json(const string& case_id, const Error& e) {
    string s = R"({"schema_version":"1.0","case_id":)";
    json::append_string(s, case_id);
    s += R"(,"status":"error","error":{"code":)";
    json::append_string(s, e.code());
    s += R"(,"message":)";
    json::append_string(s, e.what());
    if (!e.field().empty()) {
        s += R"(,"field":)";
        json::append_string(s, e.field());
    }
    s += R"(},"diagnostics":{}})";
    return s;
}

// Checks the envelope and returns the inputs.
const Value& check_envelope(const json::Parsed& p, Handler& handler) {
    if (p.duplicate_key) throw Error("E_PARSE", "duplicate key");
    if (p.number_overflow) throw Error("E_SCHEMA", "a number overflows binary64");
    if (p.lone_surrogate) throw Error("E_SCHEMA", "lone surrogate escape");
    const Value& doc = p.value;
    if (doc.kind != Kind::Object) throw Error("E_SCHEMA", "a case must be an object");
    for (const auto& [k, v] : doc.members)
        if (k != "schema_version" && k != "case_id" && k != "operation" && k != "inputs") schema(k, "unexpected key");
    const In in(doc);
    if (!valid_version(in.text("schema_version"))) schema("schema_version", "bad version");
    if (in.text("case_id").empty()) schema("case_id", "empty");
    const string& operation = in.text("operation");
    if (!valid_operation(operation)) schema("operation", "bad name");
    const Value& inputs = in.need("inputs");
    if (inputs.kind != Kind::Object) schema("inputs", "expected an object");
    const auto it = table().find(operation);
    if (it == table().end()) throw Error("E_UNSUPPORTED_OPERATION", "not in this build: " + operation, "operation");
    handler = it->second;
    return inputs;
}

}  // namespace

CaseResult run_case(string_view text) {
    string case_id = "unknown";
    try {
        if (json::deeper_than(text, 80)) throw Error("E_LIMIT", "the case is nested above 80 levels");
        const json::Parsed parsed = json::parse(text);
        if (const Value* id = parsed.value.find("case_id"); id && id->kind == Kind::String && !id->text.empty())
            case_id = id->text;
        Handler handler = nullptr;
        const Value& inputs = check_envelope(parsed, handler);
        const bool big = oversized(inputs);
        Out out;
        out.values.begin_object();
        out.diagnostics.begin_object();
        handler(In(inputs, big), out);
        In(inputs, big).ready();  // for a handler with no work to guard
        out.values.end_object();
        out.diagnostics.end_object();
        string s = R"({"schema_version":"1.0","case_id":)";
        json::append_string(s, case_id);
        s += R"(,"status":"ok","outputs":)" + out.values.str() + R"(,"diagnostics":)" + out.diagnostics.str() + "}";
        return {std::move(s), true};
    } catch (const Error& e) {
        return {error_json(case_id, e), false};
    }
}

std::vector<string> operations() {
    std::vector<string> names;
    for (const auto& [name, handler] : table()) names.push_back(name);
    return names;
}

string operations_json() {
    json::Writer w;
    w.begin_array();
    for (const string& name : operations()) w.string(name);
    w.end_array();
    return w.str();
}

string version_json() {
    json::Writer w;
    w.begin_object();
    w.key("language");
    w.string("cpp");
    w.key("implementation_version");
    w.string(QF_VERSION);
    w.key("contract_version");
    w.string("1.0.0");
    w.key("toolchain");
    #if defined(__clang__)
    w.string("Clang " __clang_version__);
#else
    w.string("GCC " __VERSION__);
#endif
    w.end_object();
    return w.str();
}

}  // namespace quantforge::cli
