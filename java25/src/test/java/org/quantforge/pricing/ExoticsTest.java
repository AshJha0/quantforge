package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** E5 by identities: in + out = vanilla, digital decomposition, limits and convergence (exotics.md). */
class ExoticsTest {
    private static final double S = 100;
    private static final double T = 0.75;
    private static final double R = 0.04;
    private static final double Q = 0.01;
    private static final double V = 0.25;

    private static double bs(double phi, double k) {
        return Exotics.gbs(phi, S, k, T, R, R - Q, V);
    }

    @Test
    void barrierInPlusOutIsVanilla() {
        for (double phi : new double[] {1, -1}) {
            for (double k : new double[] {90, 110}) {
                double down = Exotics.barrier(phi, Exotics.BarrierType.DOWN_IN, S, k, T, R, Q, V, 95, 0)
                        + Exotics.barrier(phi, Exotics.BarrierType.DOWN_OUT, S, k, T, R, Q, V, 95, 0);
                double up = Exotics.barrier(phi, Exotics.BarrierType.UP_IN, S, k, T, R, Q, V, 105, 0)
                        + Exotics.barrier(phi, Exotics.BarrierType.UP_OUT, S, k, T, R, Q, V, 105, 0);
                assertEquals(bs(phi, k), down, 1e-12);
                assertEquals(bs(phi, k), up, 1e-12);
            }
        }
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> Exotics.barrier(1, Exotics.BarrierType.DOWN_OUT, S, 100, T, R, Q, V, 100, 0)).code());
    }

    @Test
    void digitalsRebuildTheVanillaAndLimitsHold() {
        double k = 105;
        double call = Exotics.digital(1, false, S, k, T, R, Q, V, 1) - k * Exotics.digital(1, true, S, k, T, R, Q, V, 1);
        assertEquals(bs(1, k), call, 1e-12);
        // one discrete fixing at T is the vanilla
        assertEquals(bs(1, k), Exotics.asianDiscrete(1, S, k, T, R, Q, V, new double[] {T}), 1e-12);
        // chooser is worth at least the call and the put; at choose time T it is a straddle
        double ch = Exotics.chooser(S, k, T, R, Q, V, 0.3);
        assertTrue(ch > bs(1, k) && ch > bs(-1, k));
        assertEquals(bs(1, k) + bs(-1, k), Exotics.chooser(S, k, T, R, Q, V, T), 1e-12);
        // Kirk at K = 0 is Margrabe: symmetric under swapping the assets with the put-call relation
        double m = Exotics.kirk(100, 95, 0, T, R, 0.3, 0.2, 0.5);
        double swap = Exotics.kirk(95, 100, 0, T, R, 0.2, 0.3, 0.5);
        assertEquals(Math.exp(-R * T) * 5, m - swap, 1e-12);
        // quanto with zero correlation is plain GBS at carry rf - q
        assertEquals(Exotics.gbs(1, S, k, T, R, 0.02 - Q, V), Exotics.quanto(1, S, k, T, R, 0.02, Q, V, 0.1, 0), 0.0);
        // one-asset basket is Black on its forward
        double[] b = Exotics.basket(1, new double[] {S}, new double[] {1}, new double[] {V}, new double[][] {{1}},
                k, T, R);
        assertEquals(V, b[2], 1e-12);
        // lookback call is worth more than an at-the-money vanilla
        assertTrue(Exotics.lookback(1, S, S, T, R, Q, V) > bs(1, S));
    }

    @Test
    void americanMethodsAgree() {
        double[] tree = Exotics.crr(-1, S, 100, T, R, Q, V, 2000);
        double fd = Exotics.fd(-1, true, S, 100, T, R, Q, V, 801, 800, 5)[0];
        double baw = Exotics.baw(-1, S, 100, T, R, Q, V);
        assertEquals(tree[0], fd, 2e-2);
        assertEquals(tree[0], baw, 5e-2);
        assertEquals(bs(-1, 100), tree[1], 2e-3);
        assertTrue(tree[0] > tree[1]);
        double euro = Exotics.fd(-1, false, S, 100, T, R, Q, V, 801, 800, 5)[0];
        assertEquals(bs(-1, 100), euro, 2e-2);
        // a call with no dividend is never exercised early
        assertEquals(bs(1, 100) * 0 + Exotics.gbs(1, S, 100, T, R, R, V), Exotics.baw(1, S, 100, T, R, 0, V), 0.0);
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Exotics.baw(1, S, 100, T, 0.0, Q, V)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Exotics.baw(-1, S, 100, T, -0.01, Q, V)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Exotics.crr(1, S, 100, 1, 0.5, 0, 0.01, 1)).code());
    }
}
