package org.quantforge.cli;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.vol.Sabr;

/** vol.sabr.* */
final class OpsSabr {
    private OpsSabr() {}

    enum OnNegative { REPORT, REJECT }

    private static double shift(In in) {
        return in.hasKey("shift") ? in.real("shift") : 0.0;
    }

    private static Sabr.Params params(In in) {
        return new Sabr.Params(in.real("alpha"), in.real("beta"), in.real("rho"), in.real("nu"));
    }

    private static double[] shifted(double[] k, double s) {
        double[] x = new double[k.length];
        for (int i = 0; i < x.length; i++) {
            x[i] = k[i] + s;
        }
        return x;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("vol.sabr.hagan", in -> {
            double f = in.real("forward");
            double[] k = in.reals("strikes");
            in.limit(k.length > OpsForward.MAX_LIST, "strikes");
            double t = in.real("expiry_years");
            Sabr.Params p = params(in);
            double s = shift(in);
            in.gate();
            OpsForward.nonEmpty(k.length);
            double[] x = shifted(k, s);
            Sabr.check(t, p, f + s, x);
            double[] v = new double[x.length];
            for (int i = 0; i < v.length; i++) {
                v[i] = Sabr.hagan(f + s, x[i], t, p);
            }
            return Operations.out("vols", OpsSmile.list(v));
        });
        table.put("vol.sabr.density", in -> {
            double f = in.real("forward");
            double[] k = in.reals("strikes");
            in.limit(k.length > OpsForward.MAX_LIST, "strikes");
            double t = in.real("expiry_years");
            Sabr.Params p = params(in);
            double s = shift(in);
            double h = in.real("h_strike");
            OnNegative on = in.choice("on_negative", OnNegative.class);
            in.gate();
            OpsForward.nonEmpty(k.length);
            double[] x = shifted(k, s);
            Sabr.check(t, p, f + s, x);
            if (h <= 0.0) {
                throw new QfError("E_DOMAIN", "h_strike must be above 0", "h_strike");
            }
            for (double v : x) {
                if (v - h <= 0.0) {
                    throw new QfError("E_DOMAIN", "strike minus h_strike is not positive");
                }
            }
            double[] d = Sabr.density(f + s, x, t, p, h);
            double min = Arrays.stream(d).min().orElse(Double.POSITIVE_INFINITY);
            boolean negative = min < -1e-9;
            if (negative && on == OnNegative.REJECT) {
                throw new QfError("E_ARBITRAGE", "Hagan density is negative");
            }
            return Operations.out("density", OpsSmile.list(d), "min_density", min, "negative_density", negative);
        });
        table.put("vol.sabr.calibrate", in -> {
            double f = in.real("forward");
            double t = in.real("expiry_years");
            double beta = in.real("beta");
            double s = shift(in);
            double[] k = in.reals("strikes");
            double[] v = in.reals("vols");
            double[] w = in.hasKey("weights") ? in.reals("weights") : null;
            in.limit(k.length > OpsForward.MAX_LIST || v.length > OpsForward.MAX_LIST, "strikes");
            in.gate();
            OpsForward.nonEmpty(k.length);
            if (k.length < 3 || v.length != k.length || (w != null && w.length != k.length)) {
                throw new QfError("E_INPUT", "too few strikes, or lengths differ");
            }
            for (int i = 1; i < k.length; i++) {
                if (k[i] <= k[i - 1]) {
                    throw new QfError("E_INPUT", "strikes must increase");
                }
            }
            double[] x = shifted(k, s);
            Sabr.check(t, new Sabr.Params(1.0, beta, 0.0, 0.0), f + s, x);
            for (int i = 0; i < v.length; i++) {
                if (v[i] <= 0.0 || (w != null && w[i] <= 0.0)) {
                    throw new QfError("E_DOMAIN", "vol or weight");
                }
            }
            Sabr.SabrFit r = Sabr.calibrate(f + s, t, beta, x, v, w);
            return Operations.out("alpha", r.alpha(), "rho", r.rho(), "nu", r.nu(), "rmse", r.rmse());
        });
        table.put("vol.sabr.arbfree", in -> {
            double f = in.real("forward");
            double t = in.real("expiry_years");
            Sabr.Params p = params(in);
            double s = shift(in);
            long cells = in.integer("cells");
            long below = in.integer("cells_below");
            long steps = in.integer("steps");
            in.limit(cells > 20000 || steps > 20000, "cells");
            double[] k = in.reals("strikes");
            in.limit(k.length > OpsForward.MAX_LIST, "strikes");
            in.gate();
            OpsForward.nonEmpty(k.length);
            double[] x = shifted(k, s);
            Sabr.check(t, p, f + s, x);
            if (p.beta() >= 1.0) {
                throw new QfError("E_DOMAIN", "beta must be below 1", "beta");
            }
            if (below < 1 || below >= cells || steps < 1) {
                throw new QfError("E_INPUT", "cells_below or steps");
            }
            Sabr.ArbFree r = Sabr.arbFree(f + s, t, p, (int) cells, (int) below, (int) steps, x);
            return Operations.out("call_prices", OpsSmile.list(r.calls()), "vols", new ArrayList<Object>(Arrays.asList(r.vols())),
                    "mass", r.mass(), "mean", r.mean(), "absorbed", r.absorbed(), "min_density", r.minDensity());
        });
    }
}
