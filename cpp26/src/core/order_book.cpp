// micro.book.rebuild: market-by-price book rebuild from Kraken-style L2 messages
// (specifications/09-microstructure/order-book.md; rulings HR-11 to HR-17, HR-29, HR-41).
// The book keeps the price and quantity strings as received; ordering and equality use exact decimals.
// Checksum failures, crossed and locked books are counted and reported, never raised.
#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/dates.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/microstructure.hpp"

namespace quantforge::micro {
namespace {

using json::Kind;
using json::Value;
using D = ExactDecimal;
using std::string;

[[noreturn]] void fail(const char* code, const string& path, const string& why) { throw Error(code, path + ": " + why, path); }

D dec(const Value& v, const string& path) {
    if (v.kind != Kind::String || !D::well_formed(v.text)) fail("E_SCHEMA", path, "not a decimal string");
    return D::parse(v.text);
}

struct Level {
    D price;
    string ptext;
    D qty;
    string qtext;
};

std::vector<Level> levels(const Value* raw, const string& path) {
    std::vector<Level> out;
    if (raw == nullptr) return out;  // absent: no levels
    if (raw->kind != Kind::Array) fail("E_SCHEMA", path, "not an array");
    for (std::size_t k = 0; k < raw->items.size(); ++k) {
        const Value& lv = raw->items[k];
        const string at = path + "/" + std::to_string(k);
        if (lv.kind != Kind::Array || lv.items.size() != 2) fail("E_SCHEMA", at, "not a [price, qty] pair");
        const D p = dec(lv.items[0], at + "/0"), q = dec(lv.items[1], at + "/1");
        if (p.sign() <= 0) fail("E_DOMAIN", at, "price must be positive");
        if (q.sign() < 0) fail("E_DOMAIN", at, "negative quantity");
        out.push_back({p, lv.items[0].text, q, lv.items[1].text});
    }
    return out;
}

// RFC 3339 to microseconds; the fraction is read here because parse_instant keeps whole seconds.
long long instant(const Value* v, const string& path) {
    if (v == nullptr || v->kind != Kind::String) fail("E_SCHEMA", path, "not a timestamp");
    string t = v->text;
    long long micros = 0;
    if (t.size() > 20 && t[19] == '.') {
        std::size_t e = 20;
        int n = 0;
        while (e < t.size() && t[e] >= '0' && t[e] <= '9') {
            if (n < 6) micros = micros * 10 + (t[e] - '0');
            ++n;
            ++e;
        }
        if (n == 0) fail("E_SCHEMA", path, "not a timestamp");
        for (; n < 6; ++n) micros *= 10;
        t.erase(19, e - 19);
    }
    const auto s = parse_instant(t);
    if (!s) fail("E_SCHEMA", path, "not a timestamp");
    return *s * 1'000'000 + micros;
}

struct Msg {
    enum Type { Snapshot, Update, Gap } type = Gap;
    std::vector<Level> bids, asks;
    std::optional<std::uint32_t> checksum;
    bool resubscribe = false;
    std::optional<long long> t;
};

struct Checkpoint {
    long long t;
    std::vector<Level> bids, asks;
};

// [KR-CRC]: the value at the pair's precision, decimal point and leading zeros removed.
string component(const string& text, int decimals) {
    string fixed;
    if (!D::parse(text).fixed(decimals, fixed)) fail("E_DOMAIN", text, "has more than " + std::to_string(decimals) + " decimals");
    string s;
    for (const char c : fixed)
        if (c != '.') s += c;
    const auto first = s.find_first_not_of('0');
    return first == string::npos ? "0" : s.substr(first);
}

using Side = std::map<D, string>;  // price -> quantity text

struct Book {
    std::size_t depth;
    Side bids, asks;  // ascending by price; bids are read from the back
    std::map<D, string> ptext;

    Side& side(bool bid) { return bid ? bids : asks; }

    // (price text, qty text) best first.
    std::vector<std::pair<string, string>> ordered(bool bid) const {
        std::vector<std::pair<string, string>> out;
        const Side& s = bid ? bids : asks;
        if (bid)
            for (auto it = s.rbegin(); it != s.rend(); ++it) out.emplace_back(ptext.at(it->first), it->second);
        else
            for (const auto& [p, q] : s) out.emplace_back(ptext.at(p), q);
        return out;
    }

    long long truncate() {
        long long dropped = 0;
        while (bids.size() > depth) {
            bids.erase(bids.begin());
            ++dropped;
        }
        while (asks.size() > depth) {
            asks.erase(std::prev(asks.end()));
            ++dropped;
        }
        return dropped;
    }

    string checksum_string(int pdec, int qdec) const {
        string out;
        for (const bool bid : {false, true}) {  // asks ascending, then bids descending
            const auto lv = ordered(bid);
            for (std::size_t k = 0; k < lv.size() && k < 10; ++k)
                out += component(lv[k].first, pdec) + component(lv[k].second, qdec);
        }
        return out;
    }
};

constexpr std::array<const char*, 14> stat_names = {
    "checkpoint_checked", "checkpoint_failed", "checksum_checked", "checksum_failed", "crossed",
    "deletes_of_absent_level", "gaps", "level_changes", "locked", "messages",
    "resyncs", "snapshots", "truncated_levels", "updates"};  // sorted, as written
enum Stat { CpChecked, CpFailed, CsChecked, CsFailed, Crossed, DelAbsent, Gaps, LevelChanges, Locked, Messages, Resyncs, Snapshots, Truncated, Updates };

}  // namespace

std::uint32_t crc32(std::string_view bytes) {
    static const auto table = [] {
        std::array<std::uint32_t, 256> t{};
        for (std::uint32_t n = 0; n < 256; ++n) {
            std::uint32_t c = n;
            for (int k = 0; k < 8; ++k) c = (c & 1U) ? 0xEDB88320U ^ (c >> 1) : c >> 1;
            t[n] = c;
        }
        return t;
    }();
    std::uint32_t c = 0xFFFFFFFFU;
    for (const char ch : bytes) c = table[(c ^ static_cast<unsigned char>(ch)) & 0xFFU] ^ (c >> 8);
    return c ^ 0xFFFFFFFFU;
}

void book_rebuild(const Value& messages, long long depth, long long price_decimals, long long qty_decimals,
                  const Value* checkpoints, bool emit_checksum_string, json::Writer& out) {
    if (depth != 10 && depth != 25 && depth != 100 && depth != 500 && depth != 1000)
        fail("E_DOMAIN", "depth", "must be one of 10, 25, 100, 500, 1000");
    if (price_decimals < 0 || price_decimals > 18 || qty_decimals < 0 || qty_decimals > 18)
        fail("E_DOMAIN", "price_decimals", "decimals out of range");
    if ((long long)messages.items.size() > max_book_messages) throw Error("E_LIMIT", "more than 50,000,000 messages", "messages");
    const int pdec = int(price_decimals), qdec = int(qty_decimals);

    // Parse everything first: schema and domain errors come before any counting.
    std::vector<Msg> parsed;
    parsed.reserve(messages.items.size());
    for (std::size_t i = 0; i < messages.items.size(); ++i) {
        const Value& m = messages.items[i];
        const string at = "messages/" + std::to_string(i);
        const Value* type = m.kind == Kind::Object ? m.find("type") : nullptr;
        if (type == nullptr || type->kind != Kind::String || (type->text != "snapshot" && type->text != "update" && type->text != "gap"))
            fail("E_SCHEMA", "messages", at + " is not a message");
        Msg msg;
        if (type->text == "gap") {
            parsed.push_back(std::move(msg));
            continue;
        }
        msg.type = type->text == "snapshot" ? Msg::Snapshot : Msg::Update;
        if (const Value* cs = m.find("checksum"); cs && cs->kind != Kind::Null) {
            if (cs->kind != Kind::Number || !cs->integral || cs->number < 0 || cs->number >= 4294967296.0)
                fail("E_SCHEMA", "messages", at + "/checksum is not a u32");
            msg.checksum = std::uint32_t(cs->number);
        }
        if (const Value* t = m.find("t"); t && t->kind != Kind::Null) msg.t = instant(t, at + "/t");
        msg.bids = levels(m.find("bids"), at + "/bids");
        msg.asks = levels(m.find("asks"), at + "/asks");
        const Value* rs = m.find("resubscribe");
        msg.resubscribe = rs && rs->kind == Kind::Bool && rs->boolean;
        parsed.push_back(std::move(msg));
    }
    std::vector<Checkpoint> cps;
    if (checkpoints != nullptr) {
        for (std::size_t k = 0; k < checkpoints->items.size(); ++k) {
            const Value& c = checkpoints->items[k];
            const string at = "checkpoints/" + std::to_string(k);
            if (c.kind != Kind::Object) fail("E_SCHEMA", "checkpoints", at + " is not an object");
            Checkpoint cp{instant(c.find("t"), at + "/t"), {}, {}};
            cp.bids = levels(c.find("bids"), at + "/bids");
            cp.asks = levels(c.find("asks"), at + "/asks");
            cps.push_back(std::move(cp));
        }
    }

    std::array<long long, 14> stats{};
    std::vector<std::pair<long long, const char*>> events;
    long long omitted = 0;
    Book book{std::size_t(depth), {}, {}, {}};
    bool live = false, pending_resync = false;
    std::size_t cp_next = 0;

    const auto event = [&](long long i, const char* kind) {
        if (events.size() < max_book_events) events.emplace_back(i, kind);
        else ++omitted;
    };
    const auto checkpoint = [&](long long i, std::optional<long long> upto) {
        while (cp_next < cps.size() && (!upto || cps[cp_next].t < *upto)) {
            const Checkpoint& cp = cps[cp_next++];
            ++stats[CpChecked];
            bool ok = true;
            for (const bool bid : {true, false}) {
                const std::vector<Level>& lv = bid ? cp.bids : cp.asks;
                std::vector<std::pair<D, D>> want;
                for (const Level& l : lv) want.emplace_back(l.price, l.qty);
                std::sort(want.begin(), want.end(), [bid](const auto& a, const auto& b) {
                    return bid ? b < a : a < b;
                });
                std::vector<std::pair<D, D>> ours;
                const Side& s = book.side(bid);
                if (bid)
                    for (auto it = s.rbegin(); it != s.rend() && ours.size() < lv.size(); ++it) ours.emplace_back(it->first, D::parse(it->second));
                else
                    for (auto it = s.begin(); it != s.end() && ours.size() < lv.size(); ++it) ours.emplace_back(it->first, D::parse(it->second));
                if (ours != want) ok = false;
            }
            if (!ok) {
                ++stats[CpFailed];
                event(i, "CHECKPOINT_FAIL");
            }
        }
    };

    for (std::size_t n = 0; n < parsed.size(); ++n) {
        const Msg& m = parsed[n];
        const auto i = (long long)n;
        if (m.type == Msg::Gap) {
            ++stats[Gaps];
            book = Book{std::size_t(depth), {}, {}, {}};
            live = false;
            event(i, "GAP");
            continue;
        }
        if (!cps.empty() && m.t) checkpoint(i - 1, m.t);
        ++stats[Messages];
        if (m.type == Msg::Snapshot) {
            ++stats[Snapshots];
            if (m.resubscribe && pending_resync) ++stats[Resyncs];
            pending_resync = false;
            book = Book{std::size_t(depth), {}, {}, {}};
            for (const bool bid : {true, false})
                for (const Level& l : bid ? m.bids : m.asks)
                    if (l.qty.sign() != 0) {
                        book.side(bid)[l.price] = l.qtext;
                        book.ptext[l.price] = l.ptext;
                    }
            live = true;
        } else {
            ++stats[Updates];
            if (!live) {
                event(i, "UPDATE_BEFORE_SNAPSHOT");
                continue;
            }
            for (const bool bid : {true, false}) {
                Side& d = book.side(bid);
                for (const Level& l : bid ? m.bids : m.asks) {
                    ++stats[LevelChanges];
                    if (l.qty.sign() == 0) {
                        if (d.erase(l.price) == 0) ++stats[DelAbsent];
                    } else {
                        d[l.price] = l.qtext;
                        book.ptext[l.price] = l.ptext;
                    }
                }
            }
        }
        stats[Truncated] += book.truncate();
        if (m.checksum) {
            ++stats[CsChecked];
            if (crc32(book.checksum_string(pdec, qdec)) != *m.checksum) {
                ++stats[CsFailed];
                pending_resync = true;
                event(i, "CHECKSUM_FAIL");
            }
        }
        if (!book.bids.empty() && !book.asks.empty()) {
            const D& bb = std::prev(book.bids.end())->first;
            const D& ba = book.asks.begin()->first;
            if (ba < bb) {
                ++stats[Crossed];
                event(i, "CROSSED");
            } else if (bb == ba) {
                ++stats[Locked];
                event(i, "LOCKED");
            }
        }
    }
    if (!cps.empty()) checkpoint((long long)parsed.size() - 1, std::nullopt);

    const string final_string = book.checksum_string(pdec, qdec);
    out.key("book");
    out.begin_object();
    for (const bool bid : {false, true}) {  // asks, bids (sorted keys)
        out.key(bid ? "bids" : "asks");
        out.begin_array();
        for (const auto& [p, q] : book.ordered(bid)) {
            out.begin_array();
            out.string(p);
            out.string(q);
            out.end_array();
        }
        out.end_array();
    }
    out.end_object();
    if (emit_checksum_string) {
        out.key("checksum_string");
        out.string(final_string);
    }
    out.key("crc32");
    out.integer((long long)crc32(final_string));
    out.key("events");
    out.begin_array();
    for (const auto& [i, kind] : events) {
        out.begin_object();
        out.key("i");
        out.integer(i);
        out.key("kind");
        out.string(kind);
        out.end_object();
    }
    out.end_array();
    if (omitted != 0) {
        out.key("events_omitted");
        out.integer(omitted);
    }
    out.key("stats");
    out.begin_object();
    for (std::size_t k = 0; k < stat_names.size(); ++k) {
        out.key(stat_names[k]);
        out.integer(stats[k]);
    }
    out.end_object();
}

}  // namespace quantforge::micro
