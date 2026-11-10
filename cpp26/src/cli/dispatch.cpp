#include "dispatch.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <initializer_list>
#include <limits>
#include <map>
#include <span>
#include <stdexcept>
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
#include "quantforge/core/multicurve.hpp"
#include "quantforge/core/bonds.hpp"
#include "quantforge/core/rates_vol.hpp"
#include "quantforge/core/commodity.hpp"
#include "quantforge/core/mbs.hpp"
#include "quantforge/core/inflation.hpp"
#include "quantforge/core/equity_carry.hpp"
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
#include "quantforge/core/credit_options.hpp"
#include "quantforge/core/exotics.hpp"
#include "quantforge/core/correlation.hpp"
#include "quantforge/core/heston.hpp"
#include "quantforge/core/vol_stats.hpp"
#include "quantforge/core/joint.hpp"
#include "quantforge/core/risk_f3.hpp"
#include "quantforge/core/risk_f4.hpp"
#include "quantforge/core/book.hpp"
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

// The first non-finite Real read in the current case (ruling F-1, F-2). In::ready() raises it as E_DOMAIN,
// after E_SCHEMA and E_LIMIT have had their turn and before any rule check. Reset by run_case.
thread_local std::optional<string> first_non_finite;

double to_real(const Value& v, string_view key) {
    double x;
    if (v.kind == Kind::Number) x = v.number;
    else if (v.kind == Kind::String && v.text == "NaN") x = std::numeric_limits<double>::quiet_NaN();
    else if (v.kind == Kind::String && v.text == "Infinity") x = std::numeric_limits<double>::infinity();
    else if (v.kind == Kind::String && v.text == "-Infinity") x = -std::numeric_limits<double>::infinity();
    else schema(key, "expected a number");
    if (!std::isfinite(x) && !first_non_finite) first_non_finite = string(key);
    return x;
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
        if (first_non_finite) throw Error("E_DOMAIN", *first_non_finite + " must be finite", *first_non_finite);
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

// ---- the verb registry ----

using Handler = void (*)(const In&, Out&);

struct Entry {
    string_view verb;
    Handler handler;
};

// Shared readers first, then one file per domain. Each domain file ends with its <domain>_ops array.
#include "readers.inc"
#include "ops_dates.inc"
#include "ops_data.inc"
#include "ops_numerics.inc"
#include "ops_rates.inc"
#include "ops_fx.inc"
#include "ops_calibration.inc"
#include "ops_risk.inc"
#include "ops_hedge.inc"
#include "ops_usecase.inc"
#include "ops_equity.inc"
#include "ops_vol.inc"
#include "ops_bonds.inc"
#include "ops_inflation.inc"
#include "ops_commodity.inc"
#include "ops_mbs.inc"
#include "ops_credit.inc"
#include "ops_exotics.inc"
#include "ops_risk_f3.inc"
#include "ops_risk_f4.inc"
#include "ops_book.inc"

// Every verb this build runs. The operations command, and dispatch, are generated from this list alone.
constexpr std::span<const Entry> registry[] = {
    dates_ops,
    data_ops,
    numerics_ops,
    rates_ops,
    fx_ops,
    calibration_ops,
    risk_ops,
    hedge_ops,
    usecase_ops,
    equity_ops,
    vol_ops,
    bonds_ops,
    inflation_ops,
    commodity_ops,
    mbs_ops,
    credit_ops,
    exotics_ops,
    risk_f3_ops,
    risk_f4_ops,
    book_ops,
};

// Built on first use, never at static initialisation, so no order between translation units matters.
const std::map<string, Handler, std::less<>>& table() {
    static const std::map<string, Handler, std::less<>> t = [] {
        std::map<string, Handler, std::less<>> m;
        for (const auto domain : registry)
            for (const Entry& e : domain)
                if (!m.emplace(string(e.verb), e.handler).second) throw std::logic_error("verb registered twice: " + string(e.verb));
        return m;
    }();
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
        first_non_finite.reset();
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
