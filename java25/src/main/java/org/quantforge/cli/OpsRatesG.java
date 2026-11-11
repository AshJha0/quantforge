package org.quantforge.cli;

import static org.quantforge.cli.OpsShortRate.domain;
import static org.quantforge.cli.OpsShortRate.input;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.BermudanLadder;
import org.quantforge.pricing.Lmm;
import org.quantforge.pricing.ShortRate;
import org.quantforge.pricing.ShortRateFd;
import org.quantforge.pricing.ShortRateProducts;

/** Stage G waves 2c to 2g and 3b: calibration, Bermudans, caps and floors, callable bonds, LMM. */
final class OpsRatesG {
    private OpsRatesG() {}

    private static final int MAX = 10_000; // ruling G-6

    /** True when every time is one of {@code T0, T1, ..., T(n-1)}, compared exactly. */
    private static boolean resets(double[] times, double t0, double[] pay) {
        for (double t : times) {
            boolean hit = t == t0;
            for (int i = 0; i < pay.length - 1 && !hit; i++) {
                hit = t == pay[i];
            }
            if (!hit) {
                return false;
            }
        }
        return true;
    }

    private static boolean increasing(double[] x) {
        for (int i = 1; i < x.length; i++) {
            if (!(x[i] > x[i - 1])) {
                return false;
            }
        }
        return true;
    }

    /** The raw grid; checked after the gate. */
    private record RawGrid(long nx, long steps, double width) {}

    private static RawGrid grid(In in, double[] knots) {
        In g = in.object("grid");
        long nx = g.integer("nx");
        long steps = g.integer("steps_per_year");
        double width = g.real("width");
        in.limit(nx > 10_001, "grid");
        in.limit(steps > 100_000, "grid");
        double total = 0.0;
        for (int k = 1; k < knots.length; k++) {
            total += Math.max(1.0, Math.ceil(steps * (knots[k] - knots[k - 1])));
        }
        in.limit(nx * total > 5e8, "grid"); // ruling G-31, combined grid work
        return new RawGrid(nx, steps, width);
    }

    /** {@code 0} followed by the given times: the knots of the G-18 scheme. */
    private static double[] knots(double first, double[] times) {
        double[] k = new double[times.length + 1];
        k[0] = first;
        System.arraycopy(times, 0, k, 1, times.length);
        return k;
    }

    private static ShortRateFd.Grid checkGrid(RawGrid g) {
        if (g.nx() < 5 || g.nx() % 2 == 0) {
            throw input("nx");
        }
        if (g.steps() < 1) {
            throw input("steps_per_year");
        }
        if (!(g.width() > 0.0)) {
            throw domain("width");
        }
        return new ShortRateFd.Grid((int) g.nx(), g.steps(), g.width());
    }

    private static boolean listed(String value, String key, String a, String b) {
        if (value.equals(a)) {
            return true;
        }
        if (value.equals(b)) {
            return false;
        }
        throw input(key);
    }

    private static Lmm.Abcd abcd(In in) {
        In v = in.object("abcd");
        return new Lmm.Abcd(v.real("a"), v.real("b"), v.real("c"), v.real("d"));
    }

    private static void checkAbcd(Lmm.Abcd v) {
        if (!(v.c() > 0.0)) {
            throw domain("c");
        }
        if (!(v.d() >= 0.0)) {
            throw domain("d");
        }
        if (!(v.a() + v.d() > 0.0)) {
            throw domain("a");
        }
    }

    private static void checkForwards(double[] f) {
        for (double x : f) {
            if (!(x > 0.0)) {
                throw domain("curve");
            }
        }
    }

    private static void checkPeriods(double[] times) {
        if (times.length < 2) {
            throw input("period_times");
        }
        if (!increasing(times)) {
            throw input("period_times");
        }
        if (!(times[0] > 0.0)) {
            throw domain("period_times");
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.model_reserve.dispersion", OpsRatesG::reserve);

        table.put("rates.shortrate.hw_calibrate", in -> {
            In c = in.object("curve");
            double[] ct = c.reals("times");
            double[] cd = c.reals("discount_factors");
            in.limit(ct.length > MAX, "curve");
            double a = in.real("mean_reversion");
            List<In> list = in.objects("swaptions");
            in.limit(list.size() > MAX, "swaptions");
            double[] exp = new double[list.size()];
            double[][] pay = new double[list.size()][];
            double[] rate = new double[list.size()];
            String[] type = new String[list.size()];
            double[] target = new double[list.size()];
            for (int i = 0; i < list.size(); i++) {
                In s = list.get(i);
                exp[i] = s.real("expiry_years");
                pay[i] = s.reals("payment_times");
                rate[i] = s.real("fixed_rate");
                type[i] = s.string("swaption_type");
                target[i] = s.real("target_price");
            }
            in.gate();
            if (!(a > 0.0)) {
                throw domain("mean_reversion");
            }
            ShortRate.Curve curve = new ShortRate.Curve(ct, cd);
            if (list.isEmpty()) {
                throw input("swaptions");
            }
            ShortRateProducts.Quote[] q = new ShortRateProducts.Quote[list.size()];
            for (int i = 0; i < q.length; i++) {
                if (!(exp[i] > 0.0)) {
                    throw domain("expiry_years");
                }
                OpsShortRate.checkPayments(pay[i], exp[i]);
                boolean payer = listed(type[i], "swaption_type", "PAYER", "RECEIVER");
                if (!(target[i] >= 0.0)) {
                    throw domain("target_price");
                }
                q[i] = new ShortRateProducts.Quote(exp[i], pay[i], rate[i], payer, target[i]);
            }
            ShortRateProducts.Fit fit = ShortRateProducts.calibrate(curve, a, q);
            return Operations.out("sigma", fit.sigma(), "fitted_prices", fit.fitted(), "rmse", fit.rmse());
        });

        table.put("rates.shortrate.bermudan_swaption", in -> bermudan(in, false));
        table.put("rates.shortrate.bermudan_ladder", in -> bermudan(in, true));

        table.put("rates.shortrate.callable_bond", in -> {
            OpsShortRate.Raw raw = OpsShortRate.read(in, true);
            double[] pay = in.reals("payment_times");
            double coupon = in.real("coupon_rate");
            double notional = in.real("notional");
            double[] calls = in.reals("call_times");
            double callPrice = in.real("call_price");
            RawGrid rg = grid(in, knots(0.0, pay));
            in.limit(pay.length > MAX, "payment_times");
            in.limit(calls.length > MAX, "call_times");
            in.gate();
            ShortRate.Params p = OpsShortRate.params(raw, 0.0);
            OpsShortRate.checkPayments(pay, 0.0);
            if (!increasing(calls)) {
                throw input("call_times");
            }
            for (double c : calls) {
                boolean hit = false;
                for (int i = 0; i < pay.length - 1 && !hit; i++) {
                    hit = c == pay[i];
                }
                if (!hit) {
                    throw input("call_times");
                }
            }
            if (!(callPrice > 0.0)) {
                throw domain("call_price");
            }
            ShortRateFd.Grid g = checkGrid(rg);
            return Operations.out("price", ShortRateFd.callable(p, pay, coupon, notional, calls, callPrice, g));
        });

        table.put("rates.shortrate.capfloor", in -> {
            OpsShortRate.Raw raw = OpsShortRate.read(in, false);
            boolean hw = raw.model().equals("HULL_WHITE");
            boolean hasRate = in.has("short_rate");
            double r = hw ? 0.0 : in.real("short_rate");
            double[] times = in.reals("period_times");
            double k = in.real("strike");
            String cf = in.string("cap_floor");
            double notional = in.real("notional");
            in.limit(times.length > MAX, "period_times");
            in.gate();
            ShortRate.Params p = OpsShortRate.params(raw, r);
            if (hw && hasRate) {
                throw new QfError("E_INPUT", "short_rate is not allowed for HULL_WHITE", "short_rate");
            }
            checkPeriods(times);
            for (int i = 1; i < times.length; i++) {
                if (!(1.0 + k * (times[i] - times[i - 1]) > 0.0)) {
                    throw domain("strike");
                }
            }
            boolean cap = listed(cf, "cap_floor", "CAP", "FLOOR");
            double[] lets = ShortRateProducts.capFloor(p, r, times, k, cap, notional);
            double total = 0.0;
            for (double x : lets) {
                total += x;
            }
            return Operations.out("price", total, "caplet_prices", lets);
        });

        table.put("rates.lmm.capfloor", in -> {
            In c = in.object("curve");
            double[] ct = c.reals("times");
            double[] cd = c.reals("discount_factors");
            in.limit(ct.length > MAX, "curve");
            Lmm.Abcd v = abcd(in);
            double[] times = in.reals("period_times");
            double k = in.real("strike");
            String cf = in.string("cap_floor");
            double notional = in.real("notional");
            in.limit(times.length > MAX, "period_times");
            in.gate();
            ShortRate.Curve curve = new ShortRate.Curve(ct, cd);
            checkAbcd(v);
            checkPeriods(times);
            if (!(k > 0.0)) {
                throw domain("strike");
            }
            boolean cap = listed(cf, "cap_floor", "CAP", "FLOOR");
            checkForwards(Lmm.forwards(curve, times));
            Lmm.Cap r = Lmm.capFloor(curve, v, times, k, cap, notional);
            return Operations.out("price", r.price(), "caplet_prices", r.caplets(), "forward_rates", r.forwards(),
                    "black_vols", r.vols());
        });

        table.put("rates.lmm.swaption_rebonato", in -> {
            In c = in.object("curve");
            double[] ct = c.reals("times");
            double[] cd = c.reals("discount_factors");
            in.limit(ct.length > MAX, "curve");
            Lmm.Abcd v = abcd(in);
            double beta = in.real("correlation_beta");
            double t0 = in.real("expiry_years");
            double[] pay = in.reals("payment_times");
            double k = in.real("fixed_rate");
            String side = in.string("side");
            double notional = in.real("notional");
            in.limit(pay.length > MAX, "payment_times");
            in.gate();
            ShortRate.Curve curve = new ShortRate.Curve(ct, cd);
            checkAbcd(v);
            if (!(beta >= 0.0)) {
                throw domain("correlation_beta");
            }
            if (!(t0 > 0.0)) {
                throw domain("expiry_years");
            }
            OpsShortRate.checkPayments(pay, t0);
            if (!(k > 0.0)) {
                throw domain("fixed_rate");
            }
            boolean payer = listed(side, "side", "PAY", "RECEIVE");
            double[] times = new double[pay.length + 1];
            times[0] = t0;
            System.arraycopy(pay, 0, times, 1, pay.length);
            checkForwards(Lmm.forwards(curve, times));
            Lmm.Swaption s = Lmm.rebonato(curve, v, beta, t0, pay, k, payer, notional);
            return Operations.out("price", s.price(), "swap_rate", s.swapRate(), "annuity", s.annuity(), "black_vol",
                    s.blackVol());
        });
    }

    /** Model-reserve dispersion (model-reserve.md, ruling G-36). */
    private static Out reserve(In in) {
        In pr = in.object("prices");
        java.util.TreeMap<String, Double> prices = new java.util.TreeMap<>();
        for (String k : pr.keys()) {
            prices.put(k, pr.real(k));
        }
        String ref = in.string("reference_model");
        in.limit(prices.size() > MAX, "prices");
        in.gate();
        if (prices.size() < 2) {
            throw input("prices");
        }
        if (!prices.containsKey(ref)) {
            throw input("reference_model");
        }
        double pRef = prices.get(ref);
        double sum = 0.0;
        double max = Double.NEGATIVE_INFINITY;
        double min = Double.POSITIVE_INFINITY;
        double reserve = -1.0;
        String worst = null;
        for (Map.Entry<String, Double> e : prices.entrySet()) {
            double p = e.getValue();
            sum += p;
            max = Math.max(max, p);
            min = Math.min(min, p);
            double dev = Math.abs(p - pRef);
            if (dev > reserve) {
                reserve = dev;
                worst = e.getKey();
            }
        }
        double range = max - min;
        Double rel = pRef == 0.0 ? null : reserve / Math.abs(pRef);
        return Operations.out("mean", sum / prices.size(), "range", range, "half_range", range / 2.0, "reserve",
                reserve, "worst_model", worst, "relative_reserve", rel);
    }

    /** The Bermudan swaption (wave 2d) and its AAD ladder (wave 3d), with the same inputs and checks. */
    private static Out bermudan(In in, boolean ladder) {
        OpsShortRate.Raw raw = OpsShortRate.read(in, true);
        double t0 = in.real("start_years");
        double[] pay = in.reals("payment_times");
        double rate = in.real("fixed_rate");
        String type = in.string("swaption_type");
        double notional = in.real("notional");
        double[] ex = in.reals("exercise_times");
        RawGrid rg = grid(in, knots(0.0, ex));
        in.limit(pay.length > MAX, "payment_times");
        in.limit(ex.length > MAX, "exercise_times");
        in.gate();
        ShortRate.Params p = OpsShortRate.params(raw, 0.0);
        if (!(t0 > 0.0)) {
            throw domain("start_years");
        }
        OpsShortRate.checkPayments(pay, t0);
        boolean payer = listed(type, "swaption_type", "PAYER", "RECEIVER");
        if (ex.length == 0 || !increasing(ex) || !resets(ex, t0, pay)) {
            throw input("exercise_times");
        }
        ShortRateFd.Grid g = checkGrid(rg);
        if (!ladder) {
            return Operations.out("price", ShortRateFd.bermudan(p, pay, rate, payer, notional, ex, g));
        }
        BermudanLadder.Ladder l = BermudanLadder.ladder(raw.times(), raw.dfs(), p.a(), p.sigma(), pay, rate,
                payer, notional, ex, g);
        return Operations.out("price", l.price(), "d_price_d_discount_factors", l.dDiscountFactors(),
                "d_price_d_mean_reversion", l.dMeanReversion(), "d_price_d_sigma", l.dSigma());
    }
}
