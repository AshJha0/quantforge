// CLI handlers, stage F carry-over wave 2b landed in stage G: F3 sensitivities (06-risk/f3-sensitivities.md, G-47)
// and F4 portfolio tools (06-risk/portfolio-risk-tools.md, G-46). Closed forms on their inputs.
// Included by dispatch.cpp inside its unnamed namespace.

void op_sens_inflation01(const In& in, Out& out) {
    const double N = in.real("notional");
    const long long n = in.integer("years");
    const double K = in.real("fixed_rate"), z = in.real("market_rate"), P = in.real("discount_factor");
    in.ready();
    if (n < 1) throw Error("E_DOMAIN", "years is below 1", "years");
    if (!(1 + z > 0)) throw Error("E_DOMAIN", "1 + market_rate is not positive", "market_rate");
    if (!(1 + K > 0)) throw Error("E_DOMAIN", "1 + fixed_rate is not positive", "fixed_rate");
    if (!(P > 0)) throw Error("E_DOMAIN", "discount_factor is not positive", "discount_factor");
    const double dn = static_cast<double>(n);
    const auto pv = [&](double zz) { return N * P * (std::pow(1 + zz, dn) - std::pow(1 + K, dn)); };
    const double v = pv(z);
    out.key_real("pv", v);
    out.key_real("inflation01", N * P * dn * std::pow(1 + z, dn - 1) * 1e-4);
    out.key_real("inflation01_bump", pv(z + 1e-4) - v);
}

void op_sens_dividend_borrow(const In& in, Out& out) {
    const double S = in.real("spot"), K = in.real("strike"), T = in.real("expiry_years"), r = in.real("rate");
    const double q = in.real("dividend_yield"), b = in.real("borrow_rate"), v = in.real("vol");
    const bool call = sr_enum<bool>(in, "option_type", {{"CALL", true}, {"PUT", false}});
    in.ready();
    sr_positive(S, "spot");
    sr_positive(K, "strike");
    sr_positive(T, "expiry_years");
    sr_positive(v, "vol");
    const double y = q + b, sT = std::sqrt(T);
    const double d1 = (std::log(S / K) + (r - y + v * v / 2) * T) / (v * sT), d2 = d1 - v * sT;
    const double fS = S * std::exp(-y * T), dK = K * std::exp(-r * T);
    const double price = call ? fS * normal_cdf(d1) - dK * normal_cdf(d2) : dK * normal_cdf(-d2) - fS * normal_cdf(-d1);
    const double dvdy = call ? -T * fS * normal_cdf(d1) : T * fS * normal_cdf(-d1);
    out.key_real("price", price);
    out.key_real("dividend01", dvdy * 1e-4);
    out.key_real("borrow01", dvdy * 1e-4);
}

void op_sens_correlation(const In& in, Out& out) {
    const double S1 = in.real("spot1"), S2 = in.real("spot2"), Q1 = in.real("quantity1"), Q2 = in.real("quantity2");
    const double q1 = in.real("yield1"), q2 = in.real("yield2"), v1 = in.real("vol1"), v2 = in.real("vol2");
    const double rho = in.real("correlation"), T = in.real("expiry_years");
    in.ready();
    sr_positive(S1, "spot1");
    sr_positive(S2, "spot2");
    sr_positive(Q1, "quantity1");
    sr_positive(Q2, "quantity2");
    if (!(v1 >= 0)) throw Error("E_DOMAIN", "vol1 is negative", "vol1");
    if (!(v2 >= 0)) throw Error("E_DOMAIN", "vol2 is negative", "vol2");
    if (!(rho >= -1 && rho <= 1)) throw Error("E_DOMAIN", "correlation must lie in [-1, 1]", "correlation");
    sr_positive(T, "expiry_years");
    const double s2 = v1 * v1 + v2 * v2 - 2 * rho * v1 * v2;
    if (!(s2 > 0)) throw Error("E_DOMAIN", "the spread volatility is zero", "correlation");
    const double s = std::sqrt(s2), sT = std::sqrt(T);
    const double F1 = Q1 * S1 * std::exp(-q1 * T), F2 = Q2 * S2 * std::exp(-q2 * T);
    const double d1 = (std::log(F1 / F2) + s2 * T / 2) / (s * sT);
    const double pdf = std::exp(-d1 * d1 / 2) / std::sqrt(2 * 3.14159265358979323846);
    out.key_real("price", F1 * normal_cdf(d1) - F2 * normal_cdf(d1 - s * sT));
    out.key_real("correlation01", F1 * pdf * sT * (-v1 * v2 / s) * 0.01);
    out.key_real("spread_vol", s);
}

std::vector<Vec> gb_matrix(const In& in, const char* key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Array) schema(key, "expected an array");
    limit_if(v.items.size() > 10000, key);
    std::vector<Vec> m;
    for (const Value& r : v.items) m.push_back(to_reals(r, key));
    return m;
}

void op_stress_reverse(const In& in, Out& out) {
    const Vec d = in.reals("direction"), delta = in.reals("delta");
    const std::vector<Vec> G = gb_matrix(in, "gamma");
    const double L = in.real("target_loss");
    in.ready();
    const std::size_t n = d.size();
    if (n == 0 || delta.size() != n || G.size() != n) throw Error("E_INPUT", "lengths differ", "delta");
    for (const Vec& r : G)
        if (r.size() != n) throw Error("E_INPUT", "gamma is not square", "gamma");
    if (!(L > 0)) throw Error("E_DOMAIN", "target_loss is not positive", "target_loss");
    double b = 0.0, a = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        b += delta[i] * d[i];
        for (std::size_t j = 0; j < n; ++j) a += d[i] * G[i][j] * d[j];
    }
    a /= 2;
    // Smallest k > 0 with a k^2 + b k + L = 0.
    std::optional<double> k;
    const auto take = [&](double x) {
        if (std::isfinite(x) && x > 0 && (!k || x < *k)) k = x;
    };
    if (a == 0.0) {
        if (b != 0.0) take(-L / b);
    } else {
        const double disc = b * b - 4 * a * L;
        if (disc >= 0) {
            const double q = -(b + (b >= 0 ? 1.0 : -1.0) * std::sqrt(disc)) / 2;
            if (q != 0.0) {
                take(q / a);
                take(L / q);
            }
        }
    }
    if (!k) throw Error("E_DOMAIN", "no positive scale reaches the target loss", "target_loss");
    Vec shocks(n);
    for (std::size_t i = 0; i < n; ++i) shocks[i] = *k * d[i];
    out.key_real("scale", *k);
    out.key_reals("shocks", shocks);
    out.key_real("pnl", -L);
}

void op_limits_check(const In& in, Out& out) {
    const Value& mv = in.need("measures");
    const Value& lv = in.need("limits");
    if (mv.kind != Kind::Object) schema("measures", "expected an object");
    if (lv.kind != Kind::Object) schema("limits", "expected an object");
    std::map<string, double> measures;
    for (const auto& m : mv.members) measures[m.first] = to_real(m.second, "measures");
    std::map<string, std::pair<double, double>> limits;
    for (const auto& m : lv.members) {
        if (m.second.kind != Kind::Object) schema("limits", "expected an object");
        const In l(m.second);
        limits[m.first] = {l.real("soft"), l.real("hard")};
        l.ready();
    }
    in.ready();
    for (const auto& [name, sh] : limits)
        if (!(sh.first >= 0 && sh.first <= sh.second)) throw Error("E_DOMAIN", "a limit needs 0 <= soft <= hard", "limits");
    for (const auto& [name, v] : measures)
        if (!limits.count(name)) throw Error("E_INPUT", "a measure has no limit", "limits");
    int worst = 0;
    const char* names[] = {"OK", "WARN", "BREACH"};
    out.values.key("measures");
    out.values.begin_object();
    for (const auto& [name, v] : measures) {
        const auto [soft, hard] = limits[name];
        const double x = std::fabs(v);
        const int st = x > hard ? 2 : (x >= soft ? 1 : 0);
        worst = std::max(worst, st);
        out.values.key(name);
        out.values.begin_object();
        out.key_real("utilisation", x / hard);
        out.key_string("status", names[st]);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_string("overall", names[worst]);
}

void op_concentration(const In& in, Out& out) {
    const Vec x = in.reals("exposures");
    const long long top = in.integer("top_n");
    in.ready();
    limit_if(x.size() > 10000000, "exposures");
    if (x.empty()) throw Error("E_DOMAIN", "exposures is empty", "exposures");
    if (top < 1 || top > static_cast<long long>(x.size())) throw Error("E_INPUT", "top_n must lie in 1 .. count", "top_n");
    double total = 0.0;
    for (double v : x) total += std::fabs(v);
    if (!(total > 0)) throw Error("E_DOMAIN", "every exposure is zero", "exposures");
    Vec w(x.size());
    double hhi = 0.0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        w[i] = std::fabs(x[i]) / total;
        hhi += w[i] * w[i];
    }
    Vec s = w;
    std::sort(s.begin(), s.end(), std::greater<>());
    double share = 0.0;
    for (long long i = 0; i < top; ++i) share += s[static_cast<std::size_t>(i)];
    out.key_real("hhi", hhi);
    out.key_real("effective_number", 1 / hhi);
    out.key_real("top_n_share", share);
    out.key_reals("weights", w);
}

void op_var_liquidity(const In& in, Out& out) {
    const double var = in.real("var"), z = in.real("z");
    const Vec P = in.reals("position_values"), mu = in.reals("spread_mean"), sg = in.reals("spread_vol");
    in.ready();
    if (mu.size() != P.size() || sg.size() != P.size()) throw Error("E_INPUT", "lengths differ", "spread_mean");
    if (!(var >= 0)) throw Error("E_DOMAIN", "var is negative", "var");
    for (std::size_t i = 0; i < P.size(); ++i)
        if (!(mu[i] >= 0) || !(sg[i] >= 0)) throw Error("E_DOMAIN", "a spread input is negative", "spread_mean");
    double c = 0.0;
    for (std::size_t i = 0; i < P.size(); ++i) c += std::fabs(P[i]) * (mu[i] + z * sg[i]);
    c /= 2;
    out.key_real("liquidity_cost", c);
    out.key_real("lvar", var + c);
}

void op_vol_horizon(const In& in, Out& out) {
    const double s = in.real("daily_vol"), rho = in.real("ar1");
    const long long h = in.integer("horizon_days");
    in.ready();
    sr_positive(s, "daily_vol");
    if (!(std::fabs(rho) < 1)) throw Error("E_DOMAIN", "|ar1| must be below 1", "ar1");
    if (h < 1) throw Error("E_DOMAIN", "horizon_days is below 1", "horizon_days");
    limit_if(h > 100000, "horizon_days");
    const double dh = static_cast<double>(h);
    double sum = 0.0, pw = 1.0;
    for (long long k = 1; k < h; ++k) {
        pw *= rho;
        sum += static_cast<double>(h - k) * pw;
    }
    const double ratio = (dh + 2 * sum) / dh;
    out.key_real("vol", s * std::sqrt(dh * ratio));
    out.key_real("sqrt_rule_vol", s * std::sqrt(dh));
    out.key_real("variance_ratio", ratio);
}

constexpr Entry risk_gb_ops[] = {
    {"risk.sens.inflation01", op_sens_inflation01},
    {"risk.sens.dividend_borrow", op_sens_dividend_borrow},
    {"risk.sens.correlation", op_sens_correlation},
    {"risk.stress.reverse", op_stress_reverse},
    {"risk.limits.check", op_limits_check},
    {"risk.concentration.measures", op_concentration},
    {"risk.var.liquidity_adjusted", op_var_liquidity},
    {"risk.vol.horizon", op_vol_horizon},
};
