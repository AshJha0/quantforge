// CLI handlers, stage G G1: one-factor short-rate models (04-pricing/short-rate-models.md, rulings G-1 to G-6).
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.
// Stage G wave 1 first cut: the maths lives here until it moves to a core module.

enum class SrModel { Vasicek, Cir, HullWhite };

struct SrCurve {
    Vec t, lnp;  // nodes with (0, 0) first
    double ln_p(double x) const {
        const std::size_t n = t.size();
        if (x >= t[n - 1]) {
            const double f = (lnp[n - 2] - lnp[n - 1]) / (t[n - 1] - t[n - 2]);
            return lnp[n - 1] - f * (x - t[n - 1]);
        }
        std::size_t i = 1;
        while (t[i] <= x) ++i;  // t[i-1] <= x < t[i]
        const double w = (x - t[i - 1]) / (t[i] - t[i - 1]);
        return lnp[i - 1] + w * (lnp[i] - lnp[i - 1]);
    }
    double fwd(double x) const {  // right-hand instantaneous forward (G-3); flat beyond the last pillar
        const std::size_t n = t.size();
        std::size_t i = 1;
        while (i < n && t[i] <= x) ++i;
        if (i >= n) i = n - 1;
        return -(lnp[i] - lnp[i - 1]) / (t[i] - t[i - 1]);
    }
};

struct SrParams {
    SrModel model;
    double a, sigma, b = 0.0;
    SrCurve curve;
};

// B = (1 - e^{-a tau}) / a, and (B - tau) / a^2 with a series for small a tau (G-2).
double sr_b(double a, double tau) { return -std::expm1(-a * tau) / a; }
double sr_bm_tau_over_a2(double a, double tau) {
    const double x = a * tau;
    if (x < 1e-2) {
        // (B - tau)/a^2 = tau^3 sum_{k>=0} (-x)^k / (k+3)! * (-1)... : B - tau = sum_{k>=2} (-1)^{k+1} a^{k-1} tau^k / k!
        double term = -tau * tau / 2.0, sum = 0.0;  // k = 2 term of (B - tau)/a = -tau^2/2 ...
        for (int k = 2; k < 30; ++k) {
            sum += term;
            term *= -x / (k + 1);
        }
        return sum / a;  // (B - tau)/a^2 = [(B - tau)/a] / a
    }
    return (sr_b(a, tau) - tau) / (a * a);
}

// ln A and B for P(t, T) = A exp(-B r).
std::pair<double, double> sr_ab(const SrParams& p, double t, double T) {
    const double tau = T - t, a = p.a, s2 = p.sigma * p.sigma;
    if (p.model == SrModel::Vasicek) {
        const double B = sr_b(a, tau);
        return {sr_bm_tau_over_a2(a, tau) * (a * a * p.b - s2 / 2) - s2 * B * B / (4 * a), B};
    }
    if (p.model == SrModel::Cir) {
        const double g = std::sqrt(a * a + 2 * s2), em1 = std::expm1(g * tau);
        const double den = (g + a) * em1 + 2 * g;
        return {(2 * a * p.b / s2) * (std::log(2 * g / den) + (a + g) * tau / 2), 2 * em1 / den};
    }
    const double B = sr_b(a, tau);
    const double lnA = p.curve.ln_p(T) - p.curve.ln_p(t) + B * p.curve.fwd(t) -
                       s2 / (4 * a) * (-std::expm1(-2 * a * t)) * B * B;
    return {lnA, B};
}

// Regularised lower incomplete gamma P(s, x): series for x < s + 1, continued fraction otherwise.
double sr_gamma_p(double s, double x) {
    if (x <= 0) return 0.0;
    const double lead = s * std::log(x) - x - std::lgamma(s);
    if (x < s + 1) {
        double term = 1.0 / s, sum = term;
        for (int n = 1; n < 100000; ++n) {
            term *= x / (s + n);
            sum += term;
            if (term < sum * 1e-17) break;
        }
        return sum * std::exp(lead);
    }
    const double tiny = 1e-300;
    double bb = x + 1 - s, c = 1 / tiny, d = 1 / bb, h = d;
    for (int i = 1; i < 100000; ++i) {
        const double an = -i * (i - s);
        bb += 2;
        d = an * d + bb;
        if (std::fabs(d) < tiny) d = tiny;
        c = bb + an / c;
        if (std::fabs(c) < tiny) c = tiny;
        d = 1 / d;
        const double del = d * c;
        h *= del;
        if (std::fabs(del - 1) < 1e-17) break;
    }
    return 1.0 - std::exp(lead) * h;
}

// Noncentral chi-square CDF: Poisson(lambda/2) mixture of central chi-square CDFs, summed both ways from the mode.
double sr_ncx2_cdf(double x, double k, double lambda) {
    if (x <= 0) return 0.0;
    const double mu = lambda / 2;
    const long long mode = (long long)std::floor(mu);
    const auto weight = [&](long long j) { return std::exp(-mu + double(j) * std::log(std::max(mu, 1e-300)) - std::lgamma(double(j) + 1.0)); };
    const auto term = [&](long long j) { return (mu == 0 && j > 0) ? 0.0 : weight(j) * sr_gamma_p(k / 2 + double(j), x / 2); };
    double sum = term(mode);
    for (long long j = mode + 1; j < mode + 100000; ++j) {
        const double t = term(j);
        sum += t;
        if (t < 1e-17 * sum) break;
    }
    for (long long j = mode - 1; j >= 0; --j) {
        const double t = term(j);
        sum += t;
        if (t < 1e-17 * sum) break;
    }
    return sum;
}

// An enum whose unknown value is E_INPUT (spec errors list), not E_SCHEMA.
template <class T>
T sr_enum(const In& in, string_view k, std::initializer_list<std::pair<const char*, T>> table) {
    const Value& v = in.need(k);
    if (v.kind != Kind::String) schema(k, "expected a string");
    for (const auto& [name, val] : table)
        if (v.text == name) return val;
    throw Error("E_INPUT", "unknown value", string(k));
}

SrParams sr_params(const In& in, std::optional<double>& short_rate, bool option) {
    SrParams p{};
    p.model = sr_enum<SrModel>(in, "model", {{"VASICEK", SrModel::Vasicek}, {"CIR", SrModel::Cir}, {"HULL_WHITE", SrModel::HullWhite}});
    p.a = in.real("mean_reversion");
    p.sigma = in.real("sigma");
    if (!(p.a > 0)) throw Error("E_DOMAIN", "mean_reversion is not positive", "mean_reversion");
    if (!(p.sigma > 0)) throw Error("E_DOMAIN", "sigma is not positive", "sigma");
    const bool hw = p.model == SrModel::HullWhite;
    if (!hw) {
        p.b = in.real("long_term_mean");
        if (p.model == SrModel::Cir && !(p.b > 0)) throw Error("E_DOMAIN", "long_term_mean is not positive", "long_term_mean");
    }
    const bool has_r = in.find("short_rate") != nullptr;
    if (hw && option && has_r) throw Error("E_INPUT", "short_rate is not allowed for HULL_WHITE options", "short_rate");
    if (!(hw && option)) {
        short_rate = in.real("short_rate");
        if (p.model == SrModel::Cir && !(*short_rate >= 0)) throw Error("E_DOMAIN", "short_rate is negative", "short_rate");
    }
    if (hw) {
        const Value& cv = in.need("curve");
        if (cv.kind != Kind::Object) schema("curve", "expected an object");
        const In c(cv);
        const Vec times = c.reals("times"), dfs = c.reals("discount_factors");
        c.ready();
        limit_if(times.size() > 10000, "curve");
        if (times.empty() || times.size() != dfs.size()) throw Error("E_INPUT", "curve needs matching times and discount factors", "curve");
        for (std::size_t i = 0; i < times.size(); ++i) {
            if (!(times[i] > (i ? times[i - 1] : 0.0))) throw Error("E_INPUT", "curve times must increase from above 0", "curve");
            if (!(dfs[i] > 0)) throw Error("E_DOMAIN", "curve discount factor is not positive", "curve");
        }
        p.curve.t.push_back(0.0);
        p.curve.lnp.push_back(0.0);
        for (std::size_t i = 0; i < times.size(); ++i) p.curve.t.push_back(times[i]), p.curve.lnp.push_back(std::log(dfs[i]));
    }
    return p;
}

void op_sr_zcb(const In& in, Out& out) {
    std::optional<double> r;
    const SrParams p = sr_params(in, r, false);
    const double t = in.real("t_years"), T = in.real("maturity_years");
    in.ready();
    if (!(t >= 0)) throw Error("E_DOMAIN", "t_years is negative", "t_years");
    if (!(T > t)) throw Error("E_DOMAIN", "maturity_years is not after t_years", "maturity_years");
    const auto [lnA, B] = sr_ab(p, t, T);
    const double lnP = lnA - B * *r;
    out.key_real("discount_factor", std::exp(lnP));
    out.key_real("zero_rate", -lnP / (T - t));
}

void op_sr_zcb_option(const In& in, Out& out) {
    std::optional<double> r;
    const SrParams p = sr_params(in, r, true);
    const double T = in.real("expiry_years"), S = in.real("maturity_years"), K = in.real("strike");
    const double notional = in.real("notional");
    const bool call = sr_enum<bool>(in, "option_type", {{"CALL", true}, {"PUT", false}});
    in.ready();
    if (!(T > 0)) throw Error("E_DOMAIN", "expiry_years is not positive", "expiry_years");
    if (!(S > T)) throw Error("E_DOMAIN", "maturity_years is not after expiry_years", "maturity_years");
    if (!(K > 0)) throw Error("E_DOMAIN", "strike is not positive", "strike");
    const auto bond0 = [&](double x) {
        if (p.model == SrModel::HullWhite) return std::exp(p.curve.ln_p(x));
        const auto [lnA, B] = sr_ab(p, 0.0, x);
        return std::exp(lnA - B * *r);
    };
    const double pt = bond0(T), ps = bond0(S);
    double c;
    if (p.model == SrModel::Cir) {
        const double a = p.a, s2 = p.sigma * p.sigma, g = std::sqrt(a * a + 2 * s2);
        const double rho = 2 * g / (s2 * std::expm1(g * T)), psi = (a + g) / s2;
        const auto [lnA, B] = sr_ab(p, T, S);
        const double rbar = (lnA - std::log(K)) / B, k = 4 * a * p.b / s2;
        const double ee = 2 * rho * rho * *r * std::exp(g * T);
        c = ps * sr_ncx2_cdf(2 * rbar * (rho + psi + B), k, ee / (rho + psi + B)) -
            K * pt * sr_ncx2_cdf(2 * rbar * (rho + psi), k, ee / (rho + psi));
    } else {
        const double a = p.a;
        const double sp = p.sigma * sr_b(a, S - T) * std::sqrt(-std::expm1(-2 * a * T) / (2 * a));
        const double h = std::log(ps / (K * pt)) / sp + sp / 2;
        c = ps * normal_cdf(h) - K * pt * normal_cdf(h - sp);
    }
    const double price = call ? c : c - ps + K * pt;
    out.key_real("price", notional * price);
    out.key_real("bond_price_expiry", pt);
    out.key_real("bond_price_maturity", ps);
}

constexpr Entry shortrate_ops[] = {
    {"rates.shortrate.zcb", op_sr_zcb},
    {"rates.shortrate.zcb_option", op_sr_zcb_option},
};
