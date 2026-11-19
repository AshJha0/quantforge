// K-8 CN_RANNACHER_SMOOTHED (KR-8 as revised by KR-18): a port of java25 BermudanK8Test and the k8 tests of
// python/tests/test_stage_k_w1.py. The shared goldens k8_k through the CLI (values at 1e-9 of the row scale, codes
// exactly), the Python build's values on a small grid, the tangent ladder against its own bumps at 1e-8 relative on
// the same grid (acceptance 5), the smoothing of spec step 5, exact zeros, time order 2 and space error smooth at
// second order, and acceptance 3 (201/401/801), which runs only with QF_K8_ACCEPTANCE=1 against
// oracle/K8_ACCEPTANCE_W2.json.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/bermudan_k8.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/stage_k.hpp"

namespace {

namespace json = quantforge::json;
namespace bk8 = quantforge::bermudan_k8;
namespace sk = quantforge::stage_k;
using Vec = std::vector<double>;

#ifdef QF_REPO_DIR
json::Value load(const std::string& rel) {
    std::ifstream f(std::string(QF_REPO_DIR) + "/" + rel, std::ios::binary);
    REQUIRE(f.good());
    std::stringstream s;
    s << f.rdbuf();
    return json::parse(s.str()).value;
}

Vec reals(const json::Value& v) {
    Vec out;
    for (const json::Value& x : v.items) out.push_back(x.number);
    return out;
}

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

struct Case {
    Vec times, dfs;
    double a, sigma;
    Vec pay;
    double rate;
    bool payer;
    double notional;
    Vec exercise;
    double width;
};

Case ladder_case(std::size_t index) {
    const json::Value doc = load("datasets/golden/stage_g/aadladder_g.json");
    const json::Value& i = *doc.find("cases")->items.at(index).find("inputs");
    const json::Value& c = *i.find("curve");
    return {reals(*c.find("times")),       reals(*c.find("discount_factors")), i.find("mean_reversion")->number,
            i.find("sigma")->number,       reals(*i.find("payment_times")),    i.find("fixed_rate")->number,
            i.find("swaption_type")->text == "PAYER", i.find("notional")->number, reals(*i.find("exercise_times")),
            i.find("grid")->find("width")->number};
}

bk8::Ladder ladder(const Case& c, long long nx, long long spy) {
    return bk8::ladder(c.times, c.dfs, c.a, c.sigma, c.pay, c.rate, c.payer, c.notional, c.exercise, nx, spy, c.width);
}

double price(const Case& c, const Vec& dfs, double a, double s, long long nx, long long spy) {
    return bk8::price(c.times, dfs, a, s, c.pay, c.rate, c.payer, c.notional, c.exercise, nx, spy, c.width);
}

Vec row(const bk8::Ladder& l) {
    Vec r{l.price};
    r.insert(r.end(), l.d_discount_factors.begin(), l.d_discount_factors.end());
    r.push_back(l.d_mean_reversion);
    r.push_back(l.d_sigma);
    return r;
}

double max_abs(const Vec& v) {
    double m = 0;
    for (double x : v) m = std::max(m, std::abs(x));
    return m;
}

double bump(const std::function<double(double)>& f, double x, double step) {
    const double d1 = (f(x + step) - f(x - step)) / (2 * step);
    const double d2 = (f(x + step / 2) - f(x - step / 2)) / step;
    return (4 * d2 - d1) / 3;
}

// Python bermudan_k8.bermudan_ladder (spec 0.2.0) on the aadladder_g-0001..0003 inputs, grid 41/20 (2026-11-19);
// the same rows as BermudanK8Test.PYTHON_41_20.
const Vec python_41_20[3] = {
    {22287.53461841767, 0.0, 211358.63631459567, 162687.8910175668, 139306.3793174654, -231877.5339021703,
     -347142.401546213, 0.0, 0.0, 0.0, 0.0, -50599.24923667921, 2228993.5084961606},
    {14219.03198224864, 0.0, 90811.61296827145, 131329.76588168432, 150157.18125350963, -142268.28751103743,
     -277083.57865698315, 0.0, 0.0, 0.0, 0.0, -49394.77704993134, 2086503.2182632545},
    {13716.96718870294, 0.0, -85323.69457718439, -129308.55315145763, -138026.26813797135, 154928.16366504165,
     276491.2939629992, 0.0, 0.0, 0.0, 0.0, -48789.9281811259, 2034661.6889618998},
};
#endif

}  // namespace

#ifdef QF_REPO_DIR
TEST_CASE("k8_k goldens: values at 1e-9 of the row scale, codes exactly", "[k8]") {
    const json::Value doc = load("datasets/golden/stage_k/k8_k.json");
    int rows = 0;
    for (const json::Value& c : doc.find("cases")->items) {
        ++rows;
        const json::Value r = run(c.find("operation")->text, to_text(*c.find("inputs")));
        const json::Value& want = *c.find("expected");
        INFO(c.find("case_id")->text << " -> " << to_text(r));
        REQUIRE(r.find("status")->text == want.find("status")->text);
        if (want.find("status")->text == "error") {
            CHECK(r.find("error")->find("code")->text == want.find("error_code")->text);
            continue;
        }
        const json::Value& w = *want.find("outputs");
        const json::Value& g = *r.find("outputs");
        REQUIRE(w.members.size() == g.members.size());
        for (std::size_t i = 0; i < w.members.size(); ++i) CHECK(w.members[i].first == g.members[i].first);
        const double p = w.find("price")->number;
        CHECK(std::abs(g.find("price")->number - p) <= 1e-9 * std::abs(p));
        if (const json::Value* wl = w.find("d_price_d_discount_factors")) {
            const Vec want_d = reals(*wl), got_d = reals(*g.find("d_price_d_discount_factors"));
            REQUIRE(want_d.size() == got_d.size());
            const double scale = max_abs(want_d);
            for (std::size_t i = 0; i < want_d.size(); ++i) CHECK(std::abs(want_d[i] - got_d[i]) <= 1e-9 * scale);
            for (const char* key : {"d_price_d_mean_reversion", "d_price_d_sigma"}) {
                const double x = w.find(key)->number;
                CHECK(std::abs(g.find(key)->number - x) <= 1e-9 * std::abs(x));
            }
        }
    }
    CHECK(rows == 14);
}

TEST_CASE("k8: the Python build's values on 41/20 at 1e-10 of the row scale", "[k8]") {
    for (std::size_t k = 0; k < 3; ++k) {
        const Case c = ladder_case(k);
        const Vec got = row(ladder(c, 41, 20));
        const double scale = max_abs(python_41_20[k]);
        REQUIRE(got.size() == python_41_20[k].size());
        for (std::size_t j = 0; j < got.size(); ++j) {
            INFO(k << "/" << j << ": " << got[j]);
            CHECK(std::abs(got[j] - python_41_20[k][j]) <= 1e-10 * scale);
        }
        CHECK(std::abs(got[0] - price(c, c.dfs, c.a, c.sigma, 41, 20)) <= 1e-9 * std::abs(got[0]));
    }
}

TEST_CASE("k8: the ladder equals its own Richardson bumps to 1e-8 on the same grid (acceptance 5)", "[k8]") {
    const Case c = ladder_case(1);
    const bk8::Ladder l = ladder(c, 41, 20);
    const double scale = max_abs(l.d_discount_factors);
    for (std::size_t j = 0; j < c.dfs.size(); ++j) {
        const double got = bump(
            [&](double x) {
                Vec d = c.dfs;
                d[j] = x;
                return price(c, d, c.a, c.sigma, 41, 20);
            },
            c.dfs[j], 1e-4 * c.dfs[j]);
        INFO(j << ": " << got);
        CHECK(std::abs(got - l.d_discount_factors[j]) <= 1e-8 * scale);
    }
    const double ga = bump([&](double x) { return price(c, c.dfs, x, c.sigma, 41, 20); }, c.a, 1e-3 * c.a);
    CHECK(std::abs(ga - l.d_mean_reversion) <= 1e-8 * std::abs(ga));
    const double gs = bump([&](double x) { return price(c, c.dfs, c.a, x, 41, 20); }, c.sigma, 1e-3 * c.sigma);
    CHECK(std::abs(gs - l.d_sigma) <= 1e-8 * std::abs(gs));
}

TEST_CASE("k8: curve nodes the price does not depend on give exact zeros (KR-18 a)", "[k8]") {
    for (std::size_t index = 0; index < 3; ++index) {
        const Vec d = ladder(ladder_case(index), 41, 20).d_discount_factors;
        for (std::size_t k = 0; k < d.size(); ++k) {
            INFO(index << "/" << k);
            CHECK((k == 0 || k >= 6) == (d[k] == 0.0));
        }
    }
}

TEST_CASE("k8: time-only refinement gives observed order 2 on the price and every entry", "[k8]") {
    const Case c = ladder_case(0);
    const Vec r10 = row(ladder(c, 41, 10)), r20 = row(ladder(c, 41, 20)), r40 = row(ladder(c, 41, 40));
    const std::size_t entries[] = {0, 2, 3, 4, 5, 6, 11, 12};
    for (std::size_t k : entries) {
        const sk::Richardson rc = sk::richardson_check({r10[k], r20[k], r40[k]}, 2.0, 2.0);
        INFO("entry " << k);
        CHECK(rc.status == sk::RichStatus::Ok);
        REQUIRE(rc.observed_order.has_value());
        CHECK(std::abs(*rc.observed_order - 2.0) <= 0.1);
    }
}

TEST_CASE("k8: space error times cells^2 is the same on non-nested grids to 10%", "[k8]") {
    const Case c = ladder_case(0);
    const Vec ref = row(ladder(c, 321, 20));
    const long long grids[] = {61, 81, 101, 131, 161};
    const std::size_t judged[] = {0, 2, 3, 4, 5, 6, 11, 12};
    std::vector<Vec> scaled;
    for (long long nx : grids) {
        const Vec r = row(ladder(c, nx, 20));
        const double c2 = static_cast<double>((nx - 1) * (nx - 1));
        Vec s;
        for (std::size_t q : judged) s.push_back((r[q] - ref[q]) * c2 / (1 - c2 / (320.0 * 320.0)));
        scaled.push_back(s);
    }
    for (std::size_t q = 0; q < std::size(judged); ++q) {
        double mean = 0;
        for (const Vec& s : scaled) mean += s[q] / static_cast<double>(scaled.size());
        for (const Vec& s : scaled) {
            INFO("entry " << judged[q]);
            CHECK(std::abs(s[q] - mean) <= 0.1 * std::abs(mean));
        }
    }
}

TEST_CASE("k8: acceptance 3 on 201/401/801 (QF_K8_ACCEPTANCE=1 only)", "[k8][acceptance]") {
    const char* flag = std::getenv("QF_K8_ACCEPTANCE");
    if (!flag || std::string(flag) != "1") return;
    const json::Value record = load("oracle/K8_ACCEPTANCE_W2.json");
    const json::Value& py_values = *record.find("values");
    std::string bad;
    double worst_gap = 0;
    const long long grids[3][2] = {{201, 100}, {401, 200}, {801, 400}};
    for (std::size_t index = 0; index < 3; ++index) {
        const Case c = ladder_case(index);
        std::vector<Vec> rows;
        const json::Value& py = *py_values.find("aadladder_g-000" + std::to_string(index + 1));
        for (const auto& g : grids) {
            const Vec r = row(ladder(c, g[0], g[1]));
            const Vec p = reals(*py.find(std::to_string(g[0]) + "/" + std::to_string(g[1])));
            const double scale = max_abs(p);
            for (std::size_t k = 0; k < r.size(); ++k) worst_gap = std::max(worst_gap, std::abs(r[k] - p[k]) / scale);
            rows.push_back(r);
        }
        for (std::size_t k = 0; k < rows[0].size(); ++k) {
            if (rows[0][k] == 0.0 && rows[1][k] == 0.0 && rows[2][k] == 0.0) continue;
            const sk::Richardson rc = sk::richardson_check({rows[0][k], rows[1][k], rows[2][k]}, 2.0, 2.0);
            const bool in_window = rc.observed_order && *rc.observed_order >= 1.5 && *rc.observed_order <= 2.5;
            if (rc.status != sk::RichStatus::Ok || !in_window)
                bad += "[" + std::to_string(index) + ", " + std::to_string(k) + "]";
            std::printf("K-8 acceptance 3 (C++): case %zu entry %zu order %.17g\n", index, k,
                        rc.observed_order ? *rc.observed_order : -1.0);
        }
    }
    std::printf("K-8 acceptance 3 (C++): failures=[%s] max_gap_vs_python_relative_to_row_scale=%.17g\n", bad.c_str(),
                worst_gap);
    CHECK(worst_gap <= 1e-9);
    CHECK(bad.empty());
}
#endif

TEST_CASE("k8: smoothing worked example f = (-1, 0, 1) gives E, 1/18, V", "[k8]") {
    const bk8::Duals v = {{0.0}, {0.0}, {0.0}};
    const bk8::Duals got = bk8::smoothed_max(v, {{1.0}, {0.0}, {-1.0}});
    CHECK(got[0][0] == 1.0);
    CHECK(std::abs(got[1][0] - 1.0 / 18) <= 1e-16);
    CHECK(got[2][0] == 0.0);
    const bk8::Duals mirror = bk8::smoothed_max(v, {{-1.0}, {0.0}, {1.0}});
    CHECK(mirror[0][0] == 0.0);
    CHECK(std::abs(mirror[1][0] - 1.0 / 18) <= 1e-16);
    CHECK(mirror[2][0] == 1.0);
}

TEST_CASE("k8: M(p, q) against a fine midpoint sum on the four branches and their joins", "[k8]") {
    const double cases[][2] = {{1, 2}, {1, -0.5}, {-0.5, 1}, {-1, -2}, {0, 1}, {1, 0}, {0, -1}};
    const int n = 200000;
    for (const auto& c : cases) {
        double want = 0;
        for (int i = 0; i < n; ++i) {
            const double u = (i + 0.5) / n;
            want += (1 - u) * std::max(c[0] + (c[1] - c[0]) * u, 0.0);
        }
        want /= n;
        INFO(c[0] << "," << c[1]);
        CHECK(std::abs(want - bk8::hat_part({c[0]}, {c[1]})[0]) <= 1e-9);
    }
}

TEST_CASE("k8: away from the crossing the smoothing is the pointwise max", "[k8]") {
    const int n = 41;
    bk8::Duals v(n, bk8::Dual(1, 0.0));
    Vec f(n);
    int j = -1;
    for (int i = 0; i < n; ++i) {
        const double x = -1.0 + 2.0 * i / (n - 1);
        f[i] = (x - 0.013) * (1 + 0.3 * x + 0.2 * x * x);
        v[i][0] = f[i];
        if (j < 0 && f[i] > 0) j = i;
    }
    const bk8::Duals got = bk8::smoothed_max(v, bk8::Duals(n, bk8::Dual(1, 0.0)));
    for (int i = 0; i < n - 2; ++i) {
        INFO("node " << i);
        if (i >= j + 2)
            CHECK(std::abs(got[i][0] - f[i]) <= 1e-14);
        else if (i < j - 2)
            CHECK(got[i][0] == 0.0);
        else
            CHECK(got[i][0] != std::max(f[i], 0.0));
    }
}

TEST_CASE("k8: dual arithmetic", "[k8]") {
    const bk8::Dual u{2, 1, 0}, v{4, 0, 1};
    CHECK(bk8::mul(u, v) == bk8::Dual{8, 4, 2});
    CHECK(bk8::div(u, v) == bk8::Dual{0.5, 0.25, -0.125});
    CHECK(bk8::add(u, v) == bk8::Dual{6, 1, 1});
    CHECK(bk8::sub(u, v) == bk8::Dual{-2, 1, -1});
    CHECK(bk8::scale(2, u) == bk8::Dual{4, 2, 0});
}

TEST_CASE("k8: method value and error order through the CLI", "[k8]") {
    // An unlisted method is E_SCHEMA; the G-18 path keeps its value when method is G18_IMPLICIT.
    const std::string base =
        R"({"mean_reversion":0.05,"sigma":0.01,"curve":{"times":[1,2,3,5],"discount_factors":[0.97,0.94,0.91,0.85]},)"
        R"("notional":1,"start_years":1,"payment_times":[2,3,4,5],"grid":{"nx":41,"steps_per_year":20,"width":6},)"
        R"("fixed_rate":0.03,"swaption_type":"PAYER","exercise_times":[1,2,3])";
    const json::Value g18 = run("rates.shortrate.bermudan_swaption", base + "}");
    const json::Value named = run("rates.shortrate.bermudan_swaption", base + R"(,"method":"G18_IMPLICIT"})");
    REQUIRE(g18.find("status")->text == "ok");
    CHECK(g18.find("outputs")->find("price")->number == named.find("outputs")->find("price")->number);
    const json::Value k8 = run("rates.shortrate.bermudan_swaption", base + R"(,"method":"CN_RANNACHER_SMOOTHED"})");
    REQUIRE(k8.find("status")->text == "ok");
    CHECK(k8.find("outputs")->find("price")->number > 0.0);
    const json::Value bad = run("rates.shortrate.bermudan_ladder", base + R"(,"method":"CN"})");
    CHECK(bad.find("error")->find("code")->text == "E_SCHEMA");
    const json::Value not_text = run("rates.shortrate.bermudan_ladder", base + R"(,"method":1})");
    CHECK(not_text.find("error")->find("code")->text == "E_SCHEMA");
}
