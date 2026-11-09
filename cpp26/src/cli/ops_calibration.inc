// CLI handlers, the calibration verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_calib_fit(const In& in, Out& out) {
    FitInputs f;
    f.model = in.choice<FitModel>("model", {{"LINEAR", FitModel::Linear}, {"EXPONENTIAL", FitModel::Exponential},
                                            {"NELSON_SIEGEL", FitModel::NelsonSiegel}, {"ROSENBROCK", FitModel::Rosenbrock}});
    if (f.model != FitModel::Rosenbrock || in.find("x")) f.x = in.reals("x");
    if (f.model != FitModel::Rosenbrock || in.find("y")) f.y = in.reals("y");
    f.start = in.reals("start");
    f.method = in.choice<FitMethod>("method", {{"GAUSS_NEWTON", FitMethod::GaussNewton},
                                               {"LEVENBERG_MARQUARDT", FitMethod::LevenbergMarquardt}, {"BFGS", FitMethod::Bfgs}});
    f.weights = maybe_vector(in, "weights");
    f.regularisation = in.real("regularisation", 0.0);
    f.prior = maybe_vector(in, "prior");
    f.lower = maybe_vector(in, "lower");
    f.upper = maybe_vector(in, "upper");
    f.max_iter = in.integer("max_iter", 1000);
    const bool report = in.boolean("report_parameters", true);
    in.ready();
    limit_if(f.start.size() > 20, "start");
    limit_if(f.max_iter > 100000, "max_iter");
    const FitResult r = fit(f);
    if (report) out.key_reals("parameters", r.parameters);
    out.key_real("objective", r.objective);
    out.diagnostics.key("iterations");
    out.diagnostics.integer(r.iterations);
    out.diagnostics.key("status");
    out.diagnostics.string(r.status);
    out.diagnostics.key("residuals");
    out.diagnostics.begin_array();
    for (const double v : r.residuals) out.diagnostics.real(v);
    out.diagnostics.end_array();
}

void op_check_bid_ask(const In& in, Out& out) {
    const Vec fitted = in.reals("fitted"), bid = in.reals("bid"), ask = in.reals("ask");
    in.ready();
    const auto breaches = check_bid_ask(fitted, bid, ask);
    out.values.key("breaches");
    out.values.begin_array();
    for (const Breach& b : breaches) {
        out.values.begin_object();
        key_int(out, "index", (long long)b.index);
        out.key_string("side", b.side);
        out.key_real("distance", b.distance);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_curve_report(const In& in, Out& out) {
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const CurveReport r = curve_report(*c, as_of, quotes, interpolation);
    out.values.key("jacobian");
    out.values.begin_array();
    for (const Vec& row : r.jacobian) {
        out.values.begin_array();
        for (const double v : row) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
    out.key_real("condition_number", r.condition_number);
    out.diagnostics.key("inputs");
    out.diagnostics.begin_array();
    for (const Value& q : in.need("quotes").items) out.diagnostics.string(q.find("tenor")->text);
    out.diagnostics.end_array();
    out.diagnostics.key("status");
    out.diagnostics.string("OK");
    out.diagnostic("max_repricing_error", r.max_repricing_error);
    out.diagnostics.key("tolerance_breaches");
    out.diagnostics.begin_array();
    out.diagnostics.end_array();
}

void op_curve_smooth(const In& in, Out& out) {
    const Vec knots = in.reals("knots"), m = in.reals("maturities"), y = in.reals("zero_rates");
    const double lambda = in.real("lambda");
    std::optional<Vec> w;
    if (const Value* wv = in.raw().find("weights")) w = to_reals(*wv, "weights");
    in.ready();
    const SmoothFit f = smooth_fit(knots, m, y, lambda, w);
    out.key_reals("forwards", f.forwards);
    out.key_reals("fitted", f.fitted);
    out.key_real("objective", f.objective);
}

void op_curve_robust(const In& in, Out& out) {
    const Vec m = in.reals("maturities"), y = in.reals("zero_rates");
    const double tau = in.real("tau"), delta = in.real("delta");
    in.ready();
    const RobustFit f = robust_fit(m, y, tau, delta);
    out.key_reals("betas", f.betas);
    out.key_reals("residuals", f.residuals);
    out.values.key("outliers");
    out.values.begin_array();
    for (const std::size_t j : f.outliers) out.values.integer((long long)j);
    out.values.end_array();
    out.key_real("objective", f.objective);
}

constexpr Entry calibration_ops[] = {
    {"calib.check_bid_ask", op_check_bid_ask},
    {"calib.curve.robust", op_curve_robust},
    {"calib.curve.smooth", op_curve_smooth},
    {"calib.curve_report", op_curve_report},
    {"calib.fit", op_calib_fit},
};
