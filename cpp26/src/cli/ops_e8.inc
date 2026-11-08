// Stage E, E8: CDS options, copulas, large homogeneous pool. Included by dispatch.cpp after ops_e7.inc.

CdsOptionInputs cds_option_of(const In& in) {
    CdsOptionInputs c;
    c.as_of = in.date("as_of");
    c.expiry = in.date("expiry");
    c.maturity = in.date("maturity");
    c.rate = in.real("rate");
    c.hazard_rate = in.real("hazard_rate");
    c.recovery = in.real("recovery");
    c.payer = in.choice<bool>("type", {{"PAYER", true}, {"RECEIVER", false}});
    c.strike = in.real("strike");
    c.notional = in.real("notional");
    c.knock_out = in.boolean("knock_out");
    return c;
}

void op_cds_option_price(const In& in, Out& out) {
    const CdsOptionInputs c = cds_option_of(in);
    const double vol = in.real("vol");
    in.ready();
    const CdsOptionPrice r = cds_option_price(c, vol);
    out.key_real("price", r.price);
    out.key_real("forward_spread", r.forward_spread);
    out.key_real("risky_annuity", r.risky_annuity);
    out.key_real("front_end_protection", r.front_end_protection);
}

void op_cds_option_implied_vol(const In& in, Out& out) {
    const CdsOptionInputs c = cds_option_of(in);
    const double premium = in.real("premium");
    in.ready();
    out.key_real("vol", cds_option_implied_vol(c, premium));
}

void op_copula_joint_default(const In& in, Out& out) {
    const CopulaKind kind = in.choice<CopulaKind>("copula", {{"GAUSSIAN", CopulaKind::Gaussian}, {"STUDENT_T", CopulaKind::StudentT}});
    const Vec p = in.reals("default_probabilities");
    const double rho = in.real("correlation");
    std::optional<double> nu;
    if (in.find("degrees_of_freedom")) nu = in.real("degrees_of_freedom");
    in.ready();
    const JointDefault r = copula_joint_default(kind, p, rho, nu);
    out.key_real("joint_default_probability", r.joint);
    out.key_real("default_correlation", r.default_correlation);
}

void op_lhp_tranche_loss(const In& in, Out& out) {
    const double p = in.real("default_probability"), rho = in.real("correlation"), r = in.real("recovery");
    const double a = in.real("attachment"), d = in.real("detachment");
    in.ready();
    out.key_real("expected_loss_fraction", lhp_tranche_loss(p, rho, r, a, d));
}

void op_lhp_loss_cdf(const In& in, Out& out) {
    const double p = in.real("default_probability"), rho = in.real("correlation"), r = in.real("recovery");
    const Vec x = in.reals("losses");
    in.ready();
    out.key_reals("cdf", lhp_loss_cdf(p, rho, r, x));
}
