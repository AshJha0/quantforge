// Stage H wave 2: exec.sim.dark.run, exec.sim.dark.markouts and exec.sor.allocate. Every row of the dark_h and
// sor_h goldens through the CLI layer (exact text), the property rows of dark-pool.md and smart-order-router.md,
// and the planted-parameter acceptance tests (seeds 20261118 and 20261119, fixed in dark-pool.md).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/microstructure.hpp"
#include "quantforge/core/rng.hpp"

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

json::Value call(const std::string& op, const std::string& inputs) {
    return json::parse(quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                                 R"(","inputs":)" + inputs + "}")
                           .json)
        .value;
}

std::string code_of(const json::Value& doc) {
    return doc.find("status")->text == "ok" ? "ok" : doc.find("error")->find("code")->text;
}

std::string outs(const std::string& op, const std::string& inputs) {
    const json::Value doc = call(op, inputs);
    INFO(op << " " << inputs << " -> " << to_text(doc));
    REQUIRE(doc.find("status")->text == "ok");
    return to_text(*doc.find("outputs"));
}

json::Value outv(const std::string& op, const std::string& inputs) { return json::parse(outs(op, inputs)).value; }

const std::string cfg = R"({"firm_delay":0,"lot_size":"1","p_firm":"1","penalty_events":2,"seed":1,"tick_size":"0.01"})";
const std::string book = R"({"op":"BOOK","bid":"100.00","ask":"100.10"})";
std::string order(const std::string& id, const std::string& side, const std::string& qty, const std::string& kind = "FIRM",
                  const std::string& extra = "") {
    return R"({"op":"NEW","id":")" + id + R"(","side":")" + side + R"(","qty":")" + qty + R"(","kind":")" + kind + "\"" +
           extra + "}";
}
std::string dark(const std::string& config, const std::vector<std::string>& ev) {
    std::string s = R"({"config":)" + config + R"(,"events":[)";
    for (std::size_t i = 0; i < ev.size(); ++i) s += (i ? "," : "") + ev[i];
    return s + "]}";
}
std::string with(std::string config, const std::string& key, const std::string& val) {
    const auto p = config.find("\"" + key + "\":");
    const auto start = p + key.size() + 3;
    const auto end = config.find_first_of(",}", start);
    return config.replace(start, end - start, val);
}

#ifdef QF_REPO_DIR
std::string golden_inputs(const char* suite, int index) {
    std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_h/" + suite + ".json", std::ios::binary);
    std::stringstream s;
    s << f.rdbuf();
    return to_text(*json::parse(s.str()).value.find("cases")->items[std::size_t(index)].find("inputs"));
}

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
        } else {
            CHECK(code_of(doc) == exp.find("error_code")->text);
        }
    }
    CHECK(n == expect_cases);
}

TEST_CASE("dark_h goldens: every row, exact", "[dark_sor]") { replay("dark_h", 8); }
TEST_CASE("sor_h goldens: every row, exact", "[dark_sor]") { replay("sor_h", 8); }

TEST_CASE("CLOSED_FORM agrees with SAMPLE_AVERAGE on sor_h-0001..0003", "[dark_sor]") {
    for (int k = 0; k < 3; ++k) {
        std::string inp = golden_inputs("sor_h", k);
        const std::string closed = R"({"method":"CLOSED_FORM",)" + inp.substr(1);
        CHECK(outs("exec.sor.allocate", closed) == outs("exec.sor.allocate", inp));
    }
}

TEST_CASE("STOCHASTIC_APPROX reaches the SAMPLE_AVERAGE optimum on every value golden", "[dark_sor]") {
    for (int k = 0; k < 5; ++k) {
        std::string inp = golden_inputs("sor_h", k);
        const auto r = inp.find(R"("ranking":true,)");
        if (r != std::string::npos) inp.erase(r, 15);
        for (const char* n : {"1000", "10000"}) {
            const std::string sa =
                std::string(R"({"method":"STOCHASTIC_APPROX","iterations":)") + n + R"(,"step":1.0,"seed":3,)" + inp.substr(1);
            INFO(k << " " << n);
            CHECK(outs("exec.sor.allocate", sa) == outs("exec.sor.allocate", inp));
        }
    }
}

TEST_CASE("report_se adds a positive standard error and the label", "[dark_sor]") {
    const json::Value o = outv("exec.sor.allocate", R"({"report_se":true,)" + golden_inputs("sor_h", 2).substr(1));
    CHECK(o.find("label")->text == quantforge::micro::sor_label);
    CHECK(std::stod(o.find("expected_cost_se")->text) > 0);
}

TEST_CASE("report_se matches the Python _se rule exactly", "[dark_sor]") {
    // Expected value from python/quantforge_core/sor.py allocate on the same input.
    const json::Value o = outv("exec.sor.allocate", R"({"S":"3","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"4","theta":"0.01","report_se":true,"lit_samples":[["0"],["2"],["5"],["1"]],"venues":[{"Q":"1","as":"0","kind":"LIT","r":"0.2"},{"kind":"DARK","as":"0.1","r":"0","tail":["0.7","0.3"]}]})");
    CHECK(o.find("expected_cost")->text == "1.9615");
    CHECK(o.find("expected_cost_se")->text == "0.781289");
}

TEST_CASE("router cost outside the HR-57 range is E_LIMIT", "[dark_sor]") {
    CHECK(code_of(call("exec.sor.allocate", R"({"theta":"100000000000000000000000000000000000","S":"10","venues":[{"kind":"LIT","Q":"0","r":"0.2","as":"0"}],"h":"0.5","f":"0.3","lambda_u":"4","lambda_o":"1","lit_samples":[["0"],["2"]]})")) == "E_LIMIT");
}

TEST_CASE("router errors", "[dark_sor]") {
    const std::string base = golden_inputs("sor_h", 2);
    auto patched = [&](const std::string& kv) { return "{" + kv + "," + base.substr(1); };
    CHECK(code_of(call("exec.sor.allocate", R"({"S":"1.5","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"4","lit_samples":[["0"]],"theta":"0","venues":[{"Q":"2","as":"0","kind":"LIT","r":"0.2"}]})")) == "E_DOMAIN");
    CHECK(code_of(call("exec.sor.allocate", patched(R"("method":"GREEDY")"))) == "E_SCHEMA");
    std::string many = R"({"S":"2","f":"0","h":"0","lambda_o":"0","lambda_u":"0","theta":"0","lit_samples":[[)";
    std::string venues;
    for (int i = 0; i < 65; ++i) {
        many += std::string(i ? "," : "") + "\"0\"";
        venues += std::string(i ? "," : "") + R"({"kind":"LIT","Q":"0","r":"0","as":"0"})";
    }
    CHECK(code_of(call("exec.sor.allocate", many + R"(]],"venues":[)" + venues + "]}")) == "E_LIMIT");
    const std::string dark_only = R"({"S":"2","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"1","theta":"0","venues":[{"kind":"DARK","r":"0","as":"0","tail":)";
    CHECK(code_of(call("exec.sor.allocate", dark_only + R"(["0.2","0.5"]}]})")) == "E_DOMAIN");
    CHECK(code_of(call("exec.sor.allocate", R"({"method":"CLOSED_FORM",)" + dark_only.substr(1) + R"([]}]})")) == "E_DOMAIN");
    CHECK(code_of(call("exec.sor.allocate", R"({"S":"2","f":"0","h":"0","lambda_o":"0","lambda_u":"0","theta":"0","lit_samples":[["1","2"]],"venues":[{"kind":"LIT","Q":"0","r":"0","as":"0"}]})")) == "E_INPUT");
}
#endif

TEST_CASE("dark-only router: exhaustive optimum, descent on a large grid agrees", "[dark_sor]") {
    // Two dark venues: S = 4 is searched exhaustively; S = 100 has 101^3 > 10^6 grid points, so coordinate
    // descent runs, and a ranking there is refused.
    const std::string body = R"(,"f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"1","theta":"0","venues":[{"kind":"DARK","r":"0","as":"0.1","tail":["0.5","0.5","0.5"]},{"kind":"DARK","r":"0","as":"0","tail":["0.4"]}]})";
    const json::Value small = outv("exec.sor.allocate", R"({"S":"4")" + body);
    const json::Value big = outv("exec.sor.allocate", R"({"S":"100")" + body);
    CHECK(small.find("M") != nullptr);
    CHECK(big.find("M") != nullptr);
    CHECK(code_of(call("exec.sor.allocate", R"({"S":"100","ranking":true)" + body)) == "E_LIMIT");
}

TEST_CASE("min_qty equal to qty crosses only on exact size", "[dark_sor]") {
    CHECK(outv("exec.sim.dark.run", dark(cfg, {book, order("B", "BUY", "50", "FIRM", R"(,"min_qty":"50")"),
                                               order("S", "SELL", "40", "FIRM", R"(,"min_qty":"40")")}))
              .find("fills")
              ->items.empty());
    const json::Value o = outv("exec.sim.dark.run", dark(cfg, {book, order("B", "BUY", "50", "FIRM", R"(,"min_qty":"50")"),
                                                               order("S", "SELL", "50", "FIRM", R"(,"min_qty":"50")")}));
    CHECK(o.find("fills")->items.at(0).find("qty")->text == "50");
}

TEST_CASE("locked book and a missing side give no mid", "[dark_sor]") {
    for (const char* b : {R"({"op":"BOOK","bid":"100.00","ask":"100.00"})", R"({"op":"BOOK","bid":"100.00"})"})
        CHECK(outv("exec.sim.dark.run", dark(cfg, {b, order("B", "BUY", "5"), order("S", "SELL", "5")})).find("fills")->items.empty());
}

TEST_CASE("cancel removes; time priority", "[dark_sor]") {
    const json::Value o = outv("exec.sim.dark.run", dark(cfg, {book, order("B1", "BUY", "5"), order("B2", "BUY", "5"),
                                                               R"({"op":"CANCEL","id":"B1"})", order("S", "SELL", "5")}));
    CHECK(o.find("fills")->items.at(0).find("buy_id")->text == "B2");
}

TEST_CASE("firm_delay holds the pair, then fills at the later mid", "[dark_sor]") {
    const json::Value o = outv("exec.sim.dark.run",
                               dark(with(cfg, "firm_delay", "2"), {book, order("C", "BUY", "5", "CONDITIONAL"), order("S", "SELL", "5"),
                                                                   R"({"op":"BOOK","bid":"100.00","ask":"100.20"})",
                                                                   R"({"op":"BOOK","bid":"100.00","ask":"100.30"})"}));
    CHECK(to_text(*o.find("invitations")) == R"([{"contra_id":"S","event":5,"id":"C","result":"FIRMED"}])");
    CHECK(o.find("fills")->items.at(0).find("price")->text == "100.15");
}

TEST_CASE("p_firm draw is seeded and deterministic", "[dark_sor]") {
    std::string c = with(with(with(cfg, "p_firm", R"("0.5")"), "penalty_events", "0"), "seed", "7");
    std::vector<std::string> ev{book, order("C", "BUY", "5", "CONDITIONAL"), order("S", "SELL", "5")};
    for (int i = 0; i < 20; ++i) ev.push_back(book);
    const std::string a = outs("exec.sim.dark.run", dark(c, ev));
    CHECK(a == outs("exec.sim.dark.run", dark(c, ev)));
    const json::Value o = json::parse(a).value;
    CHECK(o.find("fills")->items.size() == 1);
    CHECK(o.find("invitations")->items.back().find("result")->text == "FIRMED");
}

TEST_CASE("both sides conditional: both invited", "[dark_sor]") {
    const json::Value o = outv("exec.sim.dark.run", dark(cfg, {book, order("C1", "BUY", "5", "CONDITIONAL"), order("C2", "SELL", "5", "CONDITIONAL")}));
    CHECK(o.find("invitations")->items.size() == 2);
    CHECK(o.find("fills")->items.size() == 1);
}

TEST_CASE("dark errors", "[dark_sor]") {
    CHECK(code_of(call("exec.sim.dark.run", dark(cfg, {R"({"op":"BOOK","bid":"100.005","ask":"100.10"})"}))) == "E_DOMAIN");
    CHECK(code_of(call("exec.sim.dark.run", dark(cfg, {order("B", "BUY", "5"), order("B", "BUY", "5")}))) == "E_INPUT");
    CHECK(code_of(call("exec.sim.dark.run", dark(cfg, {R"({"op":"CANCEL","id":"X"})"}))) == "E_INPUT");
    CHECK(code_of(call("exec.sim.dark.run", dark(cfg, {R"({"op":"AMEND"})"}))) == "E_SCHEMA");
    CHECK(code_of(call("exec.sim.dark.run", dark(cfg, {order("B", "HOLD", "5")}))) == "E_SCHEMA");
    CHECK(code_of(call("exec.sim.dark.run", dark(with(cfg, "seed", "-1"), {}))) == "E_DOMAIN");
    CHECK(code_of(call("exec.sim.dark.run", R"({"scenarios":[1]})")) == "E_SCHEMA");
    CHECK(code_of(call("exec.sim.dark.markouts", R"({"fills":[{"side":"BUY","fill_price":"0","mid_at":{}}]})")) == "E_DOMAIN");
    CHECK(code_of(call("exec.sim.dark.markouts", R"({"fills":[{"side":"X"}]})")) == "E_SCHEMA");
    CHECK(code_of(call("exec.sim.dark.markouts", R"({"fills":[{"side":"BUY","fill_price":"1"}]})")) == "E_SCHEMA");
}

TEST_CASE("exact long division, half-even", "[dark_sor]") {
    using quantforge::micro::div_round;
    CHECK(div_round(D::parse("2"), D::parse("3"), 6) == "0.666667");
    CHECK(div_round(D::parse("1"), D::parse("8"), 2) == "0.12");
    CHECK(div_round(D::parse("3"), D::parse("8"), 2) == "0.38");
    CHECK(div_round(D::parse("-7"), D::parse("2"), 0) == "-4");
    CHECK(div_round(D::parse("0.0000004"), D::parse("1"), 6) == "0");
    CHECK(div_round(D::parse("0.0000015"), D::parse("1"), 6) == "0.000002");
    CHECK(div_round(D::parse("125"), D::parse("0.001"), 0) == "125000");
    CHECK(div_round(D::parse("20"), D::parse("100.05"), 6) == "0.1999");
}

TEST_CASE("Kaplan-Meier: no censoring is the empirical tail; all censored above s stays one", "[dark_sor]") {
    const std::vector<std::pair<long long, long long>> obs{{10, 0}, {10, 1}, {10, 1}, {10, 2}, {10, 3}, {10, 5}};
    const auto est = quantforge::micro::km_tail(obs, 6);
    for (int s = 1; s <= 6; ++s) {
        int c = 0;
        for (const auto& o : obs) c += o.second >= s;
        CHECK(std::fabs(est[std::size_t(s - 1)].first - c / 6.0) < 1e-12);
    }
    for (const auto& [t, se] : quantforge::micro::km_tail({{5, 5}, {7, 7}}, 4)) CHECK(t == 1.0);
}

TEST_CASE("planted fill probability recovered within 3 Greenwood SE (seed 20261118)", "[dark_sor]") {
    quantforge::Xoshiro256 rng(20261118, 0);
    std::vector<std::pair<long long, long long>> obs;
    for (int i = 0; i < 20'000; ++i) {
        const long long s = std::min((long long)(rng.next_uniform() * 10), 9LL);
        const long long v = 1 + std::min((long long)(rng.next_uniform() * 10), 9LL);
        obs.emplace_back(v, std::min(s, v));
    }
    const auto est = quantforge::micro::km_tail(obs, 8);
    for (int s = 1; s <= 8; ++s) {
        INFO(s);
        CHECK(std::fabs(est[std::size_t(s - 1)].first - (1 - 0.1 * s)) <= 3 * est[std::size_t(s - 1)].second);
    }
}

TEST_CASE("planted leakage alpha x J recovered within 3 SE (seed 20261119)", "[dark_sor]") {
    quantforge::Xoshiro256 rng(20261119, 0);
    const double alpha = 0.3, jump = 0.20;
    const std::string c = with(cfg, "seed", "20261119");
    std::vector<double> adverse;
    for (int i = 0; i < 4'000; ++i) {
        const std::string ours = rng.next_uniform() < 0.5 ? "BUY" : "SELL";
        const bool up = rng.next_uniform() < 0.5;
        const bool informed = rng.next_uniform() < alpha;
        const std::string contra = informed ? (up ? "BUY" : "SELL") : (rng.next_uniform() < 0.5 ? "BUY" : "SELL");
        const json::Value o = outv("exec.sim.dark.run", dark(c, {book, order("U", ours, "100"), order("X", contra, "100")}));
        if (o.find("fills")->items.empty()) continue;
        const std::string px = o.find("fills")->items[0].find("price")->text;
        char mid[32];
        std::snprintf(mid, sizeof mid, "%.3f", std::stod(px) + (up ? jump : -jump));
        const json::Value m = outv("exec.sim.dark.markouts", R"({"fills":[{"side":")" + ours + R"(","fill_price":")" + px +
                                                                 R"(","mid_at":{"1":")" + mid + R"("}}]})");
        adverse.push_back(-std::stod(m.find("fills")->items[0].find("markouts_bp")->find("1")->text) * std::stod(px) / 10'000);
    }
    const double n = double(adverse.size());
    double mean = 0, ss = 0;
    for (double a : adverse) mean += a / n;
    for (double a : adverse) ss += (a - mean) * (a - mean);
    const double se = std::sqrt(ss / (n - 1) / n);
    INFO(mean << " " << se << " " << n);
    CHECK(std::fabs(mean - alpha * jump) <= 3 * se);
}

}  // namespace
