// Stage H wave 2: every row of the ob_h and lit_h goldens through the CLI layer (exact: decimal strings and
// integers compared as text), plus the lit-matching invariants of specifications/10-execution/lit-matching.md
// (quantity conservation per order, book never crossed, FOK all or nothing, post-only never takes, replay
// determinism) on random event streams, and the exact-decimal and CRC32 units.
#include <catch2/catch_test_macros.hpp>
#include <fstream>
#include <map>
#include <random>
#include <sstream>
#include <string>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/microstructure.hpp"

namespace {

namespace json = quantforge::json;
using D = quantforge::ExactDecimal;

std::string to_text(const json::Value& v) {
    std::string out;
    switch (v.kind) {
        case json::Kind::Number: return v.text;
        case json::Kind::String: json::append_string(out, v.text); return out;
        case json::Kind::Bool: return v.boolean ? "true" : "false";
        case json::Kind::Array:
            out = "[";
            for (std::size_t i = 0; i < v.items.size(); ++i) out += (i ? "," : "") + to_text(v.items[i]);
            return out + "]";
        case json::Kind::Object:
            out = "{";
            for (std::size_t i = 0; i < v.members.size(); ++i) {
                if (i) out += ",";
                json::append_string(out, v.members[i].first);
                out += ":" + to_text(v.members[i].second);
            }
            return out + "}";
        default: return "null";
    }
}

std::string run(const std::string& op, const std::string& inputs) {
    return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op + R"(","inputs":)" +
                                     inputs + "}")
        .json;
}

json::Value outputs_of(const std::string& result) {
    json::Value doc = json::parse(result).value;
    REQUIRE(doc.find("status")->text == "ok");
    return *doc.find("outputs");
}

#ifdef QF_REPO_DIR
void replay(const char* suite, int expect_cases) {
    std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_h/" + suite + ".json", std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    const json::Value golden = json::parse(s.str()).value;
    int n = 0;
    for (const json::Value& c : golden.find("cases")->items) {
        ++n;
        const std::string id = c.find("case_id")->text;
        const json::Value& exp = *c.find("expected");
        const std::string got = run(c.find("operation")->text, to_text(*c.find("inputs")));
        const json::Value doc = json::parse(got).value;
        INFO(id << " -> " << got);
        REQUIRE(doc.find("status")->text == exp.find("status")->text);
        if (exp.find("status")->text == "ok") CHECK(to_text(*doc.find("outputs")) == to_text(*exp.find("outputs")));
        else CHECK(doc.find("error")->find("code")->text == exp.find("error_code")->text);
    }
    CHECK(n == expect_cases);
}

TEST_CASE("ob_h goldens: every row", "[micro_w2]") { replay("ob_h", 14); }
TEST_CASE("lit_h goldens: every row", "[micro_w2]") { replay("lit_h", 15); }
#endif

TEST_CASE("exact decimal units", "[micro_w2]") {
    CHECK(D::parse("0.00100000").str() == "0.001");
    CHECK(D::parse("100.0") == D::parse("100"));
    CHECK(D::parse("-0.5") < D::parse("0.25"));
    CHECK((D::parse("0.001") * D::parse("101") * D::parse("10")).str() == "1.01");
    CHECK((D::parse("0") - D::parse("0.0002") * D::parse("1020")).str() == "-0.204");
    CHECK(D::parse("100.5").multiple_of(D::parse("0.5")));
    CHECK(!D::parse("100.5").multiple_of(D::parse("1")));
    CHECK(D::parse("203").divide_integral(D::parse("2"), false).str() == "101");
    CHECK(D::parse("203").divide_integral(D::parse("2"), true).str() == "102");
    CHECK(D::parse("-3").divide_integral(D::parse("2"), false).str() == "-2");
    std::string s;
    CHECK(D::parse("0.000123").fixed(8, s));
    CHECK(s == "0.00012300");
    CHECK(!D::parse("0.123").fixed(2, s));
    CHECK(D::well_formed("-12.5"));
    CHECK(!D::well_formed("1e3"));
    CHECK(!D::well_formed("1."));
    CHECK(!D::well_formed(".5"));
    CHECK(quantforge::micro::crc32("123456789") == 0xCBF43926U);  // the CRC-32/ISO-HDLC check value
}

TEST_CASE("book rebuild: checksum check, resync and checkpoints", "[micro_w2]") {
    const std::string snap = R"({"type":"snapshot","bids":[["100.0","1.00000000"]],"asks":[["101.0","2.00000000"]],"checksum":)";
    // A wrong venue checksum is counted, not an error; the next snapshot marked resubscribe counts a resync.
    const json::Value o = outputs_of(run("micro.book.rebuild",
                                         R"({"depth":10,"price_decimals":1,"qty_decimals":8,"messages":[)" + snap +
                                             R"(1,"t":"2026-01-01T00:00:00Z"},)" + snap +
                                             R"(null,"t":"2026-01-01T00:00:01.5Z","resubscribe":true}],)"
                                             R"("checkpoints":[{"t":"2026-01-01T00:00:01Z","bids":[["100","1"]],"asks":[["101","3"]]}]})"));
    const json::Value& st = *o.find("stats");
    CHECK(st.find("checksum_checked")->text == "1");
    CHECK(st.find("checksum_failed")->text == "1");
    CHECK(st.find("resyncs")->text == "1");
    CHECK(st.find("checkpoint_checked")->text == "1");
    CHECK(st.find("checkpoint_failed")->text == "1");
    // The matching checksum passes.
    const std::string crc = outputs_of(run("micro.book.rebuild", R"({"depth":10,"price_decimals":1,"qty_decimals":8,"messages":[)" +
                                                                    snap + R"(null}]})"))
                                .find("crc32")
                                ->text;
    const json::Value p = outputs_of(
        run("micro.book.rebuild", R"({"depth":10,"price_decimals":1,"qty_decimals":8,"messages":[)" + snap + crc + "}]}"));
    CHECK(p.find("stats")->find("checksum_failed")->text == "0");
    CHECK(p.find("stats")->find("checksum_checked")->text == "1");
}

TEST_CASE("lit engine: MODIFY with a price is E_SCHEMA; pegs never lock", "[micro_w2]") {
    const std::string head = R"({"tick_size":"1","lot_size":"1","fee_schedule":{"maker_rebate":"0","taker_fee":"0"},"events":[)";
    const std::string r = run("exec.sim.lit.run", head + R"({"op":"NEW","id":"A","trader":"T","side":"BUY","type":"LIMIT","price":"10","qty":"5"},)"
                                                         R"({"op":"MODIFY","id":"A","qty":"4","price":"11"}]})");
    CHECK(r.find(R"("code":"E_SCHEMA")") != std::string::npos);
    // Bid 100, ask 102: mid 101 on the grid. Two opposite PEG_MIDs would both price at 101; the second steps a tick away.
    const json::Value o = outputs_of(run(
        "exec.sim.lit.run",
        head + R"({"op":"NEW","id":"B","trader":"T","side":"BUY","type":"LIMIT","price":"100","qty":"5"},)"
               R"({"op":"NEW","id":"S","trader":"T","side":"SELL","type":"LIMIT","price":"102","qty":"5"},)"
               R"({"op":"NEW","id":"PB","trader":"U","side":"BUY","type":"PEG_MID","price":"200","qty":"5"},)"
               R"({"op":"NEW","id":"PS","trader":"U","side":"SELL","type":"PEG_MID","price":"1","qty":"5"}]})"));
    std::map<std::string, std::string> price;
    for (const char* side : {"bids", "asks"})
        for (const json::Value& e : o.find("book")->find(side)->items) price[e.find("id")->text] = e.find("price")->text;
    CHECK(D::parse(price["PB"]) < D::parse(price["PS"]));
    CHECK(o.find("fills")->items.empty());
}

TEST_CASE("lit engine invariants on random streams", "[micro_w2][property]") {
    std::mt19937_64 g(20261118);
    const char* types[] = {"LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY"};
    for (int trial = 0; trial < 300; ++trial) {
        std::string ev;
        const int n = 1 + int(g() % 40);
        int ids = 0;
        for (int k = 0; k < n; ++k) {
            if (!ev.empty()) ev += ",";
            const auto pick = g() % 10;
            if (ids > 0 && pick == 0) {
                ev += R"({"op":"CANCEL","id":"O)" + std::to_string(g() % unsigned(ids + 1)) + R"("})";
            } else if (ids > 0 && pick == 1) {
                ev += R"({"op":"MODIFY","id":"O)" + std::to_string(g() % unsigned(ids)) + R"(","qty":")" +
                      std::to_string(1 + g() % 20) + R"("})";
            } else {
                const std::string type = types[g() % 8];
                const unsigned long qty = 1 + g() % 30;
                ev += R"({"op":"NEW","id":"O)" + std::to_string(ids++) + R"(","trader":"T)" + std::to_string(g() % 3) +
                      R"(","side":")" + (g() % 2 ? "BUY" : "SELL") + R"(","type":")" + type + R"(","qty":")" +
                      std::to_string(qty) + "\"";
                if (type != "MARKET") ev += R"(,"price":")" + std::to_string(95 + g() % 11) + "\"";
                if (type == "ICEBERG") ev += R"(,"display_qty":")" + std::to_string(1 + g() % qty) + "\"";
                ev += "}";
            }
        }
        const std::string inputs =
            R"({"tick_size":"1","lot_size":"1","fee_schedule":{"maker_rebate":"0.0002","taker_fee":"0.001"},"events":[)" + ev + "]}";
        const std::string first = run("exec.sim.lit.run", inputs);
        INFO(inputs << " -> " << first);
        CHECK(first == run("exec.sim.lit.run", inputs));  // replay determinism, byte for byte
        const json::Value o = outputs_of(first);
        CHECK(o.find("label")->text == "simulated venue; not a real exchange");
        // Conservation: submitted = filled + resting + cancelled + rejected, per order.
        for (const json::Member& m : o.find("conservation")->members) {
            const auto f = [&](const char* k) { return D::parse(m.second.find(k)->text); };
            CHECK(f("submitted") == f("filled") + f("resting") + f("cancelled") + f("rejected"));
            CHECK((f("rejected").sign() == 0 || (f("filled").sign() == 0 && f("rejected") == f("submitted"))));
        }
        // Fill total is twice the quantity traded (taker and maker sides).
        D fills, filled;
        for (const json::Value& fl : o.find("fills")->items) fills += D::parse(fl.find("qty")->text);
        for (const json::Member& m : o.find("conservation")->members) filled += D::parse(m.second.find("filled")->text);
        CHECK(filled == fills + fills);
        // Never crossed, hidden and pegged quantity included (HR-27).
        const auto& bids = o.find("book")->find("bids")->items;
        const auto& asks = o.find("book")->find("asks")->items;
        if (!bids.empty() && !asks.empty() && bids[0].find("price")->kind == json::Kind::String &&
            asks[0].find("price")->kind == json::Kind::String)
            CHECK(D::parse(bids[0].find("price")->text) < D::parse(asks[0].find("price")->text));
    }
}

}  // namespace
