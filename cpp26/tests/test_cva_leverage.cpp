// Stage K wave 2b (K-8g CVA capital, K-8i leverage ratio and large exposures): the nine golden suites replayed through
// the CLI layer at their own tolerances, hand cases from 06-risk/cva-capital.md and leverage-large-exposures.md, and
// the KR-67 error order. Golden counts are read from the files, never written here.
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/cva.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/leverage.hpp"

namespace {

namespace json = quantforge::json;
namespace cv = quantforge::cva;
namespace lv = quantforge::leverage;

std::string read_text(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    std::stringstream s;
    s << f.rdbuf();
    return s.str();
}

std::string as_text(const json::Value& v) {
    json::Writer w;
    w.value(v);
    return w.str();
}

// The runner's rule: |got - want| <= a + r max(|got|, |want|); strings, booleans and nulls exact.
bool same(const json::Value& got, const json::Value& want, double a, double r) {
    if (got.kind != want.kind) return false;
    switch (want.kind) {
        case json::Kind::Number:
            return std::fabs(got.number - want.number) <= a + r * std::max(std::fabs(got.number), std::fabs(want.number));
        case json::Kind::Array:
            if (got.items.size() != want.items.size()) return false;
            for (std::size_t i = 0; i < want.items.size(); ++i)
                if (!same(got.items[i], want.items[i], a, r)) return false;
            return true;
        case json::Kind::Object:
            if (got.members.size() != want.members.size()) return false;
            for (const auto& [k, v] : want.members)
                if (!got.find(k) || !same(*got.find(k), v, a, r)) return false;
            return true;
        case json::Kind::String: return got.text == want.text;
        case json::Kind::Bool: return got.boolean == want.boolean;
        default: return true;
    }
}

json::Parsed run(const std::string& op, const std::string& inputs) {
    const auto res = quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"t","operation":")" + op +
                                               R"(","inputs":)" + inputs + "}");
    return json::parse(res.json);
}

std::string code(const std::string& op, const std::string& inputs) {
    const json::Parsed p = run(op, inputs);
    const json::Value* e = p.value.find("error");
    return e ? e->find("code")->text : std::string("ok");
}

double out_real(const json::Parsed& p, const char* key) { return p.value.find("outputs")->find(key)->number; }

// Every case of one suite; returns the number replayed.
std::size_t replay(const std::string& suite) {
    const json::Parsed doc = json::parse(read_text(std::string(QF_REPO_DIR) + "/datasets/golden/stage_k/" + suite + ".json"));
    const json::Value* cases = doc.value.find("cases");
    REQUIRE(cases);
    for (const json::Value& c : cases->items) {
        const std::string id = c.find("case_id")->text;
        INFO(id);
        const json::Parsed got = run(c.find("operation")->text, as_text(*c.find("inputs")));
        const json::Value& exp = *c.find("expected");
        if (exp.find("status")->text == "error") {
            const json::Value* err = got.value.find("error");
            REQUIRE(err);
            CHECK(err->find("code")->text == exp.find("error_code")->text);
            continue;
        }
        const json::Value* outs = got.value.find("outputs");
        REQUIRE(outs);
        double a = 1e-15, r = 1e-12;  // simple_analytic, KR-67
        if (const json::Value* lim = c.find("tolerance_limit")) {
            a = lim->find("absolute")->number;
            r = lim->find("relative")->number;
        }
        CHECK(same(*outs, *exp.find("outputs"), a, r));
    }
    return cases->items.size();
}

}  // namespace

TEST_CASE("wave 2b goldens: all nine suites through the CLI layer", "[cva_leverage]") {
    for (const char* suite : {"cva_k", "df_k", "sacva_k", "cva_ke", "sacva_ke", "lev_k", "lev_ke", "lex_k", "lex_ke"})
        CHECK(replay(suite) > 0);
}

TEST_CASE("BA-CVA discount factor and a single counterparty by hand (MAR50.15, KR-64)", "[cva_leverage]") {
    CHECK(cv::discount_factor(5.0, true) == 1.0);
    CHECK(std::fabs(cv::discount_factor(1.0) - 0.9754115099857198) <= 1e-16);
    CHECK(std::fabs(cv::discount_factor(5.0) - 0.8847968677143805) <= 1e-16);
    CHECK_THROWS_AS(cv::discount_factor(0.0), quantforge::Error);
    // SCVA = RW M EAD DF / alpha; with one counterparty K_reduced = sqrt((0.5 s)^2 + 0.75 s^2) = s.
    const cv::BaResult r = cv::ba_cva({{"C1", "financials", "IG", {{1e6, 5.0, false}}}}, "REDUCED", {}, {});
    const double s = 0.05 * 5e6 * 0.8847968677143805 / 1.4;
    CHECK(std::fabs(r.counterparties[0].scva - s) <= 1e-12 * s);
    CHECK(std::fabs(r.k_reduced - s) <= 1e-12 * s);
    CHECK(std::fabs(r.capital - 0.65 * s) <= 1e-12 * s);
    CHECK(std::fabs(r.rwa - 12.5 * 0.65 * s) <= 1e-12 * s);
    CHECK_FALSE(r.k_full);
    CHECK_FALSE(r.counterparties[0].snh);
}

TEST_CASE("BA-CVA full: a direct hedge of the whole exposure leaves only the beta share", "[cva_leverage]") {
    // A DIRECT hedge (r = 1) with the counterparty's own RW, M and notional = EAD: SNH = SCVA x 1.4, so
    // K_hedged = |0.5 (SCVA - SNH)| ... checked against the formula written out.
    const cv::Counterparty c{"C1", "financials", "IG", {{1e6, 5.0, false}}};
    const cv::SingleNameHedge h{"C1", "DIRECT", "financials", "IG", 5.0, 1e6};
    const cv::BaResult r = cv::ba_cva({c}, "FULL", {h}, {});
    const double df = cv::discount_factor(5.0), s = 0.05 * 5e6 * df / 1.4, x = 0.05 * 5.0 * 1e6 * df;
    const double net = s - x;
    const double k_hedged = std::sqrt(0.25 * net * net + 0.75 * net * net + 0.0);
    REQUIRE(r.k_hedged);
    CHECK(std::fabs(*r.k_hedged - k_hedged) <= 1e-12 * k_hedged);
    CHECK(std::fabs(*r.k_full - (0.25 * s + 0.75 * k_hedged)) <= 1e-12 * s);
    CHECK(*r.counterparties[0].hma == 0.0);
    // LEGAL (r = 0.8): HMA = (1 - 0.64) x^2.
    const cv::BaResult l = cv::ba_cva({c}, "FULL", {{"C1", "LEGAL", "financials", "IG", 5.0, 1e6}}, {});
    CHECK(std::fabs(*l.counterparties[0].hma - 0.36 * x * x) <= 1e-12 * x * x);
    CHECK(std::fabs(*l.counterparties[0].snh - 0.8 * x) <= 1e-12 * x);
    const cv::BaResult o = cv::ba_cva({c}, "FULL", {{"C1", "SECTOR_REGION", "financials", "IG", 5.0, 1e6}}, {});
    CHECK(std::fabs(*o.counterparties[0].snh - 0.5 * x) <= 1e-12 * x);
}

TEST_CASE("BA-CVA errors: structure before domain (KR-67)", "[cva_leverage]") {
    const std::string cp = R"({"id":"C1","sector":"financials","quality":"IG","netting_sets":[{"ead":-1,"m":1}]})";
    const std::string ok = R"({"id":"C1","sector":"financials","quality":"IG","netting_sets":[{"ead":1,"m":1}]})";
    // duplicate id (E_INPUT) outranks a negative EAD (E_DOMAIN)
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[)" + cp + "," + cp + "]}") == "E_INPUT");
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[)" + cp + "]}") == "E_DOMAIN");
    CHECK(code("risk.cva.ba", R"({"version":"MIDDLE","counterparties":[)" + ok + "]}") == "E_SCHEMA");
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[{"id":"C1","sector":"retail","quality":"IG","netting_sets":[]}]})") == "E_SCHEMA");
    const std::string hedge = R"("single_name_hedges":[{"counterparty":"C1","relation":"DIRECT","sector":"financials","quality":"IG","m":1,"notional":1}])";
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[)" + ok + "]," + hedge + "}") == "E_INPUT");
    CHECK(code("risk.cva.ba", R"({"version":"FULL","counterparties":[)" + ok + "]," + hedge + "}") == "ok");
    CHECK(code("risk.cva.ba", R"({"version":"FULL","counterparties":[],)" + hedge + "}") == "E_INPUT");
    CHECK(code("risk.cva.ba", R"({"version":"FULL","counterparties":[)" + ok + R"(],"single_name_hedges":[{"counterparty":"C1","relation":"COUSIN","sector":"financials","quality":"IG","m":1,"notional":1}]})") == "E_SCHEMA");
    for (const char* bad : {R"({"m":0,"notional":1,"constituents":[]})", R"({"m":1,"notional":-1,"constituents":[]})",
                            R"({"m":1,"notional":1,"constituents":[{"sector":"other","quality":"IG","weight":-0.5},{"sector":"other","quality":"IG","weight":1.5}]})",
                            R"({"m":1,"notional":1,"constituents":[{"sector":"other","quality":"IG","weight":0.5}]})"})
        CHECK(code("risk.cva.ba", R"({"version":"FULL","counterparties":[)" + ok + R"(],"index_hedges":[)" + bad + "]}") == "E_DOMAIN");
    for (const char* bad : {R"({"counterparty":"C1","relation":"DIRECT","sector":"other","quality":"IG","m":0,"notional":1})",
                            R"({"counterparty":"C1","relation":"DIRECT","sector":"other","quality":"IG","m":1,"notional":-1})"})
        CHECK(code("risk.cva.ba", R"({"version":"FULL","counterparties":[)" + ok + R"(],"single_name_hedges":[)" + bad + "]}") == "E_DOMAIN");
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[{"id":"C1","sector":"other","quality":"IG","netting_sets":[{"ead":1,"m":0}]}]})") == "E_DOMAIN");
    // a non-finite input is E_DOMAIN by the finite rule, ahead of a structural error
    CHECK(code("risk.cva.ba", R"({"version":"REDUCED","counterparties":[{"id":"C1","sector":"other","quality":"IG","netting_sets":[{"ead":"NaN","m":1}]},{"id":"C1","sector":"other","quality":"IG","netting_sets":[]}]})") == "E_DOMAIN");
}

TEST_CASE("py_sum is Python's compensated sum, not a plain loop", "[cva_leverage]") {
    CHECK(cv::py_sum({}) == 0.0);
    CHECK(cv::py_sum({1e16, 1.0, -1e16}) == 1.0);
    CHECK(cv::py_sum({1.0, 1e16, -1e16}) == 1.0);
    CHECK(cv::py_sum({0.1, 0.2, 0.3}) == 0.6);
}

TEST_CASE("SA-CVA IR delta by hand (MAR50.56, KR-311)", "[cva_leverage]") {
    // USD 1Y 1,000,000 x 1.11% and 5Y -2,000,000 x 0.74%, rho 0.72.
    const json::Parsed p = run("risk.cva.sa", R"({"reporting_currency":"USD","classes":{"IR.DELTA":[
        {"bucket":"USD","factor":"1Y","s_cva":1000000,"s_hdg":0},{"bucket":"USD","factor":"5Y","s_cva":-2000000,"s_hdg":0}]}})");
    const double radicand = 11100.0 * 11100.0 + 14800.0 * 14800.0 - 2 * 0.72 * 11100.0 * 14800.0;
    CHECK(std::fabs(out_real(p, "total") - std::sqrt(radicand)) <= 1e-12 * std::sqrt(radicand));
    // An unspecified currency: CURVE and inflation at 1.58%, rho 0.40; the hedge term R sum WSH^2 enters the root.
    const json::Parsed q = run("risk.cva.sa", R"({"reporting_currency":"USD","m_cva":1.25,"classes":{"IR.DELTA":[
        {"bucket":"NZD","factor":"CURVE","s_cva":100,"s_hdg":40},{"bucket":"NZD","factor":"inflation","s_cva":50,"s_hdg":0}]}})");
    const double w1 = 0.0158 * 100 - 0.0158 * 40, w2 = 0.0158 * 50, h1 = 0.0158 * 40;
    const double k = std::sqrt(w1 * w1 + w2 * w2 + 2 * 0.4 * w1 * w2 + 0.01 * h1 * h1);
    CHECK(std::fabs(out_real(q, "total") - 1.25 * k) <= 1e-12 * k);
}

TEST_CASE("SA-CVA cross-bucket gammas of every class", "[cva_leverage]") {
    // Two buckets, one factor each: K = sqrt(WS_b^2 + WS_c^2 + 2 gamma WS_b WS_c) when |S_b| <= K_b.
    const auto two = [](const std::string& key, const std::string& b, const std::string& c, const std::string& extra) {
        return run("risk.cva.sa", R"({"reporting_currency":"EUR","classes":{")" + key + R"(":[{"bucket":")" + b +
                                      R"(",)" + extra + R"("s_cva":1,"s_hdg":0},{"bucket":")" + c + R"(",)" + extra +
                                      R"("s_cva":1,"s_hdg":0}]}})");
    };
    const auto gamma_of = [&](const std::string& key, const std::string& b, const std::string& c,
                              const std::string& extra, double rw_b, double rw_c) {
        const double k = out_real(two(key, b, c, extra), "total");
        return (k * k - rw_b * rw_b - rw_c * rw_c) / (2 * rw_b * rw_c);
    };
    const std::string f = R"("factor":"x",)";
    CHECK(std::fabs(gamma_of("EQ.DELTA", "1", "2", f, 0.55, 0.60) - 0.15) < 1e-12);
    CHECK(std::fabs(gamma_of("EQ.DELTA", "1", "11", f, 0.55, 0.70) - 0.0) < 1e-12);
    CHECK(std::fabs(gamma_of("EQ.DELTA", "12", "13", f, 0.15, 0.25) - 0.75) < 1e-12);
    CHECK(std::fabs(gamma_of("EQ.DELTA", "3", "12", f, 0.45, 0.15) - 0.45) < 1e-12);
    CHECK(std::fabs(gamma_of("COM.DELTA", "1", "2", f, 0.30, 0.35) - 0.20) < 1e-12);
    CHECK(std::fabs(gamma_of("COM.DELTA", "1", "11", f, 0.30, 0.50) - 0.0) < 1e-12);
    CHECK(std::fabs(gamma_of("RCS.DELTA", "1", "2", f, 0.005, 0.01) - 0.75) < 1e-9);
    CHECK(std::fabs(gamma_of("RCS.DELTA", "1", "9", f, 0.005, 0.04) - 0.375) < 1e-9);    // cross quality, halved
    CHECK(std::fabs(gamma_of("RCS.DELTA", "15", "16", f, 0.12, 0.015) - 0.0) < 1e-9);
    CHECK(std::fabs(gamma_of("FX.DELTA", "USD", "GBP", f, 0.11, 0.11) - 0.6) < 1e-12);
    CHECK(std::fabs(gamma_of("IR.VEGA", "USD", "GBP", R"("factor":"IR_VOL",)", 1, 1) - 0.5) < 1e-12);
    const std::string cf = R"("factor":{"name":"N","tenor":"1Y","quality":"IG","index":"I","series":"S"},)";
    CHECK(std::fabs(gamma_of("CCS.DELTA", "2", "3", cf, 0.05, 0.03) - 0.05) < 1e-9);
    CHECK(std::fabs(gamma_of("CCS.DELTA", "1a", "8", cf, 0.005, 0.015) - 0.45) < 1e-9);
    // equity vega: 78% for large-cap buckets 1-8 and 12 (KR-315), 100% otherwise
    const auto vega = [](const std::string& b) {
        return out_real(run("risk.cva.sa", R"({"reporting_currency":"EUR","classes":{"EQ.VEGA":[{"bucket":")" + b +
                                               R"(","factor":"v","s_cva":1,"s_hdg":0}]}})"),
                        "total");
    };
    CHECK(vega("12") == 0.78);
    CHECK(vega("9") == 1.0);
    CHECK(out_real(run("risk.cva.sa", R"({"reporting_currency":"EUR","classes":{"RCS.VEGA":[{"bucket":"3","factor":"v","s_cva":2,"s_hdg":0}],"COM.VEGA":[{"bucket":"3","factor":"v","s_cva":-3,"s_hdg":0}],"FX.VEGA":[{"bucket":"USD","factor":"v","s_cva":4,"s_hdg":0}]}})"), "total") == 9.0);
}

TEST_CASE("SA-CVA counterparty credit spread correlations (MAR50.65, KR-63)", "[cva_leverage]") {
    // One bucket, two names: K^2 = w^2 + w^2 + 2 rho w^2 with rho = tenor x name x quality.
    const auto rho_of = [](const std::string& bucket, const std::string& f1, const std::string& f2) {
        const json::Parsed p = run("risk.cva.sa", R"({"reporting_currency":"EUR","classes":{"CCS.DELTA":[{"bucket":")" +
                                                      bucket + R"(","factor":)" + f1 + R"(,"s_cva":1,"s_hdg":0},{"bucket":")" +
                                                      bucket + R"(","factor":)" + f2 + R"(,"s_cva":1,"s_hdg":0}]}})");
        const json::Value* o = p.value.find("outputs");
        REQUIRE(o);
        const double k = o->find("total")->number;
        const double w = o->find("classes")->find("CCS.DELTA")->find("buckets")->items[0].find("sum_ws")->number / 2;
        return (k * k - 2 * w * w) / (2 * w * w);
    };
    CHECK(std::fabs(rho_of("2", R"({"name":"A","tenor":"1Y","quality":"IG"})", R"({"name":"A","tenor":"5Y","quality":"IG"})") - 0.9) < 1e-9);
    CHECK(std::fabs(rho_of("2", R"({"name":"A","tenor":"1Y","quality":"IG","legal_group":"G"})", R"({"name":"B","tenor":"1Y","quality":"IG","legal_group":"G"})") - 0.9) < 1e-9);
    CHECK(std::fabs(rho_of("2", R"({"name":"A","tenor":"1Y","quality":"IG"})", R"({"name":"B","tenor":"1Y","quality":"IG"})") - 0.5) < 1e-9);
    CHECK(std::fabs(rho_of("8", R"({"name":"A","tenor":"1Y","quality":"IG","index":"I","series":"1"})", R"({"name":"A","tenor":"3Y","quality":"IG","index":"I","series":"1"})") - 0.9) < 1e-9);
    CHECK(std::fabs(rho_of("8", R"({"name":"A","tenor":"1Y","quality":"IG","index":"I","series":"1"})", R"({"name":"A","tenor":"1Y","quality":"IG","index":"I","series":"2"})") - 0.9) < 1e-9);
    CHECK(std::fabs(rho_of("8", R"({"name":"A","tenor":"1Y","quality":"IG","index":"I","series":"1"})", R"({"name":"A","tenor":"1Y","quality":"IG","index":"J","series":"1"})") - 0.8) < 1e-9);
}

TEST_CASE("SA-CVA errors in KR-67 order", "[cva_leverage]") {
    const auto sa = [](const std::string& classes, const std::string& extra = "") {
        return code("risk.cva.sa", R"({"reporting_currency":"USD",)" + extra + R"("classes":{)" + classes + "}}");
    };
    const std::string ir = R"("IR.DELTA":[{"bucket":"USD","factor":"1Y","s_cva":1,"s_hdg":0}])";
    CHECK(sa(R"("XX.DELTA":[])") == "E_SCHEMA");
    CHECK(sa(R"("IR.DELTA":[{"bucket":"USD","factor":"7Y","s_cva":1,"s_hdg":0}])") == "E_SCHEMA");
    CHECK(sa(R"("CCS.DELTA":[{"bucket":"2","factor":"A","s_cva":1,"s_hdg":0}])") == "E_SCHEMA");
    CHECK(sa(R"("CCS.DELTA":[{"bucket":"2","factor":{"name":"A","tenor":"2Y","quality":"IG"},"s_cva":1,"s_hdg":0}])") == "E_SCHEMA");
    CHECK(code("risk.cva.sa", R"({"reporting_currency":"USD"})") == "E_SCHEMA");
    CHECK(sa(R"("CCS.VEGA":[])") == "E_INPUT");
    CHECK(code("risk.cva.sa", R"({"reporting_currency":"usd","classes":{)" + ir + "}}") == "E_INPUT");
    CHECK(sa(R"("FX.DELTA":[{"bucket":"USD","factor":"x","s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("FX.DELTA":[{"bucket":"US","factor":"x","s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("IR.DELTA":[{"bucket":"USD","factor":"CURVE","s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("IR.DELTA":[{"bucket":"NZD","factor":"5Y","s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("IR.DELTA":[{"bucket":"USD","factor":"1Y","s_cva":1,"s_hdg":0},{"bucket":"USD","factor":"1Y","s_cva":2,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("RCS.DELTA":[{"bucket":"18","factor":"x","s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("CCS.DELTA":[{"bucket":"9","factor":{"name":"A","tenor":"1Y","quality":"IG"},"s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("CCS.DELTA":[{"bucket":"8","factor":{"name":"A","tenor":"1Y","quality":"IG"},"s_cva":1,"s_hdg":0}])") == "E_INPUT");
    CHECK(sa(R"("CCS.DELTA":[{"bucket":"2","factor":{"name":"A","tenor":"1Y","quality":"IG"},"s_cva":1,"s_hdg":0},{"bucket":"2","factor":{"name":"A","tenor":"5Y","quality":"HY_NR"},"s_cva":1,"s_hdg":0}])") == "E_INPUT");
    // m_cva below 1 is E_DOMAIN, after every structural check; a structural error outranks it
    CHECK(sa(ir, R"("m_cva":0.5,)") == "E_DOMAIN");
    CHECK(sa(R"("CCS.VEGA":[])", R"("m_cva":0.5,)") == "E_INPUT");
    CHECK(sa(ir, R"("m_cva":"Infinity",)") == "E_DOMAIN");
    CHECK(sa(ir) == "ok");
}

TEST_CASE("leverage ratio parts by hand (LEV30)", "[cva_leverage]") {
    CHECK(std::fabs(lv::derivative_exposure({60, 347, 0, 0}) - 569.8) < 1e-12);
    CHECK(lv::derivative_exposure({-100, 10, 0, 0}) == 1.4 * 10);
    CHECK(lv::written_cd_effective_notional({100, -10, 0}) == 90);
    CHECK(lv::written_cd_effective_notional({100, 10, 0}) == 100);
    CHECK(lv::written_cd_effective_notional({100, -10, 95}) == 0);
    CHECK(lv::sft_exposure({10, true, {5, 3}, {2, 4}}) == 12);
    CHECK(lv::sft_exposure({10, false, {5, 3}, {2, 4}}) == 13);
    CHECK(lv::sft_exposure({10, true, {1}, {4}}) == 10);
    const lv::LeverageResult r = lv::leverage(3, {50}, {{60, 347, 0, 0}}, {{100, -10, 0}}, {{10, false, {5}, {2}}},
                                              {{100, "COMMITMENT"}, {10, "UNCONDITIONALLY_CANCELLABLE"}});
    CHECK(r.on_balance == 50);
    CHECK(std::fabs(r.derivatives - 659.8) < 1e-12);
    CHECK(r.sfts == 13);
    CHECK(r.off_balance == 41);
    CHECK(std::fabs(r.exposure - 763.8) < 1e-12);
    CHECK_FALSE(r.meets_minimum);
    for (const char* cat : {"DIRECT_CREDIT_SUBSTITUTE", "NIF_RUF", "TRANSACTION_CONTINGENT", "TRADE_LC"})
        CHECK(lv::leverage(1, {}, {}, {}, {}, {{10, cat}}).off_balance > 0);
    // 3 >= 0.03 x 100 in binary64 (LEV20.7)
    CHECK(lv::leverage(3, {100}, {}, {}, {}, {}).meets_minimum);
}

TEST_CASE("leverage errors in KR-67 order", "[cva_leverage]") {
    CHECK(code("risk.capital.leverage", R"({"tier1":1,"off_balance":[{"notional":1,"ccf_category":"LOAN"}]})") == "E_SCHEMA");
    CHECK(code("risk.capital.leverage", R"({"tier1":0,"sfts":[{"gross_assets":1,"mna":true,"exposures":[1],"collateral":[]}]})") == "E_INPUT");
    CHECK(code("risk.capital.leverage", R"({"tier1":0,"on_balance":[1]})") == "E_DOMAIN");
    CHECK(code("risk.capital.leverage", R"({"tier1":1})") == "E_DOMAIN");  // exposure 0 (KR-321)
    for (const char* bad : {R"("on_balance":[-1])", R"("derivatives":[{"v":1,"pfe":-1}])",
                            R"("derivatives":[{"v":1,"pfe":1,"cvm_received":-1}])", R"("derivatives":[{"v":1,"pfe":1,"cvm_provided":-1}])",
                            R"("written_credit_derivatives":[{"notional":-1,"fair_value":0}])",
                            R"("written_credit_derivatives":[{"notional":1,"fair_value":0,"purchased_offset":-1}])",
                            R"("sfts":[{"gross_assets":-1,"mna":false,"exposures":[],"collateral":[]}])",
                            R"("sfts":[{"gross_assets":1,"mna":false,"exposures":[-1],"collateral":[0]}])",
                            R"("sfts":[{"gross_assets":1,"mna":false,"exposures":[1],"collateral":[-1]}])",
                            R"("off_balance":[{"notional":-1,"ccf_category":"COMMITMENT"}])"})
        CHECK(code("risk.capital.leverage", std::string(R"({"tier1":1,)") + bad + "}") == "E_DOMAIN");
    const json::Parsed ok = run("risk.capital.leverage", R"({"tier1":100,"derivatives":[{"v":60,"pfe":347}]})");
    CHECK(ok.value.find("outputs")->find("meets_minimum")->boolean);
}

TEST_CASE("KR-53 offsetting by seniority for large exposures", "[cva_leverage]") {
    // a senior short cannot use an equity long; the equity short uses the senior long
    auto [l1, s1] = lv::offset_by_seniority({{3, 100.0}, {1, -40.0}, {4, -30.0}});
    CHECK(l1 == 60.0);
    CHECK(s1 == -30.0);
    // ascending rank among eligible longs: the rank 3 short takes the rank 4 long only
    auto [l2, s2] = lv::offset_by_seniority({{2, 50.0}, {4, 50.0}, {3, -70.0}});
    CHECK(l2 == 50.0);
    CHECK(s2 == -20.0);
    auto [l3, s3] = lv::offset_by_seniority({{0, 0.0}});
    CHECK(l3 == 0.0);
    CHECK(s3 == 0.0);
    CHECK(lv::jtd({"p", "c", "SENIOR", 10, 12}) == 12);
    CHECK(lv::jtd({"p", "c", "SENIOR", 10, -2}) == 0);
    CHECK(lv::jtd({"p", "c", "SENIOR", -10, -12}) == -12);
    CHECK(lv::jtd({"p", "c", "SENIOR", -10, 2}) == 0);
}

TEST_CASE("large exposures by hand (LEX10, LEX20, LEX30)", "[cva_leverage]") {
    const lv::LargeExposuresResult r = lv::large_exposures(
        1000, {{"A", "G", false, false}, {"B", "G", false, true}, {"C", std::nullopt, false, false}, {"P", std::nullopt, false, false}},
        {{"A", 150}, {"B", 200}, {"C", 50}}, {{"C", 100, 0.05}}, {{"A", "P", 20}},
        {{"t1", "C", "SENIOR", 100, 40}, {"t2", "C", "EQUITY", -100, -30}}, false);
    REQUIRE(r.counterparties.size() == 4);
    CHECK(r.counterparties[0].exposure == 130);   // 150 - 20 protected
    CHECK(r.counterparties[2].off_balance == 10);  // CCF floored at 10%
    CHECK(r.counterparties[2].trading_book_net_long == 10);
    CHECK(r.counterparties[3].exposure == 20);  // received
    REQUIRE(r.groups.size() == 3);
    CHECK(r.groups[1].group == "G");
    CHECK(r.groups[1].exposure == 330);
    CHECK(r.groups[1].large);
    CHECK_FALSE(r.groups[1].breach);  // B is exempt: 130 counted against 250
    CHECK_FALSE(r.groups[1].exempt);
    CHECK(r.report == std::vector<std::string>{"G", "C", "P"});
}

TEST_CASE("large exposures errors in KR-67 order", "[cva_leverage]") {
    const auto le = [](const std::string& body) { return code("risk.capital.large_exposures", R"({"tier1":100,)" + body + "}"); };
    CHECK(le(R"("counterparties":[{"id":"A"}],"trading_book":[{"id":"t","counterparty":"A","seniority":"JUNIOR","notional":1,"market_value":1}])") == "E_SCHEMA");
    CHECK(le(R"("counterparties":[{"id":"A"},{"id":"A"}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A","group":"B"},{"id":"B","group":"X"}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"banking_book":[{"counterparty":"Z","value":1}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"off_balance":[{"counterparty":"Z","notional":1,"ccf":1}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"crm":[{"counterparty":"A","provider":"Z","protected":1}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"crm":[{"counterparty":"A","provider":"A","protected":1}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"trading_book":[{"id":"t","counterparty":"A","seniority":"SENIOR","notional":1,"market_value":1},{"id":"t","counterparty":"A","seniority":"SENIOR","notional":1,"market_value":1}])") == "E_INPUT");
    CHECK(le(R"("counterparties":[{"id":"A"}],"banking_book":[{"counterparty":"A","value":-1}])") == "E_DOMAIN");
    CHECK(le(R"("counterparties":[{"id":"A"}],"off_balance":[{"counterparty":"A","notional":-1,"ccf":1}])") == "E_DOMAIN");
    CHECK(le(R"("counterparties":[{"id":"A"}],"off_balance":[{"counterparty":"A","notional":1,"ccf":1.5}])") == "E_DOMAIN");
    CHECK(le(R"("counterparties":[{"id":"A"},{"id":"B"}],"crm":[{"counterparty":"A","provider":"B","protected":-1}])") == "E_DOMAIN");
    CHECK(le(R"("counterparties":[{"id":"A"},{"id":"B"}],"crm":[{"counterparty":"A","provider":"B","protected":1}])") == "E_DOMAIN");
    CHECK(code("risk.capital.large_exposures", R"({"tier1":0,"counterparties":[{"id":"A"}]})") == "E_DOMAIN");
    CHECK(le(R"("counterparties":[{"id":"A"}],"trading_book":[{"id":"t","counterparty":"A","seniority":"SENIOR","notional":1,"market_value":1,"maturity_years":2,"cash_equity":false,"lgd_applies":true}])") == "ok");
    // a group of 25 single counterparties: the report keeps the top 20 plus every large one
    std::string cps, bb;
    for (int k = 0; k < 25; ++k) {
        cps += (k ? "," : "") + std::string(R"({"id":"N)") + std::to_string(100 + k) + R"("})";
        bb += (k ? "," : "") + std::string(R"({"counterparty":"N)") + std::to_string(100 + k) + R"(","value":)" +
              std::to_string(k) + "}";
    }
    const json::Parsed p = run("risk.capital.large_exposures", R"({"tier1":100,"counterparties":[)" + cps +
                                                                     R"(],"banking_book":[)" + bb + "]}");
    const json::Value& report = *p.value.find("outputs")->find("report");
    REQUIRE(report.items.size() == 20);
    CHECK(report.items[0].text == "N124");
}
