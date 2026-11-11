package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.hedging.DynamicHedge;

/**
 * Stage I wave 4b: the delta-hedge backtest and hedge effectiveness
 * ({@code 08-hedging/dynamic-hedge-and-effectiveness.md}). Series up to 100,000 values (ruling I-32) are bounded by
 * the general array limit of {@link In}.
 */
final class OpsHedgeDynamic {
    private OpsHedgeDynamic() {}

    private enum OptionType { CALL, PUT }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.backtest.delta", OpsHedgeDynamic::backtest);
        table.put("hedge.effectiveness", OpsHedgeDynamic::effectiveness);
    }

    private static Object[] stats(DynamicHedge.Effectiveness e) {
        return new Object[] {"dollar_offset", e.dollarOffset(), "regression_slope", e.regressionSlope(),
            "regression_r2", e.regressionR2(), "variance_reduction", e.varianceReduction()};
    }

    private static Out effectiveness(In in) {
        double[] x = in.reals("item_changes");
        double[] y = in.reals("hedge_changes");
        in.gate();
        return Operations.out(stats(DynamicHedge.effectiveness(x, y)));
    }

    private static Out backtest(In in) {
        In option = in.object("option");
        OptionType type = option.choice("type", OptionType.class);
        double strike = option.real("strike");
        double expiry = option.real("expiry_years");
        double quantity = in.real("quantity");
        double rate = in.real("rate");
        double q = in.real("dividend_yield");
        double vol = in.real("hedge_volatility");
        double[] times = in.reals("times");
        double[] spots = in.reals("spots");
        in.gate();
        DynamicHedge.Backtest b = DynamicHedge.backtest(type == OptionType.CALL, strike, expiry, quantity, rate, q,
                vol, times, spots);
        Out out = Operations.out("option_values", b.optionValues(), "shares", b.shares(), "portfolio_values",
                b.portfolioValues(), "final_pnl", b.finalPnl());
        out.outputs().putAll(Operations.out(stats(b.effectiveness())).outputs());
        return out;
    }
}
