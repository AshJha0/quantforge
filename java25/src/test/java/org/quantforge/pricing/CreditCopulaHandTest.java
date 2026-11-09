package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** Stage E quality pass: copula and tranche values checked by hand. */
class CreditCopulaHandTest {
    @Test
    void bivariateNormalAtZeroThresholdsMatchesTheArcsineFormula() {
        double rho = 0.5;
        assertEquals(0.25 + Math.asin(rho) / (2 * Math.PI), CreditOptions.bivariateNormal(0, 0, rho), 1e-10);
    }

    @Test
    void studentCdfIsSymmetricAboutZero() {
        for (double x : new double[] {0.3, 1.2, 4.0}) {
            assertEquals(1.0, CreditOptions.studentCdf(x, 5) + CreditOptions.studentCdf(-x, 5), 1e-12);
        }
        assertEquals(0.5, CreditOptions.studentCdf(0, 5), 1e-15);
    }

    @Test
    void theWholeCapitalStructureLosesTheExpectedLoss() {
        // Tranche [0, 1] carries every loss: (1 - R) p = 0.6 * 0.05.
        assertEquals(0.03, CreditOptions.trancheLoss(0.05, 0.3, 0.4, 0.0, 1.0), 1e-12);
    }

    @Test
    void seniorTranchesLoseLessThanJuniorOnes() {
        double equity = CreditOptions.trancheLoss(0.05, 0.3, 0.4, 0.0, 0.03);
        double mezz = CreditOptions.trancheLoss(0.05, 0.3, 0.4, 0.03, 0.07);
        double senior = CreditOptions.trancheLoss(0.05, 0.3, 0.4, 0.15, 0.3);
        assertTrue(equity > mezz && mezz > senior && senior >= 0);
    }

    @Test
    void lossCdfRisesWithTheLossLevel() {
        double previous = 0;
        for (double x : new double[] {0.001, 0.01, 0.05, 0.2, 0.59}) {
            double c = CreditOptions.lossCdf(0.05, 0.3, 0.4, x);
            assertTrue(c >= previous - 1e-12 && c <= 1.0);
            previous = c;
        }
    }
}
