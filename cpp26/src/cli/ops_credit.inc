// Stage D, D4 credit. Included by dispatch.cpp after ops_bonds.inc.

HazardCurve hazard_of(const Value& v, string_view key) {
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In h(v);
    HazardCurve out{h.date("as_of"), {}, {}};
    for (const auto& [d, s] : rows_of<std::pair<Date, double>>(h, "pillars", [](const In& row) {
             return std::pair{row.date("date"), row.real("survival")};
         })) {
        out.dates.push_back(d);
        out.survival.push_back(s);
    }
    return out;
}

void write_survival(Out& out, const HazardCurve& h) {
    out.values.key("pillars");
    out.values.begin_array();
    for (std::size_t i = 0; i < h.dates.size(); ++i) {
        out.values.begin_object();
        out.key_string("date", format_date(h.dates[i]));
        out.key_real("survival", h.survival[i]);
        out.values.end_object();
    }
    out.values.end_array();
}

// Ruling R1-4: ISDA flat forwards only, checked before every other rule check.
void require_flat_forwards(const CurveInput& d) {
    if (d.interpolation != CurveInterpolation::LogLinearDf)
        throw Error("E_INPUT", "credit needs a LOG_LINEAR_DF discount curve", "discount");
}

std::vector<CdsQuote> cds_quotes_of(const In& in) {
    return rows_of<CdsQuote>(in, "quotes", [](const In& q) { return CdsQuote{parse_tenor(q.text("tenor")), q.real("spread")}; });
}

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
