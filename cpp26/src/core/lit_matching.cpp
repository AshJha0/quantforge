// exec.sim.lit.run: a simulated lit matching engine, price-time priority
// (specifications/10-execution/lit-matching.md; rulings HR-25 to HR-31). Simulated venue; not a real exchange.
// Prices, quantities and fees are exact decimals (HR-12); the engine is deterministic.
//
// Priority within a price (HR-27): displayed quantity by `seq`, then non-displayed PEG_MID orders by `seq`.
// An iceberg's hidden quantity is refreshed into a new displayed slice at the back of the queue (new `seq`) as
// soon as its shown part is filled ([CME-FIFO]), so hidden quantity trades after every displayed order ahead
// of the refresh. Pegs are stepped one tick away from the opposite best (other pegs included), so a peg never
// takes and two PEG_MIDs never lock (the Python reference's rule, found by its property test).
#include <algorithm>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/microstructure.hpp"

namespace quantforge::micro {
namespace {

using json::Kind;
using json::Value;
using D = ExactDecimal;
using std::string;
using Price = std::optional<D>;

[[noreturn]] void fail(const char* code, const string& path, const string& why) { throw Error(code, path + ": " + why, path); }

D dec(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String || !D::well_formed(v->text)) fail("E_SCHEMA", path, "not a decimal string");
    return D::parse(v->text);
}

bool present(const Value* v) { return v != nullptr && v->kind != Kind::Null; }

enum class Type { Limit, Market, Ioc, Fok, Iceberg, PostOnly, PegMid, PegPrimary };
constexpr std::pair<std::string_view, Type> type_names[] = {
    {"LIMIT", Type::Limit},   {"MARKET", Type::Market},       {"IOC", Type::Ioc},        {"FOK", Type::Fok},
    {"ICEBERG", Type::Iceberg}, {"POST_ONLY", Type::PostOnly}, {"PEG_MID", Type::PegMid}, {"PEG_PRIMARY", Type::PegPrimary}};

bool is_peg(Type t) { return t == Type::PegMid || t == Type::PegPrimary; }

struct Order {
    string id, trader;
    bool buy = true;
    Type type = Type::Limit;
    Price cap;    // the limit; for pegs the cap
    Price price;  // current resting price; empty for an unpriced peg
    D display, hidden, slice;
    long long seq = 0;
    D open() const { return display + hidden; }
};

struct Cons {
    D submitted, filled, resting, cancelled, rejected;
};

struct Fill {
    string taker, maker;
    D price, qty;
};

class Engine {
public:
    Engine(D tick, D lot, D taker_fee, D maker_rebate) : tick_(tick), lot_(lot), taker_fee_(taker_fee), maker_rebate_(maker_rebate) {}

    void new_order(const Value& e, const string& path);
    void cancel(const Value& e, const string& path);
    void modify(const Value& e, const string& path);
    void reprice();
    void output(json::Writer& out);

private:
    long long next_seq() { return ++seq_; }

    void on_grid(D x, D unit, const char* what) const {
        if (!x.multiple_of(unit)) fail("E_DOMAIN", what, x.str() + " is not a multiple of " + unit.str());
    }

    std::vector<Order*> side(bool buy) {
        std::vector<Order*> v;
        for (auto& [id, o] : resting_)
            if (o.buy == buy && o.price) v.push_back(&o);
        return v;
    }

    Price best(bool buy, bool exclude_mid = false, const string* exclude = nullptr) {
        Price b;
        for (const Order* o : side(buy)) {
            if ((exclude_mid && o->type == Type::PegMid) || (exclude && o->id == *exclude)) continue;
            if (!b || (buy ? *b < *o->price : *o->price < *b)) b = o->price;
        }
        return b;
    }

    static bool marketable(bool buy, const Price& limit, D price) { return !limit || (buy ? price <= *limit : price >= *limit); }

    D available(bool buy, const Price& limit) {
        D s;
        for (const Order* o : side(!buy))
            if (marketable(buy, limit, *o->price)) s += o->open();
        return s;
    }

    // The order first in the queue at `price`: displayed by seq, then PEG_MID by seq.
    Order* head(bool buy_side, D price) {
        Order* h = nullptr;
        for (Order* o : side(buy_side)) {
            if (!(*o->price == price)) continue;
            if (h == nullptr) {
                h = o;
                continue;
            }
            const bool om = o->type == Type::PegMid, hm = h->type == Type::PegMid;
            if (om != hm ? hm : o->seq < h->seq) h = o;
        }
        return h;
    }

    D match(Order& taker, const Price& limit, D qty) {
        while (qty.sign() > 0) {
            const Price p = best(!taker.buy);
            if (!p || !marketable(taker.buy, limit, *p)) break;
            Order& maker = *head(!taker.buy, *p);
            const D avail = maker.type == Type::PegMid ? maker.hidden : maker.display;
            const D q = std::min(qty, avail);
            trade(taker, maker, *p, q);
            qty -= q;
            if (maker.type == Type::PegMid) {
                maker.hidden -= q;
            } else {
                maker.display -= q;
                if (maker.display.sign() == 0 && maker.hidden.sign() > 0) {  // iceberg refresh, back of the queue
                    maker.display = std::min(maker.slice, maker.hidden);
                    maker.hidden -= maker.display;
                    maker.seq = next_seq();
                }
            }
            if (maker.open().sign() == 0) resting_.erase(maker.id);
        }
        return qty;
    }

    void trade(const Order& taker, const Order& maker, D price, D q) {
        fills_.push_back({taker.id, maker.id, price, q});
        const D notional = price * q;
        fees_[taker.trader] += taker_fee_ * notional;
        fees_[maker.trader] -= maker_rebate_ * notional;
        cons_[taker.id].filled += q;
        cons_[maker.id].filled += q;
    }

    Price peg_price(const Order& o) {
        D p;
        if (o.type == Type::PegMid) {
            const Price bb = best(true, true), ba = best(false, true);
            if (!bb || !ba) return std::nullopt;
            // floor (bid) or ceil (ask) of mid / tick, HR-28
            p = (*bb + *ba).divide_integral(D::integer(2) * tick_, !o.buy) * tick_;
        } else {
            const Price same = best(o.buy, true, &o.id);
            if (!same) return std::nullopt;
            p = *same;
        }
        p = o.buy ? std::min(p, *o.cap) : std::max(p, *o.cap);
        // HR-28, rounded away from crossing: a peg never takes, so it stays a tick away from the opposite best.
        const Price opp = best(!o.buy, false, &o.id);
        if (opp && (o.buy ? p >= *opp : p <= *opp)) p = o.buy ? *opp - tick_ : *opp + tick_;
        if (p.sign() <= 0) return std::nullopt;
        return p;
    }

    void reject(const string& id, const char* reason, D qty) {
        rejects_.emplace_back(id, reason);
        cons_[id].rejected += qty;
    }

    D tick_, lot_, taker_fee_, maker_rebate_;
    std::map<string, Order> resting_;
    std::set<string> seen_;
    long long seq_ = 0;
    std::vector<Fill> fills_;
    std::vector<std::pair<string, string>> rejects_, cancelled_;
    std::map<string, D> fees_;
    std::map<string, Cons> cons_;
};

void Engine::reprice() {
    std::vector<Order*> pegs;
    for (auto& [id, o] : resting_)
        if (is_peg(o.type)) pegs.push_back(&o);
    std::sort(pegs.begin(), pegs.end(), [](const Order* a, const Order* b) { return a->seq < b->seq; });
    for (Order* o : pegs) {
        const Price p = peg_price(*o);
        if (p != o->price) {
            o->price = p;
            o->seq = next_seq();
        }
    }
}

void Engine::new_order(const Value& e, const string& path) {
    const Value* id = e.find("id");
    const Value* trader = e.find("trader");
    if (!id || id->kind != Kind::String || !trader || trader->kind != Kind::String)
        fail("E_SCHEMA", path, "id and trader must be strings");
    const Value* side_v = e.find("side");
    const Value* type_v = e.find("type");
    const bool side_ok = side_v && side_v->kind == Kind::String && (side_v->text == "BUY" || side_v->text == "SELL");
    std::optional<Type> typ;
    if (type_v && type_v->kind == Kind::String)
        for (const auto& [name, t] : type_names)
            if (type_v->text == name) typ = t;
    if (!side_ok || !typ) fail("E_SCHEMA", path, "bad side or type");
    const D qty = dec(e.find("qty"), path + "/qty");
    Price limit;
    if (*typ != Type::Market) limit = dec(e.find("price"), path + "/price");
    if (*typ == Type::Market && present(e.find("price"))) fail("E_SCHEMA", path, "MARKET takes no price");
    if (qty.sign() <= 0) fail("E_DOMAIN", path, "quantity must be positive");
    on_grid(qty, lot_, "qty");
    if (limit) {
        if (limit->sign() <= 0) fail("E_DOMAIN", path, "price must be positive");
        on_grid(*limit, tick_, "price");
    }
    D slice = qty;
    if (*typ == Type::Iceberg) {
        slice = dec(e.find("display_qty"), path + "/display_qty");
        if (slice.sign() <= 0 || qty < slice) fail("E_DOMAIN", path, "display_qty must be in (0, qty]");
        on_grid(slice, lot_, "display_qty");
    }
    const string& oid = id->text;
    if (!seen_.insert(oid).second) throw Error("E_INPUT", path + ": duplicate id " + oid, path);
    cons_[oid] = Cons{qty, {}, {}, {}, {}};
    const bool buy = side_v->text == "BUY";
    Order o{oid, trader->text, buy, *typ, limit, limit, {}, {}, slice, 0};
    if (*typ == Type::Fok && available(buy, limit) < qty) return reject(oid, "FOK_UNFILLABLE", qty);
    if (*typ == Type::PostOnly) {
        const Price p = best(!buy);
        if (p && marketable(buy, limit, *p)) return reject(oid, "POST_ONLY_WOULD_CROSS", qty);
    }
    if (is_peg(*typ)) {
        o.price = peg_price(o);
        o.seq = next_seq();
        (*typ == Type::PegMid ? o.hidden : o.display) = qty;
        resting_.emplace(oid, std::move(o));
        return;
    }
    const D rest = match(o, limit, qty);
    if (rest.sign() == 0) return;
    if (*typ == Type::Market || *typ == Type::Ioc) {
        cancelled_.emplace_back(oid, rest.str());
        cons_[oid].cancelled += rest;
        return;
    }
    o.display = std::min(slice, rest);
    o.hidden = rest - o.display;
    o.seq = next_seq();
    resting_.emplace(oid, std::move(o));
}

void Engine::cancel(const Value& e, const string& path) {
    const Value* id = e.find("id");
    if (!id || id->kind != Kind::String) fail("E_SCHEMA", path, "id must be a string");
    const auto it = resting_.find(id->text);
    if (it == resting_.end()) {
        rejects_.emplace_back(id->text, "UNKNOWN_ID");
        return;
    }
    const D open = it->second.open();
    cancelled_.emplace_back(id->text, open.str());
    cons_[id->text].cancelled += open;
    resting_.erase(it);
}

void Engine::modify(const Value& e, const string& path) {
    const Value* id = e.find("id");
    if (!id || id->kind != Kind::String) fail("E_SCHEMA", path, "id must be a string");
    const D qty = dec(e.find("qty"), path + "/qty");
    if (qty.sign() <= 0) fail("E_DOMAIN", path, "quantity must be positive");
    on_grid(qty, lot_, "qty");
    if (present(e.find("price"))) fail("E_SCHEMA", path, "MODIFY takes id and qty only (wave 1b)");
    const auto it = resting_.find(id->text);
    if (it == resting_.end()) {
        rejects_.emplace_back(id->text, "UNKNOWN_ID");
        return;
    }
    Order& o = it->second;
    // `qty` is the new open displayed quantity; a PEG_MID's whole quantity is non-displayed.
    D& field = o.type == Type::PegMid ? o.hidden : o.display;
    const D old = field;
    if (qty == old) return;
    field = qty;
    if (qty < old) {
        cons_[o.id].cancelled += old - qty;
    } else {
        cons_[o.id].submitted += qty - old;
        o.seq = next_seq();
    }
}

void Engine::output(json::Writer& out) {
    const auto pair_list = [&](const char* key, const char* second, const std::vector<std::pair<string, string>>& v) {
        out.key(key);
        out.begin_array();
        for (const auto& [a, b] : v) {
            out.begin_object();
            out.key("id");
            out.string(a);
            out.key(second);
            out.string(b);
            out.end_object();
        }
        out.end_array();
    };
    // Sorted keys (HR-29): book, cancelled, conservation, fees, fills, label, mbp, rejects.
    std::map<D, D> levels[2];  // asks, bids: displayed quantity per price
    out.key("book");
    out.begin_object();
    for (const bool buy : {false, true}) {
        std::vector<const Order*> priced, unpriced;
        for (const auto& [id, o] : resting_)
            if (o.buy == buy) (o.price ? priced : unpriced).push_back(&o);
        std::sort(priced.begin(), priced.end(), [buy](const Order* a, const Order* b) {
            if (!(*a->price == *b->price)) return buy ? *b->price < *a->price : *a->price < *b->price;
            return a->seq < b->seq;
        });
        std::sort(unpriced.begin(), unpriced.end(), [](const Order* a, const Order* b) { return a->seq < b->seq; });
        priced.insert(priced.end(), unpriced.begin(), unpriced.end());
        out.key(buy ? "bids" : "asks");
        out.begin_array();
        for (const Order* o : priced) {
            out.begin_object();
            out.key("display_qty");
            out.string(o->display.str());
            out.key("hidden_qty");
            out.string(o->hidden.str());
            out.key("id");
            out.string(o->id);
            out.key("price");
            if (o->price) out.string(o->price->str());
            else out.null();
            out.key("seq");
            out.integer(o->seq);
            out.end_object();
            if (o->price) levels[buy ? 1 : 0][*o->price] += o->display;
        }
        out.end_array();
    }
    out.end_object();
    pair_list("cancelled", "qty", cancelled_);
    out.key("conservation");
    out.begin_object();
    for (auto& [oid, c] : cons_) {
        const auto live = resting_.find(oid);
        c.resting = live == resting_.end() ? D{} : live->second.open();
        out.key(oid);
        out.begin_object();
        const std::pair<const char*, const D*> fields[] = {{"cancelled", &c.cancelled}, {"filled", &c.filled},
                                                            {"rejected", &c.rejected},   {"resting", &c.resting},
                                                            {"submitted", &c.submitted}};
        for (const auto& [k, v] : fields) {
            out.key(k);
            out.string(v->str());
        }
        out.end_object();
    }
    out.end_object();
    out.key("fees");
    out.begin_object();
    for (const auto& [t, v] : fees_) {
        out.key(t);
        out.string(v.str());
    }
    out.end_object();
    out.key("fills");
    out.begin_array();
    long long n = 0;
    for (const Fill& f : fills_) {
        out.begin_object();
        out.key("maker_id");
        out.string(f.maker);
        out.key("price");
        out.string(f.price.str());
        out.key("qty");
        out.string(f.qty.str());
        out.key("seq");
        out.integer(++n);
        out.key("taker_id");
        out.string(f.taker);
        out.end_object();
    }
    out.end_array();
    out.key("label");
    out.string(lit_label);
    out.key("mbp");
    out.begin_object();
    for (const bool buy : {false, true}) {
        out.key(buy ? "bids" : "asks");
        out.begin_array();
        const auto write = [&](const D& p, const D& q) {
            if (q.sign() <= 0) return;
            out.begin_array();
            out.string(p.str());
            out.string(q.str());
            out.end_array();
        };
        const auto& lv = levels[buy ? 1 : 0];
        if (buy)
            for (auto it = lv.rbegin(); it != lv.rend(); ++it) write(it->first, it->second);
        else
            for (const auto& [p, q] : lv) write(p, q);
        out.end_array();
    }
    out.end_object();
    pair_list("rejects", "reason", rejects_);
}

}  // namespace

void lit_run(std::string_view tick_size, std::string_view lot_size, const Value& events, const Value& fee_schedule,
             json::Writer& out) {
    if (!D::well_formed(tick_size)) fail("E_SCHEMA", "tick_size", "not a decimal string");
    const D tick = D::parse(tick_size);
    if (!D::well_formed(lot_size)) fail("E_SCHEMA", "lot_size", "not a decimal string");
    const D lot = D::parse(lot_size);
    if (tick.sign() <= 0 || lot.sign() <= 0) fail("E_DOMAIN", "tick_size", "tick_size and lot_size must be positive");
    const D taker = dec(fee_schedule.find("taker_fee"), "fee_schedule/taker_fee");
    const D rebate = dec(fee_schedule.find("maker_rebate"), "fee_schedule/maker_rebate");
    if ((long long)events.items.size() > max_lit_events) throw Error("E_LIMIT", "more than 10,000,000 events", "events");
    Engine eng(tick, lot, taker, rebate);
    for (std::size_t k = 0; k < events.items.size(); ++k) {
        const Value& e = events.items[k];
        const string path = "events/" + std::to_string(k);
        const Value* op = e.kind == Kind::Object ? e.find("op") : nullptr;
        if (!op || op->kind != Kind::String || (op->text != "NEW" && op->text != "CANCEL" && op->text != "MODIFY"))
            fail("E_SCHEMA", "events", path + " is not an event");
        if (op->text == "NEW") eng.new_order(e, path);
        else if (op->text == "CANCEL") eng.cancel(e, path);
        else eng.modify(e, path);
        eng.reprice();
    }
    eng.output(out);
}

}  // namespace quantforge::micro
