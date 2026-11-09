package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.Exotics;
import org.quantforge.vol.Black;

/** Stage E5: exotics and American options (exotics.md). */
final class OpsExotics {
    private OpsExotics() {}

    enum Payoff { CASH_OR_NOTHING, ASSET_OR_NOTHING }

    enum Averaging { CONTINUOUS, DISCRETE }

    enum Exercise { AMERICAN, EUROPEAN }

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    private static void positive(double x, String key) {
        if (!(x > 0.0)) {
            throw domain(key);
        }
    }

    /** spot, strike, expiry_years, rate, dividend_yield, vol, option_type; strike optional. */
    private record Common(double s, double k, double t, double r, double q, double v, double phi) {
        static Common read(In in, boolean strike) {
            return read(in, strike, true);
        }

        /** The chooser has no option_type: the holder picks call or put at choose_years. */
        static Common read(In in, boolean strike, boolean typed) {
            return new Common(in.real("spot"), strike ? in.real("strike") : 1.0, in.real("expiry_years"),
                    in.real("rate"), in.real("dividend_yield"), in.real("vol"),
                    typed ? Black.phi(in.choice("option_type", Black.OptionType.class)) : 1.0);
        }

        void check() {
            positive(s, "spot");
            positive(k, "strike");
            positive(t, "expiry_years");
            positive(v, "vol");
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("exotic.digital.price", in -> {
            Common c = Common.read(in, true);
            Payoff p = in.choice("payoff", Payoff.class);
            double cash = in.gate(in.real("cash"));
            c.check();
            positive(cash, "cash");
            return Operations.out("price", Exotics.digital(c.phi, p == Payoff.CASH_OR_NOTHING, c.s, c.k, c.t, c.r,
                    c.q, c.v, cash));
        });
        table.put("exotic.barrier.price", in -> {
            Common c = Common.read(in, true);
            double h = in.real("barrier");
            double rebate = in.real("rebate");
            Exotics.BarrierType type = in.gate(in.choice("barrier_type", Exotics.BarrierType.class));
            c.check();
            positive(h, "barrier");
            if (!(rebate >= 0.0)) {
                throw domain("rebate");
            }
            return Operations.out("price", Exotics.barrier(c.phi, type, c.s, c.k, c.t, c.r, c.q, c.v, h, rebate));
        });
        table.put("exotic.asian.geometric", in -> {
            Common c = Common.read(in, true);
            Averaging a = in.choice("averaging", Averaging.class);
            double[] fix = in.reals("fixing_years");
            in.limit(fix.length > OpsForward.MAX_LIST, "fixing_years"); // C10 (ruling E-A35)
            in.gate();
            c.check(); // input order: the common values before the fixing rule (ruling E-A38)
            if (a == Averaging.CONTINUOUS ? fix.length != 0 : fix.length == 0) {
                throw new QfError("E_INPUT", "fixing_years must be [] for CONTINUOUS and given for DISCRETE",
                        "fixing_years");
            }
            for (int i = 0; i < fix.length; i++) {
                if (!(fix[i] > 0.0 && fix[i] <= c.t) || (i > 0 && !(fix[i] > fix[i - 1]))) {
                    throw new QfError("E_INPUT", "fixings must increase within (0, T]", "fixing_years");
                }
            }
            return Operations.out("price", a == Averaging.CONTINUOUS
                    ? Exotics.asianContinuous(c.phi, c.s, c.k, c.t, c.r, c.q, c.v)
                    : Exotics.asianDiscrete(c.phi, c.s, c.k, c.t, c.r, c.q, c.v, fix));
        });
        table.put("exotic.lookback.floating", in -> {
            Common c = Common.read(in, false);
            double e = in.gate(in.real("running_extreme"));
            c.check();
            if (c.phi > 0 ? !(e > 0.0 && e <= c.s) : !(e >= c.s)) {
                throw domain("running_extreme");
            }
            if (Math.abs(c.r - c.q) <= 1e-8 * c.v * c.v) {
                throw new QfError("E_DOMAIN", "cost of carry too near zero (rulings E-A20, E-A28)", "dividend_yield");
            }
            return Operations.out("price", Exotics.lookback(c.phi, c.s, e, c.t, c.r, c.q, c.v));
        });
        table.put("exotic.quanto.price", in -> {
            double s = in.real("spot");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double rd = in.real("domestic_rate");
            double rf = in.real("foreign_rate");
            double q = in.real("dividend_yield");
            double v = in.real("vol");
            double fx = in.real("fx_vol");
            double rho = in.real("correlation");
            double phi = in.gate(Black.phi(in.choice("option_type", Black.OptionType.class)));
            positive(s, "spot");
            positive(k, "strike");
            positive(t, "expiry_years");
            positive(v, "vol");
            positive(fx, "fx_vol");
            if (!(rho >= -1.0 && rho <= 1.0)) {
                throw domain("correlation");
            }
            return Operations.out("price", Exotics.quanto(phi, s, k, t, rd, rf, q, v, fx, rho));
        });
        table.put("exotic.chooser.price", in -> {
            Common c = Common.read(in, true, false);
            double tc = in.gate(in.real("choose_years"));
            c.check();
            if (!(tc > 0.0 && tc <= c.t)) {
                throw new QfError("E_INPUT", "choose_years must be in (0, T]", "choose_years");
            }
            return Operations.out("price", Exotics.chooser(c.s, c.k, c.t, c.r, c.q, c.v, tc));
        });
        table.put("exotic.spread.kirk", in -> {
            double f1 = in.real("forward_1");
            double f2 = in.real("forward_2");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double r = in.real("rate");
            double v1 = in.real("vol_1");
            double v2 = in.real("vol_2");
            double rho = in.gate(in.real("correlation"));
            positive(f1, "forward_1");
            positive(f2, "forward_2");
            positive(f2 + k, "strike");
            positive(t, "expiry_years");
            positive(v1, "vol_1");
            positive(v2, "vol_2");
            if (!(rho >= -1.0 && rho <= 1.0)) {
                throw domain("correlation");
            }
            return Operations.out("price", Exotics.kirk(f1, f2, k, t, r, v1, v2, rho));
        });
        table.put("exotic.basket.moment", in -> {
            double[] f = in.reals("forwards");
            double[] w = in.reals("weights");
            double[] v = in.reals("vols");
            double[][] rho = in.anyMatrix("correlation");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double r = in.real("rate");
            double phi = Black.phi(in.choice("option_type", Black.OptionType.class));
            in.limit(f.length > OpsForward.MAX_LIST || w.length > OpsForward.MAX_LIST || v.length > OpsForward.MAX_LIST
                    || rho.length > OpsForward.MAX_LIST, "forwards"); // C10 (ruling E-A35)
            in.gate();
            int n = f.length;
            if (n == 0 || w.length != n || v.length != n || rho.length != n) {
                throw new QfError("E_INPUT", "forwards, weights, vols and correlation must match", "forwards");
            }
            for (int i = 0; i < n; i++) {
                if (rho[i].length != n || rho[i][i] != 1.0) {
                    throw new QfError("E_INPUT", "correlation must be square with a unit diagonal", "correlation");
                }
                for (int j = 0; j < n; j++) {
                    if (rho[i][j] != rho[j][i] || !(rho[i][j] >= -1.0 && rho[i][j] <= 1.0)) {
                        throw new QfError("E_INPUT", "correlation must be symmetric, in [-1, 1]", "correlation");
                    }
                }
            }
            double total = 0.0;
            for (int i = 0; i < n; i++) {
                positive(f[i], "forwards");
                if (!(w[i] >= 0.0)) {
                    throw domain("weights");
                }
                total += w[i];
                positive(v[i], "vols");
            }
            if (!(total > 0.0)) {
                throw domain("weights");
            }
            positive(k, "strike");
            positive(t, "expiry_years");
            double[] b = Exotics.basket(phi, f, w, v, rho, k, t, r);
            return Operations.out("price", b[0], "basket_forward", b[1], "basket_vol", b[2]);
        });
        table.put("exotic.american.crr", in -> {
            Common c = Common.read(in, true);
            long steps = in.integer("steps");
            in.limit(steps > 20_000, "steps"); // at the gate (ruling E-A34)
            in.gate();
            c.check();
            if (steps < 1) {
                throw new QfError("E_INPUT", "steps must be at least 1", "steps");
            }
            double[] r = Exotics.crr(c.phi, c.s, c.k, c.t, c.r, c.q, c.v, (int) steps);
            return Operations.out("american", r[0], "european", r[1], "early_exercise_premium", r[0] - r[1]);
        });
        table.put("exotic.american.baw", in -> {
            Common c = in.gate(Common.read(in, true));
            c.check();
            return Operations.out("price", Exotics.baw(c.phi, c.s, c.k, c.t, c.r, c.q, c.v));
        });
        table.put("exotic.american.fd", in -> {
            Common c = Common.read(in, true);
            Exercise e = in.choice("exercise", Exercise.class);
            In g = in.object("grid");
            long nx = g.integer("nx");
            long nt = g.integer("nt");
            double width = g.real("width");
            in.limit(nx > 1001 || nt > 10_000, "grid"); // at the gate (ruling E-A34)
            in.gate();
            c.check();
            if (nx < 5 || nx % 2 == 0 || nt < 1) {
                throw new QfError("E_INPUT", "nx must be odd and at least 5, nt at least 1", "grid");
            }
            positive(width, "width");
            double[] r = Exotics.fd(c.phi, e == Exercise.AMERICAN, c.s, c.k, c.t, c.r, c.q, c.v, (int) nx, (int) nt,
                    width);
            return Operations.out("price", r[0], "delta", r[1], "gamma", r[2]);
        });
    }
}
