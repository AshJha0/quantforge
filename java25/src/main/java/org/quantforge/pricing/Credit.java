package org.quantforge.pricing;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** ISDA CDS, index CDS and composite curves (credit.md, rulings D19 to D21). */
public final class Credit {
    private Credit() {}

    /** Survival, -ln Q linear in time from Q(T) = 1, flat hazard after the last pillar. */
    public static final class Hazard {
        private final LocalDate t0;
        private final LocalDate[] dates;
        private final double[] lnQ;

        public Hazard(LocalDate t0, LocalDate[] dates, double[] survival) {
            this.t0 = t0;
            this.dates = dates;
            this.lnQ = new double[survival.length];
            LocalDate previous = t0;
            for (int i = 0; i < dates.length; i++) {
                if (!dates[i].isAfter(previous)) {
                    throw new QfError("E_INPUT", "hazard dates must increase from as_of", "hazard");
                }
                if (!(survival[i] > 0.0) || survival[i] > 1.0) {
                    throw new QfError("E_DOMAIN", "survival must be in (0, 1]", "hazard");
                }
                previous = dates[i];
                lnQ[i] = Math.log(survival[i]);
            }
            if (dates.length == 0) {
                throw new QfError("E_INPUT", "hazard has no pillars", "hazard");
            }
        }

        private Hazard(LocalDate t0, LocalDate[] dates, double[] lnQ, boolean raw) {
            this.t0 = t0;
            this.dates = dates;
            this.lnQ = lnQ;
        }

        double t(LocalDate d) {
            return ChronoUnit.DAYS.between(t0, d) / 365.0;
        }

        public double survival(LocalDate d) {
            double x = t(d);
            if (x <= 0.0) {
                return 1.0;
            }
            int n = dates.length;
            double tPrev = 0.0;
            double lPrev = 0.0;
            for (int i = 0; i < n; i++) {
                double ti = t(dates[i]);
                if (x <= ti) {
                    return Math.exp(lPrev + (lnQ[i] - lPrev) * (x - tPrev) / (ti - tPrev));
                }
                if (i < n - 1) {
                    tPrev = ti;
                    lPrev = lnQ[i];
                }
            }
            double tn = t(dates[n - 1]);
            double tp = n > 1 ? t(dates[n - 2]) : 0.0;
            double lp = n > 1 ? lnQ[n - 2] : 0.0;
            double h = -(lnQ[n - 1] - lp) / (tn - tp);
            return Math.exp(lnQ[n - 1] - h * (x - tn));
        }

        LocalDate[] dates() {
            return dates;
        }
    }

    static boolean weekend(LocalDate d) {
        return d.getDayOfWeek() == DayOfWeek.SATURDAY || d.getDayOfWeek() == DayOfWeek.SUNDAY;
    }

    static LocalDate nextWeekday(LocalDate d) {
        while (weekend(d)) {
            d = d.plusDays(1);
        }
        return d;
    }

    static LocalDate addWeekdays(LocalDate d, int n) {
        for (int i = 0; i < n; ) {
            d = d.plusDays(1);
            if (!weekend(d)) {
                i++;
            }
        }
        return d;
    }

    /** The roll date of credit.md for trade date {@code t}. */
    public static LocalDate roll(LocalDate t) {
        int y = t.getYear();
        if (!t.isBefore(LocalDate.of(y, 9, 20))) {
            return LocalDate.of(y, 12, 20);
        }
        if (!t.isBefore(LocalDate.of(y, 3, 20))) {
            return LocalDate.of(y, 6, 20);
        }
        return LocalDate.of(y - 1, 12, 20);
    }

    public static LocalDate maturity(LocalDate t, String tenor) {
        org.quantforge.curves.Ois.checkTenor(tenor);
        int n = Integer.parseInt(tenor.substring(0, tenor.length() - 1));
        char u = tenor.charAt(tenor.length() - 1);
        if (u != 'M' && u != 'Y') {
            throw new QfError("E_SCHEMA", "CDS tenors are in months or years", "tenor");
        }
        return roll(t).plusMonths(u == 'Y' ? 12L * n : n).withDayOfMonth(20);
    }

    private record Period(LocalDate start, LocalDate end, LocalDate pay, double alpha) {}

    private static List<Period> periods(LocalDate t, LocalDate maturity) {
        if (!maturity.isAfter(t)) {
            throw new QfError("E_DATE_ORDER", "maturity is not after the trade date", "maturity");
        }
        LocalDate d = LocalDate.of(t.getYear(), 12, 20);
        while (d.isAfter(t)) {
            d = d.minusMonths(3);
        }
        List<LocalDate> raw = new ArrayList<>();
        for (LocalDate x = d; x.isBefore(maturity); x = x.plusMonths(3)) {
            raw.add(x);
        }
        raw.add(maturity);
        List<Period> out = new ArrayList<>();
        for (int i = 1; i < raw.size(); i++) {
            boolean last = i == raw.size() - 1;
            LocalDate s = nextWeekday(raw.get(i - 1));
            if (s.equals(t)) {
                throw new QfError("E_INPUT", "trade date is on a coupon date (ruling D19)", "trade_date");
            }
            LocalDate e = last ? raw.get(i) : nextWeekday(raw.get(i));
            long days = ChronoUnit.DAYS.between(s, e) + (last ? 1 : 0);
            out.add(new Period(s, e, nextWeekday(raw.get(i)), days / 360.0));
        }
        if (nextWeekday(maturity).equals(t)) {
            throw new QfError("E_INPUT", "trade date is on a coupon date (ruling D19)", "trade_date");
        }
        return out;
    }

    public record Price(double protection, double rpv01, double accrued, double parSpread, double upfront, double pv) {}

    private static double tt(LocalDate t0, LocalDate d) {
        return ChronoUnit.DAYS.between(t0, d) / 365.0;
    }

    /** Nodes in (a, b) from both curves, with a and b. */
    private static List<LocalDate> nodes(LocalDate a, LocalDate b, Curve p, Hazard q) {
        TreeSet<LocalDate> set = new TreeSet<>();
        set.add(a);
        set.add(b);
        for (LocalDate d : p.dates()) {
            if (d.isAfter(a) && d.isBefore(b)) {
                set.add(d);
            }
        }
        for (LocalDate d : q.dates()) {
            if (d.isAfter(a) && d.isBefore(b)) {
                set.add(d);
            }
        }
        return new ArrayList<>(set);
    }

    public static Price price(LocalDate t, Curve p, Hazard q, double recovery, LocalDate maturity, double coupon,
                              double notional, boolean buyer, boolean digital) {
        if (!(recovery >= 0.0 && recovery < 1.0)) {
            throw new QfError("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
        }
        List<Period> periods = periods(t, maturity);
        double[] legs = legs(t, p, q, periods, maturity);
        double lgd = digital ? 1.0 : 1.0 - recovery;
        double protection = lgd * legs[0];
        double rpv01 = legs[1];
        double accrued = coupon * ChronoUnit.DAYS.between(periods.getFirst().start(), t.plusDays(1)) / 360.0;
        double pcs = p.discount(addWeekdays(t, 3));
        double par = protection / (rpv01 - legs[2] * pcs);
        double upfront = (protection - coupon * rpv01) / pcs + accrued;
        double pv = (buyer ? 1.0 : -1.0) * notional * (protection - coupon * rpv01 + accrued * pcs);
        return new Price(protection, rpv01, accrued, par, upfront, pv);
    }

    /** {protection per unit loss, rpv01, accrued per unit coupon}. */
    private static double[] legs(LocalDate t, Curve p, Hazard q, List<Period> periods, LocalDate maturity) {
        double prot = 0.0;
        List<LocalDate> n = nodes(t, maturity, p, q);
        for (int i = 1; i < n.size(); i++) {
            LocalDate a = n.get(i - 1);
            LocalDate b = n.get(i);
            double d = tt(t, b) - tt(t, a);
            double q0 = q.survival(a);
            double q1 = q.survival(b);
            double p0 = p.discount(a);
            double p1 = p.discount(b);
            double h = Math.log(q0 / q1) / d;
            double f = Math.log(p0 / p1) / d;
            double k = f + h;
            double ratio = k == 0.0 ? 1.0 : h / k;
            prot += Math.abs(k) < 1e-300 ? h * q0 * p0 * d : ratio * (q0 * p0 - q1 * p1);
        }
        double rpv01 = 0.0;
        for (Period per : periods) {
            LocalDate obs = per.pay().minusDays(1);
            rpv01 += per.alpha() * q.survival(obs) * p.discount(per.pay());
            LocalDate accStart = per.start().minusDays(1);
            LocalDate s = accStart.isAfter(t) ? accStart : t;
            double tacc = tt(t, accStart);
            double aod = 0.0;
            List<LocalDate> m = nodes(s, obs, p, q);
            for (int i = 1; i < m.size(); i++) {
                LocalDate a = m.get(i - 1);
                LocalDate b = m.get(i);
                double t0 = tt(t, a);
                double d = tt(t, b) - t0;
                double q0 = q.survival(a);
                double q1 = q.survival(b);
                double p0 = p.discount(a);
                double p1 = p.discount(b);
                double h = Math.log(q0 / q1) / d;
                double k = Math.log(p0 / p1) / d + h;
                double kd = k * d;
                double first;
                double second;
                if (Math.abs(kd) < 1e-4) {
                    // Taylor: (1 - e^{-x})/k = D(1 - x/2 + x^2/6 - x^3/24 + x^4/120),
                    // (1 - e^{-x}(1 + x))/k^2 = D^2(1/2 - x/3 + x^2/8 - x^3/30 + x^4/144).
                    first = d * (1 - kd / 2 + kd * kd / 6 - kd * kd * kd / 24 + kd * kd * kd * kd / 120);
                    second = d * d * (0.5 - kd / 3 + kd * kd / 8 - kd * kd * kd / 30 + kd * kd * kd * kd / 144);
                } else {
                    double e = Math.exp(-kd);
                    first = (1 - e) / k;
                    second = (1 - e * (1 + kd)) / (k * k);
                }
                aod += h * q0 * p0 * ((t0 - tacc) * first + second);
            }
            rpv01 += 365.0 / 360.0 * aod;
        }
        double accruedPerCoupon = ChronoUnit.DAYS.between(periods.getFirst().start(), t.plusDays(1)) / 360.0;
        return new double[] {prot, rpv01, accruedPerCoupon};
    }

    public static Hazard bootstrap(LocalDate t, Curve p, double recovery, String[] tenors, double[] spreads) {
        if (!(recovery >= 0.0 && recovery < 1.0)) {
            throw new QfError("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
        }
        if (tenors.length == 0) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        LocalDate[] mats = new LocalDate[tenors.length];
        for (int j = 0; j < mats.length; j++) {
            mats[j] = maturity(t, tenors[j]);
            if (j > 0 && !mats[j].isAfter(mats[j - 1])) {
                throw new QfError("E_INPUT", "maturities must increase", "quotes");
            }
        }
        for (double s : spreads) {
            if (!(s > 0.0)) {
                throw new QfError("E_DOMAIN", "spreads must be positive", "quotes");
            }
        }
        List<List<Period>> sched = new ArrayList<>();
        for (LocalDate m : mats) {
            sched.add(periods(t, m));
        }
        double[] lnQ = new double[mats.length];
        double pcs = p.discount(addWeekdays(t, 3));
        for (int j = 0; j < mats.length; j++) {
            int idx = j;
            LocalDate[] prefix = java.util.Arrays.copyOf(mats, j + 1);
            double[] logs = java.util.Arrays.copyOf(lnQ, j + 1);
            java.util.function.DoubleUnaryOperator g = v -> {
                logs[idx] = v;
                Hazard h = new Hazard(t, prefix, logs, true);
                double[] l = legs(t, p, h, sched.get(idx), mats[idx]);
                return (1.0 - recovery) * l[0] - spreads[idx] * (l[1] - l[2] * pcs);
            };
            double tPrev = j == 0 ? 0.0 : tt(t, mats[j - 1]);
            double guess = (j == 0 ? 0.0 : lnQ[j - 1]) - spreads[j] / (1.0 - recovery) * (tt(t, mats[j]) - tPrev);
            lnQ[j] = secant(g, guess, guess * 1.01 - 1e-4);
            if (!(Math.abs(g.applyAsDouble(lnQ[j])) < 1e-13)) {
                throw new QfError("E_NO_CONVERGENCE", "hazard bootstrap did not converge");
            }
            logs[j] = lnQ[j];
        }
        return new Hazard(t, mats, lnQ, true);
    }

    private static double secant(java.util.function.DoubleUnaryOperator g, double a, double b) {
        double ga = g.applyAsDouble(a);
        double gb = g.applyAsDouble(b);
        double best = Math.abs(ga) < Math.abs(gb) ? a : b;
        double bestError = Math.min(Math.abs(ga), Math.abs(gb));
        int stalled = 0;
        for (int i = 0; i < 80 && bestError > 1e-17 && stalled < 3 && gb != ga; i++) {
            double next = b - gb * (b - a) / (gb - ga);
            a = b;
            ga = gb;
            b = next;
            gb = g.applyAsDouble(b);
            if (Math.abs(gb) < bestError) {
                bestError = Math.abs(gb);
                best = b;
                stalled = 0;
            } else {
                stalled++;
            }
        }
        return best;
    }

    public static double[] survivals(Hazard h) {
        double[] s = new double[h.lnQ.length];
        for (int i = 0; i < s.length; i++) {
            s[i] = Math.exp(h.lnQ[i]);
        }
        return s;
    }

    public static LocalDate[] pillarDates(Hazard h) {
        return h.dates.clone();
    }
}
