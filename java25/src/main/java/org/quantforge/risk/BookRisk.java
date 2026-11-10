package org.quantforge.risk;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.Conventions;
import org.quantforge.core.Finite;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Schedule;

/** Book sensitivities by the IFT chain rule, PCA, cross gamma, jump to default (book-sensitivities.md). */
public final class BookRisk {
    private BookRisk() {}

    public record Swap(String id, long tenorYears, double fixedRate, boolean payer) {}

    public record OisSensitivity(double[] pv, double bookPv, double[][] quoteSensitivity, double[] bookSensitivity,
                                 LocalDate[] pillars, double[][] zeroJacobian) {}

    /**
     * Exact derivatives (ruling F-29): d pv/dq = (d pv/dx)(dR/dx)^-1 with x = ln D at the pillars. On LOG_LINEAR_DF
     * and LINEAR_ZERO, ln D at any date is linear in x, so d ln D(d)/dx is exact; other methods use a Richardson
     * derivative of ln D(d) in x.
     */
    public static OisSensitivity oisSensitivity(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes,
                                                Curve.Interpolation interp, List<Swap> swaps) {
        if (swaps.isEmpty()) {
            throw new QfError("E_INPUT", "no swaps", "swaps");
        }
        Set<String> ids = new HashSet<>();
        for (Swap s : swaps) {
            Finite.check("fixed_rate", s.fixedRate());
            if (!ids.add(s.id())) {
                throw new QfError("E_INPUT", "duplicate swap id " + s.id(), "swaps");
            }
            if (s.tenorYears() < 1) {
                throw new QfError("E_DOMAIN", "tenor_years must be at least 1", "tenor_years");
            }
        }
        Curve curve = Ois.bootstrap(c, asOf, quotes, interp, CurveSolver.Method.SEQUENTIAL, null).curve();
        LocalDate[] pillars = curve.dates();
        int n = pillars.length;
        double[] x = new double[n];
        double[] df = curve.discountFactors();
        for (int i = 0; i < n; i++) {
            x[i] = Math.log(df[i]);
        }
        List<Ois.Legs> quoteLegs = new ArrayList<>();
        for (Ois.Quote q : quotes) {
            quoteLegs.add(Ois.legs(c, asOf, q.tenor()));
        }
        List<Ois.Legs> swapLegs = new ArrayList<>();
        for (Swap s : swaps) {
            swapLegs.add(Ois.legs(c, asOf, s.tenorYears() + "Y"));
        }
        Weights w = new Weights(curve, interp, x);
        double[][] jac = new double[n][];
        for (int j = 0; j < n; j++) {
            Ois.Legs l = quoteLegs.get(j);
            double a = l.annuity(curve);
            double par = l.floating(curve) / a;
            jac[j] = w.gradient(l, 1.0 / a, -par / a);
        }
        double[][] m = inverse(jac);
        int ns = swaps.size();
        double[] pv = new double[ns];
        double[][] qs = new double[ns][n];
        double bookPv = 0.0;
        double[] bookSens = new double[n];
        for (int k = 0; k < ns; k++) {
            Swap s = swaps.get(k);
            Ois.Legs l = swapLegs.get(k);
            double sign = s.payer() ? 1.0 : -1.0;
            pv[k] = sign * (l.floating(curve) - s.fixedRate() * l.annuity(curve));
            double[] g = w.gradient(l, sign, -sign * s.fixedRate());
            for (int j = 0; j < n; j++) {
                double v = 0.0;
                for (int i = 0; i < n; i++) {
                    v += g[i] * m[i][j];
                }
                qs[k][j] = v;
                bookSens[j] += v;
            }
            bookPv += pv[k];
        }
        double[][] zj = new double[n][n];
        for (int i = 0; i < n; i++) {
            double t = curve.time(pillars[i]);
            for (int j = 0; j < n; j++) {
                zj[i][j] = m[i][j] == 0.0 ? 0.0 : -m[i][j] / t;
            }
        }
        return new OisSensitivity(pv, bookPv, qs, bookSens, pillars, zj);
    }

    /** d ln D(d) / dx_i at the solution, cached per date. */
    private static final class Weights {
        final Curve curve;
        final Curve.Interpolation interp;
        final double[] x;
        final Map<LocalDate, double[]> cache = new HashMap<>();
        final boolean linear;

        Weights(Curve curve, Curve.Interpolation interp, double[] x) {
            this.curve = curve;
            this.interp = interp;
            this.x = x;
            linear = interp == Curve.Interpolation.LOG_LINEAR_DF || interp == Curve.Interpolation.LINEAR_ZERO;
        }

        private double lnAt(double[] y, LocalDate d) {
            double[] f = new double[y.length];
            for (int i = 0; i < y.length; i++) {
                f[i] = Math.exp(y[i]);
            }
            return Math.log(Curve.of(curve.asOf(), interp, curve.dates(), f, curve.jumps(), curve.shape())
                    .discount(d));
        }

        double[] at(LocalDate d) {
            return cache.computeIfAbsent(d, key -> {
                int n = x.length;
                double[] w = new double[n];
                for (int i = 0; i < n; i++) {
                    double h = linear ? 1e-2 : 1e-4;
                    double c1 = central(key, i, h);
                    w[i] = linear ? c1 : (4.0 * central(key, i, h / 2.0) - c1) / 3.0;
                }
                return w;
            });
        }

        private double central(LocalDate d, int i, double h) {
            double[] up = x.clone();
            double[] dn = x.clone();
            up[i] += h;
            dn[i] -= h;
            double a = lnAt(up, d);
            double b = lnAt(dn, d);
            return a == b ? 0.0 : (a - b) / (2.0 * h);
        }

        /** cF dF/dx + cA dA/dx for the legs of an OIS. */
        double[] gradient(Ois.Legs l, double cF, double cA) {
            int n = x.length;
            double[] g = new double[n];
            List<Schedule.Period> ps = l.periods();
            for (int k = 0; k < ps.size(); k++) {
                Schedule.Period p = ps.get(k);
                double ds = curve.discount(p.start());
                double de = curve.discount(p.end());
                double dp = curve.discount(p.payment());
                add(g, p.start(), cF * dp / de * ds);
                add(g, p.end(), -cF * ds * dp / (de * de) * de);
                add(g, p.payment(), (cF * (ds / de - 1.0) + cA * l.alpha()[k]) * dp);
            }
            return g;
        }

        /** Adds {@code coef} times d ln D(d)/dx (coef already holds dV/dD times D). */
        private void add(double[] g, LocalDate d, double coef) {
            if (!d.isAfter(curve.asOf())) {
                return;
            }
            double[] w = at(d);
            for (int i = 0; i < g.length; i++) {
                if (w[i] != 0.0) {
                    g[i] += coef * w[i];
                }
            }
        }
    }

    /** Inverse; forward substitution when the matrix is exactly lower triangular, so zeros stay exact (F-30). */
    static double[][] inverse(double[][] a) {
        int n = a.length;
        boolean lower = true;
        for (int i = 0; i < n && lower; i++) {
            for (int j = i + 1; j < n; j++) {
                if (a[i][j] != 0.0) {
                    lower = false;
                    break;
                }
            }
        }
        double[][] m = new double[n][n];
        for (int col = 0; col < n; col++) {
            double[] e = new double[n];
            e[col] = 1.0;
            double[] v;
            if (lower) {
                v = new double[n];
                for (int i = 0; i < n; i++) {
                    if (i < col) {
                        continue;
                    }
                    double s = e[i];
                    for (int k = col; k < i; k++) {
                        s -= a[i][k] * v[k];
                    }
                    v[i] = s / a[i][i];
                }
            } else {
                v = LinearAlgebra.solve(a, e);
            }
            for (int i = 0; i < n; i++) {
                m[i][col] = v[i];
            }
        }
        return m;
    }

    // ---- PCA ----

    public record Pca(double[] eigenvalues, double[][] loadings, double[] explained) {}

    public static Pca pca(double[][] changes, long components) {
        int t = changes.length;
        if (t < 2) {
            throw new QfError("E_INPUT", "need at least 2 rows", "changes");
        }
        int n = changes[0].length;
        for (double[] r : changes) {
            Finite.check("changes", r);
            if (r.length != n) {
                throw new QfError("E_INPUT", "rows must have the same length", "changes");
            }
        }
        if (components < 1) {
            throw new QfError("E_DOMAIN", "components must be at least 1", "components");
        }
        if (components > n) {
            throw new QfError("E_INPUT", "components above the tenor count", "components");
        }
        int k = (int) components;
        double[] mean = new double[n];
        for (double[] r : changes) {
            for (int j = 0; j < n; j++) {
                mean[j] += r[j];
            }
        }
        for (int j = 0; j < n; j++) {
            mean[j] /= t;
        }
        double[][] cov = new double[n][n];
        for (double[] r : changes) {
            for (int i = 0; i < n; i++) {
                double di = r[i] - mean[i];
                for (int j = i; j < n; j++) {
                    cov[i][j] += di * (r[j] - mean[j]);
                }
            }
        }
        for (int i = 0; i < n; i++) {
            for (int j = i; j < n; j++) {
                cov[i][j] /= t - 1;
                cov[j][i] = cov[i][j];
            }
        }
        double[][] v = new double[n][n];
        double[] lambda = jacobi(cov, v);
        Integer[] order = new Integer[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
        }
        java.util.Arrays.sort(order, (a, b) -> Double.compare(lambda[b], lambda[a]));
        double[] ev = new double[n];
        double total = 0.0;
        for (int i = 0; i < n; i++) {
            ev[i] = lambda[order[i]];
            total += ev[i];
        }
        int check = k == n ? n : k + 1;
        for (int i = 1; i < check; i++) {
            if (ev[i - 1] - ev[i] < 1e-6 * ev[0]) {
                throw new QfError("E_DOMAIN", "repeated eigenvalue: loadings are not unique", "changes");
            }
        }
        double[][] load = new double[k][n];
        double[] ratio = new double[k];
        for (int c = 0; c < k; c++) {
            int col = order[c];
            int big = 0;
            for (int i = 0; i < n; i++) {
                load[c][i] = v[i][col];
                if (Math.abs(load[c][i]) > Math.abs(load[c][big])) {
                    big = i;
                }
            }
            if (load[c][big] < 0) {
                for (int i = 0; i < n; i++) {
                    load[c][i] = -load[c][i];
                }
            }
            ratio[c] = ev[c] / total;
        }
        return new Pca(ev, load, ratio);
    }

    /** Cyclic Jacobi: eigenvalues returned, eigenvectors in the columns of {@code v}. */
    private static double[] jacobi(double[][] input, double[][] v) {
        int n = input.length;
        double[][] a = new double[n][];
        for (int i = 0; i < n; i++) {
            a[i] = input[i].clone();
            java.util.Arrays.fill(v[i], 0.0);
            v[i][i] = 1.0;
        }
        for (int sweep = 0; sweep < 100; sweep++) {
            double off = 0.0;
            for (int p = 0; p < n; p++) {
                for (int q = p + 1; q < n; q++) {
                    off += a[p][q] * a[p][q];
                }
            }
            if (off == 0.0) {
                break;
            }
            for (int p = 0; p < n; p++) {
                for (int q = p + 1; q < n; q++) {
                    if (a[p][q] == 0.0) {
                        continue;
                    }
                    double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                    double tt = Math.signum(theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1.0));
                    if (theta == 0.0) {
                        tt = 1.0;
                    }
                    double cs = 1.0 / Math.sqrt(tt * tt + 1.0);
                    double sn = tt * cs;
                    for (int k = 0; k < n; k++) {
                        double akp = a[k][p];
                        double akq = a[k][q];
                        a[k][p] = cs * akp - sn * akq;
                        a[k][q] = sn * akp + cs * akq;
                    }
                    for (int k = 0; k < n; k++) {
                        double apk = a[p][k];
                        double aqk = a[q][k];
                        a[p][k] = cs * apk - sn * aqk;
                        a[q][k] = sn * apk + cs * aqk;
                    }
                    for (int k = 0; k < n; k++) {
                        double vkp = v[k][p];
                        double vkq = v[k][q];
                        v[k][p] = cs * vkp - sn * vkq;
                        v[k][q] = sn * vkp + cs * vkq;
                    }
                }
            }
        }
        double[] d = new double[n];
        for (int i = 0; i < n; i++) {
            d[i] = a[i][i];
        }
        return d;
    }

    // ---- cross gamma ----

    public record CrossGamma(double value, double[][] gamma) {}

    public static CrossGamma crossGamma(Curve curve, ToDoubleFunction<Curve> product, double bumpBp) {
        CurveRisk.checkBump(bumpBp);
        LocalDate[] dates = curve.dates();
        double[] df = curve.discountFactors();
        int n = dates.length;
        double h = bumpBp * 1e-4;
        double[] t = new double[n];
        for (int i = 0; i < n; i++) {
            t[i] = curve.time(dates[i]);
        }
        java.util.function.Function<double[], Double> value = shifts -> {
            double[] b = df.clone();
            for (int i = 0; i < n; i++) {
                if (shifts[i] != 0.0) {
                    b[i] *= Math.exp(-shifts[i] * t[i]);
                }
            }
            return product.applyAsDouble(Curve.of(curve.asOf(), curve.interpolation(), dates, b, curve.jumps(),
                    curve.shape()));
        };
        double v0 = product.applyAsDouble(curve);
        double[][] g = new double[n][n];
        for (int i = 0; i < n; i++) {
            double[] up = new double[n];
            double[] dn = new double[n];
            up[i] = h;
            dn[i] = -h;
            g[i][i] = (value.apply(up) - 2.0 * v0 + value.apply(dn)) / (bumpBp * bumpBp);
            for (int j = 0; j < i; j++) {
                double[] pp = new double[n];
                double[] pm = new double[n];
                double[] mp = new double[n];
                double[] mm = new double[n];
                pp[i] = h;
                pp[j] = h;
                pm[i] = h;
                pm[j] = -h;
                mp[i] = -h;
                mp[j] = h;
                mm[i] = -h;
                mm[j] = -h;
                double v = (value.apply(pp) - value.apply(pm) - value.apply(mp) + value.apply(mm))
                        / (4.0 * bumpBp * bumpBp);
                g[i][j] = v;
                g[j][i] = v;
            }
        }
        return new CrossGamma(v0, g);
    }

    /**
     * Cross gamma of an OIS on a curve where ln D is linear in the pillar logs (LOG_LINEAR_DF, LINEAR_ZERO): each
     * cash-flow term is {@code c exp(u . shifts)}, so the formula's differences are summed in closed form
     * ({@code e^u - 2 + e^-u = 4 sinh^2(u/2)}, the four-point form is {@code 4 sinh a sinh b}) without the
     * cancellation of revaluing a large notional. Other interpolations revalue.
     */
    public static CrossGamma crossGammaOis(Curve curve, Ois.Legs legs, double signedNotional, double fixedRate,
                                           ToDoubleFunction<Curve> product, double bumpBp) {
        Curve.Interpolation m = curve.interpolation();
        if ((m != Curve.Interpolation.LOG_LINEAR_DF && m != Curve.Interpolation.LINEAR_ZERO)
                || curve.jumps().dates().length > 0) {
            return crossGamma(curve, product, bumpBp);
        }
        CurveRisk.checkBump(bumpBp);
        LocalDate[] dates = curve.dates();
        int n = dates.length;
        double[] df = curve.discountFactors();
        double[] x = new double[n];
        double[] t = new double[n];
        for (int i = 0; i < n; i++) {
            x[i] = Math.log(df[i]);
            t[i] = curve.time(dates[i]);
        }
        Weights w = new Weights(curve, m, x);
        double h = bumpBp * 1e-4;
        List<double[]> expo = new ArrayList<>();
        List<Double> coef = new ArrayList<>();
        List<Schedule.Period> ps = legs.periods();
        for (int k = 0; k < ps.size(); k++) {
            Schedule.Period p = ps.get(k);
            double ds = curve.discount(p.start());
            double de = curve.discount(p.end());
            double dp = curve.discount(p.payment());
            double[] ws = weightsOrZero(w, curve, p.start(), n);
            double[] we = weightsOrZero(w, curve, p.end(), n);
            double[] wp = weightsOrZero(w, curve, p.payment(), n);
            double[] a1 = new double[n];
            for (int i = 0; i < n; i++) {
                a1[i] = ws[i] + wp[i] - we[i];
            }
            expo.add(a1);
            coef.add(signedNotional * ds * dp / de);
            expo.add(wp);
            coef.add(-signedNotional * (1.0 + fixedRate * legs.alpha()[k]) * dp);
        }
        double v0 = product.applyAsDouble(curve);
        double[][] g = new double[n][n];
        double b2 = bumpBp * bumpBp;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j <= i; j++) {
                double sum = 0.0;
                for (int q = 0; q < expo.size(); q++) {
                    double ui = -h * t[i] * expo.get(q)[i];
                    if (i == j) {
                        double sh = Math.sinh(ui / 2.0);
                        sum += coef.get(q) * 4.0 * sh * sh;
                    } else {
                        double uj = -h * t[j] * expo.get(q)[j];
                        sum += coef.get(q) * Math.sinh(ui) * Math.sinh(uj);
                    }
                }
                g[i][j] = sum / b2;
                g[j][i] = g[i][j];
            }
        }
        return new CrossGamma(v0, g);
    }

    private static double[] weightsOrZero(Weights w, Curve curve, LocalDate d, int n) {
        return d.isAfter(curve.asOf()) ? w.at(d) : new double[n];
    }

    // ---- jump to default ----

    public enum JtdKind { BOND, CDS_PROTECTION_BUYER, CDS_PROTECTION_SELLER }

    public record JtdPosition(String id, JtdKind kind, double notional, double recovery, double marketValue) {}

    public static double[] jtd(List<JtdPosition> positions) {
        if (positions.isEmpty()) {
            throw new QfError("E_INPUT", "no positions", "positions");
        }
        double[] out = new double[positions.size()];
        for (int i = 0; i < out.length; i++) {
            JtdPosition p = positions.get(i);
            Finite.check("notional", p.notional());
            Finite.check("recovery", p.recovery());
            Finite.check("market_value", p.marketValue());
            if (p.notional() < 0.0 || p.recovery() < 0.0 || p.recovery() > 1.0) {
                throw new QfError("E_DOMAIN", "need notional >= 0 and 0 <= recovery <= 1", "positions");
            }
            double after = switch (p.kind()) {
                case BOND -> p.recovery() * p.notional();
                case CDS_PROTECTION_BUYER -> (1.0 - p.recovery()) * p.notional();
                case CDS_PROTECTION_SELLER -> -(1.0 - p.recovery()) * p.notional();
            };
            out[i] = after - p.marketValue();
        }
        return out;
    }
}
