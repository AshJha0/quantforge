// Stage F and G goldens replayed in process through the CLI layer, judged with the classes of
// conformance/tolerances/policy.yaml. tests/cli_cases.inc covers the earlier stages; this puts
// the stage F book, F3 risk and use-case-4 adapters under ctest, not only under the external runner.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <utility>

#include "dispatch.hpp"
#include "quantforge/core/json.hpp"

#ifdef QF_REPO_DIR
namespace {

namespace json = quantforge::json;

std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    return s.str();
}

// Writes a parsed value back as JSON; numbers keep their literal spelling.
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

// (absolute, relative); exact classes are (0, 0).
std::pair<double, double> tolerance(const std::string& cls) {
    static const std::map<std::string, std::pair<double, double>> classes = {
        {"date_and_convention", {0, 0}},     {"bit_exact", {0, 0}},
        {"simple_analytic", {1e-12, 1e-10}}, {"interpolation", {1e-10, 1e-8}},
        {"root_finding", {1e-10, 1e-10}},    {"quadrature", {1e-11, 1e-10}},
        {"statistics", {1e-11, 1e-10}},      {"likelihood_sum", {1e-9, 1e-10}},
        {"jacobian", {1e-9, 1e-6}},          {"jacobian_piecewise", {1e-7, 1e-5}},
        {"standard_error", {1e-15, 1e-5}},   {"aad_sensitivity", {1e-10, 1e-8}},
        {"ift_jacobian", {1e-11, 1e-9}},     {"numerical_scheme", {1e-8, 1e-8}},
        {"fourier", {1e-9, 1e-9}},           {"common_rng", {1e-9, 1e-9}},
    };
    const auto it = classes.find(cls);
    REQUIRE(it != classes.end());
    return it->second;
}

// Empty when equal within (a, r) by the runner's rule; otherwise the path of the first difference.
std::string differs(const json::Value& got, const json::Value& want, double a, double r, const std::string& path) {
    if (got.kind != want.kind) return path;
    switch (want.kind) {
        case json::Kind::Number:
            return std::fabs(got.number - want.number) <= a + r * std::max(std::fabs(got.number), std::fabs(want.number))
                       ? ""
                       : path;
        case json::Kind::Array:
            if (got.items.size() != want.items.size()) return path + "[size]";
            for (std::size_t i = 0; i < want.items.size(); ++i)
                if (auto d = differs(got.items[i], want.items[i], a, r, path + "[" + std::to_string(i) + "]"); !d.empty())
                    return d;
            return "";
        case json::Kind::Object:
            if (got.members.size() != want.members.size()) return path + "{keys}";
            for (const auto& [k, v] : want.members) {
                const json::Value* g = got.find(k);
                if (!g) return path + "." + k + "(missing)";
                if (auto d = differs(*g, v, a, r, path + "." + k); !d.empty()) return d;
            }
            return "";
        case json::Kind::String: return got.text == want.text ? "" : path;
        case json::Kind::Bool: return got.boolean == want.boolean ? "" : path;
        default: return "";
    }
}

void replay(const std::string& suite) {
    const json::Parsed doc = json::parse(read_file(std::string(QF_REPO_DIR) + "/datasets/golden/" + suite + ".json"));
    const json::Value* cases = doc.value.find("cases");
    REQUIRE(cases);
    REQUIRE(cases->items.size() >= 3);
    for (const json::Value& c : cases->items) {
        const std::string id = c.find("case_id")->text;
        INFO(id);
        const std::string wire = std::string(R"({"schema_version":"1.0","case_id":")") + id + R"(","operation":")" +
                                 c.find("operation")->text + R"(","inputs":)" + to_text(*c.find("inputs")) + "}";
        const auto res = quantforge::cli::run_case(wire);
        const json::Parsed got = json::parse(res.json);
        const json::Value& exp = *c.find("expected");
        const std::string status = exp.find("status")->text;
        if (status == "any") continue;  // rule F-3: any well-formed result
        if (status == "error") {
            CHECK_FALSE(res.ok);
            const json::Value* err = got.value.find("error");
            REQUIRE(err);
            CHECK(err->find("code")->text == exp.find("error_code")->text);
            continue;
        }
        REQUIRE(status == "ok");
        REQUIRE(res.ok);
        const json::Value* outs = got.value.find("outputs");
        REQUIRE(outs);
        const json::Value* per = c.find("output_classes");
        const auto base = tolerance(c.find("tolerance_class")->text);
        for (const auto& [k, want] : exp.find("outputs")->members) {
            const json::Value* g = outs->find(k);
            REQUIRE(g);
            const json::Value* pc = per ? per->find(k) : nullptr;
            const auto [a, r] = pc ? tolerance(pc->text) : base;
            CHECK(differs(*g, want, a, r, k).empty());
        }
    }
}

}  // namespace

TEST_CASE("stage F book lifecycle goldens: every event type, marks and their errors") { replay("stage_f/book_f"); }
TEST_CASE("stage F3 book sensitivity goldens: PV, quote sensitivity and zero Jacobian") { replay("stage_f/risk_f3"); }
TEST_CASE("stage F use case 4 goldens") { replay("stage_f/uc4_f"); }
// Stage J wave 3 and curves lane: puts ops_research_w3.inc, ops_term_curves.inc and the core
// files behind them under ctest, and so under the per-file coverage gate.
TEST_CASE("stage J scenario stress goldens") { replay("stage_j/scen_j"); }
TEST_CASE("stage J interpolation backtest goldens") { replay("stage_j/interpbt_j"); }
TEST_CASE("stage J drift detector goldens") { replay("stage_j/drift_j"); }
TEST_CASE("stage J term financing goldens") { replay("stage_j/termfin_j"); }
TEST_CASE("stage J liquidity curve goldens") { replay("stage_j/liqcurve_j"); }
// Stage H wave 1: puts ops_execution.inc and execution.cpp under ctest and the per-file coverage gate.
TEST_CASE("stage H schedule goldens") { replay("stage_h/sched_h"); }
TEST_CASE("stage H Almgren-Chriss goldens") { replay("stage_h/ac_h"); }
TEST_CASE("stage H impact goldens") { replay("stage_h/imp_h"); }
TEST_CASE("stage H shortfall TCA goldens") { replay("stage_h/tca_h"); }
TEST_CASE("stage H Avellaneda-Stoikov goldens") { replay("stage_h/as_h"); }
TEST_CASE("stage H use case 5 goldens") { replay("stage_h/uc5_h"); }
TEST_CASE("stage H E1 non-finite input goldens") { replay("stage_h/e1_h"); }
TEST_CASE("stage H dark pool goldens") { replay("stage_h/dark_h"); }
TEST_CASE("stage H smart order router goldens") { replay("stage_h/sor_h"); }
TEST_CASE("stage H auction goldens") { replay("stage_h/auc_h"); }
TEST_CASE("stage H equity convention goldens") { replay("stage_h/eqc_h"); }
TEST_CASE("stage H FX convention goldens") { replay("stage_h/fxc_h"); }
TEST_CASE("stage H FX venue goldens") { replay("stage_h/fxv_h"); }
TEST_CASE("stage H rates convention goldens") { replay("stage_h/rtc_h"); }
TEST_CASE("stage H rates futures goldens") { replay("stage_h/fut_h"); }
TEST_CASE("stage H E1 multi-asset goldens") { replay("stage_h/e1_h4"); }
TEST_CASE("stage H session phase goldens") { replay("stage_h/ses_h"); }
TEST_CASE("stage H asset-class goldens") { replay("stage_h/acls_h"); }
TEST_CASE("stage H microstructure estimator goldens") { replay("stage_h/mest_h"); }
TEST_CASE("stage H venue analytics goldens") { replay("stage_h/venue_h"); }
TEST_CASE("stage H wave 2 adaptive algorithm goldens") { replay("stage_h/alg_h"); }
TEST_CASE("stage H wave 2 pre-trade and attribution goldens") { replay("stage_h/tcx_h"); }
TEST_CASE("stage H wave 2 execution E1 goldens") { replay("stage_h/e1_h3"); }
TEST_CASE("stage H wave 2 execution enum goldens") { replay("stage_h/enum_h"); }
TEST_CASE("stage H paper trading goldens") { replay("stage_h/pt_h"); }
TEST_CASE("stage H paper trading E1 goldens") { replay("stage_h/e1_hpt"); }
#endif
