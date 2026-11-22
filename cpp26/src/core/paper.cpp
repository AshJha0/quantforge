// Paper trading (see paper.hpp). A step-for-step port of python/quantforge_core/paper.py and paper_fills.py.
#include "quantforge/core/paper.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdio>
#include <functional>
#include <tuple>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/execution.hpp"
#include "quantforge/core/microstructure.hpp"
#include "quantforge/core/snapshot.hpp"

namespace quantforge::paper {
namespace {

using json::Kind;
using json::Value;
using std::string;
using std::string_view;

[[noreturn]] void fail(const char* code, const string& field, const string& why) { throw Error(code, why, field); }

// ---------------------------------------------------------------- exact decimals (HR-77, HR-58)
// Python runs these in the 200-digit context, so every in-range sum, difference and product is exact.
// value = (-1)^neg * digits * 10^exp, normalised (no leading or trailing zeros; zero is "0", exp 0).
constexpr std::size_t prec = 200;

struct Dec {
    bool neg = false;
    string d = "0";
    long exp = 0;
    bool zero() const { return d == "0"; }
};

Dec norm(Dec x) {
    const auto first = x.d.find_first_not_of('0');
    if (first == string::npos) return Dec{};
    x.d.erase(0, first);
    while (x.d.size() > 1 && x.d.back() == '0') {
        x.d.pop_back();
        ++x.exp;
    }
    if (x.exp > 1000000 || x.exp < -1000000) fail("E_LIMIT", "value", "decimal exponent out of range");
    return x;
}

int cmp_digits(const string& a, const string& b) {  // non-negative integers without leading zeros
    if (a.size() != b.size()) return a.size() < b.size() ? -1 : 1;
    return a < b ? -1 : (a > b ? 1 : 0);
}

string add_digits(const string& a, const string& b) {
    string r;
    int carry = 0;
    for (std::size_t i = 0; i < std::max(a.size(), b.size()) || carry; ++i) {
        int s = carry;
        if (i < a.size()) s += a[a.size() - 1 - i] - '0';
        if (i < b.size()) s += b[b.size() - 1 - i] - '0';
        r.push_back(char('0' + s % 10));
        carry = s / 10;
    }
    std::reverse(r.begin(), r.end());
    return r;
}

string strip(string s) {
    const auto f = s.find_first_not_of('0');
    return f == string::npos ? "0" : s.substr(f);
}

string sub_digits(const string& a, const string& b) {  // a >= b
    string r;
    int borrow = 0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        int s = (a[a.size() - 1 - i] - '0') - borrow - (i < b.size() ? b[b.size() - 1 - i] - '0' : 0);
        borrow = s < 0;
        if (s < 0) s += 10;
        r.push_back(char('0' + s));
    }
    std::reverse(r.begin(), r.end());
    return strip(r);
}

int cmp_mag(const Dec& a, const Dec& b) {
    if (a.zero() || b.zero()) return a.zero() == b.zero() ? 0 : (a.zero() ? -1 : 1);
    const long aa = long(a.d.size()) + a.exp, ab = long(b.d.size()) + b.exp;
    if (aa != ab) return aa < ab ? -1 : 1;
    string x = a.d, y = b.d;
    x.resize(std::max(x.size(), y.size()), '0');
    y.resize(x.size(), '0');
    return x < y ? -1 : (x > y ? 1 : 0);
}

int cmp(const Dec& a, const Dec& b) {
    const int sa = a.zero() ? 0 : (a.neg ? -1 : 1), sb = b.zero() ? 0 : (b.neg ? -1 : 1);
    if (sa != sb) return sa < sb ? -1 : 1;
    return sa >= 0 ? cmp_mag(a, b) : -cmp_mag(a, b);
}
bool operator<(const Dec& a, const Dec& b) { return cmp(a, b) < 0; }
bool operator>(const Dec& a, const Dec& b) { return cmp(a, b) > 0; }
bool operator==(const Dec& a, const Dec& b) { return cmp(a, b) == 0; }
int sign(const Dec& a) { return a.zero() ? 0 : (a.neg ? -1 : 1); }

// Drops the last k digits, half-even; `sticky` is a non-zero remainder below the last digit.
Dec round_drop(Dec x, std::size_t k, bool sticky) {
    if (k == 0) return x;
    if (x.d.size() <= k) x.d.insert(0, k - x.d.size() + 1, '0');
    const std::size_t keep = x.d.size() - k;
    const char g = x.d[keep];
    bool rest = sticky;
    for (std::size_t i = keep + 1; i < x.d.size(); ++i) rest = rest || x.d[i] != '0';
    string kept = x.d.substr(0, keep);
    const bool odd = (kept.back() - '0') % 2 == 1;
    if (g > '5' || (g == '5' && (rest || odd))) kept = add_digits(kept, "1");
    x.d = kept;
    x.exp += long(k);
    return norm(x);
}

Dec ctx(Dec x, bool sticky = false) {  // round to the context precision
    const auto first = x.d.find_first_not_of('0');
    if (first == string::npos) return Dec{};
    x.d.erase(0, first);
    if (x.d.size() > prec) return round_drop(x, x.d.size() - prec, sticky);
    return norm(x);
}

Dec add_exact(const Dec& a, const Dec& b) {
    if (a.zero()) return b;
    if (b.zero()) return a;
    const long e = std::min(a.exp, b.exp);
    const string x = a.d + string(std::size_t(a.exp - e), '0'), y = b.d + string(std::size_t(b.exp - e), '0');
    Dec r;
    r.exp = e;
    if (a.neg == b.neg) {
        r.d = add_digits(x, y);
        r.neg = a.neg;
    } else if (cmp_digits(x, y) >= 0) {
        r.d = sub_digits(x, y);
        r.neg = a.neg;
    } else {
        r.d = sub_digits(y, x);
        r.neg = b.neg;
    }
    return r;
}

Dec neg(Dec a) {
    if (!a.zero()) a.neg = !a.neg;
    return a;
}
Dec add(const Dec& a, const Dec& b) { return ctx(add_exact(a, b)); }
Dec sub(const Dec& a, const Dec& b) { return ctx(add_exact(a, neg(b))); }
Dec absd(Dec a) {
    a.neg = false;
    return ctx(a);
}
Dec minus(const Dec& a) { return ctx(neg(a)); }

Dec mul(const Dec& a, const Dec& b) {
    if (a.zero() || b.zero()) return Dec{};
    std::vector<int> r(a.d.size() + b.d.size(), 0);
    for (std::size_t i = 0; i < a.d.size(); ++i)
        for (std::size_t j = 0; j < b.d.size(); ++j)
            r[i + j + 1] += (a.d[i] - '0') * (b.d[j] - '0');
    for (std::size_t i = r.size() - 1; i > 0; --i) {
        r[i - 1] += r[i] / 10;
        r[i] %= 10;
    }
    Dec x;
    x.d.clear();
    for (const int v : r) x.d.push_back(char('0' + v));
    x.neg = a.neg != b.neg;
    x.exp = a.exp + b.exp;
    return ctx(x);
}

Dec divide(const Dec& a, const Dec& b) {
    if (b.zero()) throw std::logic_error("paper: division by zero");
    if (a.zero()) return Dec{};
    string q, r = "0";
    std::size_t idx = 0;
    long extra = 0;
    const auto sig = [&] {
        const auto f = q.find_first_not_of('0');
        return f == string::npos ? std::size_t(0) : q.size() - f;
    };
    for (;;) {
        char digit = '0';
        if (idx < a.d.size()) digit = a.d[idx++];
        else ++extra;
        r = strip(r + digit);
        int c = 0;
        while (cmp_digits(r, b.d) >= 0) {
            r = sub_digits(r, b.d);
            ++c;
        }
        q.push_back(char('0' + c));
        if (idx == a.d.size() && (r == "0" || sig() > prec)) break;
    }
    Dec x;
    x.d = q;
    x.neg = a.neg != b.neg;
    x.exp = a.exp - b.exp - extra;
    return ctx(x, r != "0");
}

Dec quantize_to(const Dec& x, long places, bool sticky = false) {
    if (x.zero() || x.exp >= -places) return x;
    return round_drop(x, std::size_t(-places - x.exp), sticky);
}

// a / b rounded half-even to `places` decimals, from the exact quotient (HR-77).
Dec divide_to(const Dec& a, const Dec& b, long places) {
    if (b.zero()) throw std::logic_error("paper: division by zero");
    if (a.zero()) return Dec{};
    string q, r = "0";
    std::size_t idx = 0;
    long extra = 0;
    for (;;) {
        char digit = '0';
        if (idx < a.d.size()) digit = a.d[idx++];
        else ++extra;
        r = strip(r + digit);
        int c = 0;
        while (cmp_digits(r, b.d) >= 0) {
            r = sub_digits(r, b.d);
            ++c;
        }
        q.push_back(char('0' + c));
        const long e = a.exp - b.exp - extra;  // exponent of the last quotient digit
        if (idx == a.d.size() && (r == "0" || e < -places)) break;
    }
    Dec x;
    x.d = strip(q);
    x.neg = a.neg != b.neg;
    x.exp = a.exp - b.exp - extra;
    return norm(quantize_to(x, places, r != "0"));
}

// HR-57: at most 36 digits and `max_scale` decimals, else E_LIMIT; never rounded.
Dec rng(const Dec& x, const string& name, long max_scale = 36) {
    if (x.zero()) return x;
    const long n = x.exp >= 0 ? long(x.d.size()) + x.exp : long(x.d.size());
    const long scale = x.exp < 0 ? -x.exp : 0;
    if (n > 36 || scale > max_scale)
        fail("E_LIMIT", name, name + ": decimal outside the exact range (36 digits, " + std::to_string(max_scale) +
                                  " decimals; HR-57)");
    return x;
}

Dec integer(long long v) {
    Dec x;
    x.neg = v < 0;
    x.d = std::to_string(v < 0 ? -(unsigned long long)v : (unsigned long long)v);
    return norm(x);
}

// Python Decimal(str): whitespace, sign, digits with single underscores, point, exponent; inf/nan non-finite.
Dec parse_py(string_view t, const string& name) {
    const auto ws = [](char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v'; };
    while (!t.empty() && ws(t.front())) t.remove_prefix(1);
    while (!t.empty() && ws(t.back())) t.remove_suffix(1);
    bool negative = false;
    if (!t.empty() && (t[0] == '+' || t[0] == '-')) {
        negative = t[0] == '-';
        t.remove_prefix(1);
    }
    string low;
    for (const char c : t) low.push_back(char(c >= 'A' && c <= 'Z' ? c + 32 : c));
    const auto digits_only = [](string_view s) {
        return std::all_of(s.begin(), s.end(), [](char c) { return c >= '0' && c <= '9'; });
    };
    if (low == "inf" || low == "infinity" || (low.starts_with("nan") && digits_only(string_view(low).substr(3))) ||
        (low.starts_with("snan") && digits_only(string_view(low).substr(4))))
        fail("E_SCHEMA", name, name + " is not a finite decimal");
    std::size_t i = 0;
    const auto run = [&](string& out) {  // digit ("_"? digit)*
        const std::size_t start = i;
        while (i < t.size()) {
            if (t[i] >= '0' && t[i] <= '9') out.push_back(t[i++]);
            else if (t[i] == '_' && i > start && i + 1 < t.size() && t[i - 1] != '_' && t[i + 1] >= '0' && t[i + 1] <= '9')
                ++i;
            else break;
        }
        return i > start;
    };
    string ip, fp, ep;
    const bool has_int = run(ip);
    bool has_frac = false;
    if (i < t.size() && t[i] == '.') {
        ++i;
        has_frac = run(fp);
    }
    bool ok = has_int || has_frac;
    long e = 0;
    if (ok && i < t.size() && (t[i] == 'e' || t[i] == 'E')) {
        ++i;
        bool eneg = false;
        if (i < t.size() && (t[i] == '+' || t[i] == '-')) eneg = t[i++] == '-';
        ok = run(ep) && ep.size() < 9;
        if (ok) e = (eneg ? -1 : 1) * std::stol(ep);
    }
    if (!ok || i != t.size()) fail("E_SCHEMA", name, name + " is not a decimal");
    Dec x;
    x.d = ip + fp;
    x.neg = negative;
    x.exp = e - long(fp.size());
    return norm(x);
}

string fmt(Dec x) {  // lit_matching.fmt: normalize (context rounding), no exponent, "0" for zero
    x = ctx(x);
    if (x.zero()) return "0";
    string s;
    if (x.exp >= 0) s = x.d + string(std::size_t(x.exp), '0');
    else if (long(x.d.size()) > -x.exp) s = x.d.substr(0, x.d.size() - std::size_t(-x.exp)) + "." + x.d.substr(x.d.size() - std::size_t(-x.exp));
    else s = "0." + string(std::size_t(-x.exp - long(x.d.size())), '0') + x.d;
    return (x.neg ? "-" : "") + s;
}

double to_double(const Dec& x) {  // correctly rounded, as float(Decimal)
    const string s = (x.neg ? "-" : "") + x.d + "e" + std::to_string(x.exp);
    double v = 0;
    std::from_chars(s.data(), s.data() + s.size(), v);
    return v;
}

// Python repr(float) then Decimal then fmt: the shortest round-trip text as an HR-12 decimal string.
string shortest(double v) {
    char buf[64];
    const auto r = std::to_chars(buf, buf + sizeof buf, v);
    return fmt(parse_py(string_view(buf, std::size_t(r.ptr - buf)), "tca"));
}

// ---------------------------------------------------------------- JSON values
const Value* get(const Value& obj, string_view key) {  // Python .get: missing and null are both None
    if (obj.kind != Kind::Object) return nullptr;
    const Value* p = nullptr;
    for (const auto& m : obj.members)
        if (m.first == key) p = &m.second;  // last wins, as a Python dict
    return p && p->kind != Kind::Null ? p : nullptr;
}
bool present(const Value& obj, string_view key) {
    return std::any_of(obj.members.begin(), obj.members.end(), [&](const json::Member& m) { return m.first == key; });
}
const Value& raw_get(const Value& obj, string_view key) {  // present (possibly null)
    static const Value null_value;
    const Value* p = nullptr;
    for (const auto& m : obj.members)
        if (m.first == key) p = &m.second;
    return p ? *p : null_value;
}

Value S(string_view s) {
    Value v;
    v.kind = Kind::String;
    v.text = string(s);
    return v;
}
Value I(long long n) {
    Value v;
    v.kind = Kind::Number;
    v.integral = true;
    v.number = double(n);
    v.text = std::to_string(n);
    return v;
}
Value Obj() {
    Value v;
    v.kind = Kind::Object;
    return v;
}
Value Arr() {
    Value v;
    v.kind = Kind::Array;
    return v;
}
void put(Value& obj, string_view key, Value v) {  // dict assignment: replace in place, else append
    for (auto& m : obj.members)
        if (m.first == key) {
            m.second = std::move(v);
            return;
        }
    obj.members.push_back({string(key), std::move(v)});
}
Value strings(const std::vector<string>& xs) {
    Value a = Arr();
    for (const auto& x : xs) a.items.push_back(S(x));
    return a;
}

// paper.dec: floats and booleans are E_INPUT; everything else goes through Decimal(str(value)).
Dec dec(const Value* v, const string& name) {
    if (!v) fail("E_SCHEMA", name, name + " is missing");
    switch (v->kind) {
        case Kind::Bool: fail("E_INPUT", name, name + " must be a decimal string");
        case Kind::Number:
            if (!v->integral) fail("E_INPUT", name, name + " must be a decimal string");
            return rng(parse_py(v->text, name), name);
        case Kind::String: return rng(parse_py(v->text, name), name);
        default: fail("E_SCHEMA", name, name + " is not a decimal");
    }
}
Dec dec(const Value& v, const string& name) {
    if (v.kind == Kind::Null) fail("E_SCHEMA", name, name + " is not a decimal");
    return dec(&v, name);
}
Dec dstr(const Value* v, const string& name) {  // a CLI decimal must be a JSON string
    if (!v || v->kind != Kind::String) fail("E_SCHEMA", name, name + " must be a decimal string");
    return rng(dec(v, name), name, 18);
}

// A present side that is not a JSON string is mistyped, E_SCHEMA (cli-contract.md, error table; fuzz run
// 44937631714); a string that is not listed is E_INPUT (paper-trading.md, Errors; rule_h-0040).
int side_sign(const Value* side) {
    if (side && side->kind != Kind::String) fail("E_SCHEMA", "side", "side must be a string");
    if (side) {
        if (side->text == "BUY") return 1;
        if (side->text == "SELL") return -1;
    }
    fail("E_INPUT", "side", "unknown side");
}

bool truthy(const Value* v) {
    if (!v) return false;
    switch (v->kind) {
        case Kind::Bool: return v->boolean;
        case Kind::Number: return v->number != 0;
        case Kind::String: return !v->text.empty();
        case Kind::Array: return !v->items.empty();
        case Kind::Object: return !v->members.empty();
        default: return false;
    }
}

long long integer_input(const Value& obj, string_view key, std::optional<long long> fallback) {
    const Value* v = get(obj, key);
    if (!v) {
        if (fallback) return *fallback;
        fail("E_SCHEMA", string(key), string(key) + ": missing");
    }
    if (v->kind != Kind::Number || !v->integral || std::fabs(v->number) > 9007199254740992.0)
        fail("E_SCHEMA", string(key), string(key) + ": not an integer");
    return (long long)v->number;
}

const Value& object_input(const Value& obj, string_view key) {
    const Value* v = get(obj, key);
    if (!v) fail("E_SCHEMA", string(key), string(key) + ": missing");
    if (v->kind != Kind::Object) fail("E_SCHEMA", string(key), string(key) + ": not an object");
    return *v;
}
const Value& array_input(const Value& obj, string_view key) {
    const Value* v = get(obj, key);
    if (!v) fail("E_SCHEMA", string(key), string(key) + ": missing");
    if (v->kind != Kind::Array) fail("E_SCHEMA", string(key), string(key) + ": not an array");
    return *v;
}
const string& string_input(const Value& obj, string_view key) {
    const Value* v = get(obj, key);
    if (!v) fail("E_SCHEMA", string(key), string(key) + ": missing");
    if (v->kind != Kind::String) fail("E_SCHEMA", string(key), string(key) + ": not a string");
    return v->text;
}

// ---------------------------------------------------------------- canonical bytes (HR-45)
std::map<string, const Value*> members_of(const Value& v) {  // sorted by code point (UTF-8 byte order); last wins
    std::map<string, const Value*> m;
    for (const auto& x : v.members) m[x.first] = &x.second;
    return m;
}

void check(const Value& v, const string& path) {
    switch (v.kind) {
        case Kind::Object:
            for (const auto& [k, x] : members_of(v)) check(*x, path + "." + k);
            break;
        case Kind::Array:
            for (std::size_t i = 0; i < v.items.size(); ++i) check(v.items[i], path + "[" + std::to_string(i) + "]");
            break;
        case Kind::Bool: fail("E_INPUT", path, path + " must be a string (only seq is an integer)");
        case Kind::Number:
            if (!(v.integral && path == ".seq")) fail("E_INPUT", path, path + " must be a string (only seq is an integer)");
            break;
        default: break;
    }
}

void canon(string& out, const Value& v) {
    switch (v.kind) {
        case Kind::Null: out += "null"; break;
        case Kind::Bool: out += v.boolean ? "true" : "false"; break;
        case Kind::Number: {
            string t = v.text;
            if (t == "-0") t = "0";
            out += t;
            break;
        }
        case Kind::String: out += ascii_string(v.text); break;
        case Kind::Array:
            out += '[';
            for (std::size_t i = 0; i < v.items.size(); ++i) {
                if (i) out += ',';
                canon(out, v.items[i]);
            }
            out += ']';
            break;
        case Kind::Object: {
            out += '{';
            bool first = true;
            for (const auto& [k, x] : members_of(v)) {
                if (!first) out += ',';
                first = false;
                out += ascii_string(k);
                out += ':';
                canon(out, *x);
            }
            out += '}';
            break;
        }
    }
}

// ---------------------------------------------------------------- ledger (HR-43, HR-45, HR-46)
constexpr string_view kinds[] = {"ORDER", "REJECT", "FILL", "CANCEL", "EOD", "TCA"};
bool known_kind(string_view k) { return std::find(std::begin(kinds), std::end(kinds), k) != std::end(kinds); }

Value make_record(long long seq, const string& ts, const string& kind, Value body, const string& prev) {
    Value rec = Obj();
    put(rec, "seq", I(seq));
    put(rec, "ts", S(ts));
    put(rec, "kind", S(kind));
    put(rec, "label", S(label));
    put(rec, "body", std::move(body));
    put(rec, "prev", S(prev));
    return rec;
}

struct Ledger {
    std::vector<Value> records;
    string head = string(genesis);

    void append(const string& kind, const string& ts, Value body) {
        if (!known_kind(kind)) fail("E_INPUT", "kind", "unknown kind");
        Value rec = make_record((long long)records.size(), ts, kind, std::move(body), head);
        const string h = sha256_hex(canonical(rec));
        put(rec, "hash", S(h));
        head = h;
        records.push_back(std::move(rec));
    }
};

// Python str.splitlines on UTF-8 text.
std::vector<string_view> splitlines(string_view t) {
    std::vector<string_view> out;
    std::size_t start = 0, i = 0;
    while (i < t.size()) {
        const auto c = (unsigned char)t[i];
        std::size_t len = 0;
        if (c == '\r') len = (i + 1 < t.size() && t[i + 1] == '\n') ? 2 : 1;
        else if (c == '\n' || c == 0x0b || c == 0x0c || c == 0x1c || c == 0x1d || c == 0x1e) len = 1;
        else if (c == 0xc2 && i + 1 < t.size() && (unsigned char)t[i + 1] == 0x85) len = 2;
        else if (c == 0xe2 && i + 2 < t.size() && (unsigned char)t[i + 1] == 0x80 &&
                 ((unsigned char)t[i + 2] == 0xa8 || (unsigned char)t[i + 2] == 0xa9))
            len = 3;
        if (len) {
            out.push_back(t.substr(start, i - start));
            i += len;
            start = i;
        } else {
            ++i;
        }
    }
    if (start < t.size()) out.push_back(t.substr(start));
    return out;
}

// ---------------------------------------------------------------- book (HR-50, HR-52, HR-53)
struct Pos {
    Dec n, c;
};

struct Book {
    Dec cash;
    std::vector<std::pair<string, Pos>> positions;  // insertion order, as a Python dict
    Dec realised, fees;

    Pos& pos(const string& sym) {
        for (auto& [s, p] : positions)
            if (s == sym) return p;
        positions.push_back({sym, Pos{}});
        return positions.back().second;
    }

    void apply_fill(const string& sym, int s, const Dec& q, const Dec& p, const Dec& f) {
        if (sign(q) <= 0 || sign(p) <= 0) fail("E_DOMAIN", "quantity", "quantity and price must be positive");
        const Dec sd = integer(s);
        const Dec notional = rng(mul(q, p), "notional");
        cash = rng(sub(cash, rng(add(mul(sd, notional), f), "cash_flow")), "cash");
        fees = rng(add(fees, f), "fees");
        Pos& ps = pos(sym);
        if (ps.n.zero() || (sign(ps.n) > 0) == (s > 0)) {
            const Dec a = absd(ps.n);
            const Dec basis = rng(add(rng(mul(a, ps.c), "basis"), notional), "basis");
            // HR-77: the one division of the book, rounded half-even to 18 decimals
            ps.c = rng(divide_to(basis, rng(add(a, q), "position"), 18), "avg_cost");
            ps.n = rng(add(ps.n, mul(sd, q)), "position");
            return;
        }
        const Dec a = absd(ps.n);
        const Dec closed = a < q ? a : q;
        const int sg = sign(ps.n) > 0 ? 1 : -1;
        realised = rng(add(realised, rng(mul(mul(closed, rng(sub(p, ps.c), "pnl")), integer(sg)), "pnl")), "realised");
        ps.n = rng(add(ps.n, mul(sd, q)), "position");
        if (ps.n.zero()) ps.c = Dec{};
        else if ((sign(ps.n) > 0) != (sg > 0)) ps.c = p;
    }

    Dec nav(const Value& marks) const {
        Dec total;
        for (const auto& [sym, p] : positions)
            if (!p.n.zero()) total = add(total, rng(mul(p.n, dec(get(marks, sym), "marks." + sym)), "market_value"));
        return rng(add(cash, total), "nav");
    }
};

struct DayFill {
    string symbol;
    int side;
    Dec q, p, fee;
};

struct Financing {
    Dec interest, borrow, financing;
};

Financing financing(const Dec& cash, const std::vector<std::pair<Dec, Dec>>& shorts_open, long long days,
                    const Value* cash_rate, const Value* debit_rate, const Value* borrow_rate) {
    if (days < 0) fail("E_DOMAIN", "days", "days must be >= 0");
    const Dec r = sign(cash) >= 0 ? dec(cash_rate, "cash_rate") : dec(debit_rate, "debit_rate");
    const Dec d = integer(days), y = integer(365);
    const Dec interest = divide_to(rng(mul(mul(cash, r), d), "interest"), y, 2);
    Dec smv;
    for (const auto& [n, px] : shorts_open)
        if (sign(n) < 0) smv = add(smv, mul(minus(n), px));
    smv = rng(smv, "short_value");
    const Dec borrow = minus(divide_to(rng(mul(mul(smv, dec(borrow_rate, "borrow_rate")), d), "borrow"), y, 2));
    return {interest, borrow, rng(add(interest, borrow), "financing")};
}

struct Eod {
    Dec market, trading, fees, financing, interest, borrow, total, nav;
};

Eod end_of_day(Book& book, const std::vector<DayFill>& fills, const Value& prev_marks, const Value& marks,
               long long days, const Value* cash_rate, const Value* debit_rate, const Value* borrow_rate) {
    std::vector<std::pair<string, Dec>> opening;
    for (const auto& [s, p] : book.positions)
        if (!p.n.zero()) opening.push_back({s, p.n});
    const Dec nav0 = opening.empty() ? book.cash : book.nav(prev_marks);
    std::vector<std::pair<Dec, Dec>> shorts;
    for (const auto& [s, n] : opening) shorts.push_back({n, dec(get(prev_marks, s), "close")});
    const Financing fin = financing(book.cash, shorts, days, cash_rate, debit_rate, borrow_rate);
    Dec market;
    for (const auto& [s, n] : opening)
        market = add(market, mul(n, sub(dec(get(marks, s), "mark"), dec(get(prev_marks, s), "prev_mark"))));
    Dec trading, fees;
    for (const DayFill& f : fills) {
        trading = add(trading, mul(mul(integer(f.side), f.q), sub(dec(get(marks, f.symbol), "mark"), f.p)));
        fees = sub(fees, f.fee);
        book.apply_fill(f.symbol, f.side, f.q, f.p, f.fee);
    }
    book.cash = add(book.cash, fin.financing);
    market = rng(market, "market");
    trading = rng(trading, "trading");
    fees = rng(fees, "fees");
    book.cash = rng(book.cash, "cash");
    const Dec total = rng(add(add(add(market, trading), fees), fin.financing), "total");
    const Dec nav1 = book.nav(marks);
    if (!(total == sub(nav1, nav0))) throw std::logic_error("paper: explain residual (HR-53)");
    return {market, trading, fees, fin.financing, fin.interest, fin.borrow, total, nav1};
}

Value eod_body(const Eod& e) {
    Value b = Obj();
    put(b, "market", S(fmt(e.market)));
    put(b, "trading", S(fmt(e.trading)));
    put(b, "fees", S(fmt(e.fees)));
    put(b, "financing", S(fmt(e.financing)));
    put(b, "interest", S(fmt(e.interest)));
    put(b, "borrow", S(fmt(e.borrow)));
    put(b, "total", S(fmt(e.total)));
    put(b, "nav", S(fmt(e.nav)));
    put(b, "label", S(label));
    put(b, "ceiling", S(ceiling));
    return b;
}

// ---------------------------------------------------------------- pre-trade checks (HR-42, HR-49)
constexpr string_view types[] = {"LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY"};

long long py_int(const Value* v, const string& name) {  // Python int()
    if (!v) fail("E_SCHEMA", name, name + " is missing");
    if (v->kind == Kind::Bool) return v->boolean ? 1 : 0;
    if (v->kind == Kind::Number) return (long long)std::trunc(v->number);
    if (v->kind == Kind::String) {
        string t = v->text;
        t.erase(0, t.find_first_not_of(" \t\n\r\f\v"));
        t.erase(t.find_last_not_of(" \t\n\r\f\v") + 1);
        long long out = 0;
        const char* b = t.data() + (t.starts_with('+') ? 1 : 0);
        const auto r = std::from_chars(b, t.data() + t.size(), out);
        if (!t.empty() && r.ec == std::errc{} && r.ptr == t.data() + t.size()) return out;
    }
    fail("E_SCHEMA", name, name + " must be an integer");
}

std::vector<string> pretrade(const Value& order, const Dec& p_ref, const Dec& position, const Dec& cash,
                             long long orders_today, const Value& limits) {
    const Value* mode = present(order, "mode") ? &raw_get(order, "mode") : nullptr;
    if (mode && !(mode->kind == Kind::String && mode->text == "simulated"))
        fail("E_UNSUPPORTED_OPERATION", "mode", "paper trading never places live orders");
    const int s = side_sign(get(order, "side"));
    const Value* otype = get(order, "type");
    if (otype && otype->kind != Kind::String) fail("E_SCHEMA", "type", "type must be a string");
    if (!otype || std::find(std::begin(types), std::end(types), otype->text) == std::end(types))
        fail("E_INPUT", "type", "unknown type");
    const Dec q = dec(get(order, "quantity"), "quantity");
    const Dec band = dec(get(limits, "price_band"), "price_band");
    if (sign(q) <= 0 || sign(p_ref) <= 0) fail("E_DOMAIN", "quantity", "quantity and reference price must be positive");
    std::optional<Dec> limit;
    Dec p_chk;
    if (otype->text == "MARKET") {
        p_chk = mul(p_ref, add(integer(1), mul(integer(s), band)));
    } else {
        if (!present(order, "limit_price")) fail("E_SCHEMA", "limit_price", "limit_price is missing");
        limit = dec(raw_get(order, "limit_price"), "limit_price");
        if (sign(*limit) <= 0) fail("E_DOMAIN", "limit_price", "limit price must be positive");
        p_chk = *limit;
    }
    const Dec after = add(position, mul(integer(s), q));
    std::vector<string> reasons;
    const bool kill = truthy(get(limits, "kill_switch"));
    const bool max_orders = orders_today >= py_int(get(limits, "max_orders_per_day"), "max_orders_per_day");
    const bool max_qty = q > dec(get(limits, "max_order_qty"), "max_order_qty");
    // cross-multiplied, so no division (HR-77): |limit - P_ref| / P_ref > band
    const bool band_fail = limit && rng(absd(sub(*limit, p_ref)), "band") > rng(mul(band, p_ref), "band");
    const bool max_notional = rng(mul(q, p_chk), "notional") > dec(get(limits, "max_notional"), "max_notional");
    const Dec notional = mul(q, p_chk);
    const bool max_pos = absd(after) > dec(get(limits, "max_abs_position"), "max_abs_position");
    const Value* allow = present(limits, "allow_short") ? &raw_get(limits, "allow_short") : nullptr;
    const bool no_short = (allow ? !truthy(allow) : false) && sign(after) < 0;
    const bool no_cash = s > 0 && notional > cash;
    const std::pair<bool, const char*> checks[] = {{kill, "KILL_SWITCH"},         {max_orders, "MAX_ORDERS"},
                                                   {max_qty, "MAX_QTY"},          {band_fail, "PRICE_BAND"},
                                                   {max_notional, "MAX_NOTIONAL"}, {max_pos, "MAX_POSITION"},
                                                   {no_short, "NO_SHORT"},        {no_cash, "INSUFFICIENT_CASH"}};
    for (const auto& [failed, name] : checks)
        if (failed) reasons.emplace_back(name);
    return reasons;
}

// ---------------------------------------------------------------- CLI helpers (one symbol per case)
const string sym1 = "S";

const Value* req(const Value& m, string_view key, const string& where) {
    const Value* v = get(m, key);
    if (!v) fail("E_SCHEMA", where + string(key), where + string(key) + " is missing");
    return v;
}

// The E_SCHEMA checks of every fill, before any other check of the case (KR-230, HR-122): each fill an object,
// side, quantity and price present, and side and each decimal a JSON string (fuzz run 44937631714).
void fill_schema(const Value& fills) {
    for (std::size_t k = 0; k < fills.items.size(); ++k) {
        const Value& f = fills.items[k];
        const string w = "fills/" + std::to_string(k) + "/";
        if (f.kind != Kind::Object) fail("E_SCHEMA", w, w + " is not an object");
        for (const char* key : {"side", "quantity", "price"})
            if (req(f, key, w)->kind != Kind::String) fail("E_SCHEMA", w + key, w + key + " must be a string");
        if (present(f, "fee") && raw_get(f, "fee").kind != Kind::String)
            fail("E_SCHEMA", w + "fee", w + "fee must be a decimal string");
    }
}

// Fills in the KR-230 order over the whole list: schema, decimals (malformed, then E_LIMIT), unknown side
// (structural E_INPUT), then a non-positive quantity or price (E_DOMAIN).
std::vector<DayFill> fill_list(const Value& fills) {
    fill_schema(fills);
    static const Value zero_text = S("0");
    std::vector<std::array<Dec, 3>> parsed;
    for (std::size_t k = 0; k < fills.items.size(); ++k) {
        const Value& f = fills.items[k];
        const string w = "fills/" + std::to_string(k) + "/";
        parsed.push_back({dstr(get(f, "quantity"), w + "quantity"), dstr(get(f, "price"), w + "price"),
                          dstr(present(f, "fee") ? &raw_get(f, "fee") : &zero_text, w + "fee")});
    }
    std::vector<int> sides;
    for (const Value& f : fills.items) sides.push_back(side_sign(get(f, "side")));
    std::vector<DayFill> out;
    for (std::size_t k = 0; k < fills.items.size(); ++k) {
        const auto& [q, p, fee] = parsed[k];
        if (sign(q) <= 0 || sign(p) <= 0)
            fail("E_DOMAIN", "fills/" + std::to_string(k) + "/quantity", "quantity and price must be positive");
        out.push_back({sym1, sides[k], parse_py(fmt(q), "quantity"), parse_py(fmt(p), "price"), parse_py(fmt(fee), "fee")});
    }
    return out;
}

void write_label(json::Writer& out) {
    out.key("label");
    out.string(label);
}
void kv(json::Writer& out, string_view k, const string& v) {
    out.key(k);
    out.string(v);
}

// ---------------------------------------------------------------- simulated fills (HR-47, paper_fills.py)
struct Fill {
    Dec quantity, price, fee;
    string venue, child_id;
};

Value run_json(const std::function<void(json::Writer&)>& f) {
    json::Writer w;
    w.begin_object();
    f(w);
    w.end_object();
    return json::parse(w.str()).value;
}

const Value& level_list(const Value& snap, const char* name) {
    const Value* v = get(snap, name);
    if (!v || v->kind != Kind::Array) fail("E_SCHEMA", "snapshot", string("snapshot ") + name + " must be an array");
    for (const Value& l : v->items)
        if (l.kind != Kind::Array || l.items.size() != 2) fail("E_SCHEMA", "snapshot", "snapshot levels are [price, qty]");
    return *v;
}

Dec mid(const Value& snap) {
    if (!truthy(get(snap, "bids")) || !truthy(get(snap, "asks")))
        fail("E_INPUT", "snapshot", "snapshot has an empty side; no mid");
    const Value& b = level_list(snap, "bids");
    const Value& a = level_list(snap, "asks");
    Dec half;
    half.d = "5";
    half.exp = -1;
    return mul(add(dec(b.items[0].items[0], "bid"), dec(a.items[0].items[0], "ask")), half);  // exact (HR-77)
}

const string& text_of(const Value* v, const string& name) {
    if (!v || v->kind != Kind::String) fail("E_SCHEMA", name, name + " must be a string");
    return v->text;
}

std::pair<std::vector<Fill>, Dec> lit_child(const Value& cfg, const Value& snap, const string& cid, const string& side,
                                            const string& otype, const Dec& qty, const std::optional<Dec>& limit) {
    Value events = Arr();
    for (const auto& [name, s] : {std::pair{"asks", "SELL"}, std::pair{"bids", "BUY"}}) {
        const Value& levels = level_list(snap, name);
        for (std::size_t i = 0; i < levels.items.size(); ++i) {
            Value e = Obj();
            put(e, "op", S("NEW"));
            put(e, "id", S(string("BOOK-") + name + "-" + std::to_string(i)));
            put(e, "trader", S("BOOK"));
            put(e, "side", S(s));
            put(e, "type", S("LIMIT"));
            put(e, "price", levels.items[i].items[0]);
            put(e, "qty", levels.items[i].items[1]);
            events.items.push_back(std::move(e));
        }
    }
    Value ev = Obj();
    put(ev, "op", S("NEW"));
    put(ev, "id", S(cid));
    put(ev, "trader", S("PAPER"));
    put(ev, "side", S(side));
    put(ev, "type", S(otype));
    put(ev, "qty", S(fmt(qty)));
    if (otype != "MARKET") put(ev, "price", S(fmt(*limit)));
    events.items.push_back(std::move(ev));
    const Value& fees = raw_get(cfg, "fee_schedule");
    if (fees.kind != Kind::Object) fail("E_SCHEMA", "lit/fee_schedule", "fee_schedule must be an object");
    const string tick = text_of(get(cfg, "tick_size"), "lit/tick_size");
    const string lot = text_of(get(cfg, "lot_size"), "lit/lot_size");
    const Value out = run_json([&](json::Writer& w) { micro::lit_run(tick, lot, events, fees, w); });
    for (const Value& r : raw_get(out, "rejects").items)
        if (const Value* id = get(r, "id"); id && id->text == cid) return {{}, Dec{}};
    const Dec taker = dec(get(fees, "taker_fee"), "taker_fee"), rebate = dec(get(fees, "maker_rebate"), "maker_rebate");
    std::vector<Fill> fills;
    for (const Value& f : raw_get(out, "fills").items) {
        const string& t = get(f, "taker_id")->text;
        const string& m = get(f, "maker_id")->text;
        if (t != cid && m != cid) continue;
        const Dec q = dec(get(f, "qty"), "qty"), p = dec(get(f, "price"), "price");
        const Dec rate = t == cid ? taker : minus(rebate);
        fills.push_back({q, p, mul(mul(rate, q), p), "LIT", cid});
    }
    const Value* cons = get(raw_get(out, "conservation"), cid);
    return {fills, cons ? dec(get(*cons, "resting"), "resting") : Dec{}};
}

std::pair<std::vector<Fill>, Dec> dark_child(const Value& cfg, const Value& snap, const Value& contra, const string& cid,
                                             const string& side, const Dec& qty, const std::optional<Dec>& limit) {
    Value events = Arr();
    Value book = Obj();
    put(book, "op", S("BOOK"));
    put(book, "bid", level_list(snap, "bids").items.at(0).items[0]);
    put(book, "ask", level_list(snap, "asks").items.at(0).items[0]);
    events.items.push_back(std::move(book));
    for (const Value& c : contra.items) {
        if (c.kind != Kind::Object) fail("E_SCHEMA", "contra", "contra events must be objects");
        events.items.push_back(c);
    }
    Value ev = Obj();
    put(ev, "op", S("NEW"));
    put(ev, "id", S(cid));
    put(ev, "side", S(side));
    put(ev, "qty", S(fmt(qty)));
    put(ev, "kind", S("FIRM"));
    if (limit) put(ev, "limit", S(fmt(*limit)));
    events.items.push_back(std::move(ev));
    const Value out = run_json([&](json::Writer& w) { micro::dark_run(cfg, events, w); });
    std::vector<Fill> fills;
    for (const Value& f : raw_get(out, "fills").items)
        if (get(f, "buy_id")->text == cid || get(f, "sell_id")->text == cid)
            fills.push_back({dec(get(f, "qty"), "qty"), dec(get(f, "price"), "price"), Dec{}, "DARK", cid});
    Dec rest;
    for (const Value& r : raw_get(out, "resting").items)
        if (get(r, "id")->text == cid) {
            rest = dec(get(r, "open_qty"), "q");
            break;
        }
    return {fills, rest};
}

struct Open {
    Value order;
    Dec decision, arrival;
    std::vector<Fill> fills;
    Dec resting;
};

class Session {
public:
    Session(const Value& cash, const Value& limits, const Value& lit, const Value* dark)
        : limits_(limits), lit_(lit), dark_(dark) {
        book_.cash = dec(cash, "cash");
    }

    Value submit(const Value& order, const string& ts, const Value& snap, const Value& contra, const Value* router) {
        const Value* vv = present(order, "venue") ? &raw_get(order, "venue") : nullptr;
        const string venue = vv ? (vv->kind == Kind::String ? vv->text : string("?")) : "LIT";
        if (venue != "LIT" && venue != "DARK" && venue != "SOR") fail("E_INPUT", "venue", "unknown venue");
        const string oid = text_of(get(order, "order_id"), "order_id");
        for (const Open& o : today_)
            if (get(o.order, "order_id")->text == oid) fail("E_INPUT", "order_id", "duplicate order_id");
        const Dec p_ref = mid(snap);
        const string sym = text_of(get(order, "symbol"), "symbol");
        const std::vector<string> reasons = pretrade(order, p_ref, position(sym), cash(), orders_today_, limits_);
        ++orders_today_;
        Value body = Obj();
        for (const auto& m : order.members)
            if (m.first != "mode") put(body, m.first, m.second);
        if (!reasons.empty()) {
            put(body, "reasons", strings(reasons));
            ledger.append("REJECT", ts, std::move(body));
            Value r = Obj();
            put(r, "status", S("REJECTED"));
            put(r, "reasons", strings(reasons));
            return r;
        }
        put(body, "decision_price", S(fmt(p_ref)));
        ledger.append("ORDER", ts, std::move(body));
        const string& side = get(order, "side")->text;
        const string& otype = get(order, "type")->text;
        const Dec qty = dec(get(order, "quantity"), "quantity");
        std::optional<Dec> limit;
        if (otype != "MARKET") limit = dec(raw_get(order, "limit_price"), "limit_price");
        Open rec{order, p_ref, mid(snap), {}, Dec{}};
        if (venue == "LIT") std::tie(rec.fills, rec.resting) = lit_child(lit_, snap, oid, side, otype, qty, limit);
        else if (venue == "DARK") std::tie(rec.fills, rec.resting) = dark_child(dark(), snap, contra, oid, side, qty, limit);
        else rec.fills = route(oid, side, snap, contra, router, qty, limit);
        Dec filled;
        for (const Fill& f : rec.fills) {
            Value fb = Obj();
            put(fb, "order_id", S(oid));
            put(fb, "child_id", S(f.child_id));
            put(fb, "venue", S(f.venue));
            put(fb, "symbol", S(sym));
            put(fb, "side", S(side));
            put(fb, "quantity", S(fmt(f.quantity)));
            put(fb, "price", S(fmt(f.price)));
            put(fb, "fee", S(fmt(f.fee)));
            ledger.append("FILL", ts, std::move(fb));
            day_fills_.push_back({sym, side == "BUY" ? 1 : -1, parse_py(fmt(f.quantity), "q"), parse_py(fmt(f.price), "p"),
                                  parse_py(fmt(f.fee), "f")});
            filled = add(filled, f.quantity);
        }
        if (rec.resting.zero() && filled < qty) cancel(ts, oid, sub(qty, filled));
        const bool open = !rec.resting.zero();
        today_.push_back(std::move(rec));
        Value r = Obj();
        put(r, "status", S(open ? "OPEN" : "DONE"));
        put(r, "filled", S(fmt(filled)));
        return r;
    }

    Value close_day(const string& ts, const Value& prev_marks, const Value& marks, long long days,
                    const Value* cash_rate, const Value* debit_rate, const Value* borrow_rate) {
        for (const Open& rec : today_) {
            const Value& o = rec.order;
            const string& oid = get(o, "order_id")->text;
            const Dec qty = dec(get(o, "quantity"), "quantity");
            Dec filled, fees;
            for (const Fill& f : rec.fills) filled = add(filled, f.quantity);
            if (!rec.resting.zero()) cancel(ts, oid, sub(qty, filled));
            for (const Fill& f : rec.fills) fees = add(fees, f.fee);
            const double end = to_double(dec(get(marks, get(o, "symbol")->text), "close"));
            std::vector<execution::Fill> kf;
            for (const Fill& f : rec.fills) kf.push_back({to_double(f.quantity), to_double(f.price)});
            const double decision = to_double(rec.decision), arrival = to_double(rec.arrival), q = to_double(qty),
                         fee = to_double(fees);
            for (const double x : {decision, arrival, end, q, fee})
                if (!std::isfinite(x)) fail("E_DOMAIN", "shortfall", "shortfall inputs must be finite");
            const execution::Shortfall t = execution::shortfall(
                get(o, "side")->text == "BUY" ? execution::Side::Buy : execution::Side::Sell, decision, arrival, end, q,
                kf, fee, std::nullopt);
            Value body = Obj();
            put(body, "order_id", S(oid));
            put(body, "delay", S(shortest(t.delay)));
            put(body, "execution", S(shortest(t.execution)));
            put(body, "opportunity", S(shortest(t.opportunity)));
            put(body, "total", S(shortest(t.total)));
            put(body, "total_bps", S(shortest(t.total_bps)));
            ledger.append("TCA", ts, std::move(body));
        }
        const Eod e = end_of_day(book_, day_fills_, prev_marks, marks, days, cash_rate, debit_rate, borrow_rate);
        ledger.append("EOD", ts, eod_body(e));
        today_.clear();
        day_fills_.clear();
        orders_today_ = 0;
        Value r = Obj();
        put(r, "status", S("CLOSED"));
        put(r, "eod", eod_body(e));
        return r;
    }

    Dec position(const string& sym) {
        Dec n = book_.pos(sym).n;
        Dec extra;
        for (const DayFill& f : day_fills_)
            if (f.symbol == sym) extra = add(extra, mul(integer(f.side), f.q));
        return add(n, extra);
    }
    Dec cash() const {
        Dec spent;
        for (const DayFill& f : day_fills_) spent = add(spent, add(mul(mul(integer(f.side), f.q), f.p), f.fee));
        return sub(book_.cash, spent);
    }

    Ledger ledger;

private:
    void cancel(const string& ts, const string& oid, const Dec& q) {
        Value b = Obj();
        put(b, "order_id", S(oid));
        put(b, "quantity", S(fmt(q)));
        ledger.append("CANCEL", ts, std::move(b));
    }
    const Value& dark() const {
        if (!dark_) fail("E_SCHEMA", "dark_cfg", "dark venue configuration is missing");
        return *dark_;
    }

    std::vector<Fill> route(const string& oid, const string& side, const Value& snap, const Value& contra,
                            const Value* router, const Dec& qty, const std::optional<Dec>& limit) {
        if (!router) fail("E_SCHEMA", "router", "SOR order needs the router input");
        if (router->kind != Kind::Object) fail("E_SCHEMA", "router", "router must be an object");
        Value inp = *router;
        put(inp, "S", S(fmt(qty)));
        const Value alloc = run_json([&](json::Writer& w) { micro::sor_allocate(inp, w); });
        const Value& best = level_list(snap, side == "BUY" ? "bids" : "asks").items.at(0).items[0];
        std::vector<std::tuple<string, string, Dec>> children{{"M", "MARKET", dec(get(alloc, "M"), "M")}};
        const Value& venues = raw_get(*router, "venues");
        const Value& ls = raw_get(alloc, "L");
        for (std::size_t k = 0; k < ls.items.size() && k < venues.items.size(); ++k) {
            const Value* kind = get(venues.items[k], "kind");
            children.emplace_back("L" + std::to_string(k), kind && kind->kind == Kind::String ? kind->text : "",
                                  dec(ls.items[k], "L"));
        }
        std::vector<Fill> fills;
        for (const auto& [name, kind, q] : children) {
            if (q.zero()) continue;
            const string cid = oid + "." + name;
            std::vector<Fill> got;
            if (kind == "MARKET") got = lit_child(lit_, snap, cid, side, "MARKET", q, std::nullopt).first;
            else if (kind == "LIT") got = lit_child(lit_, snap, cid, side, "LIMIT", q, dec(best, "best")).first;
            else got = dark_child(dark(), snap, contra, cid, side, q, limit).first;
            for (Fill g : got) {  // the parent never overfills
                Dec sum;
                for (const Fill& x : fills) sum = add(sum, x.quantity);
                const Dec room = sub(qty, sum);
                if (sign(room) <= 0) break;
                if (g.quantity > room) g = Fill{room, g.price, divide(mul(g.fee, room), g.quantity), g.venue, g.child_id};
                fills.push_back(g);
            }
        }
        return fills;
    }

    Book book_;
    const Value& limits_;
    const Value& lit_;
    const Value* dark_;
    std::vector<Open> today_;
    std::vector<DayFill> day_fills_;
    long long orders_today_ = 0;
};

}  // namespace

// ---------------------------------------------------------------- public
std::string ascii_string(std::string_view s) {
    string out = "\"";
    const auto hex4 = [&](unsigned v) {
        char b[16];
        std::snprintf(b, sizeof b, "\\u%04x", v);
        out += b;
    };
    for (std::size_t i = 0; i < s.size();) {
        const auto c = (unsigned char)s[i];
        unsigned cp = c;
        std::size_t len = 1;
        if (c >= 0xf0) {
            len = 4;
            cp = c & 0x07u;
        } else if (c >= 0xe0) {
            len = 3;
            cp = c & 0x0fu;
        } else if (c >= 0xc0) {
            len = 2;
            cp = c & 0x1fu;
        }
        if (i + len > s.size()) len = 1, cp = c;
        for (std::size_t k = 1; k < len; ++k) cp = (cp << 6) | ((unsigned char)s[i + k] & 0x3fu);
        i += len;
        switch (cp) {
            case '"': out += "\\\""; continue;
            case '\\': out += "\\\\"; continue;
            case '\b': out += "\\b"; continue;
            case '\f': out += "\\f"; continue;
            case '\n': out += "\\n"; continue;
            case '\r': out += "\\r"; continue;
            case '\t': out += "\\t"; continue;
            default: break;
        }
        if (cp >= 0x20 && cp <= 0x7e) out.push_back(char(cp));
        else if (cp > 0xffff) {
            cp -= 0x10000;
            hex4(0xd800 + (cp >> 10));
            hex4(0xdc00 + (cp & 0x3ff));
        } else hex4(cp);
    }
    return out + "\"";
}

std::string canonical(const json::Value& record) {
    Value body = Obj();
    for (const auto& [k, v] : members_of(record))
        if (k != "hash") put(body, k, *v);
    check(body, "");
    string out;
    canon(out, body);
    return out;
}

Verify verify(std::string_view text) {
    string prev(genesis);
    const auto lines = splitlines(text);
    for (std::size_t n = 0; n < lines.size(); ++n) {
        Verify bad;
        bad.ok = false;
        bad.records = (long long)n;
        bad.first_bad_seq = (long long)n;
        Value rec;
        string computed;
        try {
            json::Parsed parsed = json::parse(lines[n]);
            if (parsed.duplicate_key) throw Error("E_PARSE", "duplicate key (HR-78)");
            rec = std::move(parsed.value);
            if (rec.kind != Kind::Object || !present(rec, "hash")) throw Error("E_PARSE", "record");
            computed = sha256_hex(canonical(rec));
        } catch (const Error&) {
            bad.reason = "PARSE";
            return bad;
        }
        const Value& seq = raw_get(rec, "seq");
        const string seq_text = seq.text == "-0" ? "0" : seq.text;
        if (!present(rec, "seq") || seq.kind != Kind::Number || !seq.integral || seq_text != std::to_string(n)) {
            bad.reason = "SEQ";
            return bad;
        }
        const Value& stored = raw_get(rec, "hash");
        if (stored.kind != Kind::String || stored.text != computed) {
            bad.reason = "HASH";
            return bad;
        }
        const Value& p = raw_get(rec, "prev");
        if (!present(rec, "prev") || p.kind != Kind::String || p.text != prev) {
            bad.reason = "LINK";
            return bad;
        }
        const Value& l = raw_get(rec, "label");
        if (!present(rec, "label") || l.kind != Kind::String || l.text != label) {
            bad.reason = "LABEL";
            return bad;
        }
        prev = stored.text;
    }
    Verify ok;
    ok.records = (long long)lines.size();
    ok.head = prev;
    return ok;
}

void book_apply_fill(const json::Value& in, json::Writer& out) {
    const Value& fills = array_input(in, "fills");
    fill_schema(fills);
    const Value* cash = get(in, "cash");
    static const Value zero = S("0");
    const Value* position = get(in, "position") ? get(in, "position") : &zero;
    const Value* avg_cost = get(in, "avg_cost") ? get(in, "avg_cost") : &zero;
    Book book;
    book.cash = cash ? dstr(cash, "cash") : Dec{};
    Pos& p = book.pos(sym1);
    p.n = dstr(position, "position");
    p.c = dstr(avg_cost, "avg_cost");
    for (const DayFill& f : fill_list(fills)) book.apply_fill(sym1, f.side, f.q, f.p, f.fee);
    const Pos& r = book.pos(sym1);
    kv(out, "position", fmt(r.n));
    kv(out, "avg_cost", fmt(r.c));
    kv(out, "realised", fmt(book.realised));
    kv(out, "fees", fmt(book.fees));
    write_label(out);
    kv(out, cash ? "cash" : "cash_delta", fmt(book.cash));
}

void book_end_of_day(const json::Value& in, json::Writer& out) {
    static const Value zero = S("0");
    const Value* cash_open = get(in, "cash_open");
    if (!cash_open) string_input(in, "cash_open");
    static const Value empty = Arr();
    const Value& fills = get(in, "fills") ? array_input(in, "fills") : empty;
    const Value* position_open = get(in, "position_open") ? get(in, "position_open") : &zero;
    const Value* avg_cost_open = get(in, "avg_cost_open");
    const Value* prev_close = get(in, "prev_close");
    const Value* close = get(in, "close");
    const long long days = integer_input(in, "days", 1);
    const auto rate = [&](const char* k) { return get(in, k) ? get(in, k) : &zero; };
    const Value *cash_rate = rate("cash_rate"), *debit_rate = rate("debit_rate"), *borrow_rate = rate("borrow_rate");

    fill_schema(fills);
    const Dec cash = dstr(cash_open, "cash_open");
    const Dec n = dstr(position_open, "position_open");
    const std::vector<DayFill> fl = fill_list(fills);
    if (!n.zero() && !prev_close) fail("E_SCHEMA", "prev_close", "prev_close is missing (open position)");
    if ((!n.zero() || !fl.empty()) && !close) fail("E_SCHEMA", "close", "close is missing (position or fills)");
    std::optional<Dec> prev, px;
    if (prev_close) prev = dstr(prev_close, "prev_close");
    if (close) px = dstr(close, "close");
    if (prev && sign(*prev) <= 0) fail("E_DOMAIN", "prev_close", "prev_close must be positive");
    if (px && sign(*px) <= 0) fail("E_DOMAIN", "close", "close must be positive");
    const Value cr = S(fmt(dstr(cash_rate, "cash_rate"))), dr = S(fmt(dstr(debit_rate, "debit_rate"))),
                br = S(fmt(dstr(borrow_rate, "borrow_rate")));
    Book book;
    book.cash = cash;
    Pos& pos = book.pos(sym1);
    pos.n = n;
    if (avg_cost_open) pos.c = dstr(avg_cost_open, "avg_cost_open");
    else if (prev) pos.c = *prev;
    Value prev_marks = Obj(), marks = Obj();
    if (prev) put(prev_marks, sym1, S(fmt(*prev)));
    if (px) put(marks, sym1, S(fmt(*px)));
    const Dec nav_open = add(cash, (!n.zero() && prev) ? mul(n, *prev) : Dec{});
    const Eod e = end_of_day(book, fl, prev_marks, marks, days, &cr, &dr, &br);
    kv(out, "market", fmt(e.market));
    kv(out, "trading", fmt(e.trading));
    kv(out, "fees", fmt(e.fees));
    kv(out, "financing", fmt(e.financing));
    kv(out, "cash_interest", fmt(e.interest));
    kv(out, "short_borrow", fmt(e.borrow));
    kv(out, "total", fmt(e.total));
    kv(out, "position", fmt(book.pos(sym1).n));
    kv(out, "cash_close", fmt(book.cash));
    write_label(out);
    if (px) {
        kv(out, "nav_open", fmt(nav_open));
        kv(out, "nav_close", fmt(e.nav));
    }
}

void pretrade_check(const json::Value& in, json::Writer& out) {
    static const Value zero = S("0");
    const Value& order = object_input(in, "order");
    const Value* ref_price = get(in, "ref_price");
    if (!ref_price) string_input(in, "ref_price");
    const Value* position = get(in, "position") ? get(in, "position") : &zero;
    const Value* cash = &raw_get(in, "cash");
    string_input(in, "cash");
    const long long orders_today = integer_input(in, "orders_today", 0);
    const Value& limits = object_input(in, "limits");
    for (const char* k : {"side", "type", "quantity"}) req(order, k, "order/");
    for (const char* k : {"side", "type"})  // mistyped is E_SCHEMA; an unlisted string is E_INPUT later
        if (get(order, k)->kind != Kind::String) fail("E_SCHEMA", string("order/") + k, string("order/") + k + " must be a string");
    dstr(get(order, "quantity"), "order/quantity");
    if (get(order, "limit_price")) dstr(get(order, "limit_price"), "order/limit_price");
    for (const char* k : {"max_order_qty", "max_notional", "max_abs_position", "price_band"})
        dstr(req(limits, k, "limits/"), string("limits/") + k);
    const Value* mo = req(limits, "max_orders_per_day", "limits/");
    if (mo->kind != Kind::Number || !mo->integral) fail("E_SCHEMA", "limits", "limits/max_orders_per_day must be an integer");
    for (const char* k : {"kill_switch", "allow_short"})
        if (present(limits, k) && raw_get(limits, k).kind != Kind::Bool)
            fail("E_SCHEMA", string("limits/") + k, string("limits/") + k + " must be a boolean");
    const Dec p_ref = dstr(ref_price, "ref_price");
    const Dec pos = dstr(position, "position");
    const Dec c = dstr(cash, "cash");
    const std::vector<string> reasons = pretrade(order, p_ref, pos, c, orders_today, limits);
    out.key("accepted");
    out.boolean(reasons.empty());
    out.key("reasons");
    out.value(strings(reasons));
    write_label(out);
}

void ledger_append(const json::Value& in, json::Writer& out) {
    const long long seq = integer_input(in, "seq", std::nullopt);
    const string& ts = string_input(in, "ts");
    const string& kind = string_input(in, "kind");
    const Value& body = object_input(in, "body");
    string prev = get(in, "prev") ? string_input(in, "prev") : string();
    if (prev.empty()) prev = string(genesis);
    if (!known_kind(kind)) fail("E_INPUT", "kind", "unknown kind");
    if (seq < 0) fail("E_DOMAIN", "seq", "seq must be >= 0");
    const std::function<void(const Value&, const string&)> finite = [&](const Value& v, const string& path) {
        if (v.kind == Kind::Object)
            for (const auto& [k, x] : members_of(v)) finite(*x, path + "/" + k);
        else if (v.kind == Kind::Array)
            for (std::size_t i = 0; i < v.items.size(); ++i) finite(v.items[i], path + "/" + std::to_string(i));
        else if (v.kind == Kind::String && (v.text == "NaN" || v.text == "Infinity" || v.text == "-Infinity"))
            fail("E_SCHEMA", path, path + " is not a finite decimal");
    };
    finite(body, "body");
    Value rec = make_record(seq, ts, kind, body, prev);
    const string raw = canonical(rec);
    const string h = sha256_hex(raw);
    put(rec, "hash", S(h));
    kv(out, "canonical_bytes", raw);
    kv(out, "hash", h);
    out.key("record");
    out.value(rec);
    write_label(out);
}

void ledger_verify(const json::Value& in, json::Writer& out) {
    const Verify r = verify(string_input(in, "text"));
    out.key("ok");
    out.boolean(r.ok);
    out.key("records");
    out.integer(r.records);
    out.key("first_bad_seq");
    if (r.first_bad_seq) out.integer(*r.first_bad_seq);
    else out.null();
    out.key("reason");
    if (r.ok) out.null();
    else out.string(r.reason);
    out.key("head");
    if (r.ok) out.string(r.head);
    else out.null();
    write_label(out);
}

void session_run(const json::Value& in, json::Writer& out) {
    const Value* cash = get(in, "cash");
    if (!cash) string_input(in, "cash");
    const Value& limits = object_input(in, "limits");
    const Value& lit = object_input(in, "lit");
    const Value& script = array_input(in, "script");
    const Value* dark = get(in, "dark") ? &object_input(in, "dark") : nullptr;
    dstr(cash, "cash");
    for (const char* k : {"tick_size", "lot_size", "fee_schedule"})
        if (!get(lit, k)) fail("E_SCHEMA", string("lit/") + k, string("lit/") + k + " is missing");
    Session s(*cash, limits, lit, dark);
    std::vector<Value> results;
    std::set<string> symbols;
    static const Value empty = Arr(), empty_object = Obj();
    for (std::size_t k = 0; k < script.items.size(); ++k) {
        const Value& step = script.items[k];
        const string w = "script/" + std::to_string(k) + "/";
        const Value* op = get(step, "op");
        if (step.kind != Kind::Object || !op || op->kind != Kind::String || (op->text != "SUBMIT" && op->text != "CLOSE"))
            fail("E_SCHEMA", w + "op", w + "op must be SUBMIT or CLOSE");
        const Value* ts = get(step, "ts");
        if (!ts || ts->kind != Kind::String) fail("E_SCHEMA", w + "ts", w + "ts is missing");
        if (op->text == "SUBMIT") {
            const Value* order = get(step, "order");
            const Value* snap = get(step, "snapshot");
            if (!order || order->kind != Kind::Object || !snap || snap->kind != Kind::Object)
                fail("E_SCHEMA", w + "order", w + "order and snapshot are required");
            for (const char* key : {"order_id", "symbol", "side", "type", "quantity"})
                if (!get(*order, key)) fail("E_SCHEMA", w + "order/" + key, w + "order/" + key + " is missing");
            // mistyped text fields are E_SCHEMA (fuzz run 44937631714 class); a null venue stays E_INPUT
            for (const char* key : {"order_id", "symbol", "side", "type", "venue"})
                if (const Value* v = get(*order, key); v && v->kind != Kind::String)
                    fail("E_SCHEMA", w + "order/" + key, w + "order/" + key + " must be a string");
            for (const char* key : {"quantity", "limit_price"})
                if (get(*order, key)) dstr(get(*order, key), w + "order/" + key);
            symbols.insert(text_of(get(*order, "symbol"), w + "order/symbol"));
            const Value* contra = truthy(get(step, "contra")) ? get(step, "contra") : &empty;
            if (contra->kind != Kind::Array) fail("E_SCHEMA", w + "contra", w + "contra must be an array");
            results.push_back(s.submit(*order, ts->text, *snap, *contra, get(step, "router")));
        } else {
            const Value* d = get(step, "days");
            if (present(step, "days") && (!d || d->kind != Kind::Number || !d->integral))
                fail("E_SCHEMA", w + "days", w + "days must be an integer");
            const long long days = d ? (long long)d->number : 1;
            static const Value zero = S("0");
            const auto rate = [&](const char* r) -> const Value* {
                return present(step, r) ? (raw_get(step, r).kind == Kind::Null ? nullptr : &raw_get(step, r)) : &zero;
            };
            for (const char* r : {"cash_rate", "debit_rate", "borrow_rate"}) dstr(rate(r), w + r);
            for (const char* name : {"prev_marks", "marks"})
                if (const Value* m = get(step, name); m && m->kind == Kind::Object)
                    for (const auto& mm : m->members)
                        dstr(mm.second.kind == Kind::Null ? nullptr : &mm.second, w + name + "/" + mm.first);
            const auto marks_of = [&](const char* key) -> const Value& {
                const Value* m = get(step, key);
                if (!truthy(m)) return empty_object;
                if (m->kind != Kind::Object) fail("E_SCHEMA", w + key, w + key + " must be an object");
                return *m;
            };
            results.push_back(s.close_day(ts->text, marks_of("prev_marks"), marks_of("marks"), days, rate("cash_rate"),
                                          rate("debit_rate"), rate("borrow_rate")));
        }
    }
    out.key("results");
    out.begin_array();
    for (const Value& r : results) out.value(r);
    out.end_array();
    out.key("records");
    out.begin_array();
    for (const Value& r : s.ledger.records) out.value(r);
    out.end_array();
    kv(out, "head", s.ledger.head);
    out.key("positions");
    out.begin_object();
    for (const string& sym : symbols) kv(out, sym, fmt(s.position(sym)));
    out.end_object();
    kv(out, "cash", fmt(s.cash()));
    write_label(out);
    kv(out, "ceiling", string(ceiling));
}

}  // namespace quantforge::paper
