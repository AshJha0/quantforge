package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/** E8 by identities: option parity, closed-form CDF values, tranche additivity (credit-options-and-copulas.md). */
class CreditOptionsTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final LocalDate EXPIRY = LocalDate.of(2027, 3, 20);
    private static final LocalDate MAT = LocalDate.of(2032, 3, 20);

    @Test
    void payerMinusReceiverIsTheForwardAndImpliedVolRoundTrips() {
        CreditOptions.OptionPrice p = CreditOptions.price(AS_OF, EXPIRY, MAT, 0.035, 0.02, 0.4, true, 0.012, 1e7,
                0.5, true);
        CreditOptions.OptionPrice r = CreditOptions.price(AS_OF, EXPIRY, MAT, 0.035, 0.02, 0.4, false, 0.012, 1e7,
                0.5, true);
        assertEquals(1e7 * p.annuity() * (p.forward() - 0.012), p.price() - r.price(), 1e-6);
        CreditOptions.OptionPrice fep = CreditOptions.price(AS_OF, EXPIRY, MAT, 0.035, 0.02, 0.4, true, 0.012, 1e7,
                0.5, false);
        assertEquals(p.price() + p.frontEnd(), fep.price(), 1e-9);
        double v = CreditOptions.impliedVol(AS_OF, EXPIRY, MAT, 0.035, 0.02, 0.4, true, 0.012, 1e7, p.price());
        assertEquals(0.5, v, 1e-12);
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> CreditOptions.checkOption(AS_OF, AS_OF, MAT, 0.02, 0.4, 0.01)).code());
    }

    @Test
    void bivariateNormalAndStudentKnownValues() {
        for (double rho : new double[] {-0.8, -0.3, 0.3, 0.9}) {
            assertEquals(0.25 + Math.asin(rho) / (2 * Math.PI), CreditOptions.bivariateNormal(0, 0, rho), 1e-14);
            // the t copula has the same orthant probability at 0
            assertEquals(0.25 + Math.asin(rho) / (2 * Math.PI), CreditOptions.bivariateStudent(0, 0, rho, 4), 1e-12);
        }
        assertEquals(Normal.cdf(1.3), CreditOptions.studentCdf(1.3, 1e7), 1e-7);
        // nu = 1 is Cauchy: F(x) = 1/2 + atan(x)/pi
        assertEquals(0.5 + Math.atan(2.0) / Math.PI, CreditOptions.studentCdf(2.0, 1.0), 1e-10);
        assertEquals(1.7, CreditOptions.studentInverse(CreditOptions.studentCdf(1.7, 4), 4), 1e-10);
        double[] g = CreditOptions.jointDefault(CreditOptions.Copula.GAUSSIAN, 0.02, 0.03, 0.0, 0.0);
        assertEquals(0.0006, g[0], 1e-15);
        double[] t = CreditOptions.jointDefault(CreditOptions.Copula.STUDENT_T, 0.02, 0.03, 0.0, 5);
        assertTrue(t[0] > g[0]); // tail dependence at zero correlation
    }

    @Test
    void tranchesAddUpToThePoolLoss() {
        double[] pts = {0, 0.03, 0.07, 0.1, 0.15, 0.3, 1.0};
        double sum = 0.0;
        for (int i = 1; i < pts.length; i++) {
            sum += (pts[i] - pts[i - 1]) * CreditOptions.trancheLoss(0.05, 0.3, 0.4, pts[i - 1], pts[i]);
        }
        assertEquals(0.6 * 0.05, sum, 1e-15);
        assertTrue(CreditOptions.lossCdf(0.05, 0.3, 0.4, 0.01) < CreditOptions.lossCdf(0.05, 0.3, 0.4, 0.05));
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> CreditOptions.checkPool(0.05, 1.0, 0.4)).code());
    }
}
