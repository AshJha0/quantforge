package org.quantforge.cli;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.risk.PortfolioRisk;

/** Stage F slices F3 and F4: book sensitivities, curve risk, VaR/ES, backtests, FRTB. Inputs read before the gate. */
final class OpsRiskF {
    private OpsRiskF() {}

    private static Map<String, Object> varEs(PortfolioRisk.VarEs r) {
        return Operations.out("var", r.var(), "es", r.es(), "tail_count", r.tailCount()).outputs();
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.var.historical", in -> {
            double[] pnl = in.reals("pnl");
            double c = in.gate(in.real("confidence"));
            return new Out(varEs(PortfolioRisk.historical(pnl, c)), Map.of());
        });
        table.put("risk.var.filtered_historical", in -> {
            double[] r = in.reals("returns");
            double p = in.real("position_value");
            double lambda = in.real("lambda");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.VarEs v = PortfolioRisk.filtered(r, p, lambda, c);
            return Operations.out("var", v.var(), "es", v.es(), "tail_count", v.tailCount(),
                    "sigma_next", v.sigmaNext());
        });
        table.put("risk.var.parametric", in -> {
            double mu = in.real("mean");
            double s = in.real("std");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.VarEs v = PortfolioRisk.parametric(mu, s, c);
            return Operations.out("var", v.var(), "es", v.es());
        });
        table.put("risk.var.monte_carlo", in -> {
            double[] mean = in.reals("mean");
            double[][] cov = in.anyMatrix("covariance");
            double[] w = in.reals("weights");
            long paths = in.integer("paths");
            in.limit(paths > 10_000_000, "paths");
            long seed = in.integer("seed");
            double c = in.gate(in.real("confidence"));
            return new Out(varEs(PortfolioRisk.monteCarlo(mean, cov, w, paths, seed, c)), Map.of());
        });
        table.put("risk.backtest.kupiec", in -> {
            long n = in.integer("observations");
            long x = in.integer("exceptions");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.Kupiec k = PortfolioRisk.kupiec(n, x, c);
            return Operations.out("lr_uc", k.lr(), "p_value", k.pValue());
        });
        table.put("risk.backtest.christoffersen", in -> {
            List<?> raw = in.anyValue("exceptions") instanceof List<?> l ? l : null;
            boolean[] e = bools(in, raw);
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.Christoffersen r = PortfolioRisk.christoffersen(e, c);
            return Operations.out("lr_uc", r.lrUc(), "lr_ind", r.lrInd(), "lr_cc", r.lrCc(), "p_uc", r.pUc(),
                    "p_ind", r.pInd(), "p_cc", r.pCc(), "transitions", Operations.out("n00", r.n00(), "n01", r.n01(),
                            "n10", r.n10(), "n11", r.n11()).outputs());
        });
        table.put("risk.backtest.traffic_light", in -> {
            long n = in.integer("observations");
            long x = in.integer("exceptions");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.TrafficLight t = PortfolioRisk.trafficLight(n, x, c);
            return Operations.out("cumulative_probability", t.cumulative(), "zone", t.zone(),
                    "plus_factor", t.plusFactor());
        });
    }

    private static boolean[] bools(In in, List<?> raw) {
        if (raw == null) {
            throw new org.quantforge.core.QfError("E_SCHEMA", "exceptions must be an array of booleans", "exceptions");
        }
        boolean[] e = new boolean[raw.size()];
        for (int i = 0; i < e.length; i++) {
            if (!(raw.get(i) instanceof Boolean b)) {
                throw new org.quantforge.core.QfError("E_SCHEMA", "exceptions must be booleans", "exceptions");
            }
            e[i] = b;
        }
        return e;
    }
}
