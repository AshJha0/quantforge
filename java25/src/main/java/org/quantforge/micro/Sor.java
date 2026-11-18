package org.quantforge.micro;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;

/**
 * {@code exec.sor.allocate}: order placement over simulated lit and dark venues ([CK] Cont-Kukanov),
 * {@code specifications/10-execution/smart-order-router.md}, rulings HR-37 to HR-40. Simulated venues; router scored
 * in simulation only. A port of the Python reference {@code python/quantforge_core/sor.py}.
 *
 * <p>Cost per scenario is [CK] eq. 5 with the dark extension of HR-37. The expectation is exact: equally weighted
 * {@code lit_samples} rows times the independent dark distributions given by their tails, in rational arithmetic,
 * rounded half-even to 6 decimals only on output. Methods: {@code SAMPLE_AVERAGE} (exhaustive integer grid, ties to
 * the lexicographically smallest tuple; exact coordinate descent above 10^6 points), {@code CLOSED_FORM} ([CK]
 * Prop. 3), {@code STOCHASTIC_APPROX} ([CK] section 4 projected subgradient with averaged iterates, rounded to the best
 * neighbouring integer point and finished by the exact coordinate-descent search, as the Python reference).
 */
public final class Sor {
    private Sor() {}

    public static final String LABEL = "simulated venues; router scored in simulation only";
    public static final int MAX_VENUES = 64;
    public static final long MAX_SAMPLES = 1_000_000L;
    public static final long MAX_GRID = 1_000_000L;

    /** An exact rational in lowest terms with a positive denominator. */
    record Frac(BigInteger n, BigInteger d) implements Comparable<Frac> {
        static final Frac ZERO = new Frac(BigInteger.ZERO, BigInteger.ONE);
        static final Frac ONE = new Frac(BigInteger.ONE, BigInteger.ONE);

        static Frac of(BigInteger n, BigInteger d) {
            if (d.signum() < 0) {
                n = n.negate();
                d = d.negate();
            }
            BigInteger g = n.gcd(d);
            return g.signum() == 0 || g.equals(BigInteger.ONE) ? new Frac(n, d) : new Frac(n.divide(g), d.divide(g));
        }

        static Frac of(long v) {
            return new Frac(BigInteger.valueOf(v), BigInteger.ONE);
        }

        static Frac of(BigDecimal x) {
            return x.scale() <= 0 ? new Frac(x.toBigIntegerExact(), BigInteger.ONE)
                    : of(x.unscaledValue(), BigInteger.TEN.pow(x.scale()));
        }

        Frac add(Frac o) {
            return of(n.multiply(o.d).add(o.n.multiply(d)), d.multiply(o.d));
        }

        Frac sub(Frac o) {
            return add(o.neg());
        }

        Frac neg() {
            return new Frac(n.negate(), d);
        }

        Frac mul(Frac o) {
            return of(n.multiply(o.n), d.multiply(o.d));
        }

        Frac mul(long k) {
            return of(n.multiply(BigInteger.valueOf(k)), d);
        }

        Frac div(Frac o) {
            return of(n.multiply(o.d), d.multiply(o.n));
        }

        boolean isZero() {
            return n.signum() == 0;
        }

        @Override
        public int compareTo(Frac o) {
            return n.multiply(o.d).compareTo(o.n.multiply(d));
        }

        /** Correctly rounded to the nearest double (as Python's float(Fraction)). */
        double toDouble() {
            return new BigDecimal(n).divide(new BigDecimal(d), new MathContext(80, RoundingMode.HALF_EVEN))
                    .doubleValue();
        }
    }

    private static final BigInteger FIVE = BigInteger.valueOf(5);

    /**
     * HR-57/HR-58: every exact value the router computes must be a decimal with |coefficient| &lt; 10^36 and minimal
     * scale &lt;= 36, else {@code E_LIMIT}; checked at the same steps as the Python reference's {@code _r}.
     */
    static Frac r(Frac x) {
        if (x.n.signum() == 0) {
            return x;
        }
        BigInteger d = x.d;
        int twos = d.getLowestSetBit();
        d = d.shiftRight(twos);
        int fives = 0;
        while (d.mod(FIVE).signum() == 0) {
            d = d.divide(FIVE);
            fives++;
        }
        int scale = Math.max(twos, fives);
        if (!d.equals(BigInteger.ONE) || scale > OrderBook.MAX_SCALE) {
            throw new QfError("E_LIMIT", "sor: decimal outside the exact range (36 digits, 36 decimals; HR-57)", "sor");
        }
        BigInteger unscaled = x.n.multiply(BigInteger.TEN.pow(scale).divide(x.d));
        OrderBook.range(new BigDecimal(unscaled, scale), "sor", OrderBook.MAX_SCALE);
        return x;
    }

    /** {@code x} rounded half-even to 18 decimals (after a 200-digit division, as Python), read as binary64. */
    static double dec18(Frac x) {
        BigDecimal d = new BigDecimal(x.n).divide(new BigDecimal(x.d), new MathContext(200, RoundingMode.HALF_EVEN))
                .setScale(18, RoundingMode.HALF_EVEN);
        return Double.parseDouble(d.toString());
    }

    /** HR-40 standard error, the Python reference's {@code _se} rule (binary64 steps, no fused multiply-add). */
    static String se(Frac meanCost, Frac meanSq, int nRows) {
        double a = dec18(meanSq);
        double b = dec18(meanCost);
        double bb = b * b;
        double se = Math.sqrt(Math.max(a - bb, 0.0) / nRows);
        return LitMatching.fmt(new BigDecimal(se).setScale(6, RoundingMode.HALF_EVEN));
    }

    private static Frac frac(Object v, String path) {
        return Frac.of(OrderBook.dec(v, path));
    }

    private static int lots(Object v, String path) {
        BigDecimal d = OrderBook.dec(v, path);
        if (d.signum() < 0 || d.stripTrailingZeros().scale() > 0) {
            throw new QfError("E_DOMAIN", path + ": not a non-negative integer number of lots", path);
        }
        try {
            return d.intValueExact();
        } catch (ArithmeticException e) {
            throw new QfError("E_LIMIT", path + ": too many lots", path);
        }
    }

    /** As the Python reference: the exact rational rounded half-even to 6 places, with no context in between. */
    static String out(Frac x) {
        BigDecimal q = new BigDecimal(x.n).divide(new BigDecimal(x.d), 6, RoundingMode.HALF_EVEN);
        return LitMatching.fmt(q);
    }

    /** Lexicographic order of integer tuples. */
    static int lex(int[] a, int[] b) {
        return Arrays.compare(a, b);
    }

    record Scored(Frac cost, int[] t) {}

    record Eval(Frac cost, Frac fill, Frac under, Frac sq) {}

    static final class Problem {
        final int S;
        final Frac h;
        final Frac f;
        final Frac theta;
        final Frac lu;
        final Frac lo;
        final double hD;
        final double fD;
        final double thD;
        final double luD;
        final double loD;
        final List<String> kinds = new ArrayList<>();
        final List<Integer> qs = new ArrayList<>();
        final List<Frac> coef = new ArrayList<>();
        final List<Frac[]> tails = new ArrayList<>();
        final int[] lit;
        final int[] dark;
        final int[][] rows;
        final boolean wantSq;

        Problem(Map<?, ?> inp) {
            wantSq = Boolean.TRUE.equals(inp.get("report_se"));
            S = lots(inp.get("S"), "S");
            if (S <= 0) {
                throw new QfError("E_DOMAIN", "S must be positive", "S");
            }
            String[] keys = {"h", "f", "theta", "lambda_u", "lambda_o"};
            Frac[] g = new Frac[5];
            double[] gd = new double[5];
            for (int k = 0; k < 5; k++) {
                g[k] = frac(inp.get(keys[k]), keys[k]);
                gd[k] = g[k].toDouble();
            }
            if (g[2].n.signum() < 0 || g[3].n.signum() < 0 || g[4].n.signum() < 0) {
                throw new QfError("E_DOMAIN", "negative penalty", "lambda_u");
            }
            h = g[0];
            f = g[1];
            theta = g[2];
            lu = g[3];
            lo = g[4];
            hD = gd[0];
            fD = gd[1];
            thD = gd[2];
            luD = gd[3];
            loD = gd[4];
            if (!(inp.get("venues") instanceof List<?> venues) || venues.isEmpty()) {
                throw new QfError("E_INPUT", "venues: empty", "venues");
            }
            String orderClass = DarkPool.assetClass(inp.get("asset_class"), "asset_class", false);
            List<String> classes = new ArrayList<>();
            for (int k = 0; k < venues.size(); k++) {
                classes.add(DarkPool.assetClass(venues.get(k) instanceof Map<?, ?> m ? m.get("asset_class") : null,
                        "venues/" + k + "/asset_class", false));
            }
            if (classes.stream().anyMatch(cl -> !cl.equals(orderClass))) {
                throw new QfError("E_INPUT", "a venue's asset_class differs from the order's (HR-93)", "venues");
            }
            for (int k = 0; k < venues.size(); k++) {
                if (venues.get(k) instanceof Map<?, ?> m && "DARK".equals(m.get("kind"))) {
                    DarkPool.assetClass(classes.get(k), "venues/" + k + "/asset_class", true);
                }
            }
            if (venues.size() > MAX_VENUES) {
                throw new QfError("E_LIMIT", "more than 64 venues", "venues");
            }
            for (int k = 0; k < venues.size(); k++) {
                Map<?, ?> v = venues.get(k) instanceof Map<?, ?> m ? m : null;
                Object kind = v == null ? null : v.get("kind");
                if (!("LIT".equals(kind) || "DARK".equals(kind))) {
                    throw new QfError("E_SCHEMA", "venues/" + k + "/kind", "venues");
                }
                kinds.add((String) kind);
                coef.add(r(r(h.add(frac(v.get("r"), "venues/" + k + "/r"))).sub(frac(v.get("as"), "venues/" + k + "/as"))));
                if (kind.equals("LIT")) {
                    qs.add(lots(v.get("Q"), "venues/" + k + "/Q"));
                    tails.add(new Frac[0]);
                } else {
                    qs.add(0);
                    Object raw = v.containsKey("tail") ? v.get("tail") : List.of();
                    if (!(raw instanceof List<?> tl)) {
                        throw new QfError("E_SCHEMA", "venues/" + k + "/tail: not an array", "venues");
                    }
                    Frac[] tail = new Frac[tl.size()];
                    for (int j = 0; j < tl.size(); j++) {
                        tail[j] = frac(tl.get(j), "venues/" + k + "/tail");
                    }
                    for (int j = 0; j < tail.length; j++) {
                        boolean bad = tail[j].n.signum() < 0 || tail[j].compareTo(Frac.ONE) > 0
                                || (j > 0 && tail[j - 1].compareTo(tail[j]) < 0);
                        if (bad) {
                            throw new QfError("E_DOMAIN", "venues/" + k + "/tail: not a tail", "venues");
                        }
                    }
                    tails.add(tail);
                }
            }
            lit = indices("LIT");
            dark = indices("DARK");
            Object rawRows = inp.containsKey("lit_samples") ? inp.get("lit_samples") : List.of();
            if (!(rawRows instanceof List<?> rl)) {
                throw new QfError("E_INPUT", "lit_samples: not an array", "lit_samples");
            }
            if (lit.length > 0 && rl.isEmpty()) {
                throw new QfError("E_INPUT", "lit_samples: empty", "lit_samples");
            }
            if (rl.size() > MAX_SAMPLES) {
                throw new QfError("E_LIMIT", "more than 10^6 samples", "lit_samples");
            }
            int[][] rs = new int[rl.size()][];
            for (int i = 0; i < rl.size(); i++) {
                if (!(rl.get(i) instanceof List<?> r)) {
                    throw new QfError("E_INPUT", "lit_samples/" + i + ": not a row", "lit_samples");
                }
                rs[i] = new int[r.size()];
                for (int j = 0; j < r.size(); j++) {
                    rs[i][j] = lots(r.get(j), "lit_samples/" + i);
                }
            }
            rows = rs.length == 0 ? new int[][] {new int[0]} : rs;
            for (int[] r : rows) {
                if (r.length != lit.length) {
                    throw new QfError("E_INPUT", "lit_samples: one value per LIT venue per row", "lit_samples");
                }
            }
        }

        private int[] indices(String kind) {
            List<Integer> out = new ArrayList<>();
            for (int k = 0; k < kinds.size(); k++) {
                if (kinds.get(k).equals(kind)) {
                    out.add(k);
                }
            }
            return out.stream().mapToInt(Integer::intValue).toArray();
        }

        int k() {
            return kinds.size();
        }

        boolean singleLit() {
            return kinds.size() == 1 && kinds.get(0).equals("LIT");
        }

        Frac tail(int k, int s) {
            Frac[] t = tails.get(k);
            return s <= 0 ? Frac.ONE : (s <= t.length ? t[s - 1] : Frac.ZERO);
        }

        /** Distribution of min(L, s) for dark venue k, zero-probability points dropped: {value, probability}. */
        List<Object[]> darkDist(int k, int L) {
            List<Object[]> out = new ArrayList<>();
            for (int j = 0; j < L; j++) {
                Frac p = r(tail(k, j).sub(tail(k, j + 1)));
                if (!p.isZero()) {
                    out.add(new Object[] {j, p});
                }
            }
            Frac p = tail(k, L);
            if (!p.isZero()) {
                out.add(new Object[] {L, p});
            }
            return out;
        }

        /** Exact (expected cost, E min(A, S), P(A &lt; S), E cost^2) of the tuple t = (M, L_1..L_K). */
        Eval evaluate(int[] t) {
            int K = k();
            int M = t[0];
            List<List<Object[]>> dists = new ArrayList<>();
            for (int k : dark) {
                dists.add(darkDist(k, t[k + 1]));
            }
            long sumL = 0;
            for (int k = 0; k < K; k++) {
                sumL += t[k + 1];
            }
            Frac cost = Frac.ZERO;
            Frac fill = Frac.ZERO;
            Frac under = Frac.ZERO;
            Frac sq = Frac.ZERO;
            Frac hf = r(h.add(f));
            for (int[] row : rows) {
                int[] base = new int[K];
                for (int i = 0; i < lit.length; i++) {
                    int k = lit[i];
                    long x = (long) row[i] - qs.get(k);
                    base[k] = (int) (Math.max(x, 0) - Math.max(x - t[k + 1], 0));
                }
                int[] idx = new int[dists.size()];
                boolean empty = false;
                for (List<Object[]> d : dists) {
                    empty |= d.isEmpty();
                }
                if (empty) {
                    continue;
                }
                while (true) {
                    Frac p = Frac.ONE;
                    int[] fills = base.clone();
                    for (int i = 0; i < dark.length; i++) {
                        Object[] jp = dists.get(i).get(idx[i]);
                        fills[dark[i]] = (Integer) jp[0];
                        p = r(p.mul((Frac) jp[1]));
                    }
                    long A = M;
                    for (int x : fills) {
                        A += x;
                    }
                    long underQ = Math.max(S - A, 0);
                    long overQ = Math.max(A - S, 0);
                    Frac c = r(hf.mul(M));
                    for (int k = 0; k < K; k++) {
                        if (fills[k] != 0) {
                            c = r(c.sub(r(coef.get(k).mul(fills[k]))));
                        }
                    }
                    if (!theta.isZero()) {
                        c = r(c.add(r(theta.mul(M + sumL + underQ))));
                    }
                    if (underQ != 0) {
                        c = r(c.add(r(lu.mul(underQ))));
                    }
                    if (overQ != 0) {
                        c = r(c.add(r(lo.mul(overQ))));
                    }
                    Frac pc = r(p.mul(c));
                    cost = r(cost.add(pc));
                    if (wantSq) {
                        sq = r(sq.add(r(pc.mul(c))));
                    }
                    fill = r(fill.add(r(p.mul(Math.min(A, S)))));
                    if (A < S) {
                        under = r(under.add(p));
                    }
                    int i = dists.size() - 1;
                    while (i >= 0) {
                        if (++idx[i] < dists.get(i).size()) {
                            break;
                        }
                        idx[i] = 0;
                        i--;
                    }
                    if (i < 0) {
                        break;
                    }
                }
            }
            Frac nr = Frac.of(rows.length);
            return new Eval(cost.div(nr), fill.div(nr), under.div(nr), sq.div(nr));
        }

        Frac cost(int[] t) {
            return evaluate(t).cost();
        }

        /** [CK] Prop. 3 for one lit venue, F the empirical CDF of xi, left-inverse quantile. */
        int[] closedForm() {
            if (!singleLit()) {
                throw new QfError("E_DOMAIN", "CLOSED_FORM needs exactly one LIT venue", "method");
            }
            int[] xs = new int[rows.length];
            for (int i = 0; i < rows.length; i++) {
                xs[i] = rows[i][0];
            }
            Arrays.sort(xs);
            int n = xs.length;
            int Q = qs.get(0);
            Frac rEff = r(coef.get(0).sub(h));
            Frac num = r(r(r(h.add(h)).add(f)).add(rEff));
            Frac base = r(r(h.add(rEff)).add(theta));
            Frac lb = r(lu.add(base));
            Frac numn = r(num.mul(n));
            int cLo = count(xs, (long) Q + S);
            int cHi = count(xs, Q);
            if (cLo == 0 || r(lb.mul(cLo)).compareTo(numn) <= 0) {
                return new int[] {0, S};
            }
            if (cHi != 0 && r(lb.mul(cHi)).compareTo(numn) >= 0) {
                return new int[] {S, 0};
            }
            if (lb.isZero()) {
                throw new QfError("E_DOMAIN", "lambda_u + h + r + theta is zero", "lambda_u");
            }
            int q = xs[n - 1];
            for (int v : xs) {
                int cmp = r(lb.mul(count(xs, v))).compareTo(numn);
                if (lb.n.signum() > 0 ? cmp >= 0 : cmp <= 0) {
                    q = v;
                    break;
                }
            }
            int M = (int) Math.min(Math.max((long) S - q + Q, 0), S);
            return new int[] {M, S - M};
        }

        /** n F(x): the number of samples at most x. */
        private static int count(int[] xs, long x) {
            int c = 0;
            for (int v : xs) {
                if (v <= x) {
                    c++;
                }
            }
            return c;
        }

        /** Every grid tuple in lexicographic order, scored and sorted by (cost, tuple); or null above 10^6 points. */
        List<Scored> grid() {
            int K = k();
            double size = Math.pow(S + 1.0, K + 1.0);
            if (size > MAX_GRID) {
                return null;
            }
            List<Scored> out = new ArrayList<>();
            int[] t = new int[K + 1];
            while (true) {
                out.add(new Scored(cost(t), t.clone()));
                int i = K;
                while (i >= 0) {
                    if (++t[i] <= S) {
                        break;
                    }
                    t[i] = 0;
                    i--;
                }
                if (i < 0) {
                    break;
                }
            }
            out.sort((a, b) -> {
                int c = a.cost().compareTo(b.cost());
                return c != 0 ? c : lex(a.t(), b.t());
            });
            return out;
        }

        int[] start() {
            if (singleLit()) {
                return closedForm();
            }
            int[] t = new int[k() + 1];
            t[1] = kinds.get(0).equals("LIT") ? S : 0;
            return t;
        }

        /** Exact coordinate descent from {@code from}; each pass tries every value 0..S per coordinate. */
        int[] descent(int[] from) {
            int[] best = from.clone();
            Frac cur = cost(best);
            boolean changed = true;
            while (changed) {
                changed = false;
                for (int i = 0; i < best.length; i++) {
                    for (int v = 0; v <= S; v++) {
                        int[] t = best.clone();
                        t[i] = v;
                        Frac c = cost(t);
                        int cmp = c.compareTo(cur);
                        if (cmp < 0 || (cmp == 0 && lex(t, best) < 0)) {
                            best = t;
                            cur = c;
                            changed = true;
                        }
                    }
                }
            }
            return best;
        }

        /**
         * [CK] section 4: projected subgradient on [0, S]^(K+1), step / sqrt(n), iterates averaged; the average is
         * rounded to the best floor/ceiling neighbour (HR-38), then polished by the exact coordinate descent (the
         * subgradient is zero on flat regions of the cost, so the averaged iterate can stop anywhere on a plateau).
         */
        int[] stochastic(long iterations, double step, long seed) {
            Rng rng = Rng.seeded(seed, 0);
            int K = k();
            int[] st = start();
            double[] x = new double[K + 1];
            for (int i = 0; i <= K; i++) {
                x[i] = st[i];
            }
            double[] avg = new double[K + 1];
            double[] coefD = new double[K];
            double[][] tailD = new double[K][];
            for (int k = 0; k < K; k++) {
                coefD[k] = coef.get(k).toDouble();
                Frac[] t = tails.get(k);
                tailD[k] = new double[t.length];
                for (int j = 0; j < t.length; j++) {
                    tailD[k][j] = t[j].toDouble();
                }
            }
            for (long n = 1; n <= iterations; n++) {
                int[] row = rows[(int) Math.min((long) (rng.nextUniform() * rows.length), rows.length - 1)];
                double[] room = new double[K];
                double[] fills = new double[K];
                for (int i = 0; i < lit.length; i++) {
                    int k = lit[i];
                    double xi = (double) ((long) row[i] - qs.get(k));
                    fills[k] = Math.min(Math.max(xi, 0.0), x[k + 1]);
                    room[k] = xi > x[k + 1] ? 1.0 : 0.0;
                }
                for (int k : dark) {
                    double u = rng.nextUniform();
                    int s = 0;
                    while (s < tailD[k].length && u < tailD[k][s]) {
                        s++;
                    }
                    fills[k] = Math.min((double) s, x[k + 1]);
                    room[k] = s > x[k + 1] ? 1.0 : 0.0;
                }
                double sum = 0.0;
                for (double v : fills) {
                    sum += v;
                }
                double A = x[0] + sum;
                double gA = (A < S ? -(luD + thD) : 0.0) + (A > S ? loD : 0.0);
                double[] grad = new double[K + 1];
                grad[0] = hD + fD + thD + gA;
                for (int k = 0; k < K; k++) {
                    grad[k + 1] = thD + room[k] * (gA - coefD[k]);
                }
                double eta = step / Math.sqrt((double) n);
                for (int i = 0; i <= K; i++) {
                    x[i] = Math.min(Math.max(x[i] - eta * grad[i], 0.0), (double) S);
                    avg[i] = avg[i] + (x[i] - avg[i]) / n;
                }
            }
            int[][] opts = new int[K + 1][];
            for (int i = 0; i <= K; i++) {
                int lo = (int) Math.floor(avg[i]);
                int hi = (int) Math.ceil(avg[i]);
                opts[i] = lo == hi ? new int[] {lo} : new int[] {lo, hi};
            }
            int[] idx = new int[K + 1];
            int[] best = null;
            Frac bestC = null;
            while (true) {
                int[] t = new int[K + 1];
                for (int i = 0; i <= K; i++) {
                    t[i] = opts[i][idx[i]];
                }
                Frac c = cost(t);
                if (best == null || c.compareTo(bestC) < 0 || (c.compareTo(bestC) == 0 && lex(t, best) < 0)) {
                    best = t;
                    bestC = c;
                }
                int i = K;
                while (i >= 0) {
                    if (++idx[i] < opts[i].length) {
                        break;
                    }
                    idx[i] = 0;
                    i--;
                }
                if (i < 0) {
                    break;
                }
            }
            return descent(best);
        }
    }

    private static long intArg(Object v, long dflt, String path) {
        if (v == null) {
            return dflt;
        }
        if (v instanceof Json.Number n) {
            return (long) n.value();
        }
        if (v instanceof java.lang.Number n) {
            return n.longValue();
        }
        throw new QfError("E_SCHEMA", path + ": not a number", path);
    }

    private static double realArg(Object v, double dflt, String path) {
        if (v == null) {
            return dflt;
        }
        if (v instanceof Json.Number n) {
            return n.value();
        }
        if (v instanceof java.lang.Number n) {
            return n.doubleValue();
        }
        if ("NaN".equals(v)) {
            return Double.NaN;
        }
        if ("Infinity".equals(v)) {
            return Double.POSITIVE_INFINITY;
        }
        if ("-Infinity".equals(v)) {
            return Double.NEGATIVE_INFINITY;
        }
        throw new QfError("E_SCHEMA", path + ": not a number", path);
    }

    private static List<String> strs(int[] t, int from) {
        List<String> out = new ArrayList<>();
        for (int i = from; i < t.length; i++) {
            out.add(Integer.toString(t[i]));
        }
        return out;
    }

    /** The allocation for one input object (the CLI inputs as given). */
    public static Map<String, Object> allocate(Map<?, ?> inp) {
        // F-2 (E1): `step` is the one Real input; non-finite is E_DOMAIN, the first rule check (as sor.py).
        if (!Double.isFinite(realArg(inp.get("step"), 1.0, "step"))) {
            throw new QfError("E_DOMAIN", "step: not finite", "step");
        }
        Problem p = new Problem(inp);
        Object method = inp.containsKey("method") ? inp.get("method") : "SAMPLE_AVERAGE";
        if (!("SAMPLE_AVERAGE".equals(method) || "CLOSED_FORM".equals(method)
                || "STOCHASTIC_APPROX".equals(method))) {
            throw new QfError("E_SCHEMA", "method", "method");
        }
        boolean wantRank = Boolean.TRUE.equals(inp.get("ranking"));
        List<Scored> ranking = List.of();
        int[] best;
        if ("CLOSED_FORM".equals(method)) {
            best = p.closedForm();
        } else if ("STOCHASTIC_APPROX".equals(method)) {
            best = p.stochastic(intArg(inp.get("iterations"), 10_000, "iterations"),
                    realArg(inp.get("step"), 1.0, "step"), intArg(inp.get("seed"), 0, "seed"));
        } else {
            List<Scored> g = p.grid();
            if (g != null) {
                best = g.get(0).t();
                if (wantRank) {
                    ranking = g;
                }
            } else {
                if (wantRank) {
                    throw new QfError("E_LIMIT", "ranking needs a grid of at most 10^6 points", "ranking");
                }
                best = p.descent(p.start());
            }
        }
        Eval e = p.evaluate(best);
        Map<String, Object> out = new TreeMap<>();
        out.put("M", Integer.toString(best[0]));
        out.put("L", strs(best, 1));
        out.put("expected_cost", out(e.cost()));
        out.put("expected_fill", out(e.fill()));
        out.put("p_underfill", out(e.under()));
        if (Boolean.TRUE.equals(inp.get("report_se"))) {
            out.put("expected_cost_se", se(e.cost(), e.sq(), p.rows.length));
            out.put("label", LABEL);
        }
        if (wantRank) {
            List<Object> r = new ArrayList<>();
            for (Scored s : ranking) {
                Map<String, Object> m = new TreeMap<>();
                m.put("M", Integer.toString(s.t()[0]));
                m.put("L", strs(s.t(), 1));
                m.put("expected_cost", out(s.cost()));
                r.add(m);
            }
            out.put("ranking", r);
        }
        return out;
    }
}
