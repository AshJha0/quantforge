// CLI handlers, stage G wave 4b: xVA on given paths (06-risk/xva-framework.md, rulings G-40 to G-44).
// Included by dispatch.cpp inside its unnamed namespace; formulas on given inputs, so the maths lives here.

Vec xva_increasing(const In& in, const char* key, std::size_t min_size) {
    const Vec t = sr_reals(in, key);
    limit_if(t.size() > 10000, key);
    if (t.size() < min_size) throw Error("E_INPUT", string(key) + " is too short", key);
    for (std::size_t i = 1; i < t.size(); ++i)
        if (!(t[i] > t[i - 1])) throw Error("E_INPUT", string(key) + " must increase", key);
    return t;
}

std::vector<Vec> xva_paths(const Value& v, const char* key, std::size_t len) {
    if (v.kind != Kind::Array) schema(key, "expected an array of paths");
    limit_if(v.items.size() > 10000000, key);
    std::vector<Vec> paths;
    for (const Value& p : v.items) {
        Vec x = sr_finite(to_reals(p, key), key);
        if (x.size() != len) throw Error("E_INPUT", "a path length differs from times", key);
        paths.push_back(std::move(x));
    }
    if (paths.empty()) throw Error("E_INPUT", "no paths", key);
    return paths;
}

struct XvaCsa {
    double hr, hp, mta, ia;
    long long lag;
};

void op_xva_collateralised(const In& in, Out& out) {
    const Vec t = xva_increasing(in, "times", 2);
    const Value& tv = in.need("trades");
    if (tv.kind != Kind::Array) schema("trades", "expected an array");
    if (tv.items.empty()) throw Error("E_INPUT", "no trades", "trades");
    std::map<string, std::vector<Vec>> sets;  // code-point order of names
    for (const Value& tr : tv.items) {
        if (tr.kind != Kind::Object) schema("trades", "expected an object");
        const In q(tr);
        const string name = q.text("netting_set");
        const std::vector<Vec> paths = xva_paths(q.need("values"), "values", t.size());
        q.ready();
        auto& acc = sets[name];
        if (acc.empty()) acc.assign(paths.size(), Vec(t.size(), 0.0));
        if (acc.size() != paths.size()) throw Error("E_INPUT", "trades of a set have different path counts", "values");
        for (std::size_t p = 0; p < paths.size(); ++p)
            for (std::size_t i = 0; i < t.size(); ++i) acc[p][i] += paths[p][i];
    }
    std::map<string, XvaCsa> csa;
    if (const Value* cv = in.find("csa")) {
        if (cv->kind != Kind::Object) schema("csa", "expected an object");
        for (const auto& m : cv->members) {
            if (m.second.kind != Kind::Object) schema("csa", "expected an object");
            const In c(m.second);
            XvaCsa x{c.real("threshold_receive"), c.real("threshold_post"), c.real("minimum_transfer_amount"),
                     c.real("independent_amount", 0.0), c.integer("mpor_steps")};
            c.ready();
            if (!(x.hr >= 0) || !(x.hp >= 0) || !(x.mta >= 0)) throw Error("E_DOMAIN", "a threshold or MTA is negative", "csa");
            if (x.lag < 0) throw Error("E_DOMAIN", "mpor_steps is negative", "csa");
            if (!sets.count(m.first)) throw Error("E_INPUT", "a CSA names a netting set with no trades", "csa");
            csa[m.first] = x;
        }
    }
    const double q = in.real("pfe_quantile");
    in.ready();
    if (!(q > 0 && q <= 1)) throw Error("E_DOMAIN", "pfe_quantile must lie in (0, 1]", "pfe_quantile");
    const std::size_t n = t.size();
    Vec total(n, 0.0);
    out.values.key("netting_sets");
    out.values.begin_object();
    for (const auto& [name, paths] : sets) {
        const std::size_t P = paths.size();
        Vec ee(n, 0.0), ene(n, 0.0), pfe(n, 0.0);
        std::vector<Vec> E(n, Vec(P));
        for (std::size_t p = 0; p < P; ++p) {
            const Vec& V = paths[p];
            Vec C(n, 0.0);
            if (auto it = csa.find(name); it != csa.end()) {
                const XvaCsa& c = it->second;
                const auto target = [&](double v) { return std::max(v - c.hr, 0.0) - std::max(-v - c.hp, 0.0) + c.ia; };
                Vec K(n);
                K[0] = target(V[0]);
                for (std::size_t j = 1; j < n; ++j) {
                    const double tj = target(V[j]);
                    K[j] = std::fabs(tj - K[j - 1]) >= c.mta ? tj : K[j - 1];
                }
                for (std::size_t i = 0; i < n; ++i) {
                    const long long src = std::max(static_cast<long long>(i) - c.lag, 0LL);
                    C[i] = K[static_cast<std::size_t>(src)];
                }
            }
            for (std::size_t i = 0; i < n; ++i) {
                const double x = V[i] - C[i];
                E[i][p] = std::max(x, 0.0);
                ee[i] += std::max(x, 0.0);
                ene[i] += std::min(x, 0.0);
            }
        }
        const std::size_t rank = static_cast<std::size_t>(std::ceil(q * static_cast<double>(P)));
        for (std::size_t i = 0; i < n; ++i) {
            ee[i] /= static_cast<double>(P);
            ene[i] /= static_cast<double>(P);
            std::sort(E[i].begin(), E[i].end());
            pfe[i] = E[i][std::clamp<std::size_t>(rank, 1, P) - 1];
            total[i] += ee[i];
        }
        double epe = 0.0, eepe = 0.0, eee = ee[0], horizon = 0.0;
        for (std::size_t i = 1; i < n; ++i) {
            epe += ee[i] * (t[i] - t[i - 1]);
            eee = std::max(eee, ee[i]);
            if (t[i] - t[0] <= 1.0) {
                eepe += eee * (t[i] - t[i - 1]);
                horizon = t[i] - t[0];
            }
        }
        out.values.key(name);
        out.values.begin_object();
        out.key_reals("ee", ee);
        out.key_reals("ene", ene);
        out.key_reals("pfe", pfe);
        out.key_real("epe", epe / (t[n - 1] - t[0]));
        out.key_real("effective_epe", horizon > 0 ? eepe / horizon : ee[0]);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_reals("total_ee", total);
}

struct XvaName {
    double h, R;
};
XvaName xva_name(const In& in, const char* key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In c(v);
    XvaName x{c.real("hazard_rate"), c.real("recovery")};
    c.ready();
    if (!(x.h >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", key);
    if (!(x.R >= 0 && x.R < 1)) throw Error("E_DOMAIN", "recovery must lie in [0, 1)", key);
    return x;
}

void op_xva_adjustments(const In& in, Out& out) {
    const Vec t = xva_increasing(in, "times", 1);
    if (!(t[0] > 0)) throw Error("E_DOMAIN", "times must be after 0", "times");
    const Vec D = sr_reals(in, "discount_factors"), ee = sr_reals(in, "ee"), ene = sr_reals(in, "ene");
    const std::size_t n = t.size();
    if (D.size() != n || ee.size() != n || ene.size() != n) throw Error("E_INPUT", "lengths differ from times", "ee");
    const bool has_im = in.find("im") != nullptr, has_ims = in.find("im_spread") != nullptr;
    const bool has_k = in.find("capital") != nullptr, has_h = in.find("hurdle_rate") != nullptr;
    if (has_im != has_ims) throw Error("E_INPUT", "im and im_spread come together", "im_spread");
    if (has_k != has_h) throw Error("E_INPUT", "capital and hurdle_rate come together", "hurdle_rate");
    const Vec im = has_im ? sr_reals(in, "im") : Vec{}, cap = has_k ? sr_reals(in, "capital") : Vec{};
    if ((has_im && im.size() != n) || (has_k && cap.size() != n)) throw Error("E_INPUT", "lengths differ from times", "im");
    for (std::size_t i = 0; i < n; ++i) {
        if (!(ee[i] >= 0)) throw Error("E_DOMAIN", "ee is negative", "ee");
        if (!(ene[i] <= 0)) throw Error("E_DOMAIN", "ene is positive", "ene");
    }
    const XvaName c = xva_name(in, "counterparty"), b = xva_name(in, "own");
    const Value& fv = in.need("funding");
    if (fv.kind != Kind::Object) schema("funding", "expected an object");
    const In f(fv);
    const double sb = f.real("borrow_spread"), sl0 = f.real("lend_spread");
    const bool excl = f.boolean("exclude_dva_overlap");
    f.ready();
    const double ims = has_ims ? in.real("im_spread") : 0.0, hurdle = has_h ? in.real("hurdle_rate") : 0.0;
    in.ready();
    const double sl = excl ? std::max(sl0 - b.h * (1 - b.R), 0.0) : sl0;
    double cva = 0, dva = 0, fca = 0, fba = 0, mva = 0, kva = 0, prev = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const double Sc0 = std::exp(-c.h * prev), Sc1 = std::exp(-c.h * t[i]);
        const double Sb0 = std::exp(-b.h * prev), Sb1 = std::exp(-b.h * t[i]);
        const double dt = t[i] - prev, w = D[i] * Sc0 * Sb0 * dt;
        cva += D[i] * ee[i] * (Sc0 - Sc1) * Sb0;
        dva += D[i] * std::fabs(ene[i]) * (Sb0 - Sb1) * Sc0;
        fca += w * ee[i];
        fba += w * std::fabs(ene[i]);
        if (has_im) mva += w * im[i];
        if (has_k) kva += w * cap[i];
        prev = t[i];
    }
    out.key_real("cva", (1 - c.R) * cva);
    out.key_real("dva", (1 - b.R) * dva);
    out.key_real("fca", sb * fca);
    out.key_real("fba", sl * fba);
    out.key_real("fva", sb * fca - sl * fba);
    if (has_im) out.key_real("mva", ims * mva);
    if (has_k) out.key_real("kva", hurdle * kva);
}

// `xva.sbim.ir_delta`; `xva.simm.ir_delta` is its deprecated alias in v1.0.0, removed in the first release after it (KR-152, KR-256) and maps to this same handler.
void op_xva_sbim(const In& in, Out& out) {
    const Vec s = sr_reals(in, "sensitivities"), rw = sr_reals(in, "risk_weights");
    const Value& cv = in.need("correlations");
    if (cv.kind != Kind::Array) schema("correlations", "expected an array");
    limit_if(s.size() > 10000, "sensitivities");
    std::vector<Vec> rho;
    for (const Value& r : cv.items) rho.push_back(to_reals(r, "correlations"));
    const double T = in.real("concentration_threshold");
    in.ready();
    const xva::SbimIrDelta r = xva::sbim_ir_delta(s, rw, rho, T);
    out.key_reals("weighted_sensitivities", r.weighted_sensitivities);
    out.key_real("concentration_factor", r.concentration_factor);
    out.key_real("margin", r.margin);
}

// KR-257: hazard exp(z) over dt gives default probability q = 1 - e^-x, survival r = e^-x and dq/dz = x e^-x
// with x = exp(z) dt; an overflowing exp(z) is inf (q = 1, r = 0).
struct WwrTerms {
    double q, r, dq;
};
WwrTerms wwr_terms(double z, double dt) {
    const double x = (z > 709.0 ? std::numeric_limits<double>::infinity() : std::exp(z)) * dt;
    const double r = std::exp(-x);
    return {-std::expm1(-x), r, r == 0.0 ? 0.0 : x * r};
}

// KR-257: a with sum_p S_p (1 - e^(-x_p)) = (1 - e^(-h dt)) sum_p S_p, x_p = exp(a + c_p) dt (the G-44 equation divided
// through by S(t_(i-1)); above a bucket default probability of 1/2 the survival form sum_p S_p e^(-x_p) = e^(-h dt)
// sum_p S_p). Bracket [ln h - max c - 1, ln h - min c + 1] (closed form, sign change by monotonicity), safeguarded
// Newton (rtsafe) from ln h - (S-weighted mean of c), step to 1e-15 relative, at most 200 steps.
double wwr_root(const Vec& surv, const Vec& cs, double dt, double hz) {
    const double q_t = -std::expm1(-hz * dt), r_t = std::exp(-hz * dt);
    const bool use_q = q_t <= 0.5;
    double total = 0.0, wsum = 0.0;
    for (std::size_t p = 0; p < surv.size(); ++p) {
        total += surv[p];
        wsum += surv[p] * cs[p];
    }
    const auto fval = [&](double x, double& der) {
        double sq = 0.0, sr = 0.0, d = 0.0;
        for (std::size_t p = 0; p < surv.size(); ++p) {
            const WwrTerms w = wwr_terms(x + cs[p], dt);
            sq += surv[p] * w.q;
            sr += surv[p] * w.r;
            d += surv[p] * w.dq;
        }
        der = d;
        return use_q ? sq - q_t * total : r_t * total - sr;
    };
    const double ln_h = std::log(hz);
    double lo = ln_h - *std::max_element(cs.begin(), cs.end()) - 1.0, hi = ln_h - *std::min_element(cs.begin(), cs.end()) + 1.0;
    double x = ln_h - wsum / total, dx = hi - lo, der = 0.0;
    double val = fval(x, der);
    for (int it = 0; it < 200; ++it) {
        if (val > 0) hi = x;
        else if (val < 0) lo = x;
        else return x;
        const double dx_old = dx;
        dx = der > 0 ? val / der : std::numeric_limits<double>::infinity();
        double step = x - dx;
        if (!(lo < step && step < hi && std::fabs(dx) <= 0.5 * std::fabs(dx_old))) {
            dx = 0.5 * (hi - lo);
            step = lo + dx;
        }
        if (std::fabs(step - x) <= 1e-15 * std::max(1.0, std::fabs(x))) return step;
        x = step;
        val = fval(x, der);
    }
    throw Error("E_NO_CONVERGENCE", "the a(t) root did not converge in 200 steps", "wwr_b");
}

void op_xva_wwr(const In& in, Out& out) {
    const Vec t = xva_increasing(in, "times", 1);
    if (!(t[0] > 0)) throw Error("E_DOMAIN", "times must be after 0", "times");
    const std::vector<Vec> V = xva_paths(in.need("values"), "values", t.size());
    const Vec D = sr_reals(in, "discount_factors");
    const double h = in.real("hazard_rate"), R = in.real("recovery"), b = in.real("wwr_b");
    in.ready();
    if (D.size() != t.size()) throw Error("E_INPUT", "discount_factors length differs from times", "discount_factors");
    if (!(h > 0)) throw Error("E_DOMAIN", "hazard_rate is not positive", "hazard_rate");
    if (!(R >= 0 && R < 1)) throw Error("E_DOMAIN", "recovery must lie in [0, 1)", "recovery");
    for (const Vec& path : V)
        for (const double v : path)
            if (std::fabs(b * v) > 700.0) throw Error("E_DOMAIN", "|wwr_b * value| must be at most 700 (KR-257)", "wwr_b");
    const double min_normal = std::numeric_limits<double>::min();
    double prev = 0.0;
    for (const double ti : t) {
        if (std::exp(-h * ti) < min_normal || -std::expm1(-h * (ti - prev)) < min_normal)
            throw Error("E_NON_FINITE", "the survival target or a bucket default probability is below the smallest normal double",
                        "hazard_rate");
        prev = ti;
    }
    const std::size_t P = V.size(), n = t.size();
    const double Pn = static_cast<double>(P);
    Vec S(P, 1.0), cs(P), a(n);
    double cva = 0.0;
    prev = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double dt = t[i] - prev;
        for (std::size_t p = 0; p < P; ++p) cs[p] = b * V[p][i];
        a[i] = wwr_root(S, cs, dt, h);
        double acc = 0.0;
        for (std::size_t p = 0; p < P; ++p) {
            const WwrTerms w = wwr_terms(a[i] + cs[p], dt);
            acc += std::max(V[p][i], 0.0) * S[p] * w.q;
            S[p] *= w.r;
        }
        cva += D[i] * acc / Pn;
        prev = t[i];
    }
    out.key_real("cva", (1 - R) * cva);
    out.key_reals("a", a);
}

constexpr Entry xva_ops[] = {
    {"xva.exposure.collateralised", op_xva_collateralised},
    {"xva.adjustments.value", op_xva_adjustments},
    {"xva.sbim.ir_delta", op_xva_sbim},
    {"xva.simm.ir_delta", op_xva_sbim},  // deprecated alias (KR-152)
    {"xva.wwr.cva_hw", op_xva_wwr},
};

// Q9 part 2 statistic (06-risk/model-reserve.md, ruling G-36).
void op_model_reserve(const In& in, Out& out) {
    const Value& pv = in.need("prices");
    if (pv.kind != Kind::Object) schema("prices", "expected an object");
    std::map<string, double> prices;  // code-point order
    for (const auto& m : pv.members) prices[m.first] = to_real(m.second, "prices");
    const string ref = in.text("reference_model");
    in.ready();
    if (prices.size() < 2) throw Error("E_INPUT", "prices needs at least two models", "prices");
    if (!prices.count(ref)) throw Error("E_INPUT", "reference_model is not a key of prices", "reference_model");
    const double pref = prices[ref];
    double sum = 0.0, comp = 0.0, lo = INFINITY, hi = -INFINITY, reserve = -1.0;
    string worst;
    for (const auto& [name, p] : prices) {
        const double t = sum + p;  // Neumaier sum
        comp += std::fabs(sum) >= std::fabs(p) ? (sum - t) + p : (p - t) + sum;
        sum = t;
        lo = std::min(lo, p);
        hi = std::max(hi, p);
        const double d = std::fabs(p - pref);
        if (d > reserve) reserve = d, worst = name;
    }
    const double range = hi - lo;
    out.key_real("mean", (sum + comp) / static_cast<double>(prices.size()));
    out.key_real("range", range);
    out.key_real("half_range", range / 2);
    out.key_real("reserve", reserve);
    out.key_string("worst_model", worst);
    out.key_maybe("relative_reserve", pref == 0.0 ? std::nullopt : std::optional<double>(reserve / std::fabs(pref)));
}

constexpr Entry reserve_ops[] = {
    {"risk.model_reserve.dispersion", op_model_reserve},
};
