package org.quantforge.risk;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/**
 * CVA risk capital (plan item K-8g, cva-capital.md): BA-CVA reduced (MAR50.14) and full (MAR50.20), and SA-CVA
 * (MAR50.42 to 50.53). Rulings KR-50, KR-62 to KR-64, KR-67 to KR-69 and KR-120 to KR-127
 * (stage-k-rulings-w2.md). Port of {@code python/quantforge_core/cva.py}: same checks in the same order (KR-67: E_SCHEMA,
 * then structural E_INPUT, then E_DOMAIN; the CLI layer holds E_LIMIT and the finite rule ahead of the core), same
 * sums (math.fsum as {@link StressDrift#fsum}, Python's built-in sum as {@link #pySum}). Every parameter is read from
 * the generated {@link KW2bTables} (tools/gen_k_w2b_tables.py); nothing is typed here. SA-CVA reuses the FRTB
 * sensitivity-based aggregation ({@link FrtbSbm#bucketRadicand}, {@link FrtbSbm#crossRadicand}) and adds what
 * MAR50.53 changes: the hedge term R, S_b always clipped, no correlation scenarios, the floor of KR-62 and m_CVA.
 */
public final class Cva {
    private Cva() {}

    /** KR-69. */
    public static final String LABEL = "regulatory formula on caller inputs; not a regulatory return";

    private static final Map<String, Object> T = KW2bTables.MAR50;

    static double num(String key) {
        return Double.parseDouble((String) T.get(key));
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> table(String key) {
        return (Map<String, Object>) T.get(key);
    }

    @SuppressWarnings("unchecked")
    static List<Object> list(String key) {
        return (List<Object>) T.get(key);
    }

    static final double RWA_MULTIPLIER = num("rwa_multiplier"); // MAR50.1
    static final double DS = num("ba.ds"); // MAR50.14
    static final double RHO = num("ba.rho"); // MAR50.14(2)
    static final double ALPHA = num("ba.alpha"); // MAR50.15(5)
    static final double DF_RATE = num("ba.df_rate"); // MAR50.15(4), footnote 357
    static final double BETA = num("ba.beta"); // MAR50.20
    static final double INDEX_SCALAR = num("ba.index_rw_scalar"); // MAR50.24(4)
    static final double R_HEDGE = num("sa.R"); // MAR50.53(1)
    /** MAR50.41: the default m_CVA. */
    public static final double M_CVA = num("sa.m_cva");
    /** Index weights sum to 1 within this (cva-capital.md, Errors). */
    static final double WEIGHT_TOLERANCE = 1e-12;

    /** MAR50.16 Table 1 rows, in table order. */
    public static final List<String> SECTORS = List.copyOf(table("ba.rw").keySet());
    /** MAR50.16 Table 1 columns, in that order. */
    public static final List<String> QUALITIES = List.of("IG", "HY_NR");
    /** BA-CVA versions. */
    public static final List<String> VERSIONS = List.of("REDUCED", "FULL");
    /** MAR50.26 Table 2: input names (KR-64) to table keys. */
    public static final Map<String, String> RELATIONS = orderedMap("DIRECT", "direct", "LEGAL", "legally_related",
            "SECTOR_REGION", "same_sector_region");

    private static Map<String, String> orderedMap(String... kv) {
        Map<String, String> m = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put(kv[i], kv[i + 1]);
        }
        return java.util.Collections.unmodifiableMap(m);
    }

    private static double rw(String sector, String quality) {
        @SuppressWarnings("unchecked")
        List<Object> row = (List<Object>) table("ba.rw").get(sector);
        return Double.parseDouble((String) row.get(QUALITIES.indexOf(quality)));
    }

    private static QfError schema(String message, String field) {
        return new QfError("E_SCHEMA", message, field);
    }

    private static QfError input(String message, String field) {
        return new QfError("E_INPUT", message, field);
    }

    private static QfError domain(String message, String field) {
        return new QfError("E_DOMAIN", message, field);
    }

    /**
     * Python's built-in {@code sum} of floats (CPython 3.12 and later: Neumaier compensation, the correction added
     * once at the end when it is non-zero and finite), so that the plain sums of cva.py round the same way.
     *
     * @param v the terms, in order
     * @return the sum
     */
    static double pySum(double[] v) {
        double s = 0.0;
        double c = 0.0;
        for (double x : v) {
            double t = s + x;
            if (Math.abs(s) >= Math.abs(x)) {
                c += (s - t) + x;
            } else {
                c += (x - t) + s;
            }
            s = t;
        }
        if (c != 0.0 && Double.isFinite(c)) {
            s += c;
        }
        return s;
    }

    private static double fsum(List<Double> v) {
        double[] a = new double[v.size()];
        for (int i = 0; i < a.length; i++) {
            a[i] = v.get(i);
        }
        return StressDrift.fsum(a);
    }

    // --- BA-CVA ------------------------------------------------------------------------------------------------

    /**
     * One netting set (MAR50.15).
     *
     * @param ead exposure at default
     * @param m effective maturity, years
     * @param imm true when the bank uses IMM for this netting set (DF 1)
     */
    public record NettingSet(double ead, double m, boolean imm) {}

    /**
     * One counterparty.
     *
     * @param id identifier, unique
     * @param sector MAR50.16 Table 1 row
     * @param quality IG or HY_NR
     * @param nettingSets its netting sets
     */
    public record Counterparty(String id, String sector, String quality, List<NettingSet> nettingSets) {}

    /**
     * A single-name hedge (MAR50.23).
     *
     * @param counterparty the hedged counterparty
     * @param relation DIRECT, LEGAL or SECTOR_REGION (MAR50.26 Table 2)
     * @param sector reference name's sector
     * @param quality reference name's quality
     * @param m remaining maturity
     * @param notional notional
     */
    public record SingleNameHedge(String counterparty, String relation, String sector, String quality, double m,
            double notional) {}

    /**
     * One constituent of an index hedge.
     *
     * @param sector sector
     * @param quality quality
     * @param weight share of the index
     */
    public record Constituent(String sector, String quality, double weight) {}

    /**
     * An index hedge (MAR50.24).
     *
     * @param m remaining maturity
     * @param notional notional
     * @param constituents weights summing to 1
     */
    public record IndexHedge(double m, double notional, List<Constituent> constituents) {}

    /**
     * Per-counterparty outputs.
     *
     * @param id identifier
     * @param scva stand-alone CVA capital
     * @param snh hedge sum (null for REDUCED)
     * @param hma hedge misalignment (null for REDUCED)
     * @param df discount factor per netting set
     */
    public record CounterpartyRow(String id, double scva, Double snh, Double hma, List<Double> df) {}

    /**
     * The BA-CVA result.
     *
     * @param version REDUCED or FULL
     * @param counterparties per counterparty, input order
     * @param ih index hedge term (null for REDUCED)
     * @param kReduced K_reduced
     * @param kHedged K_hedged (null for REDUCED)
     * @param kFull K_full (null for REDUCED)
     * @param capital DS times K
     * @param rwa 12.5 times capital
     * @param label KR-69 label
     */
    public record BaResult(String version, List<CounterpartyRow> counterparties, Double ih, double kReduced,
            Double kHedged, Double kFull, double capital, double rwa, String label) {}

    /**
     * MAR50.15(4): 1 for IMM, else the average discount factor at 5% to M, as -expm1(-0.05 M) / (0.05 M) (KR-64).
     *
     * @param m maturity, positive
     * @param imm IMM netting set
     * @return the discount factor
     */
    public static double discountFactor(double m, boolean imm) {
        if (!(m > 0)) {
            throw domain("m must be positive", "m");
        }
        if (imm) {
            return 1.0;
        }
        double x = DF_RATE * m;
        return -Math.expm1(-x) / x;
    }

    private static void checkEnums(List<Counterparty> cps, String version, List<SingleNameHedge> single,
            List<IndexHedge> index) {
        if (!VERSIONS.contains(version)) {
            throw schema("version " + version + " is not listed", "version");
        }
        for (Counterparty c : cps) {
            sectorQuality(c.sector(), c.quality());
        }
        for (SingleNameHedge h : single) {
            if (!RELATIONS.containsKey(h.relation())) {
                throw schema("relation " + h.relation() + " is not listed", "relation");
            }
            sectorQuality(h.sector(), h.quality());
        }
        for (IndexHedge ih : index) {
            for (Constituent k : ih.constituents()) {
                sectorQuality(k.sector(), k.quality());
            }
        }
    }

    private static void sectorQuality(String sector, String quality) {
        if (!SECTORS.contains(sector)) {
            throw schema("sector " + sector + " is not listed", "sector");
        }
        if (!QUALITIES.contains(quality)) {
            throw schema("quality " + quality + " is not listed", "quality");
        }
    }

    private static void baStructure(List<Counterparty> cps, String version, List<SingleNameHedge> single,
            List<IndexHedge> index) {
        Set<String> ids = new HashSet<>();
        for (Counterparty c : cps) {
            if (!ids.add(c.id())) {
                throw input("counterparty " + c.id() + " appears twice", "id"); // KR-121
            }
        }
        if (version.equals("REDUCED") && (!single.isEmpty() || !index.isEmpty())) {
            throw input("hedges are recognised only in the FULL version", "single_name_hedges");
        }
        for (SingleNameHedge h : single) {
            if (!ids.contains(h.counterparty())) {
                throw input("hedge references unknown counterparty " + h.counterparty(), "counterparty");
            }
        }
    }

    private static void baDomain(List<Counterparty> cps, List<SingleNameHedge> single, List<IndexHedge> index) {
        for (Counterparty c : cps) {
            for (NettingSet ns : c.nettingSets()) {
                if (ns.ead() < 0) {
                    throw domain("counterparty " + c.id() + ": ead must not be negative", "ead");
                }
                if (!(ns.m() > 0)) {
                    throw domain("counterparty " + c.id() + ": m must be positive", "m");
                }
            }
        }
        for (SingleNameHedge h : single) {
            if (!(h.m() > 0)) {
                throw domain("hedge m must be positive", "m");
            }
            if (h.notional() < 0) {
                throw domain("hedge notional must not be negative", "notional");
            }
        }
        for (IndexHedge ih : index) {
            if (!(ih.m() > 0)) {
                throw domain("index hedge m must be positive", "m");
            }
            if (ih.notional() < 0) {
                throw domain("index hedge notional must not be negative", "notional");
            }
            List<Double> w = new ArrayList<>();
            for (Constituent k : ih.constituents()) {
                if (k.weight() < 0) {
                    throw domain("index weights must not be negative", "weight"); // KR-122
                }
                w.add(k.weight());
            }
            if (!(Math.abs(fsum(w) - 1.0) <= WEIGHT_TOLERANCE)) {
                throw domain("index weights must sum to 1 within 1e-12", "weight");
            }
        }
    }

    private static double kReduced(List<Double> scva) {
        double systematic = RHO * fsum(scva);
        List<Double> sq = new ArrayList<>();
        for (double s : scva) {
            sq.add(s * s);
        }
        return Math.sqrt(systematic * systematic + (1.0 - RHO * RHO) * fsum(sq));
    }

    /**
     * BA-CVA capital, reduced (MAR50.14) or full (MAR50.20), with its intermediates.
     *
     * @param cps counterparties
     * @param version REDUCED or FULL
     * @param single single-name hedges (FULL only)
     * @param index index hedges (FULL only)
     * @return the result
     */
    public static BaResult baCva(List<Counterparty> cps, String version, List<SingleNameHedge> single,
            List<IndexHedge> index) {
        checkEnums(cps, version, single, index);
        baStructure(cps, version, single, index);
        baDomain(cps, single, index);
        List<double[]> dfs = new ArrayList<>();
        List<Double> scva = new ArrayList<>();
        for (Counterparty c : cps) {
            double[] df = new double[c.nettingSets().size()];
            List<Double> terms = new ArrayList<>();
            for (int i = 0; i < df.length; i++) {
                NettingSet ns = c.nettingSets().get(i);
                df[i] = discountFactor(ns.m(), ns.imm());
                terms.add(ns.m() * ns.ead() * df[i]);
            }
            dfs.add(df);
            scva.add(rw(c.sector(), c.quality()) * fsum(terms) / ALPHA); // MAR50.15
        }
        double kRed = kReduced(scva);
        Double ih = null;
        Double kHedged = null;
        Double kFull = null;
        double[] snh = null;
        double[] hma = null;
        double capital;
        if (version.equals("FULL")) {
            Map<String, Integer> position = new HashMap<>();
            List<List<Double>> snhParts = new ArrayList<>();
            List<List<Double>> hmaParts = new ArrayList<>();
            for (int n = 0; n < cps.size(); n++) {
                position.put(cps.get(n).id(), n);
                snhParts.add(new ArrayList<>());
                hmaParts.add(new ArrayList<>());
            }
            for (SingleNameHedge h : single) {
                double r = Double.parseDouble((String) table("ba.r_hc").get(RELATIONS.get(h.relation())));
                double x = rw(h.sector(), h.quality()) * h.m() * h.notional() * discountFactor(h.m(), false);
                int p = position.get(h.counterparty());
                snhParts.get(p).add(r * x); // MAR50.23
                hmaParts.get(p).add((1.0 - r * r) * x * x); // MAR50.25
            }
            snh = new double[cps.size()];
            hma = new double[cps.size()];
            for (int n = 0; n < cps.size(); n++) {
                snh[n] = fsum(snhParts.get(n));
                hma[n] = fsum(hmaParts.get(n));
            }
            List<Double> ihTerms = new ArrayList<>();
            for (IndexHedge i : index) {
                List<Double> wr = new ArrayList<>();
                for (Constituent k : i.constituents()) {
                    wr.add(k.weight() * rw(k.sector(), k.quality()));
                }
                ihTerms.add(INDEX_SCALAR * fsum(wr) * i.m() * i.notional() * discountFactor(i.m(), false));
            }
            ih = fsum(ihTerms); // MAR50.24
            List<Double> net = new ArrayList<>();
            List<Double> netSq = new ArrayList<>();
            List<Double> hmaList = new ArrayList<>();
            for (int n = 0; n < cps.size(); n++) {
                double x = scva.get(n) - snh[n];
                net.add(x);
                netSq.add(x * x);
                hmaList.add(hma[n]);
            }
            double systematic = RHO * fsum(net) - ih;
            kHedged = Math.sqrt(systematic * systematic + (1.0 - RHO * RHO) * fsum(netSq) + fsum(hmaList)); // MAR50.21
            kFull = BETA * kRed + (1.0 - BETA) * kHedged; // MAR50.20
            capital = DS * kFull;
        } else {
            capital = DS * kRed;
        }
        List<CounterpartyRow> rows = new ArrayList<>();
        for (int n = 0; n < cps.size(); n++) {
            List<Double> df = new ArrayList<>();
            for (double d : dfs.get(n)) {
                df.add(d);
            }
            rows.add(new CounterpartyRow(cps.get(n).id(), scva.get(n), snh == null ? null : snh[n],
                    hma == null ? null : hma[n], df));
        }
        return new BaResult(version, rows, ih, kRed, kHedged, kFull, capital, RWA_MULTIPLIER * capital, LABEL);
    }

    // --- SA-CVA ------------------------------------------------------------------------------------------------

    /** MAR50.43, KR-63. */
    public static final List<String> RISK_CLASSES = List.of("IR", "FX", "CCS", "RCS", "EQ", "COM");
    /** Delta and vega. */
    public static final List<String> KINDS = List.of("DELTA", "VEGA");
    /** Output and processing order of the class keys (KR-125); CCS has no vega. */
    public static final List<String> CLASS_KEYS;

    static {
        List<String> keys = new ArrayList<>();
        for (String c : RISK_CLASSES) {
            for (String k : KINDS) {
                if (!(c.equals("CCS") && k.equals("VEGA"))) {
                    keys.add(c + "." + k);
                }
            }
        }
        CLASS_KEYS = List.copyOf(keys);
    }

    /** MAR50.56(1), "inflation" included. */
    static final List<String> IR_TENORS = strings(list("ir.tenors_specified"));
    /** KR-120: the parallel-shift factor of an unspecified currency (MAR50.57). */
    public static final String IR_CURVE = "CURVE";
    /** IR delta factor names (KR-120). */
    public static final List<String> IR_DELTA_FACTORS;
    /** IR vega factor names (KR-120, MAR50.58(1)). */
    public static final List<String> IR_VEGA_FACTORS = List.of("IR_VOL", "INFLATION_VOL");
    /** MAR50.65(1). */
    public static final List<String> CCS_TENORS = strings(list("ccs.tenors"));
    /** MAR50.65(3) Table 7: 1a, 1b, 2 to 8. */
    static final List<String> CCS_BUCKETS = List.copyOf(table("ccs.rw").keySet());

    static {
        List<String> f = new ArrayList<>(IR_TENORS);
        f.add(IR_CURVE);
        IR_DELTA_FACTORS = List.copyOf(f);
    }

    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");

    // ===== OPEN READING KR-121 (CCS buckets 1a and 1b), under check against the Basel text by another lane. =====
    // true: 1a and 1b select the risk weight and aggregate as one bucket "1" (the Python reference). false: they are
    // two buckets "1a" and "1b" (gamma between them then needs a ruling; ccsGamma maps both to Table 6 row 1).
    static final boolean CCS_MERGE_1A_1B = true;

    // ===== OPEN READING KR-124 (equity vega 78% buckets), under check against the Basel text by another lane. =====
    // MAR50.73(3) "large market capitalisation buckets": Table 11 "Large" buckets 1 to 8 and the index bucket 12.
    static final Set<Integer> EQ_VEGA_LARGE_CAP = Set.of(1, 2, 3, 4, 5, 6, 7, 8, 12);

    private static List<String> strings(List<Object> l) {
        List<String> out = new ArrayList<>();
        for (Object o : l) {
            out.add((String) o);
        }
        return List.copyOf(out);
    }

    private static int numbered(String cls) {
        return table(cls.toLowerCase(java.util.Locale.ROOT) + ".rw").size();
    }

    /**
     * A counterparty credit spread factor (KR-63).
     *
     * @param name counterparty name
     * @param tenor one of {@link #CCS_TENORS}
     * @param quality IG or HY_NR
     * @param legalGroup optional legal group
     * @param index bucket 8: index name
     * @param series bucket 8: index series
     */
    public record CreditFactor(String name, String tenor, String quality, String legalGroup, String index,
            String series) {}

    /**
     * One SA-CVA sensitivity. Outside CCS {@code factor} is set and {@code credit} null; for CCS the reverse.
     *
     * @param bucket bucket label
     * @param factor factor name (not CCS)
     * @param credit credit factor (CCS)
     * @param sCva sensitivity of CVA
     * @param sHdg sensitivity of the eligible hedges
     */
    public record Sensitivity(String bucket, String factor, CreditFactor credit, double sCva, double sHdg) {}

    /**
     * One bucket of the output.
     *
     * @param bucket aggregation bucket label
     * @param kB K_b
     * @param sB S_b, clipped
     * @param sumWs sum of WS_k before clipping
     * @param floored true when the radicand was below 0 (KR-62, KR-127)
     */
    public record BucketRow(String bucket, double kB, double sB, double sumWs, boolean floored) {}

    /**
     * One risk class and kind.
     *
     * @param buckets bucket rows in SBM order
     * @param k the class capital
     */
    public record ClassResult(List<BucketRow> buckets, double k) {}

    /**
     * The SA-CVA result.
     *
     * @param classes per class key, in the order of {@link #CLASS_KEYS}
     * @param mCva multiplier used
     * @param total sum of the class capitals
     * @param rwa 12.5 times total
     * @param label KR-69 label
     */
    public record SaResult(Map<String, ClassResult> classes, double mCva, double total, double rwa, String label) {}

    private record Entry(String bucket, List<String> key, double rw, Sensitivity s) {}

    /** A table cell such as "0.90 legally related": its leading number. */
    static double first(String text) {
        return Double.parseDouble(text.trim().split("\\s+")[0]);
    }

    private static double upper(String key, int a, int b) {
        @SuppressWarnings("unchecked")
        List<Object> row = (List<Object>) list(key).get(Math.min(a, b));
        return Double.parseDouble((String) Objects.requireNonNull(row.get(Math.max(a, b))));
    }

    /** MAR50.56(4) Table 4 (specified currencies), symmetric. */
    static double irRho(String a, String b) {
        int i = Math.min(IR_TENORS.indexOf(a), IR_TENORS.indexOf(b));
        int j = Math.max(IR_TENORS.indexOf(a), IR_TENORS.indexOf(b));
        @SuppressWarnings("unchecked")
        Map<String, Object> row = (Map<String, Object>) table("ir.rho_specified").get(IR_TENORS.get(i));
        return Double.parseDouble((String) row.get(IR_TENORS.get(j)));
    }

    @SuppressWarnings("unchecked")
    private static String cell(Map<String, Object> p, String key, int i) {
        return (String) ((List<Object>) p.get(key)).get(i);
    }

    /** MAR50.65(4)-(5): rho_tenor x rho_name x rho_quality. */
    @SuppressWarnings("unchecked")
    static double ccsRho(String bucket, CreditFactor f, CreditFactor g) {
        Map<String, Object> spec = table("ccs.rho");
        Map<String, Object> p;
        double name;
        if (bucket.equals("8")) {
            p = (Map<String, Object>) spec.get("bucket_8");
            if (Objects.equals(f.index(), g.index()) && Objects.equals(f.series(), g.series())) {
                name = first(cell(p, "name", 0));
            } else if (Objects.equals(f.index(), g.index())) {
                name = first(cell(p, "name", 1));
            } else {
                name = first(cell(p, "name", 2));
            }
        } else {
            p = (Map<String, Object>) spec.get("buckets_1_7");
            if (f.name().equals(g.name())) {
                name = first(cell(p, "name", 0));
            } else if (f.legalGroup() != null && f.legalGroup().equals(g.legalGroup())) {
                name = first(cell(p, "name", 1));
            } else {
                name = first(cell(p, "name", 2));
            }
        }
        double tenor = first(cell(p, "tenor", f.tenor().equals(g.tenor()) ? 0 : 1));
        double quality = first(cell(p, "quality", f.quality().equals(g.quality()) ? 0 : 1));
        return tenor * name * quality;
    }

    /** MAR50.67 Table 9 rows: 1/8 .. 7/14 are rows 0..6, then 15, 16, 17 are rows 7, 8, 9 (KR-125). */
    static int rcsRow(int b) {
        return b <= 7 ? b - 1 : b - 8;
    }

    static double rcsGamma(String b, String c) {
        int x = Integer.parseInt(b);
        int y = Integer.parseInt(c);
        double g = upper("rcs.gamma_same_quality", rcsRow(x), rcsRow(y));
        if (x <= 14 && y <= 14 && (x <= 7) != (y <= 7)) {
            g /= num("rcs.gamma_cross_quality_divisor"); // MAR50.67(2)
        }
        return g;
    }

    /** MAR50.71. */
    static double eqGamma(String b, String c) {
        int x = Integer.parseInt(b);
        int y = Integer.parseInt(c);
        Map<String, Object> g = table("eq.gamma");
        String key;
        if (x == 11 || y == 11) {
            key = "with_11";
        } else if (x <= 10 && y <= 10) {
            key = "within_1_10";
        } else if ((x == 12 && y == 13) || (x == 13 && y == 12)) {
            key = "12_13";
        } else {
            key = "12_or_13_with_1_10";
        }
        return Double.parseDouble((String) g.get(key));
    }

    /** MAR50.75. */
    static double comGamma(String b, String c) {
        Map<String, Object> g = table("com.gamma");
        boolean eleven = Integer.parseInt(b) == 11 || Integer.parseInt(c) == 11;
        return Double.parseDouble((String) g.get(eleven ? "with_11" : "within_1_10"));
    }

    private static int ccsRow(String b) {
        return b.equals("1a") || b.equals("1b") ? 0 : Integer.parseInt(b) - 1;
    }

    /** MAR50.64 Table 6; buckets 1a and 1b are bucket 1 (KR-121). */
    static double ccsGamma(String b, String c) {
        return upper("ccs.gamma", ccsRow(b), ccsRow(c));
    }

    /** The aggregation bucket of a CCS bucket label (KR-121, see {@link #CCS_MERGE_1A_1B}). */
    static String ccsAggregationBucket(String b) {
        return CCS_MERGE_1A_1B && (b.equals("1a") || b.equals("1b")) ? "1" : b;
    }

    /** The equity vega risk weight key of a bucket (KR-124, see {@link #EQ_VEGA_LARGE_CAP}). */
    static String eqVegaKey(int bucket) {
        return EQ_VEGA_LARGE_CAP.contains(bucket) ? "large_cap" : "other";
    }

    /** SBM bucket order: by length, then text ({@code frtb.bucket_key}). */
    static final Comparator<String> BUCKET_ORDER = Comparator.comparingInt(String::length)
            .thenComparing(Comparator.naturalOrder());

    private static String[] parseClassKey(String key) {
        int dot = key.indexOf('.');
        String cls = dot < 0 ? key : key.substring(0, dot);
        String kind = dot < 0 ? "" : key.substring(dot + 1);
        if (!RISK_CLASSES.contains(cls) || !KINDS.contains(kind)) {
            throw schema("class " + key + " is not listed", "classes");
        }
        return new String[] {cls, kind};
    }

    private static void checkFactorSchema(String cls, String kind, Sensitivity s) {
        if (cls.equals("CCS")) {
            if (s.credit() == null) {
                throw schema("a CCS factor is an object", "factor");
            }
            if (!CCS_TENORS.contains(s.credit().tenor())) {
                throw schema("tenor " + s.credit().tenor() + " is not listed", "tenor");
            }
            if (!QUALITIES.contains(s.credit().quality())) {
                throw schema("quality " + s.credit().quality() + " is not listed", "quality");
            }
            return;
        }
        if (s.factor() == null) {
            throw schema("the factor is a string outside CCS", "factor");
        }
        if (cls.equals("IR")) {
            List<String> allowed = kind.equals("DELTA") ? IR_DELTA_FACTORS : IR_VEGA_FACTORS;
            if (!allowed.contains(s.factor())) {
                throw schema("IR factor " + s.factor() + " is not listed", "factor");
            }
        }
    }

    private static Entry entry(String cls, String kind, Sensitivity s, Set<String> specified, String rep) {
        String b = s.bucket();
        if (cls.equals("IR") || cls.equals("FX")) {
            if (!CURRENCY.matcher(b).matches()) {
                throw input(cls + " bucket " + b + " is not a currency code", "bucket");
            }
            if (cls.equals("FX")) {
                if (b.equals(rep)) {
                    throw input("the reporting currency is not an FX bucket (MAR50.59)", "bucket");
                }
                return new Entry(b, List.of(), num(kind.equals("DELTA") ? "fx.delta_rw" : "fx.vega_rw"), s);
            }
            String f = s.factor();
            if (kind.equals("VEGA")) {
                return new Entry(b, List.of(f), num("ir.vega_rw"), s);
            }
            if (specified.contains(b)) {
                if (f.equals(IR_CURVE)) {
                    throw input(b + " is a specified currency: tenor factors (MAR50.56)", "factor");
                }
                return new Entry(b, List.of(f), Double.parseDouble((String) table("ir.rw_specified").get(f)), s);
            }
            if (!f.equals(IR_CURVE) && !f.equals("inflation")) {
                throw input(b + " is not a specified currency: CURVE and inflation", "factor");
            }
            return new Entry(b, List.of(f), num("ir.rw_other_ccy"), s);
        }
        if (cls.equals("CCS")) {
            if (!CCS_BUCKETS.contains(b)) {
                throw input("CCS bucket " + b + " is not listed", "bucket");
            }
            CreditFactor f = s.credit();
            @SuppressWarnings("unchecked")
            List<Object> row = (List<Object>) table("ccs.rw").get(b);
            double rw = Double.parseDouble((String) row.get(QUALITIES.indexOf(f.quality())));
            String agg = ccsAggregationBucket(b);
            if (b.equals("8")) {
                if (f.index() == null || f.series() == null) {
                    throw input("bucket 8 factors need index and series (KR-63)", "index");
                }
                return new Entry(agg, List.of(f.index(), f.series(), f.tenor()), rw, s);
            }
            return new Entry(agg, List.of(f.name(), f.tenor()), rw, s);
        }
        int n = numbered(cls);
        int bucket = -1;
        for (int i = 1; i <= n; i++) {
            if (b.equals(Integer.toString(i))) {
                bucket = i;
            }
        }
        if (bucket < 0) {
            throw input(cls + " bucket " + b + " is not listed", "bucket");
        }
        double rw;
        String lower = cls.toLowerCase(java.util.Locale.ROOT);
        if (kind.equals("DELTA")) {
            rw = Double.parseDouble((String) table(lower + ".rw").get(b));
        } else if (cls.equals("EQ")) {
            rw = Double.parseDouble((String) table("eq.vega_rw").get(eqVegaKey(bucket)));
        } else {
            rw = num(lower + ".vega_rw");
        }
        return new Entry(b, List.of(), rw, s);
    }

    /** A CCS name (bucket 8: an index series) has one quality and one legal group (KR-123). */
    private static void checkNames(List<Entry> entries) {
        Map<List<Object>, List<String>> seen = new HashMap<>();
        for (Entry e : entries) {
            CreditFactor f = e.s().credit();
            List<Object> who = e.bucket().equals("8") ? java.util.Arrays.asList(e.bucket(), f.index(), f.series())
                    : java.util.Arrays.asList(e.bucket(), f.name());
            List<String> attrs = java.util.Arrays.asList(f.quality(), f.legalGroup());
            List<String> had = seen.putIfAbsent(who, attrs);
            if (had != null && !had.equals(attrs)) {
                throw input("name " + f.name() + " has two qualities or legal groups", "factor");
            }
        }
    }

    private static FrtbSbm.FactorRho rhoFor(String cls, String kind, String bucket, List<Entry> members) {
        if (cls.equals("IR") && kind.equals("VEGA")) {
            double r = num("ir.vega_rho");
            return (a, b) -> r;
        }
        if (cls.equals("IR")) {
            return (a, b) -> {
                String x = members.get(Integer.parseInt(a.get(0))).key().get(0);
                String y = members.get(Integer.parseInt(b.get(0))).key().get(0);
                return x.equals(IR_CURVE) || y.equals(IR_CURVE) ? num("ir.rho_other_ccy_curve_inflation")
                        : irRho(x, y);
            };
        }
        if (cls.equals("CCS")) {
            return (a, b) -> ccsRho(bucket, members.get(Integer.parseInt(a.get(0))).s().credit(),
                    members.get(Integer.parseInt(b.get(0))).s().credit());
        }
        return (a, b) -> 1.0; // one factor per bucket: never called with two entries
    }

    private static FrtbSbm.PositionGamma gammaFor(String cls, List<String> order) {
        return switch (cls) {
            case "IR" -> {
                double g = num("ir.gamma");
                yield (b, c) -> g;
            }
            case "FX" -> {
                double g = num("fx.gamma");
                yield (b, c) -> g;
            }
            case "CCS" -> (b, c) -> ccsGamma(order.get(b), order.get(c));
            case "RCS" -> (b, c) -> rcsGamma(order.get(b), order.get(c));
            case "EQ" -> (b, c) -> eqGamma(order.get(b), order.get(c));
            default -> (b, c) -> comGamma(order.get(b), order.get(c));
        };
    }

    private static ClassResult classCapital(String cls, String kind, List<Entry> entries, double mCva) {
        Map<String, List<Entry>> byBucket = new LinkedHashMap<>();
        for (Entry e : entries) {
            byBucket.computeIfAbsent(e.bucket(), k -> new ArrayList<>()).add(e);
        }
        List<String> order = new ArrayList<>(byBucket.keySet());
        order.sort(BUCKET_ORDER);
        double[] ks = new double[order.size()];
        double[] sb = new double[order.size()];
        List<BucketRow> rows = new ArrayList<>();
        for (int n = 0; n < order.size(); n++) {
            String name = order.get(n);
            List<Entry> members = byBucket.get(name);
            List<FrtbSbm.Ws> items = new ArrayList<>();
            double[] ws = new double[members.size()];
            double[] wshSq = new double[members.size()];
            for (int i = 0; i < members.size(); i++) {
                Entry e = members.get(i);
                ws[i] = e.rw() * e.s().sCva() - e.rw() * e.s().sHdg(); // MAR50.51-50.52
                double wsh = e.rw() * e.s().sHdg();
                wshSq[i] = wsh * wsh;
                items.add(new FrtbSbm.Ws(0, List.of(Integer.toString(i)), ws[i]));
            }
            double radicand = FrtbSbm.bucketRadicand(items, rhoFor(cls, kind, name, members))
                    + R_HEDGE * pySum(wshSq);
            double kB = Math.sqrt(Math.max(0.0, radicand)); // KR-62
            double total = pySum(ws);
            double sB = Math.max(-kB, Math.min(total, kB)); // MAR50.53(3)
            ks[n] = kB;
            sb[n] = sB;
            rows.add(new BucketRow(name, kB, sB, total, radicand < 0));
        }
        double k = mCva * Math.sqrt(Math.max(0.0, FrtbSbm.crossRadicand(ks, sb, gammaFor(cls, order))));
        return new ClassResult(rows, k);
    }

    /**
     * SA-CVA capital (MAR50.42-50.53): the sum of the delta and vega capital of every class given.
     *
     * @param classes class key ({@code IR.DELTA} ...) to sensitivities, in input order
     * @param reportingCurrency three upper-case letters
     * @param mCva multiplier, at least 1
     * @return the result
     */
    public static SaResult saCva(Map<String, List<Sensitivity>> classes, String reportingCurrency, double mCva) {
        Map<String, String[]> parsed = new LinkedHashMap<>();
        for (String key : classes.keySet()) {
            parsed.put(key, parseClassKey(key));
        }
        for (Map.Entry<String, List<Sensitivity>> c : classes.entrySet()) {
            String[] ck = parsed.get(c.getKey());
            for (Sensitivity s : c.getValue()) {
                checkFactorSchema(ck[0], ck[1], s);
            }
        }
        if (classes.containsKey("CCS.VEGA")) {
            throw input("counterparty credit spread has no vega (MAR50.45)", "classes");
        }
        if (!CURRENCY.matcher(reportingCurrency).matches()) {
            throw input("reporting_currency is not a currency code", "reporting_currency");
        }
        Set<String> specified = new HashSet<>();
        for (Object c : list("ir.specified_currencies")) {
            specified.add(c.equals("reporting") ? reportingCurrency : (String) c);
        }
        Map<String, List<Entry>> built = new LinkedHashMap<>();
        for (String key : CLASS_KEYS) {
            if (!classes.containsKey(key)) {
                continue;
            }
            String[] ck = parsed.get(key);
            List<Entry> entries = new ArrayList<>();
            for (Sensitivity s : classes.get(key)) {
                entries.add(entry(ck[0], ck[1], s, specified, reportingCurrency));
            }
            Set<List<Object>> seen = new HashSet<>();
            for (Entry e : entries) {
                if (!seen.add(List.of(e.bucket(), e.key()))) {
                    throw input(key + ": bucket " + e.bucket() + " holds one risk factor twice", "factor");
                }
            }
            if (ck[0].equals("CCS")) {
                checkNames(entries);
            }
            built.put(key, entries);
        }
        if (!(mCva >= 1)) {
            throw domain("m_cva must be at least 1 (MAR50.41)", "m_cva");
        }
        Map<String, ClassResult> out = new LinkedHashMap<>();
        double[] ks = new double[built.size()];
        int n = 0;
        for (Map.Entry<String, List<Entry>> e : built.entrySet()) {
            String[] ck = parsed.get(e.getKey());
            ClassResult r = classCapital(ck[0], ck[1], e.getValue(), mCva);
            out.put(e.getKey(), r);
            ks[n++] = r.k();
        }
        double total = StressDrift.fsum(ks);
        return new SaResult(out, mCva, total, RWA_MULTIPLIER * total, LABEL);
    }
}
