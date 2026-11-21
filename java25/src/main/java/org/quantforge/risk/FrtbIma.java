package org.quantforge.risk;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;
import org.quantforge.research.StressDrift;

/**
 * FRTB internal models approach, plan item K-8f (specifications/06-risk/frtb-ima.md; rulings KR-50, KR-56 to KR-61,
 * KR-67 to KR-69 and KR-305 to KR-310 of specifications/stage-k-rulings-w2.md): the PLA test, liquidity horizons, ES
 * with the liquidity-horizon cascade, stressed ES, IMCC, SES, the capital aggregation and the RFET. A port of
 * python/quantforge_core/frtb_ima.py; parameters from {@link FrtbImaTables}, generated from
 * specifications/tables/stage_k/mar31_rfet.json, mar32_pla.json and mar33_ima.json.
 *
 * <p>The PLA statistics are written from the spec's definitions (MAR32.36 to MAR32.41, KR-56, KR-305), with no
 * statistics library: average ranks, Pearson correlation of the ranks in exact integer sums, the two-sample KS count
 * by a merge of the sorted lists, and the Kolmogorov tail by its two series. Error order KR-67: E_LIMIT, structural
 * E_INPUT, E_DOMAIN here; E_SCHEMA and the finite rule in the input layer.
 */
public final class FrtbIma {
    private FrtbIma() {}

    /** KR-69. */
    public static final String LABEL = FrtbDrc.LABEL;
    /** KR-67: P&amp;L points per list. */
    public static final int MAX_PNL = 1_000_000;
    /** KR-67: charges, desks, constituents, dates. */
    public static final int MAX_LIST = 100_000;
    /** KR-56: the fewest observations of a PLA test. */
    static final int PLA_MIN_N = 3;
    /** MAR33.45. */
    static final double SURCHARGE_K = 0.5;
    /** MAR33.15 risk classes, in output order (KR-302). */
    public static final List<String> IMCC_CLASSES = List.of("IR", "EQ", "FX", "COM", "CS");
    /** MAR33.12 Table 2 categories. */
    public static final List<String> LH_CATEGORIES = List.of(FrtbImaTables.LH_CATEGORY);

    // ---- PLA (MAR32.34 to MAR32.44, KR-56, KR-305) ----------------------------------------------------------

    /** The result of {@link #pla}. */
    public record Pla(long n, double spearman, double ks, long ksCount, String zone, double ksPvalueAsymptotic,
            boolean regulatoryWindow) {}

    /** Twice the average rank (ties share the mean of their positions), so every value is an integer. */
    static long[] doubledRanks(double[] x) {
        Integer[] order = new Integer[x.length];
        for (int k = 0; k < x.length; k++) {
            order[k] = k;
        }
        Arrays.sort(order, (a, b) -> x[a] < x[b] ? -1 : x[a] > x[b] ? 1 : 0); // stable; -0.0 ties 0.0
        long[] out = new long[x.length];
        int i = 0;
        while (i < order.length) {
            int j = i;
            while (j + 1 < order.length && x[order[j + 1]] == x[order[i]]) {
                j++;
            }
            long doubled = (long) i + j + 2; // ranks i+1 .. j+1, mean (i + j + 2) / 2
            for (int k = i; k <= j; k++) {
                out[order[k]] = doubled;
            }
            i = j + 1;
        }
        return out;
    }

    /**
     * MAR32.36 to MAR32.38: the Pearson correlation of the average ranks, on centred doubled ranks 2r - (n + 1)
     * (integers in [-(n-1), n-1]; every sum exact in 64 bits up to n = 1,000,000), one rounding at the end, clamped
     * to [-1, 1] (KR-305).
     */
    public static double spearman(double[] hpl, double[] rtpl) {
        int n = hpl.length;
        long[] a = doubledRanks(hpl);
        long[] b = doubledRanks(rtpl);
        long sxy = 0;
        long sxx = 0;
        long syy = 0;
        for (int k = 0; k < n; k++) {
            long u = a[k] - (n + 1L);
            long v = b[k] - (n + 1L);
            sxy += u * v;
            sxx += u * u;
            syy += v * v;
        }
        if (sxx == 0 || syy == 0) {
            throw new QfError("E_DOMAIN", "a series is constant: its rank variance is 0", sxx == 0 ? "hpl" : "rtpl");
        }
        return Math.max(-1.0, Math.min(1.0, (double) sxy / Math.sqrt((double) sxx * (double) syy)));
    }

    /** MAR32.39 to MAR32.41 in counts: max over pooled x of |#{rtpl &lt;= x} - #{hpl &lt;= x}| (KR-56). */
    public static long ksCount(double[] hpl, double[] rtpl) {
        double[] h = hpl.clone();
        double[] r = rtpl.clone();
        Arrays.sort(h);
        Arrays.sort(r);
        int i = 0;
        int j = 0;
        long best = 0;
        while (i < h.length || j < r.length) {
            double v = i < h.length && (j >= r.length || h[i] <= r[j]) ? h[i] : r[j];
            while (i < h.length && h[i] <= v) {
                i++;
            }
            while (j < r.length && r[j] <= v) {
                j++;
            }
            best = Math.max(best, Math.abs((long) j - i));
        }
        return best;
    }

    /**
     * Kolmogorov tail Q_KS(x) = 2 sum_{k&gt;=1} (-1)^(k-1) exp(-2 k^2 x^2) (KR-56), evaluated as KR-305: 1 at
     * x &lt;= 0; for 0 &lt; x &lt; 1 the theta series 1 - sqrt(2 pi)/x sum_{k&gt;=1} exp(-(2k-1)^2 pi^2 / (8 x^2));
     * terms are added in order of k until one is 0 in binary64.
     */
    public static double kolmogorovQ(double x) {
        if (x <= 0) {
            return 1.0;
        }
        List<Double> terms = new ArrayList<>();
        if (x < 1) {
            double c = Math.PI * Math.PI / (8 * x * x);
            for (long k = 1;; k++) {
                double t = Math.exp(-(double) ((2 * k - 1) * (2 * k - 1)) * c);
                if (t == 0) {
                    break;
                }
                terms.add(t);
            }
            return Math.max(0.0, 1.0 - Math.sqrt(2 * Math.PI) / x * FrtbDrc.fsum(terms));
        }
        for (long k = 1;; k++) {
            double t = Math.exp(-2.0 * k * k * x * x);
            if (t == 0) {
                break;
            }
            terms.add(k % 2 == 1 ? t : -t);
        }
        return Math.min(1.0, 2 * FrtbDrc.fsum(terms));
    }

    private static double pvalue(double ks, long n) {
        return kolmogorovQ(ks * Math.sqrt(n / 2.0));
    }

    /** P&amp;L attribution test statistics and zone for one desk (MAR32.34 to MAR32.44). */
    public static Pla pla(double[] hpl, double[] rtpl) {
        int n = hpl.length;
        if (n > MAX_PNL || rtpl.length > MAX_PNL) {
            throw new QfError("E_LIMIT", "a P&L list is above its limit of " + MAX_PNL, n > MAX_PNL ? "hpl" : "rtpl");
        }
        if (rtpl.length != n) {
            throw new QfError("E_INPUT", "hpl and rtpl differ in length", "rtpl");
        }
        if (n < PLA_MIN_N) {
            throw new QfError("E_DOMAIN", "at least " + PLA_MIN_N + " observations are needed", "hpl");
        }
        double rs = spearman(hpl, rtpl);
        long d = ksCount(hpl, rtpl);
        double ks = (double) d / n;
        String zone;
        if (rs > FrtbImaTables.PLA_GREEN_SPEARMAN && 100 * d < FrtbImaTables.PLA_GREEN_KS_PERCENT * n) {
            zone = "GREEN";
        } else if (rs < FrtbImaTables.PLA_RED_SPEARMAN || 100 * d > FrtbImaTables.PLA_RED_KS_PERCENT * n) {
            zone = "RED";
        } else {
            zone = "AMBER";
        }
        return new Pla(n, rs, ks, d, zone, pvalue(ks, n), n == FrtbImaTables.PLA_WINDOW);
    }

    /** Q_KS(ks sqrt(n/2)), for the printed p-values of MAR32.42 (KR-305: n &gt;= 1). */
    public static double plaKsPvalue(double ks, long n) {
        if (!(ks >= 0 && ks <= 1)) {
            throw new QfError("E_DOMAIN", "ks must be in [0, 1]", "ks");
        }
        if (n < 1) {
            throw new QfError("E_DOMAIN", "n must be at least 1", "n");
        }
        return pvalue(ks, n);
    }

    // ---- Liquidity horizons (MAR33.12, KR-60, KR-306) ------------------------------------------------------

    /**
     * One index constituent (MAR33.12 FAQ5).
     *
     * @param weight weight in the index
     * @param n the constituent's liquidity horizon
     */
    public record Constituent(double weight, long n) {}

    /** The result of {@link #liquidityHorizon}. */
    public record Horizon(long n, long tableN, String rule) {}

    private static Set<String> pair(String text) {
        int k = text.indexOf('/');
        String a = k < 0 ? text : text.substring(0, k);
        String b = k < 0 ? "" : text.substring(k + 1);
        return Set.copyOf(new HashSet<>(List.of(a, b)));
    }

    private static String[] parts(String text) {
        int k = text.indexOf('/');
        return k < 0 ? new String[] {text, ""} : new String[] {text.substring(0, k), text.substring(k + 1)};
    }

    /** KR-60: listed in footnote 309 in either order, or a first-order cross of two listed pairs. */
    public static boolean fxPairSpecified(String fxPair) {
        String[] ab = parts(fxPair);
        Set<Set<String>> listed = new HashSet<>();
        Set<String> partners = new TreeSet<>();
        for (String p : FrtbImaTables.SPECIFIED_FX_PAIRS) {
            listed.add(pair(p));
            partners.addAll(List.of(parts(p)));
        }
        if (listed.contains(pair(fxPair))) {
            return true;
        }
        for (String c : partners) {
            if (listed.contains(pair(ab[0] + "/" + c)) && listed.contains(pair(ab[1] + "/" + c))) {
                return true;
            }
        }
        return false;
    }

    static long nextHorizon(double x) {
        for (int h : FrtbImaTables.LIQUIDITY_HORIZONS) {
            if (h >= x) {
                return h;
            }
        }
        return FrtbImaTables.LIQUIDITY_HORIZONS[FrtbImaTables.LIQUIDITY_HORIZONS.length - 1];
    }

    private static boolean isHorizon(long n) {
        for (int h : FrtbImaTables.LIQUIDITY_HORIZONS) {
            if (h == n) {
                return true;
            }
        }
        return false;
    }

    private static int table(String category) {
        return FrtbImaTables.LH_DAYS[LH_CATEGORIES.indexOf(category)];
    }

    /**
     * MAR33.12 Table 2, footnote 309, FAQ4 (maturity) and FAQ5 (index constituents); KR-60, KR-306. Exactly one of
     * {@code category}, {@code fxPair} and {@code constituents} is non-null; {@code maturityDays} may be null.
     */
    public static Horizon liquidityHorizon(String category, String fxPair, List<Constituent> constituents,
            Double maturityDays) {
        int given = (category != null ? 1 : 0) + (fxPair != null ? 1 : 0) + (constituents != null ? 1 : 0);
        if (given != 1) {
            throw new QfError("E_INPUT", "give exactly one of category, fx_pair and constituents", "category");
        }
        if (constituents != null) {
            if (constituents.isEmpty()) {
                throw new QfError("E_INPUT", "constituents is empty", "constituents");
            }
            if (constituents.size() > MAX_LIST) {
                throw new QfError("E_LIMIT", "constituents is above its limit of " + MAX_LIST, "constituents");
            }
        }
        if (fxPair != null) {
            String[] ab = parts(fxPair);
            if (ab[0].equals(ab[1])) {
                throw new QfError("E_DOMAIN", "an FX pair needs two different currencies", "fx_pair");
            }
        }
        if (maturityDays != null && !(maturityDays > 0)) {
            throw new QfError("E_DOMAIN", "maturity_days must be above 0", "maturity_days");
        }
        if (constituents != null) {
            double[] w = new double[constituents.size()];
            for (int k = 0; k < w.length; k++) {
                Constituent c = constituents.get(k);
                if (!(c.weight() >= 0)) {
                    throw new QfError("E_DOMAIN", "a constituent weight is negative", "constituents/" + k + "/weight");
                }
                if (!isHorizon(c.n())) {
                    throw new QfError("E_DOMAIN", "a constituent n is not 10, 20, 40, 60 or 120",
                            "constituents/" + k + "/n");
                }
                w[k] = c.weight();
            }
            if (Math.abs(StressDrift.fsum(w) - 1) > 1e-12) {
                throw new QfError("E_DOMAIN", "constituent weights must sum to 1 within 1e-12", "constituents");
            }
        }
        long base;
        String rule;
        if (category != null) {
            base = table(category);
            rule = "table";
        } else if (fxPair != null) {
            base = fxPairSpecified(fxPair) ? table("FX_specified_pairs") : table("FX_pairs");
            rule = "fx_pair";
        } else {
            double[] wh = new double[constituents.size()];
            for (int k = 0; k < wh.length; k++) {
                wh[k] = constituents.get(k).weight() * constituents.get(k).n();
            }
            base = nextHorizon(StressDrift.fsum(wh));
            rule = "index";
        }
        long n = base;
        if (maturityDays != null && maturityDays < base) {
            n = nextHorizon(maturityDays);
            rule += "+maturity";
        }
        return new Horizon(n, base, rule);
    }

    // ---- ES, stressed ES, IMCC, SES (MAR33.4 to MAR33.17) --------------------------------------------------

    /** KR-57 printed factor (documentation; {@link #normalEsFactor} computes it, one ulp away). */
    static final double NORMAL_ES_FACTOR_DOC = 2.337802792201415;

    /** The result of {@link #esLh}. */
    public record EsLh(String mode, double[] esByHorizon, double es) {}

    /** The result of {@link #esStressed}: ratio, whether the floor at 1 binds, and ES_R,S max(1, ratio). */
    public record Stressed(double ratio, boolean ratioFloored, double es) {}

    /** The result of {@link #imcc}. */
    public record Imcc(double imccC, boolean portfolioFloored, Map<String, Double> classes,
            List<String> classesFloored, double imcc) {}

    /** The result of {@link #ses}: the three square-root terms and their sum. */
    public record Ses(double idioCredit, double idioEquity, double other, double ses) {}

    /** phi(z) / (1 - 0.975) with z = Phi^-1(0.975) (KR-57). */
    public static double normalEsFactor() {
        double z = Rng.ppnd16(FrtbImaTables.ES_CONFIDENCE);
        return Math.exp(-z * z / 2) / Math.sqrt(2 * Math.PI) / (1 - FrtbImaTables.ES_CONFIDENCE);
    }

    /** (LH_j - LH_{j-1}) / T, with 1 for j = 1: (1, 1, 2, 2, 6) (MAR33.4). */
    public static double[] horizonWeights() {
        int[] lh = FrtbImaTables.LIQUIDITY_HORIZONS;
        double[] out = new double[lh.length];
        for (int j = 0; j < lh.length; j++) {
            out[j] = j == 0 ? 1.0 : (double) (lh[j] - lh[j - 1]) / FrtbImaTables.BASE_HORIZON;
        }
        return out;
    }

    /** MAR33.4: sqrt(ES_1^2 + sum_{j&gt;=2} (ES_j sqrt((LH_j - LH_{j-1}) / 10))^2). */
    public static double esCascade(double[] es) {
        double[] w = horizonWeights();
        double[] t = new double[es.length];
        for (int j = 0; j < es.length; j++) {
            t[j] = w[j] * es[j] * es[j];
        }
        return Math.sqrt(StressDrift.fsum(t));
    }

    /** Liquidity-horizon-adjusted ES (MAR33.4, KR-57): exactly one of the three inputs, five entries. */
    public static EsLh esLh(double[] esT, double[] sigma, double[][] pnl) {
        if (pnl != null) {
            for (int j = 0; j < pnl.length; j++) {
                if (pnl[j].length > MAX_PNL) {
                    throw new QfError("E_LIMIT", "a P&L list is above its limit of " + MAX_PNL, "pnl/" + j);
                }
            }
        }
        int given = (esT != null ? 1 : 0) + (sigma != null ? 1 : 0) + (pnl != null ? 1 : 0);
        if (given != 1) {
            throw new QfError("E_INPUT", "give exactly one of es_t, sigma and pnl", "es_t");
        }
        String field = esT != null ? "es_t" : sigma != null ? "sigma" : "pnl";
        int len = esT != null ? esT.length : sigma != null ? sigma.length : pnl.length;
        int horizons = FrtbImaTables.LIQUIDITY_HORIZONS.length;
        if (len != horizons) {
            throw new QfError("E_INPUT", field + " must have exactly five entries", field);
        }
        double[] es = new double[horizons];
        if (pnl == null) {
            double[] nums = esT != null ? esT : sigma;
            for (int j = 0; j < horizons; j++) {
                if (nums[j] < 0) {
                    throw new QfError("E_DOMAIN", field + " entries must be 0 or above", field + "/" + j);
                }
            }
            double f = sigma != null ? normalEsFactor() : 1.0;
            for (int j = 0; j < horizons; j++) {
                es[j] = sigma != null ? f * nums[j] : nums[j];
            }
        } else {
            for (int j = 0; j < horizons; j++) {
                double v = pnl[j].length == 0 ? 0.0
                        : PortfolioRisk.historical(pnl[j], FrtbImaTables.ES_CONFIDENCE).es();
                if (v < 0) { // KR-307
                    throw new QfError("E_DOMAIN", "the ES of a P&L list is negative (its tail is a gain)", "pnl/" + j);
                }
                es[j] = v;
            }
        }
        return new EsLh(field, es, esCascade(es));
    }

    private static Stressed stressed(double[] t) {
        double ratio = t[1] / t[2];
        return new Stressed(ratio, ratio < 1, t[0] * Math.max(1.0, ratio));
    }

    private static void tripleDomain(double[] t, String path) {
        if (t[0] < 0 || t[1] < 0) {
            throw new QfError("E_DOMAIN", "ES must be 0 or above", path);
        }
        if (!(t[2] > 0)) {
            throw new QfError("E_DOMAIN", "es_rc must be above 0", path + "es_rc");
        }
    }

    /** MAR33.6 with the ratio floored at 1 (KR-58). */
    public static Stressed esStressed(double esRs, double esFc, double esRc) {
        double[] t = {esRs, esFc, esRc};
        tripleDomain(t, "");
        return stressed(t);
    }

    /**
     * MAR33.15: 0.5 IMCC(C) + 0.5 sum_i IMCC(C_i), each triple {es_rs, es_fc, es_rc} (KR-58); {@code classes} keyed
     * by IR, EQ, FX, COM, CS.
     */
    public static Imcc imcc(double[] portfolio, Map<String, double[]> classes) {
        if (classes.isEmpty()) {
            throw new QfError("E_INPUT", "classes is empty", "classes");
        }
        tripleDomain(portfolio, "portfolio.");
        for (String c : IMCC_CLASSES) {
            if (classes.containsKey(c)) {
                tripleDomain(classes.get(c), "classes." + c + ".");
            }
        }
        Stressed whole = stressed(portfolio);
        Map<String, Double> per = new LinkedHashMap<>();
        List<String> floored = new ArrayList<>();
        List<Double> sum = new ArrayList<>();
        for (String c : IMCC_CLASSES) {
            if (classes.containsKey(c)) {
                Stressed s = stressed(classes.get(c));
                per.put(c, s.es());
                sum.add(s.es());
                if (s.ratioFloored()) {
                    floored.add(c);
                }
            }
        }
        double total = FrtbImaTables.IMCC_RHO * whole.es() + (1 - FrtbImaTables.IMCC_RHO) * FrtbDrc.fsum(sum);
        return new Imcc(whole.es(), whole.ratioFloored(), per, floored, total);
    }

    private static double sumSquares(double[] v) {
        double[] sq = new double[v.length];
        for (int k = 0; k < v.length; k++) {
            sq[k] = v[k] * v[k];
        }
        return StressDrift.fsum(sq);
    }

    /** MAR33.17: sqrt(sum ISES_i^2) + sqrt(sum ISES_j^2) + sqrt((0.6 sum SES_k)^2 + 0.64 sum SES_k^2). */
    public static Ses ses(double[] idioCredit, double[] idioEquity, double[] other) {
        String[] names = {"idio_credit", "idio_equity", "other"};
        double[][] lists = {idioCredit, idioEquity, other};
        for (int i = 0; i < 3; i++) {
            if (lists[i].length > MAX_LIST) {
                throw new QfError("E_LIMIT", names[i] + " is above its limit of " + MAX_LIST, names[i]);
            }
        }
        for (int i = 0; i < 3; i++) {
            for (int k = 0; k < lists[i].length; k++) {
                if (lists[i][k] < 0) {
                    throw new QfError("E_DOMAIN", "a stress scenario charge is negative", names[i] + "/" + k);
                }
            }
        }
        double a = Math.sqrt(sumSquares(idioCredit));
        double b = Math.sqrt(sumSquares(idioEquity));
        double s = StressDrift.fsum(other);
        double rho = FrtbImaTables.SES_RHO;
        double rs = rho * s;
        double c = Math.sqrt(rs * rs + (1 - rho * rho) * sumSquares(other));
        return new Ses(a, b, c, a + b + c);
    }

    // ---- Capital (MAR33.41 to MAR33.45, KR-61, KR-308) ------------------------------------------------------

    /**
     * One trading desk of the capital aggregation.
     *
     * @param zone GREEN or AMBER
     * @param sa the desk's standardised-approach capital
     */
    public record Desk(String zone, double sa) {}

    /** The result of {@link #capital}. */
    public record Capital(double mC, double cA, double imaGa, double saGa, double k, double surcharge,
            double acrTotal) {}

    /** MAR32.9 Table 1 (KR-61). */
    public static double multiplier(long exceptions) {
        return exceptions < FrtbImaTables.MULTIPLIER.length ? FrtbImaTables.MULTIPLIER[(int) exceptions]
                : FrtbImaTables.MULTIPLIER_RED;
    }

    /** Aggregate capital requirement for market risk (MAR33.41 to MAR33.45). */
    public static Capital capital(double imccPrev, double sesPrev, double imccAvg, double sesAvg, long exceptions,
            double drc, List<Desk> desks, double cU, double saAll, double qualitativeAddon) {
        if (desks.size() > MAX_LIST) {
            throw new QfError("E_LIMIT", "desks is above its limit of " + MAX_LIST, "desks");
        }
        String[] names = {"imcc_prev", "ses_prev", "imcc_avg", "ses_avg", "drc", "c_u", "sa_all", "qualitative_addon"};
        double[] values = {imccPrev, sesPrev, imccAvg, sesAvg, drc, cU, saAll, qualitativeAddon};
        for (int i = 0; i < names.length; i++) {
            if (values[i] < 0) { // KR-308
                throw new QfError("E_DOMAIN", names[i] + " must be 0 or above", names[i]);
            }
        }
        if (exceptions < 0) {
            throw new QfError("E_DOMAIN", "exceptions must be 0 or above", "exceptions");
        }
        double[] all = new double[desks.size()];
        List<Double> amber = new ArrayList<>();
        for (int j = 0; j < all.length; j++) {
            Desk d = desks.get(j);
            if (d.sa() < 0) { // KR-308
                throw new QfError("E_DOMAIN", "a desk SA must be 0 or above", "desks/" + j + "/sa");
            }
            all[j] = d.sa();
            if (d.zone().equals("AMBER")) {
                amber.add(d.sa());
            }
        }
        double saGa = StressDrift.fsum(all);
        boolean hasAmber = !amber.isEmpty();
        if (hasAmber && saGa == 0) {
            throw new QfError("E_DOMAIN", "SA over the green and amber desks is 0 with an amber desk", "desks");
        }
        double mC = multiplier(exceptions) + qualitativeAddon;
        double cA = Math.max(imccPrev + sesPrev, mC * imccAvg + sesAvg);
        double imaGa = cA + drc;
        double k = hasAmber ? SURCHARGE_K * FrtbDrc.fsum(amber) / saGa : 0.0;
        double surcharge = k * Math.max(0.0, saGa - imaGa);
        double acr = Math.min(imaGa + surcharge + cU, saAll) + Math.max(0.0, imaGa - saGa);
        return new Capital(mC, cA, imaGa, saGa, k, surcharge, acr);
    }

    // ---- RFET (MAR31.12 to MAR31.16, KR-59, KR-309) ---------------------------------------------------------

    /**
     * The result of {@link #rfet}; the window fields are null when no 90-day window fits.
     *
     * @param windowStart first day of the 12-month window
     * @param distinctDays distinct observation days inside it
     * @param minWindowCount smallest count over the 90-day windows
     * @param firstFailingWindowStart earliest start with fewer than 4 days
     * @param firstFailingWindowCount its count
     * @param crit1 criterion 1 of MAR31.13
     * @param crit2 criterion 2 of MAR31.13
     * @param pass crit1 or crit2
     */
    public record Rfet(LocalDate windowStart, long distinctDays, Long minWindowCount,
            LocalDate firstFailingWindowStart, Long firstFailingWindowCount, boolean crit1, boolean crit2,
            boolean pass) {}

    /** The result of {@link #rfetBucket}: 1-based bucket, lower bound, upper bound (null when open). */
    public record Bucket(long bucket, double lower, Double upper) {}

    /** Calendar months back, the day clamped to the end of the target month (KR-59). */
    public static LocalDate monthsBack(LocalDate d, int months) {
        return d.minusMonths(months);
    }

    private static int upperBound(long[] sorted, long x) {
        int lo = 0;
        int hi = sorted.length;
        while (lo < hi) {
            int mid = (lo + hi) >>> 1;
            if (x < sorted[mid]) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        return lo;
    }

    /** Risk factor eligibility test on real-price observation dates (MAR31.13, KR-59). */
    public static Rfet rfet(LocalDate asOf, List<LocalDate> observations) {
        if (observations.size() > MAX_LIST) {
            throw new QfError("E_LIMIT", "observations is above its limit of " + MAX_LIST, "observations");
        }
        LocalDate start = monthsBack(asOf, FrtbImaTables.RFET_LOOKBACK_MONTHS).plusDays(1);
        TreeSet<Long> days = new TreeSet<>();
        for (LocalDate d : observations) {
            if (!d.isBefore(start) && !d.isAfter(asOf)) {
                days.add(d.toEpochDay());
            }
        }
        long[] ordinals = days.stream().mapToLong(Long::longValue).toArray();
        int window = FrtbImaTables.RFET_WINDOW_DAYS;
        LocalDate firstBad = null;
        Long firstBadCount = null;
        Long lowest = null;
        long last = asOf.toEpochDay() - (window - 1);
        for (long s = start.toEpochDay(); s <= last; s++) {
            long count = upperBound(ordinals, s + window - 1) - upperBound(ordinals, s - 1);
            lowest = lowest == null ? count : Math.min(lowest, count);
            if (firstBad == null && count < FrtbImaTables.RFET_MIN_PER_WINDOW) {
                firstBad = LocalDate.ofEpochDay(s);
                firstBadCount = count;
            }
        }
        boolean crit1 = ordinals.length >= FrtbImaTables.RFET_MIN_DAYS && firstBad == null;
        boolean crit2 = ordinals.length >= FrtbImaTables.RFET_ALT_MIN_DAYS;
        return new Rfet(start, ordinals.length, lowest, firstBad, firstBadCount, crit1, crit2, crit1 || crit2);
    }

    private static double[] lows(String row) {
        return switch (row) {
            case "A" -> FrtbImaTables.RFET_A;
            case "B" -> FrtbImaTables.RFET_B;
            case "C" -> FrtbImaTables.RFET_C;
            default -> FrtbImaTables.RFET_D;
        };
    }

    /**
     * MAR31.16 Table 1 bucket (1-based), lower bound inclusive, upper exclusive (KR-59). Rows A to C take a maturity
     * {@code t} in years, row D an option {@code delta} (KR-309); the other must be null.
     */
    public static Bucket rfetBucket(String row, Double t, Double delta) {
        boolean d = row.equals("D");
        String field = d ? "delta" : "t";
        Double value = d ? delta : t;
        if (value == null || (d ? t : delta) != null) {
            throw new QfError("E_INPUT", "row " + row + " takes " + field + " and nothing else", field);
        }
        if (value < 0) {
            throw new QfError("E_DOMAIN", field + " must be 0 or above", field);
        }
        if (d && !(value < FrtbImaTables.RFET_D_UPPER)) {
            throw new QfError("E_DOMAIN", "delta must be below 1", "delta");
        }
        double[] lo = lows(row);
        int b = 0;
        while (b < lo.length && !(value < lo[b])) {
            b++;
        }
        Double upper = b < lo.length ? Double.valueOf(lo[b]) : d ? Double.valueOf(FrtbImaTables.RFET_D_UPPER) : null;
        return new Bucket(b, lo[b - 1], upper);
    }
}
