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
     * Price and ladder with every operation on the tape: the slow reference for {@link #ladder}.
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
    public static Ladder ladderTape(double[] times, double[] dfs, double a, double sigma, double[] pay, double rate,
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

    /** Thomas algorithm on rows {@code 1..nx-2} (boundary coupling already folded in). */
    private static void thomas(double[] lo, double[] di, double[] up, double[] rhs, double[] out, int nx,
                               double[] c, double[] d) {
        int len = nx - 2;
        c[0] = up[1] / di[1];
        d[0] = rhs[1] / di[1];
        for (int r = 1; r < len; r++) {
            int i = 1 + r;
            double den = di[i] - lo[i] * c[r - 1];
            c[r] = up[i] / den;
            d[r] = (rhs[i] - lo[i] * d[r - 1]) / den;
        }
        out[nx - 2] = d[len - 1];
        for (int r = len - 2; r >= 0; r--) {
            out[1 + r] = d[r] - c[r] * out[2 + r];
        }
    }

    /** The folded tridiagonal rows of one implicit step, exactly as {@link ShortRateFd}. */
    private static void coefficients(double[] lo, double[] di, double[] up, double diff, double[] q, double[] x,
                                     double al, double dt, int nx) {
        for (int i = 1; i < nx - 1; i++) {
            lo[i] = -dt * (diff + q[i]);
            di[i] = 1.0 - dt * (-2.0 * diff - (x[i] + al));
            up[i] = -dt * (diff - q[i]);
        }
        di[1] += 2.0 * lo[1];
        up[1] -= lo[1];
        di[nx - 2] += 2.0 * up[nx - 2];
        lo[nx - 2] -= up[nx - 2];
    }

    /**
     * Price and ladder of a Bermudan swaption on the G-18 scheme. The setup (grid, drift term, alpha per step,
     * exercise values) is taped; the time-stepping loop, where nearly all the work is, has a hand-written adjoint.
     * For each step {@code M v_new = v_old} the adjoint solves {@code M^T lambda = vbar} with the same Thomas
     * kernel and forms {@code Mbar = -lambda v_new^T} on the three diagonals, unfolding the boundary rows; each
     * exercise {@code max} passes its adjoint to the active branch. Agrees with {@link #ladderTape} to rounding.
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
        int mEx = ex.length;
        double tm = ex[mEx - 1];
        int sxN = tp.mul(sIn, tp.sqrt(tp.div(md.oneMinusExp(2.0 * tm), tp.scale(aIn, 2.0))));
        int hN = tp.scale(sxN, g.width());
        int dxN = tp.scale(tp.scale(hN, 2.0), 1.0 / (nx - 1));
        int[] xN = new int[nx];
        double[] x = new double[nx];
        for (int i = 0; i < nx; i++) {
            xN[i] = tp.add(tp.scale(hN, -1.0), tp.scale(dxN, i));
            x[i] = tp.value(xN[i]);
        }
        int dN = tp.div(tp.scale(tp.mul(sIn, sIn), 0.5), tp.mul(dxN, dxN));
        double dx = tp.value(dxN);
        double diff = tp.value(dN);
        double[] knots = new double[mEx + 1];
        System.arraycopy(ex, 0, knots, 1, mEx);
        // exercise at knot k and node i: phi (1 - P_n - K sum tau_j P_j), P_j = A_j exp(-b_j r_i), r_i = x_i +
        // alpha(t_k); only A_j, b_j and alpha are taped, the per-node work has a hand-written adjoint
        int[] exAl = new int[mEx + 1];
        int[][] exA = new int[mEx + 1][];
        int[][] exB = new int[mEx + 1][];
        double[][] exTau = new double[mEx + 1][];
        double[][] exVal = new double[mEx + 1][nx];
        double[][] exBar = new double[mEx + 1][nx];
        for (int k = 1; k <= mEx; k++) {
            double t = knots[k];
            exAl[k] = md.alpha(t);
            int cnt = 0;
            for (double tj : pay) {
                if (tj > t) {
                    cnt++;
                }
            }
            exA[k] = new int[cnt];
            exB[k] = new int[cnt];
            exTau[k] = new double[cnt];
            int idx = 0;
            double prev = t;
            int ft = md.forward(t);
            int vt = md.oneMinusExp(2.0 * t);
            int dft = md.df(t);
            for (double tj : pay) {
                if (tj > t) {
                    int b = tp.div(md.oneMinusExp(tj - t), aIn);
                    int v = tp.mul(tp.mul(tp.mul(tp.div(tp.mul(sIn, sIn), tp.scale(aIn, 4.0)), vt), b), b);
                    exA[k][idx] = tp.exp(tp.sub(tp.add(tp.log(tp.div(md.df(tj), dft)), tp.mul(b, ft)), v));
                    exB[k][idx] = b;
                    exTau[k][idx] = tj - prev;
                    prev = tj;
                    idx++;
                }
            }
            double al = tp.value(exAl[k]);
            for (int i = 0; i < nx; i++) {
                double r = x[i] + al;
                double sum = 0.0;
                double last = 0.0;
                for (int j = 0; j < cnt; j++) {
                    last = tp.value(exA[k][j]) * Math.exp(-tp.value(exB[k][j]) * r);
                    sum += exTau[k][j] * last;
                }
                exVal[k][i] = phi * (1.0 - last - rate * sum);
            }
        }
        int steps = 0;
        long[] per = new long[mEx + 1];
        for (int k = 1; k <= mEx; k++) {
            per[k] = Math.max(1L, (long) Math.ceil(g.stepsPerYear() * (knots[k] - knots[k - 1])));
            steps += (int) per[k];
        }
        int[] alN = new int[steps];
        double[] dtS = new double[steps];
        double[][] vNew = new double[steps][];
        boolean[][] active = new boolean[mEx + 1][nx];
        double[] v = new double[nx];
        for (int i = 0; i < nx; i++) {
            double e = exVal[mEx][i];
            active[mEx][i] = e >= 0.0;
            v[i] = Math.max(e, 0.0);
        }
        double[] lo = new double[nx];
        double[] di = new double[nx];
        double[] up = new double[nx];
        double[] rhs = new double[nx];
        double[] c = new double[nx];
        double[] d = new double[nx];
        double[] q = new double[nx];
        for (int i = 1; i < nx - 1; i++) {
            q[i] = a * x[i] / (2.0 * dx);
        }
        int s = 0;
        for (int k = mEx; k >= 1; k--) {
            double t1 = knots[k - 1];
            double dt = (knots[k] - t1) / per[k];
            for (long j = per[k] - 1; j >= 0; j--) {
                double t = t1 + j * dt;
                alN[s] = md.alpha(t);
                dtS[s] = dt;
                coefficients(lo, di, up, diff, q, x, tp.value(alN[s]), dt, nx);
                System.arraycopy(v, 0, rhs, 0, nx);
                thomas(lo, di, up, rhs, v, nx, c, d);
                v[0] = 2.0 * v[1] - v[2];
                v[nx - 1] = 2.0 * v[nx - 2] - v[nx - 3];
                vNew[s] = v.clone();
                s++;
            }
            if (k - 1 > 0) {
                for (int i = 0; i < nx; i++) {
                    double e = exVal[k - 1][i];
                    active[k - 1][i] = !(v[i] >= e);
                    v[i] = Math.max(v[i], e);
                }
            }
        }
        double price = notional * v[(nx - 1) / 2];

        double[] adj = new double[tp.size()];
        double[] vb = new double[nx];
        vb[(nx - 1) / 2] = notional;
        double dBar = 0.0;
        double[] qBar = new double[nx];
        double[] xBar = new double[nx];
        double[] lam = new double[nx];
        double[] g2 = new double[nx];
        double[] tl = new double[nx];
        double[] tu = new double[nx];
        s = steps - 1;
        for (int k = 1; k <= mEx; k++) {
            if (k - 1 > 0) {
                for (int i = 0; i < nx; i++) {
                    if (active[k - 1][i]) {
                        exBar[k - 1][i] += vb[i];
                        vb[i] = 0.0;
                    }
                }
            }
            for (long j = 0; j < per[k]; j++, s--) {
                double dt = dtS[s];
                double[] vn = vNew[s];
                coefficients(lo, di, up, diff, q, x, tp.value(alN[s]), dt, nx);
                vb[1] += 2.0 * vb[0];
                vb[2] -= vb[0];
                vb[nx - 2] += 2.0 * vb[nx - 1];
                vb[nx - 3] -= vb[nx - 1];
                vb[0] = 0.0;
                vb[nx - 1] = 0.0;
                for (int i = 1; i < nx - 1; i++) {
                    tl[i] = up[i - 1];
                    tu[i] = lo[i + 1];
                }
                System.arraycopy(vb, 0, g2, 0, nx);
                thomas(tl, di, tu, g2, lam, nx, c, d);
                double alBar = 0.0;
                for (int i = 1; i < nx - 1; i++) {
                    double li = lam[i];
                    double loB = i > 1 ? -li * vn[i - 1] : 0.0;
                    double diB = -li * vn[i];
                    double upB = i < nx - 2 ? -li * vn[i + 1] : 0.0;
                    if (i == 1) {
                        loB += 2.0 * diB - upB;
                    }
                    if (i == nx - 2) {
                        upB += 2.0 * diB - loB;
                    }
                    dBar += -dt * (loB + upB) + 2.0 * dt * diB;
                    qBar[i] += -dt * (loB - upB);
                    xBar[i] += dt * diB;
                    alBar += dt * diB;
                    vb[i] = li;
                }
                adj[alN[s]] += alBar;
            }
        }
        for (int i = 0; i < nx; i++) {
            if (active[mEx][i]) {
                exBar[mEx][i] += vb[i];
            }
        }
        for (int k = 1; k <= mEx; k++) {
            int cnt = exA[k].length;
            double al = tp.value(exAl[k]);
            double alBar = 0.0;
            for (int i = 0; i < nx; i++) {
                double eb = exBar[k][i];
                if (eb == 0.0) {
                    continue;
                }
                double r = x[i] + al;
                double rBar = 0.0;
                for (int j = 0; j < cnt; j++) {
                    double bj = tp.value(exB[k][j]);
                    double e = Math.exp(-bj * r);
                    double pj = tp.value(exA[k][j]) * e;
                    double pBar = phi * eb * (-rate * exTau[k][j] - (j == cnt - 1 ? 1.0 : 0.0));
                    adj[exA[k][j]] += pBar * e;
                    adj[exB[k][j]] -= pBar * r * pj;
                    rBar -= pBar * bj * pj;
                }
                xBar[i] += rBar;
                alBar += rBar;
            }
            adj[exAl[k]] += alBar;
        }
        double dxBar = 0.0;
        double qaBar = 0.0;
        for (int i = 1; i < nx - 1; i++) {
            qaBar += qBar[i] * x[i] / (2.0 * dx);
            xBar[i] += qBar[i] * a / (2.0 * dx);
            dxBar -= qBar[i] * a * x[i] / (2.0 * dx * dx);
        }
        adj[aIn] += qaBar;
        adj[dN] += dBar;
        adj[dxN] += dxBar;
        for (int i = 0; i < nx; i++) {
            adj[xN[i]] += xBar[i];
        }
        tp.sweep(adj);
        double[] dDf = new double[dfs.length];
        for (int i = 0; i < dfs.length; i++) {
            dDf[i] = adj[dfIn[i]];
        }
        return new Ladder(price, dDf, adj[aIn], adj[sIn]);
    }
}
