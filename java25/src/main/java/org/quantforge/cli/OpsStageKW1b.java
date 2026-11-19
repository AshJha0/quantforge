package org.quantforge.cli;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.FrtbBacktest;
import org.quantforge.risk.SaCcr;

/**
 * Stage K wave 1b verbs: SA-CCR (K-8d, sa-ccr.md) and FRTB IMA backtesting (K-8e, frtb-ima-backtest.md). Every input
 * is read (E_SCHEMA, enum values included) before the gate (E_LIMIT, then the finite rule), and the core then checks
 * structure (E_INPUT) before domain (E_DOMAIN): error order HR-122. Registered by the coordinator at integration
 * (program/STAGE_K_W1B_PORTS_HANDOVER.md).
 */
final class OpsStageKW1b {
    private OpsStageKW1b() {}

    private static final List<String> CLASSES = SaCcr.CLASSES;
    private static final List<String> KINDS = List.of("LINEAR", "OPTION", "CDO");
    private static final List<String> POSITIONS = List.of("LONG", "SHORT", "BOUGHT", "SOLD");
    private static final List<String> TREATMENTS = SaCcr.TREATMENTS;
    private static final List<String> OPTION_TYPES = List.of("CALL", "PUT");
    private static final List<String> SUBCLASSES = List.of("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "IG", "SG",
            "SINGLE", "INDEX", "ELECTRICITY", "OIL_GAS", "METALS", "AGRICULTURAL", "OTHER");

    /** A string from a fixed list; a value outside the list is E_SCHEMA (ruling KR-39). */
    static String choice(In in, String key, List<String> allowed) {
        String s = in.string(key);
        if (!allowed.contains(s)) {
            throw new QfError("E_SCHEMA", key + " must be one of " + allowed, key);
        }
        return s;
    }

    private static String choice(In in, String key, List<String> allowed, String fallback) {
        return in.has(key) ? choice(in, key, allowed) : fallback;
    }

    private static String optString(In in, String key) {
        return in.has(key) ? in.string(key) : null;
    }

    static SaCcr.Trade trade(In t) {
        return new SaCcr.Trade(t.string("id"), choice(t, "asset_class", CLASSES), t.real("notional"),
                t.real("market_value"), t.real("maturity"), choice(t, "kind", KINDS, "LINEAR"),
                choice(t, "position", POSITIONS), choice(t, "treatment", TREATMENTS, "NORMAL"), t.realOrNull("start"),
                t.realOrNull("end"), optString(t, "hedging_set"), optString(t, "entity"),
                choice(t, "subclass", SUBCLASSES, null), choice(t, "option_type", OPTION_TYPES, null),
                t.realOrNull("underlying_price"), t.realOrNull("strike"), t.realOrNull("exercise"),
                t.real("shift", 0.0), t.realOrNull("attachment"), t.realOrNull("detachment"));
    }

    static Out saccr(In in) {
        List<SaCcr.Trade> trades = new ArrayList<>();
        for (In t : in.objects("trades")) {
            trades.add(trade(t));
        }
        SaCcr.Margin margin = null;
        if (in.has("margin")) {
            In m = in.object("margin");
            margin = new SaCcr.Margin(m.real("threshold"), m.real("mta"), m.real("nica"), m.integer("remargin_days"),
                    m.has("mpor_days") ? m.integer("mpor_days") : null, m.bool("illiquid", false),
                    m.bool("disputes", false));
        }
        double collateral = in.real("collateral", 0.0);
        boolean irOffset = in.bool("ir_offset", true);
        in.gate();
        return Operations.out(saccrOutputs(SaCcr.ead(trades, collateral, margin, irOffset)).toArray());
    }

    /** The outputs of risk.saccr.ead as alternating keys and values, in the contract's order. */
    static List<Object> saccrOutputs(SaCcr.Result r) {
        List<Object> sets = new ArrayList<>();
        for (SaCcr.HedgingSet h : r.hedgingSets()) {
            sets.add(Operations.out("asset_class", h.assetClass(), "treatment", h.treatment(), "key", h.key(),
                    "addon", h.addon()).outputs());
        }
        List<Object> rows = new ArrayList<>();
        for (SaCcr.TradeRow t : r.trades()) {
            rows.add(Operations.out("id", t.id(), "supervisory_duration", t.supervisoryDuration(),
                    "adjusted_notional", t.adjustedNotional(), "maturity_factor", t.maturityFactor(), "delta",
                    t.delta(), "effective_notional", t.effectiveNotional(), "supervisory_factor",
                    t.supervisoryFactor()).outputs());
        }
        return Arrays.asList("ead", r.ead(), "rc", r.rc(), "pfe", r.pfe(), "multiplier", r.multiplier(), "addon_aggregate",
                r.addonAggregate(), "addon", new LinkedHashMap<String, Object>(r.addon()), "v", r.v(), "c", r.c(),
                "margined", r.margined(), "mpor_days", r.mporDays(), "ead_unmargined",
                r.eadUnmargined(), "capped", r.capped(), "hedging_sets", sets, "trades", rows);
    }

    static Out zone(In in) {
        long n = in.integer("observations");
        long a = in.integer("exceptions_actual");
        long h = in.integer("exceptions_hypothetical");
        in.limit(n > 1_000_000, "observations"); // ruling KR-46, as J-W3-17
        in.gate();
        FrtbBacktest.Zone z = FrtbBacktest.zone(n, a, h);
        return Operations.out("exceptions", z.exceptions(), "cumulative_probability", z.cumulativeProbability(),
                "zone", z.zone(), "amber_from", z.amberFrom(), "red_from", z.redFrom(), "multiplier", z.multiplier());
    }

    static Out desk(In in) {
        long n = in.integer("observations");
        long a99 = in.integer("exceptions_99_actual");
        long h99 = in.integer("exceptions_99_hypothetical");
        long a975 = in.integer("exceptions_975_actual");
        long h975 = in.integer("exceptions_975_hypothetical");
        in.limit(n > 1_000_000, "observations"); // ruling KR-46
        in.gate();
        FrtbBacktest.Desk d = FrtbBacktest.desk(n, a99, h99, a975, h975);
        return Operations.out("exceptions_99", d.exceptions99(), "exceptions_975", d.exceptions975(),
                "cumulative_probability_99", d.cumulativeProbability99(), "cumulative_probability_975",
                d.cumulativeProbability975(), "breach_99", d.breach99(), "breach_975", d.breach975(), "eligible",
                d.eligible());
    }

    static Out count(In in) {
        List<Double> var = in.nullableReals("var");
        List<Double> actual = in.nullableReals("actual");
        List<Double> hypothetical = in.nullableReals("hypothetical");
        in.gate();
        FrtbBacktest.Count c = FrtbBacktest.countExceptions(var, actual, hypothetical);
        return Operations.out("observations", c.observations(), "exceptions_actual", c.exceptionsActual(),
                "exceptions_hypothetical", c.exceptionsHypothetical(), "exceptions", c.exceptions(), "days_actual",
                c.daysActual(), "days_hypothetical", c.daysHypothetical());
    }

    /** Adds the four verbs. Called from Operations.MODULES once the coordinator registers the module. */
    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.saccr.ead", OpsStageKW1b::saccr);
        table.put("risk.frtb.backtest.zone", OpsStageKW1b::zone);
        table.put("risk.frtb.backtest.desk", OpsStageKW1b::desk);
        table.put("risk.frtb.backtest.count", OpsStageKW1b::count);
    }
}
