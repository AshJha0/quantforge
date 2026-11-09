package org.quantforge.cli;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;
import org.quantforge.vol.Garch;
import org.quantforge.vol.Smile;
import org.quantforge.vol.Surfaces;
import org.quantforge.vol.VarianceStrip;

/** Stage E operations: E1 (surfaces, local and forward vol) and E7 (GARCH, variance swaps, VIX). */
final class OpsVolSurfaces {
    private OpsVolSurfaces() {}

    enum Rule { STICKY_STRIKE, STICKY_DELTA }

    enum Method { LOG, ABSOLUTE }

    private static QfError input(String key, String why) {
        return new QfError("E_INPUT", why, key);
    }

    private static QfError domain(String key, String why) {
        return new QfError("E_DOMAIN", why, key);
    }

    private static List<Surfaces.Slice> slices(In in) {
        List<Surfaces.Slice> out = new ArrayList<>();
        for (In s : in.objects("slices")) {
            out.add(new Surfaces.Slice(s.real("expiry_years"), OpsSmile.svi(s)));
        }
        return out;
    }

    private static List<Object> cells(List<Surfaces.Cell> cells) {
        List<Object> out = new ArrayList<>();
        for (Surfaces.Cell c : cells) {
            out.add(map("expiry_index", c.expiry(), "k_index", c.k()));
        }
        return out;
    }

    private static Map<String, Object> map(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    /** The four outputs of vol.svi.surface_check, or E_ARBITRAGE when rejecting. */
    private static List<Object> checkOutputs(Surfaces.Check c, boolean reject) {
        if (reject && !c.arbitrageFree()) {
            throw new QfError("E_ARBITRAGE", "the surface has arbitrage");
        }
        List<Object> wings = new ArrayList<>();
        for (Surfaces.Wing w : c.wings()) {
            wings.add(map("expiry_index", w.expiry(), "side", w.side(), "kind", w.kind()));
        }
        return List.of("butterfly_violations", cells(c.butterfly()), "calendar_violations", cells(c.calendar()),
                "wing_violations", wings, "arbitrage_free", c.arbitrageFree());
    }

    private static void increasing(double[] t, String key) {
        if (t.length == 0) {
            throw input(key, key + " is empty");
        }
        for (int i = 1; i < t.length; i++) {
            if (!(t[i] > t[i - 1])) {
                throw input(key, key + " must increase");
            }
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        registerE1(table);
        registerE7(table);
    }

    private static void registerE1(Map<String, Function<In, Out>> table) {
        table.put("vol.svi.surface_check", in -> {
            List<Surfaces.Slice> s = slices(in);
            double[] k = in.reals("log_moneyness");
            boolean reject = in.bool("reject");
            in.limit(s.size() > Surfaces.MAX_SLICES, "slices");
            in.limit(k.length > Surfaces.MAX_POINTS, "log_moneyness");
            in.gate();
            Surfaces.checkSlices(s);
            Surfaces.checkGrid(k);
            return Operations.out(checkOutputs(Surfaces.check(s, k), reject).toArray());
        });
        table.put("vol.ssvi.to_svi", in -> {
            double rho = in.real("rho");
            double eta = in.real("eta");
            double gamma = in.real("gamma");
            double theta = in.gate(in.real("theta"));
            return Operations.out("svi", OpsSmile.json(Surfaces.ssviToSvi(rho, eta, gamma, theta)));
        });
        table.put("vol.svi.fit_surface", in -> {
            double[] t = in.reals("expiry_years");
            double[] k = in.reals("log_moneyness");
            double[][] w = in.anyMatrix("total_variance");
            boolean reject = in.bool("reject");
            in.limit(t.length > Surfaces.MAX_SLICES, "expiry_years");
            in.limit(k.length > Surfaces.MAX_POINTS, "log_moneyness");
            in.gate();
            increasing(t, "expiry_years");
            if (w.length != t.length) {
                throw input("total_variance", "one row per expiry");
            }
            if (t.length > Surfaces.MAX_SLICES) {
                throw new QfError("E_LIMIT", "more than " + Surfaces.MAX_SLICES + " slices", "expiry_years");
            }
            List<Surfaces.Slice> s = new ArrayList<>();
            List<Object> fitted = new ArrayList<>();
            List<Object> rmse = new ArrayList<>();
            for (int j = 0; j < t.length; j++) {
                Smile.SviFit f = Smile.calibrateSvi(k, w[j], null);
                s.add(new Surfaces.Slice(t[j], f.svi()));
                fitted.add(map("expiry_years", t[j], "svi", OpsSmile.json(f.svi())));
                rmse.add(f.rmse());
            }
            Surfaces.checkSlices(s);
            Surfaces.checkGrid(k);
            List<Object> kv = new ArrayList<>(List.of("slices", fitted, "rmse", rmse));
            kv.addAll(checkOutputs(Surfaces.check(s, k), reject));
            return Operations.out(kv.toArray());
        });
        table.put("vol.local.dupire", in -> {
            List<Surfaces.Slice> s = slices(in);
            List<In> pts = in.objects("points");
            double[] t = new double[pts.size()];
            double[] k = new double[pts.size()];
            for (int i = 0; i < t.length; i++) {
                t[i] = pts.get(i).real("expiry_years");
                k[i] = pts.get(i).real("log_moneyness");
            }
            in.limit(s.size() > Surfaces.MAX_SLICES, "slices");
            in.limit(t.length > Surfaces.MAX_POINTS, "points");
            in.gate();
            Surfaces.checkSlices(s);
            if (t.length == 0) {
                throw input("points", "points is empty");
            }
            if (t.length > Surfaces.MAX_POINTS) {
                throw new QfError("E_LIMIT", "too many points", "points");
            }
            for (double x : t) {
                if (!(x > 0.0)) {
                    throw domain("points", "expiry_years must be above 0");
                }
            }
            Surfaces.LocalVol lv = Surfaces.dupire(s, t, k);
            return Operations.out("total_variance", OpsSmile.list(lv.totalVariance()), "implied_vol",
                    OpsSmile.list(lv.impliedVol()), "local_vol", OpsSmile.list(lv.localVol()));
        });
        table.put("vol.forward.vol", in -> {
            double[] t = in.reals("expiry_years");
            double[] v = in.reals("vols");
            in.limit(t.length > OpsForward.MAX_LIST || v.length > OpsForward.MAX_LIST, "expiry_years"); // C10
            in.gate();
            increasing(t, "expiry_years");
            if (v.length != t.length) {
                throw input("vols", "vols and expiry_years differ in length");
            }
            if (!(t[0] > 0.0)) {
                throw domain("expiry_years", "the first expiry must be above 0 (ruling E-A36)");
            }
            for (double x : v) {
                if (!(x > 0.0)) {
                    throw domain("vols", "vols must be above 0");
                }
            }
            return Operations.out("forward_vols", OpsSmile.list(Surfaces.forwardVols(t, v)));
        });
        table.put("vol.smile.dynamics", OpsVolSurfaces::smileDynamics);
        table.put("vol.volofvol.measure", in -> {
            double[] v = in.reals("vols");
            double ppy = in.real("periods_per_year");
            Method m = in.choice("method", Method.class);
            in.limit(v.length > Surfaces.MAX_POINTS, "vols"); // stated 10,000 (ruling E-A35)
            in.gate();
            if (v.length < 3) {
                throw input("vols", "need at least 3 vols");
            }
            for (double x : v) {
                if (!(x > 0.0)) {
                    throw domain("vols", "vols must be above 0");
                }
            }
            if (!(ppy > 0.0)) {
                throw domain("periods_per_year", "periods_per_year must be above 0");
            }
            double[] r = Surfaces.volOfVol(v, ppy, m == Method.LOG);
            return Operations.out("vol_of_vol", r[1], "mean_change", r[0]);
        });
    }

    private static Out smileDynamics(In in) {
        Smile.Svi svi = OpsSmile.svi(in);
        double t = in.real("expiry_years");
        double s0 = in.real("spot");
        double s1 = in.real("spot_shifted");
        double r = in.real("rate");
        double q = in.real("dividend_yield");
        double[] k = in.reals("strikes");
        Rule rule = in.choice("rule", Rule.class);
        Black.OptionType type = in.choice("option_type", Black.OptionType.class);
        in.limit(k.length > OpsForward.MAX_LIST, "strikes"); // C10 (ruling E-A35)
        in.gate();
        if (k.length == 0) {
            throw input("strikes", "strikes is empty");
        }
        svi.check();
        if (!(t > 0.0)) {
            throw domain("expiry_years", "expiry_years must be above 0");
        }
        if (!(s0 > 0.0) || !(s1 > 0.0)) {
            throw domain("spot", "spot must be above 0");
        }
        for (double x : k) {
            if (!(x > 0.0)) {
                throw domain("strikes", "strikes must be above 0");
            }
        }
        double phi = Black.phi(type);
        double d = Math.exp(-r * t);
        double f0 = s0 * Math.exp((r - q) * t);
        double f1 = s1 * Math.exp((r - q) * t);
        double sq = Math.sqrt(t);
        double eq = Math.exp(-q * t);
        int n = k.length;
        double[] v0 = new double[n];
        double[] v1 = new double[n];
        double[] p0 = new double[n];
        double[] p1 = new double[n];
        double[] delta = new double[n];
        for (int i = 0; i < n; i++) {
            double k0 = Math.log(k[i] / f0);
            v0[i] = Math.sqrt(svi.w(k0) / t);
            v1[i] = rule == Rule.STICKY_STRIKE ? v0[i] : Math.sqrt(svi.w(Math.log(k[i] / f1)) / t);
            p0[i] = Black.lognormal(phi, f0, k[i], t, d, v0[i]);
            p1[i] = Black.lognormal(phi, f1, k[i], t, d, v1[i]);
            double d1 = Math.log(f0 / k[i]) / (v0[i] * sq) + v0[i] * sq / 2.0;
            double bs = phi * eq * Normal.cdf(phi * d1);
            double vega = s0 * eq * Normal.pdf(d1) * sq;
            double wk = svi.b() * (svi.rho() + (k0 - svi.m()) / Math.hypot(k0 - svi.m(), svi.sigma()));
            double dvds = rule == Rule.STICKY_STRIKE ? 0.0 : -(wk / (2.0 * v0[i] * t)) / s0;
            delta[i] = bs + vega * dvds;
        }
        return Operations.out("vols_base", OpsSmile.list(v0), "vols_shifted", OpsSmile.list(v1), "prices_base",
                OpsSmile.list(p0), "prices_shifted", OpsSmile.list(p1), "deltas", OpsSmile.list(delta));
    }

    /** The initial variance input: "SAMPLE" (null here) or a number; any other JSON type is E_SCHEMA. */
    private static Double initialVariance(In in) {
        Object v = in.anyValue("initial_variance");
        if (v instanceof String && !In.isNonFiniteToken(v)) {
            return null;
        }
        if (v instanceof org.quantforge.core.Json.Number || In.isNonFiniteToken(v)) {
            return in.real("initial_variance");
        }
        throw new QfError("E_SCHEMA", "initial_variance must be a string or a number", "initial_variance");
    }

    private static void sampleKeyword(In in) {
        if (in.anyValue("initial_variance") instanceof String s && !s.equals("SAMPLE") && !In.isNonFiniteToken(s)) {
            throw input("initial_variance", "initial_variance must be SAMPLE or a number");
        }
    }

    private static double startVariance(Double given, double[] r) {
        double v = given == null ? Garch.sampleVariance(r) : given;
        if (!(v > 0.0)) {
            throw domain("initial_variance", "initial variance must be above 0");
        }
        return v;
    }

    private static void registerE7(Map<String, Function<In, Out>> table) {
        table.put("vol.garch.loglik", in -> {
            double[] r = in.reals("returns");
            double omega = in.real("omega");
            double alpha = in.real("alpha");
            double beta = in.real("beta");
            Double iv = in.gate(initialVariance(in));
            if (r.length < 2) {
                throw input("returns", "need at least 2 returns");
            }
            sampleKeyword(in);
            Garch.checkParameters(omega, alpha, beta);
            Garch.Path p = Garch.path(r, omega, alpha, beta, startVariance(iv, r));
            return Operations.out("loglik", p.loglik(), "variances", OpsSmile.list(p.variances()), "next_variance",
                    p.next());
        });
        table.put("vol.garch.forecast", in -> {
            double omega = in.real("omega");
            double alpha = in.real("alpha");
            double beta = in.real("beta");
            double next = in.real("next_variance");
            long h = in.integer("horizon");
            double ppy = in.real("periods_per_year");
            in.limit(h > 100_000, "horizon");
            in.gate();
            if (h < 1 || !(ppy > 0.0)) {
                throw input("horizon", "horizon must be at least 1 and periods_per_year above 0");
            }
            Garch.checkParameters(omega, alpha, beta);
            if (!(next > 0.0)) {
                throw domain("next_variance", "next_variance must be above 0");
            }
            if (alpha + beta >= 1.0) {
                throw domain("alpha", "alpha + beta must be below 1 for a forecast");
            }
            Garch.Forecast f = Garch.forecast(omega, alpha, beta, next, (int) h, ppy);
            return Operations.out("variances", OpsSmile.list(f.variances()), "total_variance", f.total(),
                    "annualized_vol", f.annualizedVol(), "long_run_variance", f.longRun());
        });
        table.put("vol.garch.fit", in -> {
            double[] r = in.reals("returns");
            Double iv = in.gate(initialVariance(in));
            if (r.length < Garch.MIN_FIT_RETURNS) {
                throw input("returns", "need at least " + Garch.MIN_FIT_RETURNS + " returns");
            }
            sampleKeyword(in);
            return Operations.out("loglik", Garch.fit(r, startVariance(iv, r)));
        });
        table.put("vol.varswap.fair_strike", OpsVolSurfaces::fairStrike);
        table.put("vol.varswap.realized", in -> {
            double[] p = in.reals("prices");
            double a = in.real("periods_per_year");
            double kv = in.real("variance_strike");
            double nv = in.gate(in.real("variance_notional"));
            if (p.length < 2) {
                throw input("prices", "need at least 2 prices");
            }
            for (double x : p) {
                if (!(x > 0.0)) {
                    throw domain("prices", "prices must be above 0");
                }
            }
            double v = VarianceStrip.realizedVariance(p, a);
            return Operations.out("realized_variance", v, "realized_vol", Math.sqrt(v), "payoff", nv * (v - kv));
        });
        table.put("vol.vix.term_variance", in -> {
            Term t = term(in);
            in.gate();
            VarianceStrip.Term v = VarianceStrip.term(t.minutes, t.rate, t.strip);
            return Operations.out("forward", v.forward(), "k0", v.k0(), "variance", v.variance(), "strikes_used",
                    OpsSmile.list(v.strikesUsed()));
        });
        table.put("vol.vix.index", in -> {
            Term near = term(in.object("near"));
            Term next = term(in.object("next"));
            in.gate();
            // the bracket reads only the minutes, so it comes before either term's checks (ruling E-B34)
            if (!(near.minutes < next.minutes && near.minutes <= VarianceStrip.MINUTES_30D
                    && VarianceStrip.MINUTES_30D <= next.minutes)) {
                throw input("near", "terms must bracket 30 days, near before next");
            }
            VarianceStrip.Term a = VarianceStrip.term(near.minutes, near.rate, near.strip);
            VarianceStrip.Term b = VarianceStrip.term(next.minutes, next.rate, next.strip);
            return Operations.out("index", VarianceStrip.index(near.minutes, a, next.minutes, b), "near_variance",
                    a.variance(), "next_variance", b.variance());
        });
    }

    private record Term(long minutes, double rate, List<VarianceStrip.Quote> strip) {}

    /** Ruling F-15: a quote may be null, carried as NaN (a real NaN token was already held by rule F-2). */
    private static double quote(In q, String key) {
        Double v = q.nullableReal(key);
        return v == null ? Double.NaN : v;
    }

    private static Term term(In in) {
        long n = in.integer("minutes_to_expiry");
        double r = in.real("rate");
        List<VarianceStrip.Quote> strip = new ArrayList<>();
        for (In q : in.objects("strip")) {
            strip.add(new VarianceStrip.Quote(q.real("strike"), quote(q, "call_bid"), quote(q, "call_ask"),
                    quote(q, "put_bid"), quote(q, "put_ask")));
        }
        return new Term(n, r, strip);
    }

    private static Out fairStrike(In in) {
        LocalDate asOf = in.date("as_of");
        LocalDate mat = in.date("maturity");
        double s0 = in.real("spot");
        double r = in.real("rate");
        double q = in.real("dividend_yield");
        double[] puts = in.reals("put_strikes");
        double[] calls = in.reals("call_strikes");
        List<In> vl = in.objects("vols");
        double[] vk = new double[vl.size()];
        double[] vv = new double[vl.size()];
        for (int i = 0; i < vk.length; i++) {
            vk[i] = vl.get(i).real("strike");
            vv[i] = vl.get(i).real("vol");
        }
        double dk = in.real("extension_step");
        double kVar = in.real("variance_strike");
        double nVar = in.gate(in.real("variance_notional"));
        if (!mat.isAfter(asOf)) {
            throw input("maturity", "maturity must be after as_of");
        }
        Set<Double> union = new HashSet<>();
        for (double[] list : new double[][] {puts, calls}) {
            Set<Double> seen = new HashSet<>();
            if (list.length == 0) {
                throw input("put_strikes", "a strike list is empty");
            }
            for (double x : list) {
                if (!seen.add(x)) {
                    throw input("put_strikes", "repeated strike in a list");
                }
            }
            union.addAll(seen);
        }
        for (double x : puts) {
            if (x > s0) {
                throw input("put_strikes", "a put strike is above spot");
            }
        }
        for (double x : calls) {
            if (x < s0) {
                throw input("call_strikes", "a call strike is below spot");
            }
        }
        Map<Double, Double> vol = new HashMap<>();
        for (int i = 0; i < vk.length; i++) {
            if (vol.put(vk[i], vv[i]) != null || !union.contains(vk[i])) {
                throw input("vols", "vols must list each strike exactly once");
            }
        }
        if (vol.size() != union.size()) {
            throw input("vols", "vols must list each strike exactly once");
        }
        double kMin = Double.POSITIVE_INFINITY;
        for (double x : puts) {
            kMin = Math.min(kMin, x);
        }
        if (!(s0 > 0.0)) {
            throw domain("spot", "spot must be above 0");
        }
        for (double v : vv) {
            if (!(v > 0.0)) {
                throw domain("vols", "vols must be above 0");
            }
        }
        if (!(dk > 0.0) || !(kMin - dk > 0.0)) {
            throw domain("extension_step", "extension_step must be above 0 and leave the lowest strike above 0");
        }
        double t = ChronoUnit.DAYS.between(asOf, mat) / 365.0;
        double fv = VarianceStrip.fairVariance(s0, r, q, t, puts, calls, vol::get, dk);
        if (fv < 0.0) {
            throw domain("put_strikes", "replicated variance is below 0 (ruling E-B36)");
        }
        double pv = nVar * Math.exp(-r * t) * (fv - kVar);
        return Operations.out("fair_variance", fv, "fair_vol", Math.sqrt(fv), "pv", pv);
    }
}
