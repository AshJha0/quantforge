#pragma once
// Stage F (Q4): the joint multi-curve solve with calibrated turns, futures-fitted meeting steps and the
// IFT Jacobian (02-curves/joint-solve-and-funding.md, rulings F-24 to F-27), and the funding curve.
#include <string>
#include <vector>

#include "quantforge/core/linalg.hpp"
#include "quantforge/core/rates.hpp"

namespace quantforge {

enum class JointCurveType { Ois, OisSteps, Projection, Xccy };

struct JointCurveSpec {
    std::string name;
    JointCurveType type = JointCurveType::Ois;
    const RateConvention* convention = nullptr;  // OIS and OIS_STEPS: overnight; PROJECTION: the term index
    CurveInterpolation interpolation = CurveInterpolation::LogLinearDf;
    CurveShape shape;
    std::vector<Jump> jumps;       // fixed
    std::vector<Date> turns;       // factors solved
    std::vector<Date> step_dates;  // OIS_STEPS
    std::string discount;          // PROJECTION
    std::string domestic, foreign_projection;  // XCCY
    Date start{};                              // XCCY
};

enum class JointInstrumentType { Ois, Future, Deposit, Fra, Swap, Xccy };

struct JointInstrument {
    std::string id, curve;
    JointInstrumentType type = JointInstrumentType::Ois;
    bool turn = false;
    Tenor tenor{};       // OIS
    double rate = 0.0;   // OIS, DEPOSIT, FRA, SWAP
    long long months = 0;  // DEPOSIT, SWAP and XCCY length; FRA start_months
    Date start{}, end{};   // FUTURE
    double price = 0.0, sigma = 0.0, mean_reversion = 0.0;  // FUTURE
    double spread = 0.0;   // XCCY
};

struct JointCurveResult {
    std::string name;
    bool steps = false;
    std::vector<Pillar> pillars;  // full discount factors, jumps and turns included
    double base_rate = 0.0;
    std::vector<double> step_rates;
};

struct TurnFactor {
    std::string curve;
    Date date;
    double factor;
};

struct JointResult {
    std::vector<JointCurveResult> curves;
    std::vector<TurnFactor> turn_factors;
    std::vector<std::string> unknowns, quotes;
    Matrix jacobian;          // d unknown_i / d quote_j
    Matrix turn_sensitivity;  // per turn: d model_j / d ln factor
    double max_repricing_error;
};

/// E_INPUT, E_DOMAIN and E_NO_CONVERGENCE as the spec's checks. Conventions and enums are the caller's.
JointResult joint_solve(Date as_of, const std::vector<JointCurveSpec>& curves, const std::vector<JointInstrument>& instruments);

struct FundingQuote {
    Date end;
    double rate;  // simple ACT/360 from as_of
};

struct FundingCurve {
    std::vector<double> spreads;
    std::vector<Pillar> pillars;
    std::vector<double> discount_factors;
};

/// D_f(t) = D_ois(t) exp(-integral of s), s piecewise flat between quote dates and flat beyond the last.
FundingCurve funding_curve(const Curve& discount, const std::vector<FundingQuote>& quotes, const std::vector<Date>& dates);

}  // namespace quantforge
