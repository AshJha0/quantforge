// Stage E, E6: correlation. Included by dispatch.cpp after ops_e4.inc.

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
