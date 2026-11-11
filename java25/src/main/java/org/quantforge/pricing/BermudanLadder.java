package org.quantforge.pricing;

/**
 * Price and full sensitivity ladder of the G-18 Bermudan scheme by reverse-mode AAD (aad-core.md, rulings G-9 and
 * G-35). The forward pass repeats {@link ShortRateFd#bermudan} operation for operation on a {@link Tape}; the
 * derivative is that of the discrete scheme, with each exercise {@code max} taken through its active branch.
 */
public final class BermudanLadder {
    private BermudanLadder() {}

    /**
     * Price and ladder.
     *
     * @param price the scheme price
     * @param dDiscountFactors derivative per curve pillar discount factor
     * @param dMeanReversion derivative with respect to {@code a}
     * @param dSigma derivative with respect to {@code sigma}
     */
    public record Ladder(double price, double[] dDiscountFactors, double dMeanReversion, double dSigma) {}

    /** The curve and model on the tape. */
    private static final class Model {
        final Tape tp;
        final double[] tt;
        final int[] lp;
        final int[] slope;
        final int a;
        final int sigma;

        Model(Tape tp, double[] times, int[] dfs, int a, int sigma) {
            this.tp = tp;
            this.a = a;
            this.sigma = sigma;
            int m = times.length;
            tt = new double[m + 1];
            lp = new int[m + 1];
            lp[0] = tp.input(0.0);
            for (int i = 0; i < m; i++) {
                tt[i + 1] = times[i];
                lp[i + 1] = tp.log(dfs[i]);
            }
            slope = new int[m];
            for (int i = 0; i < m; i++) {
                slope[i] = tp.scale(tp.sub(lp[i + 1], lp[i]), 1.0 / (tt[i + 1] - tt[i]));
            }
        }

        int section(double x) {
            int i = 0;
            while (i < tt.length - 2 && x >= tt[i + 1]) {
                i++;
            }
            return i;
        }

        int df(double x) {
            int i = section(x);
            return tp.exp(tp.add(lp[i], tp.scale(slope[i], x - tt[i])));
        }

        int forward(double x) {
            return tp.scale(slope[section(x)], -1.0);
        }

        /** {@code -expm1(-a u)}. */
        int oneMinusExp(double u) {
            return tp.scale(tp.expm1(tp.scale(a, -u)), -1.0);
        }

        int alpha(double t) {
            int e = oneMinusExp(t);
            int s2 = tp.mul(sigma, sigma);
            int a2 = tp.scale(tp.mul(a, a), 2.0);
            return tp.add(forward(t), tp.mul(tp.mul(tp.div(s2, a2), e), e));
        }

        int zcb(int r, double t, double mat) {
            int b = tp.div(oneMinusExp(mat - t), a);
            int v = tp.mul(tp.mul(tp.mul(tp.div(tp.mul(sigma, sigma), tp.scale(a, 4.0)), oneMinusExp(2.0 * t)), b), b);
            int lnA = tp.sub(tp.add(tp.log(tp.div(df(mat), df(t))), tp.mul(b, forward(t))), v);
            return tp.exp(tp.sub(lnA, tp.mul(b, r)));
        }
    }

    private static int exercise(Model md, double t, int r, double[] pay, double rate, double phi) {
        Tape tp = md.tp;
        int sum = tp.input(0.0);
        int last = tp.input(0.0);
        double prev = t;
        for (double tj : pay) {
            if (tj > t) {
                last = md.zcb(r, t, tj);
                sum = tp.add(sum, tp.scale(last, tj - prev));
                prev = tj;
            }
        }
        return tp.scale(tp.sub(tp.rsub(1.0, last), tp.scale(sum, rate)), phi);
    }

    /**
     * Price and ladder of a Bermudan swaption on the G-18 scheme.
     *
     * @param times curve pillar times
     * @param dfs curve discount factors
     * @param a mean reversion
     * @param sigma volatility
     * @param pay payment times
     * @param rate fixed rate
     * @param payer true for a payer
     * @param notional notional
     * @param ex exercise times
     * @param g the grid
     * @return price and ladder
     */
    public static Ladder ladder(double[] times, double[] dfs, double a, double sigma, double[] pay, double rate,
                                boolean payer, double notional, double[] ex, ShortRateFd.Grid g) {
        Tape tp = new Tape();
        int[] dfIn = new int[dfs.length];
        for (int i = 0; i < dfs.length; i++) {
            dfIn[i] = tp.input(dfs[i]);
        }
        int aIn = tp.input(a);
        int sIn = tp.input(sigma);
        Model md = new Model(tp, times, dfIn, aIn, sIn);
        double phi = payer ? 1.0 : -1.0;
        int nx = g.nx();
        double tm = ex[ex.length - 1];
        int sx = tp.mul(sIn, tp.sqrt(tp.div(md.oneMinusExp(2.0 * tm), tp.scale(aIn, 2.0))));
        int h = tp.scale(sx, g.width());
        int dx = tp.scale(tp.scale(h, 2.0), 1.0 / (nx - 1));
        int[] x = new int[nx];
        for (int i = 0; i < nx; i++) {
            x[i] = tp.add(tp.scale(h, -1.0), tp.scale(dx, i));
        }
        int zero = tp.input(0.0);
        int[] v = new int[nx];
        int al = md.alpha(tm);
        for (int i = 0; i < nx; i++) {
            v[i] = tp.max(exercise(md, tm, tp.add(x[i], al), pay, rate, phi), zero);
        }
        int s2 = tp.scale(tp.mul(sIn, sIn), 0.5);
        int diff = tp.div(s2, tp.mul(dx, dx));
        int twoDx = tp.scale(dx, 2.0);
        int[] lo = new int[nx];
        int[] di = new int[nx];
        int[] up = new int[nx];
        double[] knots = new double[ex.length + 1];
        System.arraycopy(ex, 0, knots, 1, ex.length);
        for (int k = ex.length; k >= 1; k--) {
            double t1 = knots[k - 1];
            double span = knots[k] - t1;
            long n = Math.max(1L, (long) Math.ceil(g.stepsPerYear() * span));
            double dt = span / n;
            for (long j = n - 1; j >= 0; j--) {
                double t = t1 + j * dt;
                int alt = md.alpha(t);
                for (int i = 1; i < nx - 1; i++) {
                    int drift = tp.div(tp.mul(aIn, x[i]), twoDx);
                    lo[i] = tp.scale(tp.add(diff, drift), -dt);
                    int b = tp.sub(tp.scale(diff, -2.0), tp.add(x[i], alt));
                    di[i] = tp.rsub(1.0, tp.scale(b, dt));
                    up[i] = tp.scale(tp.sub(diff, drift), -dt);
                }
                di[1] = tp.add(di[1], tp.scale(lo[1], 2.0));
                up[1] = tp.sub(up[1], lo[1]);
                di[nx - 2] = tp.add(di[nx - 2], tp.scale(up[nx - 2], 2.0));
                lo[nx - 2] = tp.sub(lo[nx - 2], up[nx - 2]);
                int len = nx - 2;
                int[] c = new int[len];
                int[] d = new int[len];
                c[0] = tp.div(up[1], di[1]);
                d[0] = tp.div(v[1], di[1]);
                for (int r = 1; r < len; r++) {
                    int i = 1 + r;
                    int den = tp.sub(di[i], tp.mul(lo[i], c[r - 1]));
                    c[r] = tp.div(up[i], den);
                    d[r] = tp.div(tp.sub(v[i], tp.mul(lo[i], d[r - 1])), den);
                }
                v[nx - 2] = d[len - 1];
                for (int r = len - 2; r >= 0; r--) {
                    v[1 + r] = tp.sub(d[r], tp.mul(c[r], v[2 + r]));
                }
                v[0] = tp.sub(tp.scale(v[1], 2.0), v[2]);
                v[nx - 1] = tp.sub(tp.scale(v[nx - 2], 2.0), v[nx - 3]);
            }
            if (k - 1 > 0) {
                int alk = md.alpha(t1);
                for (int i = 0; i < nx; i++) {
                    v[i] = tp.max(v[i], exercise(md, t1, tp.add(x[i], alk), pay, rate, phi));
                }
            }
        }
        int out = tp.scale(v[(nx - 1) / 2], notional);
        double[] adj = tp.gradient(out);
        double[] dDf = new double[dfs.length];
        for (int i = 0; i < dfs.length; i++) {
            dDf[i] = adj[dfIn[i]];
        }
        return new Ladder(tp.value(out), dDf, adj[aIn], adj[sIn]);
    }
}
