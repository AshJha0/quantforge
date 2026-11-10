package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Equity forward (equity-forward.md). Dividends are carried on C = D/B, never discounted on D. */
public final class EquityForward {
    private EquityForward() {}

    public record Dividend(LocalDate exDate, double amount) {}

    public record Result(double forward, double discountFactor, double carryFactor, double pvDividends) {}

    public record Quote(double strike, double callBid, double callAsk, double putBid, double putAsk) {}

    public record Parity(double forward, double discountFactor, double maxResidual, List<Object> outsideSpread) {}

    private static QfError domain(String why) {
        return new QfError("E_DOMAIN", why);
    }

    private static double carry(Curve funding, Curve borrow, LocalDate d) {
        return borrow == null ? funding.discount(d) : funding.discount(d) / borrow.discount(d);
    }

    /** Curves are built by the caller, after the spot check. */
    public static Result outright(double spot, LocalDate asOf, LocalDate expiry, Curve funding, Curve borrow,
                                  List<Dividend> dividends) {
        Finite.check("spot", spot);
        if (!funding.asOf().equals(asOf) || (borrow != null && !borrow.asOf().equals(asOf))) {
            throw new QfError("E_INPUT", "curve as_of differs");
        }
        if (expiry.isBefore(asOf)) {
            throw new QfError("E_DATE_ORDER", "expiry is before as_of");
        }
        for (Dividend d : dividends) {
            if (d.amount() < 0.0) {
                throw domain("negative dividend");
            }
        }
        for (int i = 1; i < dividends.size(); i++) {
            if (!dividends.get(i).exDate().isAfter(dividends.get(i - 1).exDate())) {
                throw new QfError("E_INPUT", "ex_dates must increase");
            }
        }
        double c = carry(funding, borrow, expiry);
        double pv = 0.0;
        for (Dividend d : dividends) {
            if (d.exDate().isAfter(asOf) && !d.exDate().isAfter(expiry)) {
                pv += d.amount() * carry(funding, borrow, d.exDate());
            }
        }
        double f = spot / c - pv / c;
        if (f <= 0.0) {
            throw domain("forward is not positive");
        }
        return new Result(f, funding.discount(expiry), c, pv);
    }

    public static double flat(double spot, double rate, double borrow, double expiry, double[] times, double[] amounts) {
        Finite.check("spot", spot);
        Finite.check("rate", rate);
        Finite.check("borrow", borrow);
        Finite.check("expiry", expiry);
        Finite.check("times", times);
        Finite.check("amounts", amounts);
        if (spot <= 0.0 || expiry < 0.0) {
            throw domain("spot or expiry_years");
        }
        for (double a : amounts) {
            if (a < 0.0) {
                throw domain("negative dividend");
            }
        }
        for (int i = 1; i < times.length; i++) {
            if (times[i] <= times[i - 1]) {
                throw new QfError("E_INPUT", "time_years must increase");
            }
        }
        double g = rate - borrow;
        double f = spot * Math.exp(g * expiry);
        for (int i = 0; i < times.length; i++) {
            if (times[i] > 0.0 && times[i] <= expiry) {
                f -= amounts[i] * Math.exp(g * (expiry - times[i]));
            }
        }
        if (f <= 0.0) {
            throw domain("forward is not positive");
        }
        return f;
    }

    public static Parity parity(List<Quote> quotes, Double givenD) {
        int n = quotes.size();
        if (n == 0) {
            throw new QfError("E_INPUT", "no quotes");
        }
        for (Quote q : quotes) {
            if (q.strike() <= 0.0 || q.callBid() < 0.0 || q.callAsk() < 0.0 || q.putBid() < 0.0 || q.putAsk() < 0.0) {
                throw domain("strike or quote");
            }
        }
        if (givenD != null && givenD <= 0.0) {
            throw domain("discount_factor");
        }
        for (int i = 0; i < n; i++) {
            Quote q = quotes.get(i);
            if ((i > 0 && q.strike() <= quotes.get(i - 1).strike()) || q.callBid() > q.callAsk() || q.putBid() > q.putAsk()) {
                throw new QfError("E_INPUT", "strike order or crossed quote");
            }
        }
        if (givenD == null && n == 1) {
            throw new QfError("E_INPUT", "one quote cannot fix the discount factor");
        }
        double[] y = new double[n];
        double[] k = new double[n];
        for (int i = 0; i < n; i++) {
            Quote q = quotes.get(i);
            k[i] = q.strike();
            y[i] = (q.callBid() + q.callAsk()) / 2.0 - (q.putBid() + q.putAsk()) / 2.0;
        }
        double d;
        double f;
        if (givenD != null) {
            d = givenD;
            double sum = 0.0;
            for (int i = 0; i < n; i++) {
                sum += k[i] + y[i] / d;
            }
            f = sum / n;
        } else {
            double mk = 0.0;
            double my = 0.0;
            for (int i = 0; i < n; i++) {
                mk += k[i] / n;
                my += y[i] / n;
            }
            double sxy = 0.0;
            double sxx = 0.0;
            for (int i = 0; i < n; i++) {
                sxy += (k[i] - mk) * (y[i] - my);
                sxx += (k[i] - mk) * (k[i] - mk);
            }
            double s = sxy / sxx;
            d = -s;
            if (d <= 0.0) {
                throw domain("fitted discount factor");
            }
            f = (my - s * mk) / d;
        }
        if (f <= 0.0) {
            throw domain("fitted forward");
        }
        double max = 0.0;
        List<Object> outside = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            Quote q = quotes.get(i);
            double model = d * (f - k[i]);
            max = Math.max(max, Math.abs(y[i] - model));
            if (model < q.callBid() - q.putAsk() || model > q.callAsk() - q.putBid()) {
                outside.add(k[i]);
            }
        }
        return new Parity(f, d, max, outside);
    }
}
