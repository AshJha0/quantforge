package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.QfError;

/** Library-level guards and closed forms of Garch. */
class GarchGuardTest {
    static final double NAN = Double.NaN;

    static void fails(String code, String field, Executable e) {
        QfError x = assertThrows(QfError.class, e);
        assertEquals(code, x.code());
        assertEquals(field, x.field());
    }

    @Test
    void guards() {
        fails("E_DOMAIN", "omega", () -> Garch.checkParameters(NAN, 0.1, 0.8));
        fails("E_DOMAIN", "alpha", () -> Garch.checkParameters(1e-6, NAN, 0.8));
        fails("E_DOMAIN", "beta", () -> Garch.checkParameters(1e-6, 0.1, NAN));
        fails("E_DOMAIN", null, () -> Garch.checkParameters(0.0, 0.1, 0.8));
        Garch.checkParameters(1e-6, 0.0, 0.0);
        double[] r = {0.01, -0.02, 0.005};
        fails("E_DOMAIN", "r", () -> Garch.path(new double[] {NAN}, 1e-6, 0.1, 0.8, 1e-4));
        fails("E_DOMAIN", "omega", () -> Garch.path(r, NAN, 0.1, 0.8, 1e-4));
        fails("E_DOMAIN", "alpha", () -> Garch.path(r, 1e-6, NAN, 0.8, 1e-4));
        fails("E_DOMAIN", "beta", () -> Garch.path(r, 1e-6, 0.1, NAN, 1e-4));
        fails("E_DOMAIN", "v0", () -> Garch.path(r, 1e-6, 0.1, 0.8, NAN));
        fails("E_DOMAIN", "omega", () -> Garch.forecast(NAN, 0.1, 0.8, 1e-4, 5, 252));
        fails("E_DOMAIN", "alpha", () -> Garch.forecast(1e-6, NAN, 0.8, 1e-4, 5, 252));
        fails("E_DOMAIN", "beta", () -> Garch.forecast(1e-6, 0.1, NAN, 1e-4, 5, 252));
        fails("E_DOMAIN", "next", () -> Garch.forecast(1e-6, 0.1, 0.8, NAN, 5, 252));
        fails("E_DOMAIN", "ppy", () -> Garch.forecast(1e-6, 0.1, 0.8, 1e-4, 5, NAN));
        fails("E_DOMAIN", "r", () -> Garch.fit(new double[] {NAN, 0.01}, 1e-4));
        fails("E_DOMAIN", "v0", () -> Garch.fit(r, NAN));
        fails("E_DOMAIN", null, () -> Garch.fit(new double[] {0.0, 0.0}, 1e-4));
    }

    @Test
    void pathAndForecastClosedForms() {
        double[] r = {0.01, -0.02, 0.005};
        double w = 1e-6;
        double a = 0.1;
        double b = 0.8;
        double v0 = 1e-4;
        Garch.Path p = Garch.path(r, w, a, b, v0);
        double s = v0;
        double ll = 0.0;
        for (double x : r) {
            ll += -0.5 * (Math.log(2 * Math.PI) + Math.log(s) + x * x / s);
            s = w + a * x * x + b * s;
        }
        assertEquals(ll, p.loglik(), 1e-12);
        assertEquals(s, p.next(), 1e-18);
        Garch.Forecast f = Garch.forecast(w, a, b, 2e-4, 3, 252);
        double vl = w / (1 - a - b);
        assertEquals(vl, f.longRun(), 1e-18);
        double tot = 0.0;
        for (int i = 0; i < 3; i++) {
            double v = vl + Math.pow(a + b, i) * (2e-4 - vl);
            assertEquals(v, f.variances()[i], 1e-18);
            tot += v;
        }
        assertEquals(tot, f.total(), 1e-17);
        assertEquals(Math.sqrt(tot * 252 / 3), f.annualizedVol(), 1e-14);
    }
}
