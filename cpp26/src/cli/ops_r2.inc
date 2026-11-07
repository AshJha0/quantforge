// Phase R2: par and key-rate risk (06-risk/par-and-key-rate.md). Included by dispatch.cpp after ops_credit.inc.

struct RiskProduct {
    enum class Kind { Ois, Bond } kind;
    OisTrade trade{};
    Bond bond{};
    Date settlement{};
    double notional = 0.0;

    void check() const {
        if (kind == Kind::Bond && !(notional > 0.0)) throw Error("E_DOMAIN", "notional must be positive", "notional");
    }
    double value(const Curve& c) const {
        if (kind == Kind::Ois) return ois_price(trade, c).valuation.pv;
        return notional * curve_dirty(bond, settlement, c, 0.0) / 100.0;
    }
    double face() const { return kind == Kind::Ois ? trade.notional : notional; }
};

RiskProduct product_of(const In& in) {
    const Value& v = in.need("product");
    if (v.kind != Kind::Object) schema("product", "expected an object");
    const In p(v);
    RiskProduct out{p.choice<RiskProduct::Kind>("kind", {{"OIS", RiskProduct::Kind::Ois}, {"BOND", RiskProduct::Kind::Bond}})};
    if (out.kind == RiskProduct::Kind::Ois) {
        out.trade = ois_trade_of(p.need("trade"));
    } else {
        out.bond = bond_of(p);
        out.settlement = p.date("settlement");
        out.notional = p.real("notional");
    }
    return out;
}

double bump_of(const In& in) { return in.find("bump_bp") ? in.real("bump_bp") : 1.0; }

BumpScheme scheme_of(const In& in) {
    if (!in.find("scheme")) return BumpScheme::Central;
    return in.choice<BumpScheme>("scheme", {{"CENTRAL", BumpScheme::Central}, {"FORWARD", BumpScheme::Forward}});
}

CurvePricer pricer_of(const RiskProduct& p) {
    return [p](const Curve& c) { return p.value(c); };
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
