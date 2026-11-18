// Stage H multi-asset H-22, H-23, H-24 (port of python/tests/test_stage_h_multiasset.py): every row of the
// auc_h, eqc_h, fxc_h, fxv_h, rtc_h, fut_h and e1_h3 goldens through the CLI layer (exact text), then acceptance
// A3 (properties) and A4 (labels) of specifications/09-microstructure/asset-conventions.md, and the paths the
// goldens do not reach.
#include <catch2/catch_test_macros.hpp>
#include <fstream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/dates.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/multiasset.hpp"

namespace {

namespace json = quantforge::json;
namespace ma = quantforge::micro::ma;
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

json::Value call(const std::string& op, const std::string& inputs) {
    return json::parse(quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                                 R"(","inputs":)" + inputs + "}")
                           .json)
        .value;
}

std::string code_of(const json::Value& doc) {
    return doc.find("status")->text == "ok" ? "ok" : doc.find("error")->find("code")->text;
}

std::string code(const std::string& op, const std::string& inputs) { return code_of(call(op, inputs)); }

json::Value outv(const std::string& op, const std::string& inputs) {
    const json::Value doc = call(op, inputs);
    INFO(op << " " << inputs << " -> " << to_text(doc));
    REQUIRE(doc.find("status")->text == "ok");
    return *doc.find("outputs");
}

std::string out_text(const std::string& op, const std::string& inputs, const char* key) {
    return outv(op, inputs).find(key)->text;
}

const std::set<std::string> labels{std::string(ma::eq_label), std::string(ma::iex_label), std::string(ma::fx_label),
                                   std::string(ma::rates_label)};

#ifdef QF_REPO_DIR
void replay(const char* suite, int expect_cases) {
    std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_h/" + suite + ".json", std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    int n = 0;
    for (const json::Value& c : json::parse(s.str()).value.find("cases")->items) {
        ++n;
        const json::Value& exp = *c.find("expected");
        const json::Value doc = call(c.find("operation")->text, to_text(*c.find("inputs")));
        INFO(c.find("case_id")->text << " -> " << to_text(doc));
        if (exp.find("status")->text == "ok") {
            REQUIRE(doc.find("status")->text == "ok");
            CHECK(to_text(*doc.find("outputs")) == to_text(*exp.find("outputs")));
            CHECK(labels.contains(doc.find("outputs")->find("label")->text));  // A4
        } else {
            CHECK(code_of(doc) == exp.find("error_code")->text);
        }
    }
    CHECK(n == expect_cases);
}

TEST_CASE("multi-asset goldens, every row exact (A1, A4)") {
    replay("auc_h", 12);
    replay("eqc_h", 19);
    replay("fxc_h", 9);
    replay("fxv_h", 11);
    replay("rtc_h", 13);
    replay("fut_h", 8);
    replay("e1_h3", 12);
}
#endif

// ------------------------------------------------------------------ A3 properties

TEST_CASE("A3: equity rounding is never more aggressive and lands on the grid") {
    std::mt19937_64 rng(20261118);
    for (const char* tier : {"PENNY", "HALF_PENNY"})
        for (int i = 0; i < 2000; ++i) {
            const long long n = 1 + (long long)(rng() % 99'999'999);  // price n / 10^5
            const std::string p = std::to_string(n / 100000) + "." + std::string(5 - std::to_string(n % 100000).size(), '0') +
                                  std::to_string(n % 100000);
            const D price = D::parse(p);
            for (const char* side : {"BUY", "SELL"}) {
                const D r = D::parse(out_text("micro.eq.round_price",
                                              std::string(R"({"price":")") + p + R"(","side":")" + side +
                                                  R"(","tick_tier":")" + tier + "\"}",
                                              "price"));
                INFO(p << " " << side << " " << tier << " -> " << r.str());
                CHECK((std::string(side) == "BUY" ? r <= price : r >= price));
                const D tick = D::parse(r < D::integer(1) ? "0.0001" : (std::string(tier) == "HALF_PENNY" ? "0.005" : "0.01"));
                CHECK((r.multiple_of(tick) || r == D::integer(1)));
            }
        }
}

TEST_CASE("A3: 32nds text round-trips on the 1/256 grid") {
    for (int n = 0; n < 256 * 130; n += 7) {
        const D x = D::integer(n) * D::parse("0.00390625");
        const std::string text =
            out_text("micro.rates.format_32nds", R"({"resolution":256,"value":")" + x.str() + "\"}", "text");
        CHECK(D::parse(out_text("micro.rates.parse_32nds", R"({"text":")" + text + "\"}", "value")) == x);
    }
}

TEST_CASE("A3: spot date is a good day in both currencies and USD, at least T+1") {
    using quantforge::Date;
    std::mt19937_64 rng(7);
    const Date start = quantforge::make_date(2026, 1, 1);
    for (int i = 0; i < 300; ++i) {
        std::map<std::string, std::set<std::string>> hol;
        std::string hj = "{";
        for (const char* c : {"EUR", "USD", "JPY", "CAD"}) {
            hj += std::string(hj.size() > 1 ? "," : "") + "\"" + c + "\":[";
            for (int k = 0; k < 15; ++k) {
                const std::string d = quantforge::format_date(start + std::chrono::days{long(rng() % 400)});
                hol[c].insert(d);
                hj += std::string(k ? "," : "") + "\"" + d + "\"";
            }
            hj += "]";
        }
        hj += "}";
        const Date t = start + std::chrono::days{long(rng() % 365)};
        for (const char* pair_c : {"EURUSD", "USDJPY", "EURJPY", "USDCAD"}) {
            const std::string pair = pair_c;
            const std::string s = out_text("micro.fx.spot_date",
                                           R"({"holidays":)" + hj + R"(,"pair":")" + pair + R"(","trade_date":")" +
                                               quantforge::format_date(t) + "\"}",
                                           "spot_date");
            const Date sd = *quantforge::parse_date(s);
            CHECK(sd >= t + std::chrono::days{1});
            const unsigned w = quantforge::weekday_of(sd);
            CHECK((w >= 1 && w <= 5));
            for (const std::string& c : {pair.substr(0, 3), pair.substr(3), std::string("USD")}) CHECK_FALSE(hol[c].contains(s));
        }
    }
}

TEST_CASE("A3: the auction trades the most shares, conserves quantity, never fills worse than a limit") {
    std::mt19937_64 rng(11);
    for (int it = 0; it < 300; ++it) {
        struct O {
            std::string limit;  // "MARKET" or price
            long long qty;
            bool buy;
            std::string id;
        };
        std::vector<O> orders;
        const int n = 1 + int(rng() % 11);
        int nb = 0, ns = 0;
        std::string js = "[";
        for (int k = 0; k < n; ++k) {
            O o;
            o.limit = rng() % 10 == 0 ? "MARKET" : (D::integer(990 + long(rng() % 21)) * D::parse("0.01")).str();
            if (o.limit != "MARKET" && o.limit.find('.') == std::string::npos) o.limit += ".00";
            o.qty = 1 + long(rng() % 499);
            o.buy = rng() % 2 == 0;
            o.id = o.buy ? "b" + std::to_string(++nb) : "a" + std::to_string(++ns);
            orders.push_back(o);
            js += std::string(k ? "," : "") + R"({"limit":")" + o.limit + R"(","qty":)" + std::to_string(o.qty) +
                  R"(,"side":")" + (o.buy ? "BUY" : "SELL") + "\"}";
        }
        js += "]";
        const char* tie = rng() % 2 ? "CBOE" : "IEX";
        const json::Value out = outv("exec.sim.auction.uncross", R"({"orders":)" + js +
                                                                     R"(,"phase":"OPEN","ref_price":"10.00","tick_size":"0.01","tie_break":")" +
                                                                     tie + "\"}");
        long long best = 0;
        bool has_limit = false;
        for (const auto& o : orders) has_limit = has_limit || o.limit != "MARKET";
        for (int k = 990; k <= 1010; ++k) {
            const D p = D::integer(k) * D::parse("0.01");
            long long b = 0, s = 0;
            for (const auto& o : orders) {
                const bool market = o.limit == "MARKET";
                if (o.buy && (market || D::parse(o.limit) >= p)) b += o.qty;
                if (!o.buy && (market || D::parse(o.limit) <= p)) s += o.qty;
            }
            best = std::max(best, std::min(b, s));
        }
        const long long volume = std::stoll(out.find("volume")->text);
        CHECK(volume == (has_limit ? best : 0));
        std::map<std::string, long long> filled_by;
        long long filled = 0, rest = 0, cancelled = 0, total = 0;
        for (const auto& f : out.find("fills")->items) {
            const long long q = std::stoll(f.find("qty")->text);
            filled += q;
            filled_by[f.find("id")->text] += q;
            for (const auto& o : orders)
                if (o.id == f.find("id")->text && o.limit != "MARKET") {
                    const D px = D::parse(f.find("price")->text), lim = D::parse(o.limit);
                    CHECK((o.buy ? px <= lim : px >= lim));
                }
        }
        CHECK(filled == 2 * volume);
        for (const auto& r : out.find("residual")->items) rest += std::stoll(r.find("qty")->text);
        for (const auto& c : out.find("cancelled")->items)
            for (const auto& o : orders)
                if (o.id == c.text) cancelled += o.qty - filled_by[o.id];
        for (const auto& o : orders) total += o.qty;
        CHECK(filled + rest + cancelled == total);
    }
}

// ------------------------------------------------------------------ paths the goldens do not reach

TEST_CASE("fut.run reuses the lit engine; P&L per trader") {
    const std::string ev = R"([{"id":"S1","op":"NEW","price":"110-16","qty":"3","side":"SELL","trader":"M","type":"LIMIT"},)"
                           R"({"id":"B1","op":"NEW","price":"110-16","qty":"3","side":"BUY","trader":"P","type":"LIMIT"},)"
                           R"({"id":"S2","op":"NEW","price":"110-17+","qty":"3","side":"SELL","trader":"P","type":"LIMIT"},)"
                           R"({"id":"B2","op":"NEW","price":"110-17+","qty":"3","side":"BUY","trader":"N","type":"LIMIT"}])";
    const json::Value out = outv("exec.sim.fut.run", R"({"contract":{"symbol":"ZN"},"events":)" + ev + R"(,"fee_per_contract":"1.00"})");
    CHECK(out.find("label")->text == ma::rates_label);
    CHECK(out.find("pnl")->find("P")->text == "134.625");  // HR-102 round trip, same as fut_h-0005
    CHECK(out.find("fills")->items[0].find("price")->text == "110.5");
    CHECK(out.find("fees")->find("P")->text == "6");
    CHECK(out.find("book") != nullptr);
    CHECK(code("exec.sim.fut.run",
               R"({"events":[{"id":"S1","op":"NEW","price":"110-162","qty":"3","side":"SELL","trader":"M","type":"LIMIT"}]})") ==
          "E_DOMAIN");
    CHECK(code("exec.sim.fut.run", R"({"events":[],"fee_per_contract":"-1"})") == "E_DOMAIN");
    CHECK(code("exec.sim.fut.run", R"({"events":[1]})") == "E_SCHEMA");
}

TEST_CASE("more paths: labels, caps, bond, variation, T+1 pair, error codes") {
    CHECK(out_text("micro.eq.round_price", R"({"price":"5","side":"BUY","data_source":"IEX"})", "label") == ma::iex_label);
    CHECK(out_text("micro.eq.fee_check", R"({"price":"20","taker_fee":"0.01","cap_check":false})", "cap") == "0.001");
    CHECK(out_text("micro.eq.fee_check", R"({"price":"0.5","taker_fee":"0.0001","as_of":"2024-01-02"})", "cap") == "0.0015");
    CHECK(code("micro.eq.fee_check", R"({"price":"20","taker_fee":"0.0011"})") == "E_DOMAIN");
    CHECK(out_text("micro.rates.bond_price", R"({"coupon":"0","frequency":1,"periods":1,"yield":"0"})", "price") == "100");
    CHECK(to_text(*outv("exec.sim.fut.variation", R"({"price":"110-00","qty":2,"settlements":["110-01","110-00"],"side":"SELL"})")
                       .find("variation_margin")) == R"(["-62.5","62.5"])");
    CHECK(out_text("micro.fx.spot_date", R"({"pair":"USDCAD","trade_date":"2026-11-25","holidays":{"USD":["2026-11-26"]}})",
                   "spot_date") == "2026-11-27");
    for (const auto& [in, c] : std::vector<std::pair<std::string, std::string>>{
             {R"({"price":"1","side":"BUY","tick_table":[["1","0.01"]]})", "E_INPUT"},
             {R"({"price":"1","side":"BUY","tick_table":[["0","0"]]})", "E_DOMAIN"},
             {R"({"price":"1","side":"BUY","tick_tier":"X"})", "E_SCHEMA"},
             {R"({"price":"1","side":"BUY","data_source":"X"})", "E_SCHEMA"},
             {R"({"price":1,"side":"BUY"})", "E_SCHEMA"},
             {R"({"price":"1","side":"BUY","tick_tier":"HALF_PENNY","as_of":"2024-01-02"})", "E_INPUT"},
             {R"({"price":"1","side":"BUY","tick_tier":"HALF_PENNY","tick_table":[["0","0.01"]]})", "E_INPUT"},
             {R"({"price":"0","side":"BUY"})", "E_DOMAIN"}}) {
        INFO(in);
        CHECK(code("micro.eq.round_price", in) == c);
    }
    CHECK(code("micro.eq.settle_date", R"({"trade_date":"2026-13-01"})") == "E_SCHEMA");
    CHECK(code("micro.eq.settle_date", R"({"trade_date":"2026-11-02","settle_lag":31})") == "E_DOMAIN");
    CHECK(code("micro.eq.settle_date", R"({"trade_date":"2026-11-02","settle_lag":1.0})") == "E_SCHEMA");
    CHECK(out_text("micro.eq.settle_date", R"({"trade_date":"2026-11-06","holidays":["2026-11-09"]})", "settle_date") ==
          "2026-11-10");
    CHECK(code("micro.fx.pip_value", R"({"notional":"1","pair":"USDEUR"})") == "E_INPUT");
    CHECK(code("micro.fx.pip_value", R"({"notional":"1","pair":"EURXXX"})") == "E_INPUT");
    CHECK(code("micro.fx.pip_value", R"({"notional":"-1","pair":"EURUSD"})") == "E_DOMAIN");
    CHECK(out_text("micro.fx.pip_value", R"({"notional":"1000000","pair":"USDJPY"})", "pip_value") == "10000");
    CHECK(code("micro.rates.parse_32nds", R"({"text":"99-32"})") == "E_DOMAIN");
    CHECK(code("micro.rates.parse_32nds", R"({"text":"99-1"})") == "E_INPUT");
    CHECK(code("micro.rates.parse_32nds", R"({"text":"99-164"})") == "E_INPUT");
    CHECK(code("micro.rates.parse_32nds", R"({"text":99})") == "E_SCHEMA");
    CHECK(out_text("micro.rates.parse_32nds", R"({"text":"99-163"})", "value") == "99.51171875");
    CHECK(code("micro.rates.format_32nds", R"({"resolution":48,"value":"1"})") == "E_DOMAIN");
    CHECK(code("micro.rates.format_32nds", R"({"resolution":64,"value":"1.001"})") == "E_DOMAIN");
    CHECK(out_text("micro.rates.format_32nds", R"({"resolution":64,"value":"99.515625"})", "text") == "99-16+");
    CHECK(code("micro.rates.bond_price", R"({"coupon":"0.05","frequency":3,"periods":2,"yield":"0.05"})") == "E_DOMAIN");
    CHECK(code("micro.rates.bond_price", R"({"coupon":"0.05","frequency":2,"periods":1201,"yield":"0.05"})") == "E_DOMAIN");
    CHECK(code("micro.rates.bond_price", R"({"coupon":"0.05","frequency":2,"periods":2,"yield":"-2"})") == "E_DOMAIN");
    // 30-year 4 % semi-annual at 3.7 %: exact rational, rounded half-even to 9 decimals (values from the Python reference).
    CHECK(out_text("micro.rates.bond_price", R"({"coupon":"0.04","frequency":2,"periods":60,"yield":"0.037"})", "price") ==
          "105.40876848");
    CHECK(out_text("micro.rates.bond_price", R"({"coupon":"-0.01","frequency":12,"periods":1200,"yield":"0.05"})", "price") ==
          "-19.183003473");
    CHECK(out_text("micro.rates.bill_price", R"({"discount":"0.05","days":91})", "price") == "98.736111111");
    CHECK(out_text("micro.rates.bill_price", R"({"discount":"5","days":360})", "price") == "-400");
    CHECK(code("micro.rates.bill_price", R"({"discount":"0.05","days":367})") == "E_DOMAIN");
    CHECK(code("micro.rates.tick_value", R"({"face":"0","tick":"1"})") == "E_DOMAIN");
    CHECK(code("exec.sim.fut.to_ticks", R"({"price":"110-16","contract":{"symbol":"XX"}})") == "E_SCHEMA");
    CHECK(code("exec.sim.fut.to_ticks", R"({"price":"110-16","contract":{"face":"1","tick":"0"}})") == "E_DOMAIN");
    CHECK(code("exec.sim.fut.to_ticks", R"({"price":"-1"})") == "E_DOMAIN");
    CHECK(std::stoll(outv("exec.sim.fut.to_ticks", R"({"price":"110.5","contract":{"symbol":"ZB"}})").find("ticks")->text) == 3536);
    CHECK(code("exec.sim.fut.to_text", R"({"ticks":1,"contract":{"face":"1","tick":"0.01"}})") == "E_DOMAIN");
    CHECK(code("exec.sim.fut.to_text", R"({"ticks":-1})") == "E_DOMAIN");
    CHECK(out_text("exec.sim.fut.to_text", R"({"ticks":7073})", "text") == "110-16+");
    CHECK(code("exec.sim.fut.pnl", R"({"qty":0,"buy_price":"110-00","sell_price":"110-01"})") == "E_DOMAIN");
    CHECK(code("exec.sim.fut.variation", R"({"side":"BUY","qty":1,"price":"110-00","settlements":[]})") == "E_INPUT");
    CHECK(code("exec.sim.fx.stream", R"({"half_spread_pips":"1","mid_path":[],"pair":"EURUSD"})") == "E_INPUT");
    CHECK(code("exec.sim.fx.stream", R"({"half_spread_pips":"1","mid_path":[{"mid":"0","time":0}],"pair":"EURUSD"})") ==
          "E_DOMAIN");
    CHECK(to_text(*outv("exec.sim.fx.stream", R"({"half_spread_pips":"1.5","mid_path":[{"mid":"150.1234","time":3}],"pair":"USDJPY"})")
                       .find("quotes")) == R"([{"ask":"150.139","bid":"150.108","mid":"150.1234","time":3}])");
    const std::string req = R"({"mid_after":"1.0853","p_random_reject":"0.05","pair":"EURUSD","qty":"1000000",)"
                            R"("quote":{"ask":"1.0852","bid":"1.0850","quote_mid":"1.0851"},"side":"SELL","symmetric":false,)"
                            R"("threshold_pips":"1","u":"0.01"})";
    CHECK(out_text("exec.sim.fx.request", req, "outcome") == "LL_RANDOM");
    CHECK(code("exec.sim.fx.request", R"({"mid_after":"1","p_random_reject":"0","pair":"EURUSD","qty":"1",)"
                                      R"("quote":{"ask":"1","bid":"2","quote_mid":"1"},"side":"BUY","threshold_pips":"1","u":"0"})") ==
          "E_INPUT");
    CHECK(code("exec.sim.auction.uncross", R"({"orders":[{"id":"x","side":"BUY","limit":"10.00","qty":1},)"
                                           R"({"id":"x","side":"SELL","limit":"10.00","qty":1}],"phase":"OPEN","ref_price":"10","tick_size":"0.01"})") ==
          "E_INPUT");
    CHECK(code("exec.sim.auction.uncross", R"({"orders":[{"side":"BUY","limit":"10.005","qty":1}],"phase":"OPEN","ref_price":"10","tick_size":"0.01"})") ==
          "E_DOMAIN");
    CHECK(code("exec.sim.auction.uncross", R"({"orders":[{"side":"BUY","limit":"0.01","qty":1},{"side":"SELL","limit":"100000","qty":1}],)"
                                           R"("phase":"OPEN","ref_price":"10","tick_size":"0.01"})") == "E_LIMIT");
    const json::Value close = outv("exec.sim.auction.uncross",
                                   R"({"orders":[{"side":"BUY","limit":"10.00","qty":5,"on_close":true},{"side":"SELL","limit":"10.00","qty":2}],)"
                                   R"("phase":"CLOSE","ref_price":"10","tick_size":"0.01"})");
    CHECK(to_text(*close.find("cancelled")) == R"(["b1"])");
    CHECK(close.find("price")->text == "10.00");
    const json::Value none = outv("exec.sim.auction.uncross",
                                  R"({"orders":[{"side":"BUY","limit":"9.00","qty":5},{"side":"SELL","limit":"10.00","qty":2}],)"
                                  R"("phase":"OPEN","ref_price":"10","tick_size":"0.01"})");
    CHECK(none.find("price")->kind == json::Kind::Null);
    CHECK(to_text(*none.find("residual")) == R"([{"id":"b1","limit":"9.00","qty":5,"side":"B"},{"id":"a1","limit":"10.00","qty":2,"side":"S"}])");
}

}  // namespace
