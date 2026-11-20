// Stage K wave 2 (K-8a FRTB DRC and RRAO, K-8f FRTB IMA): the drc_k and ima_k golden suites replayed through the CLI
// layer at their own tolerances, hand cases from 06-risk/frtb-drc-rrao.md and frtb-ima.md, the parameters against the
// shared tables (KR-50), the A3 properties as corrected by KR-327 (seeded, 10,000 books) with the pinned
// counterexample, and the KR-67 error order. Golden counts are read from the files, never written here.
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/dates.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/frtb_drc.hpp"
#include "quantforge/core/frtb_ima.hpp"
#include "quantforge/core/json.hpp"

namespace {

namespace json = quantforge::json;
namespace dr = quantforge::frtb_drc;
namespace im = quantforge::frtb_ima;
using quantforge::make_date;

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

// Every case of one suite through the CLI layer; returns the number replayed (counts read from the file).
std::size_t replay(const std::string& suite) {
    const json::Parsed doc = json::parse(read_text(std::string(QF_REPO_DIR) + "/datasets/golden/stage_k/" + suite + ".json"));
    const json::Value* cases = doc.value.find("cases");
    REQUIRE(cases);
    for (const json::Value& c : cases->items) {
        INFO(c.find("case_id")->text);
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

bool near(double got, double want, double rel = 1e-12) {
    return std::fabs(got - want) <= 1e-15 + rel * std::max(std::fabs(got), std::fabs(want));
}

// The value of the table entry `key` in specifications/tables/stage_k/<file>.json.
json::Value table_value(const std::string& file, const std::string& key) {
    const json::Parsed doc = json::parse(read_text(std::string(QF_REPO_DIR) + "/specifications/tables/stage_k/" + file));
    for (const json::Value& e : doc.value.find("entries")->items)
        if (e.find("key")->text == key) return *e.find("value");
    FAIL("missing table entry " << key);
    return {};
}
double table_real(const std::string& file, const std::string& key) { return std::stod(table_value(file, key).text); }

dr::Position pos(const std::string& id, const std::string& obligor, const std::string& bucket, const std::string& sen,
                 double notional, double mv, double m, bool cash_equity = false) {
    dr::Position p;
    p.id = id;
    p.obligor = obligor;
    p.bucket = bucket;
    p.seniority = sen;
    p.notional = notional;
    p.market_value = mv;
    p.maturity_years = m;
    p.cash_equity = cash_equity;
    return p;
}

double bucket_drc_of(const dr::NonsecResult& r, const std::string& bucket) {
    for (const dr::BucketRow& b : r.buckets)
        if (b.bucket == bucket) return b.drc;
    return 0.0;
}

// The KR-327 property book: obligors A (BBB) and B (BB) corporate, C (AA) sovereign, as the Java FrtbDrcTest.
const std::map<std::string, std::string>& rating_map() {
    static const std::map<std::string, std::string> m = {{"A", "BBB"}, {"B", "BB"}, {"C", "AA"}};
    return m;
}
std::string bucket_for(const std::string& obligor) { return obligor == "C" ? "SOVEREIGN" : "CORPORATE"; }

std::vector<dr::Position> random_book(std::mt19937_64& g, double scale) {
    static const char* const obligors[] = {"A", "B", "C"};
    static const char* const seniorities[] = {"COVERED", "SENIOR", "NON_SENIOR", "EQUITY"};
    static const double maturities[] = {0.1, 0.25, 0.5, 0.9, 1.0, 3.0};
    std::uniform_int_distribution<int> count(1, 10), amount(-1000, 1000), pick3(0, 2), pick4(0, 3), pick6(0, 5);
    std::vector<dr::Position> book;
    const int n = count(g);
    for (int k = 0; k < n; ++k) {
        const std::string ob = obligors[pick3(g)];
        int notional = amount(g);
        if (notional == 0) notional = 1;
        const int mv = amount(g);
        book.push_back(pos("p" + std::to_string(k), ob, bucket_for(ob), seniorities[pick4(g)], scale * notional,
                           scale * mv, maturities[pick6(g)]));
    }
    return book;
}

}  // namespace

// ---- goldens ----

TEST_CASE("wave 2 lane A goldens: drc_k and ima_k through the CLI layer", "[frtb_drc_ima]") {
    CHECK(replay("drc_k") > 0);
    CHECK(replay("ima_k") > 0);
}

// ---- parameters against the shared tables (KR-50) ----

TEST_CASE("DRC and RRAO parameters equal mar22_drc.json and mar23_rrao.json", "[frtb_drc_ima]") {
    const dr::Params& p = dr::params();
    CHECK(p.lgd.at("SENIOR") == table_real("mar22_drc.json", "lgd.senior_debt"));
    CHECK(p.lgd.at("COVERED") == 0.25);
    CHECK(p.lgd.at("NON_SENIOR") == 1.0);
    CHECK(p.lgd.at("EQUITY") == 1.0);
    CHECK(p.risk_weight.at("AAA") == 0.005);
    CHECK(p.risk_weight.at("UNRATED") == table_real("mar22_drc.json", "rw.Unrated"));
    CHECK(p.risk_weight.at("DEFAULTED") == 1.0);
    CHECK(p.risk_weight.at("CCC") == 0.5);
    CHECK(p.capital_horizon == 1.0);
    CHECK(p.maturity_floor == 0.25);
    CHECK(p.cash_equity_short == 0.25);
    CHECK(p.ctp_cross_factor == 0.5);
    CHECK(p.rrao_weight.at("EXOTIC") == 0.01);
    CHECK(p.rrao_weight.at("OTHER") == table_real("mar23_rrao.json", "rw.other_residual_risk"));
    CHECK(dr::rank("COVERED") == 4);
    CHECK(dr::rank("SENIOR") == 3);
    CHECK(dr::rank("NON_SENIOR") == 2);
    CHECK(dr::rank("EQUITY") == 1);
}

TEST_CASE("IMA parameters equal mar31_rfet.json, mar32_pla.json and mar33_ima.json", "[frtb_drc_ima]") {
    const im::Params& p = im::params();
    CHECK(p.pla_green_spearman == 0.8);
    CHECK(p.pla_red_spearman == 0.7);
    CHECK(p.pla_green_ks_percent == 9);
    CHECK(p.pla_red_ks_percent == 12);
    CHECK(p.pla_window == 250);
    CHECK(p.es_confidence == 0.975);
    CHECK(p.base_horizon == 10);
    CHECK(p.horizons == std::array<long long, 5>{10, 20, 40, 60, 120});
    CHECK(p.lh_table.size() == table_value("mar33_ima.json", "lh.table").members.size());
    CHECK(p.specified_fx_pairs.size() == table_value("mar33_ima.json", "lh.specified_fx_pairs").items.size());
    CHECK(p.imcc_rho == 0.5);
    CHECK(p.ses_rho == 0.6);
    CHECK(p.multiplier == std::vector<double>{1.5, 1.5, 1.5, 1.5, 1.5, 1.7, 1.76, 1.83, 1.88, 1.92});
    CHECK(p.multiplier_red == 2.0);
    CHECK(p.rfet_min_days == 24);
    CHECK(p.rfet_window_days == 90);
    CHECK(p.rfet_min_per_window == 4);
    CHECK(p.rfet_alt_min_days == 100);
    CHECK(p.rfet_lookback_months == 12);
    CHECK(p.rfet_lower.at("A") == std::vector<double>{0, 0.75, 1.5, 4, 7, 12, 18, 25, 35});
    CHECK(p.rfet_lower.at("D") == std::vector<double>{0, 0.05, 0.3, 0.7, 0.95});
    CHECK(p.rfet_d_upper == 1.0);
}

// ---- DRC hand cases (frtb-drc-rrao.md, Golden cases and Worked example) ----

TEST_CASE("DRC non-securitisation by hand", "[frtb_drc_ima]") {
    const std::map<std::string, std::string> bbb = {{"X", "BBB"}};
    // drc_k-0001: 0.75 x 100 = 75; 0.06 x 75 = 4.5
    dr::NonsecResult r = dr::drc_nonsec({pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5)}, bbb);
    CHECK(r.positions[0].gross_jtd == 75.0);
    CHECK(r.buckets[0].hbr == 1.0);
    CHECK(near(r.drc, 4.5));
    // drc_k-0002: weight one half
    r = dr::drc_nonsec({pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 0.5)}, bbb);
    CHECK(r.positions[0].scaled_jtd == 37.5);
    CHECK(near(r.drc, 2.25));
    // drc_k-0004: the short at 0.25 offsets a quarter of the long
    r = dr::drc_nonsec({pos("l", "X", "CORPORATE", "SENIOR", 100, 100, 5), pos("s", "X", "CORPORATE", "SENIOR", -100, -100, 0.25)},
                       bbb);
    CHECK(r.obligors[0].net_long == 56.25);
    CHECK(near(r.drc, 3.375));
    // worked example drc_k-0007: senior short cannot offset an equity long
    const std::map<std::string, std::string> bb = {{"Z", "BB"}};
    r = dr::drc_nonsec({pos("stock", "Z", "CORPORATE", "EQUITY", 50, 50, 2, true), pos("bond", "Z", "CORPORATE", "SENIOR", -40, -40, 2)},
                       bb);
    CHECK(r.obligors[0].net_long == 50.0);
    CHECK(r.obligors[0].net_short == -30.0);
    CHECK(r.buckets[0].hbr == 0.625);
    CHECK(near(r.drc, 4.6875));
    // drc_k-0008: turned round, the equity short offsets the bond long: net short -20, HBR 0, DRC 0
    r = dr::drc_nonsec({pos("bond", "Z", "CORPORATE", "SENIOR", 40, 40, 2), pos("stock", "Z", "CORPORATE", "EQUITY", -50, -50, 2, true)},
                       bb);
    CHECK(r.obligors[0].net_short == -20.0);
    CHECK(r.buckets[0].hbr == 0.0);
    CHECK(r.drc == 0.0);
    // drc_k-0010: sold put mapped to a bond-equivalent: 0.75 x 100 + (92 - 100) = 67
    r = dr::drc_nonsec({pos("put", "X", "CORPORATE", "SENIOR", 100, 92, 5)}, bbb);
    CHECK(r.positions[0].gross_jtd == 67.0);
    CHECK(near(r.drc, 4.02));
    // a short with zero notional and zero value is no position: JTD 0, no obligor short
    CHECK(dr::gross_jtd(pos("z", "X", "CORPORATE", "SENIOR", 0, 0, 1)) == 0.0);
    // lgd_applies false: notional not multiplied by LGD
    dr::Position no_lgd = pos("n", "X", "CORPORATE", "SENIOR", 100, 100, 5);
    no_lgd.lgd_applies = false;
    CHECK(dr::gross_jtd(no_lgd) == 100.0);
    // maturity weights: floor 0.25, one year or more is 1
    CHECK(dr::maturity_weight(0.1) == 0.25);
    CHECK(dr::maturity_weight(0.5) == 0.5);
    CHECK(dr::maturity_weight(1.0) == 1.0);
    // positions sorted by id, obligors by name, buckets in MAR22.22 order
    r = dr::drc_nonsec({pos("b", "Y", "SOVEREIGN", "SENIOR", 10, 10, 5), pos("a", "X", "CORPORATE", "SENIOR", 10, 10, 5)},
                       {{"X", "A"}, {"Y", "AA"}});
    CHECK(r.positions[0].id == "a");
    CHECK(r.obligors[0].obligor == "X");
    CHECK(r.buckets[0].bucket == "CORPORATE");
    CHECK(r.buckets[1].bucket == "SOVEREIGN");
}

TEST_CASE("DRC securitisation, CTP and RRAO by hand", "[frtb_drc_ima]") {
    // sec_k-0001: no offset across tranches; hbr 50/70
    const dr::SecResult s = dr::drc_sec_nonctp({{"l", "RMBS-EU", "P1", "T1", 50, 5, 0.2}, {"s", "RMBS-EU", "P1", "T2", -20, 5, 0.2}});
    CHECK(near(*s.buckets[0].hbr, 50.0 / 70.0));
    CHECK(near(s.drc, 10.0 - (50.0 / 70.0) * 4.0));
    // same tranche nets: 50 - 20 = 30 long, drc 6
    const dr::SecResult n = dr::drc_sec_nonctp({{"l", "B", "P", "T", 50, 5, 0.2}, {"s", "B", "P", "T", -20, 5, 0.2}});
    CHECK(near(n.drc, 6.0));
    CHECK(dr::drc_sec_nonctp({}).drc == 0.0);
    // ctp_k-0001 (MAR22.45 printed): 100 - 0.5 x 100 = 50; ctp_k-0003: max(-5, 0) = 0
    CHECK(dr::ctp_total({100, -100}) == 50.0);
    CHECK(dr::ctp_total({-10}) == 0.0);
    // ctp_k-0002: hbr 0.5; DRC_A 100, DRC_B -50; total max(100 - 25, 0) = 75
    const dr::CtpResult c = dr::drc_ctp(std::vector<dr::CtpPosition>{{"a", "A", "S1", "T", 1000, 5, 0.1}, {"b", "B", "S1", "T", -1000, 5, 0.1}},
                                        std::nullopt);
    CHECK(c.hbr_ctp == 0.5);
    CHECK(near(c.buckets[0].drc, 100.0));
    CHECK(near(c.buckets[1].drc, -50.0));
    CHECK(near(c.drc, 75.0));
    const dr::CtpResult e = dr::drc_ctp(std::vector<dr::CtpPosition>{}, std::nullopt);
    CHECK_FALSE(e.hbr_ctp.has_value());
    CHECK(e.drc == 0.0);
    // rrao_k-0001 and 0002
    CHECK(near(dr::rrao({{"e", 1e6, "EXOTIC", false, false}, {"o", 2e6, "OTHER", false, false}}).rrao, 12000.0));
    const dr::RraoResult r = dr::rrao({{"o", 5e6, "OTHER", true, false}, {"e", 1e6, "EXOTIC", true, false}, {"b", 3e6, "EXOTIC", false, true}});
    CHECK(near(r.rrao, 10000.0));
    CHECK(r.instruments[0].excluded);
    CHECK_FALSE(r.instruments[1].excluded);
    CHECK(r.instruments[2].excluded);
    CHECK(dr::rrao({}).rrao == 0.0);
}

TEST_CASE("KR-53 greedy offset: shorts by descending rank, longs by ascending rank", "[frtb_drc_ima]") {
    // a covered short (rank 4) only offsets covered longs; an equity short (rank 1) offsets anything
    auto [l1, s1] = dr::offset({{1, 10.0}, {4, 5.0}}, {{4, -8.0}});
    CHECK(l1 == 10.0);
    CHECK(s1 == -3.0);
    auto [l2, s2] = dr::offset({{4, 5.0}, {1, 10.0}}, {{1, -12.0}});
    CHECK(l2 == 3.0);  // the equity long goes first (ascending rank), then 2 of the covered long
    CHECK(s2 == 0.0);
    auto [l3, s3] = dr::offset({}, {{3, -4.0}});
    CHECK(l3 == 0.0);
    CHECK(s3 == -4.0);
}

TEST_CASE("KR-327: the pinned A3 counterexample, 18.679 to 17.739", "[frtb_drc_ima]") {
    std::vector<dr::Position> book = {
        pos("p0", "B", "CORPORATE", "COVERED", 932, 943, 0.25), pos("p1", "B", "CORPORATE", "SENIOR", -773, 819, 3.0),
        pos("p2", "B", "CORPORATE", "NON_SENIOR", 627, 943, 0.1), pos("p3", "A", "CORPORATE", "SENIOR", -805, -412, 0.1),
        pos("p4", "A", "CORPORATE", "EQUITY", -231, -355, 0.25), pos("p5", "A", "CORPORATE", "COVERED", 368, 834, 0.25),
        pos("p6", "B", "CORPORATE", "SENIOR", -663, -798, 0.5), pos("p7", "A", "CORPORATE", "SENIOR", -684, 387, 0.1),
        pos("p8", "C", "SOVEREIGN", "COVERED", 756, 381, 1.0), pos("p9", "A", "CORPORATE", "EQUITY", -673, -326, 3.0)};
    const double before = bucket_drc_of(dr::drc_nonsec(book, rating_map()), "CORPORATE");
    book.push_back(pos("new", "A", "CORPORATE", "COVERED", 885, 885, 2.0));
    const double after = bucket_drc_of(dr::drc_nonsec(book, rating_map()), "CORPORATE");
    CHECK(near(before, 18.67915216395695));
    CHECK(near(after, 17.739318324443047));
    CHECK(after < before);  // "adding a long never lowers DRC_b" is false (KR-327)
}

TEST_CASE("A3 properties as corrected by KR-327, 10,000 seeded books", "[frtb_drc_ima]") {
    std::mt19937_64 g(20261120);
    std::uniform_int_distribution<int> pick3(0, 2), pick4(0, 3), extra(0, 1000);
    static const char* const obligors[] = {"A", "B", "C"};
    static const char* const seniorities[] = {"COVERED", "SENIOR", "NON_SENIOR", "EQUITY"};
    long long premise_met = 0;
    for (int trial = 0; trial < 10000; ++trial) {
        const std::vector<dr::Position> book = random_book(g, 1.0);
        const dr::NonsecResult out = dr::drc_nonsec(book, rating_map());
        REQUIRE(out.drc >= 0.0);
        for (const dr::BucketRow& b : out.buckets) {
            REQUIRE(b.drc >= 0.0);
            if (b.hbr) REQUIRE((*b.hbr >= 0.0 && *b.hbr <= 1.0));
        }
        // KR-327: a long added to an obligor with no net short, with risk weight at least that of every obligor
        // with a net short in the bucket, never lowers DRC_b.
        const std::string ob = obligors[pick3(g)];
        const double amount = double(extra(g));
        const std::string sen = seniorities[pick4(g)];
        const std::string bk = bucket_for(ob);
        double short_rw = 0.0;
        bool no_short = true;
        for (const dr::ObligorRow& o : out.obligors) {
            if (bucket_for(o.obligor) == bk && o.net_short != 0.0) short_rw = std::max(short_rw, o.rw);
            if (o.obligor == ob && o.net_short != 0.0) no_short = false;
        }
        if (no_short && dr::params().risk_weight.at(rating_map().at(ob)) >= short_rw) {
            ++premise_met;
            std::vector<dr::Position> more = book;
            more.push_back(pos("new", ob, bk, sen, amount, amount, 2.0));
            const double after = bucket_drc_of(dr::drc_nonsec(more, rating_map()), bk);
            const double before = bucket_drc_of(out, bk);
            REQUIRE(after >= before - 1e-9 * (1.0 + after));
        }
        // permuting the input leaves every output unchanged (totals to rounding)
        std::vector<dr::Position> shuffled = book;
        std::shuffle(shuffled.begin(), shuffled.end(), g);
        const dr::NonsecResult again = dr::drc_nonsec(shuffled, rating_map());
        REQUIRE(again.positions.size() == out.positions.size());
        for (std::size_t k = 0; k < out.positions.size(); ++k) {
            REQUIRE(again.positions[k].id == out.positions[k].id);
            REQUIRE(again.positions[k].scaled_jtd == out.positions[k].scaled_jtd);
        }
        REQUIRE(std::fabs(again.drc - out.drc) <= 1e-12 * (1.0 + out.drc));
        // scaling every notional and market value by c scales DRC by c
        std::vector<dr::Position> scaled = book;
        for (dr::Position& p : scaled) {
            p.notional *= 2.5;
            p.market_value *= 2.5;
        }
        REQUIRE(std::fabs(dr::drc_nonsec(scaled, rating_map()).drc - 2.5 * out.drc) <= 1e-9 * (1.0 + out.drc));
    }
    CHECK(premise_met > 1000);
}

TEST_CASE("DRC errors in KR-67 order", "[frtb_drc_ima]") {
    const std::string op = "risk.frtb.drc_nonsec";
    const std::string ok_pos = R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"SENIOR","notional":1,"market_value":1,"maturity_years":1})";
    CHECK(code(op, R"({"positions":[)" + ok_pos + R"(],"ratings":{"X":"BBB"}})") == "ok");
    CHECK(code(op, R"({"positions":[)" + ok_pos + R"(],"ratings":{"X":"JUNK"}})") == "E_SCHEMA");
    CHECK(code(op, R"({"positions":[)" + ok_pos + R"(],"ratings":[]})") == "E_SCHEMA");
    CHECK(code(op, R"({"positions":[],"ratings":{}})") == "E_INPUT");
    CHECK(code(op, R"({"positions":[)" + ok_pos + R"(],"ratings":{}})") == "E_INPUT");
    // duplicate id (E_INPUT) beats maturity 0 (E_DOMAIN)
    const std::string bad_m = R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"SENIOR","notional":1,"market_value":1,"maturity_years":0})";
    CHECK(code(op, R"({"positions":[)" + ok_pos + "," + bad_m + R"(],"ratings":{"X":"BBB"}})") == "E_INPUT");
    // the obligor in two buckets is E_INPUT
    const std::string sov = R"({"id":"q","obligor":"X","bucket":"SOVEREIGN","seniority":"SENIOR","notional":1,"market_value":1,"maturity_years":1})";
    CHECK(code(op, R"({"positions":[)" + ok_pos + "," + sov + R"(],"ratings":{"X":"BBB"}})") == "E_INPUT");
    // the finite rule (E_DOMAIN) beats a missing rating (E_INPUT)
    const std::string nan = R"({"id":"p","obligor":"Y","bucket":"CORPORATE","seniority":"SENIOR","notional":"NaN","market_value":1,"maturity_years":1})";
    CHECK(code(op, R"({"positions":[)" + nan + R"(],"ratings":{"X":"BBB"}})") == "E_DOMAIN");
    // cash equity: maturity 0.5, not EQUITY, notional != market value; zero notional with a value
    const auto one = [&](const std::string& p) { return code(op, R"({"positions":[)" + p + R"(],"ratings":{"X":"BBB"}})"); };
    CHECK(one(R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"EQUITY","notional":1,"market_value":1,"maturity_years":0.5,"cash_equity":true})") == "E_DOMAIN");
    CHECK(one(R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"SENIOR","notional":1,"market_value":1,"maturity_years":2,"cash_equity":true})") == "E_DOMAIN");
    CHECK(one(R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"EQUITY","notional":1,"market_value":2,"maturity_years":0.25,"cash_equity":true})") == "E_DOMAIN");
    CHECK(one(R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"SENIOR","notional":0,"market_value":2,"maturity_years":1})") == "E_DOMAIN");
    CHECK(one(R"({"id":"p","obligor":"X","bucket":"CORPORATE","seniority":"EQUITY","notional":1,"market_value":1,"maturity_years":0.25,"cash_equity":true})") == "ok");
    // securitisation: different rw in one netting group (E_INPUT) beats rw above 12.5 (E_DOMAIN)
    const std::string sec = "risk.frtb.drc_sec_nonctp";
    CHECK(code(sec, R"({"positions":[{"id":"a","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":1,"rw":13},{"id":"b","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":1,"rw":0.2}]})") == "E_INPUT");
    CHECK(code(sec, R"({"positions":[{"id":"a","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":1,"rw":13}]})") == "E_DOMAIN");
    CHECK(code(sec, R"({"positions":[{"id":"a","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":-1,"rw":0.1}]})") == "E_DOMAIN");
    CHECK(code(sec, R"({"positions":[{"id":"a","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":1,"rw":0.1},{"id":"a","bucket":"B","pool":"P","tranche":"T","market_value":1,"maturity_years":1,"rw":0.1}]})") == "E_INPUT");
    // CTP: both or neither mode is E_INPUT; bucket_drc mode reports drc only
    const std::string ctp = "risk.frtb.drc_ctp";
    CHECK(code(ctp, "{}") == "E_INPUT");
    CHECK(code(ctp, R"({"positions":[],"bucket_drc":[1]})") == "E_INPUT");
    const json::Parsed p = run(ctp, R"({"bucket_drc":[100,-100]})");
    CHECK(p.value.find("outputs")->find("drc")->number == 50.0);
    CHECK_FALSE(p.value.find("outputs")->find("positions"));
    CHECK(code(ctp, R"({"positions":[{"id":"a","index":"I","series":"S","tranche":"T","market_value":1,"maturity_years":1,"rw":-0.1}]})") == "E_DOMAIN");
    CHECK(code(ctp, R"({"positions":[{"id":"a","index":"I","series":"S","tranche":"T","market_value":1,"maturity_years":1,"rw":0.1}]})") == "ok");
    // RRAO
    const std::string rr = "risk.frtb.rrao";
    CHECK(code(rr, R"({"instruments":[{"id":"e","gross_notional":-1,"kind":"EXOTIC","listed_or_clearable":false,"back_to_back":false}]})") == "E_DOMAIN");
    CHECK(code(rr, R"({"instruments":[{"id":"e","gross_notional":1,"kind":"WEIRD","listed_or_clearable":false,"back_to_back":false}]})") == "E_SCHEMA");
    CHECK(code(rr, R"({"instruments":[{"id":"e","gross_notional":-1,"kind":"EXOTIC","listed_or_clearable":false,"back_to_back":false},{"id":"e","gross_notional":1,"kind":"OTHER","listed_or_clearable":false,"back_to_back":false}]})") == "E_INPUT");
    CHECK(code(rr, R"({"instruments":[{"id":"e","gross_notional":1,"kind":"EXOTIC","listed_or_clearable":false}]})") == "E_SCHEMA");
}

TEST_CASE("DRC core limits and checks without the CLI layer", "[frtb_drc_ima]") {
    std::vector<dr::SecPosition> many(100001, dr::SecPosition{"x", "B", "P", "T", 1, 1, 0.1});
    CHECK_THROWS_AS(dr::drc_sec_nonctp(many), quantforge::Error);
    CHECK_THROWS_AS(dr::drc_ctp(std::nullopt, std::vector<double>(100001, 1.0)), quantforge::Error);
    CHECK_THROWS_AS(dr::drc_ctp(std::nullopt, std::nullopt), quantforge::Error);
}

// ---- IMA hand cases (frtb-ima.md) ----

TEST_CASE("PLA statistics by hand (MAR32.36 to MAR32.42, KR-56, KR-305)", "[frtb_drc_ima]") {
    // pla_k-0001: ranks (1,3,5,2,4) and (1,2,5,3,4): rho = 1 - 6 x 2 / 120 = 0.9; KS one step of 1/5
    const std::vector<double> h = {-3, 1, 4, -1, 2}, r = {-2, 0, 5, 1, 3};
    CHECK(near(im::spearman(h, r), 0.9));
    CHECK(im::ks_count(h, r) == 1);
    const im::Pla p = im::pla(h, r);
    CHECK(p.n == 5);
    CHECK(p.ks == 0.2);
    CHECK(p.zone == "RED");  // KS 0.2 above 0.12
    CHECK_FALSE(p.regulatory_window);
    // ties share their mean rank: doubled ranks of (1, 1, 2) are (3, 3, 6); -0.0 ties 0.0
    CHECK(im::doubled_ranks({1, 1, 2}) == std::vector<long long>{3, 3, 6});
    CHECK(im::doubled_ranks({0.0, -0.0, -1.0}) == std::vector<long long>{5, 5, 2});
    // identical series: spearman 1, KS 0, green
    std::vector<double> x(250);
    for (std::size_t k = 0; k < x.size(); ++k) x[k] = std::sin(double(k));
    const im::Pla same_series = im::pla(x, x);
    CHECK(same_series.spearman == 1.0);
    CHECK(same_series.ks_count == 0);
    CHECK(same_series.zone == "GREEN");
    CHECK(same_series.regulatory_window);
    // reversed order: spearman -1
    std::vector<double> rev(x.rbegin(), x.rend());
    CHECK(im::spearman({1, 2, 3, 4}, {4, 3, 2, 1}) == -1.0);
    // MAR32.42 printed p-values 0.264 (KS 0.09) and 0.055 (KS 0.12) at n = 250, within the 1e-3 fixed in the spec
    CHECK(std::fabs(im::pla_ks_pvalue(0.09, 250) - 0.264) <= 1e-3);
    CHECK(std::fabs(im::pla_ks_pvalue(0.12, 250) - 0.055) <= 1e-3);
    CHECK(near(im::pla_ks_pvalue(0.09, 250), 0.2633806324222574));
    CHECK(im::pla_ks_pvalue(0.0, 10) == 1.0);
    // the theta series (x < 1) and the alternating series (x >= 1) agree at the switch
    CHECK(std::fabs(im::kolmogorov_q(std::nextafter(1.0, 0.0)) - im::kolmogorov_q(1.0)) <= 1e-14);
    CHECK(std::fabs(im::kolmogorov_q(1.0) - 0.26999967167735456) <= 1e-15);
    CHECK(im::kolmogorov_q(0.05) == 1.0);
    CHECK(im::kolmogorov_q(30.0) == 0.0);
    CHECK_THROWS_AS(im::pla_ks_pvalue(1.5, 10), quantforge::Error);
    CHECK_THROWS_AS(im::pla_ks_pvalue(0.5, 0), quantforge::Error);
    CHECK_THROWS_AS(im::spearman({1, 1, 1}, {1, 2, 3}), quantforge::Error);
    CHECK_THROWS_AS(im::spearman({1, 2, 3}, {2, 2, 2}), quantforge::Error);
    CHECK_THROWS_AS(im::pla({1, 2}, {1, 2}), quantforge::Error);
    CHECK_THROWS_AS(im::pla({1, 2, 3}, {1, 2}), quantforge::Error);
    CHECK_THROWS_AS(im::pla(std::vector<double>(1000001, 0.0), {1.0}), quantforge::Error);
}

TEST_CASE("PLA zones on the integer KS count (KR-56)", "[frtb_drc_ima]") {
    // n = 100: green needs KS count below 9, red above 12; spearman 1 throughout (rtpl a shifted copy of hpl)
    std::vector<double> h(100), r(100);
    for (std::size_t k = 0; k < 100; ++k) h[k] = double(k);
    const auto zone_for_shift = [&](double shift) {
        for (std::size_t k = 0; k < 100; ++k) r[k] = h[k] + shift;
        return im::pla(h, r);
    };
    CHECK(zone_for_shift(8.0).ks_count == 8);
    CHECK(zone_for_shift(8.0).zone == "GREEN");
    CHECK(zone_for_shift(9.0).zone == "AMBER");
    CHECK(zone_for_shift(12.0).zone == "AMBER");
    CHECK(zone_for_shift(13.0).zone == "RED");
}

TEST_CASE("liquidity horizons (MAR33.12, KR-60, KR-306)", "[frtb_drc_ima]") {
    using Cs = std::vector<std::pair<double, long long>>;
    // lh_k-0001: IR volatility 60, maturity 30 days: next horizon at or above 30 is 40
    im::Lh l = im::liquidity_horizon(std::string("IR_volatility"), std::nullopt, std::nullopt, 30.0);
    CHECK(l.n == 40);
    CHECK(l.table_n == 60);
    CHECK(l.rule == "table+maturity");
    // a maturity at or above the table horizon changes nothing
    CHECK(im::liquidity_horizon(std::string("EQ_large_cap"), std::nullopt, std::nullopt, 400.0).rule == "table");
    // footnote 309 pairs in either order, and first-order crosses (EUR/JPY listed; GBP/CAD through USD)
    CHECK(im::fx_pair_specified("EUR/USD"));
    CHECK(im::fx_pair_specified("GBP/CAD"));
    CHECK_FALSE(im::fx_pair_specified("XAU/XAG"));
    l = im::liquidity_horizon(std::nullopt, std::string("GBP/CAD"), std::nullopt, std::nullopt);
    CHECK(l.n == 10);
    CHECK(l.rule == "fx_pair");
    CHECK(im::liquidity_horizon(std::nullopt, std::string("XAU/XAG"), std::nullopt, std::nullopt).n == 20);
    // MAR33.12 FAQ5: weighted average 12 days goes up to 20
    l = im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{0.8, 10}, {0.2, 20}}, std::nullopt);
    CHECK(l.n == 20);
    CHECK(l.rule == "index");
    CHECK(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{1.0, 120}}, 5.0).n == 10);
    CHECK(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{0.5, 120}, {0.5, 120}}, std::nullopt).n == 120);
    // errors: structure before domain
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, std::nullopt, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{}, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::string("USD/USD"), std::nullopt, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::string("IR_other"), std::nullopt, std::nullopt, 0.0), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{-0.5, 10}, {1.5, 10}}, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{1.0, 15}}, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, Cs{{0.5, 10}}, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::liquidity_horizon(std::nullopt, std::nullopt, Cs(100001, {0.0, 10}), std::nullopt), quantforge::Error);
    const std::string op = "risk.frtb.ima.lh";
    CHECK(code(op, R"({"category":"IR_nothing"})") == "E_SCHEMA");
    CHECK(code(op, R"({"fx_pair":"usd/eur"})") == "E_SCHEMA");
    CHECK(code(op, R"({"fx_pair":"USDEUR"})") == "E_SCHEMA");
    CHECK(code(op, R"({"category":"IR_other","fx_pair":"USD/EUR"})") == "E_INPUT");
    CHECK(code(op, R"({"constituents":[{"weight":1,"n":10.5}]})") == "E_SCHEMA");
    CHECK(code(op, R"({"constituents":[{"weight":1,"n":10}],"maturity_days":"NaN"})") == "E_DOMAIN");
    CHECK(code(op, R"({"constituents":[{"weight":1,"n":10}]})") == "ok");
}

TEST_CASE("ES with liquidity horizons, stressed ES, IMCC and SES by hand (MAR33.4 to MAR33.17)", "[frtb_drc_ima]") {
    // KR-57: the computed normal factor is within one ulp of the printed constant
    CHECK(std::fabs(im::normal_es_factor() - 2.337802792201415) <= 4.5e-16);
    // weights (1, 1, 2, 2, 6): sqrt(1 + 1 + 2 + 2 + 6) for unit ES at every horizon
    CHECK(near(im::es_cascade({1, 1, 1, 1, 1}), std::sqrt(12.0)));
    im::EsLh e = im::es_lh(std::vector<double>{3, 0, 0, 0, 0}, std::nullopt, std::nullopt);
    CHECK(e.mode == "es_t");
    CHECK(e.es == 3.0);
    e = im::es_lh(std::nullopt, std::vector<double>{1, 0, 0, 0, 0}, std::nullopt);
    CHECK(near(e.es, 2.3378027922014146));
    // pnl mode: the historical ES at 0.975 of each list; an empty list is 0
    std::vector<double> pnl(40);
    for (std::size_t k = 0; k < pnl.size(); ++k) pnl[k] = double(k) - 20.0;  // losses 20, 19, ...; w = 1: ES 20
    e = im::es_lh(std::nullopt, std::nullopt, std::vector<std::vector<double>>{pnl, {}, {}, {}, {}});
    CHECK(e.mode == "pnl");
    CHECK(near(e.es_by_horizon[0], 20.0));
    CHECK(e.es_by_horizon[1] == 0.0);
    CHECK_THROWS_AS(im::es_lh(std::nullopt, std::nullopt, std::vector<std::vector<double>>{{5.0, 6.0}, {}, {}, {}, {}}),
                    quantforge::Error);  // KR-307: a tail of gains
    CHECK_THROWS_AS(im::es_lh(std::vector<double>{1, 1, 1, 1}, std::nullopt, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::es_lh(std::vector<double>{1, 1, -1, 1, 1}, std::nullopt, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::es_lh(std::nullopt, std::nullopt, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::es_lh(std::nullopt, std::nullopt, std::vector<std::vector<double>>{std::vector<double>(1000001, 0.0)}),
                    quantforge::Error);
    // est_k-0001: 12 x 10 / 8 = 15; ratio below 1 floored
    im::Stressed s = im::es_stressed({12, 10, 8});
    CHECK(s.ratio == 1.25);
    CHECK_FALSE(s.ratio_floored);
    CHECK(s.es == 15.0);
    s = im::es_stressed({12, 4, 8});
    CHECK(s.ratio_floored);
    CHECK(s.es == 12.0);
    CHECK_THROWS_AS(im::es_stressed({-1, 1, 1}), quantforge::Error);
    CHECK_THROWS_AS(im::es_stressed({1, 1, 0}), quantforge::Error);
    // imcc_k-0001: 0.5 x 15 + 0.5 x (7.5 + 5) = 13.75
    const im::Imcc c = im::imcc({12, 10, 8}, {{"IR", {6, 5, 4}}, {"EQ", {5, 4, 5}}});
    CHECK(c.imcc == 13.75);
    CHECK(c.classes[0].first == "IR");
    CHECK(c.classes[1].first == "EQ");
    CHECK(c.classes_floored == std::vector<std::string>{"EQ"});
    CHECK_THROWS_AS(im::imcc({1, 1, 1}, {}), quantforge::Error);
    CHECK_THROWS_AS(im::imcc({1, 1, 1}, {{"FX", {1, 1, 0}}}), quantforge::Error);
    // ses_k-0001: 5 + 13 + sqrt((0.6 x 5)^2 + 0.64 x 9)
    const im::Ses x = im::ses({3, 4}, {5, 12}, {1, 2, 2});
    CHECK(near(x.idio_credit, 5.0));
    CHECK(near(x.idio_equity, 13.0));
    CHECK(near(x.other, std::sqrt(9.0 + 0.64 * 9.0)));
    CHECK(near(x.ses, 18.0 + std::sqrt(9.0 + 0.64 * 9.0)));
    CHECK(im::ses({}, {}, {}).ses == 0.0);
    CHECK_THROWS_AS(im::ses({1}, {-1}, {}), quantforge::Error);
    CHECK_THROWS_AS(im::ses(std::vector<double>(100001, 0.0), {}, {}), quantforge::Error);
}

TEST_CASE("capital aggregation by hand (MAR33.41 to MAR33.45, KR-61, KR-308)", "[frtb_drc_ima]") {
    // cap_k-0001: m_c 1.76; C_A = max(120, 1.76 x 90 + 15) = 173.4
    im::CapitalInput in{100, 20, 90, 15, 6, 0, {{"GREEN", 200}}, 0, 1000};
    im::Capital c = im::capital(in);
    CHECK(c.m_c == 1.76);
    CHECK(near(c.c_a, 173.4));
    CHECK(c.k == 0.0);
    CHECK(near(c.acr_total, 173.4));
    // an amber desk: k = 0.5 x 100 / 300; surcharge k (300 - 173.4)
    in.desks = {{"GREEN", 200}, {"AMBER", 100}};
    c = im::capital(in);
    CHECK(near(c.k, 0.5 * 100.0 / 300.0));
    CHECK(near(c.surcharge, c.k * (300.0 - 173.4)));
    CHECK(near(c.acr_total, 173.4 + c.surcharge));
    // ten exceptions or more: 2.00; qualitative add-on on top
    CHECK(im::multiplier(10) == 2.0);
    CHECK(im::multiplier(250) == 2.0);
    CHECK(im::multiplier(0) == 1.5);
    in.exceptions = 12;
    in.qualitative_addon = 0.25;
    CHECK(im::capital(in).m_c == 2.25);
    // no desks: SA_G,A = 0 and the whole IMA_G,A is added again (KR-308, as written)
    in.desks = {};
    in.exceptions = 0;
    in.qualitative_addon = 0.0;
    c = im::capital(in);
    CHECK(near(c.acr_total, std::min(c.ima_ga, 1000.0) + c.ima_ga));
    in.desks = {{"AMBER", 0}};
    CHECK_THROWS_AS(im::capital(in), quantforge::Error);
    in.desks = {{"GREEN", -1}};
    CHECK_THROWS_AS(im::capital(in), quantforge::Error);
    in.desks = {};
    in.exceptions = -1;
    CHECK_THROWS_AS(im::capital(in), quantforge::Error);
    in.exceptions = 0;
    in.c_u = -1;
    CHECK_THROWS_AS(im::capital(in), quantforge::Error);
    in.c_u = 0;
    in.desks = std::vector<std::pair<std::string, double>>(100001, {"GREEN", 1.0});
    CHECK_THROWS_AS(im::capital(in), quantforge::Error);
    const std::string op = "risk.frtb.ima.capital";
    const std::string base = R"("imcc_prev":1,"ses_prev":1,"imcc_avg":1,"ses_avg":1,"drc":0,"c_u":0,"sa_all":10)";
    CHECK(code(op, "{" + base + R"(,"exceptions":2,"desks":[{"zone":"GREEN","sa":1}]})") == "ok");
    CHECK(code(op, "{" + base + R"(,"exceptions":2,"desks":[{"zone":"RED","sa":1}]})") == "E_SCHEMA");
    CHECK(code(op, "{" + base + R"(,"exceptions":2.5,"desks":[]})") == "E_SCHEMA");
    CHECK(code(op, "{" + base + R"(,"exceptions":-2,"desks":[{"zone":"GREEN","sa":"Infinity"}]})") == "E_DOMAIN");
}

TEST_CASE("RFET windows and buckets (MAR31.13, MAR31.16, KR-59, KR-309)", "[frtb_drc_ima]") {
    using quantforge::Date;
    // months back clamps the day to the target month's end
    CHECK(im::months_back(make_date(2024, 2, 29), 12) == make_date(2023, 2, 28));
    CHECK(im::months_back(make_date(2026, 3, 31), 1) == make_date(2026, 2, 28));
    CHECK(im::months_back(make_date(2026, 1, 15), 13) == make_date(2024, 12, 15));
    // one observation every 7 days through the year: every 90-day window holds 12 or 13; 53 days: criterion 1
    std::vector<Date> obs;
    const Date as_of = make_date(2026, 6, 30);
    for (Date d = make_date(2025, 7, 1); d <= as_of; d += std::chrono::days(7)) obs.push_back(d);
    obs.push_back(obs.front());  // duplicates count once
    obs.push_back(make_date(2020, 1, 1));  // outside the window: ignored
    im::Rfet r = im::rfet(as_of, obs);
    CHECK(r.window_start == make_date(2025, 7, 1));
    CHECK(r.distinct_days == 53);
    CHECK(*r.min_window_count >= 12);
    CHECK_FALSE(r.first_failing_window_start.has_value());
    CHECK(r.crit1);
    CHECK_FALSE(r.crit2);
    CHECK(r.pass);
    // nothing observed: the first window fails with 0
    r = im::rfet(as_of, {});
    CHECK(*r.first_failing_window_start == make_date(2025, 7, 1));
    CHECK(*r.first_failing_window_count == 0);
    CHECK(*r.min_window_count == 0);
    CHECK_FALSE(r.pass);
    CHECK_THROWS_AS(im::rfet(as_of, std::vector<Date>(100001, as_of)), quantforge::Error);
    // buckets: lower bound inclusive, upper exclusive; the last row-A bucket is open; row D ends below 1
    im::RfetBucket b = im::rfet_bucket("A", 0.75, std::nullopt);
    CHECK(b.bucket == 2);
    CHECK(b.lower == 0.75);
    CHECK(b.upper == 1.5);
    b = im::rfet_bucket("A", 50.0, std::nullopt);
    CHECK(b.bucket == 9);
    CHECK_FALSE(b.upper.has_value());
    b = im::rfet_bucket("D", std::nullopt, 0.97);
    CHECK(b.bucket == 5);
    CHECK(b.upper == 1.0);
    CHECK(im::rfet_bucket("C", 0.0, std::nullopt).bucket == 1);
    CHECK_THROWS_AS(im::rfet_bucket("D", std::nullopt, 1.0), quantforge::Error);
    CHECK_THROWS_AS(im::rfet_bucket("B", -0.1, std::nullopt), quantforge::Error);
    CHECK_THROWS_AS(im::rfet_bucket("D", 1.0, 0.5), quantforge::Error);
    CHECK_THROWS_AS(im::rfet_bucket("A", std::nullopt, std::nullopt), quantforge::Error);
    const json::Parsed p = run("risk.frtb.rfet", R"({"as_of":"2026-06-30","observations":[]})");
    const json::Value& o = *p.value.find("outputs");
    CHECK(o.find("window_start")->text == "2025-07-01");
    CHECK(o.find("first_failing_window_start")->text == "2025-07-01");
    CHECK(code("risk.frtb.rfet", R"({"as_of":"2026-06-30","observations":["2026-02-30"]})") == "E_SCHEMA");
    CHECK(code("risk.frtb.rfet.bucket", R"({"row":"E","t":1})") == "E_SCHEMA");
    CHECK(code("risk.frtb.rfet.bucket", R"({"row":"A","t":1,"delta":0.5})") == "E_INPUT");
}

TEST_CASE("IMA CLI errors in KR-67 order and the KR-67 page limits", "[frtb_drc_ima]") {
    // pla: a non-finite point (E_DOMAIN) before different lengths (E_INPUT)
    CHECK(code("risk.frtb.pla", R"({"hpl":[1,2,"NaN"],"rtpl":[1,2]})") == "E_DOMAIN");
    CHECK(code("risk.frtb.pla", R"({"hpl":[1,2,3],"rtpl":[1,2]})") == "E_INPUT");
    CHECK(code("risk.frtb.pla", R"({"hpl":[1,2,3],"rtpl":"x"})") == "E_SCHEMA");
    // P&L lists above the general 100,000 cap are allowed (KR-67: 1,000,000)
    std::string big = R"({"hpl":[)";
    for (int k = 0; k < 100001; ++k) big += (k ? "," : "") + std::to_string(k % 997);
    std::string body = big.substr(8);
    CHECK(code("risk.frtb.pla", big + R"(],"rtpl":[)" + body + "]}") == "ok");
    CHECK(code("risk.frtb.ima.ses", R"({"idio_credit":[)" + body + R"(],"idio_equity":[],"other":[]})") == "E_LIMIT");
    std::string losses;  // P&L of -(k mod 997): a positive ES
    for (int k = 0; k < 100001; ++k) losses += (k ? ",-" : "-") + std::to_string(k % 997);
    CHECK(code("risk.frtb.ima.es_lh", R"({"pnl":[[)" + losses + "],[],[],[],[]]}") == "ok");
    CHECK(code("risk.frtb.ima.es_lh", R"({"pnl":[[)" + body + "],[],[],[],[]]}") == "E_DOMAIN");  // KR-307
    CHECK(code("risk.frtb.ima.es_lh", R"({"es_t":[1,1,1,1,1],"sigma":[1,1,1,1,1]})") == "E_INPUT");
    CHECK(code("risk.frtb.ima.es_lh", R"({"sigma":[1,1,1,1,"Infinity"]})") == "E_DOMAIN");
    CHECK(code("risk.frtb.ima.es_lh", R"({"pnl":[[1],[2],[3]]})") == "E_INPUT");
    CHECK(code("risk.frtb.pla.ks_pvalue", R"({"ks":0.1,"n":2.5})") == "E_SCHEMA");
    CHECK(code("risk.frtb.pla.ks_pvalue", R"({"ks":0.1,"n":0})") == "E_DOMAIN");
    CHECK(code("risk.frtb.ima.imcc", R"({"portfolio":{"es_rs":1,"es_fc":1,"es_rc":1},"classes":{"XX":{"es_rs":1,"es_fc":1,"es_rc":1}}})") == "E_SCHEMA");
    CHECK(code("risk.frtb.ima.imcc", R"({"portfolio":{"es_rs":1,"es_fc":1,"es_rc":1},"classes":{}})") == "E_INPUT");
    CHECK(code("risk.frtb.ima.imcc", R"({"portfolio":[],"classes":{}})") == "E_SCHEMA");
    CHECK(code("risk.frtb.ima.es_stressed", R"({"es_rs":1,"es_fc":1,"es_rc":0})") == "E_DOMAIN");
    const json::Parsed p = run("risk.frtb.ima.imcc", R"({"portfolio":{"es_rs":12,"es_fc":10,"es_rc":8},"classes":{"CS":{"es_rs":1,"es_fc":1,"es_rc":2}}})");
    CHECK(p.value.find("outputs")->find("classes_floored")->items.at(0).text == "CS");
}
