package org.quantforge.research;

import java.math.BigInteger;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.quantforge.core.Finite;
import org.quantforge.core.Interpolation;
import org.quantforge.core.QfError;

/**
 * Stage J wave 3 (rulings J-W3-1 to J-W3-14): scenario stress (06-risk/scenario-stress.md), interpolation
 * backtests (11-research/interp-backtest.md) and drift detectors (11-research/drift-detectors.md).
 */
public final class StressDrift {
    public static final double PSI_FLOOR = 1e-4;

    private StressDrift() {}

    private static QfError input(String why) {
        return new QfError("E_INPUT", why);
    }

    private static QfError domain(String why) {
        return new QfError("E_DOMAIN", why);
    }

    private static boolean increasing(double[] x) {
        for (int i = 1; i < x.length; i++) {
            if (!(x[i] > x[i - 1])) {
                return false;
            }
        }
        return true;
    }

    private static void tenors(double[] t, String field) {
        for (double v : t) {
            if (!(v > 0)) {
                throw new QfError("E_DOMAIN", field + " must be positive and strictly increasing", field);
            }
        }
        if (!increasing(t)) {
            throw new QfError("E_DOMAIN", field + " must be positive and strictly increasing", field);
        }
    }

    /** Correctly rounded sum (Shewchuk partials, as Python's {@code math.fsum}) for finite inputs. */
    public static double fsum(double[] v) {
        double[] p = new double[Math.max(4, v.length + 1)];
        int np = 0;
        for (double xv : v) {
            double x = xv;
            int k = 0;
            for (int j = 0; j < np; j++) {
                double y = p[j];
                if (Math.abs(x) < Math.abs(y)) {
                    double t = x;
                    x = y;
                    y = t;
                }
                double hi = x + y;
                double lo = y - (hi - x);
                if (lo != 0.0) {
                    p[k++] = lo;
                }
                x = hi;
            }
            np = k;
            p[np++] = x;
        }
        if (np == 0) {
            return 0.0;
        }
        double hi = p[--np];
        double lo = 0.0;
        while (np > 0) {
            double x = hi;
            double y = p[--np];
            hi = x + y;
            lo = y - (hi - x);
            if (lo != 0.0) {
                break;
            }
        }
        if (np > 0 && ((lo < 0 && p[np - 1] < 0) || (lo > 0 && p[np - 1] > 0))) {
            double y = lo * 2.0;
            double x = hi + y;
            if (y == x - hi) {
                hi = x;
            }
        }
        return hi;
    }

    // --- Scenarios (J-W3-2 to J-W3-5) ---------------------------------------------------------------

    public record Shock(double[] startYields, double[] endYields, double[] shiftBp, double levelBp, double slopeBp) {}

    public static Shock historicalShock(List<LocalDate> dates, double[] tenor, double[][] yields, LocalDate start,
            LocalDate end) {
        Finite.check("tenors", tenor);
        Finite.check("yields", yields);
        int n = tenor.length;
        boolean bad = dates.isEmpty() || n == 0 || yields.length != dates.size();
        for (double[] r : yields) {
            bad |= r.length != n;
        }
        if (bad) {
            throw input("need one row per date and one column per tenor");
        }
        for (int i = 1; i < dates.size(); i++) {
            if (!dates.get(i).isAfter(dates.get(i - 1))) {
                throw new QfError("E_DATE_ORDER", "dates must be strictly increasing", "dates");
            }
        }
        tenors(tenor, "tenors");
        if (!end.isAfter(start)) {
            throw new QfError("E_DATE_ORDER", "end_date must be after start_date", "end_date");
        }
        int a = dates.indexOf(start);
        if (a < 0) {
            throw new QfError("E_DOMAIN", "start_date is not in dates", "start_date");
        }
        int b = dates.indexOf(end);
        if (b < 0) {
            throw new QfError("E_DOMAIN", "end_date is not in dates", "end_date");
        }
        double[] y0 = yields[a].clone();
        double[] y1 = yields[b].clone();
        double[] shift = new double[n];
        for (int i = 0; i < n; i++) {
            shift[i] = 100.0 * (y1[i] - y0[i]);
        }
        return new Shock(y0, y1, shift, fsum(shift) / n, shift[n - 1] - shift[0]);
    }

    static double flatLinear(double[] x, double[] y, double t) {
        int l = x.length - 1;
        if (t <= x[0]) {
            return y[0];
        }
        if (t >= x[l]) {
            return y[l];
        }
        int i = 0;
        for (int j = 0; j < l; j++) {
            if (x[j] <= t) {
                i = j;
            }
        }
        double u = (t - x[i]) / (x[i + 1] - x[i]);
        return y[i] + u * (y[i + 1] - y[i]);
    }

    /** {@code pnl} is null when no {@code dv01} is given. */
    public record Replay(double[] appliedBp, double[] shockedYields, Double pnl) {}

    public static Replay replay(double[] baseTenors, double[] baseYields, double[] shockTenors, double[] shockBp,
            double scale, double[] dv01) {
        Finite.check("base_tenors", baseTenors);
        Finite.check("base_yields", baseYields);
        Finite.check("shock_tenors", shockTenors);
        Finite.check("shock_bp", shockBp);
        Finite.check("scale", scale);
        if (dv01 != null) {
            Finite.check("dv01", dv01);
        }
        if (baseTenors.length == 0 || baseYields.length != baseTenors.length) {
            throw input("base_yields must match base_tenors");
        }
        if (shockTenors.length == 0 || shockBp.length != shockTenors.length) {
            throw input("shock_bp must match shock_tenors");
        }
        if (dv01 != null && dv01.length != baseTenors.length) {
            throw input("dv01 must match base_tenors");
        }
        tenors(baseTenors, "base_tenors");
        tenors(shockTenors, "shock_tenors");
        int n = baseTenors.length;
        double[] applied = new double[n];
        double[] shocked = new double[n];
        for (int i = 0; i < n; i++) {
            applied[i] = scale * flatLinear(shockTenors, shockBp, baseTenors[i]);
            shocked[i] = baseYields[i] + applied[i] / 100.0;
        }
        Double pnl = null;
        if (dv01 != null) {
            double[] t = new double[n];
            for (int i = 0; i < n; i++) {
                t[i] = dv01[i] * applied[i];
            }
            pnl = -fsum(t);
        }
        return new Replay(applied, shocked, pnl);
    }

    // --- Interpolation backtests (J-W3-8, J-W3-9) ---------------------------------------------------

    public record LooResult(double[] errors, double maxAbsError, double rmse) {}

    public record SurfaceResult(double[][] errors, double maxAbsError, double rmse) {}

    private static double[] summary(double[] e) {
        double mx = 0.0;
        double[] sq = new double[e.length];
        for (int i = 0; i < e.length; i++) {
            mx = Math.max(mx, Math.abs(e[i]));
            sq[i] = e[i] * e[i];
        }
        return new double[] {mx, Math.sqrt(fsum(sq) / e.length)};
    }

    private static int minKnots(Interpolation.Method m) {
        return switch (m) {
            case CUBIC_NATURAL, TENSION -> 3;
            case CUBIC_NOT_A_KNOT -> 4;
            default -> 2;
        };
    }

    private static final Interpolation.Params NO_PARAMS = new Interpolation.Params(0.0, 0.0, 0.0);

    public static LooResult interpLoo(Interpolation.Method method, double[] x, double[] y) {
        Finite.check("x", x);
        Finite.check("y", y);
        int n = x.length;
        if (y.length != n || n < 3 || n - 1 < minKnots(method)) {
            throw input("need equal lengths, n >= 3 and n - 1 at the method's minimum knots");
        }
        if (!increasing(x)) {
            throw input("knots must be strictly increasing");
        }
        double[] errors = new double[n - 2];
        for (int i = 1; i < n - 1; i++) {
            double[] xs = new double[n - 1];
            double[] ys = new double[n - 1];
            for (int j = 0, k = 0; j < n; j++) {
                if (j != i) {
                    xs[k] = x[j];
                    ys[k++] = y[j];
                }
            }
            errors[i - 1] = Interpolation.evaluate(method, xs, ys, new double[] {x[i]}, NO_PARAMS).values()[0] - y[i];
        }
        double[] s = summary(errors);
        return new LooResult(errors, s[0], s[1]);
    }

    public static SurfaceResult surfaceHoldout(Interpolation.Method method, double[] expiries, double[] strikes,
            double[][] vols, long[] holdout) {
        Finite.check("expiries", expiries);
        Finite.check("strikes", strikes);
        Finite.check("vols", vols);
        int m = strikes.length;
        boolean bad = expiries.length == 0 || vols.length != expiries.length;
        for (double[] r : vols) {
            bad |= r.length != m;
        }
        if (bad) {
            throw input("vols must have one row per expiry and one column per strike");
        }
        if (!increasing(strikes)) {
            throw input("strikes must be strictly increasing");
        }
        boolean badHold = holdout.length == 0;
        for (int i = 0; i < holdout.length; i++) {
            badHold |= !(holdout[i] > 0 && holdout[i] < m - 1) || (i > 0 && holdout[i] <= holdout[i - 1]);
        }
        if (badHold) {
            throw input("holdout must be distinct sorted interior strike indices");
        }
        boolean[] held = new boolean[m];
        for (long h : holdout) {
            held[(int) h] = true;
        }
        int kept = m - holdout.length;
        if (kept < minKnots(method)) {
            throw input("too few kept strikes for the method");
        }
        for (double t : expiries) {
            if (!(t > 0)) {
                throw domain("expiries must be positive");
            }
        }
        for (double[] r : vols) {
            for (double v : r) {
                if (!(v > 0)) {
                    throw domain("vols must be positive");
                }
            }
        }
        double[] ks = new double[kept];
        double[] at = new double[holdout.length];
        for (int j = 0, k = 0; j < m; j++) {
            if (!held[j]) {
                ks[k++] = strikes[j];
            }
        }
        for (int h = 0; h < holdout.length; h++) {
            at[h] = strikes[(int) holdout[h]];
        }
        double[][] errors = new double[expiries.length][];
        double[] flat = new double[expiries.length * holdout.length];
        int f = 0;
        for (int e = 0; e < expiries.length; e++) {
            double t = expiries[e];
            double[] row = vols[e];
            double[] w = new double[kept];
            for (int j = 0, k = 0; j < m; j++) {
                if (!held[j]) {
                    w[k++] = row[j] * row[j] * t;
                }
            }
            double[] fit = Interpolation.evaluate(method, ks, w, at, NO_PARAMS).values();
            for (double v : fit) {
                if (!(v > 0)) {
                    throw domain("interpolated total variance is not positive");
                }
            }
            errors[e] = new double[holdout.length];
            for (int h = 0; h < holdout.length; h++) {
                errors[e][h] = Math.sqrt(fit[h] / t) - row[(int) holdout[h]];
                flat[f++] = errors[e][h];
            }
        }
        double[] s = summary(flat);
        return new SurfaceResult(errors, s[0], s[1]);
    }

    // --- Drift detectors (J-W3-10 to J-W3-13) -------------------------------------------------------

    public record Alarms(long[] alarms, long[] directions, double sPlus, double sMinus) {}

    private static long[] longs(List<Long> l) {
        long[] out = new long[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = l.get(i);
        }
        return out;
    }

    /** J-W3-10: tabular two-sided CUSUM on z = (x - mu0) / sigma; alarm when a sum exceeds h. */
    public static Alarms cusum(double[] x, double k, double h, double mu0, double sigma, boolean reset) {
        Finite.check("x", x);
        Finite.check("k", k);
        Finite.check("h", h);
        Finite.check("mu0", mu0);
        Finite.check("sigma", sigma);
        if (x.length == 0) {
            throw input("x must not be empty");
        }
        if (!(k > 0) || !(h > 0) || !(sigma > 0)) {
            throw domain("k, h and sigma must be positive");
        }
        double sp = 0.0;
        double sm = 0.0;
        List<Long> al = new ArrayList<>();
        List<Long> di = new ArrayList<>();
        for (int t = 0; t < x.length; t++) {
            double z = (x[t] - mu0) / sigma;
            sp = Math.max(0.0, sp + z - k);
            sm = Math.max(0.0, sm - z - k);
            if (sp > h || sm > h) {
                al.add((long) t);
                di.add(sp > h ? 1L : -1L);
                if (!reset) {
                    break;
                }
                sp = 0.0;
                sm = 0.0;
            }
        }
        return new Alarms(longs(al), longs(di), sp, sm);
    }

    /** J-W3-11 (as corrected): running mean at each step; restart every counter after an alarm. */
    public static Alarms pageHinkley(double[] x, double delta, double lambda, String direction, boolean reset) {
        Finite.check("x", x);
        Finite.check("delta", delta);
        Finite.check("lambda", lambda);
        if (x.length == 0) {
            throw input("x must not be empty");
        }
        if (!(delta >= 0) || !(lambda > 0)) {
            throw domain("delta must be >= 0 and lambda > 0");
        }
        if (!direction.equals("up") && !direction.equals("down") && !direction.equals("both")) {
            throw input("direction must be up, down or both");
        }
        List<Long> al = new ArrayList<>();
        List<Long> di = new ArrayList<>();
        double n = 0;
        double total = 0;
        double up = 0;
        double upMin = 0;
        double dn = 0;
        double dnMin = 0;
        for (int t = 0; t < x.length; t++) {
            n += 1;
            total += x[t];
            double mean = total / n;
            up += x[t] - mean - delta;
            dn += mean - x[t] - delta;
            upMin = Math.min(upMin, up);
            dnMin = Math.min(dnMin, dn);
            boolean hitUp = !direction.equals("down") && up - upMin > lambda;
            boolean hitDn = !direction.equals("up") && dn - dnMin > lambda;
            if (hitUp || hitDn) {
                al.add((long) t);
                di.add(hitUp ? 1L : -1L);
                if (!reset) {
                    break;
                }
                n = 0;
                total = 0;
                up = 0;
                upMin = 0;
                dn = 0;
                dnMin = 0;
            }
        }
        return new Alarms(longs(al), longs(di), 0.0, 0.0);
    }

    public record Psi(double psi, double[] referenceShares, double[] testShares, boolean alarm) {}

    /** J-W3-12: bins at the reference's type-1 quantiles, shares floored at 1e-4 without renormalising. */
    public static Psi psi(double[] reference, double[] test, long bins, double threshold) {
        Finite.check("reference", reference);
        Finite.check("test", test);
        Finite.check("threshold", threshold);
        if (bins < 2) {
            throw input("bins must be at least 2");
        }
        int b = (int) Math.min(bins, Integer.MAX_VALUE);
        if (reference.length < b || test.length < b) {
            throw input("reference and test need at least bins values each");
        }
        if (!(threshold > 0)) {
            throw domain("threshold must be positive");
        }
        double[] r = reference.clone();
        Arrays.sort(r);
        long n = r.length;
        double[] edges = new double[b - 1];
        for (int j = 1; j < b; j++) {
            edges[j - 1] = r[(int) ((j * n + b - 1) / b) - 1];
        }
        double[] rs = shares(reference, edges, b);
        double[] ts = shares(test, edges, b);
        double[] terms = new double[b];
        for (int i = 0; i < b; i++) {
            terms[i] = (ts[i] - rs[i]) * Math.log(ts[i] / rs[i]);
        }
        double v = fsum(terms);
        return new Psi(v, rs, ts, v > threshold);
    }

    private static double[] shares(double[] s, double[] edges, int b) {
        long[] c = new long[b];
        for (double v : s) {
            int lo = 0;
            int hi = b - 1;
            while (lo < hi) {
                int mid = (lo + hi) >>> 1;
                if (v <= edges[mid]) {
                    hi = mid;
                } else {
                    lo = mid + 1;
                }
            }
            c[lo]++;
        }
        double[] out = new double[b];
        for (int i = 0; i < b; i++) {
            out[i] = Math.max((double) c[i] / s.length, PSI_FLOOR);
        }
        return out;
    }

    /** D n m as an integer: max |i m - j n| over the merged order, ties stepped together. */
    static long ksDScaled(double[] a, double[] b) {
        double[] xa = a.clone();
        double[] xb = b.clone();
        Arrays.sort(xa);
        Arrays.sort(xb);
        int n = xa.length;
        int m = xb.length;
        int i = 0;
        int j = 0;
        long best = 0;
        while (i < n || j < m) {
            double v = Math.min(i < n ? xa[i] : Double.POSITIVE_INFINITY, j < m ? xb[j] : Double.POSITIVE_INFINITY);
            while (i < n && xa[i] == v) {
                i++;
            }
            while (j < m && xb[j] == v) {
                j++;
            }
            best = Math.max(best, Math.abs((long) i * m - (long) j * n));
        }
        return best;
    }

    /** P(D' n m >= d) by counting lattice paths with |i m - j n| < d, in big integers; one final division. */
    static double ksP(int n, int m, long d) {
        if (d <= 0) {
            return 1.0;
        }
        BigInteger[] row = new BigInteger[m + 1];
        row[0] = BigInteger.ONE;
        for (int j = 1; j <= m; j++) {
            row[j] = (long) j * n < d ? row[j - 1] : BigInteger.ZERO;
        }
        for (int i = 1; i <= n; i++) {
            if (!((long) i * m < d)) {
                row[0] = BigInteger.ZERO;
            }
            for (int j = 1; j <= m; j++) {
                row[j] = Math.abs((long) i * m - (long) j * n) < d ? row[j].add(row[j - 1]) : BigInteger.ZERO;
            }
        }
        BigInteger total = BigInteger.ONE;
        for (int k = 1; k <= Math.min(n, m); k++) {
            total = total.multiply(BigInteger.valueOf(n + m - k + 1)).divide(BigInteger.valueOf(k));
        }
        return ratio(total.subtract(row[m]), total);
    }

    /**
     * Correctly rounded a / b for a >= 0, b > 0, like Python's float(Fraction(a, b)): an exact integer
     * division at the target ulp plus one guard bit, then round half to even on the guard bit and the
     * remainder (sticky). Subnormal results keep fewer bits; no intermediate decimal rounding.
     */
    static double ratio(BigInteger a, BigInteger b) {
        if (a.signum() == 0) {
            return 0.0;
        }
        // e = floor(log2(a / b)).
        int e = a.bitLength() - b.bitLength();
        BigInteger lhs = e < 0 ? a.shiftLeft(-e) : a;
        BigInteger rhs = e > 0 ? b.shiftLeft(e) : b;
        if (lhs.compareTo(rhs) < 0) {
            e--;
        }
        int u = Math.max(e - 52, -1074); // exponent of the result's ulp
        int shift = 1 - u; // one guard bit below the ulp
        BigInteger num = shift >= 0 ? a.shiftLeft(shift) : a;
        BigInteger den = shift >= 0 ? b : b.shiftLeft(-shift);
        BigInteger[] qr = num.divideAndRemainder(den);
        BigInteger q2 = qr[0];
        boolean guard = q2.testBit(0);
        boolean sticky = qr[1].signum() != 0;
        BigInteger q = q2.shiftRight(1);
        if (guard && (sticky || q.testBit(0))) {
            q = q.add(BigInteger.ONE);
        }
        return Math.scalb(q.doubleValue(), u); // q <= 2^53: exact, and so is the scaling
    }

    public record Ks(double statistic, double pValue, boolean reject) {}

    /** J-W3-13: two-sample KS statistic and exact two-sided p-value. */
    public static Ks ks(double[] a, double[] b, double level) {
        Finite.check("a", a);
        Finite.check("b", b);
        Finite.check("level", level);
        if (a.length == 0 || b.length == 0) {
            throw input("a and b must not be empty");
        }
        if (!(level > 0 && level < 1)) {
            throw domain("level must lie in (0, 1)");
        }
        long d = ksDScaled(a, b);
        double p = ksP(a.length, b.length, d);
        return new Ks((double) d / ((double) a.length * b.length), p, p <= level);
    }
}
