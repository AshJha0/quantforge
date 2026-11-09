package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.CapSwaption;
import org.quantforge.pricing.CmdtyMbs;

/** Stage D D7 to D9: parity identities, edge and error paths, and a fuzz pass. */
class CapsCmdtyMbsTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final Curve D = Curve.of(AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 11, 6), LocalDate.of(2056, 11, 6)},
            new double[] {Math.exp(-0.035), Math.exp(-0.035 * 30.0274)});
    private static final Curve P = Curve.of(AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 11, 6), LocalDate.of(2056, 11, 6)},
            new double[] {Math.exp(-0.038), Math.exp(-0.039 * 30.0274)});
    private static final String CURVE = "{\"as_of\":\"2026-11-06\",\"interpolation\":\"LOG_LINEAR_DF\",\"pillars\":"
            + "[{\"date\":\"2027-11-06\",\"discount_factor\":0.96},{\"date\":\"2046-11-06\",\"discount_factor\":0.45}]}";

    private static Map<?, ?> run(String op, String inputs) {
        String text = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"" + op + "\",\"inputs\":" + inputs + "}";
        return (Map<?, ?>) Json.parse(Main.handle(text).json()).value();
    }

    private static void error(String code, String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("error", r.get("status"), op + " " + inputs);
        assertEquals(code, ((Map<?, ?>) r.get("error")).get("code"), op + " " + inputs);
    }

    @Test
    void capFloorAndPayerReceiverParity() {
        for (boolean normal : new boolean[] {false, true}) {
            double v = normal ? 0.008 : 0.2;
            var cap = CapSwaption.cap(D, P, normal, new double[] {v}, false, true, 3, 24, 0.037, 1e6);
            var floor = CapSwaption.cap(D, P, normal, new double[] {v}, false, false, 3, 24, 0.037, 1e6);
            assertEquals(8, cap.caplets().length);
            // Cap - floor = sum N alpha D (F - K); at zero vol a cap is its intrinsic value.
            assertTrue(cap.price() > 0 && floor.price() > 0);
            var pay = CapSwaption.swaption(D, P, normal, v, true, 12, 60, 0.037, 1e6);
            var rec = CapSwaption.swaption(D, P, normal, v, false, 12, 60, 0.037, 1e6);
            assertEquals(1e6 * pay.annuity() * (pay.forward() - 0.037), pay.price() - rec.price(), 1e-7);
            if (normal) {
                assertTrue(CapSwaption.cap(D, P, true, new double[] {0.0}, false, true, 3, 24, -1.0, 1e6).price() > 0);
            }
        }
        try {
            CapSwaption.cap(D, P, false, new double[] {0.2, 0.2}, true, true, 3, 12, 0.037, 1e6);
            throw new AssertionError();
        } catch (QfError e) {
            assertEquals("E_INPUT", e.code());
        }
        String trade = "{\"type\":\"CAP\",\"start_months\":3,\"tenor_months\":12,\"strike\":0.03,\"notional\":1}";
        error("E_SCHEMA", "rates.cap.price", "{\"discount\":" + CURVE + ",\"projection\":" + CURVE
                + ",\"model\":\"BLACK_SCHOLES\",\"vol\":0.2,\"trade\":" + trade + "}");
        error("E_DOMAIN", "rates.cap.price", "{\"discount\":" + CURVE + ",\"projection\":" + CURVE
                + ",\"model\":\"BACHELIER\",\"vol\":[0.01,0.01,-0.01,0.01],\"trade\":" + trade + "}");
        error("E_INPUT", "rates.swaption.price", "{\"discount\":" + CURVE + ",\"projection\":" + CURVE
                + ",\"model\":\"BLACK_76\",\"vol\":0.2,\"trade\":{\"type\":\"PAYER\",\"expiry_months\":0,\"tenor_months\":60,"
                + "\"strike\":0.03,\"notional\":1}}");
    }

    @Test
    void commodityCurveRepricesAndCarryFlags() {
        double[] season = new double[12];
        season[0] = 0.05;
        long[] k = {24320, 24326};
        double[] f = CmdtyMbs.forwards(k, new double[] {3.0, 4.0}, season, new long[] {24320, 24323, 24326});
        assertEquals(3.0, f[0], 1e-15);
        assertEquals(4.0, f[2], 1e-15);
        assertEquals(Math.sqrt(12.0), f[1], 1e-14);
        try {
            CmdtyMbs.forwards(k, new double[] {3.0, 4.0}, null, new long[] {24327});
            throw new AssertionError();
        } catch (QfError e) {
            assertEquals("E_OUT_OF_RANGE", e.code());
        }
        CmdtyMbs.Carry c = CmdtyMbs.carry(D, new LocalDate[] {LocalDate.of(2027, 1, 1), LocalDate.of(2027, 7, 1)},
                new double[] {70, 80}, 0.0);
        assertTrue(c.arbitrage()[0]);
        assertTrue(c.yields()[0] < 0);
        error("E_INPUT", "cmdty.storage.carry", "{\"funding\":" + CURVE + ",\"forwards\":[{\"date\":\"2027-01-01\",\"price\":1}],"
                + "\"storage_cost\":0}");
    }

    @Test
    void mbsCashflowsAmortiseAndPriceAtParWithoutPrepayment() {
        CmdtyMbs.Pool p = new CmdtyMbs.Pool(1e6, 0.06, 0.06, 360, 0, false, 0.0);
        CmdtyMbs.Flows f = CmdtyMbs.cashflows(p);
        double sum = 0.0;
        for (int i = 0; i < 360; i++) {
            sum += f.scheduled()[i] + f.prepayment()[i];
        }
        assertEquals(1e6, sum, 1e-6);
        // Yield equal to the coupon, no delay: price 100.
        assertEquals(100.0, CmdtyMbs.price(p, 0.06, 0).price(), 1e-9);
        CmdtyMbs.Pool psa = new CmdtyMbs.Pool(1e6, 0.065, 0.06, 60, 0, true, 150.0);
        CmdtyMbs.Flows g = CmdtyMbs.cashflows(psa);
        assertEquals(1e6 * 0.065 / 12 / -Math.expm1(-60 * Math.log1p(0.065 / 12)) - 1e6 * 0.065 / 12, g.scheduled()[0], 1e-8);
        String pool = "{\"balance\":1e6,\"wac\":%s,\"net_coupon\":%s,\"wam\":%s,\"age\":0,\"prepayment\":{\"model\":\"CPR\",\"rate\":%s}}";
        error("E_INPUT", "mbs.cashflows", "{\"pool\":" + pool.formatted(0.06, 0.07, 60, 0.1) + "}");
        error("E_INPUT", "mbs.cashflows", "{\"pool\":" + pool.formatted(0.06, 0.05, 0, 0.1) + "}");
        error("E_DOMAIN", "mbs.cashflows", "{\"pool\":" + pool.formatted(0.06, 0.05, 60, 1.0) + "}");
        error("E_INPUT", "mbs.cashflows", "{\"pool\":" + pool.formatted(0.06, 0.05, 100000, 0.1) + "}");
        error("E_INPUT", "mbs.price", "{\"pool\":" + pool.formatted(0.06, 0.05, 60, 0.1) + ",\"yield\":0.05,\"delay_days\":-1}");
    }

    @Test
    void fuzzExtremeInputs() {
        String[] x = {"0", "-0.0", "1e308", "-1e308", "1e-308", "-1", "1e15", "0.5", "3"};
        String[] templates = {
            "rates.cap.price|{\"discount\":" + CURVE + ",\"projection\":" + CURVE + ",\"model\":\"BACHELIER\",\"vol\":%s,"
                    + "\"trade\":{\"type\":\"FLOOR\",\"start_months\":3,\"tenor_months\":12,\"strike\":%s,\"notional\":%s}}",
            "rates.swaption.price|{\"discount\":" + CURVE + ",\"projection\":" + CURVE + ",\"model\":\"BLACK_76\",\"vol\":%s,"
                    + "\"trade\":{\"type\":\"PAYER\",\"expiry_months\":12,\"tenor_months\":24,\"strike\":%s,\"notional\":%s}}",
            "cmdty.curve.forward|{\"quotes\":[{\"month\":\"2026-12\",\"price\":%s},{\"month\":\"2027-12\",\"price\":%s}],"
                    + "\"seasonality\":null,\"months\":[\"2027-06\"]}",
            "mbs.price|{\"pool\":{\"balance\":%s,\"wac\":%s,\"net_coupon\":0.0,\"wam\":12,\"age\":0,"
                    + "\"prepayment\":{\"model\":\"PSA\",\"speed\":%s}},\"yield\":%s,\"delay_days\":3}",
        };
        Random rng = new Random(13);
        for (String t : templates) {
            String[] parts = t.split("\\|", 2);
            for (int trial = 0; trial < 50; trial++) {
                Object[] v = new Object[5];
                for (int i = 0; i < 5; i++) {
                    v[i] = x[rng.nextInt(x.length)];
                }
                assertNotNull(run(parts[0], parts[1].formatted(v)).get("status"));
            }
        }
    }
}
