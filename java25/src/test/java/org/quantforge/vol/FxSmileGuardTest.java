package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.QfError;

/** Library-level guards, greeks and delta-strike round trips of FxSmile. */
class FxSmileGuardTest {
    static final double NAN = Double.NaN;
    static final FxSmile.Market M = new FxSmile.Market(1.1, 0.75, 0.04, 0.02);

    static void fails(String code, String field, Executable e) {
        QfError x = assertThrows(QfError.class, e);
        assertEquals(code, x.code());
        assertEquals(field, x.field());
    }

    @Test
    void guards() {
        fails("E_DOMAIN", "vol", () -> FxSmile.checkMarket(M, NAN));
        fails("E_DOMAIN", null, () -> FxSmile.checkMarket(M, 0.0));
        fails("E_DOMAIN", null, () -> FxSmile.checkMarket(new FxSmile.Market(0.0, 1.0, 0, 0), 0.1));
        fails("E_DOMAIN", null, () -> FxSmile.checkMarket(new FxSmile.Market(1.0, 0.0, 0, 0), 0.1));
        FxSmile.checkMarket(M, Double.MIN_VALUE);
        fails("E_DOMAIN", "k", () -> FxSmile.price(M, NAN, 0.1, 1, 1e6));
        fails("E_DOMAIN", "v", () -> FxSmile.price(M, 1.1, NAN, 1, 1e6));
        fails("E_DOMAIN", "phi", () -> FxSmile.price(M, 1.1, 0.1, NAN, 1e6));
        fails("E_DOMAIN", "notional", () -> FxSmile.price(M, 1.1, 0.1, 1, NAN));
        fails("E_DOMAIN", "k", () -> FxSmile.delta(M, NAN, 0.1, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "v", () -> FxSmile.delta(M, 1.1, NAN, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "phi", () -> FxSmile.delta(M, 1.1, 0.1, NAN, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "delta", () -> FxSmile.strike(M, NAN, 0.1, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "v", () -> FxSmile.strike(M, 0.25, NAN, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "phi", () -> FxSmile.strike(M, 0.25, 0.1, NAN, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "delta", () -> FxSmile.strike(M, 0.0, 0.1, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "delta", () -> FxSmile.strike(M, Math.exp(-0.02 * 0.75), 0.1, 1, FxSmile.DeltaType.SPOT));
        fails("E_DOMAIN", "delta", () -> FxSmile.strike(M, 1.0, 0.1, 1, FxSmile.DeltaType.FORWARD));
        fails("E_DOMAIN", "delta", () -> FxSmile.strike(M, 0.99, 0.1, 1, FxSmile.DeltaType.FORWARD_PA));
        fails("E_DOMAIN", "v", () -> FxSmile.atmStrike(M, NAN, FxSmile.AtmType.DNS, FxSmile.DeltaType.SPOT));
    }

    @Test
    void strikesRoundTripForEveryDeltaType() {
        double v = 0.12;
        for (FxSmile.DeltaType t : FxSmile.DeltaType.values()) {
            for (double d : new double[] {0.1, 0.25, 0.4, -0.1, -0.25, -0.6}) {
                double phi = Math.signum(d);
                double k = FxSmile.strike(M, d, v, phi, t);
                assertEquals(d, FxSmile.delta(M, k, v, phi, t), 1e-13, t + " " + d);
            }
        }
        double kDns = FxSmile.atmStrike(M, v, FxSmile.AtmType.DNS, FxSmile.DeltaType.SPOT);
        assertEquals(-FxSmile.delta(M, kDns, v, -1, FxSmile.DeltaType.SPOT),
                FxSmile.delta(M, kDns, v, 1, FxSmile.DeltaType.SPOT), 1e-15);
        double kPa = FxSmile.atmStrike(M, v, FxSmile.AtmType.DNS, FxSmile.DeltaType.SPOT_PA);
        assertEquals(-FxSmile.delta(M, kPa, v, -1, FxSmile.DeltaType.SPOT_PA),
                FxSmile.delta(M, kPa, v, 1, FxSmile.DeltaType.SPOT_PA), 1e-15);
        // the PA call delta at the maximum-delta strike is the cap
        double ks = FxSmile.maxDeltaStrike(M, v);
        double cap = FxSmile.delta(M, ks, v, 1, FxSmile.DeltaType.FORWARD_PA);
        for (double r : new double[] {0.999, 1.001}) {
            assertEquals(true, FxSmile.delta(M, ks * r, v, 1, FxSmile.DeltaType.FORWARD_PA) < cap);
        }
    }

    @Test
    void greeksMatchFiniteDifferences() {
        double k = 1.12;
        double v = 0.11;
        double h = 1e-5;
        for (double phi : new double[] {1, -1}) {
            FxSmile.Price p = FxSmile.price(M, k, v, phi, 1e6);
            FxSmile.Market up = new FxSmile.Market(M.spot() + h, M.t(), M.rd(), M.rf());
            FxSmile.Market dn = new FxSmile.Market(M.spot() - h, M.t(), M.rd(), M.rf());
            double pu = FxSmile.price(up, k, v, phi, 1e6).price();
            double pd = FxSmile.price(dn, k, v, phi, 1e6).price();
            assertEquals((pu - pd) / (2 * h), p.delta(), 1e-6 * Math.abs(p.delta()));
            assertEquals((pu - 2 * p.price() + pd) / (h * h), p.gamma(), 1e-3 * p.gamma());
            double vu = FxSmile.price(M, k, v + 1e-6, phi, 1e6).price();
            double vd = FxSmile.price(M, k, v - 1e-6, phi, 1e6).price();
            assertEquals((vu - vd) / 2e-6, p.vega(), 1e-7 * p.vega());
            assertEquals(p.price() / 1e6 / M.spot(), p.premiumPctForeign(), 1e-15);
        }
    }
}
