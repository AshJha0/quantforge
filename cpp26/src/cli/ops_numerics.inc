// CLI handlers, random numbers, roots, integrals, interpolation, linear algebra, statistics, time series and engines.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_next_u64(const In& in, Out& out) {
    auto d = draws(in);
    write_u64s(out, d.rng, d.count);
}

void op_uniforms(const In& in, Out& out) {
    auto d = draws(in);
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < d.count; ++i) out.values.real(d.rng.next_uniform());
    out.values.end_array();
}

void op_normals(const In& in, Out& out) {
    auto d = draws(in);
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < d.count; ++i) out.values.real(d.rng.next_normal());
    out.values.end_array();
}

void op_inverse_normal(const In& in, Out& out) {
    const Vec p = in.reals("p");
    in.ready();
    Vec z;
    z.reserve(p.size());
    for (const double v : p) {
        if (v <= 0.0 || v >= 1.0) throw Error("E_DOMAIN", "p must lie in (0, 1)", "p");
        z.push_back(ppnd16(v));
    }
    out.key_reals("z", z);
}

void op_set_state(const In& in, Out& out) {
    const Value& a = in.need("state");
    if (a.kind != Kind::Array || a.items.size() != 4) schema("state", "expected four u64 strings");
    Xoshiro256::State s{};
    for (std::size_t i = 0; i < 4; ++i) s[i] = to_u64(a.items[i], "state");
    const long long count = draw_count(in);
    in.ready();
    limit_if(count > 100000, "count");
    if (s == Xoshiro256::State{}) throw Error("E_INPUT", "the state is all zero", "state");
    Xoshiro256 rng(s);
    write_u64s(out, rng, count);
}

void op_sobol(const In& in, Out& out) {
    const long long dimensions = in.integer("dimensions"), count = in.integer("count"), skip = in.integer("skip", 0);
    in.ready();
    limit_if(product_above(count, dimensions, 100000), "count");
    limit_if(skip > 10000000, "skip");
    check_sobol_request(dimensions, count, skip);
    Sobol sobol{int(dimensions), std::uint64_t(skip)};
    Vec point(std::size_t(dimensions), 0.0);
    out.values.key("points");
    out.values.begin_array();
    for (long long i = 0; i < count; ++i) {
        sobol.next(point.data());
        out.values.begin_array();
        for (const double v : point) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
}

void op_bisection(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    write_root(out, bisection(fn.f, a, b, root_options(in)));
}

void op_brent(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    write_root(out, brent(fn.f, a, b, root_options(in)));
}

void op_newton(const In& in, Out& out) {
    const auto fn = root_function(in.text("function"));
    const double x0 = in.real("x0");
    if (bool(in.find("a")) != bool(in.find("b"))) schema("a", "a and b must both be given or both absent");
    std::optional<Bracket> bracket;
    if (in.find("a")) bracket = Bracket{in.real("a"), in.real("b")};
    write_root(out, newton(fn.f, fn.df, x0, bracket, root_options(in)));
}

void op_trapezoid(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    limit_if(n > 10000000, "n");
    out.key_real("value", trapezoid(f, a, b, n));
}

void op_simpson(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    limit_if(n > 10000000, "n");
    out.key_real("value", simpson(f, a, b, n));
}

void op_gauss_legendre(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b");
    const long long n = in.integer("n");
    in.ready();
    out.key_real("value", gauss_legendre(f, a, b, n));
}

void op_adaptive_simpson(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b"), tol = in.real("tol", 1e-10);
    const long long max_depth = in.integer("max_depth", 50);
    in.ready();
    limit_if(max_depth > 60, "max_depth");
    out.key_real("value", adaptive_simpson(f, a, b, tol, max_depth));
}

void op_gauss_kronrod(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double a = in.real("a"), b = in.real("b"), tol = in.real("tol", 1e-10);
    const long long max_intervals = in.integer("max_intervals", 500);
    in.ready();
    limit_if(max_intervals > 10000, "max_intervals");
    const auto r = gauss_kronrod(f, a, b, tol, max_intervals);
    out.key_real("value", r.value);
    out.diagnostics.key("error_estimate");
    out.diagnostics.real(r.error_estimate);
}

void op_central(const In& in, Out& out) {
    const Fn f = plain_function(in.text("function"));
    const double x = in.real("x"), h = in.real("h");
    const long long order = in.integer("order");
    if (order != 1 && order != 2) schema("order", "must be 1 or 2");
    in.ready();
    out.key_real("value", central_difference(f, x, h, order));
}

void op_interp(const In& in, Out& out) {
    using enum InterpMethod;
    const InterpMethod method = in.choice<InterpMethod>(
        "method", {{"linear", Linear}, {"log_linear", LogLinear}, {"cubic_natural", CubicNatural},
                   {"cubic_clamped", CubicClamped}, {"cubic_not_a_knot", CubicNotAKnot},
                   {"monotone_pchip", MonotonePchip}, {"tension", Tension}});
    const Vec x = in.reals("x"), y = in.reals("y"), at = in.reals("at");
    InterpParams p;
    if (method == CubicClamped) {
        p.slope_start = in.real("slope_start");
        p.slope_end = in.real("slope_end");
    }
    if (method == Tension) p.tension = in.real("tension");
    in.ready();
    const auto r = interpolate(method, x, y, at, p);
    out.key_reals("values", r.values);
    if (method != Linear && method != LogLinear) out.key_reals("derivatives", r.derivatives);
}

void op_monotone_convex(const In& in, Out& out) {
    const Vec t = in.reals("t"), r = in.reals("r"), at = in.reals("at");
    const bool positive = in.boolean("positive", false);
    in.ready();
    const auto v = monotone_convex(t, r, at, positive);
    out.key_reals("forwards", v.forwards);
    out.key_reals("zero_rates", v.zero_rates);
}

void op_solve(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    const Vec b = in.reals("b");
    in.ready();
    limit_if(a.size() > 200, "a");
    out.key_reals("x", solve_linear(a, b));
}

void op_cholesky(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    in.ready();
    limit_if(a.size() > 200, "a");
    const Matrix l = cholesky(a);
    out.values.key("l");
    out.values.begin_array();
    for (const Vec& row : l) {
        out.values.begin_array();
        for (const double v : row) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
}

void op_eigen(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    in.ready();
    limit_if(a.size() > 200, "a");
    out.key_reals("values", eigen_symmetric(a));
}

void op_normal(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    Vec pdf, cdf;
    for (const double v : x) {
        pdf.push_back(normal_pdf(v));
        cdf.push_back(normal_cdf(v));
    }
    out.key_reals("pdf", pdf);
    out.key_reals("cdf", cdf);
}

void op_summary(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    const Summary s = summary(x);
    out.values.key("count");
    out.values.integer((long long)s.count);
    out.key_real("mean", s.mean);
    out.key_real("variance", s.variance);
    out.key_real("stdev", s.stdev);
    out.key_maybe("skewness", s.skewness);
    out.key_maybe("excess_kurtosis", s.excess_kurtosis);
    out.key_real("min", s.min);
    out.key_real("max", s.max);
}

void op_quantile(const In& in, Out& out) {
    const Vec x = in.reals("x"), p = in.reals("p");
    in.ready();
    out.key_reals("values", quantiles(x, p));
}

void op_covariance(const In& in, Out& out) {
    const Vec x = in.reals("x"), y = in.reals("y");
    in.ready();
    const Covariance c = covariance(x, y);
    out.key_real("covariance", c.covariance);
    out.key_maybe("correlation", c.correlation);
}

void op_ols(const In& in, Out& out) {
    const Vec x = in.reals("x"), y = in.reals("y");
    in.ready();
    const Ols r = ols(x, y);
    out.key_real("alpha", r.alpha);
    out.key_real("beta", r.beta);
    out.key_maybe("r_squared", r.r_squared);
    out.key_real("se_alpha", r.se_alpha);
    out.key_real("se_beta", r.se_beta);
}

void op_returns(const In& in, Out& out) {
    const Vec p = in.reals("prices");
    const auto kind = in.choice<ReturnKind>("kind", {{"SIMPLE", ReturnKind::Simple}, {"LOG", ReturnKind::Log}});
    in.ready();
    out.key_reals("returns", returns(p, kind));
}

void op_rolling(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long window = in.integer("window");
    const auto s = in.choice<RollingStatistic>("statistic", {{"MEAN", RollingStatistic::Mean}, {"STDEV", RollingStatistic::Stdev}});
    in.ready();
    limit_if(window > 1000, "window");
    out.key_maybes("values", rolling(x, window, s));
}

void op_ewma(const In& in, Out& out) {
    const Vec r = in.reals("returns");
    const double lambda = in.real("lambda");
    in.ready();
    out.key_reals("variance", ewma_variance(r, lambda));
}

void op_autocorrelation(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long max_lag = in.integer("max_lag");
    in.ready();
    limit_if(max_lag > 1000, "max_lag");
    out.key_reals("acf", autocorrelation(x, max_lag));
}

void op_ljung_box(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const long long max_lag = in.integer("max_lag");
    in.ready();
    limit_if(max_lag > 1000, "max_lag");
    out.key_real("statistic", ljung_box(x, max_lag));
}

void op_ar1(const In& in, Out& out) {
    const Vec x = in.reals("x");
    in.ready();
    const Ar1 r = ar1(x);
    out.key_real("constant", r.constant);
    out.key_real("phi", r.phi);
    out.key_real("sigma", r.sigma);
}

void op_resample_last(const In& in, Out& out) {
    const Value& a = in.need("dates");
    if (a.kind != Kind::Array) schema("dates", "expected an array");
    std::vector<Date> dates;
    for (const Value& v : a.items) dates.push_back(to_date(v, "dates"));
    const auto values = in.maybe_reals("values");
    const auto f = in.choice<ResampleFrequency>("frequency", {{"WEEK", ResampleFrequency::Week}, {"MONTH", ResampleFrequency::Month}});
    in.ready();
    const Resampled r = resample_last(dates, values, f);
    out.values.key("dates");
    out.values.begin_array();
    for (const Date d : r.dates) out.values.string(format_date(d));
    out.values.end_array();
    out.key_reals("values", r.values);
}

void op_forward_fill(const In& in, Out& out) {
    const auto values = in.maybe_reals("values");
    const long long limit = in.integer("limit");
    in.ready();
    out.key_maybes("values", forward_fill(values, limit));
}

void op_pde(const In& in, Out& out) {
    PdeInputs p{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
                in.real("sigma"), in.real("t"), in.integer("space_steps"), in.integer("time_steps"),
                in.real("width", 6.0), in.integer("rannacher_steps", 2)};
    in.ready();
    limit_if(product_above(p.space_steps, p.time_steps, 10000000), "space_steps");
    const PdeResult r = pde_bs_european(p);
    out.key_real("price", r.price);
    out.key_real("delta", r.delta);
    out.key_real("gamma", r.gamma);
    out.diagnostic("grid_h", r.grid_h);
}

void op_mc(const In& in, Out& out) {
    using enum McMethod;
    McInputs m{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
               in.real("sigma"), in.real("t"), in.integer("paths"), in.integer("steps", 1), in.u64("seed"),
               stream_of(in.integer("stream", 0)),
               in.choice<McMethod>("method", {{"PLAIN", Plain}, {"ANTITHETIC", Antithetic},
                                              {"CONTROL_VARIATE", ControlVariate}, {"SOBOL", Sobol}})};
    in.ready();
    limit_if(product_above(m.paths, m.steps, 1000000), "paths");
    const McResult r = mc_gbm_european(m);
    out.key_real("price", r.price);
    out.key_real("stderr", r.standard_error);
}

void op_cos(const In& in, Out& out) {
    const Value& mv = in.need("model");
    if (mv.kind != Kind::Object) schema("model", "expected an object");
    const In model(mv);
    CosModel m{model.choice<CosModelName>("name", {{"BLACK_SCHOLES", CosModelName::BlackScholes}, {"HESTON", CosModelName::Heston}})};
    m.sigma = model.real("sigma");
    if (m.name == CosModelName::Heston) {
        m.v0 = model.real("v0");
        m.kappa = model.real("kappa");
        m.theta = model.real("theta");
        m.rho = model.real("rho");
    }
    const CosInputs c{in.choice("option", option_types), in.real("spot"), in.real("strike"), in.real("r"), in.real("q"),
                      in.real("t"), m, in.integer("terms"), in.real("truncation")};
    in.ready();
    limit_if(c.terms > 100000, "terms");
    const CosResult r = cos_european(c);
    out.key_real("price", r.price);
    out.diagnostic("a", r.a);
    out.diagnostic("b", r.b);
}

constexpr Entry numerics_ops[] = {
    {"core.cos.european", op_cos},
    {"core.diff.central", op_central},
    {"core.integrate.adaptive_simpson", op_adaptive_simpson},
    {"core.integrate.gauss_kronrod", op_gauss_kronrod},
    {"core.integrate.gauss_legendre", op_gauss_legendre},
    {"core.integrate.simpson", op_simpson},
    {"core.integrate.trapezoid", op_trapezoid},
    {"core.interp.evaluate", op_interp},
    {"core.interp.monotone_convex", op_monotone_convex},
    {"core.linalg.cholesky", op_cholesky},
    {"core.linalg.eigen_symmetric", op_eigen},
    {"core.linalg.solve", op_solve},
    {"core.mc.gbm_european", op_mc},
    {"core.pde.bs_european", op_pde},
    {"core.rng.inverse_normal", op_inverse_normal},
    {"core.rng.next_u64", op_next_u64},
    {"core.rng.normals", op_normals},
    {"core.rng.set_state_next_u64", op_set_state},
    {"core.rng.uniforms", op_uniforms},
    {"core.root.bisection", op_bisection},
    {"core.root.brent", op_brent},
    {"core.root.newton", op_newton},
    {"core.sobol.points", op_sobol},
    {"core.stats.covariance", op_covariance},
    {"core.stats.normal", op_normal},
    {"core.stats.ols", op_ols},
    {"core.stats.quantile", op_quantile},
    {"core.stats.summary", op_summary},
    {"core.ts.ar1", op_ar1},
    {"core.ts.autocorrelation", op_autocorrelation},
    {"core.ts.ewma_variance", op_ewma},
    {"core.ts.forward_fill", op_forward_fill},
    {"core.ts.ljung_box", op_ljung_box},
    {"core.ts.resample_last", op_resample_last},
    {"core.ts.returns", op_returns},
    {"core.ts.rolling", op_rolling},
};
