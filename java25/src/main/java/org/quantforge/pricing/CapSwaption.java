package org.quantforge.pricing;

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

    private static LocalDate start(Curve d, long months) {
        LocalDate spot = Calendars.addBusinessDays(Calendars.Id.USGS, d.asOf(), 2);
        return Calendars.adjust(Calendars.Id.USGS, spot.plusMonths(months), Calendars.Convention.MODIFIED_FOLLOWING);
    }

    private static double option(boolean normal, double phi, double f, double k, double t, double v) {
        return normal ? Black.normal(phi, f, k, t, 1.0, v) : Black.lognormal(phi, f, k, t, 1.0, v);
    }

    private static void checkMonths(long months, String key) {
        if (months < 1 || months > 1200) {
            throw new QfError("E_INPUT", key + " must be at least 1", key);
        }
    }

    public record Cap(double[] caplets, double price) {}

    /** {@code vols} has one entry (flat) or one per caplet. */
    public static Cap cap(Curve d, Curve p, boolean normal, double[] vols, boolean listed, boolean isCap,
                          long startMonths, long tenorMonths, double k, double n) {
        if (startMonths < 1) {
            throw new QfError("E_INPUT", "start_months must be at least 1", "start_months");
        }
        checkMonths(startMonths, "start_months");
        checkMonths(tenorMonths, "tenor_months");
        LocalDate s = start(d, startMonths);
        List<Schedule.Period> periods = Schedule.generate(s, s.plusMonths(tenorMonths), 3, Calendars.Id.USGS, false, 0);
        if (listed && vols.length != periods.size()) {
            throw new QfError("E_INPUT", "need one vol per caplet", "vol");
        }
        for (double v : vols) {
            if (!(v >= 0.0)) {
                throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
            }
        }
        double[] fwd = new double[periods.size()];
        double[] alpha = new double[fwd.length];
        for (int i = 0; i < fwd.length; i++) {
            Schedule.Period q = periods.get(i);
            alpha[i] = ChronoUnit.DAYS.between(q.start(), q.end()) / 360.0;
            fwd[i] = (p.discount(q.start()) / p.discount(q.end()) - 1.0) / alpha[i];
        }
        checkBlack(normal, k, fwd);
        double[] out = new double[fwd.length];
        double sum = 0.0;
        for (int i = 0; i < out.length; i++) {
            Schedule.Period q = periods.get(i);
            double t = d.time(q.start());
            double v = listed ? vols[i] : vols[0];
            out[i] = n * alpha[i] * d.discount(q.end()) * option(normal, isCap ? 1.0 : -1.0, fwd[i], k, t, v);
            sum += out[i];
        }
        return new Cap(out, sum);
    }

    private static void checkBlack(boolean normal, double k, double... fwd) {
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
        if (expiryMonths < 1) {
            throw new QfError("E_INPUT", "expiry_months must be at least 1", "expiry_months");
        }
        checkMonths(expiryMonths, "expiry_months");
        checkMonths(tenorMonths, "tenor_months");
        if (!(vol >= 0.0)) {
            throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
        }
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
        double f = fl / a;
        checkBlack(normal, k, f);
        double price = n * a * option(normal, payer ? 1.0 : -1.0, f, k, d.time(s), vol);
        return new Swaption(price, f, a);
    }
}
