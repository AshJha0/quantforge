package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** E6 against Higham's published example, reconstruction and the spec's hand cases (correlation.md). */
class CorrelationTest {
    private static final double[][] HIGHAM = {{1, 1, 0}, {1, 1, 1}, {0, 1, 1}};

    @Test
    void highamExample() {
        Correlation.Validation v = Correlation.validate(HIGHAM);
        assertEquals(1 - Math.sqrt(2), v.minEigenvalue(), 1e-14);
        assertFalse(v.psd());
        assertTrue(v.symmetric() && v.unitDiagonal() && v.inRange());
        Correlation.Nearest n = Correlation.nearest(HIGHAM);
        assertEquals(0.760690, n.matrix()[0][1], 1e-6);
        assertEquals(0.157298, n.matrix()[0][2], 1e-6);
        assertEquals(1.0, n.matrix()[1][1], 0.0);
        assertTrue(Correlation.validate(n.matrix()).minEigenvalue() > -1e-12);
        // an off-unit 2 by 2 with |rho| above 1 repairs to all ones (ruling E-B29)
        Correlation.Nearest ones = Correlation.nearest(new double[][] {{1, 1.3}, {1.3, 1}});
        assertEquals(1.0, ones.matrix()[0][1], 1e-12);
    }

    @Test
    void validInputComesBackUnchanged() {
        double[][] m = {{1, 0.3, -0.2}, {0.3, 1, 0.1}, {-0.2, 0.1, 1}};
        Correlation.Nearest n = Correlation.nearest(m);
        assertEquals(0.0, n.distance(), 1e-14);
        assertTrue(Correlation.validate(m).valid());
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> Correlation.nearest(new double[][] {{1, 0.3}, {0.2, 1}})).code());
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> Correlation.validate(new double[0][])).code());
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> Correlation.validate(new double[][] {{1, 0}})).code());
    }

    @Test
    void eigenReconstructs() {
        double[][] a = {{4, 1, -2}, {1, 3, 0.5}, {-2, 0.5, 5}};
        Correlation.Eigen e = Correlation.eigen(a);
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                double s = 0.0;
                for (int k = 0; k < 3; k++) {
                    s += e.vectors()[i][k] * e.values()[k] * e.vectors()[j][k];
                }
                assertEquals(a[i][j], s, 1e-13);
            }
        }
    }

    @Test
    void impliedAndDispersionHandCases() {
        assertEquals(0.53, Correlation.implied(new double[] {0.5, 0.5}, new double[] {0.2, 0.3}, 0.22), 1e-14);
        // three names: the closed form against the explicit pair sum
        double[] w = {0.2, 0.3, 0.5};
        double[] s = {0.25, 0.3, 0.2};
        double pairs = 0.0;
        double own = 0.0;
        for (int i = 0; i < 3; i++) {
            own += w[i] * w[i] * s[i] * s[i];
            for (int j = 0; j < 3; j++) {
                pairs += i == j ? 0.0 : w[i] * w[j] * s[i] * s[j];
            }
        }
        assertEquals((0.04 - own) / pairs, Correlation.implied(w, s, 0.2), 1e-14);
        assertThrows(QfError.class, () -> Correlation.checkNames(1, 1));
        assertThrows(QfError.class, () -> Correlation.checkNames(2, 3));
        assertThrows(QfError.class, () -> Correlation.checkPositive("vols", 0.2, 0.0));
        // ruling E-B33: a zero weight drops its name; negative or fewer than two positive is E_DOMAIN
        assertEquals(0.53, Correlation.implied(new double[] {0.5, 0.0, 0.5}, new double[] {0.2, 0.9, 0.3}, 0.22), 1e-14);
        Correlation.checkWeights(new double[] {0.5, 0.0, 0.5});
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> Correlation.checkWeights(new double[] {1.0, 0.0})).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> Correlation.checkWeights(new double[] {0.6, 0.6, -0.2})).code());
    }
}
