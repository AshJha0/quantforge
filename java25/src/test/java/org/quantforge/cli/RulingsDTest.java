package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Xccy;
import org.quantforge.pricing.Bonds;
import org.quantforge.pricing.CmdtyMbs;
import org.quantforge.pricing.Credit;

/** The code paths rulings D33 to D39 changed. */
class RulingsDTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final Curve D = Curve.of(AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 11, 6), LocalDate.of(2046, 11, 6)}, new double[] {0.96, 0.45});

    private static void code(String expected, Runnable r) {
        try {
            r.run();
            throw new AssertionError("expected " + expected);
        } catch (QfError e) {
            assertEquals(expected, e.code());
        }
    }

    @Test
    void d33AndD34Mbs() {
        code("E_INPUT", () -> CmdtyMbs.cashflows(new CmdtyMbs.Pool(1e6, 0.06, 0.05, 1201, 0, false, 0.1)));
        code("E_INPUT", () -> CmdtyMbs.cashflows(new CmdtyMbs.Pool(1e6, 0.0, 0.05, 1201, 0, false, 0.1)));
        code("E_DOMAIN", () -> CmdtyMbs.cashflows(new CmdtyMbs.Pool(1e6, 0.0, 0.05, 60, 0, false, 0.1)));
        code("E_DOMAIN", () -> CmdtyMbs.price(new CmdtyMbs.Pool(1e6, 0.06, 0.05, 60, 0, false, 0.1), -12.0, 0));
        CmdtyMbs.cashflows(new CmdtyMbs.Pool(1e6, 0.06, 0.05, 1200, 0, false, 0.1));
    }

    @Test
    void d35ConversionFactorDateOrder() {
        code("E_DATE_ORDER", () -> Bonds.conversionFactor(new Bonds.Bond(LocalDate.of(2026, 11, 15), 0.04, 2),
                YearMonth.of(2026, 12), 0.06));
    }

    @Test
    void d36CreditAsOf() {
        LocalDate t = AS_OF.plusDays(1);
        code("E_INPUT", () -> Credit.bootstrap(t, D, 0.4, new String[] {"1Y"}, new double[] {0.01}));
        Credit.Hazard h = new Credit.Hazard(t, new LocalDate[] {LocalDate.of(2030, 1, 1)}, new double[] {0.9});
        code("E_INPUT", () -> Credit.price(AS_OF, D, h, 0.4, LocalDate.of(2029, 12, 20), 0.01, 1, true, false));
    }

    @Test
    void d37NelsonSiegelZeroWeights() {
        Bonds.Bond b = new Bonds.Bond(LocalDate.of(2030, 1, 1), 0.04, 2);
        code("E_DOMAIN", () -> Bonds.nsBetas(List.of(b, b, b), new double[] {100, 100, 100}, new double[] {0, 0, 0},
                AS_OF, 2.0));
        code("E_DOMAIN", () -> Bonds.nsBetas(List.of(b, b, b), new double[] {100, 100, 100}, new double[] {1, -1, 1},
                AS_OF, 2.0));
        code("E_INPUT", () -> Bonds.nsBetas(List.of(b, b, b), new double[] {100, 100, 100}, new double[] {1, 1, 0},
                AS_OF, 2.0));
    }

    @Test
    void d39XccyStartBeforeAsOf() {
        code("E_OUT_OF_RANGE", () -> Xccy.pv(D, D, D, 1.1, LocalDate.of(2026, 11, 4), 12, 1, 0, true));
    }

    @Test
    void d52CdsMaturityNotAfterTradeDate() {
        Credit.Hazard h = new Credit.Hazard(AS_OF, new LocalDate[] {LocalDate.of(2030, 1, 1)}, new double[] {0.9});
        code("E_INPUT", () -> Credit.price(AS_OF, D, h, 0.4, AS_OF, 0.01, 1, true, false));
        code("E_INPUT", () -> new Credit.Hazard(AS_OF, new LocalDate[] {AS_OF}, new double[] {0.9}));
        code("E_DOMAIN", () -> new Credit.Hazard(AS_OF, new LocalDate[] {LocalDate.of(2030, 1, 1)}, new double[] {1.1}));
    }
}
