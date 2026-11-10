#pragma once
// Stage F, slice F3 (06-risk/book-sensitivities.md): exact OIS book sensitivities through the IFT, curve PCA,
// cross gamma and jump to default.
#include <string>
#include <vector>

#include "quantforge/core/linalg.hpp"
#include "quantforge/core/rates.hpp"
#include "quantforge/core/risk.hpp"

namespace quantforge {

// ---- risk.book.ois_sensitivity ----

struct BookSwap {
    std::string id;
    long long tenor_years;
    double fixed_rate;
    FixedSide side;  // Pay: PAYER, Receive: RECEIVER
};

struct BookSensitivity {
    std::vector<double> pv;
    double book_pv;
    Matrix quote_sensitivity;  // rows: swaps, columns: quotes; d pv / d q per unit quote
    std::vector<double> book_sensitivity;
    std::vector<Date> pillars;
    Matrix zero_jacobian;  // rows: pillars, columns: quotes; d z / d q
};

/// E_INPUT on no swaps or a repeated id; E_DOMAIN on tenor_years < 1 or an interpolation whose log discount
/// factors are not linear in the pillar unknowns (only LOG_LINEAR_DF and LINEAR_ZERO are). Exact derivatives
/// (ruling F-29): closed-form chain rule with the IFT; structural zeros stay exactly 0 (ruling F-30).
BookSensitivity ois_book_sensitivity(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                                     CurveInterpolation interpolation, const std::vector<BookSwap>& swaps);

/// d x / d q with x_i = ln D(p_i) of the sequential bootstrap: the inverse of d par / d x.
Matrix ois_curve_ift(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                     CurveInterpolation interpolation);

// ---- risk.curve.pca ----

struct CurvePca {
    std::vector<double> eigenvalues;  // all N, descending
    Matrix loadings;                  // k unit eigenvectors, largest-absolute entry positive
    std::vector<double> explained_ratio;
};

/// E_INPUT unless T >= 2, rows of one length and k <= N; E_DOMAIN on k < 1 or eigenvalues of the first k + 1
/// (all, when k = N) closer than 1e-6 lambda_1.
CurvePca curve_pca(const Matrix& changes, long long components);

/// Symmetric eigen decomposition by cyclic Jacobi: eigenvalues descending, vectors[i] the unit vector of value i.
/// unchecked: caller guarantees finite inputs
void eigen_vectors_symmetric(Matrix a, std::vector<double>& values, Matrix& vectors);

// ---- risk.curve.cross_gamma ----

struct CrossGamma {
    double value;
    Matrix gamma;  // money per bp squared
};

/// PILLAR bumps of the zero rate (par-and-key-rate.md); E_DOMAIN unless 0 < bump_bp <= 100.
CrossGamma cross_gamma(const Curve& curve, const CurvePricer& price, double bump_bp);
/// The same for an OIS: on LOG_LINEAR_DF and LINEAR_ZERO each bumped value is formed as an exact change from
/// the base (expm1 of the log shift), so the differences do not lose digits against V(0).
CrossGamma cross_gamma(const Curve& curve, const OisTrade& trade, double bump_bp);

// ---- risk.credit.jtd ----

enum class JtdKind { Bond, CdsProtectionBuyer, CdsProtectionSeller };

struct JtdPosition {
    std::string id;
    JtdKind kind;
    double notional, recovery, market_value;
};

struct Jtd {
    std::vector<double> jtd;
    double total;
};

/// E_INPUT on no positions; E_DOMAIN unless notional >= 0 and 0 <= recovery <= 1.
Jtd jump_to_default(const std::vector<JtdPosition>& positions);

}  // namespace quantforge
