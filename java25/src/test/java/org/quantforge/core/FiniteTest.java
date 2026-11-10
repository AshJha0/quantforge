package org.quantforge.core;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.quantforge.vol.Black;

/** Rule E1 edge values: NaN, both infinities, the largest finite values and both zeros. */
class FiniteTest {
    private static void rejects(double v) {
        QfError e = assertThrows(QfError.class, () -> Finite.check("x", v));
        assertEquals("E_DOMAIN", e.code());
    }

    @Test
    void scalars() {
        rejects(Double.NaN);
        rejects(Double.POSITIVE_INFINITY);
        rejects(Double.NEGATIVE_INFINITY);
        for (double ok : new double[] {0.0, -0.0, Double.MAX_VALUE, -Double.MAX_VALUE, Double.MIN_VALUE, Double.MIN_NORMAL}) {
            assertDoesNotThrow(() -> Finite.check("x", ok));
        }
    }

    @Test
    void arrays() {
        assertDoesNotThrow(() -> Finite.check("x", (double[]) null));
        assertDoesNotThrow(() -> Finite.check("x", new double[0]));
        assertThrows(QfError.class, () -> Finite.check("x", new double[] {1.0, Double.NaN}));
        assertThrows(QfError.class, () -> Finite.check("x", new double[][] {{1.0}, {Double.NEGATIVE_INFINITY}}));
        assertDoesNotThrow(() -> Finite.check("x", new double[][] {{1.0}, {-0.0}}));
    }

    @Test
    void libraryEntryPoints() {
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> Compounding.discountFactor(Double.NaN, 1.0, new Compounding.Basis(Compounding.Kind.CONTINUOUS, 0))).code());
        Black.Option o = new Black.Option(Black.Model.BLACK_76, 1.0, 100.0, 1.0, 100.0, 0.0, 0.0, 1.0, 0.0);
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Black.price(o, Double.NaN)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Black.implied(o, Double.POSITIVE_INFINITY)).code());
        // negative zero is the same input as zero (ruling F-3)
        assertEquals(Compounding.discountFactor(0.0, 1.0, new Compounding.Basis(Compounding.Kind.SIMPLE, 0)),
                Compounding.discountFactor(-0.0, 1.0, new Compounding.Basis(Compounding.Kind.SIMPLE, 0)));
    }
}
