package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.hedging.InstrumentSelection;

/** Stage I wave 4c: instrument selection ({@code 08-hedging/instrument-selection.md}), rulings I-33 to I-35. */
final class OpsHedgeSelect {
    private OpsHedgeSelect() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.select.solve", OpsHedgeSelect::select);
    }

    private static double[] bounds(In in, String key, double free) {
        if (!in.has(key)) {
            return null;
        }
        List<Double> l = in.nullableReals(key);
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = l.get(i) == null ? free : l.get(i);
        }
        return out;
    }

    private static Out select(In in) {
        for (String k : new String[] {"ridge", "lower", "upper"}) {
            in.notNull(k);
        }
        double[][] a = in.anyMatrix("a");
        double[] b = in.reals("b");
        double[] w = in.reals("weights");
        double ridge = in.real("ridge", 0.0);
        double[] lower = bounds(in, "lower", Double.NEGATIVE_INFINITY);
        double[] upper = bounds(in, "upper", Double.POSITIVE_INFINITY);
        long k = in.integer("max_instruments");
        boolean extra = in.hasKey("eq_matrix") || in.hasKey("eq_rhs") || in.hasKey("singular");
        int width = 0;
        for (double[] row : a) {
            width = Math.max(width, row.length);
        }
        in.limit(width > InstrumentSelection.MAX_INSTRUMENTS, "a");
        in.limit(a.length > 1_000, "a");
        in.gate();
        InstrumentSelection.Selection s = InstrumentSelection.select(a, b, w, ridge, lower, upper, k, extra);
        List<Long> selected = new ArrayList<>();
        for (int i : s.selected()) {
            selected.add((long) i);
        }
        return Operations.out("selected", selected, "x", s.x(), "residual", s.residual(), "objective",
                s.objective());
    }
}
