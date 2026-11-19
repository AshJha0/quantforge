package org.quantforge.execution;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import org.quantforge.core.QfError;
import org.quantforge.micro.MicroEstimators;

/**
 * Venue analytics: markouts, fill rates, toxicity ({@code specifications/10-execution/venue-analytics.md}, stage H
 * H-16; rulings HR-72, HR-75 as amended (HR-66)). Each input number is read as the decimal it prints as (shortest round trip) and every
 * sum, and the sign test of the toxicity indicator, is exact on those decimals ({@link BigDecimal}); each output is
 * rounded once to binary64 (the spec's "Exact sums" paragraph). A port of the Python build's
 * {@code venue_analytics.py}.
 */
public final class VenueAnalytics {
    private VenueAnalytics() {}

    /** A fill; {@code buy} false is a sell. */
    public record Fill(String venue, boolean buy, double quantity, double price, double t) {}

    /** Child orders sent to a venue and the quantity filled. */
    public record Order(String venue, double sent, double filled) {}

    /** One row of the markout table. */
    public record Markout(String venue, double h, double markout, double markoutBps, double toxicity) {}

    /** Fill rates by venue (code-point order) and the markout rows. */
    public record Result(Map<String, Double> fillRates, List<Markout> markouts) {}

    private static QfError fail(String code, String message, String field) {
        return new QfError(code, message, field);
    }

    /** The decimal a double prints as (shortest round trip, as Python's {@code repr}). */
    static BigDecimal dec(double x) {
        return new BigDecimal(Double.toString(x));
    }

    /** a / b correctly rounded to binary64 (b non-zero), as Python's {@code float(Fraction)}. */
    static double ratio(BigDecimal a, BigDecimal b) {
        BigInteger p = a.unscaledValue();
        BigInteger q = b.unscaledValue();
        int s = b.scale() - a.scale();
        if (s > 0) {
            p = p.multiply(BigInteger.TEN.pow(s));
        } else if (s < 0) {
            q = q.multiply(BigInteger.TEN.pow(-s));
        }
        return ratio(p, q);
    }

    static double ratio(BigInteger p, BigInteger q) {
        if (p.signum() == 0) {
            return 0.0;
        }
        int sign = p.signum() * q.signum();
        p = p.abs();
        q = q.abs();
        int shift = 55 - (p.bitLength() - q.bitLength());
        BigInteger n = shift >= 0 ? p.shiftLeft(shift) : p;
        BigInteger d = shift >= 0 ? q : q.shiftLeft(-shift);
        BigInteger[] qr = n.divideAndRemainder(d);
        long m = qr[0].longValueExact(); // 55 or 56 bits
        if (qr[1].signum() != 0) {
            m |= 1L; // sticky bit: the one rounding to 53 bits below is then correct
        }
        return sign * Math.scalb((double) m, -shift);
    }

    private static void finite(String field, double... v) {
        for (double a : v) {
            if (!Double.isFinite(a)) {
                throw fail("E_DOMAIN", field + " must be finite", field);
            }
        }
    }

    /**
     * {@code exec.venue.analytics}: per venue and horizon, markout, markout_bps and toxicity; per venue fill_rate. The
     * mid at u is the last mid stamped at or before u (HR-72). {@code mids} rows are (t, mid).
     */
    public static Result analytics(double[][] mids, List<Fill> fills, List<Order> orders, double[] horizons) {
        for (double[] m : mids) {
            finite("mids", m);
        }
        for (Fill f : fills) {
            finite("fills", f.quantity(), f.price(), f.t());
        }
        for (Order o : orders) {
            finite("orders", o.sent(), o.filled());
        }
        finite("horizons", horizons);
        // HR-75 as amended (HR-66): structural E_INPUT first, then E_DOMAIN, then the mid lookups
        for (Order o : orders) {
            if (o.filled() > o.sent()) {
                throw fail("E_INPUT", "filled exceeds sent", "orders");
            }
        }
        BigDecimal[] times = new BigDecimal[mids.length];
        for (int i = 0; i < mids.length; i++) {
            times[i] = dec(mids[i][0]);
            if (i > 0 && times[i].compareTo(times[i - 1]) <= 0) {
                throw fail("E_INPUT", "mid times must be strictly increasing", "mids");
            }
        }
        for (double[] m : mids) {
            if (m[1] <= 0) {
                throw fail("E_DOMAIN", "mids must be positive", "mids");
            }
        }
        for (Fill f : fills) {
            if (f.price() <= 0) {
                throw fail("E_DOMAIN", "fill prices must be positive", "fills");
            }
        }
        for (Fill f : fills) {
            if (f.quantity() <= 0) {
                throw fail("E_DOMAIN", "fill quantities must be positive", "fills");
            }
        }
        for (Order o : orders) {
            if (o.sent() <= 0) {
                throw fail("E_DOMAIN", "sent must be positive", "orders");
            }
        }
        for (Order o : orders) {
            if (o.filled() < 0) {
                throw fail("E_DOMAIN", "filled must be non-negative", "orders");
            }
        }
        for (double h : horizons) {
            if (h < 0) {
                throw fail("E_DOMAIN", "horizons must be non-negative", "horizons");
            }
        }
        BigDecimal[] values = new BigDecimal[mids.length];
        for (int i = 0; i < mids.length; i++) {
            values[i] = dec(mids[i][1]);
        }
        BigDecimal[] hs = new BigDecimal[horizons.length];
        for (int i = 0; i < horizons.length; i++) {
            hs[i] = dec(horizons[i]);
        }
        TreeSet<String> venues = new TreeSet<>(MicroEstimators.CODE_POINT);
        fills.forEach(f -> venues.add(f.venue()));
        List<Markout> markouts = new ArrayList<>();
        for (String venue : venues) {
            List<BigDecimal[]> mine = new ArrayList<>(); // side, q, p, t
            BigDecimal sq = BigDecimal.ZERO;
            BigDecimal sqp = BigDecimal.ZERO;
            for (Fill f : fills) {
                if (f.venue().equals(venue)) {
                    BigDecimal q = dec(f.quantity());
                    BigDecimal p = dec(f.price());
                    mine.add(new BigDecimal[] {f.buy() ? BigDecimal.ONE : BigDecimal.ONE.negate(), q, p, dec(f.t())});
                    sq = sq.add(q);
                    sqp = sqp.add(q.multiply(p));
                }
            }
            for (int k = 0; k < horizons.length; k++) {
                BigDecimal num = BigDecimal.ZERO;
                BigDecimal toxic = BigDecimal.ZERO;
                for (BigDecimal[] e : mine) {
                    BigDecimal move = e[0].multiply(midAt(times, values, e[3].add(hs[k])).subtract(e[2]));
                    num = num.add(e[1].multiply(move));
                    if (move.signum() < 0) {
                        toxic = toxic.add(e[1]);
                    }
                }
                markouts.add(new Markout(venue, horizons[k], ratio(num, sq),
                        ratio(num.multiply(BigDecimal.valueOf(10_000)), sqp), ratio(toxic, sq)));
            }
        }
        TreeSet<String> orderVenues = new TreeSet<>(MicroEstimators.CODE_POINT);
        orders.forEach(o -> orderVenues.add(o.venue()));
        Map<String, Double> rates = new LinkedHashMap<>();
        for (String venue : orderVenues) {
            BigDecimal sent = BigDecimal.ZERO;
            BigDecimal got = BigDecimal.ZERO;
            for (Order o : orders) {
                if (o.venue().equals(venue)) {
                    sent = sent.add(dec(o.sent()));
                    got = got.add(dec(o.filled()));
                }
            }
            rates.put(venue, ratio(got, sent));
        }
        return new Result(rates, markouts);
    }

    /** The last mid stamped at or before u. */
    private static BigDecimal midAt(BigDecimal[] times, BigDecimal[] values, BigDecimal u) {
        int lo = 0;
        int hi = times.length;
        while (lo < hi) { // bisect_right
            int mid = (lo + hi) >>> 1;
            if (u.compareTo(times[mid]) < 0) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        if (lo == 0) {
            throw fail("E_INPUT", "no mid at or before a fill time plus horizon", "fills");
        }
        return values[lo - 1];
    }
}
