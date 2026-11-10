package org.quantforge.curves;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.QfError;

/** Library-level guards and leg arithmetic of Xccy. */
class XccyGuardTest {
    static final double NAN = Double.NaN;
    static final LocalDate S = LocalDate.of(2026, 3, 2);
    static final Curve D = Curve.of(S, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 3, 2), LocalDate.of(2036, 3, 2)}, new double[] {0.97, 0.7});
    static final Curve F = Curve.of(S, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 3, 2), LocalDate.of(2036, 3, 2)}, new double[] {0.98, 0.8});

    static void fails(String code, String field, Executable e) {
        QfError x = assertThrows(QfError.class, e);
        assertEquals(code, x.code());
        assertEquals(field, x.field());
    }

    @Test
    void guards() {
        List<LocalDate> dates = Xccy.schedule(S, 12);
        fails("E_DOMAIN", "m", () -> Xccy.leg(dates, F, F, NAN));
        fails("E_DOMAIN", "spot", () -> Xccy.pv(D, F, F, NAN, S, 12, 1e6, 0.0, true));
        fails("E_DOMAIN", "notional", () -> Xccy.pv(D, F, F, 1.1, S, 12, NAN, 0.0, true));
        fails("E_DOMAIN", "spread", () -> Xccy.pv(D, F, F, 1.1, S, 12, 1e6, NAN, true));
        fails("E_DOMAIN", "spot", () -> Xccy.pv(D, F, F, 0.0, S, 12, 1e6, 0.0, true));
        fails("E_DOMAIN", "spreads", () -> Xccy.bootstrap(D, F, S, new long[] {12}, new double[] {NAN},
                Curve.Interpolation.LOG_LINEAR_DF));
        fails("E_INPUT", "quotes", () -> Xccy.bootstrap(D, F, S, new long[] {12, 12}, new double[] {0.0, 0.0},
                Curve.Interpolation.LOG_LINEAR_DF));
        LocalDate fix = LocalDate.of(2026, 9, 1);
        LocalDate pay = LocalDate.of(2026, 9, 3);
        fails("E_DOMAIN", "spot", () -> Xccy.ndf(D, F, NAN, fix, pay, 80.0, 1e6, true, null));
        fails("E_DOMAIN", "strike", () -> Xccy.ndf(D, F, 80.0, fix, pay, NAN, 1e6, true, null));
        fails("E_DOMAIN", "notional", () -> Xccy.ndf(D, F, 80.0, fix, pay, 80.0, NAN, true, null));
        fails("E_DOMAIN", null, () -> Xccy.ndf(D, F, 0.0, fix, pay, 80.0, 1e6, true, null));
        fails("E_DOMAIN", null, () -> Xccy.ndf(D, F, 80.0, fix, pay, 0.0, 1e6, true, null));
        fails("E_DOMAIN", null, () -> Xccy.ndf(D, F, 80.0, S, pay, 80.0, 1e6, true, 0.0));
        fails("E_DATE_ORDER", "payment_date", () -> Xccy.ndf(D, F, 80.0, pay, fix, 80.0, 1e6, true, null));
        fails("E_INPUT", "months", () -> Xccy.schedule(S, 0));
        fails("E_INPUT", "months", () -> Xccy.schedule(S, 1203));
        assertEquals(41, Xccy.schedule(S, 120).size());
        fails("E_INPUT", "months", () -> Xccy.schedule(S, 4));
    }

    @Test
    void pvIsBuiltFromTheTwoLegs() {
        List<LocalDate> dates = Xccy.schedule(S, 24);
        double f = 1e6 * Xccy.leg(dates, F, F, 0.001);
        double d = 1e6 * 1.1 * Xccy.leg(dates, D, D, 0.0);
        Xccy.Pv pv = Xccy.pv(D, F, F, 1.1, S, 24, 1e6, 0.001, true);
        assertEquals(f, pv.foreignLeg(), 1e-9);
        assertEquals(d, pv.domesticLeg(), 1e-9);
        assertEquals(1.1 * f - d, pv.pv(), 1e-9);
        assertEquals(-(1.1 * f - d), Xccy.pv(D, F, F, 1.1, S, 24, 1e6, 0.001, false).pv(), 1e-9);
    }
}
