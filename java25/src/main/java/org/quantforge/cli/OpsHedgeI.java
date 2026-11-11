package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.hedging.HedgeRatios;
import org.quantforge.hedging.LeastSquaresHedge;

/**
 * Stage I wave 1: the hedge solvers ({@code 08-hedging/hedge-solvers.md}). Inputs are read first (E_SCHEMA), then the
 * size limits of ruling I-4 are raised, then the finite rule F-2, then each operation's own checks.
 */
final class OpsHedgeI {
    private OpsHedgeI() {}

    private static final int MAX_FACTORS = 1_000;
    private static final int MAX_INSTRUMENTS = 200;
    private static final int MAX_EQUALITIES = 200;
    private static final int MAX_INTEGER_INSTRUMENTS = 12;
    private static final int MAX_POSITIONS = 1_000;
    private static final int MAX_GREEK_HEDGES = 3;
    private static final int MAX_FRONTIER_POINTS = 50;

    private enum Singular { ERROR, MIN_NORM }

    private enum Rounding { NEAREST, NONE }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.qp.solve", OpsHedgeI::qp);
        table.put("hedge.integer.solve", OpsHedgeI::integer);
        table.put("hedge.minvar.ratio", OpsHedgeI::minVariance);
        table.put("hedge.greeks.neutralise", OpsHedgeI::greeks);
        table.put("hedge.beta.futures", OpsHedgeI::beta);
        table.put("hedge.residual.report", OpsHedgeI::residual);
        table.put("hedge.frontier.solve", OpsHedgeI::frontier);
    }

    private static int width(double[][] m) {
        int w = 0;
        for (double[] row : m) {
            w = Math.max(w, row.length);
        }
        return w;
    }

    private static void optional(In in, String... keys) {
        for (String k : keys) {
            in.notNull(k);
        }
    }

    /** Null entries become an infinite bound of the given sign; an absent key gives null. */
    private static double[] realBounds(In in, String key, double free) {
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

    private static double[] lotBounds(In in, String key, double free) {
        if (!in.has(key)) {
            return null;
        }
        List<Long> l = in.nullableIntegers(key);
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = l.get(i) == null ? free : l.get(i);
        }
        return out;
    }

    /** The wave 1 inputs of {@code hedge.qp.solve}, shared with {@code hedge.frontier.solve}. */
    private record QpInputs(double[][] a, double[] b, double[] w, double ridge, double[][] eq, double[] eqRhs,
            double[] lower, double[] upper, boolean minNorm) {}

    private static final String[] COST_KEYS = {"half_spreads", "impact", "cost_weight", "margin_rates",
        "margin_limit"};

    private static QpInputs qpInputs(In in) {
        optional(in, "ridge", "eq_matrix", "eq_rhs", "lower", "upper", "singular");
        optional(in, COST_KEYS);
        double[][] a = in.anyMatrix("a");
        double[] b = in.reals("b");
        double[] w = in.reals("weights");
        double ridge = in.real("ridge", 0.0);
        double[][] eq = in.has("eq_matrix") ? in.anyMatrix("eq_matrix") : null;
        double[] eqRhs = in.has("eq_rhs") ? in.reals("eq_rhs") : null;
        double[] lower = realBounds(in, "lower", Double.NEGATIVE_INFINITY);
        double[] upper = realBounds(in, "upper", Double.POSITIVE_INFINITY);
        Singular policy = in.has("singular") ? in.choice("singular", Singular.class) : Singular.ERROR;
        in.limit(a.length > MAX_FACTORS, "a");
        in.limit(width(a) > MAX_INSTRUMENTS, "a");
        in.limit(eq != null && eq.length > MAX_EQUALITIES, "eq_matrix");
        return new QpInputs(a, b, w, ridge, eq, eqRhs, lower, upper, policy == Singular.MIN_NORM);
    }

    /** The wave 4a cost inputs, or null when none is present (ruling I-27). */
    private static LeastSquaresHedge.Costs costs(In in) {
        boolean any = false;
        for (String k : COST_KEYS) {
            any |= in.has(k);
        }
        if (!any) {
            return null;
        }
        return new LeastSquaresHedge.Costs(in.has("half_spreads") ? in.reals("half_spreads") : null,
                in.has("impact") ? in.reals("impact") : null, in.real("cost_weight", 1.0),
                in.has("margin_rates") ? in.reals("margin_rates") : null, in.realOrNull("margin_limit"));
    }

    private static LeastSquaresHedge.Solution solveQp(QpInputs q, LeastSquaresHedge.Costs c) {
        return LeastSquaresHedge.solve(q.a(), q.b(), q.w(), q.ridge(), q.eq(), q.eqRhs(), q.lower(), q.upper(),
                q.minNorm(), c);
    }

    private static Out qp(In in) {
        QpInputs q = qpInputs(in);
        LeastSquaresHedge.Costs c = costs(in);
        in.gate();
        LeastSquaresHedge.Solution s = solveQp(q, c);
        Out out = Operations.out("x", s.x(), "residual", s.residual(), "objective", s.objective(), "rank",
                (long) s.rank());
        if (s.risk() != null) {
            out.outputs().put("risk", s.risk());
            out.outputs().put("cost", s.cost());
            if (s.margin() != null) {
                out.outputs().put("margin", s.margin());
            }
        }
        return out;
    }

    private static Out frontier(In in) {
        QpInputs q = qpInputs(in);
        double[] weights = in.reals("cost_weights");
        LeastSquaresHedge.Costs base = costs(in);
        in.limit(weights.length > MAX_FRONTIER_POINTS, "cost_weights");
        in.gate();
        if (in.has("cost_weight")) {
            throw new QfError("E_INPUT", "cost_weight is set by cost_weights", "cost_weight");
        }
        if (weights.length == 0) {
            throw new QfError("E_INPUT", "cost_weights is empty", "cost_weights");
        }
        for (int i = 1; i < weights.length; i++) {
            if (!(weights[i] > weights[i - 1])) {
                throw new QfError("E_INPUT", "cost_weights must increase strictly", "cost_weights");
            }
        }
        if (base == null || (base.halfSpreads() == null && base.impact() == null)) {
            throw new QfError("E_INPUT", "a frontier needs half_spreads or impact", "half_spreads");
        }
        List<Object> points = new ArrayList<>();
        for (double cw : weights) {
            LeastSquaresHedge.Solution s = solveQp(q, new LeastSquaresHedge.Costs(base.halfSpreads(), base.impact(),
                    cw, base.marginRates(), base.marginLimit()));
            points.add(Operations.out("cost_weight", cw, "x", s.x(), "risk", s.risk(), "cost", s.cost()).outputs());
        }
        return Operations.out("points", points);
    }

    private static Out integer(In in) {
        optional(in, "ridge", "lower_lots", "upper_lots");
        double[][] a = in.anyMatrix("a");
        double[] b = in.reals("b");
        double[] w = in.reals("weights");
        double ridge = in.real("ridge", 0.0);
        double[] lots = in.reals("lot_sizes");
        double[] lower = lotBounds(in, "lower_lots", Double.NEGATIVE_INFINITY);
        double[] upper = lotBounds(in, "upper_lots", Double.POSITIVE_INFINITY);
        in.limit(a.length > MAX_FACTORS, "a");
        in.limit(width(a) > MAX_INTEGER_INSTRUMENTS, "a");
        in.gate();
        LeastSquaresHedge.IntegerSolution s = LeastSquaresHedge.solveLots(a, b, w, ridge, lots, lower, upper);
        List<Long> lotList = new ArrayList<>();
        for (long v : s.lots()) {
            lotList.add(v);
        }
        return Operations.out("lots", lotList, "x", s.x(), "residual", s.residual(), "objective", s.objective(),
                "continuous_objective", s.continuousObjective(), "rounding_cost", s.roundingCost());
    }

    private static Out minVariance(In in) {
        optional(in, "covariance", "exposure_changes", "hedge_changes");
        boolean cov = in.has("covariance");
        boolean exp = in.has("exposure_changes");
        boolean hed = in.has("hedge_changes");
        double[][] s = cov ? in.anyMatrix("covariance") : null;
        double[] e = exp ? in.reals("exposure_changes") : null;
        double[][] h = hed ? in.anyMatrix("hedge_changes") : null;
        in.limit(s != null && s.length > MAX_INSTRUMENTS + 1, "covariance");
        in.limit(h != null && h.length > MAX_INSTRUMENTS, "hedge_changes");
        in.gate();
        if (cov == (exp || hed) || exp != hed) {
            throw new org.quantforge.core.QfError("E_INPUT",
                    "give either covariance or both exposure_changes and hedge_changes", "covariance");
        }
        HedgeRatios.MinVariance r = HedgeRatios.minimumVariance(cov ? s : HedgeRatios.sampleCovariance(e, h));
        return Operations.out("hedge", r.hedge(), "variance_before", r.varianceBefore(), "variance_after",
                r.varianceAfter(), "effectiveness", r.effectiveness());
    }

    private static HedgeRatios.Position position(In p, boolean withQuantity) {
        optional(p, "strike", "expiry_years");
        HedgeRatios.Instrument kind = p.choice("instrument", HedgeRatios.Instrument.class);
        Double strike = p.has("strike") ? p.real("strike") : null;
        Double expiry = p.has("expiry_years") ? p.real("expiry_years") : null;
        double qty = withQuantity ? p.real("quantity") : 0.0;
        return new HedgeRatios.Position(kind, strike, expiry, qty);
    }

    private static Map<String, Object> greekObject(double[] g) {
        return Operations.out("delta", g[0], "gamma", g[1], "vega", g[2]).outputs();
    }

    private static Out greeks(In in) {
        HedgeRatios.Market mk = new HedgeRatios.Market(in.real("spot"), in.real("rate"), in.real("dividend_yield"),
                in.real("volatility"));
        List<In> book = in.objects("portfolio");
        List<In> hedgeIn = in.objects("hedges");
        List<HedgeRatios.Position> positions = new ArrayList<>();
        for (In p : book) {
            positions.add(position(p, true));
        }
        List<HedgeRatios.Position> hedges = new ArrayList<>();
        for (In p : hedgeIn) {
            hedges.add(position(p, false));
        }
        List<HedgeRatios.Greek> targets = new ArrayList<>();
        for (String t : in.strings("targets")) {
            targets.add(In.parseEnum("targets", t, HedgeRatios.Greek.class));
        }
        in.limit(book.size() > MAX_POSITIONS, "portfolio");
        in.limit(hedgeIn.size() > MAX_GREEK_HEDGES, "hedges");
        in.gate();
        HedgeRatios.GreekHedge g = HedgeRatios.neutralise(mk, positions, hedges, targets);
        return Operations.out("quantities", g.quantities(), "greeks_before", greekObject(g.before()),
                "greeks_after", greekObject(g.after()));
    }

    private static Out beta(In in) {
        optional(in, "rounding");
        double v = in.real("portfolio_value");
        double beta = in.real("portfolio_beta");
        double target = in.real("target_beta");
        double f = in.real("futures_price");
        double m = in.real("multiplier");
        Rounding r = in.has("rounding") ? in.choice("rounding", Rounding.class) : Rounding.NEAREST;
        in.gate();
        HedgeRatios.BetaHedge h = HedgeRatios.betaFutures(v, beta, target, f, m, r == Rounding.NEAREST);
        return Operations.out("contracts", h.contracts(), "contracts_held", h.contractsHeld(), "beta_after",
                h.betaAfter());
    }

    private static Out residual(In in) {
        double[][] a = in.anyMatrix("a");
        double[] b = in.reals("b");
        double[] x = in.reals("x");
        double[][] s = in.anyMatrix("covariance");
        in.limit(a.length > MAX_FACTORS, "a");
        in.limit(width(a) > MAX_INSTRUMENTS, "a");
        in.limit(s.length > MAX_FACTORS, "covariance");
        in.gate();
        HedgeRatios.Residual r = HedgeRatios.residualReport(a, b, x, s);
        return Operations.out("residual", r.residual(), "variance_before", r.varianceBefore(), "variance_after",
                r.varianceAfter(), "volatility_after", r.volatilityAfter(), "effectiveness", r.effectiveness(),
                "contributions", r.contributions());
    }
}
