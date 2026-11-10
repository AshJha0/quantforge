// CLI handlers, the credit verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_cds_price(const In& in, Out& out) {
    const Date t = in.date("trade_date");
    const CurveInput d = curve_of(in, "discount");
    const HazardCurve h = hazard_of(in.need("hazard"), "hazard");
    const double r = in.real("recovery");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In tr(tv);
    const Date m = tr.date("maturity");
    const double coupon = tr.real("coupon"), notional = tr.real("notional");
    const auto side = tr.choice<CdsSide>("side", {{"BUY_PROTECTION", CdsSide::Buy}, {"SELL_PROTECTION", CdsSide::Sell}});
    const auto payout = in.choice<CdsPayout>("payout", {{"STANDARD", CdsPayout::Standard}, {"DIGITAL", CdsPayout::Digital}});
    in.ready();
    d.limit();
    limit_if(h.dates.size() > max_quotes, "hazard");
    require_flat_forwards(d);
    const CdsPrice p = cds_price(t, d.build(), h, r, m, coupon, notional, side, payout);
    out.key_real("protection_leg", p.protection_leg);
    out.key_real("rpv01", p.rpv01);
    out.key_real("accrued", p.accrued);
    out.key_real("par_spread", p.par_spread);
    out.key_real("upfront", p.upfront);
    out.key_real("pv", p.pv);
}

void op_cds_bootstrap(const In& in, Out& out) {
    const Date t = in.date("trade_date");
    const CurveInput d = curve_of(in, "discount");
    const double r = in.real("recovery");
    const auto quotes = cds_quotes_of(in);
    in.ready();
    d.limit();
    limit_if(quotes.size() > max_quotes, "quotes");
    require_flat_forwards(d);
    write_survival(out, cds_bootstrap(t, d.build(), r, quotes));
}

void op_index_intrinsic(const In& in, Out& out) {
    const Date t = in.date("trade_date");
    const CurveInput d = curve_of(in, "discount");
    struct Name {
        HazardCurve h;
        double recovery, weight;
    };
    const auto names = rows_of<Name>(in, "names", [](const In& n) {
        return Name{hazard_of(n.need("hazard"), "hazard"), n.real("recovery"), n.real("weight")};
    });
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In tr(tv);
    const Date m = tr.date("maturity");
    const double coupon = tr.real("coupon"), quoted = in.real("quoted_upfront");
    in.ready();
    d.limit();
    limit_if(names.size() > max_quotes, "names");
    require_flat_forwards(d);
    if (names.empty()) throw Error("E_INPUT", "no names", "names");
    const Curve c = d.build();
    Vec ups;
    double sum = 0.0, wsum = 0.0;
    for (const Name& n : names) {
        if (!(n.weight >= 0.0)) throw Error("E_DOMAIN", "a weight is negative", "names");
        ups.push_back(cds_price(t, c, n.h, n.recovery, m, coupon, 1.0, CdsSide::Buy, CdsPayout::Standard).upfront);
        sum += n.weight * ups.back();
        wsum += n.weight;
    }
    if (!(wsum > 0.0)) throw Error("E_DOMAIN", "weights sum to zero", "names");
    out.key_reals("name_upfronts", ups);
    out.key_real("intrinsic_upfront", sum / wsum);
    out.key_real("basis", quoted - sum / wsum);
}

void op_credit_composite(const In& in, Out& out) {
    const Date t = in.date("trade_date");
    const CurveInput d = curve_of(in, "discount");
    const double r = in.real("recovery");
    struct Constituent {
        std::vector<CdsQuote> quotes;
        double weight;
    };
    const auto cs = rows_of<Constituent>(in, "constituents", [](const In& c) { return Constituent{cds_quotes_of(c), c.real("weight")}; });
    const double scale = in.real("scale");
    in.ready();
    d.limit();
    limit_if(cs.size() > max_quotes, "constituents");
    require_flat_forwards(d);
    if (cs.empty() || cs[0].quotes.empty()) throw Error("E_INPUT", "no constituents", "constituents");
    for (const Constituent& c : cs) {
        if (c.quotes.size() != cs[0].quotes.size()) throw Error("E_INPUT", "constituents must share tenors", "constituents");
        for (std::size_t j = 0; j < c.quotes.size(); ++j)
            if (c.quotes[j].tenor.count != cs[0].quotes[j].tenor.count || c.quotes[j].tenor.unit != cs[0].quotes[j].tenor.unit)
                throw Error("E_INPUT", "constituents must share tenors", "constituents");
    }
    if (!(scale > 0.0)) throw Error("E_DOMAIN", "scale must be positive", "scale");
    double wsum = 0.0;
    for (const Constituent& c : cs) {
        if (!(c.weight >= 0.0)) throw Error("E_DOMAIN", "a weight is negative", "constituents");
        wsum += c.weight;
    }
    if (!(wsum > 0.0)) throw Error("E_DOMAIN", "weights sum to zero", "constituents");
    std::vector<CdsQuote> q = cs[0].quotes;
    Vec spreads;
    for (std::size_t j = 0; j < q.size(); ++j) {
        double s = 0.0;
        for (const Constituent& c : cs) s += c.weight * c.quotes[j].spread;
        q[j].spread = scale * s / wsum;
        spreads.push_back(q[j].spread);
    }
    const HazardCurve h = cds_bootstrap(t, d.build(), r, q);
    out.key_reals("spreads", spreads);
    write_survival(out, h);
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

constexpr Entry credit_ops[] = {
    {"credit.cds.bootstrap", op_cds_bootstrap},
    {"credit.cds.price", op_cds_price},
    {"credit.cdsoption.implied_vol", op_cds_option_implied_vol},
    {"credit.cdsoption.price", op_cds_option_price},
    {"credit.copula.joint_default", op_copula_joint_default},
    {"credit.curve.composite", op_credit_composite},
    {"credit.index.intrinsic", op_index_intrinsic},
    {"credit.lhp.loss_cdf", op_lhp_loss_cdf},
    {"credit.lhp.tranche_loss", op_lhp_tranche_loss},
};
