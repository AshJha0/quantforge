package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** CPI curves with seasonality, ZCIS and linkers (inflation.md, rulings D25, D26). */
public final class Inflation {
    private Inflation() {}

    public static long index(YearMonth m) {
        return 12L * m.getYear() + m.getMonthValue() - 1;
    }

    public static final class CpiCurve {
        private final long base;
        private final double lnBase;
        private final double rawBase;
        private final long[] k;
        private final double[] ln;
        private final double[] season;

        /** {@code season} null or 12 factors; checks in the spec's order. */
        public CpiCurve(YearMonth baseMonth, double baseCpi, long[] years, double[] rates, double[] season) {
            if (years.length == 0) {
                throw new QfError("E_INPUT", "no quotes", "quotes");
            }
            for (int i = 0; i < years.length; i++) {
                if (years[i] < 1 || years[i] > 100 || (i > 0 && years[i] <= years[i - 1])) {
                    throw new QfError("E_INPUT", "years must be strictly increasing positive integers", "quotes");
                }
            }
            for (double r : rates) {
                if (!(r > -1.0)) {
                    throw new QfError("E_DOMAIN", "rate must be above -1", "quotes");
                }
            }
            if (season != null) {
                if (season.length != 12) {
                    throw new QfError("E_INPUT", "seasonality needs 12 factors", "seasonality");
                }
                for (double s : season) {
                    if (!(s > 0.0)) {
                        throw new QfError("E_DOMAIN", "seasonality factors must be positive", "seasonality");
                    }
                }
            }
            if (!(baseCpi > 0.0)) {
                throw new QfError("E_DOMAIN", "base_cpi must be positive", "base_cpi");
            }
            base = index(baseMonth);
            lnBase = Math.log(baseCpi);
            rawBase = baseCpi;
            k = new long[years.length];
            ln = new double[years.length];
            for (int i = 0; i < years.length; i++) {
                k[i] = base + 12 * years[i];
                ln[i] = lnBase + years[i] * Math.log1p(rates[i]);
            }
            this.season = season;
        }

        public double cpi(long m) {
            if (m < base) {
                throw new QfError("E_OUT_OF_RANGE", "month is before base_month");
            }
            double v;
            int n = k.length;
            long k0 = base;
            double l0 = lnBase;
            int i = 0;
            while (i < n - 1 && m > k[i]) {
                k0 = k[i];
                l0 = ln[i];
                i++;
            }
            v = l0 + (ln[i] - l0) * (m - k0) / (double) (k[i] - k0);
            double smooth = Math.exp(v);
            if (season == null) {
                return smooth;
            }
            return smooth * season[(int) (m % 12)] / season[(int) (base % 12)];
        }

        /** US TIPS reference CPI for a date. */
        public double ref(LocalDate d) {
            long m = index(YearMonth.from(d));
            double frac = (d.getDayOfMonth() - 1) / (double) d.lengthOfMonth();
            double a = cpi(m - 3);
            return a + frac * (cpi(m - 2) - a);
        }

        public double baseCpi() {
            return rawBase;
        }

        public long base() {
            return base;
        }
    }

    public record Zcis(double indexRatio, double pv) {}

    public static Zcis zcis(CpiCurve c, Curve d, long years, double k, double n, boolean receive, LocalDate pay) {
        Finite.check("k", k);
        Finite.check("n", n);
        if (years < 1 || years > 100) {
            throw new QfError("E_INPUT", "years must be a positive integer", "years");
        }
        double ratio = c.cpi(c.base() + 12 * years) / c.baseCpi();
        double pv = (receive ? 1.0 : -1.0) * n * (ratio - Math.pow(1.0 + k, years)) * d.discount(pay);
        return new Zcis(ratio, pv);
    }

    public record Linker(double refCpi, double ratio, double realClean, double realAccrued, double nominalClean,
                         double nominalAccrued) {}

    public static Linker linker(Bonds.Bond b, LocalDate settlement, double realYield, double baseRef,
                                Map<Long, Double> fixings) {
        Finite.check("realYield", realYield);
        Finite.check("baseRef", baseRef);
        Bonds.checkSettlement(b, settlement);
        if (!(baseRef > 0.0)) {
            throw new QfError("E_DOMAIN", "base_ref_cpi must be positive", "base_ref_cpi");
        }
        long m = index(YearMonth.from(settlement));
        Double a = fixings.get(m - 3);
        Double c = fixings.get(m - 2);
        if (a == null || c == null) {
            throw new QfError("E_INPUT", "a needed CPI fixing is missing", "cpi_fixings");
        }
        double ref = a + (settlement.getDayOfMonth() - 1) / (double) settlement.lengthOfMonth() * (c - a);
        double ratio = ref / baseRef;
        Bonds.YieldPrice y = Bonds.fromYield(b, settlement, realYield);
        return new Linker(ref, ratio, y.clean(), y.accrued(), y.clean() * ratio, y.accrued() * ratio);
    }

    public static double linkerCurve(Bonds.Bond b, LocalDate settlement, double baseRef, CpiCurve c, Curve d) {
        Finite.check("baseRef", baseRef);
        Bonds.checkSettlement(b, settlement);
        if (!(baseRef > 0.0)) {
            throw new QfError("E_DOMAIN", "base_ref_cpi must be positive", "base_ref_cpi");
        }
        List<LocalDate> a = b.around(settlement);
        double sum = 0.0;
        for (int i = 1; i < a.size(); i++) {
            double cf = b.amount() + (i == a.size() - 1 ? 100.0 : 0.0);
            sum += cf * c.ref(a.get(i)) / baseRef * d.discount(a.get(i));
        }
        return sum / d.discount(settlement);
    }
}
