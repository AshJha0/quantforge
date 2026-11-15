package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.research.Research;

/** Stage J wave 1: backtester, purged CV, Viterbi regimes, research statistics (11-research/, rulings J-1 to J-19). */
final class OpsResearch {
    private OpsResearch() {}

    private static List<Object> longs(long[] x) {
        List<Object> out = new ArrayList<>();
        for (long v : x) {
            out.add(v);
        }
        return out;
    }

    private static QfError input(String why) {
        return new QfError("E_INPUT", why);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("research.backtest.run", OpsResearch::backtest);
        table.put("research.cv.purged_kfold", OpsResearch::purgedKFold);
        table.put("research.cv.cpcv_paths", in -> {
            long[] r = Research.cpcv(in.integer("n_groups"), in.gate(in.integer("n_test_groups")));
            return Operations.out("n_splits", r[0], "n_paths", r[1]);
        });
        table.put("research.regime.viterbi", OpsResearch::viterbi);
        table.put("research.stats.psr", in -> {
            double[] r = Research.psr(in.real("sr"), in.integer("n_obs"), in.real("skew", 0.0),
                    in.real("kurtosis", 3.0), in.gate(in.real("sr_benchmark", 0.0)));
            return Operations.out("z", r[0], "psr", r[1]);
        });
        table.put("research.stats.dsr", in -> {
            double[] r = Research.dsr(in.real("sr"), in.integer("n_obs"), in.real("skew", 0.0),
                    in.real("kurtosis", 3.0), in.integer("n_trials"), in.gate(in.real("sr_variance")));
            return Operations.out("sr0", r[0], "z", r[1], "dsr", r[2]);
        });
        table.put("research.stats.power", in -> {
            double years = in.real("years");
            double alpha = in.real("alpha", 0.05);
            double power = in.real("power", 0.8);
            Double target = in.gate(in.realOrNull("sr_target"));
            double[] r = Research.power(years, alpha, power, target);
            Out o = Operations.out("z_sum", r[0], "mds", r[1], "se_at_zero", r[2]);
            if (r.length == 5) {
                Map<String, Object> m = new LinkedHashMap<>(o.outputs());
                m.put("years_required", r[3]);
                m.put("se_at_target", r[4]);
                return new Out(m, Map.of());
            }
            return o;
        });
        table.put("research.stats.pbo", OpsResearch::pbo);
        OpsResearchW2.register(table);
        OpsTermCurves.register(table);
        OpsResearchW3.register(table);
    }

    private static Out backtest(In in) {
        Research.Engine engine = in.has("engine") ? in.choice("engine", Research.Engine.class) : Research.Engine.EVENT;
        double[] prices = in.reals("prices");
        double[] targets = in.reals("targets");
        long lag = in.integer("lag", 1);
        double hs = in.real("half_spread_bps", 0.0);
        double comm = in.real("commission_per_unit", 0.0);
        double fixed = in.real("fixed_per_trade", 0.0);
        double m = in.real("multiplier", 1.0);
        in.limit(prices.length > 1_000_000 || targets.length > 1_000_000, "prices");
        in.gate();
        Research.checkBacktest(prices, targets, lag, hs, comm, fixed, m);
        Research.Backtest b = Research.backtest(prices, targets, (int) lag, hs, comm, fixed, m, engine);
        return Operations.out("positions", OpsSmile.list(b.positions()), "trades", OpsSmile.list(b.trades()),
                "pnl_gross", OpsSmile.list(b.gross()), "cost", OpsSmile.list(b.cost()), "pnl_net",
                OpsSmile.list(b.net()), "equity", OpsSmile.list(b.equity()), "total_gross", b.totalGross(),
                "total_spread_cost", b.totalSpread(), "total_commission", b.totalCommission(), "total_fixed_cost",
                b.totalFixed(), "total_net", b.totalNet(), "turnover", b.turnover(), "trade_count", b.tradeCount(),
                "max_drawdown", b.maxDrawdown());
    }

    private static Out purgedKFold(In in) {
        double[] t0 = in.reals("t0");
        double[] t1 = in.reals("t1");
        long k = in.integer("n_splits");
        double pct = in.real("embargo_pct", 0.0);
        in.limit(t0.length > 1_000_000 || t1.length > 1_000_000, "t0");
        in.gate();
        Research.PurgedKFold r = Research.purgedKFold(t0, t1, k, pct);
        List<Object> folds = new ArrayList<>();
        for (Research.Fold f : r.folds()) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("test", f.test());
            m.put("train", f.train());
            folds.add(m);
        }
        return Operations.out("folds", folds, "embargo_count", r.embargoCount());
    }

    private static Out viterbi(In in) {
        double[] initial = in.reals("initial");
        double[][] transition = in.anyMatrix("transition");
        boolean direct = in.has("emission");
        boolean gauss = in.has("observations") || in.has("means") || in.has("sds");
        double[][] emission = direct ? in.anyMatrix("emission") : null;
        double[] y = in.has("observations") ? in.reals("observations") : null;
        double[] means = in.has("means") ? in.reals("means") : null;
        double[] sds = in.has("sds") ? in.reals("sds") : null;
        int k = initial.length;
        int steps = direct ? emission.length : y == null ? 0 : y.length;
        in.limit(steps > 100_000, "observations");
        in.limit(k > 32, "initial");
        in.gate();
        if (direct == gauss || k < 1 || transition.length != k) {
            throw input("exactly one emission form and K x K transition required");
        }
        for (double[] r : transition) {
            if (r.length != k) {
                throw input("transition must be K x K");
            }
        }
        if (direct) {
            if (emission.length < 1) {
                throw input("no observations");
            }
            for (double[] r : emission) {
                if (r.length != k) {
                    throw input("emission must be T x K");
                }
            }
        } else if (y == null || means == null || sds == null || y.length < 1 || means.length != k
                || sds.length != k) {
            throw input("observations, means and sds required with K entries");
        }
        Research.checkModel(initial, transition);
        double[][] logE = direct ? Research.logEmission(emission) : Research.gaussianLogEmission(y, means, sds);
        Research.Viterbi v = Research.viterbi(initial, transition, logE);
        return Operations.out("states", longs(v.states()), "log_probability", v.logProbability());
    }

    private static Out pbo(In in) {
        Research.Metric metric = in.has("metric") ? in.choice("metric", Research.Metric.class)
                : Research.Metric.SHARPE;
        double[][] perf = in.anyMatrix("performance");
        long s = in.integer("n_partitions");
        in.limit(s > 16, "n_partitions");
        long cells = 0;
        int widest = 0;
        for (double[] r : perf) {
            cells += r.length;
            widest = Math.max(widest, r.length);
        }
        in.limit(cells > 10_000_000L || widest > 10_000, "performance");
        in.gate();
        Research.checkPboShape(perf, s);
        Research.Pbo r = Research.pbo(perf, (int) s, metric);
        return Operations.out("pbo", r.pbo(), "logits", OpsSmile.list(r.logits()), "n_combinations",
                r.combinations());
    }
}
