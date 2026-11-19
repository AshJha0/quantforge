// Stage K wave 1b (K-8d SA-CCR, K-8e FRTB IMA backtesting): CRE99 published EADs, rules, errors in HR-122 order,
// MAR99 Table 2, seeded property tests, and the three golden suites replayed in process through the CLI handlers
// before the coordinator registers them. No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <fstream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/frtb_backtest.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/saccr.hpp"
#include "quantforge/core/stats.hpp"
#include "dispatch.hpp"

// The CLI layer as compiled into this test, with its four external functions renamed so they do not clash with
// quantforge_cli_lib: the handlers of ops_k_w1b.inc need dispatch.cpp's anonymous-namespace In, Out and readers.
#define run_case k_w1b_copy_run_case
#define operations k_w1b_copy_operations
#define operations_json k_w1b_copy_operations_json
#define version_json k_w1b_copy_version_json
#ifndef QF_VERSION
#define QF_VERSION "test"
#endif
#include "../src/cli/dispatch.cpp"
#undef run_case
#undef operations
#undef operations_json
#undef version_json

namespace quantforge::cli {
namespace {
#include "../src/cli/ops_k_w1b.inc"  // a no-op once dispatch.cpp includes it (#pragma once)

// run_case without the envelope, the handler looked up in k_w1b_ops first, then in the registered table.
std::string k_w1b_run(string_view op, const Value& inputs) {
    first_non_finite.reset();
    Handler handler = nullptr;
    for (const Entry& e : k_w1b_ops)
        if (e.verb == op) handler = e.handler;
    if (!handler) handler = table().at(string(op));
    const bool big = oversized(inputs);
    try {
        Out out;
        out.values.begin_object();
        out.diagnostics.begin_object();
        handler(In(inputs, big), out);
        In(inputs, big).ready();
        out.values.end_object();
        return R"({"status":"ok","outputs":)" + out.values.str() + "}";
    } catch (const Error& e) {
        string s = R"({"status":"error","error":{"code":)";
        json::append_string(s, e.code());
        return s + "}}";
    }
}

bool k_w1b_registered(string_view op) { return table().contains(string(op)); }
}  // namespace
}  // namespace quantforge::cli

using namespace quantforge;
using quantforge::json::Kind;
using quantforge::json::Value;

namespace {

std::string k_read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    std::stringstream b;
    b << f.rdbuf();
    return b.str();
}

std::string k_repo(const std::string& rel) {
#ifdef QF_REPO_DIR
    return std::string(QF_REPO_DIR) + "/" + rel;
#else
    return "../" + rel;
#endif
}

// Empty when equal within (absolute, relative); exact when relative is negative.
std::string k_same(const Value& a, const Value& e, double ab, double re, const std::string& path) {
    if (e.kind == Kind::Object) {
        for (const auto& [k, ev] : e.members) {
            const Value* av = a.find(k);
            if (!av) return path + "." + k + " missing";
            if (auto p = k_same(*av, ev, ab, re, path + "." + k); !p.empty()) return p;
        }
        return {};
    }
    if (e.kind == Kind::Array) {
        if (a.kind != Kind::Array || a.items.size() != e.items.size()) return path + " length";
        for (std::size_t i = 0; i < e.items.size(); ++i)
            if (auto p = k_same(a.items[i], e.items[i], ab, re, path + "[" + std::to_string(i) + "]"); !p.empty()) return p;
        return {};
    }
    if (e.kind == Kind::Number) {
        if (a.kind != Kind::Number) return path + " not a number";
        const bool ok = re < 0 ? a.number == e.number
                               : std::fabs(a.number - e.number) <= ab + re * std::max(std::fabs(a.number), std::fabs(e.number));
        return ok ? std::string() : path + ": " + std::to_string(a.number) + " vs " + std::to_string(e.number);
    }
    const bool ok = a.kind == e.kind && a.text == e.text && a.boolean == e.boolean;
    return ok ? std::string() : path + " differs";
}

struct SuiteResult {
    std::vector<std::string> failures;
    std::size_t cases = 0, two_errors = 0;
};

SuiteResult k_replay(const std::string& name) {
    const json::Parsed doc = json::parse(k_read_file(k_repo("datasets/golden/stage_k/" + name + ".json")));
    SuiteResult out;
    for (const Value& c : doc.value.find("cases")->items) {
        ++out.cases;
        const std::string id = c.find("case_id")->text;
        if (const Value* d = c.find("description"); d && d->text.find("two errors") != std::string::npos) ++out.two_errors;
        const json::Parsed got = json::parse(cli::k_w1b_run(c.find("operation")->text, *c.find("inputs")));
        const Value& want = *c.find("expected");
        const std::string& status = want.find("status")->text;
        if (got.value.find("status")->text != status) {
            out.failures.push_back(id + ": status");
            continue;
        }
        if (status == "error") {
            if (got.value.find("error")->find("code")->text != want.find("error_code")->text)
                out.failures.push_back(id + ": code " + got.value.find("error")->find("code")->text);
            continue;
        }
        const Value* classes = c.find("output_classes");
        const std::string base = c.find("tolerance_class")->text;
        for (const auto& [k, ev] : want.find("outputs")->members) {
            const Value* cls = classes ? classes->find(k) : nullptr;
            const bool exact = (cls ? cls->text : base) != "simple_analytic";
            const Value* av = got.value.find("outputs")->find(k);
            const std::string p = av ? k_same(*av, ev, 1e-12, exact ? -1.0 : 1e-10, id + "." + k) : id + "." + k + " missing";
            if (!p.empty()) out.failures.push_back(p);
        }
    }
    return out;
}

saccr::Trade k_ir(const std::string& id, double n, double mv, double m, const std::string& pos, double s, double e,
                const std::string& ccy) {
    saccr::Trade t;
    t.id = id;
    t.asset_class = "IR";
    t.notional = n;
    t.market_value = mv;
    t.maturity = m;
    t.position = pos;
    t.start = s;
    t.end = e;
    t.hedging_set = ccy;
    return t;
}

saccr::Trade k_fx(const std::string& id, double n, double mv, double m, const std::string& pos,
                std::optional<std::string> pair) {
    saccr::Trade t;
    t.id = id;
    t.asset_class = "FX";
    t.notional = n;
    t.market_value = mv;
    t.maturity = m;
    t.position = pos;
    t.hedging_set = std::move(pair);
    return t;
}

saccr::Trade k_named(const std::string& id, const std::string& cls, double n, double mv, double m, const std::string& pos,
                   const std::string& ent, const std::string& sub) {
    saccr::Trade t;
    t.id = id;
    t.asset_class = cls;
    t.notional = n;
    t.market_value = mv;
    t.maturity = m;
    t.position = pos;
    t.entity = ent;
    t.subclass = sub;
    if (cls == "CREDIT") {
        t.start = 0.0;
        t.end = m;
    }
    return t;
}

std::vector<saccr::Trade> k_ex1() {
    saccr::Trade swaption = k_ir("3", 5000, 50, 11, "BOUGHT", 1, 11, "EUR");
    swaption.kind = "OPTION";
    swaption.option_type = "PUT";
    swaption.underlying_price = 0.06;
    swaption.strike = 0.05;
    swaption.exercise = 1.0;
    return {k_ir("1", 10000, 30, 10, "LONG", 0, 10, "USD"), k_ir("2", 10000, -20, 4, "SHORT", 0, 4, "USD"), swaption};
}

std::vector<saccr::Trade> k_ex2() {
    return {k_named("4", "CREDIT", 10000, 20, 3, "LONG", "Firm A", "AA"),
            k_named("5", "CREDIT", 10000, -40, 6, "SHORT", "Firm B", "BBB"),
            k_named("6", "CREDIT", 10000, 0, 5, "LONG", "CDX.IG", "IG")};
}

std::vector<saccr::Trade> k_ex3() {
    return {k_named("7", "COMMODITY", 10000, -50, 0.75, "LONG", "CRUDE_OIL", "OIL_GAS"),
            k_named("8", "COMMODITY", 20000, -30, 2, "SHORT", "CRUDE_OIL", "OIL_GAS"),
            k_named("9", "COMMODITY", 10000, 100, 5, "LONG", "SILVER", "METALS")};
}

std::vector<saccr::Trade> k_join(std::vector<saccr::Trade> a, const std::vector<saccr::Trade>& b) {
    a.insert(a.end(), b.begin(), b.end());
    return a;
}

saccr::Margin k_weekly() {
    saccr::Margin m;
    m.mta = 5;
    m.nica = 150;
    m.remargin_days = 5;
    return m;
}

saccr::Result k_plain_ead(const std::vector<saccr::Trade>& t) { return saccr::ead(t, 0.0, std::nullopt, true); }

template <class F>
std::string k_code_of(F f, std::string* field = nullptr) {
    try {
        f();
    } catch (const Error& e) {
        if (field) *field = e.field();
        return e.code();
    }
    return "ok";
}

}  // namespace

TEST_CASE("K-8d: CRE99 published EADs (KR-30) and intermediates", "[k_w1b]") {
    CHECK(std::round(k_plain_ead(k_ex1()).ead) == 569);
    CHECK(std::round(k_plain_ead(k_ex2()).ead) == 381);
    CHECK(std::round(k_plain_ead(k_ex3()).ead) == 5406);
    CHECK(std::round(k_plain_ead(k_join(k_ex1(), k_ex2())).ead) == 936);
    const saccr::Result r5 = saccr::ead(k_join(k_ex1(), k_ex3()), 200.0, k_weekly(), true);
    CHECK(std::round(r5.ead) == 1879);
    const saccr::Result r1 = k_plain_ead(k_ex1());
    CHECK(std::round(r1.trades[0].adjusted_notional) == 78694);
    CHECK(std::round(r1.trades[1].adjusted_notional) == 36254);
    CHECK(std::round(r1.trades[2].adjusted_notional) == 37428);
    CHECK(std::round(r1.trades[2].delta * 1e4) / 1e4 == -0.2694);
    CHECK(std::round(r1.trades[2].effective_notional) == -10083);
    CHECK(r1.hedging_sets[0].key == "EUR");
    CHECK(std::round(r1.hedging_sets[1].addon * 100) == 29635);
    CHECK(r1.rc == 60.0);
    const saccr::Result r2 = k_plain_ead(k_ex2());
    CHECK(std::round(r2.addon_aggregate) == 282);
    CHECK(std::round(r2.multiplier * 1000) == 965);
    const saccr::Result r3 = k_plain_ead(k_ex3());
    CHECK(std::round(r3.trades[0].effective_notional) == 8660);
    CHECK(r3.hedging_sets[0].key == "ENERGY");
    CHECK(std::round(r3.hedging_sets[0].addon) == 2041);
    CHECK(r5.mpor_days == 14);
    CHECK(r5.rc == 0.0);
    CHECK(r5.v == 80.0);
    CHECK(std::round(r5.trades[4].effective_notional) == -7099);  // KR-31: printed -7,100
    CHECK(std::round(r5.addon_aggregate) == 1401);
    CHECK(std::round(r5.multiplier * 1000) == 958);
    CHECK_FALSE(r5.capped);
    CHECK(r5.margined);
    CHECK(*r5.ead_unmargined > r5.ead);
}

TEST_CASE("K-8d: embedded tables parse as the spec files", "[k_w1b]") {
    const json::Parsed s = json::parse(k_read_file(k_repo("specifications/06-risk/sa-ccr-parameters.json")));
    const auto& rows = s.value.find("table2")->items;
    const auto& p = saccr::params();
    REQUIRE(p.table2.size() == rows.size());
    for (std::size_t i = 0; i < rows.size(); ++i) {
        CHECK(p.table2[i].factor == rows[i].find("supervisory_factor")->number);
        CHECK(p.table2[i].option_volatility == rows[i].find("option_volatility")->number);
        const Value* corr = rows[i].find("correlation");
        CHECK(p.table2[i].correlation.has_value() == (corr->kind == Kind::Number));
    }
    CHECK(p.alpha == s.value.find("alpha")->number);
    const json::Parsed f = json::parse(k_read_file(k_repo("specifications/06-risk/frtb-ima-backtest-tables.json")));
    const auto& m = f.value.find("multiplier_250")->items;
    REQUIRE(frtb_backtest::tables().multiplier_250.size() == m.size());
    for (std::size_t i = 0; i < m.size(); ++i) CHECK(frtb_backtest::tables().multiplier_250[i] == m[i].number);
    CHECK(double(frtb_backtest::tables().max_observations) == f.value.find("max_observations")->number);
}

TEST_CASE("K-8d: multiplier edges and the exponential overflow (KR-36)", "[k_w1b]") {
    const double tiny = std::nextafter(0.0, 1.0);
    CHECK(saccr::multiplier(1e6, tiny) == 1.0);
    CHECK(saccr::multiplier(0.0, 0.0) == 1.0);
    CHECK(saccr::multiplier(-1.0, 0.0) == 0.05);
    CHECK(saccr::multiplier(-1e6, tiny) == 0.05);
    const saccr::Result r = k_plain_ead({k_fx("a", tiny, 5, 1, "LONG", "EURUSD")});
    CHECK(r.multiplier == 1.0);
    CHECK(std::fabs(r.ead - 7.0) < 1e-12);
}

TEST_CASE("K-8d: rules and edges", "[k_w1b]") {
    CHECK(saccr::supervisory_duration(0, 0) == 10.0 / 250.0);
    CHECK(saccr::bucket(0.5) == 1);
    CHECK(saccr::bucket(1.0) == 2);
    CHECK(saccr::bucket(5.0) == 2);
    CHECK(saccr::bucket(5.0001) == 3);
    saccr::Margin daily;
    CHECK(saccr::mpor_floor(daily, 1) == 10);
    CHECK(saccr::mpor_floor(daily, 5001) == 20);
    saccr::Margin hard;
    hard.illiquid = hard.disputes = true;
    CHECK(saccr::mpor_floor(hard, 1) == 40);
    CHECK(saccr::mpor_floor(k_weekly(), 5000) == 14);
    saccr::Trade cdo = k_named("c", "CREDIT", 100, 0, 1, "SOLD", "T", "IG");
    cdo.kind = "CDO";
    cdo.attachment = 0.03;
    cdo.detachment = 0.07;
    CHECK(std::fabs(saccr::supervisory_delta(cdo) + 15 / (1.42 * 1.98)) < 1e-15);
    saccr::Trade call = k_fx("o", 100, 0, 1, "SOLD", "EURUSD");
    call.kind = "OPTION";
    call.option_type = "CALL";
    call.underlying_price = 1.1;
    call.strike = 1.0;
    call.exercise = 0.5;
    const double d1 = (std::log(1.1) + 0.5 * 0.15 * 0.15 * 0.5) / (0.15 * std::sqrt(0.5));
    CHECK(std::fabs(saccr::supervisory_delta(call) + normal_cdf(d1)) < 1e-15);
    CHECK(saccr::ead(k_ex1(), 0, std::nullopt, false).addon[0] > k_plain_ead(k_ex1()).addon[0]);
    const saccr::Trade base = k_named("e", "EQUITY", 100, 0, 1, "LONG", "X", "SINGLE");
    const double a0 = k_plain_ead({base}).addon_aggregate;
    saccr::Trade basis = base;
    basis.treatment = "BASIS";
    basis.hedging_set = "H";
    saccr::Trade vol = basis;
    vol.treatment = "VOLATILITY";
    CHECK(std::fabs(k_plain_ead({basis}).addon_aggregate - 0.5 * a0) < 1e-12);
    CHECK(std::fabs(k_plain_ead({vol}).addon_aggregate - 5 * a0) < 1e-12);
    saccr::Margin big;
    big.threshold = 1e6;
    big.mpor_days = 15;
    const saccr::Result capped = saccr::ead({k_fx("a", 100, 0, 1, "LONG", "EURUSD")}, 0, big, true);
    CHECK(capped.capped);
    CHECK(capped.mpor_days == 15);
    CHECK(capped.ead_unmargined == capped.ead);
    const saccr::Result unm = k_plain_ead({k_fx("a", 100, 0, 1, "LONG", "EURUSD")});
    CHECK_FALSE(unm.mpor_days.has_value());
    CHECK_FALSE(unm.ead_unmargined.has_value());
    CHECK_FALSE(unm.trades[0].supervisory_duration.has_value());
}

TEST_CASE("K-8d: errors, structure before domain (HR-122)", "[k_w1b]") {
    const auto expect = [](const std::string& code, const std::string& field, std::vector<saccr::Trade> t,
                           std::optional<saccr::Margin> m = std::nullopt, double collateral = 0.0) {
        std::string got_field;
        CHECK(k_code_of([&] { saccr::ead(t, collateral, m, true); }, &got_field) == code);
        CHECK(got_field == field);
    };
    const saccr::Trade ok = k_fx("a", 100, 0, 1, "LONG", "EURUSD");
    expect("E_INPUT", "trades", {});
    expect("E_INPUT", "id", {ok, ok});
    saccr::Trade no_dates = k_ir("a", 1, 0, 1, "LONG", 0, 1, "USD");
    no_dates.start.reset();
    expect("E_INPUT", "start", {no_dates});
    expect("E_INPUT", "hedging_set", {k_fx("a", 1, 0, 1, "LONG", std::nullopt)});
    saccr::Trade no_entity = k_named("a", "EQUITY", 1, 0, 1, "LONG", "X", "SINGLE");
    no_entity.entity.reset();
    expect("E_INPUT", "entity", {no_entity});
    expect("E_INPUT", "subclass", {k_named("a", "EQUITY", 1, 0, 1, "LONG", "X", "IG")});
    saccr::Trade fx_sub = ok;
    fx_sub.subclass = "IG";
    expect("E_INPUT", "subclass", {fx_sub});
    expect("E_INPUT", "subclass",
           {k_named("a", "EQUITY", 1, 0, 1, "LONG", "X", "SINGLE"), k_named("b", "EQUITY", 1, 0, 1, "LONG", "X", "INDEX")});
    expect("E_INPUT", "position", {k_fx("a", 1, 0, 1, "BOUGHT", "X")});
    saccr::Trade bare_option = ok;
    bare_option.kind = "OPTION";
    bare_option.position = "BOUGHT";
    expect("E_INPUT", "option_type", {bare_option});
    saccr::Trade fx_cdo = bare_option;
    fx_cdo.kind = "CDO";
    expect("E_INPUT", "kind", {fx_cdo});
    saccr::Trade cdo = k_named("c", "CREDIT", 1, 0, 1, "BOUGHT", "T", "IG");
    cdo.kind = "CDO";
    cdo.detachment = 0.2;
    expect("E_INPUT", "attachment", {cdo});
    expect("E_DOMAIN", "notional", {k_fx("a", 0, 0, 1, "LONG", "X")});
    expect("E_DOMAIN", "maturity", {k_fx("a", 1, 0, -1, "LONG", "X")});
    expect("E_DOMAIN", "start", {k_ir("a", 1, 0, 1, "LONG", 2, 1, "USD")});
    const auto option = [](double p, double k, double t) {
        saccr::Trade o = k_fx("o", 100, 0, 1, "BOUGHT", "X");
        o.kind = "OPTION";
        o.option_type = "CALL";
        o.underlying_price = p;
        o.strike = k;
        o.exercise = t;
        return o;
    };
    expect("E_DOMAIN", "strike", {option(1, 0, 1)});
    expect("E_DOMAIN", "strike", {option(0, 1, 1)});
    expect("E_DOMAIN", "exercise", {option(1, 1, 0)});
    for (const auto& [a, d] : {std::pair{0.3, 0.3}, std::pair{-0.1, 0.3}, std::pair{0.1, 1.3}}) {
        saccr::Trade bad = cdo;
        bad.attachment = a;
        bad.detachment = d;
        expect("E_DOMAIN", "attachment", {bad});
    }
    saccr::Margin m;
    m.threshold = -1;
    expect("E_DOMAIN", "threshold", {ok}, m);
    m = saccr::Margin{};
    m.mta = -1;
    expect("E_DOMAIN", "mta", {ok}, m);
    m = saccr::Margin{};
    m.remargin_days = 0;
    expect("E_DOMAIN", "remargin_days", {ok}, m);
    m = saccr::Margin{};
    m.mpor_days = 0;
    expect("E_DOMAIN", "mpor_days", {ok}, m);
    expect("E_INPUT", "hedging_set", {k_fx("a", -5, 0, 1, "LONG", "X"), k_fx("b", 1, 0, 1, "LONG", std::nullopt)});
    expect("E_DOMAIN", "notional", {k_fx("b", std::nan(""), 0, 1, "LONG", std::nullopt)});
    saccr::Trade inf_strike = ok;
    inf_strike.strike = INFINITY;
    expect("E_DOMAIN", "strike", {inf_strike});
    expect("E_DOMAIN", "collateral", {ok}, std::nullopt, std::nan(""));
    m = saccr::Margin{};
    m.nica = std::nan("");
    expect("E_DOMAIN", "nica", {ok}, m);
}

TEST_CASE("K-8d: seeded properties (multiplier range, netting bound, monotone EAD)", "[k_w1b]") {
    const std::vector<std::vector<std::string>> subs = {
        {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "IG", "SG"},
        {"SINGLE", "INDEX"},
        {"ELECTRICITY", "OIL_GAS", "METALS", "AGRICULTURAL", "OTHER"}};
    const auto portfolio = [&subs](unsigned seed, double scale) {
        std::mt19937_64 g(seed);
        std::uniform_real_distribution<double> u(0.0, 1.0);
        std::vector<saccr::Trade> out;
        const auto count = 1 + g() % 6;
        for (std::size_t k = 0; k < count; ++k) {
            const auto cls = std::size_t(g() % 5);
            const std::string pos = g() % 2 ? "LONG" : "SHORT";
            const double n = (1.0 + u(g) * 1e7) * scale;
            const double v = -1e5 + 2e5 * u(g);
            const double m = 0.01 + 30 * u(g);
            const double s = 5 * u(g);
            const auto pick = g();
            const std::string id = std::to_string(k);
            if (cls == 0) out.push_back(k_ir(id, n, v, m, pos, s, s + m, pick % 2 ? "USD" : "EUR"));
            else if (cls == 1) out.push_back(k_fx(id, n, v, m, pos, pick % 2 ? "EURUSD" : "USDJPY"));
            else {
                const auto& list = subs[cls - 2];
                const std::string& sb = list[pick % list.size()];
                out.push_back(k_named(id, saccr::classes[cls], n, v, m, pos, sb + "-" + std::to_string(pick % 3), sb));
            }
        }
        return out;
    };
    for (unsigned trial = 0; trial < 300; ++trial) {
        const auto t = portfolio(1000 + trial, 1.0);
        const double c = -1e5 + 2e5 * [trial] {
            std::mt19937_64 gc(trial);
            return std::uniform_real_distribution<double>(0.0, 1.0)(gc);
        }();
        const saccr::Result r = saccr::ead(t, c, std::nullopt, true);
        CHECK((r.multiplier >= 0.05 && r.multiplier <= 1.0));
        double alone = 0.0;
        for (const auto& x : t) alone += k_plain_ead({x}).addon_aggregate;
        CHECK(r.addon_aggregate <= alone * (1 + 1e-12) + 1e-9);
        CHECK(saccr::ead(portfolio(1000 + trial, 1.5), c, std::nullopt, true).ead >= r.ead * (1 - 1e-12));
        CHECK(saccr::ead(t, c + 100.0, std::nullopt, true).ead <= r.ead * (1 + 1e-12) + 1e-9);
    }
    std::mt19937_64 g(5);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    for (int i = 0; i < 2000; ++i) {
        const double addon = std::exp(-5 + 15 * u(g));
        const double m = saccr::multiplier(-addon * 30 * u(g), addon);
        CHECK((m > 0.05 && m <= 1.0));
    }
}

TEST_CASE("K-8e: MAR99 Table 2, zone boundaries, desk and counting", "[k_w1b]") {
    const json::Parsed f = json::parse(k_read_file(k_repo("specifications/06-risk/frtb-ima-backtest-tables.json")));
    const auto& pct = f.value.find("printed_table2_cumulative_percent")->items;
    const auto& zones_printed = f.value.find("printed_table2_zone")->items;
    const double mult[] = {1.5, 1.5, 1.5, 1.5, 1.5, 1.7, 1.76, 1.83, 1.88, 1.92, 2.0};
    for (long long x = 0; x <= 10; ++x) {
        const auto z = frtb_backtest::zone(250, x, 0);
        const auto i = std::size_t(x);
        CHECK(std::round(z.cumulative_probability * 1e4) / 100.0 == pct[i].number);
        CHECK(z.zone == zones_printed[i].text);
        CHECK(z.multiplier == mult[i]);
        CHECK(z.amber_from == 5);
        CHECK(z.red_from == 10);
    }
    CHECK_FALSE(frtb_backtest::zone(260, 6, 6).multiplier.has_value());
    CHECK(frtb_backtest::zone(1, 0, 0).zone == "AMBER");  // KR-42
    CHECK(frtb_backtest::binomial_cdf(10, -1, 0.01) == 0.0);
    CHECK(frtb_backtest::binomial_cdf(10, 10, 0.01) == 1.0);
    CHECK(frtb_backtest::first_at_least(1, 0.5, 0.9999) == 1);
    std::mt19937_64 g(17);
    for (int i = 0; i < 200; ++i) {
        const auto n = (long long)(1 + g() % 3000);
        const auto z = frtb_backtest::zone(n, 0, 0);
        CHECK(frtb_backtest::binomial_cdf(n, z.amber_from, 0.01) >= 0.95);
        CHECK((z.amber_from == 0 || frtb_backtest::binomial_cdf(n, z.amber_from - 1, 0.01) < 0.95));
        CHECK(frtb_backtest::binomial_cdf(n, z.red_from, 0.01) >= 0.9999);
        CHECK((z.red_from == 0 || frtb_backtest::binomial_cdf(n, z.red_from - 1, 0.01) < 0.9999));
        const auto x = (long long)(g() % std::uint64_t(n + 1));
        const std::string want = x >= z.red_from ? "RED" : x >= z.amber_from ? "AMBER" : "GREEN";
        CHECK(frtb_backtest::zone(n, x, 0).zone == want);
    }
    const auto d = frtb_backtest::desk(250, {12, 10, 30, 28});
    CHECK((d.eligible && !d.breach_99 && !d.breach_975));
    CHECK(frtb_backtest::desk(250, {13, 0, 0, 0}).breach_99);
    const auto d31 = frtb_backtest::desk(250, {0, 0, 0, 31});
    CHECK((d31.breach_975 && !d31.eligible));
    const auto c = frtb_backtest::count_exceptions({1.0, 1.0, std::nullopt, 2.0, 0.5}, {-1.0, -1.25, 0.3, std::nullopt, 0.0},
                                                   {-1.5, 0.0, 0.1, -2.5, -0.5});
    CHECK(c.days_actual == std::vector<long long>{1, 2, 3});
    CHECK(c.days_hypothetical == std::vector<long long>{0, 2, 3});
    CHECK(c.exceptions == 3);
    CHECK(k_code_of([] { frtb_backtest::zone(1000001, -1, 0); }) == "E_LIMIT");
    CHECK(k_code_of([] { frtb_backtest::zone(0, 0, 0); }) == "E_DOMAIN");
    CHECK(k_code_of([] { frtb_backtest::zone(10, 11, 0); }) == "E_DOMAIN");
    CHECK(k_code_of([] { frtb_backtest::zone(10, 0, -1); }) == "E_DOMAIN");
    CHECK(k_code_of([] { frtb_backtest::desk(250, {0, 0, 251, 0}); }) == "E_DOMAIN");
    std::string field;
    CHECK(k_code_of([] { frtb_backtest::count_exceptions({}, {}, {}); }, &field) == "E_INPUT");
    CHECK(field == "var");
    CHECK(k_code_of([] { frtb_backtest::count_exceptions({1.0}, {}, {1.0}); }, &field) == "E_INPUT");
    CHECK(field == "actual");
    CHECK(k_code_of([] { frtb_backtest::count_exceptions({1.0}, {1.0}, {}); }, &field) == "E_INPUT");
    CHECK(field == "hypothetical");
    CHECK(k_code_of([] { frtb_backtest::count_exceptions({std::nan("")}, {1.0}, {1.0}); }) == "E_DOMAIN");
}

TEST_CASE("K-8d/K-8e: the three golden suites replay in process through the handlers", "[k_w1b]") {
    for (const char* suite : {"saccr_k", "btk_k", "tlk_k"}) {
        const auto r = k_replay(suite);
        INFO(suite << ": " << (r.failures.empty() ? std::string() : r.failures.front()));
        CHECK(r.failures.empty());
        CHECK(r.cases > 0);
        if (std::string(suite) != "tlk_k") CHECK(r.two_errors >= 1);
    }
}

TEST_CASE("K-8d/K-8e: input layer order and the registered verbs", "[k_w1b]") {
    const auto code = [](const char* op, const char* text) {
        const json::Parsed in = json::parse(text);
        const json::Parsed out = json::parse(cli::k_w1b_run(op, in.value));
        const Value* e = out.value.find("error");
        return e ? e->find("code")->text : std::string("ok");
    };
    CHECK(code("risk.saccr.ead", R"({"trades":[{"id":"a","asset_class":"FX","notional":0,"market_value":0,"maturity":1,"position":"LONG","hedging_set":"X","kind":"SWAP"}]})") == "E_SCHEMA");
    CHECK(code("risk.saccr.ead", R"({"trades":[{"id":"a","asset_class":"FX","notional":"NaN","market_value":0,"maturity":1,"position":"LONG"}]})") == "E_DOMAIN");
    CHECK(code("risk.saccr.ead", R"({"trades":[{"id":"a","asset_class":"FX","notional":1,"market_value":0,"maturity":1,"position":"LONG","hedging_set":"X"}],"margin":3})") == "E_SCHEMA");
    CHECK(code("risk.frtb.backtest.desk", R"({"observations":1000001,"exceptions_99_actual":-1,"exceptions_99_hypothetical":0,"exceptions_975_actual":0,"exceptions_975_hypothetical":0})") == "E_LIMIT");
    CHECK(code("risk.saccr.ead", R"({"trades":[{"id":"o","asset_class":"EQUITY","notional":10,"market_value":1,"maturity":1,"position":"SOLD","kind":"OPTION","option_type":"PUT","underlying_price":1,"strike":1,"exercise":1,"shift":0.5,"entity":"E","subclass":"INDEX","treatment":"NORMAL"}],"collateral":1,"ir_offset":false,"margin":{"threshold":0,"mta":0,"nica":0,"remargin_days":1,"mpor_days":12,"illiquid":false,"disputes":false}})") == "ok");
    // Registered in dispatch.cpp at integration (stage K round 1).
    for (const auto& e : cli::k_w1b_ops) CHECK(cli::k_w1b_registered(e.verb));
}
