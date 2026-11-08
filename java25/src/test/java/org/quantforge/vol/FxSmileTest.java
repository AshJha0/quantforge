package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.vol.FxSmile.DeltaType;

/** FX smile by properties: parity, round trips, delta-neutral straddles, the upper PA root (fx-smile.md). */
class FxSmileTest {
    private static final FxSmile.Market USDJPY = new FxSmile.Market(150.0, 5.0, 0.001, 0.045);
    private static final FxSmile.Market EURUSD = new FxSmile.Market(1.085, 0.5, 0.043, 0.025);

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void putCallParityAndGreeksByBumps() {
        double k = 1.1;
        double v = 0.09;
        FxSmile.Price c = FxSmile.price(EURUSD, k, v, 1.0, 1e6);
        FxSmile.Price p = FxSmile.price(EURUSD, k, v, -1.0, 1e6);
        double parity = 1e6 * (EURUSD.spot() * Math.exp(-0.025 * 0.5) - k * Math.exp(-0.043 * 0.5));
        assertEquals(parity, c.price() - p.price(), 1e-8);
        double h = 1e-5;
        FxSmile.Market up = new FxSmile.Market(EURUSD.spot() + h, 0.5, 0.043, 0.025);
        FxSmile.Market dn = new FxSmile.Market(EURUSD.spot() - h, 0.5, 0.043, 0.025);
        double bump = (FxSmile.price(up, k, v, 1.0, 1e6).price() - FxSmile.price(dn, k, v, 1.0, 1e6).price()) / (2 * h);
        assertEquals(c.delta(), bump, 1e-3);
        double vega = (FxSmile.price(EURUSD, k, v + 1e-6, 1.0, 1e6).price()
                - FxSmile.price(EURUSD, k, v - 1e-6, 1.0, 1e6).price()) / 2e-6;
        assertEquals(c.vega(), vega, 1e-3);
    }

    @Test
    void strikeFromDeltaRoundTripsForEveryType() {
        for (FxSmile.Market m : new FxSmile.Market[] {USDJPY, EURUSD}) {
            for (DeltaType t : DeltaType.values()) {
                for (double d : new double[] {0.1, 0.25, -0.1, -0.25, -0.45}) {
                    double phi = Math.signum(d);
                    double k = FxSmile.strike(m, d, 0.12, phi, t);
                    assertEquals(d, FxSmile.delta(m, k, 0.12, phi, t), 1e-13);
                }
            }
        }
    }

    @Test
    void premiumAdjustedCallTakesTheUpperRoot() {
        double v = 0.6; // high vol and long expiry make the maximum low enough to bracket two roots
        double kStar = FxSmile.maxDeltaStrike(USDJPY, v);
        double max = FxSmile.delta(USDJPY, kStar, v, 1.0, DeltaType.FORWARD_PA);
        assertTrue(max > FxSmile.delta(USDJPY, kStar * 0.99, v, 1.0, DeltaType.FORWARD_PA));
        assertTrue(max > FxSmile.delta(USDJPY, kStar * 1.01, v, 1.0, DeltaType.FORWARD_PA));
        double k = FxSmile.strike(USDJPY, 0.5 * max, v, 1.0, DeltaType.FORWARD_PA);
        assertTrue(k > kStar);
        assertEquals("E_DOMAIN", code(() -> FxSmile.strike(USDJPY, max * 1.0001, v, 1.0, DeltaType.FORWARD_PA)));
        assertEquals("E_DOMAIN", code(() -> FxSmile.strike(USDJPY, -0.1, v, 1.0, DeltaType.SPOT)));
        assertEquals("E_DOMAIN", code(() -> FxSmile.strike(USDJPY, 0.999, v, 1.0, DeltaType.SPOT)));
    }

    @Test
    void dnsStrikeIsDeltaNeutral() {
        double v = 0.15;
        for (DeltaType t : DeltaType.values()) {
            double k = FxSmile.atmStrike(USDJPY, v, FxSmile.AtmType.DNS, t);
            double sum = FxSmile.delta(USDJPY, k, v, 1.0, t) + FxSmile.delta(USDJPY, k, v, -1.0, t);
            assertEquals(0.0, sum, 1e-14);
        }
        assertEquals(150.0, FxSmile.atmStrike(USDJPY, v, FxSmile.AtmType.SPOT, DeltaType.SPOT), 0.0);
        assertEquals(USDJPY.forward(), FxSmile.atmStrike(USDJPY, v, FxSmile.AtmType.FORWARD, DeltaType.SPOT_PA), 0.0);
        assertEquals("E_DOMAIN", code(() -> FxSmile.checkMarket(USDJPY, 0.0)));
    }
}
