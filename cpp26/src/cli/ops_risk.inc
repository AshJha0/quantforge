// CLI handlers, the risk verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_ois_dv01(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const OisTrade trade = ois_trade_of(in.need("trade"));
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const RateRisk r = rate_risk(trade, bumped_curves(*trade.convention, as_of, quotes, interpolation));
    out.key_real("dv01", r.dv01);
    out.key_reals("key_rate", r.key_rate);
}

void op_cashflows(const In& in, Out& out) {
    const Value& a = in.need("cashflows");
    if (a.kind != Kind::Array) schema("cashflows", "expected an array");
    std::vector<Cashflow> flows;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("cashflows", "expected an object");
        const In c(v);
        flows.push_back({c.real("t"), c.real("amount")});
    }
    const double yield = in.real("yield");
    in.ready();
    const CashflowRisk r = cashflow_risk(flows, yield);
    out.key_real("pv", r.pv);
    out.key_real("duration", r.duration);
    out.key_real("convexity", r.convexity);
}

void op_vol_greeks(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double vol = in.real("vol");
    in.ready();
    const Greeks g = option_greeks(o, vol);
    out.key_real("price", g.price);
    out.key_real("delta", g.delta);
    out.key_real("gamma", g.gamma);
    out.key_real("vega", g.vega);
    out.key_real("theta", g.theta);
    out.key_real("rho", g.rho);
    out.key_real("vanna", g.vanna);
    out.key_real("volga", g.volga);
}

void op_vol_bump_greeks(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double vol = in.real("vol");
    in.ready();
    const BumpGreeks g = bump_greeks(o, vol);
    out.key_real("delta", g.delta);
    out.key_real("gamma", g.gamma);
    out.key_real("vega", g.vega);
    out.key_real("volga", g.volga);
    out.key_real("vanna", g.vanna);
}

void op_surface_vega(const In& in, Out& out) {
    const Surface s = surface_of(in);
    const auto positions = rows_of<VegaPosition>(in, "positions", [](const In& r) {
        return VegaPosition{r.choice("option_type", option_types), r.real("forward"), r.real("strike"),
                            r.real("discount_factor"), r.real("expiry_years"), r.real("quantity")};
    });
    in.ready();
    limit_surface(s);
    limit_if(positions.size() > max_quotes, "positions");
    need_items(positions, "positions");
    check_surface(s);
    for (const VegaPosition& p : positions)
        if (p.forward <= 0 || p.strike <= 0 || p.discount_factor <= 0 || p.expiry_years <= 0)
            throw Error("E_DOMAIN", "a position input is not above 0");
    constexpr double bump = 1e-4;
    for (const Vec& row : s.vols)
        for (const double v : row)
            if (v - bump <= 0) throw Error("E_DOMAIN", "a node vol is too low to bump");
    Surface moved = s;
    Matrix buckets = s.vols;
    double bucket_sum = 0.0;
    for (std::size_t j = 0; j < s.vols.size(); ++j)
        for (std::size_t i = 0; i < s.vols[j].size(); ++i) {
            moved.vols[j][i] = s.vols[j][i] + bump;
            const double up = surface_pv(moved, positions);
            moved.vols[j][i] = s.vols[j][i] - bump;
            const double down = surface_pv(moved, positions);
            moved.vols[j][i] = s.vols[j][i];
            buckets[j][i] = (up - down) / (2 * bump);
            bucket_sum += buckets[j][i];
        }
    const auto shifted = [&](double by) {
        Surface all = s;
        for (Vec& row : all.vols)
            for (double& v : row) v += by;
        return surface_pv(all, positions);
    };
    out.key_real("pv", surface_pv(s, positions));
    out.values.key("bucket_vega");
    out.values.begin_array();
    for (const Vec& row : buckets) {
        out.values.begin_array();
        for (const double x : row) out.values.real(x);
        out.values.end_array();
    }
    out.values.end_array();
    out.key_real("parallel_vega", (shifted(bump) - shifted(-bump)) / (2 * bump));
    out.key_real("bucket_sum", bucket_sum);
}

void op_risk_par(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const RiskProduct product = product_of(in);
    const double bump = bump_of(in);
    const BumpScheme scheme = scheme_of(in);
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_bump(bump);
    product.check();
    if (product.kind == RiskProduct::Kind::Ois && product.trade.convention != c)
        throw Error("E_INPUT", "the trade's convention differs from the curve's", "product");
    check_crossed(raw);
    const ParRisk r = par_risk(*c, as_of, quotes, interpolation, pricer_of(product), bump, scheme);
    out.key_real("value", r.value);
    out.key_real("par_dv01", r.par_dv01);
    out.key_reals("par_buckets", r.buckets);
}

void op_risk_key_rate(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto mode = in.choice<KeyRateMode>("mode", {{"TRIANGULAR", KeyRateMode::Triangular}, {"PILLAR", KeyRateMode::Pillar}});
    std::optional<std::vector<Date>> keys;
    if (const Value* k = in.find("key_dates")) {
        if (k->kind != Kind::Array) schema("key_dates", "expected an array");
        keys.emplace();
        for (const Value& d : k->items) keys->push_back(to_date(d, "key_dates"));
    }
    const RiskProduct product = product_of(in);
    const double bump = bump_of(in);
    const BumpScheme scheme = scheme_of(in);
    in.ready();
    ci.limit();
    limit_if(keys && keys->size() > max_quotes, "key_dates");
    check_bump(bump);
    product.check();
    const Curve curve = ci.build();
    if (mode == KeyRateMode::Pillar && keys) throw Error("E_INPUT", "PILLAR takes no key_dates", "key_dates");
    if (mode == KeyRateMode::Triangular) check_key_dates(curve, keys.value_or(std::vector<Date>{}));
    const KeyRateRisk r = key_rate_risk(curve, mode, keys.value_or(std::vector<Date>{}), pricer_of(product), bump, scheme);
    out.key_real("value", r.value);
    out.key_reals("key_rates", r.buckets);
    out.key_real("zero_dv01", r.zero_dv01);
}

void op_risk_jacobian(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const double bump = bump_of(in);
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_bump(bump);
    check_crossed(raw);
    const ZeroJacobian j = zero_jacobian(*c, as_of, quotes, interpolation, bump);
    out.values.key("pillar_dates");
    out.values.begin_array();
    for (const Date d : j.pillar_dates) out.values.string(format_date(d));
    out.values.end_array();
    out.key_reals("zero_rates", j.zero_rates);
    out.values.key("jacobian");
    out.values.begin_array();
    for (const auto& row : j.jacobian) {
        out.values.begin_array();
        for (const double x : row) out.values.real(x);
        out.values.end_array();
    }
    out.values.end_array();
}

void op_pnl_explain(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto raw_start = quotes_of(in, "quotes_start"), raw_end = quotes_of(in, "quotes_end");
    const RiskProduct product = product_of(in);
    const double bump = bump_of(in);
    in.ready();
    const auto start = checked_quotes(raw_start), end = checked_quotes(raw_end);
    check_bump(bump);
    product.check();
    if (product.kind == RiskProduct::Kind::Ois && product.trade.convention != c)
        throw Error("E_INPUT", "the trade's convention differs from the curve's", "product");
    check_crossed(raw_start);
    check_crossed(raw_end);
    const PnlExplain r = pnl_explain(*c, as_of, start, end, interpolation, pricer_of(product), bump, product.face());
    out.key_real("value_start", r.value_start);
    out.key_real("value_end", r.value_end);
    out.key_real("full_pnl", r.full_pnl);
    out.key_reals("par_buckets", r.par_buckets);
    out.key_real("risk_pnl", r.risk_pnl);
    out.key_real("gross_risk_pnl", r.gross_risk_pnl);
    out.key_real("unexplained", r.unexplained);
    out.key_real("threshold", r.threshold);
    out.values.key("explained");
    out.values.boolean(r.explained);
}


void op_corr_validate(const In& in, Out& out) {
    const Matrix m = in.matrix("matrix");
    in.ready();
    const CorrValidation r = corr_validate(m);
    const auto flag = [&](string_view k, bool b) {
        out.values.key(k);
        out.values.boolean(b);
    };
    flag("symmetric", r.symmetric);
    flag("unit_diagonal", r.unit_diagonal);
    flag("in_range", r.in_range);
    out.key_real("min_eigenvalue", r.min_eigenvalue);
    flag("psd", r.psd);
    flag("valid", r.valid);
}

void op_corr_nearest(const In& in, Out& out) {
    const Matrix m = in.matrix("matrix");
    in.ready();
    const NearestCorr r = corr_nearest(m);
    out.values.key("matrix");
    out.values.begin_array();
    for (const auto& row : r.matrix) {
        out.values.begin_array();
        for (const double x : row) out.values.real(x);
        out.values.end_array();
    }
    out.values.end_array();
    out.key_real("frobenius_distance", r.frobenius_distance);
}

void op_corr_implied(const In& in, Out& out) {
    const Vec w = in.reals("weights"), v = in.reals("vols");
    const double iv = in.real("index_vol");
    in.ready();
    out.key_real("correlation", corr_implied(w, v, iv));
}

void op_corr_dispersion(const In& in, Out& out) {
    const Vec w = in.reals("weights"), k = in.reals("vol_strikes");
    const double ki = in.real("index_vol_strike");
    const Vec s = in.reals("realized_vols");
    const double si = in.real("index_realized_vol"), n = in.real("vega_notional");
    in.ready();
    const Dispersion d = corr_dispersion(w, k, ki, s, si, n);
    out.key_real("pnl", d.pnl);
    out.key_real("implied_correlation", d.implied_correlation);
    out.key_real("realized_correlation", d.realized_correlation);
    out.key_reals("constituent_variance_notionals", d.constituent_variance_notionals);
    out.key_real("index_variance_notional", d.index_variance_notional);
}

constexpr Entry risk_ops[] = {
    {"risk.cashflows", op_cashflows},
    {"risk.corr.dispersion", op_corr_dispersion},
    {"risk.corr.implied", op_corr_implied},
    {"risk.corr.nearest", op_corr_nearest},
    {"risk.corr.validate", op_corr_validate},
    {"risk.curve.jacobian", op_risk_jacobian},
    {"risk.curve.key_rate", op_risk_key_rate},
    {"risk.curve.par", op_risk_par},
    {"risk.ois.dv01", op_ois_dv01},
    {"risk.pnl.explain", op_pnl_explain},
    {"risk.vol.bump_greeks", op_vol_bump_greeks},
    {"risk.vol.greeks", op_vol_greeks},
    {"risk.vol.surface_vega", op_surface_vega},
};
