package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.execution.AdaptiveExec;
import org.quantforge.execution.Execution;
import org.quantforge.execution.Execution.Mode;

/** Stage H wave 1 (rulings HR-1 to HR-10): execution schedules, Almgren-Chriss, impact, TCA and A-S quotes. */
final class OpsExecution {
    private OpsExecution() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("exec.schedule.twap", OpsExecution::twap);
        table.put("exec.schedule.vwap", OpsExecution::vwap);
        table.put("exec.schedule.pov", OpsExecution::pov);
        table.put("exec.ac.trajectory", OpsExecution::trajectory);
        table.put("exec.ac.frontier", OpsExecution::frontier);
        table.put("exec.impact.sqrt", OpsExecution::sqrt);
        table.put("exec.impact.ow_optimal", OpsExecution::owOptimal);
        table.put("exec.tca.shortfall", OpsExecution::shortfall);
        table.put("micro.mm.as_quotes", OpsExecution::asQuotes);
        table.put("usecase.execution_tca", OpsExecution::executionTca);
        // Stage H wave 2 execution (HR-59 to HR-67): adaptive-algos.md and tca-pretrade.md
        table.put("exec.algo.arrival", OpsExecution::arrival);
        table.put("exec.algo.close", OpsExecution::close);
        table.put("exec.algo.liquidity_seek", OpsExecution::liquiditySeek);
        table.put("exec.algo.pair", OpsExecution::pair);
        table.put("exec.algo.basket", OpsExecution::basket);
        table.put("exec.tca.pretrade", OpsExecution::pretrade);
        table.put("exec.tca.attribution", OpsExecution::attribution);
    }

    /** HR-3: UNITS slices are written as JSON integers, CONTINUOUS slices as reals. */
    private static List<Object> slices(double[] s, Mode mode) {
        if (mode == Mode.CONTINUOUS) {
            return OpsSmile.list(s);
        }
        List<Object> out = new ArrayList<>(s.length);
        for (double x : s) {
            out.add((long) x);
        }
        return out;
    }

    private static Object amount(double x, Mode mode) {
        return mode == Mode.UNITS ? (Object) (long) x : (Object) x;
    }

    /** `mode` absent means CONTINUOUS (ruling HR-56). */
    private static Mode mode(In in) {
        return in.gate(in.has("mode") ? in.choice("mode", Mode.class) : Mode.CONTINUOUS);
    }

    private static Out twap(In in) {
        double x = in.real("quantity");
        long n = in.atMost("n_buckets", Execution.MAX_STEPS);
        Mode mode = mode(in);
        return Operations.out("slices", slices(Execution.twap(x, n, mode), mode));
    }

    private static Out vwap(In in) {
        double x = in.real("quantity");
        double[] profile = in.reals("profile");
        Mode mode = mode(in);
        return Operations.out("slices", slices(Execution.vwap(x, profile, mode), mode));
    }

    private static Out pov(In in) {
        double x = in.real("quantity");
        double p = in.real("participation");
        double[] v = in.reals("market_volume");
        Mode mode = mode(in);
        Execution.Pov r = Execution.pov(x, p, v, mode);
        return Operations.out("slices", slices(r.slices(), mode), "filled", amount(r.filled(), mode), "residual",
                amount(r.residual(), mode));
    }

    private static Execution.AcParams acParams(In in) {
        double x = in.real("quantity");
        double t = in.real("horizon");
        long n = in.atMost("n_steps", Execution.MAX_STEPS);
        double sigma = in.real("sigma");
        double eps = in.real("epsilon");
        double eta = in.real("eta");
        double gamma = in.real("gamma");
        return new Execution.AcParams(x, t, n, sigma, eps, eta, gamma);
    }

    private static Out trajectory(In in) {
        Execution.AcParams p = acParams(in);
        double lambda = in.gate(in.real("risk_aversion"));
        Execution.AcTrajectory r = Execution.acTrajectory(p, lambda);
        return Operations.out("holdings", OpsSmile.list(r.holdings()), "trades", OpsSmile.list(r.trades()), "kappa",
                r.kappa(), "expected_cost", r.expectedCost(), "variance", r.variance(), "objective", r.objective());
    }

    private static Out frontier(In in) {
        Execution.AcParams p = acParams(in);
        double[] lambdas = in.gate(in.reals("risk_aversions"));
        Execution.AcFrontier r = Execution.acFrontier(p, lambdas);
        return Operations.out("risk_aversions", OpsSmile.list(r.riskAversions()), "expected_costs",
                OpsSmile.list(r.expectedCost()), "variances", OpsSmile.list(r.variance()));
    }

    private static Out sqrt(In in) {
        double q = in.real("quantity");
        double v = in.real("daily_volume");
        double sigma = in.real("daily_vol");
        double y = in.gate(in.real("coefficient", 1.0));
        return Operations.out("impact", Execution.impactSqrt(q, v, sigma, y), "model", Execution.ASSUMED);
    }

    private static Out owOptimal(In in) {
        double x = in.real("quantity");
        double t = in.real("horizon");
        double rho = in.gate(in.real("resilience"));
        Execution.OwOptimal r = Execution.owOptimal(x, t, rho);
        return Operations.out("initial_block", r.initialBlock(), "rate", r.rate(), "final_block", r.finalBlock());
    }

    private static Out shortfall(In in) {
        Execution.Side side = in.choice("side", Execution.Side.class);
        double pd = in.real("decision_price");
        double p0 = in.real("arrival_price");
        double pc = in.real("end_price");
        double x = in.real("order_quantity");
        List<In> fills = in.objects("fills");
        double[] q = new double[fills.size()];
        double[] px = new double[fills.size()];
        for (int i = 0; i < q.length; i++) {
            q[i] = fills.get(i).real("quantity");
            px[i] = fills.get(i).real("price");
        }
        double fees = in.real("fees");
        Double vwap = in.realOrNull("benchmark_vwap");
        in.limit(fills.size() > Execution.MAX_FILLS, "fills"); // HR-9
        in.gate();
        Execution.Shortfall r = Execution.shortfall(side, pd, p0, pc, x, q, px, fees, vwap);
        Map<String, Object> m = new LinkedHashMap<>(Operations.out("delay", r.delay(), "execution", r.execution(),
                "opportunity", r.opportunity(), "total", r.total(), "total_bps", r.totalBps()).outputs());
        if (r.vwapSlippage() != null) {
            m.put("vwap_slippage", r.vwapSlippage());
        }
        return new Out(m, Map.of());
    }

    private static Out asQuotes(In in) {
        double s = in.real("mid");
        double q = in.real("inventory");
        double gamma = in.real("risk_aversion");
        double sigma = in.real("sigma");
        double tl = in.real("time_left");
        double k = in.gate(in.real("k"));
        Execution.Quotes r = Execution.asQuotes(s, q, gamma, sigma, tl, k);
        return Operations.out("reservation", r.reservation(), "spread", r.spread(), "bid", r.bid(), "ask", r.ask());
    }

    private static Out executionTca(In in) {
        Execution.AcParams p = acParams(in);
        double lambda = in.real("risk_aversion");
        Execution.Side side = in.choice("side", Execution.Side.class);
        double pd = in.real("decision_price");
        double p0 = in.real("arrival_price");
        double pc = in.real("end_price");
        double[] fp = in.reals("fill_prices");
        long done = in.integer("completed_steps");
        double fee = in.gate(in.real("fee_per_unit"));
        Execution.ExecutionTca r = Execution.executionTca(p, lambda, side, pd, p0, pc, fp, done, fee);
        Execution.Shortfall s = r.shortfall();
        return Operations.out("lots", slices(r.lots(), Mode.UNITS), "expected_cost", r.expectedCost(), "variance",
                r.variance(), "filled", (long) r.filled(), "fees", r.fees(), "delay", s.delay(), "execution",
                s.execution(), "opportunity", s.opportunity(), "total", s.total(), "total_bps", s.totalBps());
    }

    // ---- Stage H wave 2 execution ----

    private static Out arrival(In in) {
        double x = in.real("quantity");
        long n = in.atMost("n_buckets", Execution.MAX_STEPS);
        double k = in.real("urgency");
        Mode mode = mode(in);
        return Operations.out("slices", slices(AdaptiveExec.arrival(x, n, k, mode), mode));
    }

    private static Out close(In in) {
        double x = in.real("quantity");
        double v = in.real("close_volume");
        double p = in.real("auction_participation");
        double[] w = in.reals("profile");
        Mode mode = mode(in);
        AdaptiveExec.Close r = AdaptiveExec.close(x, v, p, w, mode);
        return Operations.out("auction_quantity", amount(r.auctionQuantity(), mode), "slices",
                slices(r.slices(), mode));
    }

    private static Out liquiditySeek(In in) {
        Execution.Side side = in.choice("side", Execution.Side.class);
        double x = in.real("quantity");
        double lim = in.real("limit_price");
        double a = in.real("take_fraction");
        double[][][] books = in.gate(in.tuples("books", 2));
        AdaptiveExec.Seek r = AdaptiveExec.liquiditySeek(side, x, lim, a, books);
        return Operations.out("slices", OpsSmile.list(r.slices()), "avg_prices",
                new ArrayList<Object>(java.util.Arrays.asList((Object[]) r.avgPrices())), "filled", r.filled(),
                "residual", r.residual(), "notional", r.notional(), "avg_fill_price", r.avgFillPrice());
    }

    private static Out pair(In in) {
        In a = in.object("leg_a");
        Execution.Side sa = a.choice("side", Execution.Side.class);
        double qa = a.real("quantity");
        double pa = a.real("price");
        In b = in.object("leg_b");
        Execution.Side sb = b.choice("side", Execution.Side.class);
        double pb = b.real("price");
        AdaptiveExec.PairMode pm = in.choice("pair_mode", AdaptiveExec.PairMode.class);
        Double h = in.has("hedge_ratio") ? in.real("hedge_ratio") : null;
        long n = in.atMost("n_buckets", Execution.MAX_STEPS);
        Mode mode = mode(in);
        AdaptiveExec.Pair r = AdaptiveExec.pair(sa, qa, pa, sb, pb, pm, h, n, mode);
        return Operations.out("slices_a", slices(r.slicesA(), mode), "slices_b", slices(r.slicesB(), mode),
                "quantity_b", amount(r.quantityB(), mode), "cash_imbalance", OpsSmile.list(r.cashImbalance()));
    }

    private static Out basket(In in) {
        List<In> raw = in.objects("legs");
        AdaptiveExec.Leg[] legs = new AdaptiveExec.Leg[raw.size()];
        for (int k = 0; k < legs.length; k++) {
            In g = raw.get(k);
            legs[k] = new AdaptiveExec.Leg(g.choice("side", Execution.Side.class), g.real("quantity"),
                    g.real("price"));
        }
        long n = in.atMost("n_buckets", Execution.MAX_STEPS);
        Mode mode = mode(in);
        AdaptiveExec.Basket r = AdaptiveExec.basket(legs, n, mode);
        List<Object> s = new ArrayList<>(legs.length);
        for (double[] leg : r.slices()) {
            s.add(slices(leg, mode));
        }
        return Operations.out("slices", s, "cash_imbalance", OpsSmile.list(r.cashImbalance()), "gross_notional",
                r.grossNotional());
    }

    private static Out pretrade(In in) {
        double x = in.real("quantity");
        double adv = in.real("adv");
        double sigma = in.real("daily_vol");
        double p = in.real("participation");
        double hs = in.real("half_spread_bps");
        In k = in.object("params");
        double a1 = k.real("a1");
        double a2 = k.real("a2");
        double a3 = k.real("a3");
        double a4 = k.real("a4");
        double b1 = k.real("b1");
        Double price = in.has("price") ? in.real("price") : null;
        in.gate();
        AdaptiveExec.Pretrade r = AdaptiveExec.pretrade(x, adv, sigma, p, hs, a1, a2, a3, a4, b1, price);
        Map<String, Object> m = new LinkedHashMap<>(Operations.out("istar_bps", r.istarBps(), "impact_bps",
                r.impactBps(), "spread_bps", r.spreadBps(), "expected_cost_bps", r.expectedCostBps(), "duration_days",
                r.durationDays(), "timing_risk_bps", r.timingRiskBps()).outputs());
        if (price != null) {
            m.put("expected_cost", r.expectedCost());
            m.put("timing_risk", r.timingRisk());
        }
        return new Out(m, Map.of());
    }

    private static Out attribution(In in) {
        Execution.Side side = in.choice("side", Execution.Side.class);
        double pd = in.real("decision_price");
        double m0 = in.real("arrival_mid");
        double pc = in.real("end_price");
        double x = in.real("order_quantity");
        List<In> fills = in.objects("fills");
        double[] q = new double[fills.size()];
        double[] px = new double[fills.size()];
        double[] mid = new double[fills.size()];
        for (int i = 0; i < q.length; i++) {
            q[i] = fills.get(i).real("quantity");
            px[i] = fills.get(i).real("price");
            mid[i] = fills.get(i).real("mid");
        }
        double fees = in.real("fees", 0.0);
        in.limit(fills.size() > Execution.MAX_FILLS, "fills"); // HR-9
        in.gate();
        AdaptiveExec.Attribution r = AdaptiveExec.attribution(side, pd, m0, pc, x, q, px, mid, fees);
        return Operations.out("delay", r.delay(), "impact", r.impact(), "spread", r.spread(), "execution",
                r.execution(), "opportunity", r.opportunity(), "fees", r.fees(), "total", r.total(), "total_bps",
                r.totalBps());
    }
}
