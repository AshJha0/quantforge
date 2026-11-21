// exec.sim.dark.run, exec.sim.dark.markouts (specifications/10-execution/dark-pool.md, HR-32 to HR-36) and
// exec.sor.allocate (specifications/10-execution/smart-order-router.md, HR-37 to HR-40). Simulated venues only.
// Prices, quantities and costs are exact decimals (ExactDecimal, HR-12, HR-57/58); the router's expectations are
// exact sums over the equally weighted lit rows and the independent dark distributions, divided by the row count
// only on output, by long division rounded half-even to 6 decimals. Ports python/quantforge_core/dark_pool.py
// and sor.py line for line, including the order of the checks and of the core.rng draws.
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/microstructure.hpp"
#include "quantforge/core/rng.hpp"

namespace quantforge::micro {

namespace {

using json::Kind;
using json::Value;
using D = ExactDecimal;
using Int = ExactDecimal::Int;
using std::string;

[[noreturn]] void fail(const char* code, const string& path, const string& why) { throw Error(code, path + ": " + why, path); }

// HR-93, HR-113: `asset_class` (default EQUITY; null counts as absent); a dark venue of another class is an
// invalid input combination, E_INPUT (structural cross-field check, HR-66).
string asset_class(const Value* v, const string& path, bool dark = false) {
    string c = "EQUITY";
    if (v != nullptr && v->kind != Kind::Null) {
        if (v->kind != Kind::String || (v->text != "EQUITY" && v->text != "FX" && v->text != "RATES"))
            fail("E_SCHEMA", path, "not EQUITY, FX or RATES");
        c = v->text;
    }
    if (dark && c != "EQUITY") fail("E_INPUT", path, "dark pool is equities only (HR-93, HR-113)");
    return c;
}

bool present(const Value* v) { return v != nullptr && v->kind != Kind::Null; }

D dec(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String || !D::well_formed(v->text)) fail("E_SCHEMA", path, "not a decimal string");
    return D::parse(v->text);
}

// Python's _int: a non-negative JSON integer, else E_DOMAIN.
long long nonneg_int(const Value* v, long long fallback, const string& path) {
    if (!present(v)) return fallback;
    if (v->kind != Kind::Number || !v->integral || v->text.starts_with("-")) fail("E_DOMAIN", path, "not a non-negative integer");
    long long r = 0;
    const auto [p, ec] = std::from_chars(v->text.data(), v->text.data() + v->text.size(), r);
    if (ec != std::errc() || p != v->text.data() + v->text.size()) fail("E_LIMIT", path, "integer too large");
    return r;
}

// Mantissa and scale of an exact decimal, read back from its canonical text.
std::pair<Int, int> split(D x) {
    const string s = x.str();
    Int m = 0;
    int scale = 0;
    bool frac = false;
    for (char c : s) {
        if (c == '-') continue;
        if (c == '.') {
            frac = true;
            continue;
        }
        m = m * 10 + (c - '0');
        if (frac) ++scale;
    }
    return {s.starts_with("-") ? -m : m, scale};
}

string int_text(Int v) {  // v >= 0
    if (v == 0) return "0";
    string s;
    while (v > 0) {
        s.push_back(char('0' + int(v % 10)));
        v /= 10;
    }
    return {s.rbegin(), s.rend()};
}

// Add one to a string of decimal digits.
void increment(string& digits) {
    for (auto i = digits.size(); i-- > 0;) {
        if (digits[i] != '9') {
            ++digits[i];
            return;
        }
        digits[i] = '0';
    }
    digits.insert(digits.begin(), '1');
}

// Remove trailing zeros of the fraction (no exponent, "0" for zero; HR-12).
string trim(string s) {
    if (s.find('.') != string::npos) {
        while (s.back() == '0') s.pop_back();
        if (s.back() == '.') s.pop_back();
    }
    if (s == "-0") s = "0";
    return s;
}

}  // namespace

string div_round(D num, D den, int places) {
    if (den.sign() == 0) throw Error("E_DOMAIN", "division by zero");
    auto [a, sa] = split(num);
    auto [b, sb] = split(den);
    const bool neg = (a < 0) != (b < 0) && a != 0;
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    // value = (a / b) * 10^(sb - sa); value * 10^places = (a / b) * 10^n.
    const int n = sb - sa + places;
    Int r = a % b;
    string digits = int_text(a / b);
    for (int i = 0; i < n; ++i) {  // n further digits of a / b
        r *= 10;
        digits.push_back(char('0' + int(r / b)));
        r %= b;
    }
    // digits (with n >= 0) is floor(value * 10^places); the rest is r / b. With n < 0 drop -n digits.
    int cmp = 0;  // remainder against one half: -1 below, 0 equal, 1 above
    if (n >= 0) {
        cmp = r == 0 ? -1 : (2 * r < b ? -1 : (2 * r == b ? 0 : 1));
    } else {
        const auto drop = std::size_t(-n);
        if (digits.size() < drop) digits.insert(0, drop - digits.size(), '0');
        string tail = digits.substr(digits.size() - drop);
        digits.erase(digits.size() - drop);
        if (digits.empty()) digits = "0";
        const char first = tail[0];
        const bool rest_zero = tail.find_first_not_of('0', 1) == string::npos && r == 0;
        cmp = first < '5' ? -1 : (first > '5' ? 1 : (rest_zero ? 0 : 1));
    }
    if (cmp > 0 || (cmp == 0 && (digits.back() - '0') % 2 == 1)) increment(digits);
    digits.erase(0, std::min(digits.find_first_not_of('0'), digits.size() - 1));
    if (int(digits.size()) <= places) digits.insert(0, std::size_t(places) - digits.size() + 1, '0');
    string out = digits;
    if (places > 0) out.insert(out.size() - std::size_t(places), ".");
    return trim((neg ? "-" : "") + out);
}

namespace {

// ===================================================================== dark pool

// Compare two non-negative fixed-point decimal strings numerically.
int cmp_fixed(const string& x, const string& y) {
    auto parts = [](const string& s) {
        const auto dot = s.find('.');
        string i = s.substr(0, dot), f = dot == string::npos ? "" : s.substr(dot + 1);
        i.erase(0, std::min(i.find_first_not_of('0'), i.size()));
        return std::pair{i, f};
    };
    auto [xi, xf] = parts(x);
    auto [yi, yf] = parts(y);
    if (xi.size() != yi.size()) return xi.size() < yi.size() ? -1 : 1;
    if (xi != yi) return xi < yi ? -1 : 1;
    const auto w = std::max(xf.size(), yf.size());
    xf.resize(w, '0');
    yf.resize(w, '0');
    return xf == yf ? 0 : (xf < yf ? -1 : 1);
}

struct DarkOrder {
    string id;
    bool buy = true;
    D open;
    std::optional<D> limit;
    D min_qty;
    bool conditional = false;
    long long seq = 0;
    long long suspended_to = 0;
    long long held_to = 0;
};

struct Pending {
    long long due;
    std::size_t b, s;
};

class Pool {
public:
    explicit Pool(const Value& cfg) : rng_(0, 0) {
        tick_ = dec(cfg.find("tick_size"), "config/tick_size");
        lot_ = dec(cfg.find("lot_size"), "config/lot_size");
        if (tick_.sign() <= 0 || lot_.sign() <= 0) fail("E_DOMAIN", "config/tick_size", "tick_size and lot_size must be positive");
        const Value* pf = cfg.find("p_firm");
        p_firm_ = present(pf) ? dec(pf, "config/p_firm") : D::parse("0.8");
        if (p_firm_.sign() < 0 || p_firm_ > D::integer(1)) fail("E_DOMAIN", "config/p_firm", "p_firm outside [0, 1]");
        delay_ = nonneg_int(cfg.find("firm_delay"), 0, "config/firm_delay");
        penalty_ = nonneg_int(cfg.find("penalty_events"), 0, "config/penalty_events");
        rng_ = Xoshiro256(std::uint64_t(nonneg_int(cfg.find("seed"), 0, "config/seed")), 0);
    }

    void book(const Value& e, const string& path) {
        std::optional<D> bid, ask;
        if (present(e.find("bid"))) bid = dec(e.find("bid"), path + "/bid");
        if (present(e.find("ask"))) ask = dec(e.find("ask"), path + "/ask");
        if (bid) on_grid(*bid, path + "/bid");
        if (ask) on_grid(*ask, path + "/ask");
        if (!bid || !ask || *bid >= *ask) mid_.reset();
        else mid_ = (*bid + *ask) * D::parse("0.5");  // exact: on the half-tick grid (HR-32)
    }

    void add(const Value& e, const string& path) {
        const Value* id = e.find("id");
        if (id == nullptr || id->kind != Kind::String) fail("E_SCHEMA", "events", path + "/id: not a string");
        for (const DarkOrder& o : orders_)
            if (o.id == id->text) fail("E_INPUT", "events", path + ": duplicate id " + id->text);
        const Value* side = e.find("side");
        const Value* kind = e.find("kind");
        const bool side_ok = side && side->kind == Kind::String && (side->text == "BUY" || side->text == "SELL");
        const bool kind_ok = kind && kind->kind == Kind::String && (kind->text == "FIRM" || kind->text == "CONDITIONAL");
        if (!side_ok || !kind_ok) fail("E_SCHEMA", "events", path + ": side or kind");
        const D qty = dec(e.find("qty"), path + "/qty");
        const D mq = present(e.find("min_qty")) ? dec(e.find("min_qty"), path + "/min_qty") : lot_;
        if (qty.sign() <= 0 || mq.sign() <= 0 || mq > qty) fail("E_DOMAIN", "events", path + ": qty must be positive and min_qty <= qty");
        on_grid_lot(qty, path + "/qty");
        DarkOrder o;
        if (present(e.find("limit"))) o.limit = dec(e.find("limit"), path + "/limit");
        o.id = id->text;
        o.buy = side->text == "BUY";
        o.open = qty;
        o.min_qty = mq;
        o.conditional = kind->text == "CONDITIONAL";
        o.seq = ++seq_;
        orders_.push_back(std::move(o));
    }

    void cancel(const Value& e, const string& path) {
        const Value* id = e.find("id");
        for (DarkOrder& o : orders_)
            if (id && id->kind == Kind::String && o.id == id->text) {
                o.open = D();
                return;
            }
        fail("E_INPUT", "events", path + ": unknown id");
    }

    void settle(long long n) {
        std::vector<Pending> due, keep;
        for (const Pending& p : pending_) (p.due == n ? due : keep).push_back(p);
        pending_ = std::move(keep);
        for (const Pending& p : due) {
            DarkOrder& b = orders_[p.b];
            DarkOrder& s = orders_[p.s];
            b.held_to = s.held_to = 0;
            if (invite(b, s, n) && eligible(b, n) && eligible(s, n) && pair_ok(b, s)) fill(b, s);
        }
    }

    void cross(long long n) {
        while (mid_) {
            std::optional<std::pair<std::size_t, std::size_t>> pair;
            for (std::size_t i = 0; i < orders_.size() && !pair; ++i) {
                if (!orders_[i].buy || !eligible(orders_[i], n)) continue;
                for (std::size_t j = 0; j < orders_.size(); ++j)
                    if (!orders_[j].buy && eligible(orders_[j], n) && pair_ok(orders_[i], orders_[j])) {
                        pair = {i, j};
                        break;
                    }
            }
            if (!pair) return;
            DarkOrder& b = orders_[pair->first];
            DarkOrder& s = orders_[pair->second];
            if (!b.conditional && !s.conditional) {
                fill(b, s);
            } else if (delay_ > 0) {
                b.held_to = s.held_to = n + delay_;
                pending_.push_back({n + delay_, pair->first, pair->second});
            } else if (invite(b, s, n)) {
                fill(b, s);
            }
        }
    }

    // Writes the members of one run (sorted keys, HR-29).
    void write(json::Writer& out) const {
        out.key("fills");
        out.begin_array();
        long long k = 0;
        for (const auto& [b, s, px, q] : fills_) {
            out.begin_object();
            out.key("buy_id");
            out.string(b);
            out.key("price");
            out.string(px);
            out.key("qty");
            out.string(q);
            out.key("sell_id");
            out.string(s);
            out.key("seq");
            out.integer(++k);
            out.end_object();
        }
        out.end_array();
        out.key("invitations");
        out.begin_array();
        for (const auto& [id, contra, ev, firmed] : invitations_) {
            out.begin_object();
            out.key("contra_id");
            out.string(contra);
            out.key("event");
            out.integer(ev);
            out.key("id");
            out.string(id);
            out.key("result");
            out.string(firmed ? "FIRMED" : "DECLINED");
            out.end_object();
        }
        out.end_array();
        out.key("label");
        out.string(dark_label);
        out.key("resting");
        out.begin_array();
        for (const DarkOrder& o : orders_) {
            if (o.open.sign() <= 0) continue;
            out.begin_object();
            out.key("id");
            out.string(o.id);
            out.key("open_qty");
            out.string(o.open.str());
            out.key("seq");
            out.integer(o.seq);
            out.key("side");
            out.string(o.buy ? "BUY" : "SELL");
            out.end_object();
        }
        out.end_array();
        out.key("suspensions");
        out.begin_array();
        for (const auto& [id, from, to] : suspensions_) {
            out.begin_object();
            out.key("from_event");
            out.integer(from);
            out.key("id");
            out.string(id);
            out.key("to_event");
            out.integer(to);
            out.end_object();
        }
        out.end_array();
    }

private:
    void on_grid(D x, const string& path) const {
        if (!x.multiple_of(tick_)) fail("E_DOMAIN", path, "not on the grid " + tick_.str());
    }
    void on_grid_lot(D x, const string& path) const {
        if (!x.multiple_of(lot_)) fail("E_DOMAIN", path, "not on the grid " + lot_.str());
    }

    bool eligible(const DarkOrder& o, long long n) const {
        if (o.open.sign() <= 0 || n <= o.suspended_to || n < o.held_to || !mid_) return false;
        if (!o.limit) return true;
        return o.buy ? *o.limit >= *mid_ : *o.limit <= *mid_;
    }

    static bool pair_ok(const DarkOrder& b, const DarkOrder& s) {
        const D q = std::min(b.open, s.open);
        return q >= b.min_qty && q >= s.min_qty;
    }

    // Python: Decimal(repr(u)) < p_firm, a core.rng draw only when 0 < p_firm < 1.
    bool firm() {
        if (p_firm_ == D::integer(1)) return true;
        if (p_firm_.sign() == 0) return false;
        const double u = rng_.next_uniform();
        char buf[512];
        const auto res = std::to_chars(buf, buf + sizeof buf, u, std::chars_format::fixed);
        return cmp_fixed(string(buf, res.ptr), p_firm_.str()) < 0;
    }

    void fill(DarkOrder& b, DarkOrder& s) {
        const D q = std::min(b.open, s.open);
        b.open -= q;
        s.open -= q;
        fills_.emplace_back(b.id, s.id, mid_->str(), q.str());
    }

    bool invite(DarkOrder& b, DarkOrder& s, long long n) {
        bool ok = true;
        for (auto [o, c] : {std::pair{&b, &s}, std::pair{&s, &b}}) {
            if (!o->conditional) continue;
            const bool firmed = firm();
            invitations_.emplace_back(o->id, c->id, n, firmed);
            if (!firmed) {
                ok = false;
                o->suspended_to = n + penalty_;
                if (penalty_ > 0) suspensions_.emplace_back(o->id, n + 1, n + penalty_);
            }
        }
        return ok;
    }

    D tick_, lot_, p_firm_;
    long long delay_ = 0, penalty_ = 0, seq_ = 0;
    Xoshiro256 rng_;
    std::optional<D> mid_;
    std::vector<DarkOrder> orders_;
    std::vector<Pending> pending_;
    std::vector<std::tuple<string, string, string, string>> fills_;
    std::vector<std::tuple<string, string, long long, bool>> invitations_;
    std::vector<std::tuple<string, long long, long long>> suspensions_;
};

}  // namespace

void dark_run(const Value& config, const Value& events, json::Writer& out) {
    if (events.kind != Kind::Array) fail("E_SCHEMA", "events", "expected an array");
    if (config.kind == Kind::Object) asset_class(config.find("asset_class"), "config/asset_class", true);
    if ((long long)events.items.size() > max_dark_events) throw Error("E_LIMIT", "more than 10,000,000 events", "events");
    if (config.kind != Kind::Object) fail("E_SCHEMA", "config", "expected an object");
    Pool pool(config);
    long long n = 0;
    for (const Value& e : events.items) {
        const string path = "events/" + std::to_string(n);
        ++n;
        const Value* op = e.kind == Kind::Object ? e.find("op") : nullptr;
        const string kind = op && op->kind == Kind::String ? op->text : "";
        if (kind == "BOOK") pool.book(e, path);
        else if (kind == "NEW") pool.add(e, path);
        else if (kind == "CANCEL") pool.cancel(e, path);
        else fail("E_SCHEMA", "events", path + ": not an event");
        pool.settle(n);
        pool.cross(n);
    }
    pool.write(out);
}

void dark_markouts(const Value& fills, json::Writer& out) {
    if (fills.kind != Kind::Array) fail("E_SCHEMA", "fills", "expected an array");
    const D bp_scale = D::integer(10000);
    out.key("fills");
    out.begin_array();
    std::size_t k = 0;
    for (const Value& f : fills.items) {
        const string path = "fills/" + std::to_string(k++);
        const Value* side = f.kind == Kind::Object ? f.find("side") : nullptr;
        if (!side || side->kind != Kind::String || (side->text != "BUY" && side->text != "SELL"))
            fail("E_SCHEMA", "fills", path + ": side");
        const D px = dec(f.find("fill_price"), path + "/fill_price");
        if (px.sign() <= 0) fail("E_DOMAIN", "fills", path + "/fill_price: not positive");
        const Value* mids = f.find("mid_at");
        if (!mids || mids->kind != Kind::Object) fail("E_SCHEMA", "fills", path + "/mid_at: not an object");
        std::vector<std::pair<string, string>> bp;
        for (const auto& m : mids->members) {
            D v = (dec(&m.second, path + "/mid_at/" + m.first) - px) * bp_scale;
            if (side->text == "SELL") v = -v;
            bp.emplace_back(m.first, div_round(v, px, 6));
        }
        std::sort(bp.begin(), bp.end());
        out.begin_object();
        out.key("label");
        out.string(dark_label);
        out.key("markouts_bp");
        out.begin_object();
        for (const auto& [h, v] : bp) {
            out.key(h);
            out.string(v);
        }
        out.end_object();
        out.end_object();
    }
    out.end_array();
}

std::vector<std::pair<double, double>> km_tail(const std::vector<std::pair<long long, long long>>& obs, int s_max) {
    double t = 1.0, gw = 0.0;
    std::vector<std::pair<double, double>> out;
    for (int s = 1; s <= s_max; ++s) {
        const long long j = s - 1;  // hazard at j: P(S = j | S >= j)
        long long at_risk = 0, d = 0;
        for (const auto& [v, r] : obs) {
            if ((r < v && r >= j) || (r == v && v > j)) ++at_risk;
            if (r < v && r == j) ++d;
        }
        if (at_risk > 0 && d > 0) {
            t *= 1.0 - double(d) / double(at_risk);
            if (at_risk > d) gw += double(d) / (double(at_risk) * double(at_risk - d));
        }
        out.emplace_back(t, t * std::sqrt(gw));
    }
    return out;
}

// ===================================================================== router

namespace {

constexpr std::size_t max_venues = 64;
constexpr std::size_t max_samples = 1'000'000;
constexpr long long max_grid = 1'000'000;

long long lots(const Value* v, const string& path) {
    const D d = dec(v, path);
    if (d.sign() < 0 || !d.multiple_of(D::integer(1))) fail("E_DOMAIN", path, "not a non-negative integer number of lots");
    const string s = d.str();
    if (s.size() > 15) fail("E_LIMIT", path, "too many lots");
    return std::stoll(s);
}

using Tuple = std::vector<long long>;

struct Totals {
    D cost, fill, under;  // sums over rows (dark probabilities applied); divide by the row count for the mean
    D sq;                 // sum of (p * cost) * cost, exact, for the standard error only (report_se)
};

class Problem {
public:
    explicit Problem(const Value& inp) {
        S_ = lots(inp.find("S"), "S");
        if (S_ <= 0) fail("E_DOMAIN", "S", "S must be positive");
        h_ = dec(inp.find("h"), "h");
        f_ = dec(inp.find("f"), "f");
        theta_ = dec(inp.find("theta"), "theta");
        lu_ = dec(inp.find("lambda_u"), "lambda_u");
        lo_ = dec(inp.find("lambda_o"), "lambda_o");
        if (theta_.sign() < 0 || lu_.sign() < 0 || lo_.sign() < 0) fail("E_DOMAIN", "lambda_u", "negative penalty");
        const Value* venues = inp.find("venues");
        if (!venues || venues->kind != Kind::Array || venues->items.empty()) fail("E_INPUT", "venues", "empty");
        {
            const string order_class = asset_class(inp.find("asset_class"), "asset_class");
            std::vector<string> classes;
            for (std::size_t k = 0; k < venues->items.size(); ++k) {
                const Value& v = venues->items[k];
                classes.push_back(asset_class(v.kind == Kind::Object ? v.find("asset_class") : nullptr,
                                              "venues/" + std::to_string(k) + "/asset_class"));
            }
            for (const string& c : classes)
                if (c != order_class) fail("E_INPUT", "venues", "a venue's asset_class differs from the order's (HR-93)");
            for (std::size_t k = 0; k < venues->items.size(); ++k) {
                const Value& v = venues->items[k];
                const Value* kind = v.kind == Kind::Object ? v.find("kind") : nullptr;
                if (kind && kind->kind == Kind::String && kind->text == "DARK")
                    asset_class(v.find("asset_class"), "venues/" + std::to_string(k) + "/asset_class", true);
            }
        }
        if (venues->items.size() > max_venues) fail("E_LIMIT", "venues", "more than 64 venues");
        for (std::size_t k = 0; k < venues->items.size(); ++k) {
            const Value& v = venues->items[k];
            const string path = "venues/" + std::to_string(k);
            const Value* kind = v.kind == Kind::Object ? v.find("kind") : nullptr;
            if (!kind || kind->kind != Kind::String || (kind->text != "LIT" && kind->text != "DARK"))
                fail("E_SCHEMA", "venues", path + "/kind");
            const bool lit = kind->text == "LIT";
            lit_kind_.push_back(lit);
            coef_.push_back(h_ + dec(v.find("r"), path + "/r") - dec(v.find("as"), path + "/as"));
            std::vector<D> tail;
            if (lit) {
                Q_.push_back(lots(v.find("Q"), path + "/Q"));
                lit_.push_back(k);
            } else {
                Q_.push_back(0);
                dark_.push_back(k);
                const Value* t = v.find("tail");
                if (present(t)) {
                    if (t->kind != Kind::Array) fail("E_SCHEMA", "venues", path + "/tail: not an array");
                    for (const Value& x : t->items) tail.push_back(dec(&x, path + "/tail"));
                }
                for (std::size_t i = 0; i < tail.size(); ++i)
                    if (tail[i].sign() < 0 || tail[i] > D::integer(1) || (i > 0 && tail[i - 1] < tail[i]))
                        fail("E_DOMAIN", "venues", path + "/tail: not a tail");
            }
            tails_.push_back(std::move(tail));
        }
        const Value* rows = inp.find("lit_samples");
        const bool rows_list = rows && rows->kind == Kind::Array;
        // Absent or null is no rows; any other non-array is mistyped (cli-contract.md), as a row that is not an
        // array (fuzz run 44815591552).
        if (present(rows) && !rows_list) fail("E_SCHEMA", "lit_samples", "not an array");
        if (!lit_.empty() && (!rows_list || rows->items.empty())) fail("E_INPUT", "lit_samples", "empty");
        if (rows_list && rows->items.size() > max_samples) fail("E_LIMIT", "lit_samples", "more than 10^6 samples");
        if (rows_list)
            for (std::size_t i = 0; i < rows->items.size(); ++i) {
                const Value& r = rows->items[i];
                if (r.kind != Kind::Array) fail("E_SCHEMA", "lit_samples", "a row is not an array");
                std::vector<long long> row;
                for (const Value& x : r.items) row.push_back(lots(&x, "lit_samples/" + std::to_string(i)));
                rows_.push_back(std::move(row));
            }
        if (rows_.empty()) rows_.emplace_back();
        for (const auto& r : rows_)
            if (r.size() != lit_.size()) fail("E_INPUT", "lit_samples", "one value per LIT venue per row");
    }

    void want_sq() const { want_sq_ = true; }
    std::size_t K() const { return lit_kind_.size(); }
    std::size_t rows() const { return rows_.size(); }

    D tail(std::size_t k, long long s) const {
        const auto& t = tails_[k];
        if (s <= 0) return D::integer(1);
        return s <= (long long)t.size() ? t[std::size_t(s - 1)] : D();
    }

    std::vector<std::pair<long long, D>> dark_dist(std::size_t k, long long L) const {
        std::vector<std::pair<long long, D>> out;
        for (long long j = 0; j < L; ++j) {
            const D p = tail(k, j) - tail(k, j + 1);
            if (p.sign() != 0) out.emplace_back(j, p);
        }
        if (tail(k, L).sign() != 0) out.emplace_back(L, tail(k, L));
        return out;
    }

    Totals evaluate(const Tuple& t) const {
        const long long M = t[0];
        const std::size_t K = this->K();
        std::vector<std::vector<std::pair<long long, D>>> dists;
        for (std::size_t k : dark_) dists.push_back(dark_dist(k, t[k + 1]));
        long long sumL = 0;
        for (std::size_t k = 0; k < K; ++k) sumL += t[k + 1];
        Totals tot;
        std::vector<long long> fills(K, 0);
        for (const auto& row : rows_) {
            for (std::size_t i = 0; i < lit_.size(); ++i) {
                const std::size_t k = lit_[i];
                const long long x = row[i] - Q_[k];
                fills[k] = std::max(x, 0LL) - std::max(x - t[k + 1], 0LL);
            }
            combos(dists, 0, D::integer(1), fills, M, sumL, tot);
        }
        return tot;
    }

    // Python sorts (cost, tuple); with one row count throughout, the row sums order as the means do.
    std::vector<std::pair<D, Tuple>> exhaustive() const {
        std::vector<std::pair<D, Tuple>> scored;
        Tuple t(K() + 1, 0);
        while (true) {
            scored.emplace_back(evaluate(t).cost, t);
            std::size_t i = t.size();
            while (i-- > 0) {
                if (t[i] < S_) {
                    ++t[i];
                    break;
                }
                t[i] = 0;
            }
            if (i == std::size_t(-1)) break;
        }
        std::sort(scored.begin(), scored.end());
        return scored;
    }

    bool grid_small() const {
        long long g = 1;
        for (std::size_t i = 0; i <= K(); ++i) {
            if (g > max_grid / (S_ + 1) + 1) return false;
            g *= S_ + 1;
        }
        return g <= max_grid;
    }

    Tuple closed_form() const {
        if (K() != 1 || !lit_kind_[0]) fail("E_DOMAIN", "method", "CLOSED_FORM needs exactly one LIT venue");
        std::vector<long long> xs;
        for (const auto& r : rows_) xs.push_back(r[0]);
        std::sort(xs.begin(), xs.end());
        const auto n = (long long)xs.size();
        const long long Q = Q_[0];
        const D r_eff = coef_[0] - h_;
        const D num = h_ + h_ + f_ + r_eff;
        const D base = h_ + r_eff + theta_;
        auto count = [&](long long x) { return (long long)(std::upper_bound(xs.begin(), xs.end(), x) - xs.begin()); };
        // lambda_u <= num / F(x) - base  <=>  (lambda_u + base) * c <= num * n, with c = n F(x) > 0.
        const D lb = lu_ + base, numn = num * D::integer(n);
        const long long c_lo = count(Q + S_), c_hi = count(Q);
        if (c_lo == 0 || lb * D::integer(c_lo) <= numn) return {0, S_};
        if (c_hi != 0 && lb * D::integer(c_hi) >= numn) return {S_, 0};
        // target = num / (lambda_u + base); first v with c(v) / n >= target. Here lambda_u + base > 0, since
        // lambda_u exceeds the lower threshold num / F - base with num / F >= num ... checked as Python does.
        if (lb.sign() == 0) fail("E_DOMAIN", "lambda_u", "lambda_u + h + r + theta is zero");
        long long q = xs.back();
        for (long long v : xs) {
            const D lhs = D::integer(count(v));
            const bool ok = lb.sign() > 0 ? lhs * lb >= numn : lhs * lb <= numn;
            if (ok) {
                q = v;
                break;
            }
        }
        const long long M = std::min(std::max(S_ - q + Q, 0LL), S_);
        return {M, S_ - M};
    }

    Tuple start() const {
        if (K() == 1 && lit_kind_[0]) return closed_form();
        Tuple t(K() + 1, 0);
        t[1] = lit_kind_[0] ? S_ : 0;
        return t;
    }

    // Exact coordinate descent on the sample-average cost; each pass tries every value 0..S per coordinate.
    Tuple descent(Tuple best) const {
        D cur = evaluate(best).cost;
        bool changed = true;
        while (changed) {
            changed = false;
            for (std::size_t i = 0; i < best.size(); ++i)
                for (long long v = 0; v <= S_; ++v) {
                    Tuple t = best;
                    t[i] = v;
                    const D c = evaluate(t).cost;
                    if (std::pair(c, t) < std::pair(cur, best)) {
                        best = t;
                        cur = c;
                        changed = true;
                    }
                }
        }
        return best;
    }

    // [CK] section 4: projected subgradient on [0, S]^(K+1), step / sqrt(n), iterates averaged; the average is
    // rounded to its best floor/ceiling neighbour (HR-38), then polished by exact coordinate descent.
    Tuple stochastic(long long iterations, double step, std::uint64_t seed) const {
        Xoshiro256 rng(seed, 0);
        const std::size_t K = this->K();
        auto real = [](D x) { return std::strtod(x.str().c_str(), nullptr); };
        const Tuple s0 = start();
        std::vector<double> x(s0.begin(), s0.end()), avg(K + 1, 0.0);
        const double h = real(h_), f = real(f_), th = real(theta_), lu = real(lu_), lo = real(lo_), S = double(S_);
        std::vector<double> coef;
        for (D c : coef_) coef.push_back(real(c));
        std::vector<std::vector<double>> tails;
        for (const auto& t : tails_) {
            tails.emplace_back();
            for (D v : t) tails.back().push_back(real(v));
        }
        const auto nrows = rows_.size();
        for (long long n = 1; n <= iterations; ++n) {
            const auto idx = std::min(std::size_t(rng.next_uniform() * double(nrows)), nrows - 1);
            const auto& row = rows_[idx];
            std::vector<double> room(K, 0.0), fills(K, 0.0);
            for (std::size_t i = 0; i < lit_.size(); ++i) {
                const std::size_t k = lit_[i];
                const double xi = double(row[i] - Q_[k]);
                fills[k] = std::min(std::max(xi, 0.0), x[k + 1]);
                room[k] = xi > x[k + 1] ? 1.0 : 0.0;
            }
            for (std::size_t k : dark_) {
                const double u = rng.next_uniform();
                std::size_t s = 0;
                while (s < tails[k].size() && u < tails[k][s]) ++s;
                fills[k] = std::min(double(s), x[k + 1]);
                room[k] = double(s) > x[k + 1] ? 1.0 : 0.0;
            }
            double A = x[0];
            for (double v : fills) A += v;
            const double g_a = (A < S ? -(lu + th) : 0.0) + (A > S ? lo : 0.0);
            std::vector<double> grad{h + f + th + g_a};
            for (std::size_t k = 0; k < K; ++k) grad.push_back(th + room[k] * (g_a - coef[k]));
            const double eta = step / std::sqrt(double(n));
            for (std::size_t i = 0; i <= K; ++i) {
                x[i] = std::min(std::max(x[i] - eta * grad[i], 0.0), S);
                avg[i] = avg[i] + (x[i] - avg[i]) / double(n);
            }
        }
        // Every floor/ceiling neighbour of the average; the lowest (cost, tuple) wins.
        std::vector<std::vector<long long>> opts;
        for (double a : avg) {
            const auto lo_v = (long long)std::floor(a), hi_v = (long long)std::ceil(a);
            opts.push_back(lo_v == hi_v ? std::vector{lo_v} : std::vector{lo_v, hi_v});
        }
        std::optional<std::pair<D, Tuple>> best;
        Tuple t(K + 1, 0);
        std::vector<std::size_t> pos(K + 1, 0);
        while (true) {
            for (std::size_t i = 0; i <= K; ++i) t[i] = opts[i][pos[i]];
            std::pair<D, Tuple> c{evaluate(t).cost, t};
            if (!best || c < *best) best = c;
            std::size_t i = K + 1;
            while (i-- > 0) {
                if (++pos[i] < opts[i].size()) break;
                pos[i] = 0;
            }
            if (i == std::size_t(-1)) break;
        }
        return descent(best->second);
    }

private:
    void combos(const std::vector<std::vector<std::pair<long long, D>>>& dists, std::size_t d, D p,
                std::vector<long long>& fills, long long M, long long sumL, Totals& tot) const {
        if (d < dists.size()) {
            for (const auto& [j, pj] : dists[d]) {
                fills[dark_[d]] = j;
                combos(dists, d + 1, p * pj, fills, M, sumL, tot);
            }
            return;
        }
        long long A = M;
        D c = (h_ + f_) * D::integer(M);
        for (std::size_t k = 0; k < fills.size(); ++k) {
            A += fills[k];
            if (fills[k] != 0) c -= coef_[k] * D::integer(fills[k]);
        }
        const long long under = std::max(S_ - A, 0LL), over = std::max(A - S_, 0LL);
        if (theta_.sign() != 0) c += theta_ * D::integer(M + sumL + under);
        if (under != 0) c += lu_ * D::integer(under);
        if (over != 0) c += lo_ * D::integer(over);
        tot.cost += p * c;
        if (want_sq_) tot.sq += (p * c) * c;  // after cost, before fill: the order of the HR-57 checks in sor.py
        tot.fill += p * D::integer(std::min(A, S_));
        if (A < S_) tot.under += p;
    }

    long long S_ = 0;
    mutable bool want_sq_ = false;
    D h_, f_, theta_, lu_, lo_;
    std::vector<bool> lit_kind_;
    std::vector<long long> Q_;
    std::vector<D> coef_;  // h + r - as
    std::vector<std::vector<D>> tails_;
    std::vector<std::size_t> lit_, dark_;
    std::vector<std::vector<long long>> rows_;
};

// HR-40 standard error, the rule of sor.py _se: a = E[c^2] and b = E[c], each exact, rounded half-even to 18
// decimals by long division and read as binary64 (strtod rounds correctly); then se = sqrt(max(a - b * b, 0) / n)
// in binary64 basic operations, each stored through a volatile so no fused multiply-add can form; written from the
// exact binary value rounded half-even to 6 decimals (glibc printf is exact and rounds ties to even).
string std_error(const D& cost, const D& sq, long long rows) {
    const D n = D::integer(rows);
    const volatile double a = std::strtod(div_round(sq, n, 18).c_str(), nullptr);
    const volatile double b = std::strtod(div_round(cost, n, 18).c_str(), nullptr);
    const volatile double bb = b * b;
    const volatile double diff = a - bb;
    const volatile double var = std::max(double(diff), 0.0) / double(rows);
    const double se = std::sqrt(double(var));
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.6f", se);
    return trim(buf);
}

void write_tuple(json::Writer& out, const Tuple& t) {
    out.key("L");
    out.begin_array();
    for (std::size_t i = 1; i < t.size(); ++i) out.string(std::to_string(t[i]));
    out.end_array();
    out.key("M");
    out.string(std::to_string(t[0]));
}

}  // namespace

void sor_allocate(const Value& inp, json::Writer& out) {
    // F-2 (E1): `step` is the router's one Real input, a number or "NaN" / "Infinity" / "-Infinity" (F-1);
    // non-finite is E_DOMAIN, checked first, as sor.py does.
    double step = 1.0;
    if (const Value* st = inp.find("step"); present(st)) {
        if (st->kind == Kind::Number) step = st->number;
        else if (st->kind == Kind::String && st->text == "NaN") step = std::numeric_limits<double>::quiet_NaN();
        else if (st->kind == Kind::String && st->text == "Infinity") step = std::numeric_limits<double>::infinity();
        else if (st->kind == Kind::String && st->text == "-Infinity") step = -std::numeric_limits<double>::infinity();
        else fail("E_SCHEMA", "step", "expected a number");
    }
    if (!std::isfinite(step)) fail("E_DOMAIN", "step", "step: not finite");
    const Problem p(inp);
    const Value* m = inp.find("method");
    const string method = present(m) ? (m->kind == Kind::String ? m->text : "?") : "SAMPLE_AVERAGE";
    if (method != "SAMPLE_AVERAGE" && method != "CLOSED_FORM" && method != "STOCHASTIC_APPROX")
        fail("E_SCHEMA", "method", "method");
    const Value* rk = inp.find("ranking");
    const bool want_rank = rk && rk->kind == Kind::Bool && rk->boolean;
    const Value* se = inp.find("report_se");
    const bool report_se = se && se->kind == Kind::Bool && se->boolean;
    Tuple best;
    std::vector<std::pair<D, Tuple>> ranking;
    if (method == "CLOSED_FORM") {
        best = p.closed_form();
    } else if (method == "STOCHASTIC_APPROX") {
        const long long iters = nonneg_int(inp.find("iterations"), 10'000, "iterations");
        best = p.stochastic(iters, step, std::uint64_t(nonneg_int(inp.find("seed"), 0, "seed")));
    } else if (p.grid_small()) {
        auto scored = p.exhaustive();
        best = scored.front().second;
        if (want_rank) ranking = std::move(scored);
    } else {
        if (want_rank) fail("E_LIMIT", "ranking", "ranking needs a grid of at most 10^6 points");
        best = p.descent(p.start());
    }
    if (report_se) p.want_sq();
    const Totals t = p.evaluate(best);
    const D n = D::integer((long long)p.rows());
    write_tuple(out, best);
    out.key("expected_cost");
    out.string(div_round(t.cost, n, 6));
    if (report_se) {
        out.key("expected_cost_se");
        out.string(std_error(t.cost, t.sq, (long long)p.rows()));
    }
    out.key("expected_fill");
    out.string(div_round(t.fill, n, 6));
    if (report_se) {
        out.key("label");
        out.string(sor_label);
    }
    out.key("p_underfill");
    out.string(div_round(t.under, n, 6));
    if (want_rank) {
        out.key("ranking");
        out.begin_array();
        for (const auto& [c, tup] : ranking) {
            out.begin_object();
            write_tuple(out, tup);
            out.key("expected_cost");
            out.string(div_round(c, n, 6));
            out.end_object();
        }
        out.end_array();
    }
}

}  // namespace quantforge::micro
