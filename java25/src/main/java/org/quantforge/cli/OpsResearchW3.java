package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Interpolation.Method;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/** Stage J wave 3 (rulings J-W3-1 to J-W3-14): scenario stress, interpolation backtests, drift detectors. */
final class OpsResearchW3 {
    private static final int GENERIC = 100_000;

    private OpsResearchW3() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.scenario.historical_shock", OpsResearchW3::historicalShock);
        table.put("risk.scenario.replay", OpsResearchW3::replay);
        table.put("research.backtest.interp_loo", OpsResearchW3::interpLoo);
        table.put("research.backtest.surface_holdout", OpsResearchW3::surfaceHoldout);
        table.put("research.drift.cusum", OpsResearchW3::cusum);
        table.put("research.drift.page_hinkley", OpsResearchW3::pageHinkley);
        table.put("research.drift.psi", OpsResearchW3::psi);
        table.put("research.drift.ks", OpsResearchW3::ks);
    }

    private static List<Object> rows(double[][] m) {
        List<Object> out = new ArrayList<>();
        for (double[] r : m) {
            out.add(OpsSmile.list(r));
        }
        return out;
    }

    private static List<Object> longs(long[] x) {
        List<Object> out = new ArrayList<>();
        for (long v : x) {
            out.add(v);
        }
        return out;
    }

    private static boolean widerThan(double[][] m, int max) {
        boolean over = m.length > max;
        for (double[] r : m) {
            over |= r.length > max;
        }
        return over;
    }

    private static Method method(In in, boolean surface) {
        String s = in.string("method");
        return switch (s) {
            case "linear" -> Method.LINEAR;
            case "log_linear" -> {
                if (surface) {
                    throw new QfError("E_SCHEMA", "unknown method", "method");
                }
                yield Method.LOG_LINEAR;
            }
            case "cubic_natural" -> Method.CUBIC_NATURAL;
            case "monotone_pchip" -> Method.MONOTONE_PCHIP;
            default -> throw new QfError("E_SCHEMA", "unknown method", "method");
        };
    }

    private static Out historicalShock(In in) {
        var dates = in.dates("dates");
        double[] t = in.reals("tenors");
        double[][] y = in.anyMatrix("yields");
        var start = in.date("start_date");
        var end = in.date("end_date");
        in.limit(dates.size() > GENERIC, "dates");
        in.limit(t.length > 100, "tenors");
        boolean wide = y.length > GENERIC;
        for (double[] r : y) {
            wide |= r.length > 100;
        }
        in.limit(wide, "yields");
        in.gate();
        StressDrift.Shock r = StressDrift.historicalShock(dates, t, y, start, end);
        return Operations.out("start_yields", OpsSmile.list(r.startYields()), "end_yields",
                OpsSmile.list(r.endYields()), "shift_bp", OpsSmile.list(r.shiftBp()), "level_bp", r.levelBp(),
                "slope_bp", r.slopeBp());
    }

    private static Out replay(In in) {
        double[] bt = in.reals("base_tenors");
        double[] by = in.reals("base_yields");
        double[] st = in.reals("shock_tenors");
        double[] sb = in.reals("shock_bp");
        double scale = in.real("scale", 1.0);
        double[] dv01 = in.has("dv01") ? in.reals("dv01") : null;
        in.limit(bt.length > 100, "base_tenors");
        in.limit(by.length > 100, "base_yields");
        in.limit(st.length > 100, "shock_tenors");
        in.limit(sb.length > 100, "shock_bp");
        in.limit(dv01 != null && dv01.length > 100, "dv01");
        in.gate();
        StressDrift.Replay r = StressDrift.replay(bt, by, st, sb, scale, dv01);
        if (r.pnl() == null) {
            return Operations.out("applied_bp", OpsSmile.list(r.appliedBp()), "shocked_yields",
                    OpsSmile.list(r.shockedYields()));
        }
        return Operations.out("applied_bp", OpsSmile.list(r.appliedBp()), "shocked_yields",
                OpsSmile.list(r.shockedYields()), "pnl", r.pnl());
    }

    private static Out interpLoo(In in) {
        Method m = method(in, false);
        double[] x = in.reals("x");
        double[] y = in.reals("y");
        in.limit(x.length > 10_000, "x");
        in.limit(y.length > 10_000, "y");
        in.gate();
        StressDrift.LooResult r = StressDrift.interpLoo(m, x, y);
        return Operations.out("errors", OpsSmile.list(r.errors()), "max_abs_error", r.maxAbsError(), "rmse",
                r.rmse());
    }

    private static Out surfaceHoldout(In in) {
        Method m = method(in, true);
        double[] e = in.reals("expiries");
        double[] k = in.reals("strikes");
        double[][] v = in.anyMatrix("vols");
        long[] h = in.integers("holdout");
        in.limit(e.length > 1_000, "expiries");
        in.limit(k.length > 1_000, "strikes");
        in.limit(widerThan(v, 1_000), "vols");
        in.limit(h.length > 1_000, "holdout");
        in.gate();
        StressDrift.SurfaceResult r = StressDrift.surfaceHoldout(m, e, k, v, h);
        return Operations.out("errors", rows(r.errors()), "max_abs_error", r.maxAbsError(), "rmse", r.rmse());
    }

    private static Out cusum(In in) {
        double[] x = in.reals("x");
        double k = in.real("k");
        double h = in.real("h");
        double mu0 = in.real("mu0", 0.0);
        double sigma = in.real("sigma", 1.0);
        boolean reset = in.bool("reset", true);
        in.limit(x.length > 10_000_000, "x");
        in.gate();
        StressDrift.Alarms a = StressDrift.cusum(x, k, h, mu0, sigma, reset);
        return Operations.out("alarms", longs(a.alarms()), "directions", longs(a.directions()), "s_plus", a.sPlus(),
                "s_minus", a.sMinus());
    }

    private static Out pageHinkley(In in) {
        double[] x = in.reals("x");
        double delta = in.real("delta");
        double lambda = in.real("lambda");
        String dir = "both";
        if (in.has("direction")) {
            dir = in.string("direction");
            if (!dir.equals("up") && !dir.equals("down") && !dir.equals("both")) {
                throw new QfError("E_SCHEMA", "direction must be up, down or both", "direction");
            }
        }
        boolean reset = in.bool("reset", true);
        in.limit(x.length > 10_000_000, "x");
        in.gate();
        StressDrift.Alarms a = StressDrift.pageHinkley(x, delta, lambda, dir, reset);
        return Operations.out("alarms", longs(a.alarms()), "directions", longs(a.directions()));
    }

    private static Out psi(In in) {
        double[] r = in.reals("reference");
        double[] t = in.reals("test");
        long bins = in.integer("bins", 10);
        double th = in.real("threshold", 0.25);
        in.limit(r.length > 1_000_000, "reference");
        in.limit(t.length > 1_000_000, "test");
        in.limit(bins > 1_000, "bins");
        in.gate();
        StressDrift.Psi p = StressDrift.psi(r, t, bins, th);
        return Operations.out("psi", p.psi(), "reference_shares", OpsSmile.list(p.referenceShares()), "test_shares",
                OpsSmile.list(p.testShares()), "alarm", p.alarm());
    }

    private static Out ks(In in) {
        double[] a = in.reals("a");
        double[] b = in.reals("b");
        double level = in.real("level", 0.05);
        in.limit(a.length > 1_000_000, "a");
        in.limit(b.length > 1_000_000, "b");
        in.limit(In.productOver(a.length, b.length, 4_000_000L), "b");
        in.gate();
        StressDrift.Ks r = StressDrift.ks(a, b, level);
        return Operations.out("statistic", r.statistic(), "p_value", r.pValue(), "reject", r.reject());
    }
}
