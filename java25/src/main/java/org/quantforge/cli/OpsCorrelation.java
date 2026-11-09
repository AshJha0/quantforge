package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.risk.Correlation;

/** Stage E6: correlation (correlation.md). */
final class OpsCorrelation {
    private OpsCorrelation() {}

    private static List<Object> rows(double[][] m) {
        List<Object> out = new ArrayList<>();
        for (double[] r : m) {
            out.add(OpsSmile.list(r));
        }
        return out;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.corr.validate", in -> {
            double[][] m = in.gate(in.anyMatrix("matrix"));
            Correlation.Validation v = Correlation.validate(m);
            return Operations.out("symmetric", v.symmetric(), "unit_diagonal", v.unitDiagonal(), "in_range",
                    v.inRange(), "min_eigenvalue", v.minEigenvalue(), "psd", v.psd(), "valid", v.valid());
        });
        table.put("risk.corr.nearest", in -> {
            double[][] m = in.gate(in.anyMatrix("matrix"));
            Correlation.Nearest r = Correlation.nearest(m);
            return Operations.out("matrix", rows(r.matrix()), "frobenius_distance", r.distance());
        });
        table.put("risk.corr.implied", in -> {
            double[] w = in.reals("weights");
            double[] s = in.reals("vols");
            double si = in.gate(in.real("index_vol"));
            Correlation.checkNames(w.length, s.length);
            // order of ruling E-B39: negative weight, member vols, index_vol, fewer than two positive weights
            Correlation.checkNonNegative(w);
            Correlation.checkPositive("vols", s);
            Correlation.checkPositive("index_vol", si);
            Correlation.checkTwoPositive(w);
            return Operations.out("correlation", Correlation.implied(w, s, si));
        });
        table.put("risk.corr.dispersion", in -> {
            double[] w = in.reals("weights");
            double[] k = in.reals("vol_strikes");
            double ki = in.real("index_vol_strike");
            double[] s = in.reals("realized_vols");
            double si = in.real("index_realized_vol");
            double n = in.gate(in.real("vega_notional"));
            Correlation.checkNames(w.length, k.length, s.length);
            Correlation.checkPositive("vol_strikes", k);
            Correlation.checkPositive("index_vol_strike", ki);
            Correlation.checkPositive("realized_vols", s);
            Correlation.checkPositive("index_realized_vol", si);
            double[] legs = new double[w.length];
            double nI = n / (2.0 * ki);
            double pnl = -nI * (si * si - ki * ki);
            for (int i = 0; i < w.length; i++) {
                legs[i] = n * w[i] / (2.0 * k[i]);
                pnl += legs[i] * (s[i] * s[i] - k[i] * k[i]);
            }
            return Operations.out("pnl", pnl, "implied_correlation", Correlation.implied(w, k, ki),
                    "realized_correlation", Correlation.implied(w, s, si), "constituent_variance_notionals",
                    OpsSmile.list(legs), "index_variance_notional", nI);
        });
    }
}
