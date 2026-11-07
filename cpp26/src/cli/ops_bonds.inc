// Stage D, D2 bonds and repo. Included by dispatch.cpp after ops_stage_d.inc.

Bond bond_fields(const In& b) {
    const Date maturity = b.date("maturity");
    const double coupon = b.real("coupon");
    const long long f = b.integer("frequency");
    if (f != 1 && f != 2 && f != 4) schema("frequency", "must be 1, 2 or 4");
    return {maturity, coupon, int(f)};
}

Bond bond_of(const In& in) {
    const Value& v = in.need("bond");
    if (v.kind != Kind::Object) schema("bond", "expected an object");
    return bond_fields(In(v));
}

void op_bond_from_yield(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const double y = in.real("yield");
    in.ready();
    const YieldPrice p = price_from_yield(b, s, y);
    out.key_real("dirty", p.dirty);
    out.key_real("accrued", p.accrued);
    out.key_real("clean", p.clean);
    out.key_real("modified_duration", p.modified_duration);
    out.key_real("macaulay_duration", p.macaulay_duration);
    out.key_real("convexity", p.convexity);
}

void op_bond_yield(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const double clean = in.real("clean_price");
    in.ready();
    const double y = yield_from_price(b, s, clean);
    const double acc = accrued(b, s);
    out.key_real("yield", y);
    out.key_real("dirty", clean + acc);
    out.key_real("accrued", acc);
}

void op_bond_from_curve(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const CurveInput ci = curve_of(in, "curve");
    in.ready();
    ci.limit();
    const double dirty = curve_dirty(b, s, ci.build(), 0.0), acc = accrued(b, s);
    out.key_real("dirty", dirty);
    out.key_real("accrued", acc);
    out.key_real("clean", dirty - acc);
}

void op_bond_z(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const CurveInput ci = curve_of(in, "curve");
    const double clean = in.real("clean_price");
    in.ready();
    ci.limit();
    out.key_real("z_spread", z_spread(b, s, ci.build(), clean));
}

void op_bond_asw(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const CurveInput ci = curve_of(in, "curve");
    const double dirty = in.real("dirty_price");
    in.ready();
    ci.limit();
    const AssetSwap a = asset_swap(b, s, ci.build(), dirty);
    out.key_real("spread", a.spread);
    out.key_real("annuity", a.annuity);
}

void op_frn(const In& in, Out& out) {
    const Date s = in.date("settlement"), m = in.date("maturity");
    const long long f = in.integer("frequency");
    if (f != 1 && f != 2 && f != 4) schema("frequency", "must be 1, 2 or 4");
    const Frn n{m, int(f), in.real("current_rate"), in.real("margin"), in.real("discount_margin")};
    const CurveInput d = curve_of(in, "discount"), p = curve_of(in, "projection");
    in.ready();
    d.limit();
    p.limit();
    const FrnPrice r = frn_price(n, s, d.build(), p.build());
    out.key_real("dirty", r.dirty);
    out.key_real("accrued", r.accrued);
    out.key_real("clean", r.clean);
}

void op_repo_forward(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date start = in.date("start"), end = in.date("end");
    const double clean = in.real("clean_price"), r = in.real("repo_rate");
    const Value* g = in.raw().find("gc_rate");
    if (!g) schema("gc_rate", "missing");
    const std::optional<double> gc = g->kind == Kind::Null ? std::nullopt : std::optional<double>(to_real(*g, "gc_rate"));
    in.ready();
    const RepoForward f = repo_forward(b, start, end, clean, r, gc);
    out.key_real("dirty", f.dirty);
    out.key_real("forward_dirty", f.forward_dirty);
    out.key_real("forward_clean", f.forward_clean);
    out.key_real("interest", f.interest);
    out.key_maybe("special_spread", f.special_spread);
    out.key_maybe("specialness_value", f.specialness_value);
}

void op_repo_implied(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date start = in.date("start"), end = in.date("end");
    const double clean = in.real("clean_price"), fc = in.real("forward_clean");
    in.ready();
    out.key_real("repo_rate", repo_implied_rate(b, start, end, clean, fc));
}

Date delivery_month_of(const In& in) {
    const string& m = in.text("delivery_month");
    const auto d = m.size() == 7 ? parse_date(m + "-01") : std::nullopt;
    if (!d) schema("delivery_month", "expected YYYY-MM");
    return *d;
}

void op_conversion_factor(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date d = delivery_month_of(in);
    const double nc = in.real("notional_coupon");
    in.ready();
    out.key_real("conversion_factor", conversion_factor(b, d, nc));
}

void op_futures_basis(const In& in, Out& out) {
    const double f = in.real("futures_price");
    const Date s = in.date("settlement"), d = in.date("delivery");
    const double r = in.real("repo_rate");
    const auto bonds = rows_of<BasisBond>(in, "bonds", [](const In& row) {
        return BasisBond{bond_fields(row), row.real("clean_price"), row.real("conversion_factor")};
    });
    in.ready();
    limit_if(bonds.size() > max_quotes, "bonds");
    const Basis b = futures_basis(f, s, d, r, bonds);
    out.values.key("bonds");
    out.values.begin_array();
    for (const BasisRow& row : b.bonds) {
        out.values.begin_object();
        out.key_real("invoice", row.invoice);
        out.key_real("gross_basis", row.gross_basis);
        out.key_real("net_basis", row.net_basis);
        out.key_real("implied_repo", row.implied_repo);
        out.values.end_object();
    }
    out.values.end_array();
    key_int(out, "ctd", (long long)b.ctd);
}

void op_bond_ns(const In& in, Out& out) {
    const Date s = in.date("settlement");
    const double tau = in.real("tau");
    const auto bonds = rows_of<NsBond>(in, "bonds", [](const In& row) { return NsBond{bond_fields(row), row.real("dirty_price")}; });
    std::optional<Vec> w;
    if (const Value* wv = in.raw().find("weights")) w = to_reals(*wv, "weights");
    in.ready();
    limit_if(bonds.size() > max_quotes, "bonds");
    const NsFit fit = bond_nelson_siegel(s, tau, bonds, w);
    out.key_reals("betas", fit.betas);
    out.key_reals("residuals", fit.residuals);
}
