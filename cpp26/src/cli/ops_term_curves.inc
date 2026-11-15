// Stage J curves lane (rulings J-C-1 to J-C-9): repo.term.curve, eq.forward.term_financed, liq.curve.cost.
// Included after ops_research.inc (uses key_matrix).

namespace tcv = quantforge::termcurves;

// Reads the six curve arrays, then gates: call it after reading every other key.
tcv::FinancingCurve read_financing_curve(const In& in) {
    const Vec ft = in.reals("funding_times"), fz = in.reals("funding_zero_rates");
    const Vec qt = in.reals("quote_times"), qr = in.reals("repo_rates");
    const Vec bt = in.reals("borrow_times"), bf = in.reals("borrow_fees");
    in.ready();
    return tcv::build(ft, fz, qt, qr, bt, bf);
}

void key_optional_reals(Out& out, string_view k, const std::optional<Vec>& v) {
    if (v) {
        out.key_reals(k, *v);
    } else {
        out.values.key(k);
        out.values.null();
    }
}

void op_repo_term_curve(const In& in, Out& out) {
    const Vec q = in.reals("query_times");
    const tcv::TermCurve r = tcv::term_curve(read_financing_curve(in), q);
    out.key_reals("pillar_spreads", r.pillar_spreads);
    out.key_reals("spread", r.spread);
    out.key_reals("financing_df", r.financing_df);
    out.key_reals("financing_rate", r.financing_rate);
    out.key_reals("forward_financing", r.forward_financing);
    key_optional_reals(out, "borrow_fee", r.borrow_fee);
}

void op_eq_forward_term_financed(const In& in, Out& out) {
    const double spot = in.real("spot"), t = in.real("maturity_years");
    const Vec dt = in.reals("dividend_times"), da = in.reals("dividend_amounts");
    const tcv::TermForward r = tcv::forward_term_financed(read_financing_curve(in), spot, t, dt, da);
    out.key_real("forward", r.forward);
    out.key_real("carry", r.carry);
    out.key_real("carry_factor", r.carry_factor);
    out.key_real("financing_df", r.financing_df);
    out.key_real("pv_dividends", r.pv_dividends);
}

void op_liq_curve_cost(const In& in, Out& out) {
    tcv::LiquidityParams p{};
    p.half_spread_bps = in.real("half_spread_bps");
    p.daily_volume = in.real("daily_volume");
    p.daily_vol = in.real("daily_vol");
    p.coefficient = in.real("coefficient", 1.0);
    p.exponent = in.real("exponent", 0.5);
    p.risk_multiplier = in.real("risk_multiplier", 0.0);
    const Vec q = in.reals("sizes"), h = in.reals("horizons_days");
    in.ready();
    const tcv::LiquidityCurve r = tcv::liquidity_cost(p, q, h);
    out.key_real("spread_cost", r.spread_cost);
    key_matrix(out, "impact", r.impact);
    out.key_reals("timing_risk", r.timing_risk);
    key_matrix(out, "total_cost", r.total_cost);
    key_optional_reals(out, "optimal_horizon", r.optimal_horizon);
    key_optional_reals(out, "min_cost", r.min_cost);
}

constexpr Entry term_curve_ops[] = {
    {"repo.term.curve", op_repo_term_curve},
    {"eq.forward.term_financed", op_eq_forward_term_financed},
    {"liq.curve.cost", op_liq_curve_cost},
};
