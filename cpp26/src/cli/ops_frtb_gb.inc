// CLI handlers, FRTB SA carry-over landed in stage G: FX, equity, CSR and commodity delta (06-risk/frtb-sa-fx-equity.md,
// G-48, G-49) and vega and curvature (06-risk/frtb-sa-vega-curvature.md, G-51). MAR21.4 aggregation and MAR21.6
// scenarios as risk.frtb.girr_delta. Included by dispatch.cpp inside its unnamed namespace.

struct SbmFactor {
    long long bucket_num = 0;  // numeric bucket (0 when the bucket is a string)
    string bucket;             // display and string key
    string name, kind, tenor, curve, location;
    double t = 0.0, u = 0.0;  // option and underlying maturity (vega)
    double ws = 0.0;          // weighted sensitivity (delta, vega) or unused (curvature)
    double up = 0.0, down = 0.0;
};

double sbm_scenario(double x, int sc) {  // 0 high, 1 medium, 2 low
    if (sc == 0) return std::min(1.25 * x, 1.0);
    if (sc == 2) return std::max(2 * x - 1, 0.75 * x);
    return x;
}

struct SbmClass {
    std::function<double(const SbmFactor&, const SbmFactor&)> rho;  // within a bucket, medium, k != l
    std::function<double(const SbmFactor&, const SbmFactor&)> gamma;  // across buckets, medium
    std::function<bool(const SbmFactor&)> other;                      // other-sector bucket: simple sum
    std::function<string(const SbmFactor&)> factor_id;                // risk factor for other-sector netting
};

// Buckets in numeric order when numeric, else code-point order.
std::vector<std::vector<std::size_t>> sbm_buckets(const std::vector<SbmFactor>& f) {
    std::vector<std::size_t> idx(f.size());
    for (std::size_t i = 0; i < f.size(); ++i) idx[i] = i;
    std::stable_sort(idx.begin(), idx.end(), [&](std::size_t a, std::size_t b) {
        if (f[a].bucket_num != f[b].bucket_num) return f[a].bucket_num < f[b].bucket_num;
        return f[a].bucket < f[b].bucket;
    });
    std::vector<std::vector<std::size_t>> out;
    for (std::size_t i : idx) {
        if (out.empty() || f[out.back().front()].bucket != f[i].bucket) out.emplace_back();
        out.back().push_back(i);
    }
    return out;
}

constexpr std::string_view sbm_names[] = {"high", "medium", "low"};

// Delta and vega: MAR21.4 with the alternative S_b, three scenarios.
void sbm_linear(const std::vector<SbmFactor>& f, const SbmClass& cls, const char* measure, Out& out) {
    const auto buckets = sbm_buckets(f);
    double best = -1.0;
    int bind = 0;
    out.values.key("scenarios");
    out.values.begin_object();
    for (int sc = 0; sc < 3; ++sc) {
        struct B {
            string name;
            double k, s, s_used;
        };
        std::vector<B> bs;
        for (const auto& idx : buckets) {
            double s = 0.0, sum = 0.0;
            for (std::size_t k : idx) s += f[k].ws;
            if (cls.other(f[idx.front()])) {
                std::map<string, double> net;
                for (std::size_t k : idx) net[cls.factor_id(f[k])] += f[k].ws;
                double K = 0.0;
                for (const auto& [id, v] : net) K += std::fabs(v);
                bs.push_back({f[idx.front()].bucket, K, s, s});
                continue;
            }
            for (std::size_t k : idx)
                for (std::size_t l : idx)
                    sum += k == l ? f[k].ws * f[k].ws : sbm_scenario(cls.rho(f[k], f[l]), sc) * f[k].ws * f[l].ws;
            bs.push_back({f[idx.front()].bucket, std::sqrt(std::max(0.0, sum)), s, s});
        }
        const auto total = [&](bool alt) {
            double t = 0.0;
            for (std::size_t b = 0; b < bs.size(); ++b) {
                t += bs[b].k * bs[b].k;
                for (std::size_t c = 0; c < bs.size(); ++c)
                    if (b != c) {
                        const double g = sbm_scenario(cls.gamma(f[buckets[b].front()], f[buckets[c].front()]), sc);
                        t += g * (alt ? bs[b].s_used * bs[c].s_used : bs[b].s * bs[c].s);
                    }
            }
            return t;
        };
        double t = total(false);
        bool alt = false;
        if (t < 0.0) {
            alt = true;
            for (auto& b : bs) b.s_used = std::max(std::min(b.s, b.k), -b.k);
            t = total(true);
        }
        const double v = std::sqrt(std::max(0.0, t));
        if (v > best) best = v, bind = sc;
        out.values.key(sbm_names[sc]);
        out.values.begin_object();
        out.values.key("buckets");
        out.values.begin_array();
        for (const B& b : bs) {
            out.values.begin_object();
            out.key_string("bucket", b.name);
            out.key_real("k", b.k);
            out.key_real("s", b.s);
            out.key_real("s_used", b.s_used);
            out.values.end_object();
        }
        out.values.end_array();
        out.key_real(measure, v);
        out.values.key("alternative_used");
        out.values.boolean(alt);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_real("capital", best);
    out.key_string("binding_scenario", sbm_names[bind]);
}

double sbm_psi(double x, double y) { return (x < 0 && y < 0) ? 0.0 : 1.0; }

// Curvature, MAR21.5(3) and (4): rho and gamma are squared delta correlations, scenarios applied to the squares.
void sbm_curvature(const std::vector<SbmFactor>& f, const SbmClass& cls, Out& out) {
    const auto buckets = sbm_buckets(f);
    double best = -1.0;
    int bind = 0;
    out.values.key("scenarios");
    out.values.begin_object();
    for (int sc = 0; sc < 3; ++sc) {
        struct B {
            string name;
            double k, s;
            bool up;
        };
        std::vector<B> bs;
        for (const auto& idx : buckets) {
            double sp = 0.0, sm = 0.0, kp, km;
            for (std::size_t k : idx) sp += f[k].up, sm += f[k].down;
            if (cls.other(f[idx.front()])) {
                kp = km = 0.0;
                for (std::size_t k : idx) kp += std::max(f[k].up, 0.0), km += std::max(f[k].down, 0.0);
            } else {
                const auto kk = [&](bool upward) {
                    double sum = 0.0;
                    for (std::size_t k : idx) {
                        const double a = upward ? f[k].up : f[k].down;
                        sum += std::max(a, 0.0) * std::max(a, 0.0);
                        for (std::size_t l : idx)
                            if (k != l) {
                                const double b = upward ? f[l].up : f[l].down;
                                const double r = cls.rho(f[k], f[l]);
                                sum += sbm_scenario(r * r, sc) * a * b * sbm_psi(a, b);
                            }
                    }
                    return std::sqrt(std::max(0.0, sum));
                };
                kp = kk(true);
                km = kk(false);
            }
            const bool up = kp > km || (kp == km && sp > sm);
            bs.push_back({f[idx.front()].bucket, std::max(kp, km), up ? sp : sm, up});
        }
        double t = 0.0;
        for (std::size_t b = 0; b < bs.size(); ++b) {
            t += bs[b].k * bs[b].k;
            for (std::size_t c = 0; c < bs.size(); ++c)
                if (b != c) {
                    const double g = cls.gamma(f[buckets[b].front()], f[buckets[c].front()]);
                    t += sbm_scenario(g * g, sc) * bs[b].s * bs[c].s * sbm_psi(bs[b].s, bs[c].s);
                }
        }
        const double v = std::sqrt(std::max(0.0, t));
        if (v > best) best = v, bind = sc;
        out.values.key(sbm_names[sc]);
        out.values.begin_object();
        out.values.key("buckets");
        out.values.begin_array();
        for (const B& b : bs) {
            out.values.begin_object();
            out.key_string("bucket", b.name);
            out.key_real("k", b.k);
            out.key_real("s", b.s);
            out.key_string("selected", b.up ? "UP" : "DOWN");
            out.values.end_object();
        }
        out.values.end_array();
        out.key_real("curvature", v);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_real("capital", best);
    out.key_string("binding_scenario", sbm_names[bind]);
}

// ---- class definitions (MAR21) ----

double eq_rw(long long b) {
    constexpr double w[] = {0, 0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70, 0.15, 0.25};
    return w[b];
}
double eq_name_rho(long long b) {  // MAR21.78, different issuers, same kind
    if (b <= 4) return 0.15;
    if (b <= 8) return 0.25;
    if (b == 9) return 0.075;
    if (b == 10) return 0.125;
    return 0.80;  // 12, 13
}
double eq_gamma(long long b, long long c) {  // MAR21.80
    if (b == 11 || c == 11) return 0.0;
    if (b <= 10 && c <= 10) return 0.15;
    if ((b == 12 && c == 13) || (b == 13 && c == 12)) return 0.75;
    return 0.45;
}
double csr_rw(long long b) {
    constexpr double w[] = {0, 0.5, 1.0, 5.0, 3.0, 3.0, 2.0, 1.5, 2.5, 2.0, 4.0, 12.0, 7.0, 8.5, 5.5, 5.0, 12.0, 1.5, 5.0};
    return w[b] / 100;
}
double csr_name_rho(long long b) { return (b == 17 || b == 18) ? 0.80 : 0.35; }
double csr_gamma(long long b, long long c) {  // MAR21.57
    if (b == c) return 1.0;
    const auto sector = [](long long x) -> int {
        if (x <= 8) return static_cast<int>(x - 1);       // 0..7
        if (x <= 15) return static_cast<int>(x - 9);      // 0..6
        return static_cast<int>(x - 16 + 8);              // 16 -> 8, 17 -> 9, 18 -> 10
    };
    constexpr double t5[11][11] = {
        {100, 75, 10, 20, 25, 20, 15, 10, 0, 45, 45}, {75, 100, 5, 15, 20, 15, 10, 10, 0, 45, 45},
        {10, 5, 100, 5, 15, 20, 5, 20, 0, 45, 45},    {20, 15, 5, 100, 20, 25, 5, 5, 0, 45, 45},
        {25, 20, 15, 20, 100, 25, 5, 15, 0, 45, 45},  {20, 15, 20, 25, 25, 100, 5, 20, 0, 45, 45},
        {15, 10, 5, 5, 5, 5, 100, 5, 0, 45, 45},      {10, 10, 20, 5, 15, 20, 5, 100, 0, 45, 45},
        {0, 0, 0, 0, 0, 0, 0, 0, 100, 0, 0},          {45, 45, 45, 45, 45, 45, 45, 45, 0, 100, 75},
        {45, 45, 45, 45, 45, 45, 45, 45, 0, 75, 100}};
    const double sector_g = t5[sector(b)][sector(c)] / 100;
    const bool both = b <= 15 && c <= 15;
    const bool mixed = both && ((b <= 8) != (c <= 8));
    return (mixed ? 0.5 : 1.0) * sector_g;
}
double cmd_rw(long long b) {
    constexpr double w[] = {0, 30, 35, 60, 80, 40, 45, 20, 35, 25, 35, 50};
    return w[b] / 100;
}
double cmd_name_rho(long long b) {
    constexpr double w[] = {0, 55, 95, 40, 80, 60, 65, 55, 45, 15, 40, 15};
    return w[b] / 100;
}
double cmd_gamma(long long b, long long c) { return (b == 11 || c == 11) ? 0.0 : 0.20; }

long long sbm_bucket_num(const In& r, long long lo, long long hi) {
    const long long b = r.integer("bucket");
    if (b < lo || b > hi) throw Error("E_INPUT", "unknown bucket", "bucket");
    return b;
}

const Value& sbm_list(const In& in, const char* key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Array) schema(key, "expected an array");
    limit_if(v.items.size() > 10000, key);
    if (v.items.empty()) throw Error("E_INPUT", string(key) + " is empty", key);
    return v;
}

void sbm_unique(const std::vector<SbmFactor>& f, const std::function<string(const SbmFactor&)>& id) {
    std::set<string> seen;
    for (const auto& x : f)
        if (!seen.insert(x.bucket + "\x1f" + id(x)).second) throw Error("E_INPUT", "a risk factor appears twice", "sensitivities");
}

void op_frtb_fx_delta(const In& in, Out& out) {
    const Value& list = sbm_list(in, "sensitivities");
    std::set<string> specified;
    if (in.find("specified_pairs")) {
        const Value& sp = in.need("specified_pairs");
        if (sp.kind != Kind::Array) schema("specified_pairs", "expected an array");
        for (const Value& p : sp.items) specified.insert(to_string(p, "specified_pairs"));
    }
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("sensitivities", "expected an object");
        const In r(v);
        SbmFactor x;
        x.bucket = r.text("pair");
        const double s = r.real("sensitivity");
        r.ready();
        x.ws = (specified.count(x.bucket) ? 0.15 / std::sqrt(2.0) : 0.15) * s;
        f.push_back(x);
    }
    in.ready();
    sbm_unique(f, [](const SbmFactor&) { return string(); });
    SbmClass c{[](const SbmFactor&, const SbmFactor&) { return 1.0; }, [](const SbmFactor&, const SbmFactor&) { return 0.6; },
               [](const SbmFactor&) { return false; }, [](const SbmFactor&) { return string(); }};
    sbm_linear(f, c, "delta", out);
}

SbmClass equity_class() {
    return {[](const SbmFactor& a, const SbmFactor& b) {
                if (a.name == b.name) return 0.999;  // same issuer, spot against repo
                const double r = eq_name_rho(a.bucket_num);
                return a.kind == b.kind ? r : r * 0.999;
            },
            [](const SbmFactor& a, const SbmFactor& b) { return eq_gamma(a.bucket_num, b.bucket_num); },
            [](const SbmFactor& a) { return a.bucket_num == 11; },
            [](const SbmFactor& a) { return a.name + "\x1f" + a.kind; }};
}

void op_frtb_equity_delta(const In& in, Out& out) {
    const Value& list = sbm_list(in, "sensitivities");
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("sensitivities", "expected an object");
        const In r(v);
        SbmFactor x;
        x.name = r.text("issuer");
        x.bucket_num = sbm_bucket_num(r, 1, 13);
        x.bucket = std::to_string(x.bucket_num);
        x.kind = sr_enum<string>(r, "kind", {{"SPOT", "SPOT"}, {"REPO", "REPO"}});
        const double s = r.real("sensitivity");
        r.ready();
        x.ws = (x.kind == "SPOT" ? eq_rw(x.bucket_num) : eq_rw(x.bucket_num) / 100) * s;
        f.push_back(x);
    }
    in.ready();
    sbm_unique(f, [](const SbmFactor& x) { return x.name + "\x1f" + x.kind; });
    sbm_linear(f, equity_class(), "delta", out);
}

double csr_tenor_years(const string& t) {
    if (t == "0.5Y") return 0.5;
    if (t == "1Y") return 1;
    if (t == "3Y") return 3;
    if (t == "5Y") return 5;
    if (t == "10Y") return 10;
    throw Error("E_INPUT", "tenor must be one of 0.5Y, 1Y, 3Y, 5Y, 10Y", "tenor");
}

void op_frtb_csr_delta(const In& in, Out& out) {
    const Value& list = sbm_list(in, "sensitivities");
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("sensitivities", "expected an object");
        const In r(v);
        SbmFactor x;
        x.name = r.text("issuer");
        x.bucket_num = sbm_bucket_num(r, 1, 18);
        x.bucket = std::to_string(x.bucket_num);
        x.tenor = r.text("tenor");
        csr_tenor_years(x.tenor);
        x.curve = sr_enum<string>(r, "curve", {{"BOND", "BOND"}, {"CDS", "CDS"}});
        const double s = r.real("sensitivity");
        r.ready();
        x.ws = csr_rw(x.bucket_num) * s;
        f.push_back(x);
    }
    in.ready();
    const auto id = [](const SbmFactor& x) { return x.name + "\x1f" + x.tenor + "\x1f" + x.curve; };
    sbm_unique(f, id);
    SbmClass c{[](const SbmFactor& a, const SbmFactor& b) {
                   return (a.name == b.name ? 1.0 : csr_name_rho(a.bucket_num)) * (a.tenor == b.tenor ? 1.0 : 0.65) *
                          (a.curve == b.curve ? 1.0 : 0.999);
               },
               [](const SbmFactor& a, const SbmFactor& b) { return csr_gamma(a.bucket_num, b.bucket_num); },
               [](const SbmFactor& a) { return a.bucket_num == 16; }, id};
    sbm_linear(f, c, "delta", out);
}

void op_frtb_commodity_delta(const In& in, Out& out) {
    const Value& list = sbm_list(in, "sensitivities");
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("sensitivities", "expected an object");
        const In r(v);
        SbmFactor x;
        x.name = r.text("commodity");
        x.bucket_num = sbm_bucket_num(r, 1, 11);
        x.bucket = std::to_string(x.bucket_num);
        x.tenor = r.text("tenor");
        x.location = r.text("location");
        const double s = r.real("sensitivity");
        r.ready();
        x.ws = cmd_rw(x.bucket_num) * s;
        f.push_back(x);
    }
    in.ready();
    const auto id = [](const SbmFactor& x) { return x.name + "\x1f" + x.tenor + "\x1f" + x.location; };
    sbm_unique(f, id);
    SbmClass c{[](const SbmFactor& a, const SbmFactor& b) {
                   return (a.name == b.name ? 1.0 : cmd_name_rho(a.bucket_num)) * (a.tenor == b.tenor ? 1.0 : 0.99) *
                          (a.location == b.location ? 1.0 : 0.999);
               },
               [](const SbmFactor& a, const SbmFactor& b) { return cmd_gamma(a.bucket_num, b.bucket_num); },
               [](const SbmFactor&) { return false; }, id};
    sbm_linear(f, c, "delta", out);
}

enum class SbmRisk { Girr, Csr, Equity, Commodity, Fx };

SbmRisk sbm_risk_class(const In& in) {
    return sr_enum<SbmRisk>(in, "risk_class", {{"GIRR", SbmRisk::Girr}, {"CSR_NONSEC", SbmRisk::Csr}, {"EQUITY", SbmRisk::Equity},
                                               {"COMMODITY", SbmRisk::Commodity}, {"FX", SbmRisk::Fx}});
}

// Reads bucket (string for GIRR and FX, else numeric in the class range) and name (not for GIRR or FX).
void sbm_bucket_name(const In& r, SbmRisk rc, SbmFactor& x) {
    if (rc == SbmRisk::Girr || rc == SbmRisk::Fx) {
        x.bucket = r.text("bucket");
        return;
    }
    const long long hi = rc == SbmRisk::Csr ? 18 : rc == SbmRisk::Equity ? 13 : 11;
    x.bucket_num = sbm_bucket_num(r, 1, hi);
    x.bucket = std::to_string(x.bucket_num);
    x.name = r.text("name");
}

// Delta name-dimension correlation (MAR21.94 FAQ1, MAR21.100) and the delta gamma across buckets.
double sbm_name_rho(SbmRisk rc, const SbmFactor& a, const SbmFactor& b) {
    if (rc == SbmRisk::Girr || rc == SbmRisk::Fx || a.name == b.name) return 1.0;
    if (rc == SbmRisk::Csr) return csr_name_rho(a.bucket_num);
    if (rc == SbmRisk::Equity) return eq_name_rho(a.bucket_num);
    return cmd_name_rho(a.bucket_num);
}
double sbm_gamma(SbmRisk rc, const SbmFactor& a, const SbmFactor& b) {
    switch (rc) {
        case SbmRisk::Girr: return 0.5;
        case SbmRisk::Fx: return 0.6;
        case SbmRisk::Csr: return csr_gamma(a.bucket_num, b.bucket_num);
        case SbmRisk::Equity: return eq_gamma(a.bucket_num, b.bucket_num);
        case SbmRisk::Commodity: return cmd_gamma(a.bucket_num, b.bucket_num);
    }
    return 0.0;
}
bool sbm_other(SbmRisk rc, const SbmFactor& a) {
    return (rc == SbmRisk::Equity && a.bucket_num == 11) || (rc == SbmRisk::Csr && a.bucket_num == 16);
}

void op_frtb_vega(const In& in, Out& out) {
    const SbmRisk rc = sbm_risk_class(in);
    const Value& list = sbm_list(in, "sensitivities");
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("sensitivities", "expected an object");
        const In r(v);
        SbmFactor x;
        sbm_bucket_name(r, rc, x);
        x.t = r.real("option_maturity");
        if (rc == SbmRisk::Girr) {
            if (!r.find("underlying_maturity")) throw Error("E_INPUT", "GIRR needs underlying_maturity", "underlying_maturity");
            x.u = r.real("underlying_maturity");
        }
        const double vr = r.real("vega");
        r.ready();
        if (!(x.t > 0)) throw Error("E_DOMAIN", "option_maturity is not positive", "option_maturity");
        if (rc == SbmRisk::Girr && !(x.u > 0)) throw Error("E_DOMAIN", "underlying_maturity is not positive", "underlying_maturity");
        const bool large = rc == SbmRisk::Equity && (x.bucket_num <= 8 || x.bucket_num == 12 || x.bucket_num == 13);
        x.ws = (large ? 0.7778 : 1.0) * vr;
        f.push_back(x);
    }
    in.ready();
    const auto id = [](const SbmFactor& x) {
        char buf[64];
        std::snprintf(buf, sizeof buf, "%.17g\x1f%.17g", x.t, x.u);
        return x.name + "\x1f" + buf;
    };
    sbm_unique(f, id);
    const auto mat = [](double a, double b) { return std::exp(-0.01 * std::fabs(a - b) / std::min(a, b)); };
    SbmClass c{[rc, mat](const SbmFactor& a, const SbmFactor& b) {
                   if (rc == SbmRisk::Girr) return std::min(mat(a.t, b.t) * mat(a.u, b.u), 1.0);
                   return std::min(sbm_name_rho(rc, a, b) * mat(a.t, b.t), 1.0);
               },
               [rc](const SbmFactor& a, const SbmFactor& b) { return sbm_gamma(rc, a, b); },
               [rc](const SbmFactor& a) { return sbm_other(rc, a); }, id};
    sbm_linear(f, c, "vega", out);
}

void op_frtb_curvature(const In& in, Out& out) {
    const SbmRisk rc = sbm_risk_class(in);
    const bool has_scalar = in.find("fx_scalar") != nullptr;
    const bool scalar = in.boolean("fx_scalar", false);
    if (has_scalar && rc != SbmRisk::Fx) throw Error("E_INPUT", "fx_scalar is for FX only", "fx_scalar");
    const Value& list = sbm_list(in, "factors");
    std::vector<SbmFactor> f;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("factors", "expected an object");
        const In r(v);
        SbmFactor x;
        sbm_bucket_name(r, rc, x);
        x.up = r.real("cvr_up");
        x.down = r.real("cvr_down");
        r.ready();
        if (scalar) x.up /= 1.5, x.down /= 1.5;
        f.push_back(x);
    }
    in.ready();
    sbm_unique(f, [](const SbmFactor& x) { return x.name; });
    SbmClass c{[rc](const SbmFactor& a, const SbmFactor& b) { return sbm_name_rho(rc, a, b); },
               [rc](const SbmFactor& a, const SbmFactor& b) { return sbm_gamma(rc, a, b); },
               [rc](const SbmFactor& a) { return sbm_other(rc, a); }, [](const SbmFactor& x) { return x.name; }};
    sbm_curvature(f, c, out);
}

constexpr Entry frtb_gb_ops[] = {
    {"risk.frtb.fx_delta", op_frtb_fx_delta},
    {"risk.frtb.equity_delta", op_frtb_equity_delta},
    {"risk.frtb.csr_delta", op_frtb_csr_delta},
    {"risk.frtb.commodity_delta", op_frtb_commodity_delta},
    {"risk.frtb.vega", op_frtb_vega},
    {"risk.frtb.curvature", op_frtb_curvature},
};
