package org.quantforge.risk;

import java.util.ArrayList;
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
 * FRTB standardised approach: default risk charge (DRC) and residual risk add-on (RRAO), plan item K-8a
 * (specifications/06-risk/frtb-drc-rrao.md; rulings KR-50 to KR-55, KR-67 to KR-69 and KR-112 to KR-116 of
 * specifications/stage-k-rulings-w2.md). A port of python/quantforge_core/frtb_drc.py; the parameters come from
 * {@link FrtbDrcTables}, generated from specifications/tables/stage_k/mar22_drc.json and mar23_rrao.json.
 *
 * <p>The records below are plain carriers and validate nothing on construction: every rule is checked by the entry
 * points in the order of KR-67 (E_LIMIT, then structural E_INPUT over every position, then E_DOMAIN). E_SCHEMA and
 * the finite rule belong to the input layer (the CLI handler), as in the Python reference.
 */
public final class FrtbDrc {
    private FrtbDrc() {}

    /** KR-69. */
    public static final String LABEL = "regulatory formula on caller inputs; not a regulatory return";
    /** KR-55. */
    public static final String RW_SOURCE =
            "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)";
    /** KR-67: positions and instruments per call. */
    public static final int MAX_POSITIONS = 100_000;
    /** MAR22.22, in output order (KR-114). */
    public static final List<String> BUCKETS = List.of("CORPORATE", "SOVEREIGN", "LOCAL_GOV");
    /** KR-51 seniorities. */
    public static final List<String> SENIORITIES = List.of("COVERED", "SENIOR", "NON_SENIOR", "EQUITY");
    /** MAR22.24 Table 2 rating names. */
    public static final List<String> RATINGS = List.of(FrtbDrcTables.RATINGS);
    /** MAR23 instrument kinds. */
    public static final List<String> KINDS = List.of("EXOTIC", "OTHER");
    /** frtb-drc-rrao.md Errors: a caller rw above 1250% is E_DOMAIN. */
    static final double RW_CAP = 12.5;

    /**
     * A non-securitisation position (KR-51); {@code notional} and {@code marketValue} are signed, long above 0.
     *
     * @param id unique id
     * @param obligor obligor name, key of the ratings map
     * @param bucket CORPORATE, SOVEREIGN or LOCAL_GOV
     * @param seniority COVERED, SENIOR, NON_SENIOR or EQUITY
     * @param notional signed notional
     * @param marketValue signed bond-equivalent market value
     * @param maturityYears maturity in years
     * @param cashEquity a stock (MAR22.16)
     * @param lgdApplies false for MAR22.12(4)
     */
    public record Position(String id, String obligor, String bucket, String seniority, double notional,
            double marketValue, double maturityYears, boolean cashEquity, boolean lgdApplies) {}

    /**
     * A securitisation position outside the CTP; JTD is the market value (MAR22.27), {@code rw} the caller's (KR-55).
     *
     * @param id unique id
     * @param bucket bucket key
     * @param pool pool key
     * @param tranche tranche key
     * @param marketValue signed market value
     * @param maturityYears maturity in years
     * @param rw risk weight
     */
    public record SecPosition(String id, String bucket, String pool, String tranche, double marketValue,
            double maturityYears, double rw) {}

    /**
     * A correlation trading position: netting key (index, series, tranche), bucket = index (MAR22.39).
     *
     * @param id unique id
     * @param index index name, the bucket
     * @param series series
     * @param tranche tranche
     * @param marketValue signed market value
     * @param maturityYears maturity in years
     * @param rw risk weight
     */
    public record CtpPosition(String id, String index, String series, String tranche, double marketValue,
            double maturityYears, double rw) {}

    /**
     * An instrument subject to the residual risk add-on (MAR23).
     *
     * @param id unique id
     * @param grossNotional gross notional
     * @param kind EXOTIC or OTHER
     * @param listedOrClearable listed or eligible for central clearing
     * @param backToBack an exact back-to-back trade
     */
    public record Instrument(String id, double grossNotional, String kind, boolean listedOrClearable,
            boolean backToBack) {}

    /** A non-securitisation position row: gross JTD, maturity weight, scaled JTD. */
    public record JtdRow(String id, double grossJtd, double weight, double scaledJtd) {}

    /** A securitisation or CTP position row: maturity weight and scaled JTD. */
    public record WeightRow(String id, double weight, double scaledJtd) {}

    /** One obligor after offsetting (KR-53). */
    public record ObligorRow(String obligor, double netLong, double netShort, double rw) {}

    /** One bucket: HBR (null when undefined, KR-54), weighted sums and DRC_b. */
    public record BucketRow(String bucket, Double hbr, double wtdLong, double wtdShort, double drc) {}

    /** The result of {@link #drcNonsec}. */
    public record NonsecResult(List<JtdRow> positions, List<ObligorRow> obligors, List<BucketRow> buckets,
            double drc) {}

    /** The result of {@link #drcSecNonctp}. */
    public record SecResult(List<WeightRow> positions, List<BucketRow> buckets, double drc) {}

    /** The result of {@link #drcCtp}; in bucket_drc mode {@code positions} and {@code buckets} are null. */
    public record CtpResult(List<WeightRow> positions, Double hbrCtp, List<BucketRow> buckets, double drc) {}

    /** One RRAO instrument row. */
    public record RraoRow(String id, double weight, boolean excluded, double addon) {}

    /** The result of {@link #rrao}. */
    public record RraoResult(List<RraoRow> instruments, double rrao) {}

    /** MAR22.12 LGD by seniority. */
    static double lgd(String seniority) {
        return switch (seniority) {
            case "COVERED" -> FrtbDrcTables.LGD_COVERED;
            case "SENIOR" -> FrtbDrcTables.LGD_SENIOR;
            case "NON_SENIOR" -> FrtbDrcTables.LGD_NON_SENIOR;
            default -> FrtbDrcTables.LGD_EQUITY;
        };
    }

    /** KR-53 offsetting rank: COVERED 4, SENIOR 3, NON_SENIOR 2, EQUITY 1. */
    static int rank(String seniority) {
        return 4 - SENIORITIES.indexOf(seniority);
    }

    /** MAR22.24 Table 2 risk weight of a rating. */
    static double riskWeight(String rating) {
        return FrtbDrcTables.RISK_WEIGHT[RATINGS.indexOf(rating)];
    }

    /** MAR22.15, MAR22.18, KR-52: 1 at one year or more, else the maturity floored at 0.25. */
    public static double maturityWeight(double maturityYears) {
        return maturityYears >= FrtbDrcTables.CAPITAL_HORIZON ? 1.0
                : Math.max(maturityYears, FrtbDrcTables.MATURITY_FLOOR);
    }

    /** MAR22.11, MAR22.12: LGD x notional + P&amp;L, floored at 0 for a long and capped at 0 for a short. */
    public static double grossJtd(Position p) {
        double l = p.lgdApplies() ? lgd(p.seniority()) : 1.0;
        double pnl = p.marketValue() - p.notional();
        double raw = l * p.notional() + pnl;
        if (p.notional() > 0) {
            return Math.max(raw, 0.0);
        }
        if (p.notional() < 0) {
            return Math.min(raw, 0.0);
        }
        return 0.0;
    }

    static double fsum(List<Double> v) {
        double[] a = new double[v.size()];
        for (int i = 0; i < a.length; i++) {
            a[i] = v.get(i);
        }
        return StressDrift.fsum(a);
    }

    /** Unicode code-point order, as Python sorts strings. */
    static final Comparator<String> CODE_POINT = (a, b) -> {
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
    };

    private static void limit(int n, String field) {
        if (n > MAX_POSITIONS) {
            throw new QfError("E_LIMIT", field + " is above its limit of " + MAX_POSITIONS, field);
        }
    }

    private static void unique(List<String> ids, String field) {
        Set<String> seen = new HashSet<>();
        for (int k = 0; k < ids.size(); k++) {
            if (!seen.add(ids.get(k))) {
                throw new QfError("E_INPUT", "duplicate id " + ids.get(k), field + "/" + k + "/id");
            }
        }
    }

    private static void maturity(double m, String path) {
        if (!(m > 0)) {
            throw new QfError("E_DOMAIN", "maturity_years must be above 0", path);
        }
    }

    /**
     * KR-53 greedy offsetting within one obligor. {@code longs} and {@code shorts} hold {rank, scaled JTD} in input
     * order (longs above 0, shorts below 0). Shorts are served in descending rank (ties: input order); each consumes
     * the eligible longs (rank at least its own) in ascending rank (ties: input order).
     *
     * @return {net long &gt;= 0, net short &lt;= 0}
     */
    public static double[] offset(List<double[]> longs, List<double[]> shorts) {
        int nl = longs.size();
        double[] left = new double[nl];
        List<Integer> order = new ArrayList<>();
        for (int k = 0; k < nl; k++) {
            left[k] = longs.get(k)[1];
            order.add(k);
        }
        order.sort(Comparator.comparingDouble((Integer k) -> longs.get(k)[0]).thenComparingInt(k -> k));
        List<Integer> served = new ArrayList<>();
        for (int k = 0; k < shorts.size(); k++) {
            served.add(k);
        }
        served.sort(Comparator.comparingDouble((Integer k) -> -shorts.get(k)[0]).thenComparingInt(k -> k));
        List<Double> rest = new ArrayList<>();
        for (int k : served) {
            double r = shorts.get(k)[0];
            double need = -shorts.get(k)[1];
            for (int j : order) {
                if (need <= 0) {
                    break;
                }
                if (longs.get(j)[0] < r || left[j] <= 0) {
                    continue;
                }
                double used = Math.min(need, left[j]);
                left[j] -= used;
                need -= used;
            }
            if (need > 0) {
                rest.add(-need);
            }
        }
        return new double[] {StressDrift.fsum(left), fsum(rest)};
    }

    /** MAR22.23, MAR22.25 and KR-54 over {rw, net long, net short} of one bucket. */
    static BucketRow bucketDrc(String bucket, List<double[]> pairs) {
        List<Double> longs = new ArrayList<>();
        List<Double> shorts = new ArrayList<>();
        List<Double> wl = new ArrayList<>();
        List<Double> ws = new ArrayList<>();
        for (double[] p : pairs) {
            longs.add(p[1]);
            shorts.add(-p[2]);
            wl.add(p[0] * p[1]);
            ws.add(p[0] * -p[2]);
        }
        double longSum = fsum(longs);
        double total = longSum + fsum(shorts);
        double wtdLong = fsum(wl);
        double wtdShort = fsum(ws);
        Double hbr = total > 0 ? longSum / total : null;
        double drc = hbr != null ? Math.max(wtdLong - hbr * wtdShort, 0.0) : 0.0;
        return new BucketRow(bucket, hbr, wtdLong, wtdShort, drc);
    }

    private static double sumDrc(List<BucketRow> buckets) {
        List<Double> v = new ArrayList<>();
        for (BucketRow b : buckets) {
            v.add(b.drc());
        }
        return fsum(v);
    }

    /** Default risk charge for non-securitisations (MAR22.9 to MAR22.26). */
    public static NonsecResult drcNonsec(List<Position> positions, Map<String, String> ratings) {
        limit(positions.size(), "positions");
        if (positions.isEmpty()) {
            throw new QfError("E_INPUT", "positions is empty", "positions");
        }
        unique(positions.stream().map(Position::id).toList(), "positions");
        Map<String, String> bucketOf = new HashMap<>();
        for (int k = 0; k < positions.size(); k++) {
            Position p = positions.get(k);
            if (!ratings.containsKey(p.obligor())) {
                throw new QfError("E_INPUT", "obligor " + p.obligor() + " has no rating", "positions/" + k + "/obligor");
            }
            if (!bucketOf.computeIfAbsent(p.obligor(), o -> p.bucket()).equals(p.bucket())) { // KR-113
                throw new QfError("E_INPUT", "obligor " + p.obligor() + " is in two buckets",
                        "positions/" + k + "/bucket");
            }
        }
        for (int k = 0; k < positions.size(); k++) {
            Position p = positions.get(k);
            String path = "positions/" + k;
            maturity(p.maturityYears(), path + "/maturity_years");
            if (p.cashEquity()) {
                double m = p.maturityYears();
                if (m != FrtbDrcTables.CASH_EQUITY_SHORT && m < FrtbDrcTables.CAPITAL_HORIZON) { // KR-52
                    throw new QfError("E_DOMAIN", "cash equity maturity must be 0.25 or at least 1", path);
                }
                if (!p.seniority().equals("EQUITY") || p.notional() != p.marketValue()) { // KR-112
                    throw new QfError("E_DOMAIN", "cash equity must be EQUITY with notional = market value", path);
                }
            }
            if (p.notional() == 0 && p.marketValue() != 0) {
                throw new QfError("E_DOMAIN", "zero notional with a nonzero market value", path + "/notional");
            }
        }
        List<JtdRow> rows = new ArrayList<>();
        Map<String, List<double[]>> longs = new TreeMap<>(CODE_POINT);
        Map<String, List<double[]>> shorts = new HashMap<>();
        for (Position p : positions) {
            double jtd = grossJtd(p);
            double w = maturityWeight(p.maturityYears());
            double scaled = w * jtd;
            rows.add(new JtdRow(p.id(), jtd, w, scaled));
            List<double[]> l = longs.computeIfAbsent(p.obligor(), o -> new ArrayList<>());
            List<double[]> s = shorts.computeIfAbsent(p.obligor(), o -> new ArrayList<>());
            if (scaled > 0) {
                l.add(new double[] {rank(p.seniority()), scaled});
            } else if (scaled < 0) {
                s.add(new double[] {rank(p.seniority()), scaled});
            }
        }
        List<ObligorRow> obligors = new ArrayList<>();
        Map<String, List<double[]>> perBucket = new HashMap<>();
        for (Map.Entry<String, List<double[]>> e : longs.entrySet()) {
            String name = e.getKey();
            double[] net = offset(e.getValue(), shorts.get(name));
            double rw = riskWeight(ratings.get(name));
            obligors.add(new ObligorRow(name, net[0], net[1], rw));
            perBucket.computeIfAbsent(bucketOf.get(name), b -> new ArrayList<>()).add(new double[] {rw, net[0], net[1]});
        }
        List<BucketRow> buckets = new ArrayList<>();
        for (String b : BUCKETS) {
            if (perBucket.containsKey(b)) {
                buckets.add(bucketDrc(b, perBucket.get(b)));
            }
        }
        rows.sort(Comparator.comparing(JtdRow::id, CODE_POINT));
        return new NonsecResult(rows, obligors, buckets, sumDrc(buckets));
    }

    private static void callerRw(double[] rws, double[] maturities, String field) {
        for (int k = 0; k < rws.length; k++) {
            maturity(maturities[k], field + "/" + k + "/maturity_years");
            if (!(rws[k] >= 0 && rws[k] <= RW_CAP)) {
                throw new QfError("E_DOMAIN", "rw must be in [0, " + RW_CAP + "]", field + "/" + k + "/rw");
            }
        }
    }

    /** Sums scaled JTDs per netting key (MAR22.29, MAR22.39(1)); one rw per key (KR-115). Value {rw, net}. */
    private static Map<List<String>, double[]> netGroups(List<List<String>> keys, double[] rws, double[] scaled,
            String field) {
        Map<List<String>, Double> rwOf = new HashMap<>();
        for (int k = 0; k < keys.size(); k++) {
            double rw = rws[k];
            if (rwOf.computeIfAbsent(keys.get(k), x -> rw) != rw) {
                throw new QfError("E_INPUT", "positions netted together carry different rw", field + "/" + k + "/rw");
            }
        }
        Map<List<String>, List<Double>> parts = new LinkedHashMap<>();
        for (int k = 0; k < keys.size(); k++) {
            parts.computeIfAbsent(keys.get(k), x -> new ArrayList<>()).add(scaled[k]);
        }
        Map<List<String>, double[]> out = new LinkedHashMap<>();
        for (Map.Entry<List<String>, List<Double>> e : parts.entrySet()) {
            out.put(e.getKey(), new double[] {rwOf.get(e.getKey()), fsum(e.getValue())});
        }
        return out;
    }

    private static double weightOrZero(double m) {
        return m > 0 ? maturityWeight(m) : 0.0;
    }

    private static List<WeightRow> weightRows(List<String> ids, double[] weights, double[] scaled) {
        List<WeightRow> rows = new ArrayList<>();
        for (int k = 0; k < ids.size(); k++) {
            rows.add(new WeightRow(ids.get(k), weights[k], scaled[k]));
        }
        rows.sort(Comparator.comparing(WeightRow::id, CODE_POINT));
        return rows;
    }

    /** Default risk charge for securitisations outside the CTP (MAR22.27 to MAR22.35, KR-55). */
    public static SecResult drcSecNonctp(List<SecPosition> positions) {
        limit(positions.size(), "positions");
        List<String> ids = positions.stream().map(SecPosition::id).toList();
        unique(ids, "positions");
        int n = positions.size();
        List<List<String>> keys = new ArrayList<>();
        double[] rws = new double[n];
        double[] mats = new double[n];
        double[] weights = new double[n];
        double[] scaled = new double[n];
        for (int k = 0; k < n; k++) {
            SecPosition p = positions.get(k);
            keys.add(List.of(p.bucket(), p.pool(), p.tranche()));
            rws[k] = p.rw();
            mats[k] = p.maturityYears();
            weights[k] = weightOrZero(p.maturityYears());
            scaled[k] = weights[k] * p.marketValue();
        }
        Map<List<String>, double[]> nets = netGroups(keys, rws, scaled, "positions");
        callerRw(rws, mats, "positions");
        Map<String, List<double[]>> perBucket = new TreeMap<>(CODE_POINT);
        for (Map.Entry<List<String>, double[]> e : nets.entrySet()) {
            double[] v = e.getValue();
            perBucket.computeIfAbsent(e.getKey().get(0), b -> new ArrayList<>())
                    .add(new double[] {v[0], Math.max(v[1], 0.0), Math.min(v[1], 0.0)});
        }
        List<BucketRow> buckets = new ArrayList<>();
        for (Map.Entry<String, List<double[]>> e : perBucket.entrySet()) {
            buckets.add(bucketDrc(e.getKey(), e.getValue()));
        }
        return new SecResult(weightRows(ids, weights, scaled), buckets, sumDrc(buckets));
    }

    /** MAR22.45: max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0). */
    public static double ctpTotal(double[] bucketDrc) {
        double[] terms = new double[bucketDrc.length];
        for (int k = 0; k < terms.length; k++) {
            double d = bucketDrc[k];
            terms[k] = Math.max(d, 0.0) + FrtbDrcTables.CTP_CROSS_FACTOR * Math.min(d, 0.0);
        }
        return Math.max(StressDrift.fsum(terms), 0.0);
    }

    /**
     * Default risk charge for the correlation trading portfolio (MAR22.36 to MAR22.45, KR-55): exactly one of
     * {@code positions} and {@code bucketDrc} (index-level DRC_b) is non-null.
     */
    public static CtpResult drcCtp(List<CtpPosition> positions, double[] bucketDrc) {
        if ((positions == null) == (bucketDrc == null)) {
            throw new QfError("E_INPUT", "give exactly one of positions and bucket_drc", "positions");
        }
        if (bucketDrc != null) {
            limit(bucketDrc.length, "bucket_drc");
            return new CtpResult(null, null, null, ctpTotal(bucketDrc));
        }
        limit(positions.size(), "positions");
        List<String> ids = positions.stream().map(CtpPosition::id).toList();
        unique(ids, "positions");
        int n = positions.size();
        List<List<String>> keys = new ArrayList<>();
        double[] rws = new double[n];
        double[] mats = new double[n];
        double[] weights = new double[n];
        double[] scaled = new double[n];
        for (int k = 0; k < n; k++) {
            CtpPosition p = positions.get(k);
            keys.add(List.of(p.index(), p.series(), p.tranche()));
            rws[k] = p.rw();
            mats[k] = p.maturityYears();
            weights[k] = weightOrZero(p.maturityYears());
            scaled[k] = weights[k] * p.marketValue();
        }
        Map<List<String>, double[]> nets = netGroups(keys, rws, scaled, "positions");
        callerRw(rws, mats, "positions");
        List<Double> longs = new ArrayList<>();
        List<Double> shorts = new ArrayList<>();
        Map<String, List<double[]>> perIndex = new TreeMap<>(CODE_POINT);
        for (Map.Entry<List<String>, double[]> e : nets.entrySet()) {
            double net = e.getValue()[1];
            longs.add(Math.max(net, 0.0));
            shorts.add(-Math.min(net, 0.0));
            perIndex.computeIfAbsent(e.getKey().get(0), b -> new ArrayList<>()).add(e.getValue());
        }
        double longSum = fsum(longs);
        double total = longSum + fsum(shorts);
        Double hbr = total > 0 ? longSum / total : null; // KR-54 analogue
        double h = hbr != null ? hbr : 0.0;
        List<BucketRow> buckets = new ArrayList<>();
        double[] drcs = new double[perIndex.size()];
        for (Map.Entry<String, List<double[]>> e : perIndex.entrySet()) {
            List<Double> wl = new ArrayList<>();
            List<Double> ws = new ArrayList<>();
            for (double[] v : e.getValue()) {
                if (v[1] > 0) {
                    wl.add(v[0] * v[1]);
                } else if (v[1] < 0) {
                    ws.add(v[0] * -v[1]);
                }
            }
            double l = fsum(wl);
            double s = fsum(ws);
            double drcB = l - h * s; // MAR22.44: no floor
            drcs[buckets.size()] = drcB;
            buckets.add(new BucketRow(e.getKey(), null, l, s, drcB));
        }
        return new CtpResult(weightRows(ids, weights, scaled), hbr, buckets, ctpTotal(drcs));
    }

    /** Residual risk add-on (MAR23.7, MAR23.8). */
    public static RraoResult rrao(List<Instrument> instruments) {
        limit(instruments.size(), "instruments");
        unique(instruments.stream().map(Instrument::id).toList(), "instruments");
        for (int k = 0; k < instruments.size(); k++) {
            if (!(instruments.get(k).grossNotional() >= 0)) {
                throw new QfError("E_DOMAIN", "gross_notional must be 0 or above",
                        "instruments/" + k + "/gross_notional");
            }
        }
        List<RraoRow> rows = new ArrayList<>();
        List<Double> addons = new ArrayList<>();
        for (Instrument x : instruments) {
            boolean excluded = x.backToBack() || (x.kind().equals("OTHER") && x.listedOrClearable());
            double w = x.kind().equals("EXOTIC") ? FrtbDrcTables.RRAO_EXOTIC : FrtbDrcTables.RRAO_OTHER;
            double addon = excluded ? 0.0 : w * x.grossNotional();
            rows.add(new RraoRow(x.id(), w, excluded, addon));
            addons.add(addon);
        }
        return new RraoResult(rows, fsum(addons));
    }
}
