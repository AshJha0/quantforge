package org.quantforge.risk;

import java.util.Arrays;
import org.quantforge.core.QfError;

/**
 * The deterministic xVA layer on given paths (xva-framework.md, rulings G-40 to G-44): collateralised exposure,
 * valuation adjustments, sensitivity-based IR delta margin and Hull-White wrong-way CVA.
 */
public final class Xva {
    /** KR-257: the largest {@code |b V|} the wrong-way root accepts ({@code E_DOMAIN} above it). */
    public static final double WWR_MAX_BV = 700.0;

    private Xva() {}

    /**
     * CSA terms of one netting set.
     *
     * @param thresholdReceive threshold above which collateral is received
     * @param thresholdPost threshold above which collateral is posted
     * @param mta minimum transfer amount
     * @param mporSteps margin period of risk in grid steps
     * @param independentAmount independent amount
     */
    public record Csa(double thresholdReceive, double thresholdPost, double mta, int mporSteps,
                      double independentAmount) {}

    /**
     * Exposure profile of one netting set.
     *
     * @param ee expected exposure per time
     * @param ene expected negative exposure per time
     * @param pfe potential future exposure per time
     * @param epe time-averaged EE
     * @param effectiveEpe time-averaged effective EE over the first year
     */
    public record Profile(double[] ee, double[] ene, double[] pfe, double epe, double effectiveEpe) {}

    /**
     * Exposure profile of one netting set from its netted path values (G-40).
     *
     * @param times grid {@code t_0 < ... < t_n}
     * @param v netted values {@code [path][time]}
     * @param csa CSA terms, or null
     * @param q PFE quantile in (0, 1]
     * @return the profile
     */
    public static Profile profile(double[] times, double[][] v, Csa csa, double q) {
        int np = v.length;
        int nt = times.length;
        double[][] e = new double[nt][np];
        double[] ee = new double[nt];
        double[] ene = new double[nt];
        for (int p = 0; p < np; p++) {
            double[] k = new double[nt];
            for (int j = 0; j < nt; j++) {
                if (csa == null) {
                    break;
                }
                double target = Math.max(v[p][j] - csa.thresholdReceive(), 0.0)
                        - Math.max(-v[p][j] - csa.thresholdPost(), 0.0) + csa.independentAmount();
                k[j] = j == 0 || Math.abs(target - k[j - 1]) >= csa.mta() ? target : k[j - 1];
            }
            for (int i = 0; i < nt; i++) {
                double c = csa == null ? 0.0 : k[Math.max(i - csa.mporSteps(), 0)];
                double x = v[p][i] - c;
                e[i][p] = Math.max(x, 0.0);
                ee[i] += Math.max(x, 0.0);
                ene[i] += Math.min(x, 0.0);
            }
        }
        double[] pfe = new double[nt];
        int rank = (int) Math.ceil(q * np);
        for (int i = 0; i < nt; i++) {
            ee[i] /= np;
            ene[i] /= np;
            double[] s = e[i].clone();
            Arrays.sort(s);
            pfe[i] = s[Math.max(rank, 1) - 1];
        }
        double epe = 0.0;
        for (int i = 1; i < nt; i++) {
            epe += ee[i] * (times[i] - times[i - 1]);
        }
        epe /= times[nt - 1] - times[0];
        double eee = ee[0];
        double eff = 0.0;
        double end = times[0];
        for (int i = 1; i < nt && times[i] - times[0] <= 1.0; i++) {
            eee = Math.max(eee, ee[i]);
            eff += eee * (times[i] - times[i - 1]);
            end = times[i];
        }
        double effective = end > times[0] ? eff / (end - times[0]) : ee[0];
        return new Profile(ee, ene, pfe, epe, effective);
    }

    /**
     * Valuation adjustments on bucketed profiles (G-41).
     *
     * @param t bucket ends
     * @param df discount factors
     * @param ee expected exposure
     * @param ene expected negative exposure
     * @param hc counterparty hazard
     * @param rc counterparty recovery
     * @param hb own hazard
     * @param rb own recovery
     * @param sb borrow spread
     * @param sl lend spread
     * @param excludeOverlap remove the own-credit part of the lend spread
     * @param im initial margin profile, or null
     * @param imSpread IM funding spread
     * @param capital capital profile, or null
     * @param hurdle hurdle rate
     * @return {cva, dva, fca, fba, fva, mva, kva}
     */
    public static double[] adjustments(double[] t, double[] df, double[] ee, double[] ene, double hc, double rc,
                                       double hb, double rb, double sb, double sl, boolean excludeOverlap,
                                       double[] im, double imSpread, double[] capital, double hurdle) {
        double sLend = excludeOverlap ? Math.max(sl - hb * (1.0 - rb), 0.0) : sl;
        double cva = 0.0;
        double dva = 0.0;
        double fca = 0.0;
        double fba = 0.0;
        double mva = 0.0;
        double kva = 0.0;
        double prev = 0.0;
        for (int i = 0; i < t.length; i++) {
            double scP = Math.exp(-hc * prev);
            double sbP = Math.exp(-hb * prev);
            double dt = t[i] - prev;
            double qcI = scP * -Math.expm1(-hc * dt); // cancellation free (PT-6)
            double qbI = sbP * -Math.expm1(-hb * dt);
            double neg = Math.abs(ene[i]);
            cva += df[i] * ee[i] * qcI * sbP;
            dva += df[i] * neg * qbI * scP;
            double alive = scP * sbP * dt;
            fca += df[i] * ee[i] * alive;
            fba += df[i] * neg * alive;
            if (im != null) {
                mva += df[i] * im[i] * alive;
            }
            if (capital != null) {
                kva += df[i] * capital[i] * alive;
            }
            prev = t[i];
        }
        cva *= 1.0 - rc;
        dva *= 1.0 - rb;
        fca *= sb;
        fba *= sLend;
        return new double[] {cva, dva, fca, fba, fca - fba, imSpread * mva, hurdle * kva};
    }

    /**
     * Sensitivity-based IR delta margin, operation {@code xva.sbim.ir_delta} (G-43; the deprecated alias
     * {@code xva.simm.ir_delta} runs the same code, KR-152).
     *
     * @param s sensitivities
     * @param rw risk weights
     * @param rho correlations
     * @param threshold concentration threshold
     * @return {concentration factor, margin} with the weighted sensitivities written to {@code ws}
     * @param ws output weighted sensitivities
     */
    public static double[] sbimIrDelta(double[] s, double[] rw, double[][] rho, double threshold, double[] ws) {
        double sum = 0.0;
        for (double x : s) {
            sum += x;
        }
        double cr = Math.max(1.0, Math.sqrt(Math.abs(sum) / threshold));
        for (int k = 0; k < s.length; k++) {
            ws[k] = rw[k] * s[k] * cr;
        }
        double q = 0.0;
        for (int k = 0; k < s.length; k++) {
            for (int l = 0; l < s.length; l++) {
                q += (k == l ? 1.0 : rho[k][l]) * ws[k] * ws[l];
            }
        }
        return new double[] {cr, Math.sqrt(Math.max(0.0, q))};
    }

    /**
     * Hull-White wrong-way CVA (G-44): hazard {@code exp(a_i + b V_p(t_i))} in bucket i, with {@code a_i} fitted
     * so the path-average survival matches {@code exp(-h t_i)}.
     *
     * @param t bucket ends
     * @param v path values {@code [path][time]}
     * @param df discount factors
     * @param h hazard rate
     * @param r recovery
     * @param b wrong-way coefficient
     * @param a output, the fitted {@code a_i}
     * @return the CVA
     */
    public static double wwrCva(double[] t, double[][] v, double[] df, double h, double r, double b, double[] a) {
        for (double[] path : v) {
            for (double x : path) {
                if (Math.abs(b * x) > WWR_MAX_BV) {
                    throw new QfError("E_DOMAIN", "|wwr_b * value| must be at most 700 (KR-257)", "wwr_b");
                }
            }
        }
        double prev = 0.0;
        for (double ti : t) {
            if (Math.exp(-h * ti) < Double.MIN_NORMAL || -Math.expm1(-h * (ti - prev)) < Double.MIN_NORMAL) {
                throw new QfError("E_NON_FINITE",
                        "the survival target or a bucket default probability is below the smallest normal double",
                        "hazard_rate");
            }
            prev = ti;
        }
        int np = v.length;
        double[] surv = new double[np];
        Arrays.fill(surv, 1.0);
        double[] cs = new double[np];
        double cva = 0.0;
        prev = 0.0;
        for (int i = 0; i < t.length; i++) {
            double dt = t[i] - prev;
            for (int p = 0; p < np; p++) {
                cs[p] = b * v[p][i];
            }
            a[i] = wwrRoot(surv, cs, dt, h);
            double sum = 0.0;
            for (int p = 0; p < np; p++) {
                double[] w = wwrTerms(a[i] + cs[p], dt);
                sum += Math.max(v[p][i], 0.0) * surv[p] * w[0];
                surv[p] *= w[1];
            }
            cva += df[i] * sum / np;
            prev = t[i];
        }
        return (1.0 - r) * cva;
    }

    /**
     * KR-257: for hazard {@code exp(z)} over {@code dt}, the default probability {@code q = 1 - e^-x}, the survival
     * {@code r = e^-x} and {@code dq/dz = x e^-x}, with {@code x = exp(z) dt}; an overflowing {@code exp(z)} is
     * infinite (q = 1, r = 0).
     */
    static double[] wwrTerms(double z, double dt) {
        double x = (z > 709.0 ? Double.POSITIVE_INFINITY : Math.exp(z)) * dt;
        double r = Math.exp(-x);
        return new double[] {-Math.expm1(-x), r, r == 0.0 ? 0.0 : x * r};
    }

    /**
     * KR-257: {@code a} with {@code sum_p S_p (1 - e^(-x_p)) = (1 - e^(-h dt)) sum_p S_p}, {@code x_p = exp(a + c_p)
     * dt} (the G-44 equation divided through by {@code S(t_(i-1))}; above a bucket default probability of 1/2 the
     * survival form {@code sum_p S_p e^(-x_p) = e^(-h dt) sum_p S_p}). Bracket {@code [ln h - max c - 1, ln h - min c +
     * 1]} (closed form, sign change by monotonicity), safeguarded Newton (rtsafe) from {@code ln h - (S-weighted mean of
     * c)}, step to 1e-15 relative, at most 200 steps.
     */
    static double wwrRoot(double[] surv, double[] cs, double dt, double h) {
        double qT = -Math.expm1(-h * dt);
        double rT = Math.exp(-h * dt);
        boolean useQ = qT <= 0.5;
        double total = 0.0;
        double wsum = 0.0;
        double cMax = Double.NEGATIVE_INFINITY;
        double cMin = Double.POSITIVE_INFINITY;
        for (int p = 0; p < surv.length; p++) {
            total += surv[p];
            wsum += surv[p] * cs[p];
            cMax = Math.max(cMax, cs[p]);
            cMin = Math.min(cMin, cs[p]);
        }
        double lnH = Math.log(h);
        double lo = lnH - cMax - 1.0;
        double hi = lnH - cMin + 1.0;
        double x = lnH - wsum / total;
        double dx = hi - lo;
        double[] fd = wwrValue(surv, cs, dt, useQ, qT, rT, total, x);
        for (int it = 0; it < 200; it++) {
            if (fd[0] > 0) {
                hi = x;
            } else if (fd[0] < 0) {
                lo = x;
            } else {
                return x;
            }
            double dxOld = dx;
            dx = fd[1] > 0 ? fd[0] / fd[1] : Double.POSITIVE_INFINITY;
            double step = x - dx;
            if (!(lo < step && step < hi && Math.abs(dx) <= 0.5 * Math.abs(dxOld))) {
                dx = 0.5 * (hi - lo);
                step = lo + dx;
            }
            if (Math.abs(step - x) <= 1e-15 * Math.max(1.0, Math.abs(x))) {
                return step;
            }
            x = step;
            fd = wwrValue(surv, cs, dt, useQ, qT, rT, total, x);
        }
        throw new QfError("E_NO_CONVERGENCE", "the a(t) root did not converge in 200 steps", "wwr_b");
    }

    /** KR-257: the bracketed function (increasing in {@code x}) and its derivative. */
    private static double[] wwrValue(double[] surv, double[] cs, double dt, boolean useQ, double qT, double rT,
            double total, double x) {
        double sq = 0.0;
        double sr = 0.0;
        double d = 0.0;
        for (int p = 0; p < surv.length; p++) {
            double[] w = wwrTerms(x + cs[p], dt);
            sq += surv[p] * w[0];
            sr += surv[p] * w[1];
            d += surv[p] * w[2];
        }
        return new double[] {useQ ? sq - qT * total : rT * total - sr, d};
    }

    /** Validation helper: a non-empty, strictly increasing grid. */
    static boolean increasing(double[] x) {
        for (int i = 1; i < x.length; i++) {
            if (!(x[i] > x[i - 1])) {
                return false;
            }
        }
        return true;
    }

    /**
     * Rejects an empty or non-increasing grid with E_INPUT.
     *
     * @param key the input name
     * @param x the grid
     * @param min the minimum length
     */
    public static void checkGrid(String key, double[] x, int min) {
        if (x.length < min || !increasing(x)) {
            throw new QfError("E_INPUT", key + " must be strictly increasing", key);
        }
    }
}
