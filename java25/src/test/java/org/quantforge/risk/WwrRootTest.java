package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/**
 * KR-257 (proposed 2026-11-20): the wrong-way-risk root a(t) of {@code xva.wwr.cva_hw}. The old Newton iteration from
 * ln h diverged for large |b V| (h = 0.01, b = 1, V = 10 on every path: exact a = -14.605, cva = 0.11347). Identical V
 * on every path has the closed form a_i = ln h - b V_i and cva = (1 - R) sum D_i max(V_i, 0) (e^(-h t_(i-1)) -
 * e^(-h t_i)); the mixed-path values are the 50-digit oracle values of {@code wwr_g}.
 */
class WwrRootTest {
    private static final double[][] MIXED = {{30, 25, 40}, {-20, 5, -35}, {10, 40, 0}, {2, -8, 15}};
    private static final double[] MT = {0.5, 1.0, 2.0};
    private static final double[] MD = {0.99, 0.98, 0.955};

    private static boolean close(double got, double want) {
        return Math.abs(got - want) <= 1e-9 + 1e-12 * Math.abs(want);
    }

    @Test
    void identicalPathsMatchTheClosedFormForLargeBv() {
        for (double bv : new double[] {-700, -60, -10, 10, 20, 60, 700}) {
            double[] a = new double[2];
            double cva = Xva.wwrCva(new double[] {1, 2}, new double[][] {{bv, bv}, {bv, bv}}, new double[] {0.97, 0.94},
                    0.01, 0.4, 1.0, a);
            double exact = Math.log(0.01) - bv;
            for (double x : a) {
                assertTrue(Math.abs(x - exact) <= 1e-14 * Math.max(1.0, Math.abs(exact)), bv + ": " + x);
            }
            double want = 0.6 * Math.max(bv, 0.0)
                    * (0.97 * -Math.expm1(-0.01) + 0.94 * (Math.exp(-0.01) - Math.exp(-0.02)));
            assertTrue(Math.abs(cva - want) <= 1e-13 * want, bv + ": " + cva);
        }
    }

    @Test
    void oracleValuesForMixedPathsAndHazards() {
        double[] a = new double[3];
        assertTrue(close(Xva.wwrCva(MT, MIXED, MD, 0.02, 0.4, 1.0, a), 0.853870876724446));
        assertTrue(close(a[1], -42.520691113242584));
        assertTrue(close(Xva.wwrCva(MT, MIXED, MD, 2.0, 0.4, 0.1, a), 7.864264489887716));
        assertTrue(close(a[2], 3.6961779146431604));
        assertTrue(close(Xva.wwrCva(MT, MIXED, MD, 1e-10, 0.4, 0.3, a), 4.351665120150955e-09));
        assertTrue(close(a[0], -30.6422568451193));
        double[] one = new double[1];
        assertTrue(close(Xva.wwrCva(new double[] {1}, new double[][] {{5}, {-5}, {1}}, new double[] {0.97}, 40, 0.4, 0.2,
                one), 1.164));
        assertTrue(close(one[0], 4.661029923801264));
        Xva.wwrCva(new double[] {1}, new double[][] {{10}, {10}}, new double[] {0.97}, 1e-50, 0.4, 70, one);
        assertTrue(close(one[0], -815.1292546497023));
    }

    @Test
    void limitAndNonFiniteErrorsNameTheirFields() {
        double[] t = {1};
        double[] d = {0.97};
        double[] one = new double[1];
        QfError e = assertThrows(QfError.class, () -> Xva.wwrCva(t, new double[][] {{1}, {-10}}, d, 0.01, 0.4, 70.01, one));
        assertEquals("E_DOMAIN", e.code());
        assertEquals("wwr_b", e.field());
        e = assertThrows(QfError.class, () -> Xva.wwrCva(t, new double[][] {{1}}, d, 709, 0.4, 0, one));
        assertEquals("E_NON_FINITE", e.code());
        assertEquals("hazard_rate", e.field());
        e = assertThrows(QfError.class, () -> Xva.wwrCva(t, new double[][] {{1}}, d, 2e-308, 0.4, 0, one));
        assertEquals("E_NON_FINITE", e.code());
        double cva = Xva.wwrCva(t, new double[][] {{10}, {-10}}, d, 708, 0.4, 70, one);
        assertTrue(Math.abs(cva - 0.6 * 0.97 * 5.0) <= 1e-12 * cva, "edge " + cva);
    }
}
