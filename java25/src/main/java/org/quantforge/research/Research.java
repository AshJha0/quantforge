package org.quantforge.research;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.pricing.CreditOptions;

/**
 * Stage J wave 1 research operations: backtester (backtester.md), purged CV (purged-cv.md), Viterbi (regimes.md),
 * PSR, DSR, PBO and power (research-statistics.md). Rulings J-1 to J-19. Inputs are checked by the caller up to F-2;
 * the page-specific checks are here.
 */
public final class Research {
    /** Euler-Mascheroni constant (research-statistics.md). */
    public static final double GAMMA = 0.5772156649015329;

    private Research() {}

    private static QfError input(String why) {
        return new QfError("E_INPUT", why);
    }

    private static QfError domain(String why) {
        return new QfError("E_DOMAIN", why);
    }

    private static double pz(double x) {
        return x + 0.0;
    }

    // ---- backtester ----

    /** Engine choice of ruling J-3. */
    public enum Engine { EVENT, VECTOR }

    /** Backtest outputs, per bar and totals. */
    public record Backtest(double[] positions, double[] trades, double[] gross, double[] cost, double[] net,
            double[] equity, double totalGross, double totalSpread, double totalCommission, double totalFixed,
            double totalNet, double turnover, long tradeCount, double maxDrawdown) {}

    public static void checkBacktest(double[] prices, double[] targets, long lag, double halfSpreadBps,
            double commission, double fixed, double multiplier) {
        int t = prices.length;
        if (targets.length != t || t < 2 || lag < 0 || lag >= t) {
            throw input("prices, targets and lag do not fit");
        }
        for (double p : prices) {
            if (p <= 0) {
                throw domain("price must be positive");
            }
        }
        if (halfSpreadBps < 0 || commission < 0 || fixed < 0 || multiplier <= 0) {
            throw domain("costs must be non-negative and multiplier positive");
        }
    }

    public static Backtest backtest(double[] p, double[] targets, int lag, double hs, double comm, double fixed,
            double m, Engine engine) {
        checkBacktest(p, targets, lag, hs, comm, fixed, m);
        return engine == Engine.EVENT ? eventLoop(p, targets, lag, hs, comm, fixed, m)
                : vector(p, targets, lag, hs, comm, fixed, m);
    }

    private static Backtest eventLoop(double[] p, double[] targets, int lag, double hs, double comm, double fixed,
            double m) {
        int n = p.length;
        double[] q = new double[n];
        double[] d = new double[n];
        double[] g = new double[n];
        double[] k = new double[n];
        double[] net = new double[n];
        double[] eq = new double[n];
        double prev = 0;
        double e = 0;
        double peak = 0;
        double dd = 0;
        double tg = 0;
        double ts = 0;
        double tc = 0;
        double tf = 0;
        double turn = 0;
        long count = 0;
        for (int t = 0; t < n; t++) {
            double qt = t >= lag ? targets[t - lag] : 0.0;
            double dt = qt - prev;
            double gt = t >= 1 ? prev * (p[t] - p[t - 1]) * m : 0.0;
            double s = Math.abs(dt) * p[t] * (hs / 1e4) * m;
            double c = Math.abs(dt) * comm;
            double f = dt != 0 ? fixed : 0.0;
            double kt = s + c + f;
            double nt = gt - kt;
            e += nt;
            q[t] = pz(qt);
            d[t] = pz(dt);
            g[t] = pz(gt);
            k[t] = pz(kt);
            net[t] = pz(nt);
            eq[t] = pz(e);
            tg += gt;
            ts += s;
            tc += c;
            tf += f;
            turn += Math.abs(dt) * p[t] * m;
            if (dt != 0) {
                count++;
            }
            peak = Math.max(peak, e);
            dd = Math.max(dd, peak - e);
            prev = qt;
        }
        return new Backtest(q, d, g, k, net, eq, pz(tg), pz(ts), pz(tc), pz(tf), pz(tg - ts - tc - tf), pz(turn),
                count, pz(dd));
    }

    /** Whole-array form: shift, diff, multiply, cumsum (J-3). */
    private static Backtest vector(double[] p, double[] targets, int lag, double hs, double comm, double fixed,
            double m) {
        int n = p.length;
        double[] q = new double[n];
        System.arraycopy(targets, 0, q, lag, n - lag);
        double[] qPrev = new double[n];
        System.arraycopy(q, 0, qPrev, 1, n - 1);
        double[] dp = new double[n];
        for (int t = 1; t < n; t++) {
            dp[t] = p[t] - p[t - 1];
        }
        double[] d = new double[n];
        double[] g = new double[n];
        double[] s = new double[n];
        double[] c = new double[n];
        double[] f = new double[n];
        double[] k = new double[n];
        double[] net = new double[n];
        for (int t = 0; t < n; t++) {
            d[t] = q[t] - qPrev[t];
            g[t] = t >= 1 ? qPrev[t] * dp[t] * m : 0.0;
            s[t] = Math.abs(d[t]) * p[t] * (hs / 1e4) * m;
            c[t] = Math.abs(d[t]) * comm;
            f[t] = d[t] != 0 ? fixed : 0.0;
            k[t] = s[t] + c[t] + f[t];
            net[t] = g[t] - k[t];
        }
        double[] eq = cumsum(net);
        double peak = 0;
        double dd = 0;
        double turn = 0;
        long count = 0;
        for (int t = 0; t < n; t++) {
            peak = Math.max(peak, eq[t]);
            dd = Math.max(dd, peak - eq[t]);
            turn += Math.abs(d[t]) * p[t] * m;
            count += d[t] != 0 ? 1 : 0;
        }
        double tg = sum(g);
        double ts = sum(s);
        double tc = sum(c);
        double tf = sum(f);
        return new Backtest(clean(q), clean(d), clean(g), clean(k), clean(net), clean(eq), pz(tg), pz(ts), pz(tc),
                pz(tf), pz(tg - ts - tc - tf), pz(turn), count, pz(dd));
    }

    private static double[] cumsum(double[] x) {
        double[] out = new double[x.length];
        double a = 0;
        for (int i = 0; i < x.length; i++) {
            a += x[i];
            out[i] = a;
        }
        return out;
    }

    private static double sum(double[] x) {
        double a = 0;
        for (double v : x) {
            a += v;
        }
        return a;
    }

    private static double[] clean(double[] x) {
        for (int i = 0; i < x.length; i++) {
            x[i] = pz(x[i]);
        }
        return x;
    }

    // ---- purged CV ----

    /** One fold: test and train indices, ascending. */
    public record Fold(List<Long> test, List<Long> train) {}

    /** Purged k-fold result. */
    public record PurgedKFold(List<Fold> folds, long embargoCount) {}

    public static PurgedKFold purgedKFold(double[] t0, double[] t1, long k, double embargoPct) {
        int n = t0.length;
        if (t1.length != n || k < 2 || k > n) {
            throw input("lengths differ or n_splits out of range");
        }
        for (int i = 1; i < n; i++) {
            if (t0[i] < t0[i - 1]) {
                throw input("t0 must be non-decreasing");
            }
        }
        for (int i = 0; i < n; i++) {
            if (t1[i] < t0[i]) {
                throw domain("t1 before t0");
            }
        }
        if (embargoPct < 0 || embargoPct >= 1) {
            throw domain("embargo_pct outside [0, 1)");
        }
        int h = (int) Math.floor(embargoPct * n);
        int kk = (int) k;
        List<Fold> folds = new ArrayList<>();
        int a = 0;
        for (int f = 0; f < kk; f++) {
            int size = n / kk + (f < n % kk ? 1 : 0);
            int b = a + size;
            double lo = t0[a];
            double hi = Double.NEGATIVE_INFINITY;
            for (int i = a; i < b; i++) {
                hi = Math.max(hi, t1[i]);
            }
            List<Long> test = new ArrayList<>();
            List<Long> train = new ArrayList<>();
            for (int j = 0; j < n; j++) {
                if (j >= a && j < b) {
                    test.add((long) j);
                } else if (!(t0[j] <= hi && t1[j] >= lo) && !(j >= b && j < b + h)) {
                    train.add((long) j);
                }
            }
            folds.add(new Fold(test, train));
            a = b;
        }
        return new PurgedKFold(folds, h);
    }

    /** CPCV counts: {C(N, k), k C(N, k) / N}. */
    public static long[] cpcv(long groups, long testGroups) {
        if (groups > 64) {
            throw new QfError("E_LIMIT", "n_groups above 64", "n_groups");
        }
        if (groups < 2 || testGroups < 1 || testGroups >= groups) {
            throw input("n_groups or n_test_groups out of range");
        }
        java.math.BigInteger c = java.math.BigInteger.ONE;
        for (long i = 0; i < testGroups; i++) {
            c = c.multiply(java.math.BigInteger.valueOf(groups - i)).divide(java.math.BigInteger.valueOf(i + 1));
        }
        java.math.BigInteger paths = c.multiply(java.math.BigInteger.valueOf(testGroups))
                .divide(java.math.BigInteger.valueOf(groups));
        return new long[] {c.longValueExact(), paths.longValueExact()};
    }

    // ---- Viterbi ----

    /** Viterbi path and its joint log probability. */
    public record Viterbi(long[] states, double logProbability) {}

    /** Checks probabilities: non-negative entries and rows summing to 1 within 1e-9. */
    public static void checkModel(double[] initial, double[][] transition) {
        checkRow(initial);
        for (double[] r : transition) {
            checkRow(r);
        }
    }

    private static void checkRow(double[] r) {
        double s = 0;
        for (double v : r) {
            if (v < 0) {
                throw domain("negative probability");
            }
            s += v;
        }
        if (Math.abs(s - 1.0) > 1e-9) {
            throw domain("probabilities do not sum to 1");
        }
    }

    /** Gaussian log densities, T x K. */
    public static double[][] gaussianLogEmission(double[] y, double[] means, double[] sds) {
        for (double s : sds) {
            if (s <= 0) {
                throw domain("sd must be positive");
            }
        }
        double[][] out = new double[y.length][means.length];
        double c = Math.log(2 * Math.PI) / 2;
        for (int t = 0; t < y.length; t++) {
            for (int j = 0; j < means.length; j++) {
                double z = y[t] - means[j];
                out[t][j] = -Math.log(sds[j]) - c - z * z / (2 * sds[j] * sds[j]);
            }
        }
        return out;
    }

    /** Logs of a direct emission matrix; negative entries are E_DOMAIN. */
    public static double[][] logEmission(double[][] e) {
        double[][] out = new double[e.length][];
        for (int t = 0; t < e.length; t++) {
            out[t] = new double[e[t].length];
            for (int j = 0; j < e[t].length; j++) {
                if (e[t][j] < 0) {
                    throw domain("negative emission");
                }
                out[t][j] = Math.log(e[t][j]);
            }
        }
        return out;
    }

    /** Viterbi in logs; ties to the smallest index (J-11). An all -inf end is E_DOMAIN. */
    public static Viterbi viterbi(double[] initial, double[][] transition, double[][] logE) {
        int k = initial.length;
        int n = logE.length;
        double[][] la = new double[k][k];
        for (int i = 0; i < k; i++) {
            for (int j = 0; j < k; j++) {
                la[i][j] = Math.log(transition[i][j]);
            }
        }
        double[] delta = new double[k];
        for (int j = 0; j < k; j++) {
            delta[j] = Math.log(initial[j]) + logE[0][j];
        }
        int[][] back = new int[n][k];
        for (int t = 1; t < n; t++) {
            double[] next = new double[k];
            for (int j = 0; j < k; j++) {
                int best = 0;
                double bv = delta[0] + la[0][j];
                for (int i = 1; i < k; i++) {
                    double v = delta[i] + la[i][j];
                    if (v > bv) {
                        bv = v;
                        best = i;
                    }
                }
                back[t][j] = best;
                next[j] = bv + logE[t][j];
            }
            delta = next;
        }
        int end = 0;
        for (int j = 1; j < k; j++) {
            if (delta[j] > delta[end]) {
                end = j;
            }
        }
        if (delta[end] == Double.NEGATIVE_INFINITY || Double.isNaN(delta[end])) {
            throw domain("every path has probability zero");
        }
        long[] states = new long[n];
        int s = end;
        for (int t = n - 1; t >= 0; t--) {
            states[t] = s;
            s = back[t][s];
        }
        return new Viterbi(states, pz(delta[end]));
    }

    // ---- PSR, DSR, power ----

    /** Normal quantile: AS 241 refined by one Newton step. */
    public static double inverseNormal(double p) {
        return CreditOptions.inverseNormal(p);
    }

    private static void checkSharpeInputs(long nObs, double kurtosis) {
        if (nObs < 2) {
            throw input("n_obs below 2");
        }
        if (kurtosis < 1) {
            throw domain("kurtosis below 1");
        }
    }

    /** {z, psr}. */
    public static double[] psr(double sr, long nObs, double skew, double kurtosis, double benchmark) {
        checkSharpeInputs(nObs, kurtosis);
        double z = z(sr, nObs, skew, kurtosis, benchmark);
        return new double[] {pz(z), Normal.cdf(z)};
    }

    private static double z(double sr, long nObs, double skew, double kurtosis, double benchmark) {
        double v = 1 - skew * sr + (kurtosis - 1) / 4 * sr * sr;
        if (v <= 0) {
            throw domain("variance term not positive");
        }
        return (sr - benchmark) * Math.sqrt(nObs - 1.0) / Math.sqrt(v);
    }

    /** {sr0, z, dsr}. */
    public static double[] dsr(double sr, long nObs, double skew, double kurtosis, long nTrials, double srVariance) {
        checkSharpeInputs(nObs, kurtosis);
        if (nTrials < 1) {
            throw input("n_trials below 1");
        }
        if (srVariance < 0) {
            throw domain("sr_variance negative");
        }
        double sr0 = 0.0;
        if (nTrials > 1) {
            double n = nTrials;
            sr0 = Math.sqrt(srVariance)
                    * ((1 - GAMMA) * inverseNormal(1 - 1 / n) + GAMMA * inverseNormal(1 - 1 / (n * Math.E)));
        }
        double z = z(sr, nObs, skew, kurtosis, sr0);
        return new double[] {pz(sr0), pz(z), Normal.cdf(z)};
    }

    /** {z_sum, mds, se_at_zero[, years_required, se_at_target]}. */
    public static double[] power(double years, double alpha, double power, Double srTarget) {
        if (years <= 0 || alpha <= 0 || alpha >= 1 || power <= 0 || power >= 1 || alpha >= power) {
            throw domain("years, alpha or power out of range");
        }
        if (srTarget != null && srTarget <= 0) {
            throw domain("sr_target must be positive");
        }
        double zs = inverseNormal(1 - alpha) + inverseNormal(power);
        double se0 = 1 / Math.sqrt(years);
        if (srTarget == null) {
            return new double[] {zs, zs / Math.sqrt(years), se0};
        }
        double r = zs / srTarget;
        return new double[] {zs, zs / Math.sqrt(years), se0, r * r,
            Math.sqrt((1 + srTarget * srTarget / 2) / years)};
    }

    // ---- PBO by CSCV ----

    /** CSCV metric. */
    public enum Metric { SHARPE, MEAN }

    /** PBO result. */
    public record Pbo(double pbo, double[] logits, long combinations) {}

    public static void checkPboShape(double[][] perf, long s) {
        int t = perf.length;
        if (s < 2 || s % 2 != 0 || t == 0 || t % s != 0 || t / s < 2) {
            throw input("n_partitions does not fit the rows");
        }
        int n = perf[0].length;
        for (double[] r : perf) {
            if (r.length != n) {
                throw input("ragged performance");
            }
        }
        if (n < 2) {
            throw input("fewer than two strategies");
        }
    }

    public static Pbo pbo(double[][] perf, int s, Metric metric) {
        checkPboShape(perf, s);
        int t = perf.length;
        int n = perf[0].length;
        int block = t / s;
        if (metric == Metric.SHARPE) {
            for (int b = 0; b < s; b++) {
                for (int j = 0; j < n; j++) {
                    double[] col = new double[block];
                    for (int i = 0; i < block; i++) {
                        col[i] = perf[b * block + i][j];
                    }
                    if (sampleSd(col) == 0) {
                        throw domain("zero standard deviation in a block");
                    }
                }
            }
        }
        List<int[]> combos = new ArrayList<>();
        combine(new int[s / 2], 0, 0, s, combos);
        double[] logits = new double[combos.size()];
        int bad = 0;
        for (int c = 0; c < combos.size(); c++) {
            boolean[] inTrain = new boolean[s];
            for (int b : combos.get(c)) {
                inTrain[b] = true;
            }
            double[] train = new double[n];
            double[] test = new double[n];
            for (int j = 0; j < n; j++) {
                train[j] = metric(perf, j, block, inTrain, true, metric);
                test[j] = metric(perf, j, block, inTrain, false, metric);
            }
            int star = 0;
            for (int j = 1; j < n; j++) {
                if (train[j] > train[star]) {
                    star = j;
                }
            }
            int less = 0;
            int equal = 0;
            for (int j = 0; j < n; j++) {
                if (test[j] < test[star]) {
                    less++;
                } else if (test[j] == test[star]) {
                    equal++;
                }
            }
            double rank = less + (equal + 1) / 2.0;
            double omega = rank / (n + 1);
            logits[c] = pz(Math.log(omega / (1 - omega)));
            if (logits[c] <= 0) {
                bad++;
            }
        }
        return new Pbo((double) bad / combos.size(), logits, combos.size());
    }

    private static void combine(int[] cur, int depth, int start, int s, List<int[]> out) {
        if (depth == cur.length) {
            out.add(cur.clone());
            return;
        }
        for (int b = start; b < s; b++) {
            cur[depth] = b;
            combine(cur, depth + 1, b + 1, s, out);
        }
    }

    private static double metric(double[][] perf, int j, int block, boolean[] inTrain, boolean train, Metric m) {
        double[] x = new double[perf.length / 2];
        int k = 0;
        for (int b = 0; b < inTrain.length; b++) {
            if (inTrain[b] == train) {
                for (int i = 0; i < block; i++) {
                    x[k++] = perf[b * block + i][j];
                }
            }
        }
        double mean = mean(x);
        return m == Metric.MEAN ? mean : mean / sampleSd(x);
    }

    private static double mean(double[] x) {
        return sum(x) / x.length;
    }

    private static double sampleSd(double[] x) {
        double mu = mean(x);
        double a = 0;
        for (double v : x) {
            a += (v - mu) * (v - mu);
        }
        return Math.sqrt(a / (x.length - 1));
    }
}
