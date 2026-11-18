// H-21 paper trading in C++: acceptance tests A1, A5, A6, A8 and the byte-exact ledger rules (paper-trading.md,
// cli-contract.md "Stage H paper trading operations"). The goldens pt_h and e1_hpt replay in test_golden_replay.cpp.
#include <catch2/catch_test_macros.hpp>
#include <string>

#include "dispatch.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/paper.hpp"
#include "quantforge/core/snapshot.hpp"

using quantforge::cli::run_case;
namespace paper = quantforge::paper;
namespace json = quantforge::json;

namespace {
bool has(const std::string& s, const std::string& part) { return s.find(part) != std::string::npos; }
std::string wrap(const std::string& op, const std::string& inputs) {
    return R"({"schema_version":"1.0","case_id":"c1","operation":")" + op + R"(","inputs":)" + inputs + "}";
}
const std::string limits =
    R"({"max_order_qty":"10","max_notional":"1000","max_abs_position":"5","price_band":"0.05","max_orders_per_day":3})";
const std::string order_text =
    R"({"side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101")";

std::string session(const std::string& venue, const std::string& extra) {
    return R"({"cash":"10000","limits":)" + limits +
           R"(,"lit":{"tick_size":"0.5","lot_size":"1","fee_schedule":{"maker_rebate":"0","taker_fee":"0.001"}})" + extra +
           R"(,"script":[{"op":"SUBMIT","ts":"2026-11-18T00:00:01Z","order":{"order_id":"O1","symbol":"BTC-USD","side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101","venue":")" +
           venue +
           R"("},"snapshot":{"bids":[["99.5","4"]],"asks":[["100.5","2"],["101","5"]]}},{"op":"CLOSE","ts":"2026-11-19T00:00:00Z","prev_marks":{},"marks":{"BTC-USD":"102"}}]})";
}
}  // namespace

TEST_CASE("A5: a live order is E_UNSUPPORTED_OPERATION, in the check and in a session") {
    for (const char* mode : {R"("live")", R"("LIVE")", "1", "false"}) {
        const auto r = run_case(wrap("paper.pretrade.check", R"({"order":)" + order_text + R"(,"mode":)" + mode +
                                                                 R"(},"ref_price":"100","cash":"10000","limits":)" + limits + "}"));
        CHECK(has(r.json, "E_UNSUPPORTED_OPERATION"));
    }
    std::string s = session("LIT", "");
    s.replace(s.find(R"("venue":"LIT")"), 13, R"("venue":"LIT","mode":"live")");
    CHECK(has(run_case(wrap("paper.session.run", s)).json, "E_UNSUPPORTED_OPERATION"));
    const auto ok = run_case(wrap("paper.pretrade.check", R"({"order":)" + order_text + R"(,"mode":"simulated"},"ref_price":"100","cash":"10000","limits":)" + limits + "}"));
    CHECK(has(ok.json, R"("accepted":true)"));
}

TEST_CASE("SHA-256 test vectors (FIPS 180-4) and the pt_h-0020 check value") {
    CHECK(quantforge::sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    CHECK(quantforge::sha256_hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const auto r = run_case(wrap("paper.ledger.append", R"({"seq":0,"ts":"2026-11-18T00:00:01Z","kind":"ORDER","body":{"order_id":"O1","symbol":"BTC-USD","side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101"}})"));
    CHECK(has(r.json, "72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81"));
}

TEST_CASE("canonical bytes are Python json.dumps with ensure_ascii") {
    CHECK(paper::ascii_string("a\"\\\b\f\n\r\t/\x01\x7f") == R"("a\"\\\b\f\n\r\t/\u0001\u007f")");
    CHECK(paper::ascii_string("\xc3\xa9\xf0\x9f\x98\x80") == "\"\\u00e9\\ud83d\\ude00\"");
    const json::Value v = json::parse(R"({"seq":0,"b":{"z":"1","a":["x",null]},"hash":"h"})").value;
    CHECK(paper::canonical(v) == R"({"b":{"a":["x",null],"z":"1"},"seq":0})");
    CHECK_THROWS(paper::canonical(json::parse(R"({"seq":0,"b":{"n":1}})").value));
    CHECK_THROWS(paper::canonical(json::parse(R"({"seq":0,"b":true})").value));
    CHECK_THROWS(paper::canonical(json::parse(R"({"seq":1.0})").value));
}

TEST_CASE("A1, A6, A8: a session ledger verifies, is deterministic, and breaks at the edited record") {
    const auto a = run_case(wrap("paper.session.run", session("LIT", "")));
    const auto b = run_case(wrap("paper.session.run", session("LIT", "")));
    REQUIRE(a.ok);
    CHECK(a.json == b.json);
    const json::Value out = *json::parse(a.json).value.find("outputs");
    std::string text;
    for (const auto& rec : out.find("records")->items) {
        CHECK(rec.find("label")->text == paper::label);
        std::string line = paper::canonical(rec);
        line.insert(line.size() - 1, R"(,"hash":")" + rec.find("hash")->text + "\"");
        text += line + "\n";
    }
    paper::Verify v = paper::verify(text);
    CHECK(v.ok);
    CHECK(v.records == 5);  // ORDER, FILL, FILL, TCA, EOD
    CHECK(v.head == out.find("head")->text);
    for (std::size_t i = 0; i < text.size(); i += 37) {
        if (text[i] == '\n') continue;
        std::string bad = text;
        bad[i] = bad[i] == 'A' ? 'B' : 'A';
        const paper::Verify w = paper::verify(bad);
        CHECK_FALSE(w.ok);
    }
    const auto cut = text.substr(0, text.rfind('\n', text.size() - 2) + 1);
    CHECK(paper::verify(cut).ok);
    CHECK(paper::verify("").ok);
    CHECK(paper::verify("").head == paper::genesis);
    CHECK(paper::verify("{}\n").reason == "PARSE");
}

TEST_CASE("DARK and SOR sessions replay through this build's venues and keep the label") {
    const std::string dark =
        R"(,"dark":{"firm_delay":0,"lot_size":"1","p_firm":"1","penalty_events":2,"seed":20261118,"tick_size":"0.01"})";
    std::string d = session("DARK", dark);
    d.replace(d.find(R"("snapshot")"), 10, R"("contra":[{"id":"C1","kind":"FIRM","op":"NEW","qty":"2","side":"SELL"}],"snapshot")");
    const auto rd = run_case(wrap("paper.session.run", d));
    CHECK(has(rd.json, R"("venue":"DARK")"));
    CHECK(has(rd.json, R"("label":"crypto venue; simulated")"));
    std::string s = session("SOR", "");
    s.replace(s.find(R"("snapshot")"), 10,
              R"("router":{"f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"0.1","lit_samples":[["10"],["12"],["15"]],"theta":"0","venues":[{"Q":"0","as":"0","kind":"LIT","r":"0.2"}]},"snapshot")");
    const auto rs = run_case(wrap("paper.session.run", s));
    CHECK(rs.ok);
    CHECK(has(rs.json, R"("kind":"CANCEL")"));  // the LIT child rests at the best bid and never crosses
    CHECK(has(run_case(wrap("paper.session.run", session("SOR", ""))).json, "E_SCHEMA"));  // no router
    CHECK(has(run_case(wrap("paper.session.run", session("NYSE", ""))).json, "E_INPUT"));
}

TEST_CASE("HR-77 exact decimals: the stated division, the range, and duplicate keys (HR-78)") {
    // avg cost (1 x 100 + 2 x 101) / 3, half-even to 18 decimals (HR-77)
    const auto r = run_case(wrap("paper.book.apply_fill", R"({"fills":[{"side":"BUY","quantity":"1","price":"100"},{"side":"BUY","quantity":"2","price":"101"}]})"));
    CHECK(has(r.json, R"("avg_cost":"100.666666666666666667")"));
    CHECK(has(r.json, R"("cash_delta":"-302")"));
    CHECK(has(run_case(wrap("paper.book.apply_fill", R"({"fills":[{"side":"BUY","quantity":"1","price":"1e2"}]})")).json, R"("avg_cost":"100")"));
    CHECK(has(run_case(wrap("paper.book.apply_fill", R"({"fills":[{"side":"BUY","quantity":"1","price":"abc"}]})")).json, "E_PARSE"));
    CHECK(has(run_case(wrap("paper.book.apply_fill", R"({"fills":[{"side":"BUY","quantity":"1","price":"nan"}]})")).json, "E_SCHEMA"));
    CHECK(has(run_case(wrap("paper.book.apply_fill", R"({"fills":[{"side":"BUY","quantity":"1","price":"1.0000000000000000001"}]})")).json, "E_LIMIT"));
    CHECK(paper::verify(R"({"a":{"b":"1","b":"1"},"hash":"x"})").reason == "PARSE");
}
