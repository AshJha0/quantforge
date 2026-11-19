package org.quantforge.risk;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/**
 * Standardised approach for counterparty credit risk, SA-CCR (plan item K-8d; specifications/06-risk/sa-ccr.md,
 * rulings KR-30 to KR-39). A port of python/quantforge_core/saccr.py. The supervisory parameters come from
 * {@link SaCcrTables}, generated from specifications/06-risk/sa-ccr-parameters.json.
 */
public final class SaCcr {
    private SaCcr() {}

    /** The asset classes, in output order (CRE52.26). */
    public static final List<String> CLASSES = List.of("IR", "FX", "CREDIT", "EQUITY", "COMMODITY");
    /** The hedging-set treatments, in output order (CRE52.46, CRE52.47). */
    public static final List<String> TREATMENTS = List.of("NORMAL", "BASIS", "VOLATILITY");

    private static final double MIN_YEARS =
            (double) SaCcrTables.MIN_BUSINESS_DAYS / SaCcrTables.BUSINESS_DAYS_PER_YEAR;

    /**
     * One trade of the netting set. Optional fields are null when absent.
     *
     * @param id unique identifier
     * @param assetClass IR, FX, CREDIT, EQUITY or COMMODITY
     * @param notional domestic-currency notional, before SD for IR and credit
     * @param marketValue market value, part of V
     * @param maturity M in years
     * @param kind LINEAR, OPTION or CDO
     * @param position LONG or SHORT (linear), BOUGHT or SOLD (option, CDO)
     * @param treatment NORMAL, BASIS or VOLATILITY
     * @param start S in years (IR and credit)
     * @param end E in years (IR and credit)
     * @param hedgingSet currency, pair or label
     * @param entity reference entity, index or commodity type
     * @param subclass Table 2 subclass
     * @param optionType CALL or PUT
     * @param underlyingPrice P
     * @param strike K
     * @param exercise T in years
     * @param shift lambda of CRE52.40 FAQ2
     * @param attachment A
     * @param detachment D
     */
    public record Trade(String id, String assetClass, double notional, double marketValue, double maturity,
            String kind, String position, String treatment, Double start, Double end, String hedgingSet,
            String entity, String subclass, String optionType, Double underlyingPrice, Double strike, Double exercise,
            double shift, Double attachment, Double detachment) {}

    /**
     * The margin agreement of a margined netting set.
     *
     * @param threshold TH
     * @param mta minimum transfer amount
     * @param nica net independent collateral amount
     * @param remarginDays re-margining period in business days
     * @param mporDays the caller's MPOR estimate, or null
     * @param illiquid illiquid collateral or hard-to-replace trades (CRE52.51(2))
     * @param disputes the disputes condition of CRE52.51(3)
     */
    public record Margin(double threshold, double mta, double nica, long remarginDays, Long mporDays,
            boolean illiquid, boolean disputes) {}

    /**
     * Per-trade figures.
     *
     * @param id trade id
     * @param supervisoryDuration SD, null outside IR and credit
     * @param adjustedNotional d
     * @param maturityFactor MF
     * @param delta supervisory delta
     * @param effectiveNotional D = d MF delta
     * @param supervisoryFactor SF times the treatment scale
     */
    public record TradeRow(String id, Double supervisoryDuration, double adjustedNotional, double maturityFactor,
            double delta, double effectiveNotional, double supervisoryFactor) {}

    /**
     * One hedging set's add-on.
     *
     * @param assetClass asset class
     * @param treatment treatment
     * @param key currency, pair, commodity set or label; "" for credit and equity NORMAL
     * @param addon add-on
     */
    public record HedgingSet(String assetClass, String treatment, String key, double addon) {}

    /**
     * The result of {@link #ead}.
     *
     * @param ead exposure at default (capped when margined)
     * @param rc replacement cost
     * @param pfe potential future exposure
     * @param multiplier PFE multiplier
     * @param addonAggregate aggregate add-on
     * @param addon add-on per asset class, in {@link #CLASSES} order
     * @param v net market value
     * @param c collateral
     * @param margined true when a margin agreement was given
     * @param mporDays MPOR in business days, or null when unmargined
     * @param eadUnmargined the unmargined EAD of the same trades, or null when unmargined
     * @param capped true when the margined EAD is capped at the unmargined one
     * @param hedgingSets hedging sets in output order
     * @param trades per-trade rows in input order
     */
    public record Result(double ead, double rc, double pfe, double multiplier, double addonAggregate,
            Map<String, Double> addon, double v, double c, boolean margined, Long mporDays, Double eadUnmargined,
            boolean capped, List<HedgingSet> hedgingSets, List<TradeRow> trades) {}

    private static int row(String assetClass, String subclass) {
        String s = subclass == null ? "" : subclass;
        for (int i = 0; i < SaCcrTables.CLASS.length; i++) {
            if (SaCcrTables.CLASS[i].equals(assetClass) && SaCcrTables.SUBCLASS[i].equals(s)) {
                return i;
            }
        }
        return -1;
    }

    private static boolean creditEquityCommodity(String c) {
        return c.equals("CREDIT") || c.equals("EQUITY") || c.equals("COMMODITY");
    }

    private static void need(Trade t, Object value, String field, String why) {
        if (value == null) {
            throw new QfError("E_INPUT", "trade " + t.id() + ": " + field + " is required " + why, field);
        }
    }

    /** Structural checks (E_INPUT), all before any domain check (HR-122 order). */
    static void structure(List<Trade> trades) {
        if (trades.isEmpty()) {
            throw new QfError("E_INPUT", "trades is empty", "trades");
        }
        Set<String> seen = new HashSet<>();
        for (Trade t : trades) {
            if (!seen.add(t.id())) {
                throw new QfError("E_INPUT", "duplicate trade id " + t.id(), "id");
            }
            String c = t.assetClass();
            if (c.equals("IR") || c.equals("CREDIT")) {
                need(t, t.start(), "start", "for IR and CREDIT trades");
                need(t, t.end(), "end", "for IR and CREDIT trades");
            }
            if (c.equals("IR") || c.equals("FX") || !t.treatment().equals("NORMAL")) {
                need(t, t.hedgingSet(), "hedging_set", "for IR, FX, basis and volatility trades");
            }
            if (creditEquityCommodity(c)) {
                need(t, t.entity(), "entity", "for CREDIT, EQUITY and COMMODITY trades");
                need(t, t.subclass(), "subclass", "for CREDIT, EQUITY and COMMODITY trades");
                if (row(c, t.subclass()) < 0) {
                    throw new QfError("E_INPUT", "trade " + t.id() + ": subclass " + t.subclass() + " is not a " + c
                            + " subclass", "subclass");
                }
            } else if (t.subclass() != null) {
                throw new QfError("E_INPUT", "trade " + t.id() + ": " + c + " trades take no subclass", "subclass");
            }
            boolean linear = t.position().equals("LONG") || t.position().equals("SHORT");
            if (t.kind().equals("LINEAR") != linear) {
                throw new QfError("E_INPUT", "trade " + t.id() + ": position " + t.position() + " does not fit kind "
                        + t.kind(), "position");
            }
            if (t.kind().equals("OPTION")) {
                need(t, t.optionType(), "option_type", "for OPTION trades");
                need(t, t.underlyingPrice(), "underlying_price", "for OPTION trades");
                need(t, t.strike(), "strike", "for OPTION trades");
                need(t, t.exercise(), "exercise", "for OPTION trades");
            }
            if (t.kind().equals("CDO")) {
                if (!c.equals("CREDIT")) {
                    throw new QfError("E_INPUT", "trade " + t.id() + ": CDO tranches are CREDIT trades", "kind");
                }
                need(t, t.attachment(), "attachment", "for CDO trades");
                need(t, t.detachment(), "detachment", "for CDO trades");
            }
        }
        Map<List<String>, String> entitySub = new HashMap<>();
        for (Trade t : trades) {
            if (t.entity() == null || t.subclass() == null) {
                continue;
            }
            List<String> key = List.of(t.assetClass(), t.treatment(), t.hedgingSet() == null ? "" : t.hedgingSet(),
                    t.entity());
            if (!entitySub.computeIfAbsent(key, k -> t.subclass()).equals(t.subclass())) {
                throw new QfError("E_INPUT", "entity " + t.entity() + " has two subclasses", "subclass");
            }
        }
    }

    private static double or0(Double v) {
        return v == null ? 0.0 : v;
    }

    static void domain(List<Trade> trades, Margin margin) {
        for (Trade t : trades) {
            if (!(t.notional() > 0)) {
                throw new QfError("E_DOMAIN", "trade " + t.id() + ": notional must be positive", "notional");
            }
            if (!(t.maturity() > 0)) {
                throw new QfError("E_DOMAIN", "trade " + t.id() + ": maturity must be positive", "maturity");
            }
            if (t.start() != null && t.end() != null && !(0 <= t.start() && t.start() <= t.end())) {
                throw new QfError("E_DOMAIN", "trade " + t.id() + ": need 0 <= start <= end", "start");
            }
            if (t.kind().equals("OPTION")) {
                double p = or0(t.underlyingPrice()) + t.shift();
                double k = or0(t.strike()) + t.shift();
                if (!(p > 0 && k > 0)) {
                    throw new QfError("E_DOMAIN", "trade " + t.id() + ": shifted price and strike must be positive",
                            "strike");
                }
                if (!(or0(t.exercise()) > 0)) {
                    throw new QfError("E_DOMAIN", "trade " + t.id() + ": exercise must be positive", "exercise");
                }
            }
            if (t.kind().equals("CDO")) {
                double a = or0(t.attachment());
                double d = or0(t.detachment());
                if (!(0 <= a && a < d && d <= 1)) {
                    throw new QfError("E_DOMAIN", "trade " + t.id() + ": need 0 <= attachment < detachment <= 1",
                            "attachment");
                }
            }
        }
        if (margin != null) {
            if (margin.threshold() < 0) {
                throw new QfError("E_DOMAIN", "threshold must not be negative", "threshold");
            }
            if (margin.mta() < 0) {
                throw new QfError("E_DOMAIN", "mta must not be negative", "mta");
            }
            if (margin.remarginDays() < 1) {
                throw new QfError("E_DOMAIN", "remargin_days must be at least 1", "remargin_days");
            }
            if (margin.mporDays() != null && margin.mporDays() < 1) {
                throw new QfError("E_DOMAIN", "mpor_days must be at least 1", "mpor_days");
            }
        }
    }

    /** CRE52.34, floored at ten business days. */
    public static double supervisoryDuration(double start, double end) {
        double r = SaCcrTables.SUPERVISORY_DURATION_RATE;
        double sd = (Math.exp(-r * start) - Math.exp(-r * end)) / r;
        return Math.max(sd, MIN_YEARS);
    }

    /** CRE52.50 and CRE52.51 floors, in business days (ruling KR-35). */
    public static long mporFloor(Margin margin, int tradeCount) {
        long base = margin.remarginDays() == 1 ? SaCcrTables.MPOR_DAILY
                : SaCcrTables.MPOR_NON_DAILY_BASE + margin.remarginDays();
        if (tradeCount > SaCcrTables.MPOR_LARGE_TRADES_ABOVE || margin.illiquid()) {
            base = Math.max(base, SaCcrTables.MPOR_LARGE_OR_ILLIQUID);
        }
        return margin.disputes() ? SaCcrTables.MPOR_DISPUTE_MULTIPLIER * base : base;
    }

    private static double phi(double x) {
        return Normal.cdf(x);
    }

    /** CRE52.39 to CRE52.41. */
    public static double supervisoryDelta(Trade t) {
        if (t.kind().equals("LINEAR")) {
            return t.position().equals("LONG") ? 1.0 : -1.0;
        }
        if (t.kind().equals("CDO")) {
            double a = or0(t.attachment());
            double d = or0(t.detachment());
            double v = SaCcrTables.CDO_NUMERATOR
                    / ((1.0 + SaCcrTables.CDO_SLOPE * a) * (1.0 + SaCcrTables.CDO_SLOPE * d));
            return t.position().equals("BOUGHT") ? v : -v;
        }
        double sigma = SaCcrTables.OPTION_VOLATILITY[row(t.assetClass(), t.subclass())];
        double tt = or0(t.exercise());
        double p = or0(t.underlyingPrice()) + t.shift();
        double k = or0(t.strike()) + t.shift();
        double d1 = (Math.log(p / k) + 0.5 * sigma * sigma * tt) / (sigma * Math.sqrt(tt));
        double sign = t.position().equals("BOUGHT") ? 1.0 : -1.0;
        return sign * (t.optionType().equals("CALL") ? phi(d1) : -phi(-d1));
    }

    private static double scale(String treatment) {
        return switch (treatment) {
            case "BASIS" -> SaCcrTables.SCALE_BASIS;
            case "VOLATILITY" -> SaCcrTables.SCALE_VOLATILITY;
            default -> SaCcrTables.SCALE_NORMAL;
        };
    }

    private static double factor(Trade t) {
        return SaCcrTables.FACTOR[row(t.assetClass(), t.subclass())] * scale(t.treatment());
    }

    /** CRE52.57 step 3 on E (CRE52.31(3)); 1 and 5 years fall in bucket 2 (ruling KR-32). */
    static int bucket(double end) {
        return end < SaCcrTables.IR_BUCKET1_BELOW ? 1 : end <= SaCcrTables.IR_BUCKET2_UP_TO ? 2 : 3;
    }

    private static double fsum(List<Double> v) {
        double[] a = new double[v.size()];
        for (int i = 0; i < a.length; i++) {
            a[i] = v.get(i);
        }
        return StressDrift.fsum(a);
    }

    /** CRE52.61 step 4, CRE52.66 step 4, CRE52.70 step 5: rho and add-on pairs. */
    static double singleFactor(double[] rho, double[] addon) {
        double[] sys = new double[rho.length];
        double[] idio = new double[rho.length];
        for (int i = 0; i < rho.length; i++) {
            sys[i] = rho[i] * addon[i];
            idio[i] = (1.0 - rho[i] * rho[i]) * addon[i] * addon[i];
        }
        double s = StressDrift.fsum(sys);
        return Math.sqrt(s * s + StressDrift.fsum(idio));
    }

    /** Code-point order, as Python sorts strings. */
    static int codePointCompare(String a, String b) {
        int i = 0;
        int j = 0;
        while (i < a.length() && j < b.length()) {
            int x = a.codePointAt(i);
            int y = b.codePointAt(j);
            if (x != y) {
                return Integer.compare(x, y);
            }
            i += Character.charCount(x);
            j += Character.charCount(y);
        }
        return Integer.compare(a.length() - i, b.length() - j);
    }

    private record Group(int cls, int treatment, String key) implements Comparable<Group> {
        @Override
        public int compareTo(Group o) {
            int c = Integer.compare(cls, o.cls);
            if (c == 0) {
                c = Integer.compare(treatment, o.treatment);
            }
            return c != 0 ? c : codePointCompare(key, o.key);
        }
    }

    private record Netting(double ead, double pfe, double m, Map<String, Double> byClass, List<HedgingSet> rows,
            double[] deltas, double[] eff) {}

    private static String groupKey(Trade t) {
        if (t.assetClass().equals("COMMODITY") && t.treatment().equals("NORMAL")) {
            return SaCcrTables.HEDGING_SET[row(t.assetClass(), t.subclass())];
        }
        if ((t.assetClass().equals("CREDIT") || t.assetClass().equals("EQUITY")) && t.treatment().equals("NORMAL")) {
            return "";
        }
        return t.hedgingSet() == null ? "" : t.hedgingSet();
    }

    private static double irAddon(List<Trade> trades, List<Integer> members, double[] eff, String treatment,
            boolean irOffset) {
        List<List<Double>> parts = List.of(new ArrayList<>(), new ArrayList<>(), new ArrayList<>());
        for (int i : members) {
            parts.get(bucket(or0(trades.get(i).end())) - 1).add(eff[i]);
        }
        double b1 = fsum(parts.get(0));
        double b2 = fsum(parts.get(1));
        double b3 = fsum(parts.get(2));
        double en;
        if (irOffset) {
            en = Math.sqrt(Math.max(b1 * b1 + b2 * b2 + b3 * b3 + SaCcrTables.IR_RHO_B1_B2 * b1 * b2
                    + SaCcrTables.IR_RHO_B2_B3 * b2 * b3 + SaCcrTables.IR_RHO_B1_B3 * b1 * b3, 0.0));
        } else {
            en = Math.abs(b1) + Math.abs(b2) + Math.abs(b3);
        }
        return SaCcrTables.FACTOR[row("IR", null)] * scale(treatment) * en;
    }

    private static Netting netting(List<Trade> trades, double[] mf, double[] d, double v, double c, double rc,
            boolean irOffset) {
        int n = trades.size();
        double[] deltas = new double[n];
        double[] eff = new double[n];
        for (int i = 0; i < n; i++) {
            deltas[i] = supervisoryDelta(trades.get(i));
            eff[i] = d[i] * mf[i] * deltas[i];
        }
        TreeMap<Group, List<Integer>> groups = new TreeMap<>();
        for (int i = 0; i < n; i++) {
            Trade t = trades.get(i);
            Group g = new Group(CLASSES.indexOf(t.assetClass()), TREATMENTS.indexOf(t.treatment()), groupKey(t));
            groups.computeIfAbsent(g, k -> new ArrayList<>()).add(i);
        }
        Map<String, Double> byClass = new LinkedHashMap<>();
        for (String k : CLASSES) {
            byClass.put(k, 0.0);
        }
        List<HedgingSet> rows = new ArrayList<>();
        for (Map.Entry<Group, List<Integer>> e : groups.entrySet()) {
            Group g = e.getKey();
            List<Integer> members = e.getValue();
            String cls = CLASSES.get(g.cls());
            String treatment = TREATMENTS.get(g.treatment());
            double addon;
            if (cls.equals("IR")) {
                addon = irAddon(trades, members, eff, treatment, irOffset);
            } else if (cls.equals("FX")) {
                List<Double> s = new ArrayList<>();
                for (int i : members) {
                    s.add(eff[i]);
                }
                addon = SaCcrTables.FACTOR[row("FX", null)] * scale(treatment) * Math.abs(fsum(s));
            } else {
                TreeMap<String, List<Integer>> entities = new TreeMap<>(SaCcr::codePointCompare);
                for (int i : members) {
                    String name = trades.get(i).entity() == null ? "" : trades.get(i).entity();
                    entities.computeIfAbsent(name, k -> new ArrayList<>()).add(i);
                }
                double[] rho = new double[entities.size()];
                double[] a = new double[entities.size()];
                int j = 0;
                for (List<Integer> idx : entities.values()) {
                    Trade first = trades.get(idx.getFirst());
                    double r = SaCcrTables.CORRELATION[row(cls, first.subclass())];
                    rho[j] = Double.isNaN(r) ? 0.0 : r;
                    List<Double> s = new ArrayList<>();
                    for (int i : idx) {
                        s.add(eff[i]);
                    }
                    a[j++] = factor(first) * fsum(s);
                }
                addon = singleFactor(rho, a);
            }
            byClass.put(cls, byClass.get(cls) + addon);
            rows.add(new HedgingSet(cls, treatment, g.key(), addon));
        }
        double aggregate = aggregate(byClass);
        double m = multiplier(v - c, aggregate);
        double pfe = m * aggregate;
        double ead = SaCcrTables.ALPHA * (rc + pfe);
        return new Netting(ead, pfe, m, byClass, rows, deltas, eff);
    }

    private static double aggregate(Map<String, Double> byClass) {
        return fsum(new ArrayList<>(byClass.values()));
    }

    /**
     * CRE52.23; with a zero aggregate add-on, the limit of the formula (ruling KR-36). V - C >= 0 gives exactly 1,
     * without evaluating an exponential that can overflow when the add-on is tiny.
     */
    public static double multiplier(double vMinusC, double addon) {
        if (vMinusC >= 0) {
            return 1.0;
        }
        double floor = SaCcrTables.MULTIPLIER_FLOOR;
        if (addon == 0.0) {
            return floor;
        }
        return Math.min(1.0, floor + (1.0 - floor) * Math.exp(vMinusC / (2.0 * (1.0 - floor) * addon)));
    }

    /** EAD of one netting set under SA-CCR (CRE52.1). {@code margin} null means unmargined. */
    public static Result ead(List<Trade> trades, double collateral, Margin margin, boolean irOffset) {
        structure(trades);
        domain(trades, margin);
        int n = trades.size();
        double[] mv = new double[n];
        for (int i = 0; i < n; i++) {
            mv[i] = trades.get(i).marketValue();
        }
        double v = StressDrift.fsum(mv);
        double c = collateral;
        Double[] sd = new Double[n];
        double[] d = new double[n];
        double[] mfUn = new double[n];
        for (int i = 0; i < n; i++) {
            Trade t = trades.get(i);
            if (t.assetClass().equals("IR") || t.assetClass().equals("CREDIT")) {
                double s = supervisoryDuration(or0(t.start()), or0(t.end()));
                sd[i] = s;
                d[i] = t.notional() * s;
            } else {
                d[i] = t.notional();
            }
            mfUn[i] = Math.sqrt(Math.min(Math.max(t.maturity(), MIN_YEARS), 1.0));
        }
        double rcUn = Math.max(v - c, 0.0);
        Netting un = netting(trades, mfUn, d, v, c, rcUn, irOffset);
        Netting result;
        double[] mf;
        double rc;
        Long mpor = null;
        Double eadUn = null;
        boolean capped = false;
        if (margin == null) {
            result = un;
            mf = mfUn;
            rc = rcUn;
        } else {
            long floor = mporFloor(margin, n);
            mpor = Math.max(floor, margin.mporDays() == null ? 0L : margin.mporDays());
            double mfM = SaCcrTables.MARGINED_MF_SCALE
                    * Math.sqrt((double) mpor / SaCcrTables.BUSINESS_DAYS_PER_YEAR);
            mf = new double[n];
            java.util.Arrays.fill(mf, mfM);
            rc = Math.max(Math.max(v - c, margin.threshold() + margin.mta() - margin.nica()), 0.0);
            result = netting(trades, mf, d, v, c, rc, irOffset);
            eadUn = un.ead();
            capped = un.ead() < result.ead();
        }
        List<TradeRow> rows = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            Trade t = trades.get(i);
            rows.add(new TradeRow(t.id(), sd[i], d[i], mf[i], result.deltas()[i], result.eff()[i], factor(t)));
        }
        double total = eadUn == null ? result.ead() : Math.min(result.ead(), eadUn);
        return new Result(total, rc, result.pfe(), result.m(), aggregate(result.byClass()), result.byClass(), v, c,
                margin != null, mpor, eadUn, capped, result.rows(), rows);
    }
}
