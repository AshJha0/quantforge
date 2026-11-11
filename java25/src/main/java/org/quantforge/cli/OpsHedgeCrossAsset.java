package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.hedging.CrossAssetHedge;

/**
 * Stage I wave 3: the equity and rates cross-asset hedge ({@code 08-hedging/cross-asset-hedge.md}). Inputs are read
 * first (E_SCHEMA), then the size limits of ruling I-23, then the finite rule F-2, then the operation's own checks.
 */
final class OpsHedgeCrossAsset {
    private OpsHedgeCrossAsset() {}

    private static final int MAX_BOOK = 1_000;
    private static final int MAX_HEDGES = 200;
    private static final int MAX_PILLARS = 100;
    private static final Set<String> NUMERIC_KEYS = Set.of("strike", "expiry_years", "notional", "quantity");

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.crossasset.solve", OpsHedgeCrossAsset::solve);
    }

    private static CrossAssetHedge.Instrument instrument(In p) {
        CrossAssetHedge.Kind kind = p.choice("instrument", CrossAssetHedge.Kind.class);
        Map<String, Double> values = new LinkedHashMap<>();
        boolean unknown = false;
        for (String k : p.keys()) {
            if (k.equals("instrument")) {
                continue;
            }
            if (NUMERIC_KEYS.contains(k)) {
                values.put(k, p.real(k));
            } else {
                unknown = true;
            }
        }
        return new CrossAssetHedge.Instrument(kind, values, unknown);
    }

    private static Out solve(In in) {
        in.notNull("ridge");
        double spot = in.real("spot");
        double q = in.real("dividend_yield");
        double vol = in.real("volatility");
        In curve = in.object("curve");
        double[] times = curve.reals("times");
        double[] zeros = curve.reals("zero_rates");
        List<In> bookIn = in.objects("book");
        List<In> hedgeIn = in.objects("hedges");
        List<CrossAssetHedge.Instrument> book = new ArrayList<>();
        for (In p : bookIn) {
            book.add(instrument(p));
        }
        List<CrossAssetHedge.Instrument> hedges = new ArrayList<>();
        for (In p : hedgeIn) {
            hedges.add(instrument(p));
        }
        double[] weights = in.reals("weights");
        double ridge = in.real("ridge", 0.0);
        in.limit(bookIn.size() > MAX_BOOK, "book");
        in.limit(hedgeIn.size() > MAX_HEDGES, "hedges");
        in.limit(times.length > MAX_PILLARS, "curve");
        in.gate();
        CrossAssetHedge.Result r = CrossAssetHedge.solve(new CrossAssetHedge.Market(spot, q, vol, times, zeros), book,
                hedges, weights, ridge);
        return Operations.out("positions", r.positions(), "book_risk", r.bookRisk(), "residual_risk",
                r.residualRisk(), "objective", r.objective());
    }
}
