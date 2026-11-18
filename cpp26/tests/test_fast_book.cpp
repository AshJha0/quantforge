// H-9 low-latency book (specifications/09-microstructure/low-latency-book.md): equivalence with micro.book.rebuild.
//  1. Every ob_h golden row, decoded to fixed point, through lowlat::Book: book, crc32, stats and events equal the
//     golden; error rows are rejected by the decoder with the golden's code. ob_h-0016 (36 digits) is outside the
//     int64 fixed-point range and is rejected with E_LIMIT: the stated scope limit of the fast book.
//  2. Property test (spec "Golden plan"): 1,000 seeded random streams of 10,000 messages. After every message the
//     fast book's top(100) on both sides equals a direct transcription of the normative algorithm (std::map);
//     at the end of every stream the book, crc32, stats and events equal micro::book_rebuild, the C++ port of
//     micro.book.rebuild that replays the ob_h goldens exactly (test_micro_w2.cpp).
#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "quantforge/core/fast_book.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/microstructure.hpp"
#include "quantforge/core/rng.hpp"

namespace json = quantforge::json;
namespace ll = quantforge::lowlat;

namespace {

struct DecodeError : std::runtime_error {
    std::string code;
    DecodeError(std::string c, const std::string& what) : std::runtime_error(what), code(std::move(c)) {}
};

// Decimal string -> fixed point at `dec` decimals (HR-20). Codes follow order-book.md / HR-57.
std::int64_t to_fixed(const json::Value& v, int dec, bool is_price) {
    if (v.kind != json::Kind::String) throw DecodeError("E_SCHEMA", "price or quantity is not a decimal string");
    const std::string& s = v.text;
    std::size_t k = 0;
    bool neg = false;
    if (k < s.size() && s[k] == '-') neg = true, ++k;
    std::string ip, fp;
    while (k < s.size() && s[k] >= '0' && s[k] <= '9') ip += s[k++];
    if (k < s.size() && s[k] == '.') {
        ++k;
        while (k < s.size() && s[k] >= '0' && s[k] <= '9') fp += s[k++];
        if (fp.empty()) throw DecodeError("E_SCHEMA", "not a decimal: " + s);
    }
    if (k != s.size() || ip.empty()) throw DecodeError("E_SCHEMA", "not a decimal: " + s);
    if (ip.size() + fp.size() > 36 || fp.size() > 18) throw DecodeError("E_LIMIT", "outside the exact decimal range");
    bool zero = true;
    for (char c : ip + fp) zero = zero && c == '0';
    if (neg && !zero) throw DecodeError("E_DOMAIN", "negative value");
    if (is_price && zero) throw DecodeError("E_DOMAIN", "non-positive price");
    for (std::size_t j = std::size_t(dec); j < fp.size(); ++j)
        if (fp[j] != '0') throw DecodeError("E_DOMAIN", "more decimals than the pair's precision");
    fp.resize(std::size_t(dec), '0');
    const std::string digits = ip + fp;
    std::int64_t out = 0;
    for (char c : digits) {
        const int d = c - '0';
        if (out > (INT64_MAX - d) / 10) throw DecodeError("E_LIMIT", "outside the fast book's int64 fixed-point range");
        out = out * 10 + d;
    }
    return out;
}

struct Stream {
    std::vector<ll::Msg> msgs;
    std::vector<ll::Level> levels;
};

Stream decode(const json::Value& inputs) {
    const long long depth = (long long)inputs.find("depth")->number;
    if (depth != 10 && depth != 25 && depth != 100 && depth != 500 && depth != 1000)
        throw DecodeError("E_DOMAIN", "depth not in the list");
    const int pdec = (int)inputs.find("price_decimals")->number, qdec = (int)inputs.find("qty_decimals")->number;
    Stream st;
    for (const json::Value& m : inputs.find("messages")->items) {
        const std::string type = m.find("type") ? m.find("type")->text : "";
        ll::Msg out{};
        out.first = (std::uint32_t)st.levels.size();
        if (type == "gap") {
            out.type = ll::MsgType::Gap;
            st.msgs.push_back(out);
            continue;
        }
        if (type == "snapshot") out.type = ll::MsgType::Snapshot;
        else if (type == "update") out.type = ll::MsgType::Update;
        else throw DecodeError("E_SCHEMA", "unknown message type");
        for (const char* side : {"bids", "asks"}) {
            const json::Value* arr = m.find(side);
            std::uint16_t n = 0;
            for (const json::Value& l : arr->items) {
                st.levels.push_back({to_fixed(l.items.at(0), pdec, true), to_fixed(l.items.at(1), qdec, false)});
                ++n;
            }
            (side[0] == 'b' ? out.n_bids : out.n_asks) = n;
        }
        if (const json::Value* c = m.find("checksum"); c && c->kind == json::Kind::Number) {
            out.flags |= ll::flag_checksum;
            out.checksum = (std::uint32_t)c->number;
        }
        if (const json::Value* r = m.find("resubscribe"); r && r->kind == json::Kind::Bool && r->boolean)
            out.flags |= ll::flag_resubscribe;
        st.msgs.push_back(out);
    }
    return st;
}

std::string fixed_text(std::int64_t v, int dec) {
    std::string d = std::to_string(v);
    if (dec == 0) return d;
    if (d.size() <= std::size_t(dec)) d.insert(0, std::size_t(dec) + 1 - d.size(), '0');
    d.insert(d.size() - std::size_t(dec), ".");
    return d;
}

const char* kind_name(ll::EventKind k) {
    switch (k) {
        case ll::EventKind::ChecksumFail: return "CHECKSUM_FAIL";
        case ll::EventKind::Crossed: return "CROSSED";
        case ll::EventKind::Locked: return "LOCKED";
        case ll::EventKind::Gap: return "GAP";
        default: return "UPDATE_BEFORE_SNAPSHOT";
    }
}

// The fast book's result in the golden's canonical shape (sorted keys, no spaces).
std::string outputs(const ll::Book& b, int pdec, int qdec) {
    std::string o = "{\"book\":{";
    for (const bool bid : {false, true}) {
        std::vector<ll::Level> lv(b.depth());
        const std::size_t n = b.top(bid, lv.size(), lv.data());
        o += bid ? ",\"bids\":[" : "\"asks\":[";
        for (std::size_t k = 0; k < n; ++k)
            o += (k ? ",[\"" : "[\"") + fixed_text(lv[k].px, pdec) + "\",\"" + fixed_text(lv[k].qty, qdec) + "\"]";
        o += "]";
    }
    o += "},\"crc32\":" + std::to_string(b.checksum()) + ",\"events\":[";
    for (std::size_t k = 0; k < b.events().size(); ++k)
        o += (k ? ",{\"i\":" : "{\"i\":") + std::to_string(b.events()[k].i) + ",\"kind\":\"" + kind_name(b.events()[k].kind) + "\"}";
    const ll::Stats& s = b.stats();
    o += "],\"stats\":{\"checkpoint_checked\":0,\"checkpoint_failed\":0,\"checksum_checked\":" + std::to_string(s.checksum_checked) +
         ",\"checksum_failed\":" + std::to_string(s.checksum_failed) + ",\"crossed\":" + std::to_string(s.crossed) +
         ",\"deletes_of_absent_level\":" + std::to_string(s.deletes_of_absent_level) + ",\"gaps\":" + std::to_string(s.gaps) +
         ",\"level_changes\":" + std::to_string(s.level_changes) + ",\"locked\":" + std::to_string(s.locked) +
         ",\"messages\":" + std::to_string(s.messages) + ",\"resyncs\":" + std::to_string(s.resyncs) +
         ",\"snapshots\":" + std::to_string(s.snapshots) + ",\"truncated_levels\":" + std::to_string(s.truncated_levels) +
         ",\"updates\":" + std::to_string(s.updates) + "}}";
    return o;
}

// Canonical text of a parsed value restricted to the keys the fast book produces (events keep i and kind).
std::string canon(const json::Value& v) {
    switch (v.kind) {
        case json::Kind::String: {
            std::string o;
            json::append_string(o, v.text);
            return o;
        }
        case json::Kind::Number: return v.text;
        case json::Kind::Bool: return v.boolean ? "true" : "false";
        case json::Kind::Array: {
            std::string o = "[";
            for (std::size_t k = 0; k < v.items.size(); ++k) o += (k ? "," : "") + canon(v.items[k]);
            return o + "]";
        }
        case json::Kind::Object: {
            std::map<std::string, std::string> m;
            for (const auto& [key, val] : v.members)
                if (key != "detail" && key != "checksum_string" && key != "events_omitted") m[key] = canon(val);
            std::string o = "{";
            bool first = true;
            for (const auto& [key, val] : m) {
                std::string k;
                json::append_string(k, key);
                o += (first ? "" : ",") + k + ":" + val;
                first = false;
            }
            return o + "}";
        }
        default: return "null";
    }
}

ll::Book run_fast(const Stream& st, std::size_t depth) {
    ll::Book b(depth);
    for (const ll::Msg& m : st.msgs) b.apply(m, st.levels.data());
    return b;
}

}  // namespace

#ifdef QF_REPO_DIR
TEST_CASE("fast book: every ob_h golden row", "[lowlat]") {
    std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_h/ob_h.json", std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    const json::Value golden = json::parse(s.str()).value;
    int ok = 0, rejected = 0;
    for (const json::Value& c : golden.find("cases")->items) {
        const std::string id = c.find("case_id")->text;
        const json::Value& in = *c.find("inputs");
        const json::Value& exp = *c.find("expected");
        INFO(id);
        if (id == "ob_h-0016") {  // stated scope limit: 36-digit values do not fit int64 fixed point
            CHECK_THROWS_AS(decode(in), DecodeError);
            continue;
        }
        if (exp.find("status")->text != "ok") {
            std::string code;
            try {
                decode(in);
            } catch (const DecodeError& e) {
                code = e.code;
            }
            CHECK(code == exp.find("error_code")->text);
            ++rejected;
            continue;
        }
        const Stream st = decode(in);
        const ll::Book b = run_fast(st, (std::size_t)in.find("depth")->number);
        CHECK(outputs(b, (int)in.find("price_decimals")->number, (int)in.find("qty_decimals")->number) ==
              canon(*exp.find("outputs")));
        ++ok;
    }
    CHECK(ok == 9);
    CHECK(rejected == 7);
}
#endif

namespace {

// Direct transcription of order-book.md steps 1-5 on std::map (price -> qty), for the per-message check.
struct NaiveBook {
    std::size_t depth;
    std::map<std::int64_t, std::int64_t> bids, asks;
    bool live = false;
    void apply(const ll::Msg& m, const ll::Level* lv) {
        if (m.type == ll::MsgType::Trade) return;
        if (m.type == ll::MsgType::Gap) {
            bids.clear(), asks.clear(), live = false;
            return;
        }
        const ll::Level* lb = lv + m.first;
        const ll::Level* la = lb + m.n_bids;
        if (m.type == ll::MsgType::Snapshot) {
            bids.clear(), asks.clear(), live = true;
            for (int k = 0; k < m.n_bids; ++k)
                if (lb[k].qty) bids[lb[k].px] = lb[k].qty;
            for (int k = 0; k < m.n_asks; ++k)
                if (la[k].qty) asks[la[k].px] = la[k].qty;
        } else {
            if (!live) return;
            for (int k = 0; k < m.n_bids; ++k) lb[k].qty ? void(bids[lb[k].px] = lb[k].qty) : void(bids.erase(lb[k].px));
            for (int k = 0; k < m.n_asks; ++k) la[k].qty ? void(asks[la[k].px] = la[k].qty) : void(asks.erase(la[k].px));
        }
        while (bids.size() > depth) bids.erase(bids.begin());
        while (asks.size() > depth) asks.erase(std::prev(asks.end()));
    }
};

// A random stream on a narrow tick grid so that truncation, crosses, locks, absent deletes, duplicate prices,
// gaps, updates before a snapshot, checksums (some right, most wrong) and resubscribes all occur.
Stream random_stream(std::uint64_t seed, std::size_t depth, int n) {
    quantforge::Xoshiro256 r(seed, 0);
    auto u = [&](std::uint64_t m) { return (std::int64_t)(r.next() % m); };
    Stream st;
    const std::int64_t mid = 1000, span = (std::int64_t)depth + 20;
    for (int i = 0; i < n; ++i) {
        ll::Msg m{};
        m.first = (std::uint32_t)st.levels.size();
        const std::int64_t roll = u(1000);
        if (roll < 3) m.type = ll::MsgType::Gap;
        else if (roll < 15 || i == 1) m.type = ll::MsgType::Snapshot;
        else if (roll < 40) m.type = ll::MsgType::Trade;
        else m.type = ll::MsgType::Update;
        if (m.type == ll::MsgType::Trade) {
            st.levels.push_back({mid + u(10), 1 + u(100)});
            m.n_bids = 1;
        } else if (m.type != ll::MsgType::Gap) {
            const bool snap = m.type == ll::MsgType::Snapshot;
            for (int side = 0; side < 2; ++side) {
                const int L = snap ? (int)u(depth + 15) : (int)(u(10) < 7 ? u(2) : u(6));
                for (int k = 0; k < L; ++k) {
                    // bids below mid+3, asks above mid-3: overlapping by a few ticks, so books can cross.
                    const std::int64_t px = side == 0 ? mid + 3 - u((std::uint64_t)span) : mid - 3 + u((std::uint64_t)span);
                    const std::int64_t q = (!snap && u(10) < 3) || (snap && u(20) == 0) ? 0 : 1 + u(1'000'000);
                    st.levels.push_back({px, q});
                }
                (side == 0 ? m.n_bids : m.n_asks) = (std::uint16_t)L;
            }
            if (u(20) == 0) m.flags |= ll::flag_checksum, m.checksum = (std::uint32_t)r.next();
            if (snap && u(3) == 0) m.flags |= ll::flag_resubscribe;
        }
        st.msgs.push_back(m);
    }
    return st;
}

// The same stream as micro.book.rebuild input JSON (trades are not part of its contract and are left out).
std::string to_json(const Stream& st, std::size_t depth, int pdec, int qdec) {
    std::string o = "[";
    bool first = true;
    for (const ll::Msg& m : st.msgs) {
        if (m.type == ll::MsgType::Trade) continue;
        o += first ? "" : ",";
        first = false;
        if (m.type == ll::MsgType::Gap) {
            o += "{\"type\":\"gap\"}";
            continue;
        }
        o += "{\"type\":\"";
        o += m.type == ll::MsgType::Snapshot ? "snapshot" : "update";
        o += "\",\"t\":\"2026-01-01T00:00:00Z\",\"checksum\":";
        o += (m.flags & ll::flag_checksum) ? std::to_string(m.checksum) : "null";
        if (m.flags & ll::flag_resubscribe) o += ",\"resubscribe\":true";
        for (int side = 0; side < 2; ++side) {
            o += side == 0 ? ",\"bids\":[" : ",\"asks\":[";
            const std::size_t base = m.first + (side == 0 ? 0 : m.n_bids);
            const int n = side == 0 ? m.n_bids : m.n_asks;
            for (int k = 0; k < n; ++k) {
                const ll::Level& l = st.levels[base + (std::size_t)k];
                o += (k ? ",[\"" : "[\"") + fixed_text(l.px, pdec) + "\",\"" + fixed_text(l.qty, qdec) + "\"]";
            }
            o += "]";
        }
        o += "}";
    }
    (void)depth;
    return o + "]";
}

}  // namespace

TEST_CASE("fast book: property test, 1,000 seeded streams of 10,000 messages", "[lowlat][property]") {
    const std::size_t depths[] = {10, 25, 100};
    std::vector<ll::Level> fb(100), fa(100);
    long long compared = 0;
    for (std::uint64_t s = 0; s < 1000; ++s) {
        const std::size_t depth = depths[s % 3];
        const Stream st = random_stream(20261117ULL + s, depth, 10'000);
        ll::Book b(depth);
        NaiveBook nb{depth, {}, {}, false};
        bool same = true;
        for (std::size_t i = 0; i < st.msgs.size() && same; ++i) {
            b.apply(st.msgs[i], st.levels.data());
            nb.apply(st.msgs[i], st.levels.data());
            const std::size_t nbid = b.top(true, 100, fb.data()), nask = b.top(false, 100, fa.data());
            same = nbid == std::min<std::size_t>(100, nb.bids.size()) && nask == std::min<std::size_t>(100, nb.asks.size());
            auto it = nb.bids.rbegin();
            for (std::size_t k = 0; same && k < nbid; ++k, ++it) same = fb[k].px == it->first && fb[k].qty == it->second;
            auto ja = nb.asks.begin();
            for (std::size_t k = 0; same && k < nask; ++k, ++ja) same = fa[k].px == ja->first && fa[k].qty == ja->second;
            for (std::size_t k = 0; same && k < nbid; ++k) same = b.qty_at(true, fb[k].px) == fb[k].qty;
            for (std::size_t k = 0; same && k < nask; ++k) same = b.qty_at(false, fa[k].px) == fa[k].qty;
            ll::Level bb{}, ba{};
            same = same && b.best_bid(bb) == (nbid > 0) && b.best_ask(ba) == (nask > 0);
            same = same && (nbid == 0 || (bb.px == fb[0].px && bb.qty == fb[0].qty)) &&
                   (nask == 0 || (ba.px == fa[0].px && ba.qty == fa[0].qty));
            same = same && b.qty_at(true, 1000 + 4 + std::int64_t(i % 7)) == 0 && b.qty_at(false, 1000 - 4 - std::int64_t(i % 7)) == 0;
            if (!same) UNSCOPED_INFO("stream " << s << " diverges at message " << i);
            ++compared;
        }
        REQUIRE(same);
        // End of stream: the whole contract against the golden-verified C++ port of micro.book.rebuild.
        const json::Value msgs = json::parse(to_json(st, depth, 1, 8)).value;
        json::Writer w;
        w.begin_object();
        quantforge::micro::book_rebuild(msgs, (long long)depth, 1, 8, nullptr, false, w);
        w.end_object();
        INFO("stream " << s);
        REQUIRE(outputs(b, 1, 8) == canon(json::parse(w.str()).value));
    }
    CHECK(compared == 10'000'000);
}

TEST_CASE("fast book: limit cases of low-latency-book.md", "[lowlat]") {
    ll::Book b(3);
    std::vector<ll::Level> lv = {{100, 1}, {99, 1}, {98, 1}, {101, 1}, {102, 1}, {103, 1}};
    b.apply(ll::Msg{ll::MsgType::Snapshot, 0, 3, 3, 0, 0, 0}, lv.data());
    // An update beyond depth on the far side: inserted, then truncated.
    std::vector<ll::Level> far = {{50, 7}};
    b.apply(ll::Msg{ll::MsgType::Update, 0, 1, 0, 0, 0, 0}, far.data());
    CHECK(b.stats().truncated_levels == 1);
    CHECK(b.qty_at(true, 50) == 0);
    // A sweep emptying a side: the empty marker, not an error.
    std::vector<ll::Level> sweep = {{100, 0}, {99, 0}, {98, 0}};
    b.apply(ll::Msg{ll::MsgType::Update, 0, 3, 0, 0, 0, 0}, sweep.data());
    ll::Level best{};
    CHECK_FALSE(b.best_bid(best));
    CHECK(b.best_ask(best));
    CHECK(best.px == 101);
    // A trade changes nothing and is counted apart.
    std::vector<ll::Level> tr = {{101, 1}};
    b.apply(ll::Msg{ll::MsgType::Trade, 0, 1, 0, 0, 0, 0}, tr.data());
    CHECK(b.stats().trades == 1);
    CHECK(b.stats().messages == 3);
    CHECK(b.grows() == 0);
}

TEST_CASE("fast book: a message wider than the spare capacity grows the buffer and stays correct", "[lowlat]") {
    ll::Book b(10);  // capacity 8 * 10 + 64 = 144 per side
    std::vector<ll::Level> lv;
    for (std::int64_t k = 0; k < 400; ++k) lv.push_back({1000 - k, 1});
    b.apply(ll::Msg{ll::MsgType::Snapshot, 0, 400, 0, 0, 0, 0}, lv.data());
    CHECK(b.grows() >= 1);
    std::vector<ll::Level> top(10);
    REQUIRE(b.top(true, 10, top.data()) == 10);
    CHECK(top[0].px == 1000);
    CHECK(top[9].px == 991);
    CHECK(b.stats().truncated_levels == 390);
}

TEST_CASE("fast book: qty_at direct index with shared slots", "[lowlat]") {
    ll::Book b(10);
    // 100, 1124 and 2148 share slot 100 (mod 1024); 101 has its own.
    std::vector<ll::Level> lv = {{2148, 3}, {1124, 2}, {101, 4}, {100, 1}};
    b.apply(ll::Msg{ll::MsgType::Snapshot, 0, 4, 0, 0, 0, 0}, lv.data());
    CHECK(b.qty_at(true, 100) == 1);
    CHECK(b.qty_at(true, 1124) == 2);
    CHECK(b.qty_at(true, 2148) == 3);
    CHECK(b.qty_at(true, 3172) == 0);
    std::vector<ll::Level> del = {{2148, 0}, {1124, 9}};
    b.apply(ll::Msg{ll::MsgType::Update, 0, 2, 0, 0, 0, 0}, del.data());
    CHECK(b.qty_at(true, 2148) == 0);
    CHECK(b.qty_at(true, 1124) == 9);
    CHECK(b.qty_at(true, 100) == 1);
    CHECK(b.index_fallbacks() > 0);
    ll::Level best{};
    REQUIRE(b.best_bid(best));
    CHECK(best.px == 1124);
    CHECK(best.qty == 9);
    std::vector<ll::Level> gap = {};
    b.apply(ll::Msg{ll::MsgType::Gap, 0, 0, 0, 0, 0, 0}, gap.data());
    CHECK_FALSE(b.best_bid(best));
    CHECK(b.qty_at(true, 100) == 0);
    CHECK(b.qty_at(true, 1124) == 0);
}
