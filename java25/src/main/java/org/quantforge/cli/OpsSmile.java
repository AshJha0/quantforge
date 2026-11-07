package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;
import org.quantforge.vol.Black;
import org.quantforge.vol.Smile;

/** vol.delta.*, vol.smile.*, vol.svi.*, vol.ssvi.* */
final class OpsSmile {
    private OpsSmile() {}

    enum Convention { FORWARD, SPOT }

    enum Atm { ATM_FORWARD, DELTA_NEUTRAL }

    private static QfError domain(String why) {
        return new QfError("E_DOMAIN", why);
    }

    private static double scale(Convention c, Double scale) {
        if (c == Convention.FORWARD) {
            if (scale != null) {
                throw new QfError("E_INPUT", "scale must be null for FORWARD", "scale");
            }
            return 1.0;
        }
        if (scale == null || scale <= 0.0) {
            throw domain("scale must be above 0");
        }
        return scale;
    }

    private static double toStrike(double f, double v, double t, double phi, double delta, double s) {
        if (f <= 0.0 || v <= 0.0 || t <= 0.0) {
            throw domain("forward, vol and expiry_years must be above 0");
        }
        double p = phi * delta / s;
        if (!(p > 0.0 && p < 1.0)) {
            throw domain("delta is out of range");
        }
        double d1 = phi * Rng.ppnd16(p);
        return f * Math.exp(-d1 * v * Math.sqrt(t) + v * v * t / 2.0);
    }

    static List<Object> list(double[] x) {
        List<Object> l = new ArrayList<>(x.length);
        for (double v : x) {
            l.add(v);
        }
        return l;
    }

    private static Smile.Svi svi(In in) {
        In s = in.object("svi");
        return new Smile.Svi(s.real("a"), s.real("b"), s.real("rho"), s.real("m"), s.real("sigma"));
    }

    private static Map<String, Object> json(Smile.Svi s) {
        Map<String, Object> m = new java.util.LinkedHashMap<>();
        m.put("a", s.a());
        m.put("b", s.b());
        m.put("rho", s.rho());
        m.put("m", s.m());
        m.put("sigma", s.sigma());
        return m;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("vol.delta.to_strike", in -> {
            double f = in.real("forward");
            double v = in.real("vol");
            double t = in.real("expiry_years");
            double phi = Black.phi(in.choice("option_type", Black.OptionType.class));
            double delta = in.real("delta");
            Convention c = in.choice("convention", Convention.class);
            Double sc = in.nullableReal("scale");
            in.gate();
            return Operations.out("strike", toStrike(f, v, t, phi, delta, scale(c, sc)));
        });
        table.put("vol.delta.from_strike", in -> {
            double f = in.real("forward");
            double v = in.real("vol");
            double t = in.real("expiry_years");
            double phi = Black.phi(in.choice("option_type", Black.OptionType.class));
            double k = in.real("strike");
            Convention c = in.choice("convention", Convention.class);
            Double sc = in.nullableReal("scale");
            in.gate();
            double s = scale(c, sc);
            if (f <= 0.0 || v <= 0.0 || t <= 0.0 || k <= 0.0) {
                throw domain("forward, vol, expiry_years and strike must be above 0");
            }
            double r = v * Math.sqrt(t);
            double d1 = (Math.log(f / k) + v * v * t / 2.0) / r;
            return Operations.out("delta", phi * s * Normal.cdf(phi * d1));
        });
        table.put("vol.smile.rr_bf", in -> {
            double f = in.real("forward");
            double t = in.real("expiry_years");
            double atm = in.real("atm_vol");
            Atm ac = in.choice("atm_convention", Atm.class);
            double rr = in.real("rr");
            double bf = in.real("bf");
            double delta = in.real("delta");
            Convention c = in.choice("convention", Convention.class);
            Double sc = in.nullableReal("scale");
            in.gate();
            double s = scale(c, sc);
            double cv = atm + bf + rr / 2.0;
            double pv = atm + bf - rr / 2.0;
            if (atm <= 0.0 || cv <= 0.0 || pv <= 0.0 || delta <= 0.0) {
                throw domain("a vol or delta is not positive");
            }
            double ck = toStrike(f, cv, t, 1.0, delta, s);
            double pk = toStrike(f, pv, t, -1.0, -delta, s);
            double ak = ac == Atm.ATM_FORWARD ? f : f * Math.exp(atm * atm * t / 2.0);
            return Operations.out("atm_strike", ak, "call_vol", cv, "put_vol", pv, "call_strike", ck, "put_strike", pk);
        });
        table.put("vol.svi.evaluate", in -> {
            Smile.Svi s = svi(in);
            double[] k = in.reals("log_moneyness");
            in.limit(k.length > OpsForward.MAX_LIST, "log_moneyness");
            double t = in.real("expiry_years");
            in.gate();
            s.check();
            if (t <= 0.0) {
                throw domain("expiry_years must be above 0");
            }
            double[] w = new double[k.length];
            double[] v = new double[k.length];
            double[] g = new double[k.length];
            double min = Double.POSITIVE_INFINITY;
            for (int i = 0; i < k.length; i++) {
                w[i] = s.w(k[i]);
                v[i] = Math.sqrt(w[i] / t);
                g[i] = s.g(k[i]);
                min = Math.min(min, g[i]);
            }
            return Operations.out("total_variance", list(w), "implied_vol", list(v), "g", list(g), "min_g", min,
                    "butterfly_free", min >= 0.0);
        });
        table.put("vol.svi.calibrate", in -> {
            double[] k = in.reals("log_moneyness");
            double[] w = in.reals("total_variance");
            double[] wt = in.hasKey("weights") ? in.reals("weights") : null;
            in.limit(k.length > OpsForward.MAX_LIST || w.length > OpsForward.MAX_LIST, "log_moneyness");
            in.gate();
            Smile.SviFit f = Smile.calibrateSvi(k, w, wt);
            return Operations.out("svi", json(f.svi()), "rmse", f.rmse());
        });
        table.put("vol.ssvi.evaluate", in -> {
            Smile.Ssvi s = new Smile.Ssvi(in.real("rho"), in.real("eta"), in.real("gamma"));
            double[] th = in.reals("thetas");
            double[] k = in.reals("log_moneyness");
            in.limit(th.length > OpsForward.MAX_LIST || k.length > OpsForward.MAX_LIST, "thetas");
            in.gate();
            Smile.check(s);
            Smile.checkThetas(th);
            List<Object> rows = new ArrayList<>();
            for (double t : th) {
                double[] r = new double[k.length];
                for (int i = 0; i < r.length; i++) {
                    r[i] = s.w(k[i], t);
                }
                rows.add(list(r));
            }
            return Operations.out("total_variance", rows, "butterfly_free", s.butterflyFree(th), "calendar_free",
                    s.calendarFree(th));
        });
        table.put("vol.ssvi.calibrate", in -> {
            double[] th = in.reals("thetas");
            double[] k = in.reals("log_moneyness");
            double[][] w = in.anyMatrix("total_variance");
            in.limit(th.length > OpsForward.MAX_LIST || k.length > OpsForward.MAX_LIST, "thetas");
            in.gate();
            Smile.SsviFit f = Smile.calibrateSsvi(th, k, w);
            return Operations.out("rho", f.ssvi().rho(), "eta", f.ssvi().eta(), "gamma", f.ssvi().gamma(), "rmse", f.rmse());
        });
    }
}
