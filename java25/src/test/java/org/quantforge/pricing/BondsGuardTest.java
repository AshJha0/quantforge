package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Library-level guards of Bonds: each finite check and date check names its own field. */
class BondsGuardTest {
    static final double NAN = Double.NaN;
    static final LocalDate S = LocalDate.of(2026, 3, 2);
    static final Bonds.Bond B = new Bonds.Bond(LocalDate.of(2031, 2, 15), 0.04, 2);
    static final Curve C = Curve.of(S, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 3, 2), LocalDate.of(2036, 3, 2)}, new double[] {0.97, 0.7});

    static void fails(String code, String field, Executable e) {
        QfError x = assertThrows(QfError.class, e);
        assertEquals(code, x.code());
        assertEquals(field, x.field());
    }

    static void nan(String field, Executable e) {
        fails("E_DOMAIN", field, e);
    }

    @Test
    void finiteChecksNameTheirField() {
        nan("y", () -> Bonds.fromYield(B, S, NAN));
        nan("clean", () -> Bonds.yieldFromPrice(B, S, NAN));
        nan("z", () -> Bonds.curveDirty(B, S, C, NAN));
        nan("clean", () -> Bonds.zSpread(B, S, C, NAN));
        nan("dirtyPrice", () -> Bonds.assetSwap(B, S, C, NAN));
        LocalDate m = LocalDate.of(2029, 3, 2);
        nan("current", () -> Bonds.frn(S, m, 4, NAN, 0.01, 0.0, C, C));
        nan("margin", () -> Bonds.frn(S, m, 4, 0.03, NAN, 0.0, C, C));
        nan("dm", () -> Bonds.frn(S, m, 4, 0.03, 0.01, NAN, C, C));
        LocalDate e = S.plusMonths(3);
        nan("clean", () -> Bonds.repo(B, S, e, NAN, 0.03, null));
        nan("r", () -> Bonds.repo(B, S, e, 99.0, NAN, null));
        nan("clean", () -> Bonds.impliedRepo(B, S, e, NAN, 99.0));
        nan("forwardClean", () -> Bonds.impliedRepo(B, S, e, 99.0, NAN));
        nan("notional", () -> Bonds.conversionFactor(B, YearMonth.of(2026, 6), NAN, Bonds.Contract.FIVE_YEAR));
        nan("clean", () -> Bonds.basis(B, NAN, 0.9, 110.0, S, e, 0.03));
        nan("cf", () -> Bonds.basis(B, 99.0, NAN, 110.0, S, e, 0.03));
        nan("futures", () -> Bonds.basis(B, 99.0, 0.9, NAN, S, e, 0.03));
        nan("r", () -> Bonds.basis(B, 99.0, 0.9, 110.0, S, e, NAN));
        nan("guess", () -> Bonds.solveDecreasing(x -> 1.0 - x, NAN, -5.0, 5.0));
        nan("lo", () -> Bonds.solveDecreasing(x -> 1.0 - x, 0.0, NAN, 5.0));
        nan("hi", () -> Bonds.solveDecreasing(x -> 1.0 - x, 0.0, -5.0, NAN));
        List<Bonds.Bond> bs = List.of(B);
        nan("dirty", () -> Bonds.nsBetas(bs, new double[] {NAN}, new double[] {1.0}, S, 2.0));
        nan("w", () -> Bonds.nsBetas(bs, new double[] {100.0}, new double[] {NAN}, S, 2.0));
        nan("tau", () -> Bonds.nsBetas(bs, new double[] {100.0}, new double[] {1.0}, S, NAN));
        double[] beta = {0.04, -0.01, 0.01};
        nan("tau", () -> Bonds.nsModel(B, S, NAN, beta, null));
        nan("beta", () -> Bonds.nsModel(B, S, 2.0, new double[] {NAN, 0, 0}, null));
        nan("grad", () -> Bonds.nsModel(B, S, 2.0, beta, new double[] {NAN, 0, 0}));
    }

    @Test
    void settlementAndTermChecks() {
        LocalDate late = B.maturity();
        fails("E_DATE_ORDER", "settlement", () -> Bonds.curveDirty(B, late, C, 0.0));
        fails("E_DATE_ORDER", "settlement", () -> Bonds.yieldFromPrice(B, late, 99.0));
        fails("E_DATE_ORDER", "settlement", () -> Bonds.frn(late, late, 4, 0.03, 0.01, 0.0, C, C));
        fails("E_DATE_ORDER", "settlement",
                () -> Bonds.nsBetas(List.of(B), new double[] {100.0}, new double[] {1.0}, late, 2.0));
        fails("E_DATE_ORDER", "end", () -> Bonds.impliedRepo(B, S, S, 99.0, 99.0));
    }

    @Test
    void solverEdgesAndYieldRoundTrip() {
        // root exactly at the guess, and roots near the bracket ends
        assertEquals(0.5, Bonds.solveDecreasing(x -> 0.5 - x, 0.5, -1.0, 1.0), 0.0);
        assertEquals(0.999, Bonds.solveDecreasing(x -> 0.999 - x, 0.0, -1.0, 1.0), 1e-14);
        assertEquals(-0.999, Bonds.solveDecreasing(x -> -0.999 - x, 0.0, -1.0, 1.0), 1e-14);
        assertEquals(Math.log(3.0), Bonds.solveDecreasing(x -> 3.0 - Math.exp(x), 0.0, -5.0, 5.0), 1e-15);
        assertEquals("E_NO_CONVERGENCE",
                assertThrows(QfError.class, () -> Bonds.solveDecreasing(x -> 2.0 - x, 0.0, -1.0, 1.0)).code());
        for (double y : new double[] {-0.01, 0.0, 0.035, 0.2}) {
            double clean = Bonds.fromYield(B, S, y).clean();
            assertEquals(y, Bonds.yieldFromPrice(B, S, clean), 1e-13);
        }
        for (double z : new double[] {-0.02, 0.0, 0.015}) {
            double dirty = Bonds.curveDirty(B, S, C, z);
            assertEquals(z, Bonds.zSpread(B, S, C, dirty - B.accrued(S)), 1e-13);
        }
        // 1 + y/f must be positive: y = -2 is the edge for semi-annual
        fails("E_DOMAIN", "yield", () -> Bonds.fromYield(B, S, -2.0));
        assertTrue(Bonds.fromYield(B, S, -1.99).dirty() > 0.0);
    }

    @Test
    void conversionFactorAroundTheSevenMonthEdge() {
        Bonds.Bond hi = new Bonds.Bond(LocalDate.of(2031, 1, 15), 0.08, 2);
        double z6 = Bonds.conversionFactor(hi, YearMonth.of(2025, 7), 0.06, Bonds.Contract.TWO_YEAR);
        double z7 = Bonds.conversionFactor(hi, YearMonth.of(2025, 6), 0.06, Bonds.Contract.TWO_YEAR);
        assertEquals(expectedCf(0.08, 5, 6), z6, 0.0);
        assertEquals(expectedCf(0.08, 5, 7), z7, 0.0);
        assertEquals(expectedCf(0.08, 0, 0),
                Bonds.conversionFactor(new Bonds.Bond(LocalDate.of(2026, 6, 15), 0.08, 2), YearMonth.of(2026, 6),
                        0.06, Bonds.Contract.TWO_YEAR), 0.0);
        fails("E_DATE_ORDER", "bond", () -> Bonds.conversionFactor(hi, YearMonth.of(2031, 2), 0.06,
                Bonds.Contract.TWO_YEAR));
    }

    private static double expectedCf(double cpn, long n, long z) {
        double v = z < 7 ? z : z - 6;
        double a = Math.pow(1.03, -v / 6.0);
        double bb = cpn / 2.0 * (6.0 - v) / 6.0;
        double c = z < 7 ? Math.pow(1.03, -2.0 * n) : Math.pow(1.03, -2.0 * n - 1.0);
        double cf = a * (cpn / 2.0 + cpn / 0.06 * (1.0 - c) + c) - bb;
        return new java.math.BigDecimal(cf).setScale(4, java.math.RoundingMode.HALF_EVEN).doubleValue();
    }
}
