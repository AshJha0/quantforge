// Unit tests that close coverage gaps in modules the conformance suite reaches but the unit suite did not.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <string>

#include "quantforge/core/calibration.hpp"
#include "quantforge/core/compounding.hpp"
#include "quantforge/core/daycount.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/models.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
}  // namespace

TEST_CASE("30/360 variants follow their end-of-month rules") {
    using enum DayCount;
    CHECK(year_fraction(Thirty360Us, d("2024-02-29"), d("2025-02-28")) == Approx(1.0));
    CHECK(year_fraction(Thirty360Us, d("2024-02-29"), d("2024-03-31")) == Approx(30.0 / 360));
    CHECK(year_fraction(Thirty360Us, d("2024-01-15"), d("2024-03-31")) == Approx(76.0 / 360));
    CHECK(year_fraction(ThirtyE360, d("2024-01-31"), d("2024-03-31")) == Approx(60.0 / 360));
    CHECK(year_fraction(ThirtyE360, d("2024-02-28"), d("2024-08-31")) == Approx(182.0 / 360));
    const DayCountInputs far{{}, {}, {}, d("2025-02-28"), {}};
    CHECK(year_fraction(ThirtyE360Isda, d("2024-02-29"), d("2024-08-31"), far) == Approx(180.0 / 360));
    CHECK(year_fraction(ThirtyE360Isda, d("2023-08-31"), d("2024-02-29"), far) == Approx(180.0 / 360));
    const DayCountInputs at_end{{}, {}, {}, d("2024-02-29"), {}};
    CHECK(year_fraction(ThirtyE360Isda, d("2023-08-31"), d("2024-02-29"), at_end) == Approx(179.0 / 360));
    CHECK(code_of([] { year_fraction(ThirtyE360Isda, d("2024-01-01"), d("2024-02-01")); }) == "E_SCHEMA");
}

TEST_CASE("actual, business-day and Act365L conventions") {
    using enum DayCount;
    CHECK(year_fraction(Act364, d("2024-01-01"), d("2024-07-01")) == Approx(0.5));
    CHECK(year_fraction(Act365_25, d("2024-01-01"), d("2025-01-01")) == Approx(366.0 / 365.25));
    CHECK(year_fraction(OneOne, d("2024-01-01"), d("2024-01-02")) == 1.0);
    const DayCountInputs gblo{{}, {}, {}, {}, Calendar::Gblo};
    CHECK(year_fraction(Bus252, d("2024-03-25"), d("2024-04-03"), gblo) == Approx(5.0 / 252));
    CHECK(code_of([] { year_fraction(Bus252, d("2024-01-01"), d("2024-02-01")); }) == "E_SCHEMA");
    const DayCountInputs euta{{}, {}, {}, {}, Calendar::Euta};
    CHECK(code_of([&] { year_fraction(Bus252, d("1999-12-30"), d("2024-01-01"), euta); }) == "E_DATE_RANGE");
    const DayCountInputs annual{1, {}, {}, {}, {}}, semi{2, {}, {}, {}, {}}, odd{5, {}, {}, {}, {}};
    CHECK(year_fraction(Act365L, d("2023-06-01"), d("2024-06-01"), annual) == Approx(1.0));
    CHECK(year_fraction(Act365L, d("2022-06-01"), d("2023-06-01"), annual) == Approx(1.0));
    CHECK(year_fraction(Act365L, d("2024-01-01"), d("2024-07-01"), semi) == Approx(182.0 / 366));
    CHECK(year_fraction(Act365L, d("2023-01-01"), d("2023-07-01"), semi) == Approx(181.0 / 365));
    CHECK(code_of([&] { year_fraction(Act365L, d("2024-01-01"), d("2024-02-01"), odd); }) == "E_SCHEMA");
}

TEST_CASE("ICMA needs a reference period that contains the accrual") {
    const DayCountInputs no_ref{2, {}, {}, {}, {}};
    CHECK(code_of([&] { year_fraction(DayCount::ActActIcma, d("2024-01-01"), d("2024-02-01"), no_ref); }) ==
          "E_SCHEMA");
    const DayCountInputs no_end{2, d("2024-01-01"), {}, {}, {}};
    CHECK(code_of([&] { year_fraction(DayCount::ActActIcma, d("2024-01-01"), d("2024-02-01"), no_end); }) ==
          "E_SCHEMA");
    const DayCountInputs ref{2, d("2024-01-01"), d("2024-07-01"), {}, {}};
    CHECK(code_of([&] { year_fraction(DayCount::ActActIcma, d("2023-12-01"), d("2024-02-01"), ref); }) ==
          "E_INPUT");
    CHECK(code_of([&] { year_fraction(DayCount::ActActIcma, d("2024-02-01"), d("2024-08-01"), ref); }) ==
          "E_INPUT");
    CHECK(year_fraction(DayCount::ActActIcma, d("2024-01-01"), d("2024-04-01"), ref) == Approx(91.0 / 364));
}

TEST_CASE("compounding conventions and their domain checks") {
    const Compounding simple{CompoundingKind::Simple, {}}, cont{CompoundingKind::Continuous, {}};
    const Compounding semi{CompoundingKind::Periodic, 2}, annual{CompoundingKind::Periodic, 1};
    CHECK(discount_factor(0.04, 1.0, semi) == Approx(std::pow(1.02, -2.0)));
    CHECK(discount_factor(0.04, 0.0, semi) == 1.0);
    CHECK(convert_rate(0.05, 2.0, cont, annual) == Approx(std::exp(0.05) - 1.0));
    CHECK(convert_rate(0.05, 2.0, cont, semi) == Approx(2.0 * (std::exp(0.025) - 1.0)));
    CHECK(convert_rate(0.05, 0.5, semi, simple) == Approx(0.05));
    CHECK(code_of([&] { discount_factor(-2.0, 1.0, simple); }) == "E_DOMAIN");
    CHECK(code_of([&] { discount_factor(-2.5, 1.0, semi); }) == "E_DOMAIN");
    CHECK(code_of([&] { discount_factor(0.01, -1.0, cont); }) == "E_DOMAIN");
    CHECK(code_of([&] { convert_rate(0.01, -1.0, cont, simple); }) == "E_DOMAIN");
    CHECK(code_of([&] { convert_rate(0.01, 0.0, cont, simple); }) == "E_DOMAIN");
    CHECK(code_of([&] { convert_rate(-2.0, 1.0, simple, cont); }) == "E_DOMAIN");
    CHECK(code_of([] { check_frequency({CompoundingKind::Periodic, {}}); }) == "E_SCHEMA");
    CHECK(code_of([] { check_frequency({CompoundingKind::Periodic, 5}); }) == "E_SCHEMA");
}

TEST_CASE("json decodes every escape and validates raw UTF-8") {
    const json::Parsed p = json::parse(R"("\/\b\f\n\r\t\"\\é€😀")");
    CHECK(p.value.text == "/\b\f\n\r\t\"\\\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80");
    CHECK_FALSE(p.lone_surrogate);
    const json::Parsed lone = json::parse(R"("\uD800A")");
    CHECK(lone.lone_surrogate);
    CHECK(lone.value.text == "\xED\xA0\x80" "A");
    CHECK(json::parse("\"\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80\"").value.text == "\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80");
    for (const char* bad : {R"("\uZZZZ")", R"("\q")", R"("\u12")", "\"\xC0\xAF\"", "\"\xE0\x80\x80\"", "\"\xC3(\"",
                            "\"\xED\xA0\x80\"", "\"\xFF\"", "\"\xF4\x90\x80\x80\"", "\"\xC3"})
        CHECK(code_of([&] { json::parse(bad); }) == "E_PARSE");
}

TEST_CASE("json writer re-emits a parsed value") {
    const char* text = R"({"a":[null,true,false,1.5,"x"],"b":{},"c":[]})";
    json::Writer w;
    w.value(json::parse(text).value);
    CHECK(w.str() == text);
    json::Value nan;
    nan.kind = json::Kind::Number;
    nan.number = std::nan("");
    json::Writer w2;
    CHECK(code_of([&] { w2.value(nan); }) == "E_NON_FINITE");
}

TEST_CASE("Nelson-Siegel fit recovers its parameters, including at x = 0") {
    FitInputs f;
    f.model = FitModel::NelsonSiegel;
    const double b0 = 0.03, b1 = -0.01, b2 = 0.02, tau = 1.5;
    for (const double x : {0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0}) {
        const double a = x / tau, e = x == 0.0 ? 1.0 : (1.0 - std::exp(-a)) / a;
        f.x.push_back(x);
        f.y.push_back(b0 + b1 * e + b2 * (e - std::exp(-a)));
    }
    f.start = {0.025, -0.005, 0.015, 1.2};
    f.method = FitMethod::LevenbergMarquardt;
    const FitResult r = fit(f);
    CHECK(r.parameters[0] == Approx(b0).margin(1e-6));
    CHECK(r.parameters[3] == Approx(tau).margin(1e-4));
    CHECK(r.objective < 1e-14);
}

TEST_CASE("ridge regularisation pulls a linear fit toward its prior") {
    FitInputs f;
    f.model = FitModel::Linear;
    f.x = {0, 1, 2};
    f.y = {1, 3, 5};
    f.start = {0, 0};
    f.prior = std::vector<double>{0, 0};
    f.regularisation = 1.0;
    f.method = FitMethod::GaussNewton;
    // Normal equations (X'X + I) p = X'y give p = (1, 5/3).
    const FitResult r = fit(f);
    CHECK(r.parameters[0] == Approx(1.0).margin(1e-9));
    CHECK(r.parameters[1] == Approx(5.0 / 3.0).margin(1e-9));
}

TEST_CASE("fit rejects inconsistent weights and bounds") {
    FitInputs base;
    base.model = FitModel::Linear;
    base.x = {0, 1, 2};
    base.y = {1, 3, 5};
    base.start = {0, 0};
    base.method = FitMethod::LevenbergMarquardt;
    FitInputs f = base;
    f.weights = std::vector<double>{1, 1};
    CHECK(code_of([&] { fit(f); }) == "E_INPUT");
    f = base;
    f.weights = std::vector<double>{1, -1, 1};
    CHECK(code_of([&] { fit(f); }) == "E_DOMAIN");
    f = base;
    f.lower = std::vector<double>{0};
    CHECK(code_of([&] { fit(f); }) == "E_INPUT");
    f = base;
    f.upper = std::vector<double>{9, 9};
    f.method = FitMethod::Bfgs;
    CHECK(code_of([&] { fit(f); }) == "E_INPUT");
}

TEST_CASE("PDE prices a put and validates its grid") {
    PdeInputs in{OptionType::Put, 100, 100, 0.05, 0.02, 0.2, 1, 400, 200};
    // Put from the call target by parity: C - S e^{-qT} + K e^{-rT}.
    const double put_true = 9.227005508154049 - 100.0 * std::exp(-0.02) + 100.0 * std::exp(-0.05);
    CHECK(pde_bs_european(in).price == Approx(put_true).margin(1e-3));
    PdeInputs bad = in;
    bad.sigma = 0.0;
    CHECK(code_of([&] { pde_bs_european(bad); }) == "E_DOMAIN");
    bad = in;
    bad.rannacher_steps = bad.time_steps;
    CHECK(code_of([&] { pde_bs_european(bad); }) == "E_INPUT");
}
