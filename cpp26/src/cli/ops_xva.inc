// CLI handlers, stage G wave 4b: xVA on given paths (06-risk/xva-framework.md, rulings G-40 to G-44).
// Included by dispatch.cpp inside its unnamed namespace; formulas on given inputs, so the maths lives here.

// Error order HR-122 (KR-230; the KR-258 sweep found C++ out of step): every handler here first reads all of its
// inputs (E_SCHEMA), then size limits and the finite rule, then structural E_INPUT, then E_DOMAIN.

// Structural check of a time grid: at least `min_size` points, strictly increasing.
void xva_grid(const Vec& t, const char* key, std::size_t min_size) {
    if (t.size() < min_size) throw Error("E_INPUT", string(key) + " is too short", key);
    for (std::size_t i = 1; i < t.size(); ++i)
        if (!(t[i] > t[i - 1])) throw Error("E_INPUT", string(key) + " must increase", key);
}

// Read phase: a list of paths, each a list of numbers (E_SCHEMA and the path-count limit only).
std::vector<Vec> xva_read_paths(const Value& v, const char* key) {
    if (v.kind != Kind::Array) schema(key, "expected an array of paths");
    limit_if(v.items.size() > 10000000, key);
    std::vector<Vec> paths;
    paths.reserve(v.items.size());
    for (const Value& p : v.items) paths.push_back(to_reals(p, key));
    return paths;
}

void xva_finite_paths(const std::vector<Vec>& paths, const char* key) {
    for (const Vec& x : paths) static_cast<void>(sr_finite(x, key));
}

// Structural phase: every path has the grid's length, and there is at least one path.
void xva_check_paths(const std::vector<Vec>& paths, const char* key, std::size_t len) {
    for (const Vec& x : paths)
        if (x.size() != len) throw Error("E_INPUT", "a path length differs from times", key);
    if (paths.empty()) throw Error("E_INPUT", "no paths", key);
}

struct XvaCsa {
    double hr, hp, mta, ia;
    long long lag;
};

void op_xva_collateralised(const In& in, Out& out) {
    // Read phase (E_SCHEMA).
    const Vec t = in.reals("times");
    limit_if(t.size() > 10000, "times");
    const Value& tv = in.need("trades");
    if (tv.kind != Kind::Array) schema("trades", "expected an array");
    std::vector<std::pair<string, std::vector<Vec>>> trades;
    for (const Value& tr : tv.items) {
        if (tr.kind != Kind::Object) schema("trades", "expected an object");
        const In q(tr);
        string name = q.text("netting_set");
        std::vector<Vec> paths = xva_read_paths(q.need("values"), "values");
        q.ready();
        trades.emplace_back(std::move(name), std::move(paths));
    }
    std::vector<std::pair<string, XvaCsa>> csa_in;
    if (const Value* cv = in.find("csa")) {
        if (cv->kind != Kind::Object) schema("csa", "expected an object");
        for (const auto& m : cv->members) {
            if (m.second.kind != Kind::Object) schema("csa", "expected an object");
            const In c(m.second);
            XvaCsa x{c.real("threshold_receive"), c.real("threshold_post"), c.real("minimum_transfer_amount"),
                     c.real("independent_amount", 0.0), c.integer("mpor_steps")};
            c.ready();
            csa_in.emplace_back(m.first, x);
        }
    }
    const double q = in.real("pfe_quantile");
    in.ready();
    // Finite rule.
    static_cast<void>(sr_finite(t, "times"));
    for (const auto& tr : trades) xva_finite_paths(tr.second, "values");
    // Structural E_INPUT, then E_DOMAIN (per CSA in name order, as in the other builds).
    xva_grid(t, "times", 2);
    if (trades.empty()) throw Error("E_INPUT", "no trades", "trades");
    std::map<string, std::vector<Vec>> sets;  // code-point order of names
    for (const auto& [name, paths] : trades) {
        xva_check_paths(paths, "values", t.size());
        auto& acc = sets[name];
        if (acc.empty()) acc.assign(paths.size(), Vec(t.size(), 0.0));
        if (acc.size() != paths.size()) throw Error("E_INPUT", "trades of a set have different path counts", "values");
        for (std::size_t p = 0; p < paths.size(); ++p)
            for (std::size_t i = 0; i < t.size(); ++i) acc[p][i] += paths[p][i];
    }
    std::map<string, XvaCsa> csa;
    for (const auto& [name, x] : csa_in) {
        if (!(x.hr >= 0) || !(x.hp >= 0) || !(x.mta >= 0)) throw Error("E_DOMAIN", "a threshold or MTA is negative", "csa");
        if (x.lag < 0) throw Error("E_DOMAIN", "mpor_steps is negative", "csa");
        if (!sets.count(name)) throw Error("E_INPUT", "a CSA names a netting set with no trades", "csa");
        csa[name] = x;
    }
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
XvaName xva_read_name(const In& in, const char* key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In c(v);
    XvaName x{c.real("hazard_rate"), c.real("recovery")};
    c.ready();
    return x;
}
void xva_check_name(const XvaName& x, const char* key) {
    if (!(x.h >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", key);
    if (!(x.R >= 0 && x.R < 1)) throw Error("E_DOMAIN", "recovery must lie in [0, 1)", key);
}

void op_xva_adjustments(const In& in, Out& out) {
    // Read phase (E_SCHEMA).
    const Vec t = in.reals("times");
    limit_if(t.size() > 10000, "times");
    const Vec D = in.reals("discount_factors"), ee = in.reals("ee"), ene = in.reals("ene");
    const bool has_im = in.find("im") != nullptr, has_ims = in.find("im_spread") != nullptr;
    const bool has_k = in.find("capital") != nullptr, has_h = in.find("hurdle_rate") != nullptr;
    const Vec im = has_im ? in.reals("im") : Vec{}, cap = has_k ? in.reals("capital") : Vec{};
    const XvaName c = xva_read_name(in, "counterparty"), b = xva_read_name(in, "own");
    const Value& fv = in.need("funding");
    if (fv.kind != Kind::Object) schema("funding", "expected an object");
    const In f(fv);
    const double sb = f.real("borrow_spread"), sl0 = f.real("lend_spread");
    const bool excl = f.boolean("exclude_dva_overlap");
    f.ready();
    const double ims = has_ims ? in.real("im_spread") : 0.0, hurdle = has_h ? in.real("hurdle_rate") : 0.0;
    in.ready();
    // Finite rule.
    for (const Vec* v : {&t, &D, &ee, &ene, &im, &cap}) static_cast<void>(sr_finite(*v, "inputs"));
    // Structural E_INPUT.
    xva_grid(t, "times", 1);
    if (!(t[0] > 0)) throw Error("E_INPUT", "times must start after 0 (KR-258)", "times");
    const std::size_t n = t.size();
    if (D.size() != n || ee.size() != n || ene.size() != n) throw Error("E_INPUT", "lengths differ from times", "ee");
    if (has_im != has_ims) throw Error("E_INPUT", "im and im_spread come together", "im_spread");
    if (has_k != has_h) throw Error("E_INPUT", "capital and hurdle_rate come together", "hurdle_rate");
    if ((has_im && im.size() != n) || (has_k && cap.size() != n)) throw Error("E_INPUT", "lengths differ from times", "im");
    // E_DOMAIN.
    for (std::size_t i = 0; i < n; ++i) {
        if (!(ee[i] >= 0)) throw Error("E_DOMAIN", "ee is negative", "ee");
        if (!(ene[i] <= 0)) throw Error("E_DOMAIN", "ene is positive", "ene");
    }
    xva_check_name(c, "counterparty");
    xva_check_name(b, "own");
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

// `xva.sens.aad` (06-risk/xva-aad-adjustments.md, KR-262 to KR-267): every typed read first (E_SCHEMA), then the
// KR-266 limits, the finite rule, the wrt and G-41 structural checks, then the G-41 domain checks.
void op_xva_sens_aad(const In& in, Out& out) {
    if (in.text("operation") != "xva.adjustments.value")
        throw Error("E_SCHEMA", "operation is not supported", "operation");
    const Value& iv = in.need("inputs");
    if (iv.kind != Kind::Object) schema("inputs", "expected an object");
    const In x(iv);
    namespace xa = quantforge::xva_aad;
    xa::Request r;
    r.t = x.reals("times");
    r.df = x.reals("discount_factors");
    r.ee = x.reals("ee");
    r.ene = x.reals("ene");
    auto name = [&](const char* key, double& h, double& rec) {
        const Value& v = x.need(key);
        if (v.kind != Kind::Object) schema(key, "expected an object");
        const In c(v);
        h = c.real("hazard_rate");
        rec = c.real("recovery");
    };
    name("counterparty", r.hc, r.rc);
    name("own", r.hb, r.rb);
    const Value& fv = x.need("funding");
    if (fv.kind != Kind::Object) schema("funding", "expected an object");
    const In f(fv);
    r.sb = f.real("borrow_spread");
    r.sl = f.real("lend_spread");
    r.exclude_overlap = f.boolean("exclude_dva_overlap");
    const bool has_ims = x.find("im_spread") != nullptr, has_h = x.find("hurdle_rate") != nullptr;
    r.has_im = x.find("im") != nullptr;
    r.has_capital = x.find("capital") != nullptr;
    if (r.has_im) r.im = x.reals("im");
    if (has_ims) r.im_spread = x.real("im_spread");
    if (r.has_capital) r.capital = x.reals("capital");
    if (has_h) r.hurdle = x.real("hurdle_rate");
    std::optional<std::vector<string>> wrt;
    if (const Value* w = in.find("wrt")) {
        if (w->kind != Kind::Array) schema("wrt", "expected an array of strings");
        wrt.emplace();
        for (const Value& k : w->items) wrt->push_back(to_string(k, "wrt"));
    }
    for (const Vec* v : {&r.t, &r.df, &r.ee, &r.ene, &r.im, &r.capital}) limit_if(v->size() > 10000, "inputs");
    in.ready();
    const std::vector<string> names = xa::check_wrt(wrt, xa::keys(r.has_im, r.has_capital));
    const std::size_t n = r.t.size();
    if (n == 0) throw Error("E_INPUT", "times needs at least one time", "times");
    for (std::size_t i = 1; i < n; ++i)
        if (!(r.t[i] > r.t[i - 1])) throw Error("E_INPUT", "times must be increasing", "times");
    if (r.df.size() != n || r.ee.size() != n || r.ene.size() != n)
        throw Error("E_INPUT", "lengths differ from times", "ee");
    if (r.has_im != has_ims) throw Error("E_INPUT", "im and im_spread come together", "im_spread");
    if (r.has_capital != has_h) throw Error("E_INPUT", "capital and hurdle_rate come together", "hurdle_rate");
    if ((r.has_im && r.im.size() != n) || (r.has_capital && r.capital.size() != n))
        throw Error("E_INPUT", "lengths differ from times", "im");
    if (!(r.t[0] > 0)) throw Error("E_INPUT", "times must be after 0", "times");
    if (!(r.hc >= 0) || !(r.hb >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", "hazard_rate");
    if (!(r.rc >= 0 && r.rc < 1) || !(r.rb >= 0 && r.rb < 1))
        throw Error("E_DOMAIN", "recovery must lie in [0, 1)", "recovery");
    for (std::size_t i = 0; i < n; ++i) {
        if (!(r.ee[i] >= 0)) throw Error("E_DOMAIN", "ee is negative", "ee");
        if (!(r.ene[i] <= 0)) throw Error("E_DOMAIN", "ene is positive", "ene");
    }
    const double sl = r.exclude_overlap ? std::max(r.sl - r.hb * (1 - r.rb), 0.0) : r.sl;
    double cva = 0, dva = 0, fca = 0, fba = 0, mva = 0, kva = 0, prev = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const double Sc0 = std::exp(-r.hc * prev), Sc1 = std::exp(-r.hc * r.t[i]);
        const double Sb0 = std::exp(-r.hb * prev), Sb1 = std::exp(-r.hb * r.t[i]);
        const double dt = r.t[i] - prev, w = r.df[i] * Sc0 * Sb0 * dt;
        cva += r.df[i] * r.ee[i] * (Sc0 - Sc1) * Sb0;
        dva += r.df[i] * std::fabs(r.ene[i]) * (Sb0 - Sb1) * Sc0;
        fca += w * r.ee[i];
        fba += w * std::fabs(r.ene[i]);
        if (r.has_im) mva += w * r.im[i];
        if (r.has_capital) kva += w * r.capital[i];
        prev = r.t[i];
    }
    out.key_real("cva", (1 - r.rc) * cva);
    out.key_real("dva", (1 - r.rb) * dva);
    out.key_real("fca", r.sb * fca);
    out.key_real("fba", sl * fba);
    out.key_real("fva", r.sb * fca - sl * fba);
    if (r.has_im) out.key_real("mva", r.im_spread * mva);
    if (r.has_capital) out.key_real("kva", r.hurdle * kva);
    out.values.key("gradient");
    out.values.begin_object();
    for (const auto& [o, g] : xa::gradient(r, names)) {
        out.values.key(o);
        out.values.begin_object();
        for (const auto& e : g) {
            if (e.scalar) out.key_real(e.key, e.s);
            else out.key_reals(e.key, e.v);
        }
        out.values.end_object();
    }
    out.values.end_object();
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
    // Read phase (E_SCHEMA).
    const Vec t = in.reals("times");
    limit_if(t.size() > 10000, "times");
    const std::vector<Vec> V = xva_read_paths(in.need("values"), "values");
    const Vec D = in.reals("discount_factors");
    const double h = in.real("hazard_rate"), R = in.real("recovery"), b = in.real("wwr_b");
    in.ready();
    // Finite rule.
    static_cast<void>(sr_finite(t, "times"));
    xva_finite_paths(V, "values");
    static_cast<void>(sr_finite(D, "discount_factors"));
    // Structural E_INPUT, then E_DOMAIN.
    xva_grid(t, "times", 1);
    if (!(t[0] > 0)) throw Error("E_INPUT", "times must start after 0 (KR-258)", "times");
    xva_check_paths(V, "values", t.size());
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
    {"xva.sens.aad", op_xva_sens_aad},
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
