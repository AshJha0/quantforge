// Stage H H-4b and H-16: every mest_h and venue_h golden row through the CLI (values to 1e-12 relative, 1e-15
// absolute, key order checked), the error paths the goldens miss, the numpy default_rng port against numpy's own
// draws, and the seven planted-recovery tests with the 200-seed coverage run of micro-estimators.md (HR-70, HR-71).
// As the streams are numpy's, the misses must be the Python and Java builds' own.
#include <catch2/catch_test_macros.hpp>
#include <array>
#include <cmath>
#include <fstream>
#include <functional>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "numpy_rng.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/micro_est.hpp"
#include "quantforge/core/research.hpp"

namespace {

namespace json = quantforge::json;
namespace mest = quantforge::micro_est;
using quantforge::test::NumpyRng;

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

json::Value run(const std::string& op, const std::string& inputs) {
    return json::parse(quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                                 R"(","inputs":)" + inputs + "}")
                           .json)
        .value;
}

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

}  // namespace

#ifdef QF_REPO_DIR
TEST_CASE("mest_h and venue_h goldens: every row, values and key order", "[micro_est]") {
    for (const char* suite : {"mest_h", "venue_h"}) {
        std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/stage_h/" + suite + ".json", std::ios::binary);
        REQUIRE(f.good());
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
        CHECK(n >= 8);
    }
}
#endif

TEST_CASE("micro.est schema, non-finite and error order (HR-75 as amended)", "[micro_est]") {
    CHECK(code("micro.est.arrival_rate", R"({"count":1.5,"window":1.0})") == "E_SCHEMA");
    CHECK(code("micro.est.cancel_rate", R"({"orders":[{"lifetime":1.0,"outcome":"EXPIRE"}]})") == "E_SCHEMA");
    CHECK(code("micro.est.cancel_rate", R"({"orders":[3]})") == "E_SCHEMA");
    CHECK(code("micro.est.passive_vs_aggressive", R"({"passive":[1.0,"Infinity"],"aggressive":[1.0,2.0]})") ==
          "E_DOMAIN");
    CHECK(code("micro.est.arrival_rate", R"({"count":-1,"window":1.0})") == "E_DOMAIN");
    const json::Value zero = ok("micro.est.arrival_rate", R"({"count":0,"window":2.0})");
    CHECK(zero.find("lambda")->number == 0.0);
    CHECK(zero.find("se")->number == 0.0);
    CHECK(code("micro.est.regime_impact", R"({"regimes":{"calm":3}})") == "E_SCHEMA");
    CHECK(code("micro.est.regime_impact", R"({"regimes":[]})") == "E_SCHEMA");

    CHECK(code("micro.est.cancel_rate", R"({"orders":[{"lifetime":0.0,"outcome":"CANCEL"}]})") == "E_DOMAIN");
    CHECK(code("micro.est.cancel_rate", R"({"orders":[{"lifetime":1.0,"outcome":"FILL"}]})") == "E_INPUT");
    CHECK(code("micro.est.resilience", R"({"s_inf":1.0,"points":[{"t":0,"s":2.0},{"t":0,"s":3.0},{"t":0,"s":4.0}]})") ==
          "E_INPUT");
    CHECK(code("micro.est.resilience", R"({"s_inf":1.0,"points":[{"t":0,"s":2.0},{"t":1,"s":0.5},{"t":2,"s":4.0}]})") ==
          "E_DOMAIN");
    CHECK(code("micro.est.liquidity_decay", R"({"levels":[{"k":0,"depth":1.0},{"k":1,"depth":0.0},{"k":2,"depth":1.0}]})") ==
          "E_DOMAIN");
    CHECK(code("micro.est.liquidity_decay", R"({"levels":[{"k":0,"depth":1.0},{"k":1,"depth":0.0}]})") == "E_INPUT");
    CHECK(code("micro.est.liquidity_decay", R"({"levels":[{"k":1,"depth":1.0},{"k":1,"depth":2.0},{"k":1,"depth":3.0}]})") ==
          "E_INPUT");
    CHECK(code("micro.est.adverse_selection", R"({"x":[1.0],"y":[1.0,2.0]})") == "E_INPUT");
    CHECK(code("micro.est.adverse_selection", R"({"x":[0.0,0.0],"y":[1.0,2.0]})") == "E_INPUT");
    const std::string good = R"({"x":[1.0,2.0],"y":[1.0,2.0]})";
    CHECK(code("micro.est.regime_impact", R"({"regimes":{"calm":)" + good + "}}") == "E_INPUT");
    CHECK(code("micro.est.regime_impact", R"({"regimes":{"stressed":)" + good + "}}") == "E_INPUT");
    CHECK(code("micro.est.regime_impact", R"({"regimes":{"calm":)" + good + R"(,"stressed":{"x":[1.0],"y":[1.0]}}})") ==
          "E_INPUT");
    CHECK(code("micro.est.regime_impact",
               R"({"regimes":{"calm":{"x":[1.0,-1.0],"y":[1.0,1.0]},"stressed":)" + good + "}}") == "E_DOMAIN");
    CHECK(code("micro.est.passive_vs_aggressive", R"({"passive":[1.0,2.0],"aggressive":[1.0]})") == "E_INPUT");
    CHECK(code("micro.est.passive_vs_aggressive", R"({"passive":[1.0],"aggressive":[1.0,2.0]})") == "E_INPUT");
    const json::Value r =
        ok("micro.est.regime_impact", R"({"regimes":{"stressed":)" + good + R"(,"calm":)" + good + R"(,"B":)" + good +
                                          R"(,"é":)" + good + "}}");
    const json::Value& regs = *r.find("regimes");
    REQUIRE(regs.members.size() == 4);
    CHECK(regs.members[0].first == "B");
    CHECK(regs.members[1].first == "calm");
    CHECK(regs.members[2].first == "stressed");
    CHECK(regs.members[3].first == "\xc3\xa9");
    CHECK(r.find("ratio")->number == 1.0);
}

namespace {
const std::string mids =
    R"([{"t":0.0,"mid":100.0},{"t":1.0,"mid":100.02},{"t":5.0,"mid":100.05},{"t":10.0,"mid":99.98}])";
const std::string fills = R"([{"venue":"A","side":"BUY","quantity":100.0,"price":100.01,"t":0.0},)"
                          R"({"venue":"A","side":"SELL","quantity":200.0,"price":100.03,"t":1.0},)"
                          R"({"venue":"B","side":"BUY","quantity":300.0,"price":100.0,"t":1.0}])";
const std::string orders = R"([{"venue":"A","sent":500.0,"filled":300.0},{"venue":"B","sent":300.0,"filled":300.0}])";

std::string venue(const std::string& m, const std::string& f, const std::string& o, const std::string& h) {
    return R"({"mids":)" + m + R"(,"fills":)" + f + R"(,"orders":)" + o + R"(,"horizons":)" + h + "}";
}
}  // namespace

TEST_CASE("exec.venue.analytics errors and edge cases", "[micro_est]") {
    const std::string op = "exec.venue.analytics";
    CHECK(code(op, venue(R"([{"t":1.0,"mid":100.0},{"t":0.0,"mid":100.0}])", fills, orders, "[5.0]")) == "E_INPUT");
    CHECK(code(op, venue(R"([{"t":1.0,"mid":100.0},{"t":1.0,"mid":100.0}])", fills, orders, "[5.0]")) == "E_INPUT");
    CHECK(code(op, venue(R"([{"t":0.0,"mid":0.0}])", fills, orders, "[5.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(mids, R"([{"venue":"A","side":"BUY","quantity":100.0,"price":0.0,"t":0.0}])", orders,
                         "[5.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(mids, R"([{"venue":"A","side":"BUY","quantity":-1.0,"price":1.0,"t":0.0}])", orders,
                         "[5.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(mids, fills, R"([{"venue":"A","sent":0.0,"filled":0.0}])", "[5.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(mids, fills, R"([{"venue":"A","sent":1.0,"filled":-1.0}])", "[5.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(mids, fills, R"([{"venue":"A","sent":1.0,"filled":2.0}])", "[5.0]")) == "E_INPUT");
    // structural E_INPUT outranks E_DOMAIN (HR-66)
    CHECK(code(op, venue(R"([{"t":0.0,"mid":0.0}])", fills, R"([{"venue":"A","sent":1.0,"filled":2.0}])", "[5.0]")) ==
          "E_INPUT");
    CHECK(code(op, venue(mids, fills, orders, "[-1.0]")) == "E_DOMAIN");
    CHECK(code(op, venue(R"([{"t":2.0,"mid":100.0}])", fills, orders, "[0.0]")) == "E_INPUT");
    CHECK(code(op, venue(mids, R"([{"venue":"A","side":"HOLD","quantity":1.0,"price":1.0,"t":0.0}])", orders,
                         "[5.0]")) == "E_SCHEMA");
    CHECK(code(op, venue(mids, fills, orders, R"([5.0,"NaN"])")) == "E_DOMAIN");
    const json::Value empty = ok(op, venue(mids, "[]", "[]", "[5.0]"));
    CHECK(empty.find("fill_rates")->members.empty());
    CHECK(empty.find("markouts")->items.empty());

    const json::Value r = ok(op, venue(R"([{"t":0.0,"mid":101.0}])",
                                       R"([{"venue":"A","side":"BUY","quantity":1.0,"price":100.0,"t":0.0}])",
                                       R"([{"venue":"A","sent":2.0,"filled":1.0}])", "[0.0]"));
    CHECK(r.find("fill_rates")->find("A")->number == 0.5);
    const json::Value& m = r.find("markouts")->items.at(0);
    CHECK(m.find("venue")->text == "A");
    CHECK(m.find("markout")->number == 1.0);
    CHECK(m.find("markout_bps")->number == 100.0);
    CHECK(m.find("toxicity")->number == 0.0);
}

TEST_CASE("exec.venue.analytics: mirrored prices and sides give the same markouts", "[micro_est]") {
    const std::string mids2 =
        R"([{"t":0.0,"mid":140.0},{"t":1.0,"mid":139.98},{"t":5.0,"mid":139.95},{"t":10.0,"mid":140.02}])";
    const std::string fills2 = R"([{"venue":"A","side":"SELL","quantity":100.0,"price":139.99,"t":0.0},)"
                               R"({"venue":"A","side":"BUY","quantity":200.0,"price":139.97,"t":1.0},)"
                               R"({"venue":"B","side":"SELL","quantity":300.0,"price":140.0,"t":1.0}])";
    for (const char* h : {"0.0", "0.5", "1.0", "4.0", "5.0", "9.0", "10.0", "100.0"}) {
        const json::Value a = ok("exec.venue.analytics", venue(mids, fills, orders, std::string("[") + h + "]"));
        const json::Value b = ok("exec.venue.analytics", venue(mids2, fills2, orders, std::string("[") + h + "]"));
        const auto& ra = a.find("markouts")->items;
        const auto& rb = b.find("markouts")->items;
        REQUIRE(ra.size() == 2);
        REQUIRE(rb.size() == 2);
        for (std::size_t i = 0; i < ra.size(); ++i) {
            const double tox = ra[i].find("toxicity")->number, mk = ra[i].find("markout")->number;
            CHECK(tox >= 0);
            CHECK(tox <= 1);
            CHECK((mk == 0 || std::signbit(mk) == std::signbit(ra[i].find("markout_bps")->number)));
            CHECK(std::fabs(mk - rb[i].find("markout")->number) <= 1e-12);
        }
    }
}

TEST_CASE("exact ratio is correctly rounded (Python float(Fraction))", "[micro_est]") {
    CHECK(mest::venue::exact_ratio("1", "3") == 1.0 / 3.0);
    CHECK(mest::venue::exact_ratio("-2", "3") == -2.0 / 3.0);
    CHECK(mest::venue::exact_ratio("0", "7") == 0.0);
    CHECK(mest::venue::exact_ratio("0.1", "1") == 0.1);
    CHECK(mest::venue::exact_ratio("123456789012345678901234567890", "1e10") == 12345678901234567890.0);
    // 2^53 + 1 is a tie: round to even
    CHECK(mest::venue::exact_ratio("9007199254740993", "1") == 9007199254740992.0);
    CHECK(mest::venue::exact_ratio("9007199254740995", "1") == 9007199254740996.0);
    // just above the tie rounds up
    CHECK(mest::venue::exact_ratio("90071992547409930000000000001", "10000000000000") == 9007199254740994.0);
}

// ---- the numpy port (HR-71) against values numpy printed (as java25 NumpyRngTest fixes them) ----

TEST_CASE("numpy default_rng port: draw-for-draw equality with numpy", "[micro_est]") {
    struct Want {
        long long seed;
        std::uint64_t raw;
        double random;
        long long s, q;
        double n, e;
        long long p1, p2;
    };
    const Want want[] = {
        {20261119, 1684628720167899607ULL, 0.29071362979956594, -1, 58, -0.06724342672535288, 2.7156780461168064, 9010,
         9077},
        {70000, 6024274701318062869ULL, 0.4008755151155149, 1, 93, 0.01077855715010661, 6.522768631588426, 8887, 9109},
        {70123, 7416423396052956773ULL, 0.11062102713738753, -1, 39, 0.017782774812657554, 0.7215412971042601, 8924,
         9023},
    };
    const std::array<long long, 2> signs = {-1, 1};
    for (const Want& w : want) {
        INFO(w.seed);
        NumpyRng r(w.seed);
        CHECK(r.next_u64() == w.raw);
        CHECK(r.random() == w.random);
        CHECK(r.choice(signs) == w.s);
        CHECK(r.integers(1, 101) == w.q);
        CHECK(r.normal(0, 0.05) == w.n);
        CHECK(r.exponential(2.0) == w.e);
        for (int i = 1; i < 3000; ++i) {
            r.choice(signs);
            r.integers(1, 101);
            r.normal(0, 0.05);
            r.exponential(2.0);
        }
        CHECK(r.poisson(9000.0) == w.p1);
        CHECK(r.poisson(9000.0) == w.p2);
    }
}

TEST_CASE("numpy default_rng port: ziggurat checksum and guards", "[micro_est]") {
    NumpyRng r(70000);
    std::vector<double> v(200000);
    for (std::size_t i = 0; i < 100000; ++i) v[i] = r.standard_normal();
    for (std::size_t i = 100000; i < 200000; ++i) v[i] = r.standard_exponential();
    CHECK(quantforge::research::fsum(v) == 100216.18527592497);  // math.fsum in numpy's run
    CHECK(v[199999] == 1.4622581364761265);
    CHECK_THROWS_AS(NumpyRng(-1), std::invalid_argument);
    CHECK_THROWS_AS(NumpyRng(1LL << 32), std::invalid_argument);
    CHECK_THROWS_AS(NumpyRng(1).poisson(5.0), std::invalid_argument);
    CHECK(NumpyRng(1).integers(7, 8) == 7);
    CHECK(NumpyRng::loggam(1.0) == 0.0);
    CHECK(NumpyRng::loggam(2.0) == 0.0);
    CHECK(std::fabs(NumpyRng::loggam(4.0) - std::log(6.0)) <= 1e-14);
}

// ---- planted recovery (micro-estimators.md, HR-70, HR-71) ----

namespace {

bool hit(const mest::Estimate& e, double truth) { return std::fabs(e.value - truth) <= 3 * e.se; }

mest::Sample impact(NumpyRng& rng, double lam, int n) {
    static constexpr std::array<long long, 2> signs = {-1, 1};
    mest::Sample s;
    for (int i = 0; i < n; ++i) {
        const auto sg = static_cast<double>(rng.choice(signs));
        const auto q = static_cast<double>(rng.integers(1, 101));
        const double e = rng.normal(0, 0.05);
        s.x.push_back(sg * q);
        s.y.push_back(lam * sg * q + e);
    }
    return s;
}

bool r1(NumpyRng& rng) {
    const double lam = 2.5, t = 3600.0;
    return hit(mest::arrival_rate(rng.poisson(lam * t), t), lam);
}

bool r2(NumpyRng& rng) {
    const double theta = 0.4, fill = 0.1;
    std::vector<mest::Order> rows(5000);
    for (auto& o : rows) {
        const double life = rng.exponential(1 / (theta + fill));
        o = {life, rng.random() < theta / (theta + fill)};
    }
    return hit(mest::cancel_rate(rows), theta);
}

bool r3(NumpyRng& rng) {
    const double kappa = 0.3, s0 = 5.0, sinf = 1.0;
    std::vector<std::pair<double, double>> pts;
    for (int t = 0; t <= 20; ++t)
        pts.emplace_back(t, sinf + (s0 - sinf) * std::exp(-kappa * t) * std::exp(rng.normal(0, 0.05)));
    return hit(mest::resilience(sinf, pts), kappa);
}

bool r4(NumpyRng& rng) {
    const double alpha = 0.15, d0 = 1000.0;
    std::vector<std::pair<double, double>> lv;
    for (int k = 0; k <= 30; ++k) lv.emplace_back(k, d0 * std::exp(-alpha * k) * std::exp(rng.normal(0, 0.1)));
    return hit(mest::liquidity_decay(lv), alpha);
}

bool r5(NumpyRng& rng) {
    const mest::Sample s = impact(rng, 0.002, 2000);
    return hit(mest::adverse_selection(s.x, s.y), 0.002);
}

bool r6(NumpyRng& rng) {
    std::map<std::string, mest::Sample, mest::CodePointLess> m;
    m["calm"] = impact(rng, 0.001, 1000);
    m["stressed"] = impact(rng, 0.004, 1000);
    const auto r = mest::regime_impact(m).regimes;
    return hit(r[0].second, 0.001) && hit(r[1].second, 0.004);
}

bool r7(NumpyRng& rng) {
    std::vector<double> passive(1000), aggressive(1000);
    for (double& x : passive) x = rng.normal(-1, 2);
    for (double& x : aggressive) x = rng.normal(1.5, 2);
    return hit(mest::passive_vs_aggressive(passive, aggressive), 2.5);
}

const std::array<std::function<bool(NumpyRng&)>, 7> recovery = {r1, r2, r3, r4, r5, r6, r7};

}  // namespace

TEST_CASE("planted recovery: seeds 20261118 + j within 3 SE", "[micro_est]") {
    for (int j = 1; j <= 7; ++j) {
        INFO("test " << j);
        NumpyRng rng(20261118 + j);
        CHECK(recovery[static_cast<std::size_t>(j - 1)](rng));
    }
}

TEST_CASE("planted recovery: 200-seed coverage misses equal the Python and Java builds'", "[micro_est]") {
    // python/tests/test_stage_h_micro.py and java25 MicroEstimatorsRecoveryTest: 70075 (1), 70190 (4), 70028 (7)
    const std::array<std::vector<int>, 7> expected = {
        std::vector<int>{70075}, {}, {}, {70190}, {}, {}, {70028}};
    for (std::size_t j = 0; j < 7; ++j) {
        std::vector<int> misses;
        for (int s = 70000; s < 70200; ++s) {
            NumpyRng rng(s);
            if (!recovery[j](rng)) misses.push_back(s);
        }
        INFO("test " << j + 1);
        CHECK(misses.size() <= 4);
        CHECK(misses == expected[j]);
    }
}
