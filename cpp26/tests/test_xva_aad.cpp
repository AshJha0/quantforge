// xva_aad (06-risk/xva-aad-adjustments.md, KR-262 to KR-268): identities of the backward pass on 1,000 seeded
// random requests, the overlap branches, exact zeros and the wrt rules. The goldens replay in test_golden_replay.cpp.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "quantforge/core/xva_aad.hpp"

namespace {

namespace xa = quantforge::xva_aad;

struct Lcg {
    std::uint64_t s;
    double next() {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        return double(s >> 11) / double(1ULL << 53);
    }
};

const xa::Entry& entry(const xa::Gradient& g, const std::string& k) {
    const auto it = std::find_if(g.begin(), g.end(), [&](const xa::Entry& e) { return e.key == k; });
    REQUIRE(it != g.end());
    return *it;
}

const xa::Gradient& output(const std::vector<std::pair<std::string, xa::Gradient>>& g, const std::string& o) {
    const auto it = std::find_if(g.begin(), g.end(), [&](const auto& p) { return p.first == o; });
    REQUIRE(it != g.end());
    return it->second;
}

bool near(double a, double b, double tol) { return std::fabs(a - b) <= tol * std::max({1.0, std::fabs(a), std::fabs(b)}); }

xa::Request base() {
    xa::Request r;
    r.t = {0.5, 1.0, 1.5, 2.0};
    r.df = {0.985, 0.97, 0.955, 0.94};
    r.ee = {120, 150, 130, 80};
    r.ene = {-60, -90, -100, -70};
    r.hc = 0.02, r.rc = 0.4, r.hb = 0.01, r.rb = 0.4, r.sb = 0.008, r.sl = 0.008;
    return r;
}

}  // namespace

TEST_CASE("xva_aad: golden 0001 selected entries and output order") {
    const auto g = xa::gradient(base(), xa::keys(false, false));
    REQUIRE(g.size() == 5);
    const auto& c = output(g, "cva");
    CHECK(near(entry(c, "counterparty.hazard_rate").s, 133.0258166316599, 1e-12));
    CHECK(near(entry(c, "counterparty.recovery").s, -4.51643629000504, 1e-12));
    CHECK(near(entry(c, "ee").v[1], 0.005704780048492856, 1e-12));
    CHECK(entry(c, "own.hazard_buckets").v[3] == 0.0);
    CHECK(near(entry(output(g, "fca"), "funding.borrow_spread").s, 226.952805418071, 1e-12));
}

TEST_CASE("xva_aad: identities on 1,000 random requests") {
    Lcg r{20261120};
    for (int c = 0; c < 1000; ++c) {
        xa::Request q;
        const std::size_t n = 1 + std::size_t(r.next() * 6);
        const double scale = std::pow(10.0, -3 + 9 * r.next());
        double acc = 0;
        for (std::size_t i = 0; i < n; ++i) {
            acc += 0.01 + 3 * r.next();
            q.t.push_back(acc);
            q.df.push_back(0.3 + 0.75 * r.next());
            q.ee.push_back(r.next() < 0.15 ? 0.0 : scale * r.next());
            q.ene.push_back(r.next() < 0.15 ? 0.0 : -scale * r.next());
            q.im.push_back(scale * r.next());
            q.capital.push_back(scale * r.next());
        }
        q.hc = r.next() < 0.5 ? 0.0 : 0.6 * r.next();
        q.rc = 0.999999 * r.next();
        q.hb = r.next() < 0.5 ? 0.0 : 0.1 * r.next();
        q.rb = 0.99 * r.next();
        q.sb = 0.03 * r.next();
        q.sl = 0.03 * r.next();
        q.exclude_overlap = r.next() < 0.5;
        q.has_im = q.has_capital = true;
        q.im_spread = 0.02 * r.next();
        q.hurdle = 0.15 * r.next();
        const auto g = xa::gradient(q, xa::keys(true, true));
        REQUIRE(g.size() == 7);
        for (const auto& [o, row] : g) {
            for (const std::string name : {"counterparty", "own"}) {
                const double flat = entry(row, name + ".hazard_rate").s;
                double sum = 0;
                for (double x : entry(row, name + ".hazard_buckets").v) sum += x;
                CHECK(near(flat, sum, 1e-11));
            }
        }
        double cva = 0, lin = 0;
        for (std::size_t i = 0; i < n; ++i) {
            const double p = i ? q.t[i - 1] : 0.0;
            cva += q.df[i] * q.ee[i] * (std::exp(-q.hc * p) - std::exp(-q.hc * q.t[i])) * std::exp(-q.hb * p);
            lin += entry(output(g, "cva"), "ee").v[i] * q.ee[i];
        }
        cva *= 1 - q.rc;
        CHECK(near(lin, cva, 1e-12));
        CHECK(near(entry(output(g, "cva"), "counterparty.recovery").s, -cva / (1 - q.rc), 1e-12));
        const double d = entry(output(g, "fca"), "discount_factors").v[0] - entry(output(g, "fba"), "discount_factors").v[0];
        CHECK(entry(output(g, "fva"), "discount_factors").v[0] == d);
    }
}

TEST_CASE("xva_aad: overlap kink, floor and exact zeros") {
    xa::Request r = base();
    r.hb = 0.01, r.rb = 0.5, r.sl = 0.005, r.exclude_overlap = true;  // 0.005 - 0.01 x 0.5 = 0 exactly
    auto g = xa::gradient(r, xa::keys(false, false));
    const double sl = entry(output(g, "fba"), "funding.lend_spread").s;
    CHECK(near(sl, 150.34122754292395, 1e-12));
    CHECK(near(entry(output(g, "fba"), "own.hazard_rate").s, -0.5 * sl, 1e-12));
    CHECK(near(entry(output(g, "fba"), "own.recovery").s, 0.01 * sl, 1e-12));
    r.hb = 0.02;  // below the kink: the floor
    g = xa::gradient(r, xa::keys(false, false));
    for (const auto& e : output(g, "fba")) {
        CHECK(e.s == 0.0);
        for (double x : e.v) CHECK(x == 0.0);
    }
    xa::Request z = base();
    z.hc = 0.0;
    z.ee = {1e5, 0.0, 3.5e4, 0.0};
    g = xa::gradient(z, xa::keys(false, false));
    CHECK(entry(output(g, "cva"), "counterparty.hazard_buckets").v[1] == 0.0);
    CHECK(entry(output(g, "cva"), "counterparty.hazard_buckets").v[3] == 0.0);
}

TEST_CASE("xva_aad: wrt rules and keys") {
    const auto all = xa::keys(true, false);
    CHECK(all.size() == 13);
    CHECK(xa::keys(false, true).back() == "hurdle_rate");
    CHECK(xa::check_wrt(std::nullopt, all) == all);
    CHECK(xa::check_wrt(std::vector<std::string>{"ene", "own.recovery"}, all) ==
          std::vector<std::string>{"own.recovery", "ene"});
    for (const auto& bad : std::vector<std::vector<std::string>>{{}, {"ee", "ee"}, {"capital"}, {"x"}}) {
        try {
            (void)xa::check_wrt(bad, all);
            FAIL("expected E_INPUT");
        } catch (const quantforge::Error& e) {
            CHECK(std::string(e.code()) == "E_INPUT");
        }
    }
    const auto g = xa::gradient(base(), {"ee"});
    for (const auto& [o, row] : g) CHECK((row.size() == 1 && row[0].key == "ee"));
}
