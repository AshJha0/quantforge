package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.Rng;

/** lmm.md properties: cap-floor parity, payer-receiver parity, the flat limit, and the wave 3c simulation. */
class LmmTest {
    private static final ShortRate.Curve CURVE = new ShortRate.Curve(
            new double[] {0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                10.005479452054795},
            new double[] {0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787});
    private static final Lmm.Abcd HUMP = new Lmm.Abcd(-0.06, 0.17, 0.54, 0.17);

    @Test
    void capMinusFloorIsTheSwap() {
        double[] t = {0.5, 1.0, 1.5, 2.0, 2.5, 3.0};
        double k = 0.03;
        double cap = Lmm.capFloor(CURVE, HUMP, t, k, true, 1e6).price();
        double floor = Lmm.capFloor(CURVE, HUMP, t, k, false, 1e6).price();
        double swap = 0.0;
        for (int i = 1; i < t.length; i++) {
            swap += CURVE.df(t[i - 1]) - (1.0 + k * (t[i] - t[i - 1])) * CURVE.df(t[i]);
        }
        assertEquals(1e6 * swap, cap - floor, 1e-6);
    }

    @Test
    void payerMinusReceiverAndFlatLimit() {
        double[] pay = {2.0, 3.0, 4.0, 5.0, 6.0};
        Lmm.Swaption p = Lmm.rebonato(CURVE, HUMP, 0.1, 1.0, pay, 0.035, true, 1e6);
        Lmm.Swaption r = Lmm.rebonato(CURVE, HUMP, 0.1, 1.0, pay, 0.035, false, 1e6);
        assertEquals(1e6 * p.annuity() * (p.swapRate() - 0.035), p.price() - r.price(), 1e-6);
        Lmm.Abcd flat = new Lmm.Abcd(0.0, 0.0, 0.5, 0.2);
        assertEquals(0.2, Lmm.rebonato(CURVE, flat, 0.0, 1.0, pay, 0.035, true, 1.0).blackVol(), 1e-14);
        for (double v : Lmm.capFloor(CURVE, flat, new double[] {0.5, 1.0, 2.0}, 0.03, true, 1.0).vols()) {
            assertEquals(0.2, v, 1e-14);
        }
    }

    /**
     * Wave 3c acceptance (ruling G-26) with this build's own stream: terminal measure at 7 years, log-Euler with a
     * predictor-corrector drift, sigma at the step midpoint, beta 0.1, K 4.5%, 100,000 paths, 20 steps a year.
     * Every caplet (fixings 1 to 6) must lie within 3 standard errors of the closed form.
     */
    @Test
    void simulatedCapletsMatchClosedForm() {
        int nf = 6;
        double beta = 0.1;
        double k = 0.045;
        int paths = 100_000;
        int perYear = 20;
        double[][] chol = new double[nf][nf];
        for (int i = 0; i < nf; i++) {
            for (int j = 0; j <= i; j++) {
                double s = Math.exp(-beta * Math.abs(i - j));
                for (int m = 0; m < j; m++) {
                    s -= chol[i][m] * chol[j][m];
                }
                chol[i][j] = i == j ? Math.sqrt(s) : s / chol[j][j];
            }
        }
        double[] f0 = new double[nf];
        for (int i = 0; i < nf; i++) {
            f0[i] = CURVE.df(i + 1.0) / CURVE.df(i + 2.0) - 1.0;
        }
        Rng rng = Rng.seeded(20261111L, 0);
        double dt = 1.0 / perYear;
        double[] sum = new double[nf];
        double[] sumSq = new double[nf];
        double[] lnF = new double[nf];
        double[][] atInt = new double[nf + 2][nf];
        double[] z = new double[nf];
        double[] w = new double[nf];
        double[] sig = new double[nf];
        double[] mu0 = new double[nf];
        double[] pred = new double[nf];
        double[] mu1 = new double[nf];
        for (int p = 0; p < paths; p++) {
            for (int i = 0; i < nf; i++) {
                lnF[i] = Math.log(f0[i]);
            }
            for (int step = 0; step < nf * perYear; step++) {
                double t = step * dt;
                for (int i = 0; i < nf; i++) {
                    z[i] = rng.nextNormal();
                }
                for (int i = 0; i < nf; i++) {
                    double s = 0.0;
                    for (int m = 0; m <= i; m++) {
                        s += chol[i][m] * z[m];
                    }
                    w[i] = s;
                    sig[i] = i + 1.0 > t ? HUMP.at(i + 1.0, t + dt / 2.0) : 0.0;
                }
                drift(lnF, sig, beta, mu0);
                for (int i = 0; i < nf; i++) {
                    pred[i] = lnF[i] + (mu0[i] - sig[i] * sig[i] / 2.0) * dt + sig[i] * Math.sqrt(dt) * w[i];
                }
                drift(pred, sig, beta, mu1);
                for (int i = 0; i < nf; i++) {
                    if (sig[i] > 0.0) {
                        lnF[i] += (0.5 * (mu0[i] + mu1[i]) - sig[i] * sig[i] / 2.0) * dt
                                + sig[i] * Math.sqrt(dt) * w[i];
                    }
                }
                if ((step + 1) % perYear == 0) {
                    int year = (step + 1) / perYear;
                    for (int i = 0; i < nf; i++) {
                        atInt[year][i] = Math.exp(lnF[i]);
                    }
                }
            }
            for (int kk = 0; kk < nf; kk++) {
                double fix = atInt[kk + 1][kk];
                double v = Math.max(fix - k, 0.0);
                for (int j = kk + 1; j < nf; j++) {
                    v *= 1.0 + atInt[kk + 2][j];
                }
                sum[kk] += v;
                sumSq[kk] += v * v;
            }
        }
        double pn = CURVE.df(7.0);
        double[] t = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0};
        double[] closed = Lmm.capFloor(CURVE, HUMP, java.util.Arrays.copyOfRange(t, 1, 8), k, true, 1.0).caplets();
        for (int kk = 0; kk < nf; kk++) {
            double mean = sum[kk] / paths;
            double se = Math.sqrt((sumSq[kk] / paths - mean * mean) / (paths - 1));
            double zScore = (pn * mean - closed[kk]) / (pn * se);
            assertTrue(Math.abs(zScore) < 3.0, "caplet " + (kk + 1) + " z = " + zScore);
        }
    }

    /** Terminal-measure drift of each live forward (annual accruals). */
    private static void drift(double[] lnF, double[] sig, double beta, double[] out) {
        int nf = lnF.length;
        for (int i = 0; i < nf; i++) {
            double s = 0.0;
            for (int j = i + 1; j < nf; j++) {
                double fj = Math.exp(lnF[j]);
                s += Math.exp(-beta * (j - i)) * sig[j] * fj / (1.0 + fj);
            }
            out[i] = -sig[i] * s;
        }
    }
}
