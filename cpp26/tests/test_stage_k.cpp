// Stage K wave 1 (PROPOSED rulings KR-1 to KR-14): every stage_k golden row through the CLI (values to 1e-12
// relative and 1e-15 absolute, key order checked), the HR-66 error order on each verb, every library branch, and
// the properties the specs fix: KR-4 on 10,000 generated logs, the incremental update against a full rebuild on
// 10,000 random vectors (copied pillars bit-identical), and |estimate - revaluation| <= bound on the seeded
// 50-position book of intraday-risk-bounds.md (numpy's default_rng stream, so the book is the Python test's own).
// A port of python/tests/test_stage_k_w1.py.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <optional>
#include <fstream>
#include <limits>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "numpy_rng.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"
#include "quantforge/core/stage_k.hpp"
#include "quantforge/core/store.hpp"

namespace {

namespace json = quantforge::json;
namespace sk = quantforge::stage_k;
using quantforge::test::NumpyRng;
using Vec = std::vector<double>;

constexpr std::int64_t t0 = 1767225600;  // 2026-01-01T00:00:00Z
constexpr std::int64_t day = 86400;

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

std::string run_text(const std::string& op, const std::string& inputs) {
    return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                     R"(","inputs":)" + inputs + "}")
        .json;
}

json::Value run(const std::string& op, const std::string& inputs) { return json::parse(run_text(op, inputs)).value; }

std::string code(const std::string& op, const std::string& inputs) {
    const json::Value r = run(op, inputs);
    INFO(to_text(r));
    REQUIRE(r.find("status")->text == "error");
    return r.find("error")->find("code")->text;
}

json::Value ok(const std::string& op, const std::string& inputs) {
    const json::Value r = run(op, inputs);
    INFO(to_text(r));
    REQUIRE(r.find("status")->text == "ok");
    return *r.find("outputs");
}

template <class F>
std::string lib_code(F f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code();
    }
    return "none";
}

// Empty when equal (numbers within 1e-15 + 1e-12 relative, keys in the same order); else the first difference.
std::string differs(const json::Value& a, const json::Value& e, const std::string& path) {
    if (a.kind != e.kind) return path + " kind";
    switch (e.kind) {
        case json::Kind::Number:
            return std::fabs(a.number - e.number) <= 1e-15 + 1e-12 * std::max(std::fabs(a.number), std::fabs(e.number))
                       ? ""
                       : path;
        case json::Kind::Array:
            if (a.items.size() != e.items.size()) return path + "[size]";
            for (std::size_t i = 0; i < e.items.size(); ++i)
                if (auto d = differs(a.items[i], e.items[i], path + "[" + std::to_string(i) + "]"); !d.empty()) return d;
            return "";
        case json::Kind::Object:
            if (a.members.size() != e.members.size()) return path + "{keys}";
            for (std::size_t i = 0; i < e.members.size(); ++i) {
                if (a.members[i].first != e.members[i].first) return path + " key order";
                if (auto d = differs(a.members[i].second, e.members[i].second, path + "." + e.members[i].first);
                    !d.empty())
                    return d;
            }
            return "";
        default: return to_text(a) == to_text(e) ? "" : path;
    }
}

std::string reals_text(const Vec& v) {
    json::Writer w;
    w.begin_array();
    for (const double x : v) w.real(x);
    w.end_array();
    return w.str();
}

std::string repeat(const std::string& item, std::size_t n) {
    std::string s = "[";
    for (std::size_t i = 0; i < n; ++i) s += (i ? "," : "") + item;
    return s + "]";
}

std::uint64_t bits(double x) {
    std::uint64_t u;
    std::memcpy(&u, &x, sizeof u);
    return u;
}

const std::string base_records = R"([
 {"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":100},
 {"sequence":2,"series_id":"A","valid_from":"2026-03-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-03-02T00:00:00Z","value":{"px":[1,"NaN"]}},
 {"sequence":3,"series_id":"A","valid_from":"2026-02-01T00:00:00Z","valid_to":"2026-03-01T00:00:00Z","knowledge_time":"2026-04-01T00:00:00Z","value":null},
 {"sequence":4,"series_id":"A","valid_from":"2026-01-15T00:00:00Z","valid_to":"2026-02-01T00:00:00Z","knowledge_time":"2026-04-02T00:00:00Z","value":0,"deleted":true}])";

std::string bt(const std::string& records, const std::string& k, const std::string& v, const std::string& series = "A") {
    return R"({"records":)" + records + R"(,"series_id":")" + series + R"(","knowledge_as_of":")" + k +
           R"(","valid_at":")" + v + R"("})";
}

std::string record(long long seq, const std::string& extra) {
    return R"({"sequence":)" + std::to_string(seq) +
           R"(,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","knowledge_time":"2026-01-02T00:00:00Z")" + extra +
           "}";
}

}  // namespace

#ifdef QF_REPO_DIR
TEST_CASE("stage_k goldens: every row, values and key order", "[stage_k]") {
    int total = 0;
    for (const char* suite : {"bt_k", "inc_k", "trig_k", "idr_k", "rich_k", "e1_k", "e2_k"}) {
        std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_k/" + suite + ".json", std::ios::binary);
        if (!f.good()) {
            CHECK(std::string(suite) == "e2_k");  // the two-error suite may not be on this branch yet
            continue;
        }
        std::stringstream s;
        s << f.rdbuf();
        const json::Value doc = json::parse(s.str()).value;
        int n = 0;
        for (const json::Value& c : doc.find("cases")->items) {
            ++n;
            const json::Value r = run(c.find("operation")->text, to_text(*c.find("inputs")));
            const json::Value& exp = *c.find("expected");
            INFO(c.find("case_id")->text << " -> " << to_text(r));
            REQUIRE(r.find("status")->text == exp.find("status")->text);
            if (exp.find("status")->text == "error")
                CHECK(r.find("error")->find("code")->text == exp.find("error_code")->text);
            else
                CHECK(differs(*r.find("outputs"), *exp.find("outputs"), "outputs").empty());
        }
        CHECK(n >= 5);
        total += n;
    }
    CHECK(total >= 59);
}
#endif

// ---- bitemporal store ----

TEST_CASE("bitemporal query: found, corrected, withdrawn, none, any value echoed", "[stage_k]") {
    json::Value r = ok("core.store.bitemporal_query", bt(base_records, "2026-03-05T00:00:00Z", "2026-03-10T00:00:00Z"));
    CHECK(r.find("status")->text == "FOUND");
    const json::Value& row = *r.find("row");
    CHECK(to_text(row) == R"({"sequence":2,"valid_from":"2026-03-01T00:00:00Z","valid_to":null,)"
                          R"("knowledge_time":"2026-03-02T00:00:00Z","value":{"px":[1,"NaN"]}})");
    // The correction known on 04-01 wins over February, and its null value is echoed.
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-04-01T00:00:00Z", "2026-02-10T00:00:00Z"));
    CHECK(to_text(*r.find("row")) == R"({"sequence":3,"valid_from":"2026-02-01T00:00:00Z","valid_to":)"
                                     R"("2026-03-01T00:00:00Z","knowledge_time":"2026-04-01T00:00:00Z","value":null})");
    // Before the correction is known, the first record answers (KR-4 on a hand case).
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-03-31T23:59:59Z", "2026-02-10T00:00:00Z"));
    CHECK(r.find("row")->find("sequence")->number == 1);
    // valid_to is exclusive: at 03-01 the correction does not hold, the March record does.
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-04-01T00:00:00Z", "2026-03-01T00:00:00Z"));
    CHECK(r.find("row")->find("sequence")->number == 2);
    // A deleted winner masks the older record (KR-2, KR-14).
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-04-02T00:00:00Z", "2026-01-20T00:00:00Z"));
    CHECK(r.find("status")->text == "WITHDRAWN");
    CHECK(r.find("row")->kind == json::Kind::Null);
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-04-02T00:00:00Z", "2025-12-31T00:00:00Z"));
    CHECK(r.find("status")->text == "NONE");
    CHECK(r.find("row")->kind == json::Kind::Null);
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-04-02T00:00:00Z", "2026-01-20T00:00:00Z", "B"));
    CHECK(r.find("status")->text == "NONE");
    // Knowledge before every record; an offset instant is read and written back in Z form.
    r = ok("core.store.bitemporal_query", bt(base_records, "2026-01-01T00:00:00Z", "2026-01-20T00:00:00Z"));
    CHECK(r.find("status")->text == "NONE");
    r = ok("core.store.bitemporal_query", bt("[" + record(1, R"(,"valid_to":null,"value":"x")") + "]",
                                             "2026-01-02T01:00:00+01:00", "2026-01-01T00:00:00Z"));
    CHECK(r.find("row")->find("value")->text == "x");
    // An empty log answers NONE.
    CHECK(ok("core.store.bitemporal_query", bt("[]", "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"))
              .find("status")
              ->text == "NONE");
}

TEST_CASE("bitemporal query: E_SCHEMA, structural E_INPUT, F-2 and the skipped general array limit", "[stage_k]") {
    const std::string op = "core.store.bitemporal_query";
    const std::string k = "2026-04-02T00:00:00Z", v = "2026-01-20T00:00:00Z";
    CHECK(code(op, R"({"records":{},"series_id":"A","knowledge_as_of":"2026-04-02T00:00:00Z","valid_at":"2026-01-20T00:00:00Z"})") == "E_SCHEMA");
    CHECK(code(op, R"({"series_id":"A","knowledge_as_of":"2026-04-02T00:00:00Z","valid_at":"2026-01-20T00:00:00Z"})") == "E_SCHEMA");
    CHECK(code(op, bt("[1]", k, v)) == "E_SCHEMA");
    CHECK(code(op, bt("[" + record(1, R"(,"value":1)") + "]", k, v)) == "E_SCHEMA");         // no valid_to key
    CHECK(code(op, bt("[" + record(1, R"(,"valid_to":null)") + "]", k, v)) == "E_SCHEMA");   // no value key
    CHECK(code(op, bt("[" + record(0, R"(,"valid_to":null,"value":1)") + "]", k, v)) == "E_SCHEMA");
    CHECK(code(op, bt("[" + record(1, R"(,"valid_to":"bad","value":1)") + "]", k, v)) == "E_SCHEMA");
    CHECK(code(op, bt("[" + record(1, R"(,"valid_to":null,"value":1,"deleted":3)") + "]", k, v)) == "E_SCHEMA");
    CHECK(code(op, bt(R"([{"sequence":1,"series_id":"","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}])", k, v)) == "E_SCHEMA");
    CHECK(code(op, bt(base_records, "yesterday", v)) == "E_SCHEMA");
    CHECK(code(op, R"({"records":[],"knowledge_as_of":"2026-04-02T00:00:00Z","valid_at":"2026-01-20T00:00:00Z"})") == "E_SCHEMA");
    // Log checks 2 to 4, each one before the finite rule's E_DOMAIN (HR-66).
    const std::string nan_first = record(1, R"(,"valid_to":null,"value":"NaN")");
    CHECK(code(op, bt("[" + nan_first + "," + record(1, R"(,"valid_to":null,"value":1)") + "]", k, v)) == "E_INPUT");
    CHECK(code(op, bt("[" + nan_first +
                          R"(,{"sequence":2,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-01T00:00:00Z","value":1}])",
                      k, v)) == "E_INPUT");
    CHECK(code(op, bt("[" + nan_first + "," + record(2, R"(,"valid_to":"2026-01-01T00:00:00Z","value":1)") + "]", k, v)) ==
          "E_INPUT");
    // F-38: a top-level token is a Real (E_DOMAIN); every token spelling.
    for (const char* t : {"NaN", "Infinity", "-Infinity"})
        CHECK(code(op, bt("[" + record(1, std::string(R"(,"valid_to":null,"value":")") + t + "\"") + "]", k, v)) ==
              "E_DOMAIN");
    // The general 100,000 array limit is skipped for stage K verbs: a large value is echoed.
    const std::string big = record(1, R"(,"valid_to":null,"value":)" + repeat("0", 100001));
    const json::Value r = ok(op, bt("[" + big + "]", "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"));
    CHECK(r.find("row")->find("value")->items.size() == 100001);
}

TEST_CASE("bitemporal library: status names, log checks and the record limit", "[stage_k]") {
    CHECK(sk::status_name(sk::BiStatus::Found) == "FOUND");
    CHECK(sk::status_name(sk::BiStatus::Withdrawn) == "WITHDRAWN");
    CHECK(sk::status_name(sk::BiStatus::None) == "NONE");
    const sk::BiRecord a{1, "A", t0, std::nullopt, t0, false};
    const sk::BiRecord d{2, "A", t0, std::nullopt, t0 + day, true};
    CHECK(sk::bitemporal_query({a, d}, "A", t0 + day, t0).status == sk::BiStatus::Withdrawn);
    const auto found = sk::bitemporal_query({a, d}, "A", t0, t0);
    CHECK(found.status == sk::BiStatus::Found);
    CHECK(found.winner == std::optional<std::size_t>(0));
    // KR-3: a stage A record is [event, event + 1 s); the end is excluded.
    const sk::BiRecord p{1, "A", t0, t0 + 1, t0, false};
    CHECK(sk::bitemporal_query({p}, "A", t0, t0 + 1).status == sk::BiStatus::None);
    CHECK(sk::bitemporal_query({p}, "A", t0, t0).status == sk::BiStatus::Found);
    CHECK(lib_code([&] { sk::check_log({d, a}); }) == "E_INPUT");
    CHECK(lib_code([&] { sk::check_log({sk::BiRecord{1, "A", t0, std::nullopt, t0 + day, false}, d}); }) == "none");
    CHECK(lib_code([&] { sk::check_log({sk::BiRecord{1, "A", t0, std::nullopt, t0 + 2 * day, false}, d}); }) ==
          "E_INPUT");
    CHECK(lib_code([&] { sk::check_log({sk::BiRecord{1, "A", t0, t0, t0, false}}); }) == "E_INPUT");
    std::vector<sk::BiRecord> log;
    log.reserve(sk::max_records + 1);
    for (std::size_t s = 1; s <= sk::max_records + 1; ++s) log.push_back({(long long)s, "A", t0, std::nullopt, t0, false});
    CHECK(lib_code([&] { (void)sk::bitemporal_query(log, "A", t0, t0); }) == "E_LIMIT");
    log.pop_back();
    CHECK(sk::bitemporal_query(log, "A", t0, t0).winner == std::optional<std::size_t>(sk::max_records - 1));
}

TEST_CASE("KR-4: a record known after K never changes a (K, V) answer, on 10,000 generated logs", "[stage_k]") {
    std::mt19937_64 rng(20261118);
    const auto uniform = [&](long long lo, long long hi) {
        return std::uniform_int_distribution<long long>(lo, hi)(rng);
    };
    long long checked = 0, cli_checked = 0;
    for (int trial = 0; trial < 10000; ++trial) {
        std::vector<sk::BiRecord> log;
        std::string records = "[";
        std::int64_t kt = 0;
        const long long n = uniform(0, 8);
        for (long long s = 1; s <= n; ++s) {
            kt += uniform(0, 3) * day;
            const std::int64_t vf = t0 + uniform(0, 20) * day;
            const std::optional<std::int64_t> vt =
                uniform(0, 9) < 3 ? std::nullopt : std::optional<std::int64_t>(vf + uniform(1, 10) * day);
            const std::string series = uniform(0, 1) ? "A" : "B";
            const bool deleted = uniform(0, 99) < 15;
            log.push_back({s, series, vf, vt, t0 + kt, deleted});
            records += std::string(s > 1 ? "," : "") + R"({"sequence":)" + std::to_string(s) + R"(,"series_id":")" +
                       series + R"(","valid_from":")" + quantforge::format_instant(vf) + R"(","valid_to":)" +
                       (vt ? "\"" + quantforge::format_instant(*vt) + "\"" : std::string("null")) +
                       R"(,"knowledge_time":")" + quantforge::format_instant(t0 + kt) + R"(","value":)" +
                       std::to_string(uniform(0, 99)) + (deleted ? R"(,"deleted":true})" : "}");
        }
        const std::int64_t k = t0 + uniform(0, kt / day + 2) * day + (uniform(0, 1) ? 43200 : 0);
        const std::int64_t later = std::max(t0 + kt, k + 1) + uniform(0, 2) * day;
        const std::string extra_series = uniform(0, 1) ? "A" : "B";
        const std::int64_t extra_from = t0 + uniform(0, 20) * day;
        std::vector<sk::BiRecord> longer = log;
        longer.push_back({n + 1, extra_series, extra_from, std::nullopt, later, false});
        for (int vd = 0; vd < 25; ++vd) {
            const std::int64_t v = t0 + vd * day;
            for (const char* series : {"A", "B"}) {
                const auto x = sk::bitemporal_query(log, series, k, v), y = sk::bitemporal_query(longer, series, k, v);
                REQUIRE(x.status == y.status);
                REQUIRE(x.winner == y.winner);
                ++checked;
            }
        }
        if (trial % 10 == 0) {  // byte for byte through the CLI on every tenth log
            const std::string with = records + std::string(n ? "," : "") + R"({"sequence":)" + std::to_string(n + 1) +
                                     R"(,"series_id":")" + extra_series + R"(","valid_from":")" +
                                     quantforge::format_instant(extra_from) + R"(","valid_to":null,"knowledge_time":")" +
                                     quantforge::format_instant(later) + R"(","value":-1}])";
            const std::string v = quantforge::format_instant(t0 + uniform(0, 24) * day);
            const std::string kk = quantforge::format_instant(k);
            const std::string a = run_text("core.store.bitemporal_query", bt(records + "]", kk, v));
            REQUIRE(a.find(R"("status":"ok")") != std::string::npos);
            REQUIRE(a == run_text("core.store.bitemporal_query", bt(with, kk, v)));
            ++cli_checked;
        }
    }
    CHECK(checked == 500000);
    CHECK(cli_checked == 1000);
}

// ---- par bootstrap and incremental update ----

TEST_CASE("par bootstrap: the recursion, the error order and the quote limit", "[stage_k]") {
    const Vec dfs = sk::par_annual({0.02, 0.025, 0.03});
    REQUIRE(dfs.size() == 3);
    CHECK(dfs[0] == 1.0 / 1.02);
    CHECK(dfs[1] == (1.0 - 0.025 * dfs[0]) / 1.025);
    CHECK(dfs[2] == (1.0 - 0.03 * (dfs[0] + dfs[1])) / 1.03);
    const std::string op = "curve.bootstrap.par_annual";
    CHECK(code(op, R"({"quotes":[]})") == "E_INPUT");
    CHECK(code(op, R"({"quotes":"x"})") == "E_SCHEMA");
    CHECK(code(op, R"({"quotes":[0.01,-1.0]})") == "E_DOMAIN");
    CHECK(code(op, R"({"quotes":[0.01,"NaN"]})") == "E_DOMAIN");
    CHECK(code(op, R"({"quotes":)" + repeat("0.01", 201) + "}") == "E_LIMIT");
    CHECK(code(op, R"({"quotes":[-2,)" + repeat("0.01", 200).substr(1) + "}") ==
          "E_DOMAIN");  // E_DOMAIN before E_LIMIT
    CHECK(ok(op, R"({"quotes":)" + repeat("0.01", 200) + "}").find("discount_factors")->items.size() == 200);
    CHECK(lib_code([] { (void)sk::par_annual({}); }) == "E_INPUT");
}

TEST_CASE("incremental update: copied pillars, the stale cache bit for bit, sign of zero, limits", "[stage_k]") {
    const Vec q = {0.02, 0.025, 0.03};
    const Vec prev = sk::par_annual(q);
    const sk::Update same = sk::incremental_update(q, prev, q);
    CHECK(!same.first_changed_index);
    CHECK(same.recomputed == 0);
    CHECK(same.discount_factors == prev);
    const sk::Update moved = sk::incremental_update(q, prev, {0.02, 0.026, 0.03});
    CHECK(moved.first_changed_index == std::optional<std::size_t>(1));
    CHECK(moved.recomputed == 2);
    CHECK(bits(moved.discount_factors[0]) == bits(prev[0]));
    CHECK(moved.discount_factors == sk::par_annual({0.02, 0.026, 0.03}));
    // One ulp off the bootstrap is a stale cache (value-dependent E_INPUT).
    Vec stale = prev;
    stale[2] = std::nextafter(stale[2], 2.0);
    CHECK(lib_code([&] { (void)sk::incremental_update(q, stale, q); }) == "E_INPUT");
    // The sign of zero counts: quotes 1 and 2 bootstrap to exactly 0.0, a cached -0.0 is stale.
    const Vec zq = {1.0, 2.0};
    const Vec zd = sk::par_annual(zq);
    REQUIRE(zd[1] == 0.0);
    REQUIRE(!std::signbit(zd[1]));
    CHECK(sk::incremental_update(zq, zd, zq).recomputed == 0);
    CHECK(lib_code([&] { (void)sk::incremental_update(zq, {zd[0], -0.0}, zq); }) == "E_INPUT");
    CHECK(lib_code([&] { (void)sk::incremental_update({}, {}, {}); }) == "E_INPUT");
    CHECK(lib_code([&] { (void)sk::incremental_update(q, {1.0, 1.0}, q); }) == "E_INPUT");
    CHECK(lib_code([&] { (void)sk::incremental_update(q, prev, {0.02, 0.025}); }) == "E_INPUT");
    CHECK(lib_code([&] { (void)sk::incremental_update({0.02, -1.5, 0.03}, prev, q); }) == "E_DOMAIN");
    CHECK(lib_code([&] { (void)sk::incremental_update(q, stale, {0.02, -1.5, 0.03}); }) == "E_DOMAIN");
    const std::string op = "curve.incremental.update";
    const std::string p = reals_text(prev);
    CHECK(code(op, R"({"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":)" + p +
                       R"(,"new_quotes":[0.02,"NaN"]})") == "E_INPUT");  // lengths before F-2
    CHECK(code(op, R"({"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":)" + reals_text(stale) +
                       R"(,"new_quotes":[0.02,"NaN",0.03]})") == "E_DOMAIN");  // F-2 before the stale cache
    CHECK(code(op, R"({"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":)" + p + "}") == "E_SCHEMA");
    const json::Value r = ok(op, R"({"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":)" + p +
                                     R"(,"new_quotes":[0.02,0.025,0.031]})");
    CHECK(r.find("first_changed_index")->number == 2);
    CHECK(r.find("recomputed")->number == 1);
    CHECK(ok(op, R"({"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":)" + p +
                     R"(,"new_quotes":[0.02,0.025,0.03]})")
              .find("first_changed_index")
              ->kind == json::Kind::Null);
    // E_LIMIT last: 201 pillars with a valid cache, and a stale cache wins over the limit.
    const Vec big_q(201, 0.01);
    const Vec big_d = [&] {
        Vec d;
        double acc = 0;
        for (const double s : big_q) {
            d.push_back((1.0 - s * acc) / (1.0 + s));
            acc += d.back();
        }
        return d;
    }();
    CHECK(lib_code([&] { (void)sk::incremental_update(big_q, big_d, big_q); }) == "E_LIMIT");
    Vec big_stale = big_d;
    big_stale[0] = 0.5;
    CHECK(lib_code([&] { (void)sk::incremental_update(big_q, big_stale, big_q); }) == "E_INPUT");
}

TEST_CASE("KR-5: incremental equals a full rebuild, copied pillars bit-identical, on 10,000 vectors", "[stage_k]") {
    std::mt19937_64 rng(20261118);
    std::uniform_real_distribution<double> level(-0.01, 0.08);
    std::normal_distribution<double> bump(0.0, 0.002);
    for (int trial = 0; trial < 10000; ++trial) {
        const std::size_t n = std::uniform_int_distribution<std::size_t>(1, 40)(rng);
        Vec old(n);
        for (double& x : old) x = level(rng);
        Vec now = old;
        const std::size_t changes = std::uniform_int_distribution<std::size_t>(1, std::min<std::size_t>(n, 4))(rng);
        for (std::size_t c = 0; c < changes; ++c) {
            const std::size_t j = std::uniform_int_distribution<std::size_t>(0, n - 1)(rng);
            now[j] = old[j] + bump(rng);
        }
        const Vec prev = sk::par_annual(old);
        const sk::Update up = sk::incremental_update(old, prev, now);
        const Vec full = sk::par_annual(now);
        const std::size_t j0 = up.first_changed_index.value_or(n);
        for (std::size_t i = 0; i < j0; ++i) REQUIRE(bits(up.discount_factors[i]) == bits(prev[i]));
        REQUIRE(up.discount_factors.size() == n);
        for (std::size_t i = 0; i < n; ++i) REQUIRE(bits(up.discount_factors[i]) == bits(full[i]));
        REQUIRE(up.recomputed == n - j0);
    }
}

// ---- recalibration trigger ----

TEST_CASE("trigger: strict threshold, sigma with exact sums, the error order and the limit", "[stage_k]") {
    const sk::Trigger t = sk::trigger_check({1.0, -1.0, 1.0, -1.0}, 100.0, 105.0, 1.0, 3.0);
    CHECK(t.fire);
    CHECK(t.sigma == std::sqrt(4.0 / 3.0));
    CHECK(t.threshold == 3.0 * t.sigma);
    CHECK(t.false_alarm_rate == std::erfc(3.0 / std::sqrt(2.0)));
    // KR-13: a move equal to the threshold does not fire.
    const Vec w = {0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0};
    CHECK_FALSE(sk::trigger_check(w, 0.0, 2.5, 1.0, 2.5).fire);
    CHECK(sk::trigger_check(w, 0.0, -2.5000001, 1.0, 2.5).fire);
    // The mean is a correctly rounded sum: a naive left-to-right sum loses the 1.0 against 1e16 (mean 0.5, not
    // 0.75), which moves sigma.
    const sk::Trigger e = sk::trigger_check({1e16, 1.0, -1e16, 2.0}, 0.0, 0.0, 1.0, 1.0);
    const double m = 0.75;
    const double dev[] = {1e16 - m, 1.0 - m, -1e16 - m, 2.0 - m};
    CHECK(e.sigma == std::sqrt(quantforge::research::fsum({dev[0] * dev[0], dev[1] * dev[1], dev[2] * dev[2],
                                                           dev[3] * dev[3]}) / 3.0));
    CHECK(lib_code([&] { (void)sk::trigger_check({1.0}, 0, 0, 1, 1); }) == "E_INPUT");
    CHECK(lib_code([&] { (void)sk::trigger_check(w, 0, 0, 1, 0); }) == "E_DOMAIN");
    CHECK(lib_code([&] { (void)sk::trigger_check(w, 0, 0, 0.5, 1); }) == "E_DOMAIN");
    CHECK(lib_code([&] { (void)sk::trigger_check({2.0, 2.0, 2.0}, 0, 0, 1, 1); }) == "E_DOMAIN");
    const std::string op = "calib.trigger.check";
    const std::string tail = R"(,"x_ref":100.0,"days_since":1.0,"k":3.0)";
    CHECK(code(op, R"({"changes":[1.0],"x_now":"NaN")" + tail + "}") == "E_INPUT");  // HR-66
    CHECK(code(op, R"({"changes":[1.0,-1.0],"x_now":"NaN")" + tail + "}") == "E_DOMAIN");
    CHECK(code(op, R"({"changes":[1.0,-1.0],"x_now":1.0,"x_ref":100.0,"days_since":1.0})") == "E_SCHEMA");
    const std::string many = repeat("1.0,-1.0", 50001);
    CHECK(code(op, R"({"changes":)" + many + R"(,"x_now":105.0)" + tail + "}") == "E_LIMIT");
    CHECK(code(op, R"({"changes":)" + many + R"(,"x_now":105.0,"x_ref":100.0,"days_since":1.0,"k":-1.0})") ==
          "E_DOMAIN");  // E_DOMAIN before E_LIMIT
    const json::Value r = ok(op, R"({"changes":[1.0,-1.0,1.0,-1.0],"x_now":102.0)" + tail + "}");
    CHECK(r.find("fire")->kind == json::Kind::Bool);
    CHECK_FALSE(r.find("fire")->boolean);
    CHECK(r.members[1].first == "sigma");
}

// ---- intraday delta-gamma ----

TEST_CASE("intraday: estimate, bound, label, the error order and the position limit", "[stage_k]") {
    const sk::ZeroPosition p{1e6, 5.0, 0.04};
    CHECK(sk::position_estimate(p, 0.0) == 0.0);
    CHECK(sk::position_bound(p, 0.0) == 0.0);
    // The bound uses min(y, y + h) and |N|: a short position has the same bound as the long one.
    const sk::ZeroPosition s{-1e6, 5.0, 0.04};
    CHECK(sk::position_bound(s, 0.01) == sk::position_bound(p, 0.01));
    CHECK(sk::position_bound(p, -0.01) > sk::position_bound(p, 0.01));
    CHECK(sk::position_estimate(s, 0.01) == -sk::position_estimate(p, 0.01));
    const sk::Intraday r = sk::delta_gamma_bound({p, s}, 0.01);
    CHECK(r.estimate_pnl == 0.0);
    CHECK(r.bound == 2 * sk::position_bound(p, 0.01));
    CHECK(std::fabs(sk::zero_revalue({p}, 0.01) - sk::position_estimate(p, 0.01)) <= sk::position_bound(p, 0.01));
    CHECK(lib_code([] { (void)sk::delta_gamma_bound({}, 0.01); }) == "E_INPUT");
    CHECK(lib_code([] { (void)sk::delta_gamma_bound({{1.0, 0.0, 0.0}}, 0.01); }) == "E_DOMAIN");
    std::vector<sk::ZeroPosition> big(sk::max_positions + 1, p);
    CHECK(lib_code([&] { (void)sk::delta_gamma_bound(big, 0.01); }) == "E_LIMIT");
    big.back().maturity = -1.0;
    CHECK(lib_code([&] { (void)sk::delta_gamma_bound(big, 0.01); }) == "E_DOMAIN");  // before E_LIMIT
    const std::string op = "risk.intraday.delta_gamma_bound";
    const std::string pos = R"({"notional":1000000.0,"maturity":5.0,"yield":0.04})";
    CHECK(code(op, R"({"positions":[],"shift":"NaN"})") == "E_INPUT");  // HR-66
    CHECK(code(op, R"({"positions":[)" + pos + R"(],"shift":"NaN"})") == "E_DOMAIN");
    CHECK(code(op, R"({"positions":[1],"shift":0.01})") == "E_SCHEMA");
    CHECK(code(op, R"({"positions":[{"notional":1.0,"maturity":5.0}],"shift":0.01})") == "E_SCHEMA");
    CHECK(code(op, R"({"positions":)" + repeat(pos, 100001) + R"(,"shift":0.01})") == "E_LIMIT");
    const json::Value out = ok(op, R"({"positions":[)" + pos + R"(],"shift":0.0})");
    CHECK(to_text(out) == R"({"estimate_pnl":0,"bound":0,"label":"latency-aware analytics on simulated data"})");
}

TEST_CASE("intraday acceptance: seeded 50-position book, 1,000 moves, |estimate - revaluation| <= bound",
          "[stage_k]") {
    NumpyRng rng(20261118);
    const auto uniform = [&](double lo, double hi) { return lo + (hi - lo) * rng.random(); };
    std::vector<sk::ZeroPosition> book;
    for (int i = 0; i < 50; ++i) {
        const double notional = uniform(-5e6, 5e6), maturity = uniform(0.1, 30.0);
        book.push_back({notional, maturity, uniform(-0.01, 0.08)});
    }
    double worst = 0.0;
    for (int i = 0; i < 1000; ++i) {
        const double h = uniform(-0.02, 0.02);
        const sk::Intraday r = sk::delta_gamma_bound(book, h);
        const double err = std::fabs(r.estimate_pnl - sk::zero_revalue(book, h));
        INFO("h=" << h << " err=" << err << " bound=" << r.bound);
        REQUIRE(err <= r.bound);
        worst = std::max(worst, err / r.bound);
    }
    CHECK(worst > 0.0);
    CHECK(worst <= 1.0);
}

// ---- Richardson guard ----

TEST_CASE("Richardson: OK, ORDER_MISMATCH, NON_MONOTONE, the error order", "[stage_k]") {
    CHECK(sk::status_name(sk::RichStatus::Ok) == "OK");
    CHECK(sk::status_name(sk::RichStatus::OrderMismatch) == "ORDER_MISMATCH");
    CHECK(sk::status_name(sk::RichStatus::NonMonotone) == "NON_MONOTONE");
    sk::Richardson r = sk::richardson_check({10.5, 10.125, 10.03125}, 2.0, 2.0);
    CHECK(r.status == sk::RichStatus::Ok);
    CHECK(r.observed_order == std::optional<double>(2.0));
    CHECK(r.extrapolated == std::optional<double>(10.0));
    // Decreasing differences of the other sign extrapolate too.
    r = sk::richardson_check({9.5, 9.875, 9.96875}, 2.0, 2.0);
    CHECK(r.status == sk::RichStatus::Ok);
    CHECK(r.extrapolated == std::optional<double>(10.0));
    r = sk::richardson_check({11.0, 10.5, 10.25}, 2.0, 2.0);
    CHECK(r.status == sk::RichStatus::OrderMismatch);
    CHECK(r.observed_order == std::optional<double>(1.0));
    CHECK(!r.extrapolated);
    // Exactly 0.5 away is still within (<=).
    CHECK(sk::richardson_check({11.0, 10.5, 10.25}, 2.0, 1.5).status == sk::RichStatus::Ok);
    for (const Vec& v : {Vec{1.0, 1.0, 0.5}, Vec{1.0, 0.5, 0.5}, Vec{1.0, 0.5, 0.75}, Vec{0.5, 1.0, 0.75}}) {
        r = sk::richardson_check(v, 2.0, 2.0);
        CHECK(r.status == sk::RichStatus::NonMonotone);
        CHECK(!r.observed_order);
        CHECK(!r.extrapolated);
    }
    CHECK(lib_code([] { (void)sk::richardson_check({1.0, 2.0}, 2.0, 2.0); }) == "E_INPUT");
    CHECK(lib_code([] { (void)sk::richardson_check({1.0, 2.0, 3.0}, 1.0, 2.0); }) == "E_DOMAIN");
    CHECK(lib_code([] { (void)sk::richardson_check({1.0, 2.0, 3.0}, 2.0, 0.0); }) == "E_DOMAIN");
    const std::string op = "num.richardson.check";
    CHECK(code(op, R"({"values":[1.0,"NaN"],"ratio":2.0,"assumed_order":2.0})") == "E_INPUT");  // HR-66
    CHECK(code(op, R"({"values":[1.0,"NaN",3.0],"ratio":0.5,"assumed_order":2.0})") == "E_DOMAIN");
    CHECK(code(op, R"({"values":[1.0,2.0,3.0],"ratio":2.0})") == "E_SCHEMA");
    const json::Value out = ok(op, R"({"values":[98464.0,93700.0,96435.0],"ratio":2.0,"assumed_order":2.0})");
    CHECK(to_text(out) == R"({"status":"NON_MONOTONE","observed_order":null,"extrapolated":null})");
}
