package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** K-9 review fixes: SABR chi(z) without cancellation (KR-340) and implied-vol acceptance (KR-341). */
class StageKRev1Test {
    @Test
    void chiSmallZKeepsItsDigits() {
        // chi = z (1 + rho z/2 + (rho^2/2 - 1/6) z^2 + O(z^3)), from the spec's series for z/chi; the direct form
        // misses by 2.7e-9 relative at z = 1.01e-7 (mpmath, 50 digits).
        double z = 1.01e-7;
        double rho = 0.3;
        double direct = Math.log((Math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho) / (1.0 - rho));
        double chi = Sabr.chi(z, rho);
        assertTrue(Math.abs(direct / chi - 1.0) > 1e-9);
        assertEquals(z * (1.0 + rho * z / 2.0 + (rho * rho / 2.0 - 1.0 / 6.0) * z * z), chi, 1e-15 * z);
    }

    @Test
    void chiBranchesAgreeWithTheDirectFormWhereItIsSafe() {
        for (double rho : new double[] {-0.9, 0.0, 0.6}) {
            for (double z : new double[] {-3.0, -0.8, 0.9, 4.0}) {
                double direct = Math.log((Math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho) / (1.0 - rho));
                assertEquals(direct, Sabr.chi(z, rho), 1e-14 * Math.abs(direct));
            }
        }
    }

    @Test
    void deepOutOfTheMoneyPriceGivesTheVol() {
        double price = Black.lognormal(1.0, 100.0, 300.0, 0.1, 1.0, 0.1);
        assertTrue(price < 1e-260);
        assertEquals(0.1, Black.solve(false, 1.0, 100.0, 300.0, 0.1, 1.0, price), 1e-10);
    }

    @Test
    void subnormalPriceIsNotIdentified() {
        QfError e = assertThrows(QfError.class,
                () -> Black.solve(true, -1.0, 100.0, 86.83731917681901, 2.9082679923151997, 1.0, 1.5826e-319));
        assertEquals("E_NO_CONVERGENCE", e.code());
    }
}
