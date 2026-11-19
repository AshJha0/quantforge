// K-4b on the stage B production bootstrap (incremental-update.md, Acceptance, third line; ruling KR-5):
// on 10,000 quote moves over every sequential stage B instrument set, the incremental path equals a full
// rebuild to 1e-12 relative and the copied pillars are bit-identical to the cache. The sets and the move
// plan are those of the Python test (test_stage_k_w1.py); the random part draws from the SplitMix64 stream
// seeded 20261119, as the Rust test does.
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <variant>
#include <vector>

#include "quantforge/core/dates.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/rates.hpp"

using namespace quantforge;

#ifdef QF_REPO_DIR
namespace {

constexpr double bp = 1e-4;

using Q = std::variant<OisQuote, ProjectionQuote>;

bool same_quote(const Q& a, const Q& b) {
    if (a.index() != b.index()) return false;
    if (const auto* x = std::get_if<OisQuote>(&a)) {
        const auto& y = std::get<OisQuote>(b);
        return x->tenor.count == y.tenor.count && x->tenor.unit == y.tenor.unit &&
               std::bit_cast<std::uint64_t>(x->rate) == std::bit_cast<std::uint64_t>(y.rate);
    }
    const auto& x = std::get<ProjectionQuote>(a);
    const auto& y = std::get<ProjectionQuote>(b);
    return x.type == y.type && x.months == y.months &&
           std::bit_cast<std::uint64_t>(x.rate) == std::bit_cast<std::uint64_t>(y.rate);
}

Q shifted(const Q& q, double d) {
    if (const auto* o = std::get_if<OisQuote>(&q)) return OisQuote{o->tenor, o->rate + d};
    ProjectionQuote p = std::get<ProjectionQuote>(q);
    p.rate += d;
    return p;
}

Tenor tenor_of(const std::string& s) { return Tenor{std::stoi(s.substr(0, s.size() - 1)), s.back()}; }

Date date_of(const json::Value& v, const char* k) { return *parse_date(v.find(k)->text); }

std::vector<Jump> jumps_of(const json::Value& v) {
    std::vector<Jump> out;
    if (const json::Value* j = v.find("jumps"))
        for (const json::Value& x : j->items) out.push_back({date_of(x, "date"), x.find("factor")->number});
    return out;
}

CurveInterpolation interp_of(const std::string& s) {
    return s == "LINEAR_ZERO" ? CurveInterpolation::LinearZero : CurveInterpolation::LogLinearDf;
}

struct IncSet {
    std::string id;
    const RateConvention* convention = nullptr;  // OIS sets
    std::vector<Jump> jumps;
    std::optional<Curve> discount;  // projection sets
    const RateConvention* index = nullptr;
    Date as_of{};
    CurveInterpolation interpolation{};
    std::vector<Q> quotes;

    template <class T>
    static std::vector<T> as(const std::vector<Q>& q) {
        std::vector<T> out;
        for (const Q& x : q) out.push_back(std::get<T>(x));
        return out;
    }

    SolvedCurve solve(const std::vector<Q>& q) const {
        if (convention)
            return ois_bootstrap(*convention, as_of, as<OisQuote>(q), interpolation, SolveMethod::Sequential, jumps);
        double e = 0.0;
        Curve c = projection_bootstrap(*discount, *index, as_of, as<ProjectionQuote>(q), interpolation, &e);
        return {std::move(c), e};
    }

    IncrementalCurve incremental(const std::vector<Q>& prev, const std::vector<double>& f,
                                 const std::vector<Q>& next) const {
        if (convention)
            return ois_bootstrap_incremental(*convention, as_of, as<OisQuote>(prev), f, as<OisQuote>(next),
                                             interpolation, jumps);
        return projection_bootstrap_incremental(*discount, *index, as_of, as<ProjectionQuote>(prev), f,
                                                as<ProjectionQuote>(next), interpolation);
    }
};

std::vector<double> factors(const Curve& c) {
    std::vector<double> out;
    for (const Pillar& p : c.pillars()) out.push_back(p.discount_factor);
    return out;
}

std::vector<IncSet> load_sets() {
    std::vector<IncSet> out;
    const std::pair<const char*, const char*> files[] = {
        {"stage_b", "ois"}, {"stage_b", "projection"}, {"stage_b", "projection_deep"}, {"stage_d", "ois_d"}};
    for (const auto& [folder, name] : files) {
        std::ifstream f(std::string(QF_REPO_DIR) + "/datasets/golden/" + folder + "/" + name + ".json",
                        std::ios::binary);
        std::stringstream s;
        s << f.rdbuf();
        const json::Value doc = json::parse(s.str()).value;
        for (const json::Value& c : doc.find("cases")->items) {
            const json::Value& i = *c.find("inputs");
            const std::string op = c.find("operation")->text;
            const std::string interp = i.find("interpolation")->text;
            const json::Value* method = i.find("method");
            if (!op.ends_with(".bootstrap") || c.find("expected")->find("status")->text != "ok" ||
                (method && method->text != "SEQUENTIAL") || (interp != "LOG_LINEAR_DF" && interp != "LINEAR_ZERO") ||
                i.find("tension") || i.find("step_end"))
                continue;
            IncSet set;
            set.id = c.find("case_id")->text;
            set.as_of = date_of(i, "as_of");
            if (op == "rates.ois.bootstrap") {
                set.convention = rate_convention(i.find("convention")->text);
                set.jumps = jumps_of(i);
                set.interpolation = interp_of(interp);
                for (const json::Value& q : i.find("quotes")->items) {
                    const json::Value* r = q.find("rate");
                    const double rate = r ? r->number : (q.find("bid")->number + q.find("ask")->number) / 2.0;
                    set.quotes.emplace_back(OisQuote{tenor_of(q.find("tenor")->text), rate});
                }
                out.push_back(std::move(set));
            } else if (op == "rates.projection.bootstrap") {
                const json::Value& d = *i.find("discount");
                std::vector<Pillar> pillars;
                for (const json::Value& p : d.find("pillars")->items)
                    pillars.push_back({date_of(p, "date"), p.find("discount_factor")->number});
                set.discount.emplace(date_of(d, "as_of"), interp_of(d.find("interpolation")->text), pillars, jumps_of(d));
                set.index = rate_convention(i.find("index")->text);
                for (const json::Value& q : i.find("quotes")->items) {
                    const std::string t = q.find("type")->text;
                    const ProjectionQuoteType type = t == "DEPOSIT" ? ProjectionQuoteType::Deposit
                                                     : t == "FRA"   ? ProjectionQuoteType::Fra
                                                                    : ProjectionQuoteType::Swap;
                    const double months = q.find(type == ProjectionQuoteType::Fra ? "start_months" : "months")->number;
                    set.quotes.emplace_back(ProjectionQuote{type, static_cast<long long>(months), q.find("rate")->number});
                }
                for (const CurveInterpolation m : {CurveInterpolation::LogLinearDf, CurveInterpolation::LinearZero}) {
                    IncSet copy = set;
                    copy.interpolation = m;
                    copy.id += m == CurveInterpolation::LinearZero ? "/LINEAR_ZERO" : "/LOG_LINEAR_DF";
                    out.push_back(std::move(copy));
                }
            }
        }
    }
    return out;
}

// SplitMix64, as in the Rust test, so the random part is reproducible without a library.
struct IncRng {
    std::uint64_t s;
    std::uint64_t next() {
        s += 0x9E3779B97F4A7C15ULL;
        std::uint64_t z = s;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }
    std::size_t below(std::size_t n) { return static_cast<std::size_t>(next() % n); }
    double unit() { return static_cast<double>(next() >> 11) / static_cast<double>(1ULL << 53); }
};

struct IncMove {
    std::size_t set;
    std::string kind;
    std::vector<Q> prev, next;
};

std::vector<IncMove> inc_plan(const std::vector<IncSet>& sets, std::size_t total, std::uint64_t seed) {
    std::vector<IncMove> out;
    for (std::size_t s = 0; s < sets.size(); ++s) {
        const auto& base = sets[s].quotes;
        const std::size_t n = base.size();
        out.push_back({s, "none", base, base});
        for (std::size_t j = 0; j < n; ++j) {
            auto q = base;
            q[j] = shifted(base[j], bp);
            out.push_back({s, j == 0 ? "single_first" : j == n - 1 ? "single_last" : "single_middle", base, q});
        }
        auto both = base;
        both[0] = shifted(base[0], -bp);
        both[n - 1] = shifted(base[n - 1], -bp);
        out.push_back({s, "multi_first_and_last", base, both});
        std::vector<Q> all;
        for (const Q& q : base) all.push_back(shifted(q, 2.0 * bp));
        out.push_back({s, "multi_all", base, all});
    }
    IncRng rng{seed};
    while (out.size() < total) {
        const std::size_t s = rng.below(sets.size());
        const auto& base = sets[s].quotes;
        const std::size_t n = base.size();
        std::vector<Q> prev;
        for (const Q& q : base) prev.push_back((rng.next() & 1U) == 1U ? shifted(q, (rng.unit() * 2.0 - 1.0) * 50.0 * bp) : q);
        std::vector<std::size_t> idx(n);
        for (std::size_t k = 0; k < n; ++k) idx[k] = k;
        for (std::size_t k = n - 1; k >= 1; --k) std::swap(idx[k], idx[rng.below(k + 1)]);
        idx.resize(1 + rng.below(n));
        std::sort(idx.begin(), idx.end());
        auto next = prev;
        for (const std::size_t k : idx) {
            const double size = (0.01 + rng.unit() * 24.99) * bp;
            next[k] = shifted(prev[k], (rng.next() & 1U) == 1U ? size : -size);
        }
        const char* where = idx[0] == 0 ? "first" : idx[0] == n - 1 ? "last" : "middle";
        out.push_back({s, std::string(idx.size() > 1 ? "multi_" : "single_") + where, prev, next});
    }
    return out;
}

}  // namespace

TEST_CASE("K-4b: incremental stage B bootstrap equals a full rebuild on 10,000 moves", "[stage_k]") {
    const std::vector<IncSet> sets = load_sets();
    REQUIRE(sets.size() == 25);
    const std::vector<IncMove> moves = inc_plan(sets, 10000, 20261119ULL);
    REQUIRE(moves.size() == 10000);
    double worst = 0.0;
    std::size_t bit_equal = 0;
    std::map<std::string, int> kinds;
    for (const IncMove& m : moves) {
        const IncSet& s = sets[m.set];
        const std::vector<double> cache = factors(s.solve(m.prev).curve);
        const IncrementalCurve inc = s.incremental(m.prev, cache, m.next);
        const SolvedCurve full = s.solve(m.next);
        const std::vector<double> got = factors(inc.solved.curve), want = factors(full.curve);
        const std::size_t n = m.next.size();
        std::optional<std::size_t> first;
        for (std::size_t k = 0; k < n && !first; ++k)
            if (!same_quote(m.prev[k], m.next[k])) first = k;
        INFO(s.id << " " << m.kind);
        REQUIRE(inc.first_changed_index == first);
        REQUIRE(inc.recomputed == (first ? n - *first : 0));
        const std::size_t j = first.value_or(n);
        for (std::size_t k = 0; k < j; ++k)
            REQUIRE(std::bit_cast<std::uint64_t>(cache[k]) == std::bit_cast<std::uint64_t>(got[k]));
        bool same = inc.solved.max_repricing_error == full.max_repricing_error;
        for (std::size_t k = 0; k < n; ++k) {
            const double rel = std::fabs(got[k] - want[k]) / std::max(std::fabs(want[k]), 1e-300);
            worst = std::max(worst, rel);
            REQUIRE(rel <= 1e-12);
            same = same && std::bit_cast<std::uint64_t>(got[k]) == std::bit_cast<std::uint64_t>(want[k]);
        }
        bit_equal += same ? 1U : 0U;
        ++kinds[m.kind];
    }
    CHECK(kinds.contains("single_first"));
    CHECK(kinds.contains("single_last"));
    CHECK(kinds.contains("multi_first"));
    CHECK(kinds.contains("multi_all"));
    INFO("worst relative difference " << worst);
    CHECK(bit_equal == moves.size());
}

TEST_CASE("K-4b: incremental stage B errors and a changed tenor", "[stage_k]") {
    const std::vector<IncSet> sets = load_sets();
    const IncSet& s = *std::find_if(sets.begin(), sets.end(), [](const IncSet& x) { return x.convention != nullptr; });
    const auto& q = s.quotes;
    const std::vector<double> f = factors(s.solve(q).curve);
    const auto code = [](auto&& call) {
        try {
            call();
        } catch (const Error& e) {
            return std::string(e.code());
        }
        return std::string("none");
    };
    auto stale = f;
    stale.back() = std::nextafter(stale.back(), 2.0);
    CHECK(code([&] { s.incremental(q, stale, q); }) == "E_INPUT");
    CHECK(code([&] { s.incremental(q, f, std::vector<Q>(q.begin(), q.end() - 1)); }) == "E_INPUT");
    CHECK(code([&] { s.incremental(q, std::vector<double>(f.begin(), f.end() - 1), q); }) == "E_INPUT");
    IncSet smooth = s;
    smooth.interpolation = CurveInterpolation::MonotoneConvex;
    CHECK(code([&] { smooth.incremental(q, f, q); }) == "E_INPUT");
    CHECK(code([&] { ois_bootstrap_incremental(*s.convention, s.as_of, {}, {}, {}, s.interpolation); }) == "E_INPUT");
    const IncrementalCurve none = s.incremental(q, f, q);
    CHECK(!none.first_changed_index);
    CHECK(none.recomputed == 0);
    CHECK(factors(none.solved.curve) == f);
    // a changed tenor is a changed instrument: its pillar and every later one are solved again
    auto longer = q;
    OisQuote last = std::get<OisQuote>(q.back());
    CHECK((last.tenor.count == 30 && last.tenor.unit == 'Y'));
    last.tenor.count = 25;
    longer.back() = last;
    const IncrementalCurve t = s.incremental(q, f, longer);
    CHECK(t.first_changed_index == q.size() - 1);
    CHECK(t.recomputed == 1);
    const IncSet& p = *std::find_if(sets.begin(), sets.end(), [](const IncSet& x) { return x.discount.has_value(); });
    auto pf = factors(p.solve(p.quotes).curve);
    pf[0] = 0.5;
    CHECK(code([&] { p.incremental(p.quotes, pf, p.quotes); }) == "E_INPUT");
}
#endif
