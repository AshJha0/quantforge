package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.quantforge.core.Calendars;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Schedule;
import org.quantforge.vol.Black;

/** Caps, floors and swaptions on USD-TERM-3M (caps-and-swaptions.md, ruling D28). */
public final class CapSwaption {
    private CapSwaption() {}

    public static LocalDate start(Curve d, long months) {
        LocalDate spot = Calendars.addBusinessDays(Calendars.Id.USGS, d.asOf(), 2);
        return Calendars.adjust(Calendars.Id.USGS, spot.plusMonths(months), Calendars.Convention.MODIFIED_FOLLOWING);
    }

    public static double option(boolean normal, double phi, double f, double k, double t, double v) {
        Finite.check("phi", phi);
        Finite.check("f", f);
        Finite.check("k", k);
        Finite.check("t", t);
        Finite.check("v", v);
        return normal ? Black.normal(phi, f, k, t, 1.0, v) : Black.lognormal(phi, f, k, t, 1.0, v);
    }

    private static void checkMonths(long months, String key) {
        if (months < 1 || months > 1200) {
            throw new QfError("E_INPUT", key + " must be at least 1", key);
        }
    }

    public record Cap(double[] caplets, double price) {}

    /** The caplets of a cap: forward, accrual, payment discount factor and fixing time, per period. */
    public record Caplets(double[] forward, double[] alpha, double[] discount, double[] time) {
        public double price(int i, boolean normal, boolean isCap, double k, double n, double vol) {
            return n * alpha[i] * discount[i] * option(normal, isCap ? 1.0 : -1.0, forward[i], k, time[i], vol);
        }
    }

    /** Quarterly caplets from adjust(spot + start_months) over tenor_months (no fixing lag, ruling D28). */
    public static Caplets caplets(Curve d, Curve p, long startMonths, long tenorMonths) {
        LocalDate s = start(d, startMonths);
        List<Schedule.Period> periods = Schedule.generate(s, s.plusMonths(tenorMonths), 3, Calendars.Id.USGS, false, 0);
        int m = periods.size();
        double[] fwd = new double[m];
        double[] alpha = new double[m];
        double[] df = new double[m];
        double[] t = new double[m];
        for (int i = 0; i < m; i++) {
            Schedule.Period q = periods.get(i);
            alpha[i] = ChronoUnit.DAYS.between(q.start(), q.end()) / 360.0;
            fwd[i] = (p.discount(q.start()) / p.discount(q.end()) - 1.0) / alpha[i];
            df[i] = d.discount(q.end());
            t[i] = d.time(q.start());
        }
        return new Caplets(fwd, alpha, df, t);
    }

    /** {@code vols} has one entry (flat) or one per caplet. */
    public static Cap cap(Curve d, Curve p, boolean normal, double[] vols, boolean listed, boolean isCap,
                          long startMonths, long tenorMonths, double k, double n) {
        Finite.check("vols", vols);
        Finite.check("k", k);
        Finite.check("n", n);
        if (startMonths < 1) {
            throw new QfError("E_INPUT", "start_months must be at least 1", "start_months");
        }
        checkMonths(startMonths, "start_months");
        checkMonths(tenorMonths, "tenor_months");
        Caplets c = caplets(d, p, startMonths, tenorMonths);
        double[] fwd = c.forward();
        if (listed && vols.length != fwd.length) {
            throw new QfError("E_INPUT", "need one vol per caplet", "vol");
        }
        for (double v : vols) {
            if (!(v >= 0.0)) {
                throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
            }
        }
        checkBlack(normal, k, fwd);
        double[] out = new double[fwd.length];
        double sum = 0.0;
        for (int i = 0; i < out.length; i++) {
            out[i] = c.price(i, normal, isCap, k, n, listed ? vols[i] : vols[0]);
            sum += out[i];
        }
        return new Cap(out, sum);
    }

    public static void checkBlack(boolean normal, double k, double... fwd) {
        Finite.check("k", k);
        Finite.check("fwd", fwd);
        if (normal) {
            return;
        }
        if (!(k > 0.0)) {
            throw new QfError("E_DOMAIN", "BLACK_76 needs a positive strike", "strike");
        }
        for (double f : fwd) {
            if (!(f > 0.0)) {
                throw new QfError("E_DOMAIN", "BLACK_76 needs a positive forward");
            }
        }
    }

    public record Swaption(double price, double forward, double annuity) {}

    public static Swaption swaption(Curve d, Curve p, boolean normal, double vol, boolean payer, long expiryMonths,
                                    long tenorMonths, double k, double n) {
        Finite.check("vol", vol);
        Finite.check("k", k);
        Finite.check("n", n);
        if (expiryMonths < 1) {
            throw new QfError("E_INPUT", "expiry_months must be at least 1", "expiry_months");
        }
        checkMonths(expiryMonths, "expiry_months");
        checkMonths(tenorMonths, "tenor_months");
        if (!(vol >= 0.0)) {
            throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
        }
        double[] fa = forwardAnnuity(d, p, expiryMonths, tenorMonths);
        double f = fa[0];
        double a = fa[1];
        checkBlack(normal, k, f);
        double price = n * a * option(normal, payer ? 1.0 : -1.0, f, k, fa[2], vol);
        return new Swaption(price, f, a);
    }

    /** {forward swap rate, annuity, exercise time} of D7's swap starting adjust(spot + expiry_months). */
    public static double[] forwardAnnuity(Curve d, Curve p, long expiryMonths, long tenorMonths) {
        LocalDate s = start(d, expiryMonths);
        LocalDate end = s.plusMonths(tenorMonths);
        double a = 0.0;
        for (Schedule.Period q : Schedule.generate(s, end, 12, Calendars.Id.USGS, false, 0)) {
            a += org.quantforge.core.DayCount.yearFraction(org.quantforge.core.DayCount.Convention.THIRTY_360_BOND,
                    q.start(), q.end(), new org.quantforge.core.DayCount.Extras(null, null, null, null, null))
                    * d.discount(q.end());
        }
        double fl = 0.0;
        for (Schedule.Period q : Schedule.generate(s, end, 3, Calendars.Id.USGS, false, 0)) {
            fl += (p.discount(q.start()) / p.discount(q.end()) - 1.0) * d.discount(q.end());
        }
        return new double[] {fl / a, a, d.time(s)};
    }
}
