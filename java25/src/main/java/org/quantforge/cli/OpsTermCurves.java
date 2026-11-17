package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.curves.TermCurves;

/** Stage J curves lane (rulings J-C-1 to J-C-9): financing term structure and liquidity curve. */
final class OpsTermCurves {
    private OpsTermCurves() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("repo.term.curve", OpsTermCurves::termCurve);
        table.put("eq.forward.term_financed", OpsTermCurves::forward);
        table.put("liq.curve.cost", OpsTermCurves::liquidity);
    }

    /** Reads the six curve arrays, then gates: call it after reading every other key. */
    private static TermCurves.FinancingCurve curve(In in) {
        double[] ft = in.reals("funding_times");
        double[] fz = in.reals("funding_zero_rates");
        double[] qt = in.reals("quote_times");
        double[] qr = in.reals("repo_rates");
        double[] bt = in.reals("borrow_times");
        double[] bf = in.reals("borrow_fees");
        in.gate();
        return TermCurves.build(ft, fz, qt, qr, bt, bf);
    }

    private static Object listOrNull(double[] x) {
        return x == null ? null : OpsSmile.list(x);
    }

    private static List<Object> rows(double[][] m) {
        List<Object> out = new ArrayList<>();
        for (double[] r : m) {
            out.add(OpsSmile.list(r));
        }
        return out;
    }

    private static Out termCurve(In in) {
        double[] q = in.reals("query_times");
        TermCurves.TermCurve r = TermCurves.termCurve(curve(in), q);
        return Operations.out("pillar_spreads", OpsSmile.list(r.pillarSpreads()), "spread", OpsSmile.list(r.spread()),
                "financing_df", OpsSmile.list(r.financingDf()), "financing_rate", OpsSmile.list(r.financingRate()),
                "forward_financing", OpsSmile.list(r.forwardFinancing()), "borrow_fee", listOrNull(r.borrowFee()));
    }

    private static Out forward(In in) {
        double spot = in.real("spot");
        double t = in.real("maturity_years");
        double[] dt = in.reals("dividend_times");
        double[] da = in.reals("dividend_amounts");
        TermCurves.TermForward r = TermCurves.forward(curve(in), spot, t, dt, da);
        return Operations.out("forward", r.forward(), "carry", r.carry(), "carry_factor", r.carryFactor(),
                "financing_df", r.financingDf(), "pv_dividends", r.pvDividends());
    }

    private static Out liquidity(In in) {
        double hs = in.real("half_spread_bps");
        double v = in.real("daily_volume");
        double sigma = in.real("daily_vol");
        double y = in.real("coefficient", 1.0);
        double d = in.real("exponent", 0.5);
        double z = in.real("risk_multiplier", 0.0);
        double[] q = in.reals("sizes");
        double[] h = in.reals("horizons_days");
        in.gate();
        TermCurves.LiquidityCurve r = TermCurves.liquidity(hs, v, sigma, y, d, z, q, h);
        return Operations.out("spread_cost", r.spreadCost(), "impact", rows(r.impact()), "timing_risk",
                OpsSmile.list(r.timingRisk()), "total_cost", rows(r.totalCost()), "optimal_horizon",
                listOrNull(r.optimalHorizon()), "min_cost", listOrNull(r.minCost()));
    }
}
