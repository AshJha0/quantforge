package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.List;
import java.util.function.ToDoubleFunction;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.pricing.Pricing;

/** Properties of par, key-rate and Jacobian risk that hold whatever the market (par-and-key-rate.md). */
class CurveRiskTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final List<Ois.Quote> QUOTES = List.of(q("1M", 0.0386), q("6M", 0.0377), q("1Y", 0.0365),
            q("2Y", 0.035), q("5Y", 0.035), q("10Y", 0.0375));
    private static final Pricing.OisTrade RECEIVER =
            new Pricing.OisTrade(Conventions.SOFR, "2Y", 0.0345, 1e7, Pricing.Side.RECEIVE);

    private static Ois.Quote q(String tenor, double rate) {
        return new Ois.Quote(tenor, rate, null, null);
    }

    private static Curve curve() {
        return Ois.bootstrap(Conventions.SOFR, AS_OF, QUOTES, Curve.Interpolation.LOG_LINEAR_DF,
                CurveSolver.Method.SEQUENTIAL, null).curve();
    }

    private static ToDoubleFunction<Curve> receiver() {
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, RECEIVER.tenor());
        return c -> Pricing.oisPv(RECEIVER, legs, c);
    }

    @Test
    void triangularWeightsSumToOneAndPeakAtTheirKey() {
        double[] k = {1.0, 2.0, 5.0};
        for (double t = 0.0; t <= 7.0; t += 0.125) {
            double sum = 0.0;
            for (int i = 0; i < k.length; i++) {
                double w = CurveRisk.weight(k, i, t);
                assertTrue(w >= 0.0 && w <= 1.0);
                sum += w;
            }
            assertEquals(1.0, sum, 1e-15, "t = " + t);
        }
        assertEquals(1.0, CurveRisk.weight(k, 1, 2.0));
        assertEquals(0.5, CurveRisk.weight(k, 1, 1.5));
        assertEquals(0.5, CurveRisk.weight(k, 2, 3.5));
        assertEquals(1.0, CurveRisk.weight(k, 2, 9.0));
    }

    @Test
    void zeroShiftMovesEveryDiscountFactor() {
        Curve c = curve();
        LocalDate d = LocalDate.of(2030, 3, 1);
        Curve up = c.withZeroShift(t -> 0.01);
        assertEquals(c.discount(d) * Math.exp(-0.01 * c.time(d)), up.discount(d), 1e-15);
        assertEquals(c.zeroRate(d) + 0.01, up.zeroRate(d), 1e-15);
        assertThrows(IllegalStateException.class, () -> up.withZeroShift(t -> 0.0));
    }

    @Test
    void receiverGainsWhenRatesFallAndBucketsAddUp() {
        CurveRisk.Par p = CurveRisk.par(Conventions.SOFR, AS_OF, QUOTES, Curve.Interpolation.LOG_LINEAR_DF,
                receiver(), 1.0, CurveRisk.Scheme.CENTRAL);
        assertTrue(p.parDv01() < 0.0, "a receiver loses when rates rise");
        double sum = 0.0;
        for (double b : p.parBuckets()) {
            sum += b;
        }
        assertEquals(p.parDv01(), sum, 1e-4 * Math.abs(p.parDv01()));
        assertEquals(0.0, p.parBuckets()[5], 0.0, "a 2Y swap cannot see the 10Y quote");
        CurveRisk.Par fwd = CurveRisk.par(Conventions.SOFR, AS_OF, QUOTES, Curve.Interpolation.LOG_LINEAR_DF,
                receiver(), 1.0, CurveRisk.Scheme.FORWARD);
        assertEquals(p.value(), fwd.value(), 0.0);
        assertEquals(p.parDv01(), fwd.parDv01(), 1e-3 * Math.abs(p.parDv01()));
    }

    @Test
    void keyRatesAddUpInBothModesAndScaleWithTheBump() {
        Curve c = curve();
        LocalDate[] keys = {LocalDate.of(2027, 11, 6), LocalDate.of(2028, 11, 6), LocalDate.of(2031, 11, 6)};
        for (CurveRisk.Mode mode : CurveRisk.Mode.values()) {
            LocalDate[] k = mode == CurveRisk.Mode.TRIANGULAR ? keys : null;
            CurveRisk.KeyRate r = CurveRisk.keyRate(c, mode, k, receiver(), 1.0, CurveRisk.Scheme.CENTRAL);
            double sum = 0.0;
            for (double b : r.keyRates()) {
                sum += b;
            }
            assertEquals(r.zeroDv01(), sum, 1e-6 * Math.abs(r.zeroDv01()), mode.name());
            CurveRisk.KeyRate wide = CurveRisk.keyRate(c, mode, k, receiver(), 10.0, CurveRisk.Scheme.CENTRAL);
            assertEquals(r.zeroDv01(), wide.zeroDv01(), 1e-3 * Math.abs(r.zeroDv01()), "per-bp units");
        }
    }

    @Test
    void jacobianIsLowerTriangularAndGivesParFromPillarKeyRates() {
        CurveRisk.Jacobian j = CurveRisk.jacobian(Conventions.SOFR, AS_OF, QUOTES, Curve.Interpolation.LOG_LINEAR_DF,
                1.0);
        int n = QUOTES.size();
        for (int i = 0; i < n; i++) {
            for (int k = i + 1; k < n; k++) {
                assertEquals(0.0, j.jacobian()[i][k], 0.0);
            }
            assertTrue(j.jacobian()[i][i] > 0.5, "a pillar moves with its own quote");
        }
        CurveRisk.KeyRate pillar = CurveRisk.keyRate(curve(), CurveRisk.Mode.PILLAR, null, receiver(), 1.0,
                CurveRisk.Scheme.CENTRAL);
        CurveRisk.Par par = CurveRisk.par(Conventions.SOFR, AS_OF, QUOTES, Curve.Interpolation.LOG_LINEAR_DF,
                receiver(), 1.0, CurveRisk.Scheme.CENTRAL);
        for (int q = 0; q < n; q++) {
            double chain = 0.0;
            for (int i = 0; i < n; i++) {
                chain += pillar.keyRates()[i] * j.jacobian()[i][q];
            }
            assertEquals(par.parBuckets()[q], chain, 1e-3 * Math.abs(par.parDv01()), "quote " + q);
        }
    }

    @Test
    void pnlExplainPassesSmallMovesAndFailsAShockOnALongTrade() {
        List<Ois.Quote> up1 = QUOTES.stream().map(x -> q(x.tenor(), x.rate() + 0.0001)).toList();
        CurveRisk.Explain e = CurveRisk.explain(Conventions.SOFR, AS_OF, Curve.Interpolation.LOG_LINEAR_DF, QUOTES,
                up1, receiver(), 1.0, RECEIVER.notional());
        assertEquals(e.valueEnd() - e.valueStart(), e.fullPnl(), 0.0);
        assertEquals(e.fullPnl() - e.riskPnl(), e.unexplained(), 0.0);
        assertTrue(e.explained());
        Pricing.OisTrade longPay = new Pricing.OisTrade(Conventions.SOFR, "10Y", 0.0375, 1e8, Pricing.Side.PAY);
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, "10Y");
        List<Ois.Quote> twist = QUOTES.stream()
                .map(x -> q(x.tenor(), x.rate() + (x.tenor().equals("10Y") ? 0.03 : -0.03))).toList();
        CurveRisk.Explain shock = CurveRisk.explain(Conventions.SOFR, AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
                QUOTES, twist, c -> Pricing.oisPv(longPay, legs, c), 1.0, longPay.notional());
        assertTrue(Math.abs(shock.unexplained()) > 0.0);
        assertTrue(shock.grossRiskPnl() >= Math.abs(shock.riskPnl()));
        assertEquals(0.05 * Math.max(Math.abs(shock.fullPnl()), shock.grossRiskPnl()) + 1e-8 * longPay.notional(),
                shock.threshold(), 0.0);
        CurveRisk.Explain still = CurveRisk.explain(Conventions.SOFR, AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
                QUOTES, QUOTES, receiver(), 1.0, RECEIVER.notional());
        assertEquals(0.0, still.grossRiskPnl(), 0.0);
        assertEquals(1e-8 * RECEIVER.notional(), still.threshold(), 0.0, "no move leaves only the floor");
        assertTrue(still.explained());
        assertEquals(Math.abs(shock.unexplained()) <= shock.threshold(), shock.explained());
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> CurveRisk.checkSameTenors(QUOTES, QUOTES.subList(0, 3))).code());
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> CurveRisk.checkSameTenors(QUOTES, QUOTES.reversed())).code());
    }

    @Test
    void inputChecks() {
        Curve c = curve();
        for (double b : new double[] {0.0, -1.0, 100.5, Double.NaN}) {
            assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> CurveRisk.checkBump(b)).code());
        }
        CurveRisk.checkBump(100.0);
        LocalDate[] none = {};
        LocalDate[] unordered = {LocalDate.of(2028, 1, 1), LocalDate.of(2027, 1, 1)};
        LocalDate[] atAsOf = {AS_OF};
        for (LocalDate[] k : new LocalDate[][] {null, none, unordered, atAsOf}) {
            assertEquals("E_INPUT", assertThrows(QfError.class,
                    () -> CurveRisk.checkKeyDates(c, CurveRisk.Mode.TRIANGULAR, k)).code());
        }
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> CurveRisk.checkKeyDates(c, CurveRisk.Mode.PILLAR, unordered)).code());
    }
}
