// Stage H multi-asset microstructure (H-22 equities, H-23 FX spot, H-24 rates): a port of
// python/quantforge_core/multiasset.py, matching it value for value and error for error.
// Specs: specifications/09-microstructure/asset-conventions.md, 10-execution/auction.md, fx-rfq-venue.md,
// rates-futures-venue.md; rulings specifications/stage-h-rulings-multiasset.md.
//
// Error order HR-66: every function parses its fields (E_SCHEMA) in the reference's order before it checks a
// structure (E_INPUT) or a domain (E_DOMAIN); E_LIMIT is an exact value outside HR-57. Prices, quantities and
// fees are ExactDecimal (HR-12). The two prices that need a division (bond, bill) are exact rationals over a
// small unsigned big integer, rounded half-even: the bond as the reference does, first to 30 decimals (then
// range-checked) and then to 9; the bill straight to 9.
#include "quantforge/core/multiasset.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <initializer_list>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "quantforge/core/dates.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/microstructure.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/root.hpp"

// The accessors return references into the inputs document, never into their temporary path arguments; GCC
// cannot see that and warns on every call that builds a path.
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic ignored "-Wdangling-reference"
#endif

namespace quantforge::micro::ma {
namespace {

using json::Kind;
using D = ExactDecimal;
using std::string;
using std::string_view;

[[noreturn]] void fail(const char* code, const string& path, const string& why) { throw Error(code, path + ": " + why, path); }

// ------------------------------------------------------------------ parsing helpers (E_SCHEMA)
// A key present with null counts as present, as `key in raw` does in the reference.

const Value& obj(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::Object) fail("E_SCHEMA", path, "not an object");
    return *v;
}

const Value& need(const Value& o, string_view key, const string& prefix = "") {
    const Value* v = o.find(key);
    if (v == nullptr) fail("E_SCHEMA", prefix + string(key), "missing");
    return *v;
}

D input_dec(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String || !D::well_formed(v->text)) fail("E_SCHEMA", path, "not a decimal string");
    return D::parse(v->text);
}

D dec(const Value& o, string_view key, const string& prefix = "") { return input_dec(&need(o, key, prefix), prefix + string(key)); }

D dec_or(const Value& o, string_view key, string_view fallback) {
    const Value* v = o.find(key);
    return v ? input_dec(v, string(key)) : D::parse(fallback);
}

long long to_int(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::Number || !v->integral) fail("E_SCHEMA", path, "not an integer");
    long long r = 0;
    const char* b = v->text.data();
    const char* e = b + v->text.size();
    const auto [p, ec] = std::from_chars(b, e, r);
    if (ec != std::errc{} || p != e) fail("E_DOMAIN", path, "integer outside the 64-bit range");
    return r;
}

long long int_need(const Value& o, string_view key, const string& prefix = "") {
    return to_int(&need(o, key, prefix), prefix + string(key));
}

long long int_or(const Value& o, string_view key, long long fallback, const string& prefix = "") {
    const Value* v = o.find(key);
    return v ? to_int(v, prefix + string(key)) : fallback;
}

bool bool_or(const Value& o, string_view key, bool fallback) {
    const Value* v = o.find(key);
    if (v == nullptr) return fallback;
    if (v->kind != Kind::Bool) fail("E_SCHEMA", string(key), "not a boolean");
    return v->boolean;
}

const string& str_need(const Value& o, string_view key, const string& prefix = "") {
    const Value& v = need(o, key, prefix);
    if (v.kind != Kind::String) fail("E_SCHEMA", prefix + string(key), "not a string");
    return v.text;
}

const string& enum_need(const Value& o, string_view key, std::initializer_list<string_view> allowed, const string& prefix = "") {
    const string& v = str_need(o, key, prefix);
    if (std::find(allowed.begin(), allowed.end(), string_view(v)) == allowed.end())
        fail("E_SCHEMA", prefix + string(key), "not an allowed value");
    return v;
}

Date to_date(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String) fail("E_SCHEMA", path, "not an ISO date");
    const auto d = parse_date(v->text);
    if (!d || year_of(*d) < 1) fail("E_SCHEMA", path, "not an ISO date");
    return *d;
}

std::set<Date> to_dates(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::Array) fail("E_SCHEMA", path, "not an array");
    std::set<Date> s;
    for (std::size_t k = 0; k < v->items.size(); ++k) s.insert(to_date(&v->items[k], path + "/" + std::to_string(k)));
    return s;
}

const Value& list_need(const Value& o, string_view key) {
    const Value& v = need(o, key);
    if (v.kind != Kind::Array) fail("E_SCHEMA", string(key), "not an array");
    return v;
}

// ------------------------------------------------------------------ decimal helpers

const D zero{};
const D one = D::integer(1);

int places(D x) {  // decimals of the normalised value (trailing zeros gone)
    const string s = x.str();
    const auto dot = s.find('.');
    return dot == string::npos ? 0 : int(s.size() - dot - 1);
}

D unit(int p) { return p == 0 ? one : D::parse("0." + string(std::size_t(p - 1), '0') + "1"); }

bool odd(D integral) {
    const string s = integral.str();
    return (s.back() - '0') % 2 != 0;
}

// `x` printed with exactly `p` decimals, rounded half-even (Decimal.quantize in the reference's context).
string at(D x, int p) {
    const D u = unit(p);
    D q = x.divide_integral(u, false);
    const D rem = x - q * u;
    const D twice = rem + rem;
    if (twice > u || (twice == u && odd(q))) q += one;
    string out;
    (q * u).fixed(p, out);
    return out;
}

long long to_ll(D integral) {
    const string s = integral.str();
    long long r = 0;
    const auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), r);
    if (ec != std::errc{} || p != s.data() + s.size()) throw Error("E_LIMIT", "integer outside the 64-bit range");
    return r;
}

void put(Writer& out, string_view k, string_view v) {
    out.key(k);
    out.string(v);
}

// ------------------------------------------------------------------ an unsigned big integer, base 10^9
// Only for the two rational prices: products of up to 1,200 powers and one long division.

struct Big {
    std::vector<std::uint32_t> d;  // little endian; empty is zero
};
constexpr std::uint32_t base = 1'000'000'000;

void trim(Big& a) {
    while (!a.d.empty() && a.d.back() == 0) a.d.pop_back();
}

Big from_digits(string_view s) {
    Big r;
    for (std::size_t end = s.size(); end > 0;) {
        const std::size_t start = end >= 9 ? end - 9 : 0;
        std::uint32_t limb = 0;
        for (std::size_t i = start; i < end; ++i) limb = limb * 10 + std::uint32_t(s[i] - '0');
        r.d.push_back(limb);
        end = start;
    }
    trim(r);
    return r;
}

Big small(std::uint64_t v) {
    Big r;
    for (; v != 0; v /= base) r.d.push_back(std::uint32_t(v % base));
    return r;
}

int cmp(const Big& a, const Big& b) {
    if (a.d.size() != b.d.size()) return a.d.size() < b.d.size() ? -1 : 1;
    for (std::size_t i = a.d.size(); i-- > 0;)
        if (a.d[i] != b.d[i]) return a.d[i] < b.d[i] ? -1 : 1;
    return 0;
}

Big add(const Big& a, const Big& b) {
    Big r;
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < std::max(a.d.size(), b.d.size()) || carry; ++i) {
        const std::uint64_t s = carry + (i < a.d.size() ? a.d[i] : 0) + (i < b.d.size() ? b.d[i] : 0);
        r.d.push_back(std::uint32_t(s % base));
        carry = s / base;
    }
    trim(r);
    return r;
}

Big sub(const Big& a, const Big& b) {  // a >= b
    Big r = a;
    std::int64_t borrow = 0;
    for (std::size_t i = 0; i < r.d.size(); ++i) {
        std::int64_t s = std::int64_t(r.d[i]) - borrow - (i < b.d.size() ? std::int64_t(b.d[i]) : 0);
        borrow = s < 0;
        if (s < 0) s += base;
        r.d[i] = std::uint32_t(s);
    }
    trim(r);
    return r;
}

Big mul(const Big& a, const Big& b) {
    if (a.d.empty() || b.d.empty()) return {};
    std::vector<std::uint64_t> t(a.d.size() + b.d.size() + 1, 0);
    for (std::size_t i = 0; i < a.d.size(); ++i) {
        std::uint64_t carry = 0;
        for (std::size_t j = 0; j < b.d.size() || carry; ++j) {
            const std::uint64_t cur = t[i + j] + carry + (j < b.d.size() ? std::uint64_t(a.d[i]) * b.d[j] : 0);
            t[i + j] = cur % base;
            carry = cur / base;
        }
    }
    Big r;
    r.d.assign(t.begin(), t.end());
    trim(r);
    return r;
}

Big pow10b(int n) {
    Big r = small(1);
    for (; n >= 9; n -= 9) r = mul(r, small(base));
    std::uint64_t p = 1;
    for (int i = 0; i < n; ++i) p *= 10;
    return mul(r, small(p));
}

string digits(const Big& a) {
    if (a.d.empty()) return "0";
    string s = std::to_string(a.d.back());
    for (std::size_t i = a.d.size() - 1; i-- > 0;) {
        const string limb = std::to_string(a.d[i]);
        s += string(9 - limb.size(), '0') + limb;
    }
    return s;
}

// round_half_even(n * 10^p / den), den > 0, by long division.
Big round_ratio(const Big& n, const Big& den, int p) {
    Big num = mul(n, pow10b(p));
    Big q;
    if (cmp(num, den) >= 0) {
        std::vector<Big> steps{den};  // den * 10^k, k = 0.. while it does not exceed num
        while (true) {
            Big next = mul(steps.back(), small(10));
            if (cmp(next, num) > 0) break;
            steps.push_back(std::move(next));
        }
        for (std::size_t k = steps.size(); k-- > 0;) {
            std::uint32_t digit = 0;
            while (cmp(num, steps[k]) >= 0) {
                num = sub(num, steps[k]);
                ++digit;
            }
            q = add(mul(q, small(10)), small(digit));
        }
    }
    const Big twice = add(num, num);
    const int c = cmp(twice, den);
    if (c > 0 || (c == 0 && !q.d.empty() && q.d[0] % 2 == 1)) q = add(q, small(1));
    return q;
}

// (negative, magnitude digits, scale) of an exact decimal.
struct Parts {
    bool negative;
    Big mag;
    int scale;
};
Parts parts(D x) {
    string s = x.str();
    const bool neg = s.front() == '-';
    if (neg) s.erase(0, 1);
    const auto dot = s.find('.');
    int scale = 0;
    if (dot != string::npos) {
        scale = int(s.size() - dot - 1);
        s.erase(dot, 1);
    }
    return {neg, from_digits(s), scale};
}

// `q * 10^-scale` with the sign, no trailing zeros, "0" for zero (HR-12).
string fmt_scaled(bool negative, const Big& q, int scale) {
    string s = digits(q);
    if (s == "0") return "0";
    if ((int)s.size() <= scale) s.insert(0, std::size_t(scale + 1) - s.size(), '0');
    if (scale > 0) {
        s.insert(s.size() - std::size_t(scale), ".");
        while (s.back() == '0') s.pop_back();
        if (s.back() == '.') s.pop_back();
    }
    return negative ? "-" + s : s;
}

// ------------------------------------------------------------------ equities (H-22)

const D fee_cap_current = D::parse("0.001");
const D fee_cap_old = D::parse("0.003");

bool current_rules(const Value& raw) {
    const Value* cv = raw.find("compliance_date");
    const Value dflt = [] {
        Value v;
        v.kind = Kind::String;
        v.text = string(rule_2024_compliance);
        return v;
    }();
    const Date cd = to_date(cv ? cv : &dflt, "compliance_date");
    const Value* as_of = raw.find("as_of");
    return as_of == nullptr || to_date(as_of, "as_of") >= cd;
}

using Table = std::vector<std::pair<D, D>>;

Table tick_table(const Value& raw) {
    string tier = "PENNY";
    if (const Value* t = raw.find("tick_tier")) {
        if (t->kind != Kind::String || (t->text != "PENNY" && t->text != "HALF_PENNY"))
            fail("E_SCHEMA", "tick_tier", "not PENNY or HALF_PENNY");
        tier = t->text;
    }
    const bool current = current_rules(raw);
    const bool half = tier == "HALF_PENNY";
    if (half && !current) fail("E_INPUT", "tick_tier", "HALF_PENNY before the compliance date");
    if (half && raw.find("tick_table")) fail("E_INPUT", "tick_tier", "HALF_PENNY with an explicit tick_table");
    Table rows;
    if (const Value* v = raw.find("tick_table")) {
        if (v->kind != Kind::Array) fail("E_SCHEMA", "tick_table", "not an array");
        for (std::size_t k = 0; k < v->items.size(); ++k) {
            const Value& r = v->items[k];
            if (r.kind != Kind::Array || r.items.size() != 2) fail("E_SCHEMA", "tick_table", "not a [floor, tick] pair");
            const string p = "tick_table/" + std::to_string(k) + "/";
            const D f = input_dec(&r.items[0], p + "0");
            rows.emplace_back(f, input_dec(&r.items[1], p + "1"));
        }
    } else {
        rows = {{zero, D::parse("0.0001")}, {D::parse("1.00"), D::parse(half ? "0.005" : "0.01")}};  // [REGNMS-612]
    }
    bool ok = !rows.empty() && rows[0].first == zero;
    for (std::size_t i = 1; ok && i < rows.size(); ++i) ok = rows[i - 1].first < rows[i].first;
    if (!ok) fail("E_INPUT", "tick_table", "floors must start at 0 and increase");
    for (const auto& r : rows)
        if (r.second.sign() <= 0) fail("E_DOMAIN", "tick_table", "ticks must be positive");
    return rows;
}

D tick_at(const Table& t, D price) {
    D tick = t.front().second;
    for (const auto& [f, k] : t)
        if (f <= price) tick = k;
    return tick;
}

string_view label_eq(const Value& raw) {
    const Value* v = raw.find("data_source");
    if (v == nullptr) return eq_label;
    if (v->kind != Kind::String || (v->text != "SIMULATED" && v->text != "IEX"))
        fail("E_SCHEMA", "data_source", "not SIMULATED or IEX");
    return v->text == "IEX" ? iex_label : eq_label;
}

bool good(Date d, const std::set<Date>& hol) {
    const unsigned w = weekday_of(d);
    return w >= 1 && w <= 5 && !hol.contains(d);
}

Date add_good(Date d, long long n, const std::function<bool(Date)>& ok) {
    for (long long i = 0; i < n; ++i) {
        d += std::chrono::days{1};
        int k = 0;
        for (; k < max_calendar_days; ++k) {
            if (ok(d)) break;
            d += std::chrono::days{1};
        }
        if (k == max_calendar_days) fail("E_DOMAIN", "holidays", "no business day within ten years");
    }
    return d;
}

// ------------------------------------------------------------------ FX (H-23)

constexpr string_view ccy_order[] = {"EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"};  // HR-88

int rank(string_view c) {
    for (int i = 0; i < 8; ++i)
        if (ccy_order[i] == c) return i;
    return -1;
}

std::pair<string, string> pair_of(const Value& raw) {
    const string& p = str_need(raw, "pair");
    const string b = p.substr(0, 3), q = p.size() > 3 ? p.substr(3) : string();
    if (p.size() != 6 || rank(b) < 0 || rank(q) < 0 || b == q) fail("E_INPUT", "pair", "not a pair of two listed currencies");
    if (rank(b) > rank(q)) fail("E_INPUT", "pair", "base must rank before quote (HR-88)");
    return {b, q};
}

D pip(const string& quote) { return D::parse(quote == "JPY" ? "0.01" : "0.0001"); }
D per_pip(const string& quote) { return D::integer(quote == "JPY" ? 100 : 10000); }

// ------------------------------------------------------------------ rates (H-24)

const D one_128th = D::parse("0.0078125");

// HR-109: CME convention, third digit in quarter-32nds [CME-32NDS, unverified]: 0, 2, 5, 7 = 0, 1/4, 1/2,
// 3/4 and "+" = 1/2. Anything else, the shape included, is E_SCHEMA.
D parse_32nds(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String) fail("E_SCHEMA", path, "not a string");
    const string& t = v->text;
    std::size_t i = 0;
    while (i < t.size() && t[i] >= '0' && t[i] <= '9') ++i;
    const std::size_t h_end = i;
    const auto isd = [&](std::size_t j) { return j < t.size() && t[j] >= '0' && t[j] <= '9'; };
    const bool shape = h_end > 0 && h_end < t.size() && t[h_end] == '-' && isd(h_end + 1) && isd(h_end + 2) &&
                       (t.size() == h_end + 3 ||
                        (t.size() == h_end + 4 && string_view("0257+").find(t[h_end + 3]) != string_view::npos));
    if (!shape) fail("E_SCHEMA", path, "not H-FF[q] with q in 0, 2, 5, 7, + (HR-109)");
    const int ff = (t[h_end + 1] - '0') * 10 + (t[h_end + 2] - '0');
    if (ff > 31) fail("E_DOMAIN", path, "32nds above 31");
    int q = 0;
    if (t.size() == h_end + 4) {
        const char c = t[h_end + 3];
        q = c == '2' ? 1 : (c == '5' || c == '+') ? 2 : c == '7' ? 3 : 0;
    }
    return D::parse(string_view(t).substr(0, h_end)) + D::integer(4 * ff + q) * one_128th;
}

string format_32nds(D x, long long res) {
    if (res != 32 && res != 64 && res != 128) fail("E_DOMAIN", "resolution", "resolution not 32, 64 or 128");
    if (x.sign() < 0 || !(x * D::integer(res)).multiple_of(one)) fail("E_DOMAIN", "value", "value not on the requested grid");
    const D h = x.divide_integral(one, false);
    const long long quarters = to_ll((x - h) * D::integer(128));
    const long long ff = quarters / 4, q = quarters % 4;
    static constexpr const char* text[] = {"", "2", "+", "7"};
    return h.str() + "-" + (ff < 10 ? "0" : "") + std::to_string(ff) + text[q];
}

std::pair<D, D> contract(const Value& raw) {
    const Value* cv = raw.find("contract");
    Value zn;
    if (cv == nullptr) {
        zn.kind = Kind::Object;
        Value s;
        s.kind = Kind::String;
        s.text = "ZN";
        zn.members.push_back({"symbol", s});
        cv = &zn;
    }
    const Value& c = obj(cv, "contract");
    const Value* sym = c.find("symbol");
    if (sym && sym->kind != Kind::Null && sym->kind != Kind::String) fail("E_SCHEMA", "contract/symbol", "not a string");
    const string s = sym && sym->kind == Kind::String ? sym->text : "";
    std::optional<string> face_d, tick_d;  // HR-91, [CME-ZN] and [CME-ZB]
    if (s == "ZN") face_d = "100000", tick_d = "0.015625";
    if (s == "ZB") face_d = "100000", tick_d = "0.03125";
    const auto field = [&](string_view key, const std::optional<string>& d) {
        const Value* v = c.find(key);
        if (v == nullptr && d) return D::parse(*d);
        return input_dec(v, "contract/" + string(key));
    };
    const D face = field("face", face_d);
    const D tick = field("tick", tick_d);
    if (face.sign() <= 0 || tick.sign() <= 0) fail("E_DOMAIN", "contract", "contract face and tick must be positive");
    return {face, tick};
}

D tick_value(D face, D tick) { return face * tick * D::parse("0.01"); }

long long fut_ticks(const Value* v, D tick, const string& path) {
    const bool text = v != nullptr && v->kind == Kind::String && v->text.find('-', 1) != string::npos;
    const D x = text ? parse_32nds(v, path) : input_dec(v, path);
    if (x.sign() < 0 || !x.multiple_of(tick)) fail("E_DOMAIN", path, "price off the contract grid");
    return to_ll(x.divide_integral(tick, false));
}

// Writes a parsed value; integral numbers keep their spelling.
void emit(Writer& out, const Value& v) {
    switch (v.kind) {
        case Kind::Number:
            if (v.integral) out.integer(std::stoll(v.text));
            else out.real(v.number);
            break;
        case Kind::Array:
            out.begin_array();
            for (const Value& x : v.items) emit(out, x);
            out.end_array();
            break;
        case Kind::Object:
            out.begin_object();
            for (const auto& m : v.members) {
                out.key(m.first);
                emit(out, m.second);
            }
            out.end_object();
            break;
        default: out.value(v);
    }
}

}  // namespace

// ------------------------------------------------------------------ equities (H-22)

void eq_round_price(const Value& raw, Writer& out) {
    const D price = dec(raw, "price");
    const bool buy = enum_need(raw, "side", {"BUY", "SELL"}) == "BUY";
    const Table table = tick_table(raw);
    if (price.sign() <= 0) fail("E_DOMAIN", "price", "price must be positive");
    const D tick = tick_at(table, price);
    const D r = price.divide_integral(tick, !buy) * tick;
    // A sell rounded up across a floor lands on the floor, which is on both grids (HR-81).
    put(out, "price", at(r, places(tick_at(table, r))));
}

void eq_fee_check(const Value& raw, Writer& out) {
    const D price = dec(raw, "price");
    const D fee = dec(raw, "taker_fee");
    const bool check = bool_or(raw, "cap_check", true);
    const D cap_rate = current_rules(raw) ? fee_cap_current : fee_cap_old;  // [REGNMS-610]
    if (price.sign() <= 0) fail("E_DOMAIN", "price", "price must be positive");
    const D cap = price >= one ? cap_rate : cap_rate * price;
    if (check && fee > cap) fail("E_DOMAIN", "taker_fee", "taker_fee above the Rule 610 cap");
    put(out, "cap", cap.str());
    put(out, "taker_fee", fee.str());
}

void eq_round_lot(const Value& raw, Writer& out) {
    const D price = dec(raw, "price");
    const bool current = current_rules(raw);
    if (price.sign() <= 0) fail("E_DOMAIN", "price", "price must be positive");
    long long lot = 100;
    if (current) {  // amended Reg NMS 242.600(b)(93)
        if (price <= D::integer(250)) lot = 100;
        else if (price <= D::integer(1000)) lot = 40;
        else if (price <= D::integer(10000)) lot = 10;
        else lot = 1;
    }
    out.key("round_lot");
    out.integer(lot);
}

void eq_settle_date(const Value& raw, Writer& out) {
    const Date trade = to_date(&need(raw, "trade_date"), "trade_date");
    const long long lag = int_or(raw, "settle_lag", 1);
    const Value* hv = raw.find("holidays");
    const std::set<Date> hol = hv ? to_dates(hv, "holidays") : std::set<Date>{};
    if (lag < 0 || lag > 30) fail("E_DOMAIN", "settle_lag", "settle_lag outside 0..30");
    const Date s = add_good(trade, lag, [&](Date d) { return good(d, hol); });
    put(out, "settle_date", format_date(s));
}

// ------------------------------------------------------------------ equity auction (HR-84, HR-96, HR-101)

namespace {
struct AOrder {
    string id;
    bool buy;
    std::optional<D> limit;  // empty for MARKET
    long long qty, seq;
    bool on_close;
};
struct Cand {
    D px;
    long long vol, imb;
};
D abs_d(D x) { return x.sign() < 0 ? -x : x; }
long long checked_add(long long a, long long b) {
    long long r;
    if (__builtin_add_overflow(a, b, &r)) throw Error("E_LIMIT", "auction quantity above the 64-bit range", "orders");
    return r;
}
}  // namespace

void auction_uncross(const Value& raw, Writer& out) {
    const string_view label = label_eq(raw);
    const D tick = dec(raw, "tick_size");
    const D ref = dec(raw, "ref_price");
    enum_need(raw, "phase", {"OPEN", "CLOSE"});
    string tie = "CBOE";
    if (const Value* t = raw.find("tie_break")) {
        if (t->kind != Kind::String || (t->text != "CBOE" && t->text != "IEX")) fail("E_SCHEMA", "tie_break", "not CBOE or IEX");
        tie = t->text;
    }
    const Value& orders = list_need(raw, "orders");
    if ((long long)orders.items.size() > max_auction_orders) fail("E_LIMIT", "orders", "more than 10,000,000 orders");
    std::vector<AOrder> parsed;
    long long nb = 0, ns = 0;
    for (std::size_t k = 0; k < orders.items.size(); ++k) {
        const string p = "orders/" + std::to_string(k) + "/";
        const Value& o = obj(&orders.items[k], p.substr(0, p.size() - 1));
        const bool buy = enum_need(o, "side", {"BUY", "SELL"}, p) == "BUY";
        const Value& lim = need(o, "limit", p);
        std::optional<D> limit;
        if (!(lim.kind == Kind::String && lim.text == "MARKET")) limit = input_dec(&lim, p + "limit");
        const long long qty = int_need(o, "qty", p);
        bool on_close = false;
        if (const Value* oc = o.find("on_close")) {
            if (oc->kind != Kind::Bool) fail("E_SCHEMA", p + "on_close", "not a boolean");
            on_close = oc->boolean;
        }
        (buy ? nb : ns) += 1;
        string id = buy ? "b" + std::to_string(nb) : "a" + std::to_string(ns);
        if (const Value* iv = o.find("id")) {
            if (iv->kind != Kind::String) fail("E_SCHEMA", p + "id", "not a string");
            id = iv->text;
        }
        const long long seq = int_or(o, "seq", (long long)k + 1, p);
        parsed.push_back({id, buy, limit, qty, seq, on_close});
    }
    {
        std::set<string> ids;
        for (const auto& o : parsed) ids.insert(o.id);
        if (ids.size() != parsed.size()) fail("E_INPUT", "orders", "duplicate order id");
    }
    if (tick.sign() <= 0) fail("E_DOMAIN", "tick_size", "tick_size must be positive");
    if (ref.sign() <= 0) fail("E_DOMAIN", "ref_price", "ref_price must be positive");
    for (std::size_t k = 0; k < parsed.size(); ++k) {
        const auto& o = parsed[k];
        if (o.qty <= 0) fail("E_DOMAIN", "orders", "orders/" + std::to_string(k) + ": qty must be positive");
        if (o.limit && (o.limit->sign() <= 0 || !o.limit->multiple_of(tick)))
            fail("E_DOMAIN", "orders", "orders/" + std::to_string(k) + ": limit not a positive tick multiple");
    }
    const int dp = places(tick);
    std::vector<AOrder> buys, sells;
    for (const auto& o : parsed) (o.buy ? buys : sells).push_back(o);
    std::stable_sort(buys.begin(), buys.end(), [](const AOrder& a, const AOrder& b) {
        if (a.limit.has_value() != b.limit.has_value()) return !a.limit.has_value();
        if (a.limit && !(*a.limit == *b.limit)) return *b.limit < *a.limit;
        return a.seq < b.seq;
    });
    std::stable_sort(sells.begin(), sells.end(), [](const AOrder& a, const AOrder& b) {
        if (a.limit.has_value() != b.limit.has_value()) return !a.limit.has_value();
        if (a.limit && !(*a.limit == *b.limit)) return *a.limit < *b.limit;
        return a.seq < b.seq;
    });
    std::optional<D> lo, hi;
    for (const auto& o : parsed)
        if (o.limit) {
            if (!lo || *o.limit < *lo) lo = o.limit;
            if (!hi || *hi < *o.limit) hi = o.limit;
        }
    std::optional<Cand> best;
    if (!buys.empty() && !sells.empty() && lo) {
        const D count = (*hi - *lo).divide_integral(tick, false) + one;
        if (count > D::integer(max_auction_candidates)) fail("E_LIMIT", "orders", "more than 1,000,000 candidate prices");
        const long long n = to_ll(count);
        std::vector<Cand> cands;
        cands.reserve(std::size_t(n));
        long long vmax = 0;
        for (long long i = 0; i < n; ++i) {
            const D px = *lo + D::integer(i) * tick;
            long long b = 0, s = 0;
            for (const auto& o : buys)
                if (!o.limit || *o.limit >= px) b = checked_add(b, o.qty);
            for (const auto& o : sells)
                if (!o.limit || *o.limit <= px) s = checked_add(s, o.qty);
            cands.push_back({px, std::min(b, s), b - s});
            vmax = std::max(vmax, std::min(b, s));
        }
        if (vmax > 0) {
            std::vector<Cand> keep;
            for (const auto& c : cands)
                if (c.vol == vmax) keep.push_back(c);
            if (tie == "CBOE") {
                long long imin = -1;
                for (const auto& c : keep) imin = imin < 0 ? std::llabs(c.imb) : std::min(imin, std::llabs(c.imb));
                std::vector<Cand> k2;
                for (const auto& c : keep)
                    if (std::llabs(c.imb) == imin) k2.push_back(c);
                const bool all_pos = std::all_of(k2.begin(), k2.end(), [](const Cand& c) { return c.imb > 0; });
                const bool all_neg = std::all_of(k2.begin(), k2.end(), [](const Cand& c) { return c.imb < 0; });
                if (all_pos) k2 = {*std::max_element(k2.begin(), k2.end(), [](const Cand& a, const Cand& b) { return a.px < b.px; })};
                else if (all_neg)
                    k2 = {*std::min_element(k2.begin(), k2.end(), [](const Cand& a, const Cand& b) { return a.px < b.px; })};
                keep = std::move(k2);
            }
            // Nearest the reference price (IEX: the reference-range midpoint), then the higher price.
            std::optional<D> dmin;
            for (const auto& c : keep)
                if (!dmin || abs_d(c.px - ref) < *dmin) dmin = abs_d(c.px - ref);
            for (const auto& c : keep)
                if (abs_d(c.px - ref) == *dmin && (!best || best->px < c.px)) best = c;
        }
    }
    std::vector<std::tuple<string, string, long long, bool>> fills, residual;  // id, price/limit, qty, buy
    std::vector<string> cancelled;
    for (const auto* side : {&buys, &sells}) {
        long long left = best ? best->vol : 0;
        for (const auto& o : *side) {
            const long long q = std::min(o.qty, left);
            if (q > 0) {
                fills.emplace_back(o.id, at(best->px, dp), q, o.buy);
                left -= q;
            }
            if (o.qty - q > 0) {
                if (!o.limit || o.on_close) cancelled.push_back(o.id);
                else residual.emplace_back(o.id, at(*o.limit, dp), o.qty - q, o.buy);
            }
        }
    }
    const auto rows = [&](string_view key, string_view price_key, const auto& v) {
        out.key(key);
        out.begin_array();
        for (const auto& [id, px, q, buy] : v) {
            out.begin_object();
            put(out, "id", id);
            put(out, price_key, px);
            out.key("qty");
            out.integer(q);
            put(out, "side", buy ? "B" : "S");
            out.end_object();
        }
        out.end_array();
    };
    out.key("cancelled");
    out.begin_array();
    for (const auto& id : cancelled) out.string(id);
    out.end_array();
    rows("fills", "price", fills);
    out.key("imbalance");
    out.integer(best ? best->imb : 0);
    put(out, "label", label);
    out.key("price");
    if (best) out.string(at(best->px, dp));
    else out.null();
    rows("residual", "limit", residual);
    out.key("volume");
    out.integer(best ? best->vol : 0);
}

// ------------------------------------------------------------------ FX spot (H-23)

void fx_pip_value(const Value& raw, Writer& out) {
    const D notional = dec(raw, "notional");
    const auto [b, q] = pair_of(raw);
    if (notional.sign() < 0) fail("E_DOMAIN", "notional", "notional must not be negative");
    put(out, "currency", q);
    put(out, "pip_value", (notional * pip(q)).str());
}

void fx_spot_date(const Value& raw, Writer& out) {
    const Date trade = to_date(&need(raw, "trade_date"), "trade_date");
    std::map<string, std::set<Date>> hol;
    if (const Value* hv = raw.find("holidays")) {
        if (hv->kind != Kind::Object) fail("E_SCHEMA", "holidays", "not an object of currency -> dates");
        for (const auto& m : hv->members) hol[m.first] = to_dates(&m.second, "holidays/" + m.first);
    }
    std::vector<string> t1{"USDCAD"};  // HR-89 [BIS-FX]
    if (const Value* tv = raw.find("t1_pairs")) {
        if (tv->kind != Kind::Array) fail("E_SCHEMA", "t1_pairs", "not an array of strings");
        t1.clear();
        for (const Value& x : tv->items) {
            if (x.kind != Kind::String) fail("E_SCHEMA", "t1_pairs", "not an array of strings");
            t1.push_back(x.text);
        }
    }
    const auto [base, quote] = pair_of(raw);
    const std::set<Date> empty;
    const auto h = [&](const string& c) -> const std::set<Date>& {
        const auto it = hol.find(c);
        return it == hol.end() ? empty : it->second;
    };
    const auto both = [&](Date d) { return good(d, h(base)) && good(d, h(quote)); };
    const auto non_usd = [&](Date d) {  // a USD-only holiday on T+1 does not stop the count
        return (base == "USD" || good(d, h(base))) && (quote == "USD" || good(d, h(quote)));
    };
    Date d;
    if (std::find(t1.begin(), t1.end(), base + quote) != t1.end()) d = add_good(trade, 1, both);
    else d = add_good(add_good(trade, 1, non_usd), 1, both);
    d = add_good(d - std::chrono::days{1}, 1, [&](Date x) { return both(x) && good(x, h("USD")); });
    put(out, "spot_date", format_date(d));
}

void fx_stream(const Value& raw, Writer& out) {
    const Value& path = list_need(raw, "mid_path");
    const D hs = dec(raw, "half_spread_pips");
    std::vector<std::pair<long long, D>> pts;
    for (std::size_t k = 0; k < path.items.size(); ++k) {
        const string p = "mid_path/" + std::to_string(k);
        const Value& x = obj(&path.items[k], p);
        const long long t = int_need(x, "time", p + "/");
        pts.emplace_back(t, dec(x, "mid", p + "/"));
    }
    const auto [b, quote] = pair_of(raw);
    const D pp = pip(quote);
    const D tick = dec_or(raw, "tick", quote == "JPY" ? "0.001" : "0.00001");
    if (pts.empty()) fail("E_INPUT", "mid_path", "mid_path is empty");
    if (tick.sign() <= 0 || hs.sign() < 0) fail("E_DOMAIN", "tick", "tick must be positive and half_spread_pips not negative");
    const int dp = places(tick);
    std::vector<std::tuple<string, string, string, long long>> quotes;
    for (const auto& [t, mid] : pts) {
        if (mid.sign() <= 0) fail("E_DOMAIN", "mid_path", "mid must be positive");
        const D bid = (mid - hs * pp).divide_integral(tick, false) * tick;
        const D ask = (mid + hs * pp).divide_integral(tick, true) * tick;
        quotes.emplace_back(at(ask, dp), at(bid, dp), mid.str(), t);
    }
    put(out, "label", fx_label);
    out.key("quotes");
    out.begin_array();
    for (const auto& [ask, bid, mid, t] : quotes) {
        out.begin_object();
        put(out, "ask", ask);
        put(out, "bid", bid);
        put(out, "mid", mid);
        out.key("time");
        out.integer(t);
        out.end_object();
    }
    out.end_array();
}

void fx_request(const Value& raw, Writer& out) {
    const Value& q = obj(&need(raw, "quote"), "quote");
    const D bid = dec(q, "bid", "quote/"), ask = dec(q, "ask", "quote/"), qmid = dec(q, "quote_mid", "quote/");
    const bool buy = enum_need(raw, "side", {"BUY", "SELL"}) == "BUY";
    const D qty = dec(raw, "qty");
    const D after = dec(raw, "mid_after");
    const D thr = dec(raw, "threshold_pips");
    const bool sym = bool_or(raw, "symmetric", true);
    const D prr = dec(raw, "p_random_reject");
    // HR-97: without `u`, u is drawn from core.rng, stream = request_index (rng.md jumps). A draw is
    // (k + 1/2) 2^-52 exactly, so u < p is decided exactly as (2k + 1) < p 2^53.
    const bool drawn = raw.find("u") == nullptr;
    D u, u_scaled;
    double uf = 0.0;
    if (drawn) {
        const Value* sv = &need(raw, "seed");
        if (sv->kind != Kind::Number || !sv->integral) fail("E_SCHEMA", "seed", "not an integer");
        const long long idx = int_need(raw, "request_index");
        std::uint64_t seed = 0;
        const char* sb = sv->text.data();
        const char* se = sb + sv->text.size();
        const auto [sp, sec] = std::from_chars(sb, se, seed);
        if (idx < 0 || sv->text.front() == '-' || sec != std::errc{} || sp != se)
            fail("E_SCHEMA", "request_index", "seed or request_index out of range");
        if (idx > 2'147'483'647) fail("E_LIMIT", "request_index", "request_index above 2^31 - 1");
        uf = Xoshiro256(seed, int(idx)).next_uniform();
        u_scaled = D::integer((long long)std::ldexp(uf, 53));
    } else {
        u = dec(raw, "u");
    }
    const D two53 = D::integer(9'007'199'254'740'992LL);
    const auto [b, quote] = pair_of(raw);
    if (bid > ask) fail("E_INPUT", "quote", "bid above ask");
    if (qty.sign() <= 0 || thr.sign() < 0 || prr.sign() < 0 || prr > one || (!drawn && (u.sign() < 0 || u >= one)))
        fail("E_DOMAIN", "u", "qty > 0, threshold >= 0, p in [0, 1], u in [0, 1)");
    const bool u_below = drawn ? u_scaled < prr * two53 : u < prr;
    const D move = (after - qmid) * per_pip(quote);
    const D adverse = buy ? move : -move;
    const char* outcome = (sym ? abs_d(move) : adverse) > thr ? "LL_PRICE" : (u_below ? "LL_RANDOM" : "FILL");
    put(out, "label", fx_label);
    put(out, "move_pips", move.str());
    put(out, "outcome", outcome);
    out.key("price");
    if (string_view(outcome) == "FILL") out.string((buy ? ask : bid).str());
    else out.null();
    if (drawn) {
        out.key("u");
        out.real(uf);
    }
}

// ------------------------------------------------------------------ rates (H-24)

void rates_parse_32nds(const Value& raw, Writer& out) {
    const D v = parse_32nds(&need(raw, "text"), "text");
    put(out, "value", v.str());
}

void rates_format_32nds(const Value& raw, Writer& out) {
    const D x = dec(raw, "value");
    const long long res = int_need(raw, "resolution");
    put(out, "text", format_32nds(x, res));
}

void rates_tick_value(const Value& raw, Writer& out) {
    const D face = dec(raw, "face"), tick = dec(raw, "tick");
    if (face.sign() <= 0 || tick.sign() <= 0) fail("E_DOMAIN", "face", "face and tick must be positive");
    put(out, "tick_value", tick_value(face, tick).str());
}

void rates_bond_price(const Value& raw, Writer& out) {
    const D c = dec(raw, "coupon"), y = dec(raw, "yield");
    const long long f = int_need(raw, "frequency"), n = int_need(raw, "periods");
    if (f != 1 && f != 2 && f != 4 && f != 12) fail("E_DOMAIN", "frequency", "frequency not 1, 2, 4 or 12");
    if (n < 1 || n > 1200) fail("E_DOMAIN", "periods", "periods outside 1..1200");
    if ((y + D::integer(f)).sign() <= 0) fail("E_DOMAIN", "yield", "yield at or below -frequency");
    // P = cpn sum_{i=1..n} g^-i + 100 g^-n, g = Gn / Gd = (f 10^sy + Y) / (f 10^sy), cpn = 100 C / (f 10^sc):
    // P = [100 C S + 100 f 10^sc Gd^n] / (f 10^sc Gn^n), S = sum_i Gd^i Gn^(n-i) (Horner: S_k = Gn S_(k-1) + Gd^k).
    const Parts cp = parts(c), yp = parts(y);
    const Big gd = mul(small(std::uint64_t(f)), pow10b(yp.scale));
    const Big gn = yp.negative ? sub(gd, yp.mag) : add(gd, yp.mag);
    Big s, gd_pow = small(1), gn_pow = small(1);
    for (long long k = 1; k <= n; ++k) {
        gd_pow = mul(gd_pow, gd);
        gn_pow = mul(gn_pow, gn);
        s = add(mul(s, gn), gd_pow);
    }
    const Big hundred = small(100);
    const Big fsc = mul(small(std::uint64_t(f)), pow10b(cp.scale));
    const Big a = mul(mul(hundred, fsc), gd_pow);
    const Big b = mul(mul(hundred, cp.mag), s);
    const Big den = mul(fsc, gn_pow);
    bool negative = false;
    Big num;
    if (!cp.negative) num = add(a, b);
    else if (cmp(a, b) >= 0) num = sub(a, b);
    else num = sub(b, a), negative = true;
    // HR-57 on the 30-decimal value (the reference's quantize then range check): at most 36 digits.
    if (cmp(num, mul(den, pow10b(37))) >= 0) throw Error("E_LIMIT", "value: decimal outside the exact range (HR-57)", "value");
    const Big q30 = round_ratio(num, den, 30);
    const string d30 = digits(q30);
    if (d30 != "0") {
        std::size_t z = 0;
        while (z < 30 && d30[d30.size() - 1 - z] == '0') ++z;
        const std::size_t sig = z < 30 ? d30.size() - z : (d30.size() > 30 ? d30.size() - 30 : 1);
        if (sig > 36) throw Error("E_LIMIT", "value: decimal outside the exact range (HR-57)", "value");
    }
    const Big q9 = round_ratio(q30, pow10b(21), 0);
    put(out, "price", fmt_scaled(negative, q9, 9));
}

void rates_bond_yield(const Value& raw, Writer& out) {
    const D c = dec(raw, "coupon"), p = dec(raw, "price");
    const long long f = int_need(raw, "frequency"), n = int_need(raw, "periods");
    if (f != 1 && f != 2 && f != 4 && f != 12) fail("E_DOMAIN", "frequency", "frequency not 1, 2, 4 or 12");
    if (n < 1 || n > 1200) fail("E_DOMAIN", "periods", "periods outside 1..1200");
    if (p.sign() <= 0) fail("E_DOMAIN", "price", "price must be positive");
    // cf = float(100 c / f): the exact quotient to 60 decimals, then correctly rounded by strtod.
    const Parts cp = parts(c);
    const Big q = round_ratio(mul(small(100), cp.mag), mul(small(std::uint64_t(f)), pow10b(cp.scale)), 60);
    const double cf = std::strtod(fmt_scaled(cp.negative, q, 60).c_str(), nullptr);
    const double pf = std::strtod(p.str().c_str(), nullptr);
    const double fd = double(f);
    const auto g = [&](double y) {
        const double d = 1.0 + y / fd;
        double s = 0.0;
        for (long long i = 1; i <= n; ++i) s += cf / std::pow(d, double(i));
        return s + 100.0 / std::pow(d, double(n)) - pf;
    };
    const double lo = -0.99 * fd, hi = 10.0;
    if (g(lo) * g(hi) > 0) fail("E_DOMAIN", "price", "no yield in (-0.99 f, 10)");
    RootOptions opt;
    opt.x_tol = 1e-12;
    out.key("yield");
    out.real(brent(g, lo, hi, opt).root);
}

void rates_bill_price(const Value& raw, Writer& out) {
    const D d = dec(raw, "discount");
    const long long days = int_need(raw, "days");
    if (days < 0 || days > 366) fail("E_DOMAIN", "days", "days outside 0..366");
    // 100 (1 - d days / 360) = (36000 10^sd - 100 Dm days) / (360 10^sd), rounded half-even to 9 decimals.
    const Parts dp = parts(d);
    const Big a = mul(small(36000), pow10b(dp.scale));
    const Big b = mul(dp.mag, small(std::uint64_t(100 * days)));
    const Big den = mul(small(360), pow10b(dp.scale));
    bool negative = false;
    Big num;
    if (dp.negative) num = add(a, b);
    else if (cmp(a, b) >= 0) num = sub(a, b);
    else num = sub(b, a), negative = true;
    put(out, "price", fmt_scaled(negative, round_ratio(num, den, 9), 9));
}

void fut_to_ticks(const Value& raw, Writer& out) {
    const Value& v = need(raw, "price");
    const auto [face, tick] = contract(raw);
    const long long t = fut_ticks(&v, tick, "price");
    put(out, "label", rates_label);
    out.key("ticks");
    out.integer(t);
}

void fut_to_text(const Value& raw, Writer& out) {
    const long long t = int_need(raw, "ticks");
    const auto [face, tick] = contract(raw);
    if (t < 0) fail("E_DOMAIN", "ticks", "ticks must not be negative");
    long long res = 0;
    for (const long long r : {32LL, 64LL, 128LL})
        if (tick * D::integer(r) == one) res = r;
    if (res == 0) fail("E_DOMAIN", "contract", "contract tick is not 1/32, 1/64 or 1/128");
    const string text = format_32nds(D::integer(t) * tick, res);
    put(out, "label", rates_label);
    put(out, "text", text);
}

void fut_pnl(const Value& raw, Writer& out) {
    const long long qty = int_need(raw, "qty");
    const Value& bp = need(raw, "buy_price");
    const Value& sp = need(raw, "sell_price");
    const D fee = dec_or(raw, "fee_per_contract", "0");
    const auto [face, tick] = contract(raw);
    if (qty <= 0 || fee.sign() < 0) fail("E_DOMAIN", "qty", "qty must be positive and fee not negative");
    const long long st = fut_ticks(&sp, tick, "sell_price");
    const long long bt = fut_ticks(&bp, tick, "buy_price");
    const D d = D::integer(st) - D::integer(bt);
    const D fees = fee * D::integer(2) * D::integer(qty);
    const D pnl = d * D::integer(qty) * tick_value(face, tick) - fees;
    put(out, "fees", fees.str());
    put(out, "label", rates_label);
    put(out, "pnl", pnl.str());
}

void fut_variation(const Value& raw, Writer& out) {
    const bool buy = enum_need(raw, "side", {"BUY", "SELL"}) == "BUY";
    const long long qty = int_need(raw, "qty");
    const Value& p0 = need(raw, "price");
    const Value& settles = list_need(raw, "settlements");
    const auto [face, tick] = contract(raw);
    if (settles.items.empty()) fail("E_INPUT", "settlements", "settlements is empty");
    if (qty <= 0) fail("E_DOMAIN", "qty", "qty must be positive");
    D mark = D::integer(fut_ticks(&p0, tick, "price"));
    const D scale = D::integer(buy ? qty : -qty) * tick_value(face, tick);
    std::vector<string> vm;
    for (std::size_t k = 0; k < settles.items.size(); ++k) {
        const D t = D::integer(fut_ticks(&settles.items[k], tick, "settlements/" + std::to_string(k)));
        vm.push_back(((t - mark) * scale).str());
        mark = t;
    }
    put(out, "label", rates_label);
    out.key("variation_margin");
    out.begin_array();
    for (const auto& s : vm) out.string(s);
    out.end_array();
}

void fut_run(const Value& raw, Writer& out) {
    const Value& events = list_need(raw, "events");
    const D fee = dec_or(raw, "fee_per_contract", "0");
    const auto [face, tick] = contract(raw);
    if (fee.sign() < 0) fail("E_DOMAIN", "fee_per_contract", "fee_per_contract must not be negative");
    Value mapped;
    mapped.kind = Kind::Array;
    std::map<string, string> trader;
    std::map<string, bool> buyer;
    for (std::size_t k = 0; k < events.items.size(); ++k) {
        const string p = "events/" + std::to_string(k);
        Value e = obj(&events.items[k], p);
        for (auto& m : e.members)
            if (m.first == "price" && m.second.kind == Kind::String)
                m.second.text = (D::integer(fut_ticks(&m.second, tick, p + "/price")) * tick).str();
        const Value* op = e.find("op");
        const Value* id = e.find("id");
        const Value* tr = e.find("trader");
        if (op && op->kind == Kind::String && op->text == "NEW" && id && id->kind == Kind::String && tr && tr->kind == Kind::String)
            trader[id->text] = tr->text;
        mapped.items.push_back(std::move(e));
    }
    for (const Value& e : mapped.items) {
        const Value* op = e.find("op");
        const Value* id = e.find("id");
        const Value* side = e.find("side");
        if (op && op->kind == Kind::String && op->text == "NEW" && id && id->kind == Kind::String)
            buyer[id->text] = side && side->kind == Kind::String && side->text == "BUY";
    }
    Value zero_fees;
    zero_fees.kind = Kind::Object;
    for (const char* k : {"maker_rebate", "taker_fee"}) {
        Value z;
        z.kind = Kind::String;
        z.text = "0";
        zero_fees.members.push_back({k, z});
    }
    Writer lit;
    lit.begin_object();
    lit_run(tick.str(), "1", mapped, zero_fees, lit);
    lit.end_object();
    const json::Parsed parsed = json::parse(lit.str());
    const D tv = tick_value(face, tick);
    std::map<string, D> pos, cash, fees;
    std::optional<D> last;
    if (const Value* fl = parsed.value.find("fills"))
        for (const Value& f : fl->items) {
            const D p = D::parse(f.find("price")->text), q = D::parse(f.find("qty")->text);
            last = p;
            const D p_ticks = p.divide_integral(tick, false);
            for (const char* role : {"maker_id", "taker_id"}) {
                const string& oid = f.find(role)->text;
                const string& t = trader.at(oid);
                const D sq = buyer.at(oid) ? q : -q;
                pos[t] += sq;
                cash[t] -= sq * p_ticks;
                fees[t] += fee * q;
            }
        }
    const D mark = last ? last->divide_integral(tick, false) : zero;
    std::vector<json::Member> members;
    for (const auto& m : parsed.value.members)
        if (m.first != "fees" && m.first != "label") members.push_back(m);
    const auto text_map = [](const std::map<string, D>& v) {
        Value o;
        o.kind = Kind::Object;
        for (const auto& [k, x] : v) {
            Value s;
            s.kind = Kind::String;
            s.text = x.str();
            o.members.push_back({k, s});
        }
        return o;
    };
    std::map<string, D> pnl;
    for (const auto& [t, p] : pos) pnl[t] = (p * mark + cash[t]) * tv - fees[t];
    Value label;
    label.kind = Kind::String;
    label.text = string(rates_label);
    members.push_back({"fees", text_map(fees)});
    members.push_back({"label", label});
    members.push_back({"pnl", text_map(pnl)});
    std::sort(members.begin(), members.end(), [](const json::Member& a, const json::Member& b) { return a.first < b.first; });
    for (const auto& m : members) {
        out.key(m.first);
        emit(out, m.second);
    }
}

}  // namespace quantforge::micro::ma
