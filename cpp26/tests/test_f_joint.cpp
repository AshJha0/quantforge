// Stage F wave 1b unit tests (Q4 joint solve, funding curve). No namespace-scope static objects.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/joint.hpp"
#include "quantforge/core/rates.hpp"

using namespace quantforge;

namespace {

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "OK";
}

Date as_of() { return make_date(2026, 11, 9); }

JointCurveSpec sofr(CurveInterpolation m = CurveInterpolation::LogLinearDf, std::vector<Date> turns = {}) {
    JointCurveSpec c;
    c.name = "USD-SOFR";
    c.type = JointCurveType::Ois;
    c.convention = rate_convention("SOFR");
    c.interpolation = m;
    c.turns = std::move(turns);
    return c;
}

JointCurveSpec term() {
    JointCurveSpec c;
    c.name = "USD-TERM-3M";
    c.type = JointCurveType::Projection;
    c.convention = rate_convention("USD-TERM-3M");
    c.discount = "USD-SOFR";
    return c;
}

JointInstrument ois(const std::string& id, int count, char unit, double rate, bool turn = false) {
    JointInstrument j;
    j.id = id;
    j.curve = "USD-SOFR";
    j.type = JointInstrumentType::Ois;
    j.tenor = {count, unit};
    j.rate = rate;
    j.turn = turn;
    return j;
}

JointInstrument proj(const std::string& id, JointInstrumentType t, long long months, double rate) {
    JointInstrument j;
    j.id = id;
    j.curve = "USD-TERM-3M";
    j.type = t;
    j.months = months;
    j.rate = rate;
    return j;
}

std::vector<JointInstrument> sofr_quotes() {
    return {ois("S1M", 1, 'M', 0.043), ois("S3M", 3, 'M', 0.0425), ois("S6M", 6, 'M', 0.0412), ois("S1Y", 1, 'Y', 0.039),
            ois("S2Y", 2, 'Y', 0.0365), ois("S5Y", 5, 'Y', 0.0352)};
}

std::vector<JointInstrument> two_curve_quotes() {
    auto q = sofr_quotes();
    q.push_back(proj("TDEP", JointInstrumentType::Deposit, 3, 0.0445));
    q.push_back(proj("TFRA", JointInstrumentType::Fra, 3, 0.0432));
    q.push_back(proj("TSW2", JointInstrumentType::Swap, 24, 0.0388));
    q.push_back(proj("TSW5", JointInstrumentType::Swap, 60, 0.0376));
    return q;
}

}  // namespace

TEST_CASE("joint solve: one OIS curve equals rates.ois.bootstrap") {
    const JointResult r = joint_solve(as_of(), {sofr()}, sofr_quotes());
    std::vector<OisQuote> q;
    for (const JointInstrument& j : sofr_quotes()) q.push_back({j.tenor, j.rate});
    const SolvedCurve s = ois_bootstrap(*rate_convention("SOFR"), as_of(), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential);
    const auto p = s.curve.pillars();
    REQUIRE(p.size() == r.curves[0].pillars.size());
    for (std::size_t i = 0; i < p.size(); ++i) {
        CHECK(p[i].date == r.curves[0].pillars[i].date);
        CHECK(std::fabs(p[i].discount_factor - r.curves[0].pillars[i].discount_factor) < 1e-14);
    }
    CHECK(r.max_repricing_error <= 1e-13);
}

TEST_CASE("joint solve: block structure gives exact zeros and matches bump-and-rebuild") {
    const auto quotes = two_curve_quotes();
    const JointResult r = joint_solve(as_of(), {sofr(), term()}, quotes);
    const std::size_t n = quotes.size();
    REQUIRE(r.jacobian.size() == n);
    // SOFR unknowns (rows 0..5) against term quotes (columns 6..9) are exact zeros.
    for (std::size_t i = 0; i < 6; ++i)
        for (std::size_t j = 6; j < n; ++j) CHECK(r.jacobian[i][j] == 0.0);
    // Bump-and-rebuild, Richardson over h = 1e-4 and 5e-5, for two columns.
    for (const std::size_t q : {std::size_t{3}, std::size_t{8}}) {
        const auto rebuild = [&](double h) {
            auto b = quotes;
            b[q].rate += h;
            const JointResult up = joint_solve(as_of(), {sofr(), term()}, b);
            b[q].rate -= 2.0 * h;
            const JointResult down = joint_solve(as_of(), {sofr(), term()}, b);
            std::vector<double> d;
            for (std::size_t c = 0; c < 2; ++c)
                for (std::size_t i = 0; i < up.curves[c].pillars.size(); ++i)
                    d.push_back((std::log(up.curves[c].pillars[i].discount_factor) - std::log(down.curves[c].pillars[i].discount_factor)) /
                                (2.0 * h));
            return d;
        };
        const auto d1 = rebuild(1e-4), d2 = rebuild(5e-5);
        for (std::size_t i = 0; i < n; ++i) {
            const double ref = (4.0 * d2[i] - d1[i]) / 3.0;
            CHECK(std::fabs(r.jacobian[i][q] - ref) <= 1e-9 + 1e-6 * std::fabs(ref));
        }
    }
}

TEST_CASE("joint solve: a turn quoted at the no-turn par rate has factor 1, and sensitivity is zero off the turn") {
    // The no-turn par rate of a 2M OIS on the curve solved without the turn.
    auto base = sofr_quotes();
    const JointResult plain = joint_solve(as_of(), {sofr()}, base);
    const Curve c(as_of(), CurveInterpolation::LogLinearDf, plain.curves[0].pillars);
    const RateConvention& conv = *rate_convention("SOFR");
    const double par2m = ois_legs(conv, ois_periods(conv, as_of(), {2, 'M'}), c).par();
    auto quotes = base;
    quotes.insert(quotes.begin() + 1, ois("S2M", 2, 'M', par2m, true));
    const JointResult r = joint_solve(as_of(), {sofr(CurveInterpolation::LogLinearDf, {make_date(2026, 12, 31)})}, quotes);
    REQUIRE(r.turn_factors.size() == 1);
    CHECK(std::fabs(r.turn_factors[0].factor - 1.0) < 1e-12);
    REQUIRE(r.turn_sensitivity.size() == 1);
    CHECK(r.turn_sensitivity[0][0] == 0.0);  // 1M ends before the turn
    CHECK(r.turn_sensitivity[0][1] != 0.0);  // 2M spans it
    CHECK(r.unknowns.back() == "USD-SOFR:turn:2026-12-31");
}

TEST_CASE("joint solve: meeting steps fitted to futures") {
    JointCurveSpec s;
    s.name = "STEPS";
    s.type = JointCurveType::OisSteps;
    s.convention = rate_convention("SOFR");
    s.step_dates = {make_date(2026, 12, 10), make_date(2027, 3, 18)};
    JointInstrument a = ois("S1M", 1, 'M', 0.0431);
    a.curve = "STEPS";
    JointInstrument f1, f2;
    f1.id = "Z6";
    f1.curve = "STEPS";
    f1.type = JointInstrumentType::Future;
    f1.start = make_date(2026, 12, 16);
    f1.end = make_date(2027, 3, 17);
    f1.price = 95.82;
    f1.sigma = 0.0085;
    f1.mean_reversion = 0.03;
    f2 = f1;
    f2.id = "H7";
    f2.start = make_date(2027, 3, 17);
    f2.end = make_date(2027, 6, 16);
    f2.price = 96.01;
    const JointResult r = joint_solve(as_of(), {s}, {a, f1, f2});
    CHECK(r.curves[0].steps);
    CHECK(r.curves[0].step_rates.size() == 2);
    CHECK(r.max_repricing_error <= 1e-13);
    // A higher H7 price is a lower futures rate, so a lower last step (dR/dq = 0.01 e^{-z} > 0).
    CHECK(r.jacobian[2][2] < 0.0);
    // A future with end before start is E_INPUT; negative sigma E_DOMAIN.
    auto g = f2;
    g.end = make_date(2027, 3, 1);
    CHECK(code_of([&] { joint_solve(as_of(), {s}, {a, f1, g}); }) == "E_INPUT");
    g = f2;
    g.sigma = -0.01;
    CHECK(code_of([&] { joint_solve(as_of(), {s}, {a, f1, g}); }) == "E_DOMAIN");
}

TEST_CASE("joint solve: input checks") {
    // A curve naming a later curve.
    CHECK(code_of([&] { joint_solve(as_of(), {term(), sofr()}, two_curve_quotes()); }) == "E_INPUT");
    // Duplicate instrument id.
    auto q = sofr_quotes();
    q[1].id = q[0].id;
    CHECK(code_of([&] { joint_solve(as_of(), {sofr()}, q); }) == "E_INPUT");
    // A turn with no turn instrument.
    CHECK(code_of([&] { joint_solve(as_of(), {sofr(CurveInterpolation::LogLinearDf, {make_date(2026, 12, 31)})}, sofr_quotes()); }) ==
          "E_INPUT");
    // Pillars out of order.
    q = sofr_quotes();
    std::swap(q[1], q[2]);
    CHECK(code_of([&] { joint_solve(as_of(), {sofr()}, q); }) == "E_INPUT");
    // A projection instrument on an OIS curve.
    q = sofr_quotes();
    q.push_back(proj("X", JointInstrumentType::Deposit, 3, 0.04));
    q.back().curve = "USD-SOFR";
    CHECK(code_of([&] { joint_solve(as_of(), {sofr()}, q); }) == "E_INPUT");
}

TEST_CASE("funding curve: closed form, zero-spread limit and checks") {
    const Curve d(as_of(), CurveInterpolation::LogLinearDf,
                  {{make_date(2027, 2, 8), 0.98946}, {make_date(2027, 11, 9), 0.96175}, {make_date(2031, 11, 9), 0.83854}});
    // Funding at the OIS simple rates gives zero spreads.
    std::vector<FundingQuote> q;
    for (const Date e : {make_date(2027, 2, 8), make_date(2027, 11, 9), make_date(2031, 11, 9)}) {
        const double tau = double(days_between(as_of(), e)) / 360.0;
        q.push_back({e, (1.0 / d.discount(e) - 1.0) / tau});
    }
    const FundingCurve z = funding_curve(d, q, {make_date(2029, 1, 1)});
    for (const double s : z.spreads) CHECK(std::fabs(s) < 1e-14);
    CHECK(std::fabs(z.discount_factors[0] - d.discount(make_date(2029, 1, 1))) < 1e-15);
    // Pillars reprice the funding quotes: D_f(end) = 1 / (1 + rate tau).
    q[1].rate += 0.004;
    const FundingCurve f = funding_curve(d, q, {});
    const double tau = double(days_between(as_of(), q[1].end)) / 360.0;
    CHECK(std::fabs(f.pillars[1].discount_factor - 1.0 / (1.0 + q[1].rate * tau)) < 1e-15);
    CHECK(f.spreads[1] > 0.0);
    CHECK(f.discount_factors.empty());
    CHECK(code_of([&] { funding_curve(d, {}, {}); }) == "E_INPUT");
    CHECK(code_of([&] { funding_curve(d, {{make_date(2027, 1, 1), -400.0}}, {}); }) == "E_DOMAIN");
    CHECK(code_of([&] { funding_curve(d, q, {make_date(2026, 1, 1)}); }) == "E_OUT_OF_RANGE");
}
