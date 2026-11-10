package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.ShortRate;

/** Stage G short-rate models: bonds, bond options and the Hull-White swaption (short-rate-models.md). */
final class OpsShortRate {
    private OpsShortRate() {}

    private static final int MAX_PILLARS = 10_000; // ruling G-6

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    private static QfError input(String key) {
        return new QfError("E_INPUT", key + " is not a listed value", key);
    }

    /** A string input whose unknown value is E_INPUT, as the stage G specs say. */
    private static <E extends Enum<E>> E listed(In in, String key, Class<E> type) {
        String s = in.string(key);
        for (E e : type.getEnumConstants()) {
            if (e.name().equals(s)) {
                return e;
            }
        }
        throw input(key);
    }

    /** The raw model inputs; checks run after the finite gate, in the spec order. */
    private record Raw(String model, double a, double sigma, double b, double[] times, double[] dfs) {}

    private static Raw read(In in, boolean hullWhiteOnly) {
        String name = hullWhiteOnly ? "HULL_WHITE" : in.string("model");
        double a = in.real("mean_reversion");
        double sigma = in.real("sigma");
        double b = 0.0;
        double[] times = null;
        double[] dfs = null;
        if (name.equals("HULL_WHITE")) {
            In c = in.object("curve");
            times = c.reals("times");
            dfs = c.reals("discount_factors");
            in.limit(times.length > MAX_PILLARS, "curve");
        } else if (name.equals("VASICEK") || name.equals("CIR")) {
            b = in.real("long_term_mean");
        }
        return new Raw(name, a, sigma, b, times, dfs);
    }

    private static ShortRate.Model model(Raw r) {
        for (ShortRate.Model m : ShortRate.Model.values()) {
            if (m.name().equals(r.model())) {
                return m;
            }
        }
        throw input("model");
    }

    private static ShortRate.Params params(Raw r, double shortRate) {
        ShortRate.Model m = model(r);
        if (!(r.a() > 0.0) || !(r.sigma() > 0.0)) {
            throw domain(r.a() > 0.0 ? "sigma" : "mean_reversion");
        }
        if (m == ShortRate.Model.CIR && (!(r.b() > 0.0) || shortRate < 0.0)) {
            throw domain(r.b() > 0.0 ? "short_rate" : "long_term_mean");
        }
        ShortRate.Curve curve = m == ShortRate.Model.HULL_WHITE ? new ShortRate.Curve(r.times(), r.dfs()) : null;
        return new ShortRate.Params(m, r.a(), r.sigma(), r.b(), curve);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("rates.shortrate.zcb", in -> {
            Raw raw = read(in, false);
            double r = in.real("short_rate");
            double t = in.real("t_years");
            double mat = in.real("maturity_years");
            in.gate();
            ShortRate.Params p = params(raw, r);
            if (!(t >= 0.0)) {
                throw domain("t_years");
            }
            if (!(mat > t)) {
                throw domain("maturity_years");
            }
            double df = ShortRate.zcb(p, r, t, mat);
            return Operations.out("discount_factor", df, "zero_rate", -Math.log(df) / (mat - t));
        });
        table.put("rates.shortrate.zcb_option", in -> {
            Raw raw = read(in, false);
            boolean hw = raw.model().equals("HULL_WHITE");
            boolean hasRate = in.has("short_rate");
            double r = hw ? 0.0 : in.real("short_rate");
            String type = in.string("option_type");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double s = in.real("maturity_years");
            double notional = in.real("notional");
            in.gate();
            ShortRate.Params p = params(raw, r);
            if (hw && hasRate) {
                throw new QfError("E_INPUT", "short_rate is not allowed for HULL_WHITE", "short_rate");
            }
            if (!(t > 0.0)) {
                throw domain("expiry_years");
            }
            if (!(s > t)) {
                throw domain("maturity_years");
            }
            if (!(k > 0.0)) {
                throw domain("strike");
            }
            if (!type.equals("CALL") && !type.equals("PUT")) {
                throw input("option_type");
            }
            double price = notional * ShortRate.bondOption(p, r, type.equals("CALL"), k, t, s);
            double pt = hw ? p.curve().df(t) : ShortRate.zcb(p, r, 0.0, t);
            double ps = hw ? p.curve().df(s) : ShortRate.zcb(p, r, 0.0, s);
            return Operations.out("price", price, "bond_price_expiry", pt, "bond_price_maturity", ps);
        });
        table.put("rates.shortrate.swaption", in -> {
            boolean hasRate = in.has("short_rate");
            Raw raw = read(in, true);
            double t0 = in.real("expiry_years");
            double[] pay = in.reals("payment_times");
            double rate = in.real("fixed_rate");
            String type = in.string("swaption_type");
            double notional = in.real("notional");
            in.limit(pay.length > MAX_PILLARS, "payment_times");
            in.gate();
            if (hasRate) {
                throw new QfError("E_INPUT", "short_rate is not allowed for the Hull-White swaption", "short_rate");
            }
            ShortRate.Params p = params(raw, 0.0);
            if (!(t0 > 0.0)) {
                throw domain("expiry_years");
            }
            boolean ok = pay.length > 0 && pay[0] > t0;
            for (int i = 1; i < pay.length && ok; i++) {
                ok = pay[i] > pay[i - 1];
            }
            if (!ok) {
                throw input("payment_times");
            }
            if (!type.equals("PAYER") && !type.equals("RECEIVER")) {
                throw input("swaption_type");
            }
            ShortRate.Swaption sw = ShortRate.swaption(p, t0, pay, rate, type.equals("PAYER"), notional);
            return Operations.out("price", sw.price(), "forward_swap_rate", sw.forwardSwapRate(), "annuity",
                    sw.annuity());
        });
    }
}
