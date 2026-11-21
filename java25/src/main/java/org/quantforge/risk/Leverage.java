package org.quantforge.risk;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/**
 * Leverage ratio and large exposures, simplified (plan item K-8i, leverage-large-exposures.md). Rulings KR-50 to
 * KR-53, KR-65 to KR-69 and KR-319 to KR-326 (stage-k-rulings-w2.md). Port of
 * {@code python/quantforge_core/leverage.py}: same checks in the same order (E_SCHEMA, structural E_INPUT, E_DOMAIN;
 * the CLI layer holds E_LIMIT and the finite rule ahead of the core) and the same correctly rounded sums
 * ({@link StressDrift#fsum}, as math.fsum). Parameters come from the generated {@link KW2bTables}. "Simplified" means
 * exactly the spec's Limits list: Tier 1, PFE, eligibility of purchased protection, connectedness, exemptions and
 * the standardised CCFs are the caller's.
 */
public final class Leverage {
    private Leverage() {}

    /** KR-65. */
    public static final String LEVERAGE_LABEL = "simplified leverage ratio (LEV30 subset); not a regulatory return";
    /** KR-66. */
    public static final String LARGE_EXPOSURES_LABEL =
            "simplified large exposures (LEX subset); not a regulatory return";

    private static double lev(String key) {
        return Double.parseDouble((String) KW2bTables.LEV.get(key));
    }

    private static double lex(String key) {
        return Double.parseDouble((String) KW2bTables.LEX.get(key));
    }

    static final double ALPHA = lev("deriv.alpha"); // LEV30.14
    static final double MIN_RATIO = lev("min_leverage_ratio"); // LEV20.7
    /** LEV30.49-30.54: input category (KR-65) to the table key. */
    public static final Map<String, String> CCF_CATEGORIES;

    static {
        Map<String, String> m = new LinkedHashMap<>();
        m.put("DIRECT_CREDIT_SUBSTITUTE", "direct_credit_substitutes_and_other_100pct_items");
        m.put("FORWARD_PURCHASE", "direct_credit_substitutes_and_other_100pct_items");
        m.put("OTHER_CREDIT_SUBSTITUTE", "direct_credit_substitutes_and_other_100pct_items");
        m.put("NIF_RUF", "nif_ruf");
        m.put("TRANSACTION_CONTINGENT", "transaction_related_contingent");
        m.put("COMMITMENT", "commitments");
        m.put("TRADE_LC", "short_term_trade_lc");
        m.put("UNCONDITIONALLY_CANCELLABLE", "unconditionally_cancellable");
        CCF_CATEGORIES = Collections.unmodifiableMap(m);
    }

    static final double LARGE = lex("large_exposure_threshold"); // LEX10.8
    static final double LIMIT = lex("limit"); // LEX20.1
    static final double LIMIT_GSIB = lex("limit.gsib_to_gsib"); // LEX20.1, LEX40
    static final double CCF_FLOOR = lex("exposure.obs_ccf_floor"); // LEX30.6
    static final int TOP_N = ((Long) KW2bTables.LEX.get("report.top_n")).intValue(); // LEX20.4(4)
    /** KR-53 seniority ranks (a short offsets longs of equal or higher rank). */
    public static final Map<String, Integer> RANKS;

    static {
        Map<String, Integer> m = new LinkedHashMap<>();
        m.put("COVERED", 4);
        m.put("SENIOR", 3);
        m.put("NON_SENIOR", 2);
        m.put("EQUITY", 1);
        RANKS = Collections.unmodifiableMap(m);
    }

    // KR-324, CONFIRMED 2026-11-20 as an inferred reading (LEX20.1 and LEX40 are silent on mixed groups): a group
    // takes the 15% limit when the bank is a G-SIB and ANY member is flagged. Golden lex_k-0010 is the mixed group.
    static final boolean GSIB_GROUP_ANY_MEMBER = true;

    private static QfError schema(String message, String field) {
        return new QfError("E_SCHEMA", message, field);
    }

    private static QfError input(String message, String field) {
        return new QfError("E_INPUT", message, field);
    }

    private static QfError domain(String message, String field) {
        return new QfError("E_DOMAIN", message, field);
    }

    private static void notNegative(double value, String field) {
        if (value < 0) {
            throw domain(field + " must not be negative", field);
        }
    }

    private static double fsum(List<Double> v) {
        double[] a = new double[v.size()];
        for (int i = 0; i < a.length; i++) {
            a[i] = v.get(i);
        }
        return StressDrift.fsum(a);
    }

    // --- leverage ratio ----------------------------------------------------------------------------------------

    /**
     * One derivative netting set (LEV30.14-30.16).
     *
     * @param v replacement value
     * @param pfe potential future exposure (input)
     * @param cvmReceived variation margin received
     * @param cvmProvided variation margin provided
     */
    public record DerivativeSet(double v, double pfe, double cvmReceived, double cvmProvided) {}

    /**
     * A written credit derivative (LEV30.31).
     *
     * @param notional notional
     * @param fairValue fair value (a negative one reduces the notional, footnote 384)
     * @param purchasedOffset eligible purchased protection
     */
    public record WrittenCreditDerivative(double notional, double fairValue, double purchasedOffset) {}

    /**
     * A securities financing transaction set (LEV30.37).
     *
     * @param grossAssets gross SFT assets
     * @param mna under a master netting agreement
     * @param exposures exposures E_i
     * @param collateral collateral C_i, same length
     */
    public record Sft(double grossAssets, boolean mna, double[] exposures, double[] collateral) {}

    /**
     * An off-balance sheet item (LEV30.49-30.54).
     *
     * @param notional notional
     * @param ccfCategory one of {@link #CCF_CATEGORIES}
     */
    public record OffBalance(double notional, String ccfCategory) {}

    /**
     * The leverage ratio result.
     *
     * @param onBalance on-balance sheet part
     * @param derivatives derivative part (netting sets plus written CDs, KR-320)
     * @param derivativeNettingSets netting sets only
     * @param writtenCreditDerivatives written CD effective notionals
     * @param sfts SFT part
     * @param offBalance off-balance sheet part
     * @param exposure exposure measure (LEV20.5)
     * @param ratio Tier 1 over exposure
     * @param meetsMinimum tier1 >= 0.03 x exposure in binary64
     * @param label KR-65 label
     */
    public record LeverageResult(double onBalance, double derivatives, double derivativeNettingSets,
            double writtenCreditDerivatives, double sfts, double offBalance, double exposure, double ratio,
            boolean meetsMinimum, String label) {}

    /**
     * LEV30.14-30.16: alpha (RC + PFE), RC = max(V - CVM received + CVM provided, 0).
     *
     * @param d the netting set
     * @return its exposure
     */
    public static double derivativeExposure(DerivativeSet d) {
        return ALPHA * (Math.max(d.v() - d.cvmReceived() + d.cvmProvided(), 0.0) + d.pfe());
    }

    /**
     * LEV30.31 and footnote 384: reduced by a negative fair value only, then by purchased protection, never below 0.
     *
     * @param w the written credit derivative
     * @return its effective notional
     */
    public static double writtenCdEffectiveNotional(WrittenCreditDerivative w) {
        return Math.max(w.notional() - Math.max(0.0, -w.fairValue()) - w.purchasedOffset(), 0.0);
    }

    /**
     * LEV30.37: gross assets plus the counterparty measure, netted only under an MNA.
     *
     * @param s the SFT set
     * @return its exposure
     */
    public static double sftExposure(Sft s) {
        double add;
        if (s.mna()) {
            add = Math.max(0.0, StressDrift.fsum(s.exposures()) - StressDrift.fsum(s.collateral()));
        } else {
            double[] t = new double[s.exposures().length];
            for (int i = 0; i < t.length; i++) {
                t[i] = Math.max(0.0, s.exposures()[i] - s.collateral()[i]);
            }
            add = StressDrift.fsum(t);
        }
        return s.grossAssets() + add;
    }

    /**
     * Leverage ratio exposure measure (LEV20.5) and ratio (LEV20.3), simplified (KR-65).
     *
     * @param tier1 Tier 1 capital, positive
     * @param onBalance on-balance sheet items
     * @param derivatives derivative netting sets
     * @param written written credit derivatives
     * @param sfts SFT sets
     * @param offBalance off-balance sheet items
     * @return the result
     */
    public static LeverageResult leverage(double tier1, double[] onBalance, List<DerivativeSet> derivatives,
            List<WrittenCreditDerivative> written, List<Sft> sfts, List<OffBalance> offBalance) {
        for (OffBalance o : offBalance) {
            if (!CCF_CATEGORIES.containsKey(o.ccfCategory())) {
                throw schema("ccf_category " + o.ccfCategory() + " is not listed", "ccf_category");
            }
        }
        for (Sft s : sfts) {
            if (s.exposures().length != s.collateral().length) {
                throw input("exposures and collateral differ in length", "collateral");
            }
        }
        if (!(tier1 > 0)) {
            throw domain("tier1 must be positive", "tier1");
        }
        for (double x : onBalance) {
            notNegative(x, "on_balance");
        }
        for (DerivativeSet d : derivatives) {
            notNegative(d.cvmReceived(), "cvm_received");
            notNegative(d.cvmProvided(), "cvm_provided");
            notNegative(d.pfe(), "pfe");
        }
        for (WrittenCreditDerivative w : written) {
            notNegative(w.notional(), "notional");
            notNegative(w.purchasedOffset(), "purchased_offset");
        }
        for (Sft s : sfts) {
            notNegative(s.grossAssets(), "gross_assets");
            for (double e : s.exposures()) {
                notNegative(e, "exposures");
            }
            for (double c : s.collateral()) {
                notNegative(c, "collateral");
            }
        }
        for (OffBalance o : offBalance) {
            notNegative(o.notional(), "notional");
        }
        double on = StressDrift.fsum(onBalance);
        List<Double> parts = new ArrayList<>();
        for (DerivativeSet d : derivatives) {
            parts.add(derivativeExposure(d));
        }
        double nettingSets = fsum(parts);
        parts.clear();
        for (WrittenCreditDerivative w : written) {
            parts.add(writtenCdEffectiveNotional(w));
        }
        double writtenSum = fsum(parts);
        double deriv = nettingSets + writtenSum; // KR-320: written credit derivatives sit in the derivatives part
        parts.clear();
        for (Sft s : sfts) {
            parts.add(sftExposure(s));
        }
        double sft = fsum(parts);
        parts.clear();
        for (OffBalance o : offBalance) {
            parts.add(o.notional() * Double.parseDouble((String) ccfTable().get(CCF_CATEGORIES.get(o.ccfCategory()))));
        }
        double obs = fsum(parts);
        double exposure = StressDrift.fsum(new double[] {on, deriv, sft, obs}); // LEV20.5
        if (!(exposure > 0)) {
            throw domain("the exposure measure is zero: no ratio (KR-321)", "on_balance");
        }
        return new LeverageResult(on, deriv, nettingSets, writtenSum, sft, obs, exposure, tier1 / exposure,
                tier1 >= MIN_RATIO * exposure, LEVERAGE_LABEL); // LEV20.3, LEV20.7 in binary64
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> ccfTable() {
        return (Map<String, Object>) KW2bTables.LEV.get("ccf");
    }

    // --- large exposures ---------------------------------------------------------------------------------------

    /**
     * A counterparty.
     *
     * @param id identifier, unique
     * @param group connected group label (null: its own group)
     * @param gsib flagged G-SIB
     * @param exempt exempted exposure (flag only)
     */
    public record LeCounterparty(String id, String group, boolean gsib, boolean exempt) {}

    /**
     * A banking book exposure.
     *
     * @param counterparty counterparty id
     * @param value exposure value
     */
    public record BankingBookExposure(String counterparty, double value) {}

    /**
     * An off-balance sheet exposure.
     *
     * @param counterparty counterparty id
     * @param notional notional
     * @param ccf the caller's CCF in [0, 1], floored at 10% (LEX30.6)
     */
    public record OffBalanceExposure(String counterparty, double notional, double ccf) {}

    /**
     * Credit protection moving exposure from a counterparty to the provider (LEX30.13-30.15).
     *
     * @param counterparty protected counterparty
     * @param provider protection provider
     * @param protectedAmount amount recognised
     */
    public record Protection(String counterparty, String provider, double protectedAmount) {}

    /**
     * A trading book position (KR-51 with a counterparty, KR-66); maturity, cash equity and LGD flags are read and
     * ignored (LEX30.17-30.18, KR-322).
     *
     * @param id position id, unique
     * @param counterparty counterparty id
     * @param seniority one of {@link #RANKS}
     * @param notional notional (>= 0 long, KR-323)
     * @param marketValue market value
     */
    public record TradingPosition(String id, String counterparty, String seniority, double notional,
            double marketValue) {}

    /**
     * One counterparty row.
     *
     * @param id identifier
     * @param bankingBook banking book sum
     * @param offBalance converted off-balance sheet sum
     * @param tradingBookNetLong trading book net long after KR-53 offsetting
     * @param tradingBookNetShort net short left (not an exposure)
     * @param protectedAmount protection bought on it
     * @param received protection it provides
     * @param exposure exposure after CRM
     */
    public record CounterpartyRow(String id, double bankingBook, double offBalance, double tradingBookNetLong,
            double tradingBookNetShort, double protectedAmount, double received, double exposure) {}

    /**
     * One group row.
     *
     * @param group label
     * @param members member ids, input order
     * @param exposure sum of member exposures
     * @param share exposure over Tier 1
     * @param large exposure >= 10% of Tier 1
     * @param limit 25% (or 15%) of Tier 1
     * @param breach non-exempt sum above the limit
     * @param exempt every member exempt
     */
    public record GroupRow(String group, List<String> members, double exposure, double share, boolean large,
            double limit, boolean breach, boolean exempt) {}

    /**
     * The large exposures result.
     *
     * @param counterparties per counterparty, input order
     * @param groups per group, by label in code-point order
     * @param report reported group labels, largest first
     * @param label KR-66 label
     */
    public record LargeExposuresResult(List<CounterpartyRow> counterparties, List<GroupRow> groups,
            List<String> report, String label) {}

    /**
     * KR-53 for one obligor: shorts in descending rank (ties: input order) each consume the longs of equal or higher
     * rank in ascending rank (ties: input order) until used up.
     *
     * @param ranks seniority rank per position
     * @param jtd signed JTD per position
     * @return {net long, net short}
     */
    public static double[] offsetBySeniority(int[] ranks, double[] jtd) {
        List<double[]> longs = new ArrayList<>();
        List<double[]> shorts = new ArrayList<>();
        for (int i = 0; i < ranks.length; i++) {
            if (jtd[i] > 0) {
                longs.add(new double[] {ranks[i], jtd[i]});
            } else if (jtd[i] < 0) {
                shorts.add(new double[] {ranks[i], -jtd[i]});
            }
        }
        List<Integer> longOrder = new ArrayList<>();
        for (int i = 0; i < longs.size(); i++) {
            longOrder.add(i);
        }
        longOrder.sort(Comparator.comparingDouble(i -> longs.get(i)[0])); // stable: input order on ties
        List<double[]> sortedShorts = new ArrayList<>(shorts);
        sortedShorts.sort(Comparator.comparingDouble(x -> -x[0])); // stable
        double[] leftShort = new double[sortedShorts.size()];
        for (int s = 0; s < sortedShorts.size(); s++) {
            double r = sortedShorts.get(s)[0];
            double amount = sortedShorts.get(s)[1];
            for (int i : longOrder) {
                if (amount <= 0) {
                    break;
                }
                double[] l = longs.get(i);
                if (l[0] >= r && l[1] > 0) {
                    double used = Math.min(amount, l[1]);
                    l[1] -= used;
                    amount -= used;
                }
            }
            leftShort[s] = amount;
        }
        double[] remaining = new double[longs.size()];
        for (int i = 0; i < remaining.length; i++) {
            remaining[i] = longs.get(i)[1];
        }
        return new double[] {StressDrift.fsum(remaining), -StressDrift.fsum(leftShort)};
    }

    /**
     * LEX30.17: gross JTD of MAR22.11 with LGD 100% is the market value, kept on the position's side (KR-323).
     *
     * @param p the position
     * @return signed JTD
     */
    public static double jtd(TradingPosition p) {
        return p.notional() >= 0 ? Math.max(p.marketValue(), 0.0) : Math.min(p.marketValue(), 0.0);
    }

    private static void leStructure(List<LeCounterparty> cps, List<String[]> refs, List<Protection> crm,
            List<TradingPosition> tb) {
        Map<String, String> groupOf = new HashMap<>();
        for (LeCounterparty c : cps) {
            if (groupOf.containsKey(c.id())) {
                throw input("counterparty " + c.id() + " appears twice (so possibly in two groups)", "id");
            }
            groupOf.put(c.id(), c.group());
        }
        for (LeCounterparty c : cps) {
            if (c.group() != null && groupOf.containsKey(c.group()) && !c.group().equals(groupOf.get(c.group()))) {
                throw input("group " + c.group() + " is also a counterparty outside it (KR-324)", "group");
            }
        }
        for (String[] r : refs) {
            if (!groupOf.containsKey(r[1])) {
                throw input("unknown counterparty " + r[1], r[0]);
            }
        }
        for (Protection p : crm) {
            if (p.provider().equals(p.counterparty())) {
                throw input("a counterparty cannot protect itself", "provider");
            }
        }
        Set<String> ids = new HashSet<>();
        for (TradingPosition t : tb) {
            if (!ids.add(t.id())) {
                throw input("position id " + t.id() + " appears twice", "id");
            }
        }
    }

    private static Map<String, Double> parts(List<LeCounterparty> cps, List<String> names, List<Double> values) {
        Map<String, List<Double>> by = new LinkedHashMap<>();
        for (LeCounterparty c : cps) {
            by.put(c.id(), new ArrayList<>());
        }
        for (int i = 0; i < names.size(); i++) {
            by.get(names.get(i)).add(values.get(i));
        }
        Map<String, Double> out = new HashMap<>();
        by.forEach((k, v) -> out.put(k, fsum(v)));
        return out;
    }

    /**
     * Exposure per counterparty and per group against the LEX20.1 limit, simplified (KR-66).
     *
     * @param tier1 Tier 1 capital, positive
     * @param cps counterparties
     * @param bankingBook banking book exposures
     * @param offBalance off-balance sheet exposures
     * @param crm protection
     * @param tradingBook trading book positions
     * @param bankGsib the bank is a G-SIB
     * @return the result
     */
    public static LargeExposuresResult largeExposures(double tier1, List<LeCounterparty> cps,
            List<BankingBookExposure> bankingBook, List<OffBalanceExposure> offBalance, List<Protection> crm,
            List<TradingPosition> tradingBook, boolean bankGsib) {
        for (TradingPosition t : tradingBook) {
            if (!RANKS.containsKey(t.seniority())) {
                throw schema("seniority " + t.seniority() + " is not listed", "seniority");
            }
        }
        List<String[]> refs = new ArrayList<>();
        bankingBook.forEach(b -> refs.add(new String[] {"counterparty", b.counterparty()}));
        offBalance.forEach(o -> refs.add(new String[] {"counterparty", o.counterparty()}));
        crm.forEach(p -> refs.add(new String[] {"counterparty", p.counterparty()}));
        crm.forEach(p -> refs.add(new String[] {"provider", p.provider()}));
        tradingBook.forEach(t -> refs.add(new String[] {"counterparty", t.counterparty()}));
        leStructure(cps, refs, crm, tradingBook);
        if (!(tier1 > 0)) {
            throw domain("tier1 must be positive", "tier1");
        }
        for (BankingBookExposure b : bankingBook) {
            notNegative(b.value(), "value");
        }
        for (OffBalanceExposure o : offBalance) {
            notNegative(o.notional(), "notional");
            if (!(0 <= o.ccf() && o.ccf() <= 1)) {
                throw domain("ccf must lie in [0, 1]", "ccf");
            }
        }
        for (Protection p : crm) {
            notNegative(p.protectedAmount(), "protected");
        }
        List<String> n1 = new ArrayList<>();
        List<Double> v1 = new ArrayList<>();
        for (BankingBookExposure b : bankingBook) {
            n1.add(b.counterparty());
            v1.add(b.value());
        }
        Map<String, Double> bb = parts(cps, n1, v1);
        List<String> n2 = new ArrayList<>();
        List<Double> v2 = new ArrayList<>();
        for (OffBalanceExposure o : offBalance) {
            n2.add(o.counterparty());
            v2.add(o.notional() * Math.max(o.ccf(), CCF_FLOOR));
        }
        Map<String, Double> obs = parts(cps, n2, v2);
        List<String> n3 = new ArrayList<>();
        List<String> n4 = new ArrayList<>();
        List<Double> v3 = new ArrayList<>();
        for (Protection p : crm) {
            n3.add(p.counterparty());
            n4.add(p.provider());
            v3.add(p.protectedAmount());
        }
        Map<String, Double> prot = parts(cps, n3, v3);
        Map<String, Double> received = parts(cps, n4, v3);
        Map<String, List<double[]>> positions = new HashMap<>();
        for (LeCounterparty c : cps) {
            positions.put(c.id(), new ArrayList<>());
        }
        for (TradingPosition t : tradingBook) {
            positions.get(t.counterparty()).add(new double[] {RANKS.get(t.seniority()), jtd(t)});
        }
        List<CounterpartyRow> rows = new ArrayList<>();
        Map<String, Double> exposure = new HashMap<>();
        for (LeCounterparty c : cps) {
            List<double[]> ps = positions.get(c.id());
            int[] ranks = new int[ps.size()];
            double[] j = new double[ps.size()];
            for (int i = 0; i < ranks.length; i++) {
                ranks[i] = (int) ps.get(i)[0];
                j[i] = ps.get(i)[1];
            }
            double[] net = offsetBySeniority(ranks, j); // LEX30.22-30.23, 30.30
            double gross = StressDrift.fsum(new double[] {bb.get(c.id()), obs.get(c.id()), net[0]});
            if (prot.get(c.id()) > gross) {
                throw domain("counterparty " + c.id() + ": protected amount above its exposure", "protected");
            }
            double e = StressDrift.fsum(new double[] {gross, -prot.get(c.id()), received.get(c.id())}); // LEX30.13
            exposure.put(c.id(), e);
            rows.add(new CounterpartyRow(c.id(), bb.get(c.id()), obs.get(c.id()), net[0], net[1], prot.get(c.id()),
                    received.get(c.id()), e));
        }
        TreeMap<String, List<LeCounterparty>> members = new TreeMap<>(FrtbDrc.CODE_POINT); // KR-326: code-point order
        for (LeCounterparty c : cps) {
            members.computeIfAbsent(c.group() != null ? c.group() : c.id(), k -> new ArrayList<>()).add(c);
        }
        List<GroupRow> groups = new ArrayList<>();
        for (Map.Entry<String, List<LeCounterparty>> g : members.entrySet()) {
            List<LeCounterparty> ms = g.getValue();
            List<Double> all = new ArrayList<>();
            List<Double> counted = new ArrayList<>();
            List<String> ids = new ArrayList<>();
            boolean anyGsib = false;
            boolean everyGsib = true;
            boolean allExempt = true;
            for (LeCounterparty c : ms) {
                all.add(exposure.get(c.id()));
                if (!c.exempt()) {
                    counted.add(exposure.get(c.id())); // KR-325
                }
                ids.add(c.id());
                anyGsib |= c.gsib();
                everyGsib &= c.gsib();
                allExempt &= c.exempt();
            }
            double total = fsum(all); // LEX10.9
            double countedSum = fsum(counted);
            boolean gsib = bankGsib && (GSIB_GROUP_ANY_MEMBER ? anyGsib : everyGsib); // KR-324, open reading
            double limit = (gsib ? LIMIT_GSIB : LIMIT) * tier1;
            boolean large = total >= LARGE * tier1; // LEX10.8, binary64 (KR-326)
            groups.add(new GroupRow(g.getKey(), List.copyOf(ids), total, total / tier1, large, limit,
                    countedSum > limit, allExempt));
        }
        List<GroupRow> ranked = new ArrayList<>(groups);
        // LEX20.4: largest first, ties by label; + 0.0 makes -0.0 equal to 0.0 as in Python's comparison
        ranked.sort((a, b) -> {
            int c = Double.compare(b.exposure() + 0.0, a.exposure() + 0.0);
            return c != 0 ? c : FrtbDrc.CODE_POINT.compare(a.group(), b.group()); // KR-326
        });
        List<String> report = new ArrayList<>();
        for (int n = 0; n < ranked.size(); n++) {
            if (ranked.get(n).large() || n < TOP_N) {
                report.add(ranked.get(n).group());
            }
        }
        return new LargeExposuresResult(rows, groups, report, LARGE_EXPOSURES_LABEL);
    }
}
