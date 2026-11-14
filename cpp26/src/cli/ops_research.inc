// CLI handlers, stage J wave 1 research verbs (specifications/11-research/, rulings J-1 to J-19).
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.
// Order in every handler: read all inputs (E_SCHEMA), page limits (E_LIMIT), in.ready() (F-2), then the page checks.

constexpr EnumTable<research::Engine> research_engines = {{"EVENT", research::Engine::Event},
                                                          {"VECTOR", research::Engine::Vector}};
constexpr EnumTable<research::Metric> research_metrics = {{"SHARPE", research::Metric::Sharpe},
                                                          {"MEAN", research::Metric::Mean}};

void key_integers(Out& out, string_view k, const std::vector<long long>& v) {
    out.values.key(k);
    out.values.begin_array();
    for (const long long x : v) out.values.integer(x);
    out.values.end_array();
}

void op_research_backtest(const In& in, Out& out) {
    const auto engine = in.find("engine") ? in.choice("engine", research_engines) : research::Engine::Event;
    research::BacktestInput b;
    b.prices = in.reals("prices");
    b.targets = in.reals("targets");
    b.lag = in.integer("lag", 1);
    b.half_spread_bps = in.real("half_spread_bps", 0.0);
    b.commission_per_unit = in.real("commission_per_unit", 0.0);
    b.fixed_per_trade = in.real("fixed_per_trade", 0.0);
    b.multiplier = in.real("multiplier", 1.0);
    limit_if(b.prices.size() > 1000000 || b.targets.size() > 1000000, "prices");  // J-5
    in.ready();
    const research::Backtest r = research::backtest(b, engine);
    out.key_reals("positions", r.positions);
    out.key_reals("trades", r.trades);
    out.key_reals("pnl_gross", r.pnl_gross);
    out.key_reals("cost", r.cost);
    out.key_reals("pnl_net", r.pnl_net);
    out.key_reals("equity", r.equity);
    out.key_real("total_gross", r.total_gross);
    out.key_real("total_spread_cost", r.total_spread);
    out.key_real("total_commission", r.total_commission);
    out.key_real("total_fixed_cost", r.total_fixed);
    out.key_real("total_net", r.total_net);
    out.key_real("turnover", r.turnover);
    out.values.key("trade_count");
    out.values.integer(r.trade_count);
    out.key_real("max_drawdown", r.max_drawdown);
}

void op_research_purged_kfold(const In& in, Out& out) {
    const Vec t0 = in.reals("t0"), t1 = in.reals("t1");
    const long long k = in.integer("n_splits");
    const double pct = in.real("embargo_pct", 0.0);
    limit_if(t0.size() > 1000000 || t1.size() > 1000000, "t0");  // J-9
    in.ready();
    const research::PurgedKFold r = research::purged_kfold(t0, t1, k, pct);
    out.values.key("folds");
    out.values.begin_array();
    for (const research::Fold& f : r.folds) {
        out.values.begin_object();
        key_integers(out, "test", f.test);
        key_integers(out, "train", f.train);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("embargo_count");
    out.values.integer(r.embargo_count);
}

void op_research_cpcv_paths(const In& in, Out& out) {
    const long long groups = in.integer("n_groups"), test = in.integer("n_test_groups");
    in.ready();
    const research::CpcvCounts r = research::cpcv_paths(groups, test);
    out.values.key("n_splits");
    out.values.integer(r.n_splits);
    out.values.key("n_paths");
    out.values.integer(r.n_paths);
}

void op_research_viterbi(const In& in, Out& out) {
    const Vec initial = in.reals("initial");
    const Matrix transition = in.matrix("transition");
    const bool direct = in.find("emission") != nullptr;
    const bool gauss = in.find("observations") || in.find("means") || in.find("sds");
    const Matrix emission = direct ? in.matrix("emission") : Matrix{};
    const Vec y = in.find("observations") ? in.reals("observations") : Vec{};
    const Vec means = in.find("means") ? in.reals("means") : Vec{};
    const Vec sds = in.find("sds") ? in.reals("sds") : Vec{};
    const std::size_t k = initial.size(), steps = direct ? emission.size() : y.size();
    limit_if(steps > 100000, direct ? "emission" : "observations");  // J-12
    limit_if(k > 32, "initial");
    in.ready();
    const auto input_error = [](const char* why) { throw Error("E_INPUT", why); };
    if (direct == gauss) input_error("exactly one emission form is required (J-10)");
    if (k < 1 || transition.size() != k) input_error("transition must be K x K");
    for (const Vec& r : transition)
        if (r.size() != k) input_error("transition must be K x K");
    if (direct) {
        if (emission.empty()) input_error("no observations");
        for (const Vec& r : emission)
            if (r.size() != k) input_error("emission must be T x K");
    } else if (!in.find("observations") || !in.find("means") || !in.find("sds") || y.empty() || means.size() != k ||
               sds.size() != k) {
        input_error("observations, means and sds are required, with K means and sds");
    }
    research::check_model(initial, transition);
    const Matrix log_e = direct ? research::log_emission(emission) : research::gaussian_log_emission(y, means, sds);
    const research::ViterbiResult r = research::viterbi(initial, transition, log_e);
    key_integers(out, "states", r.states);
    out.key_real("log_probability", r.log_probability);
}

void op_research_psr(const In& in, Out& out) {
    const double sr = in.real("sr");
    const long long n = in.integer("n_obs");
    const double skew = in.real("skew", 0.0), kurt = in.real("kurtosis", 3.0), bench = in.real("sr_benchmark", 0.0);
    in.ready();
    const research::Psr r = research::psr(sr, n, skew, kurt, bench);
    out.key_real("z", r.z);
    out.key_real("psr", r.psr);
}

void op_research_dsr(const In& in, Out& out) {
    const double sr = in.real("sr");
    const long long n = in.integer("n_obs");
    const double skew = in.real("skew", 0.0), kurt = in.real("kurtosis", 3.0);
    const long long trials = in.integer("n_trials");
    const double var = in.real("sr_variance");
    in.ready();
    const research::Dsr r = research::dsr(sr, n, skew, kurt, trials, var);
    out.key_real("sr0", r.sr0);
    out.key_real("z", r.z);
    out.key_real("dsr", r.dsr);
}

void op_research_power(const In& in, Out& out) {
    const double years = in.real("years"), alpha = in.real("alpha", 0.05), pw = in.real("power", 0.8);
    const std::optional<double> target = in.find("sr_target") ? std::optional(in.real("sr_target")) : std::nullopt;
    in.ready();
    const research::Power r = research::power(years, alpha, pw, target);
    out.key_real("z_sum", r.z_sum);
    out.key_real("mds", r.mds);
    out.key_real("se_at_zero", r.se_at_zero);
    if (r.years_required) out.key_real("years_required", *r.years_required);
    if (r.se_at_target) out.key_real("se_at_target", *r.se_at_target);
}

void op_research_pbo(const In& in, Out& out) {
    const auto metric = in.find("metric") ? in.choice("metric", research_metrics) : research::Metric::Sharpe;
    const Matrix perf = in.matrix("performance");
    const long long s = in.integer("n_partitions");
    limit_if(s > 16, "n_partitions");  // J-15
    std::size_t cells = 0, widest = 0;
    for (const Vec& r : perf) {
        cells += r.size();
        widest = std::max(widest, r.size());
    }
    limit_if(cells > 10000000 || widest > 10000, "performance");
    in.ready();
    const research::Pbo r = research::pbo(perf, s, metric);
    out.key_real("pbo", r.pbo);
    out.key_reals("logits", r.logits);
    out.values.key("n_combinations");
    out.values.integer(r.n_combinations);
}

constexpr Entry research_ops[] = {
    {"research.backtest.run", op_research_backtest},
    {"research.cv.purged_kfold", op_research_purged_kfold},
    {"research.cv.cpcv_paths", op_research_cpcv_paths},
    {"research.regime.viterbi", op_research_viterbi},
    {"research.stats.psr", op_research_psr},
    {"research.stats.dsr", op_research_dsr},
    {"research.stats.power", op_research_power},
    {"research.stats.pbo", op_research_pbo},
};
