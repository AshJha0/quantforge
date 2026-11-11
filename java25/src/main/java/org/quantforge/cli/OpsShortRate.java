package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.G2pp;
import org.quantforge.pricing.ShortRate;
import org.quantforge.risk.McGreeks;

/** Stage G short-rate models: bonds, bond options and the Hull-White swaption (short-rate-models.md). */
final class OpsShortRate {
    private OpsShortRate() {}

    private static final int MAX_PILLARS = 10_000; // ruling G-6

    static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    static QfError input(String key) {
        return new QfError("E_INPUT", key + " is not a listed value", key);
    }

    /** A string input whose unknown value is E_INPUT, as the stage G specs say. */
    static <E extends Enum<E>> E listed(In in, String key, Class<E> type) {
        String s = in.string(key);
        for (E e : type.getEnumConstants()) {
            if (e.name().equals(s)) {
                return e;
            }
        }
        throw input(key);
    }

    /** The raw model inputs; checks run after the finite gate, in the spec order. */
    record Raw(String model, double a, double sigma, double b, double[] times, double[] dfs) {}

    static Raw read(In in, boolean hullWhiteOnly) {
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

    static ShortRate.Params params(Raw r, double shortRate) {
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

    /** Raw G2++ parameters; the curve is built (and its rules applied) in {@link #checkG2}. */
    private record Raw2(double[] times, double[] dfs, double a, double sigma, double b, double eta, double rho) {}

    private static Raw2 g2(In in) {
        double[] times = in.object("curve").reals("times");
        double[] dfs = in.object("curve").reals("discount_factors");
        in.limit(times.length > MAX_PILLARS, "curve");
        double a = in.real("a");
        double sigma = in.real("sigma");
        double b = in.real("b");
        double eta = in.real("eta");
        double rho = in.real("rho");
        return new Raw2(times, dfs, a, sigma, b, eta, rho);
    }

    private static G2pp.Params checkG2(Raw2 r) {
        if (!(r.a() > 0.0)) {
            throw domain("a");
        }
        if (!(r.sigma() > 0.0)) {
            throw domain("sigma");
        }
        if (!(r.b() > 0.0)) {
            throw domain("b");
        }
        if (!(r.eta() > 0.0)) {
            throw domain("eta");
        }
        if (!(r.rho() > -1.0 && r.rho() < 1.0)) {
            throw domain("rho");
        }
        return new G2pp.Params(new ShortRate.Curve(r.times(), r.dfs()), r.a(), r.sigma(), r.b(), r.eta(), r.rho());
    }

    /** Payment times: at least one, strictly increasing, the first after {@code t0}; else E_INPUT. */
    static void checkPayments(double[] pay, double t0) {
        boolean ok = pay.length > 0 && pay[0] > t0;
        for (int i = 1; i < pay.length && ok; i++) {
            ok = pay[i] > pay[i - 1];
        }
        if (!ok) {
            throw input("payment_times");
        }
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
            boolean hw = !in.has("model") || in.string("model").equals("HULL_WHITE");
            boolean hasRate = in.has("short_rate");
            Raw raw = read(in, !in.has("model"));
            double r0 = hw ? 0.0 : in.real("short_rate");
            double t0 = in.real("expiry_years");
            double[] pay = in.reals("payment_times");
            double rate = in.real("fixed_rate");
            String type = in.string("swaption_type");
            double notional = in.real("notional");
            in.limit(pay.length > MAX_PILLARS, "payment_times");
            in.gate();
            ShortRate.Params p = params(raw, r0);
            if (hw && hasRate) {
                throw new QfError("E_INPUT", "short_rate is not allowed for the Hull-White swaption", "short_rate");
            }
            if (!(t0 > 0.0)) {
                throw domain("expiry_years");
            }
            checkPayments(pay, t0);
            if (!type.equals("PAYER") && !type.equals("RECEIVER")) {
                throw input("swaption_type");
            }
            ShortRate.Swaption sw = ShortRate.swaption(p, r0, t0, pay, rate, type.equals("PAYER"), notional);
            return Operations.out("price", sw.price(), "forward_swap_rate", sw.forwardSwapRate(), "annuity",
                    sw.annuity());
        });

        table.put("rates.g2pp.zcb", in -> {
            Raw2 raw = g2(in);
            double x = in.real("x");
            double y = in.real("y");
            double t = in.real("t_years");
            double mat = in.real("maturity_years");
            in.gate();
            G2pp.Params p = checkG2(raw);
            if (!(t >= 0.0)) {
                throw domain("t_years");
            }
            if (!(mat > t)) {
                throw domain("maturity_years");
            }
            double df = G2pp.zcb(p, x, y, t, mat);
            return Operations.out("discount_factor", df, "zero_rate", -Math.log(df) / (mat - t));
        });
        table.put("rates.g2pp.zcb_option", in -> {
            Raw2 raw = g2(in);
            boolean states = in.has("x") || in.has("y");
            String type = in.string("option_type");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double s = in.real("maturity_years");
            double notional = in.real("notional");
            in.gate();
            G2pp.Params p = checkG2(raw);
            if (states) {
                throw new QfError("E_INPUT", "x and y are not allowed: both factors start at 0", "x");
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
            return Operations.out("price", notional * G2pp.bondOption(p, type.equals("CALL"), k, t, s),
                    "bond_price_expiry", p.curve().df(t), "bond_price_maturity", p.curve().df(s));
        });

        table.put("xva.exposure.swap_ee_hw", in -> exposure(in));

        table.put("risk.mc.greeks", in -> {
            McGreeks.Payoff pay = listed(in, "payoff", McGreeks.Payoff.class);
            McGreeks.Method method = listed(in, "method", McGreeks.Method.class);
            long n = in.integer("paths");
            long seed = in.u64("seed");
            double s = in.real("spot");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double r = in.real("rate");
            double q = in.real("dividend_yield");
            double v = in.real("vol");
            boolean smoothed = method == McGreeks.Method.PATHWISE && pay == McGreeks.Payoff.DIGITAL_CALL;
            boolean hasWidth = in.has("smoothing_width");
            boolean hasBump = in.has("bump_relative");
            double width = hasWidth ? in.real("smoothing_width") : 0.0;
            double bump = hasBump ? in.real("bump_relative") : 0.0;
            in.limit(n > 10_000_000L, "paths");
            if (n < 2) {
                throw input("paths");
            }
            in.gate();
            if (!(s > 0.0)) {
                throw domain("spot");
            }
            if (!(k > 0.0)) {
                throw domain("strike");
            }
            if (!(t > 0.0)) {
                throw domain("expiry_years");
            }
            if (!(v > 0.0)) {
                throw domain("vol");
            }
            if (hasWidth != smoothed) {
                throw input("smoothing_width");
            }
            boolean bumped = method == McGreeks.Method.BUMP;
            if (hasBump != bumped) {
                throw input("bump_relative");
            }
            if (smoothed && !(width > 0.0)) {
                throw domain("smoothing_width");
            }
            if (bumped && !(bump > 0.0 && bump < 1.0)) {
                throw domain("bump_relative");
            }
            McGreeks.Result g = McGreeks.run(pay, method, s, k, t, r, q, v, n, seed, width, bump);
            return Operations.out("price", g.price(), "price_se", g.priceSe(), "delta", g.delta(), "delta_se",
                    g.deltaSe(), "vega", g.vega(), "vega_se", g.vegaSe());
        });
    }
    /**
     * Discounted expected exposure of a swap at its reset dates and the bucketed CVA (xva-exposure.md,
     * ruling G-16). Each point is the Hull-White swaption on the remaining swap.
     */
    private static Out exposure(In in) {
        Raw raw = read(in, true);
        double t0 = in.real("start_years");
        double[] pay = in.reals("payment_times");
        double rate = in.real("fixed_rate");
        String side = in.string("side");
        double notional = in.real("notional");
        double[] ex = in.reals("exposure_times");
        boolean hasHazard = in.has("hazard_rate");
        boolean hasRecovery = in.has("recovery");
        double lambda = hasHazard ? in.real("hazard_rate") : 0.0;
        double rec = hasRecovery ? in.real("recovery") : 0.0;
        in.limit(pay.length > MAX_PILLARS, "payment_times");
        in.limit(ex.length > MAX_PILLARS, "exposure_times");
        in.gate();
        ShortRate.Params p = params(raw, 0.0);
        if (!side.equals("PAY") && !side.equals("RECEIVE")) {
            throw input("side");
        }
        if (!(t0 >= 0.0)) {
            throw domain("start_years");
        }
        boolean ok = pay.length > 0 && pay[0] > t0;
        for (int i = 1; i < pay.length && ok; i++) {
            ok = pay[i] > pay[i - 1];
        }
        if (!ok) {
            throw input("payment_times");
        }
        if (ex.length == 0) {
            throw input("exposure_times");
        }
        for (double t : ex) {
            if (!(t > 0.0)) {
                throw domain("exposure_times");
            }
        }
        int[] first = new int[ex.length];
        for (int j = 0; j < ex.length; j++) {
            if (j > 0 && !(ex[j] > ex[j - 1])) {
                throw input("exposure_times");
            }
            int k = -1;
            if (ex[j] == t0) {
                k = 0;
            } else {
                for (int i = 0; i < pay.length - 1; i++) {
                    if (ex[j] == pay[i]) {
                        k = i + 1;
                    }
                }
            }
            if (k < 0) {
                throw input("exposure_times");
            }
            first[j] = k;
        }
        if (hasHazard != hasRecovery) {
            throw input(hasHazard ? "recovery" : "hazard_rate");
        }
        if (hasHazard && !(lambda >= 0.0)) {
            throw domain("hazard_rate");
        }
        if (hasRecovery && !(rec >= 0.0 && rec < 1.0)) {
            throw domain("recovery");
        }
        double[] ee = new double[ex.length];
        for (int j = 0; j < ex.length; j++) {
            double[] rest = java.util.Arrays.copyOfRange(pay, first[j], pay.length);
            ee[j] = ShortRate.swaption(p, ex[j], rest, rate, side.equals("PAY"), notional).price();
        }
        if (!hasHazard) {
            return Operations.out("discounted_ee", ee);
        }
        double cva = 0.0;
        double prev = 1.0;
        for (int j = 0; j < ex.length; j++) {
            double surv = Math.exp(-lambda * ex[j]);
            cva += ee[j] * (prev - surv);
            prev = surv;
        }
        return Operations.out("discounted_ee", ee, "cva", (1.0 - rec) * cva);
    }
}
