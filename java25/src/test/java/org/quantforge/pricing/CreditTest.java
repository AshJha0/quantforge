package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Credit boundaries and the accrual-on-default series, against an independent integral (credit.md). */
class CreditTest {
    private static final LocalDate T = LocalDate.of(2026, 3, 2);
    private static final LocalDate FAR = LocalDate.of(2040, 1, 2);
    private static final Curve FLAT_ZERO = Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF, new LocalDate[] {FAR},
            new double[] {1.0});

    private static double years(LocalDate a, LocalDate b) {
        return ChronoUnit.DAYS.between(a, b) / 365.0;
    }

    private static Credit.Hazard flat(double h) {
        return new Credit.Hazard(T, new LocalDate[] {FAR}, new double[] {Math.exp(-h * years(T, FAR))});
    }

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    /** integral of (u - c) e^{-h u} du over [a, b], with no cancellation for small h (b - a). */
    private static double accrualIntegral(double h, double a, double b, double c) {
        double d = b - a;
        double x = h * d;
        double first = -Math.expm1(-x) / h;
        double series = 0.0; // (1 - e^{-x}(1 + x)) / h^2 = d^2 sum_{m>=2} (-1)^m x^(m-2) (m-1)/m!
        double fact = 2.0;
        for (int m = 2; m <= 14; m++) {
            series += (m % 2 == 0 ? 1.0 : -1.0) * Math.pow(x, m - 2) * (m - 1) / fact;
            fact *= m + 1;
        }
        return Math.exp(-h * a) * ((a - c) * first + d * d * series);
    }

    @Test
    void accrualOnDefaultMatchesTheIntegralWhereTheSeriesIsUsed() {
        double h = 3e-4; // every node interval has h d below 1e-4, so legs takes the series branch
        LocalDate maturity = LocalDate.of(2031, 6, 20);
        Credit.Hazard q = flat(h);
        double premium = 0.0;
        double aod = 0.0;
        for (Credit.Period per : Credit.periods(T, maturity)) {
            LocalDate obs = per.pay().minusDays(1);
            premium += per.alpha() * q.survival(obs);
            LocalDate accStart = per.start().minusDays(1);
            LocalDate s = accStart.isAfter(T) ? accStart : T;
            aod += h * accrualIntegral(h, years(T, s), years(T, obs), years(T, accStart));
        }
        Credit.Price p = Credit.price(T, FLAT_ZERO, q, 0.4, maturity, 0.01, 1.0, true, false);
        double modelAod = (p.rpv01() - premium) * 360.0 / 365.0;
        assertEquals(aod, modelAod, 1e-9 * aod); // the subtraction leaves about 1e-9 relative
    }

    @Test
    void recoveryAndSpreadBoundaries() {
        Credit.Hazard q = flat(0.02);
        LocalDate m = LocalDate.of(2031, 6, 20);
        Credit.price(T, FLAT_ZERO, q, 0.0, m, 0.01, 1.0, true, false); // 0 is allowed
        assertEquals("E_DOMAIN", code(() -> Credit.price(T, FLAT_ZERO, q, 1.0, m, 0.01, 1.0, true, false)));
        Credit.bootstrap(T, FLAT_ZERO, 0.0, new String[] {"5Y"}, new double[] {0.01});
        assertEquals("E_DOMAIN", code(() -> Credit.bootstrap(T, FLAT_ZERO, 1.0, new String[] {"5Y"},
                new double[] {0.01})));
        assertEquals("E_DOMAIN", code(() -> Credit.bootstrap(T, FLAT_ZERO, 0.4, new String[] {"5Y"},
                new double[] {0.0})));
    }

    @Test
    void tenorIsCheckedBeforeItIsParsed() {
        assertEquals("E_SCHEMA", code(() -> Credit.maturity(T, "0Y")));
        assertEquals("E_SCHEMA", code(() -> Credit.maturity(T, "5D")));
    }
}
