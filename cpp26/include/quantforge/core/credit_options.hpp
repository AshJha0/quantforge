#pragma once
// Credit options: CDS options, default copulas, large homogeneous pool (04-pricing/credit-options-and-copulas.md).
// Rulings E-B22 to E-B26.
#include <optional>
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge {

/// Bivariate standard normal CDF P(X <= a, Y <= b) with correlation rho (Genz's method, 20-point rule).
/// Special functions, called inside pricers; unchecked: caller guarantees finite inputs.
double bivariate_normal_cdf(double a, double b, double rho);
/// Student t CDF and its inverse, nu > 0 (any real).
double student_t_cdf(double x, double nu);
double student_t_inverse(double p, double nu);
/// Bivariate Student t CDF, one nu, scale matrix with off-diagonal rho.
double bivariate_t_cdf(double a, double b, double rho, double nu);

struct CdsOptionInputs {
    Date as_of, expiry, maturity;
    double rate, hazard_rate, recovery;
    bool payer;
    double strike, notional;
    bool knock_out;
};
struct CdsOptionPrice {
    double price, forward_spread, risky_annuity, front_end_protection;
};
CdsOptionPrice cds_option_price(const CdsOptionInputs& in, double vol);
double cds_option_implied_vol(const CdsOptionInputs& in, double premium);

enum class CopulaKind { Gaussian, StudentT };
struct JointDefault {
    double joint, default_correlation;
};
JointDefault copula_joint_default(CopulaKind kind, const std::vector<double>& p, double rho, std::optional<double> nu);

double lhp_tranche_loss(double p, double rho, double recovery, double attachment, double detachment);
std::vector<double> lhp_loss_cdf(double p, double rho, double recovery, const std::vector<double>& losses);

}  // namespace quantforge
