package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Equity curves, index dividends, rebalancing, corporate actions and TRS (equity-curves.md, equity-index.md). */
public final class EquityCurves {
    private EquityCurves() {}

    public record Div(LocalDate exDate, double amount) {}

    /** Carry discount C = D exp(b t) exp(-s t). */
    private static double carry(Curve f, LocalDate d, double b, double s) {
        double t = f.time(d);
        return f.discount(d) * Math.exp((b - s) * t);
    }

    public static double forward(double spot, Curve f, double b, double s, List<Div> divs, LocalDate expiry) {
        Finite.check("spot", spot);
        Finite.check("b", b);
        Finite.check("s", s);
        double sum = 0.0;
        for (Div d : divs) {
            if (d.exDate().isAfter(f.asOf()) && !d.exDate().isAfter(expiry)) {
                sum += d.amount() * carry(f, d.exDate(), b, s);
            }
        }
        return (spot - sum) / carry(f, expiry, b, s);
    }

    public record Implied(double[] pv, double[] period, double[] yields) {}

    public static Implied impliedDividends(double spot, Curve f, double b, LocalDate[] expiries, double[] prices) {
        Finite.check("spot", spot);
        Finite.check("b", b);
        Finite.check("prices", prices);
        if (expiries.length == 0) {
            throw new QfError("E_INPUT", "no futures", "futures");
        }
        LocalDate previous = f.asOf();
        for (LocalDate e : expiries) {
            if (!e.isAfter(previous)) {
                throw new QfError("E_INPUT", "expiries must increase from as_of", "futures");
            }
            previous = e;
        }
        if (!(spot > 0.0)) {
            throw new QfError("E_DOMAIN", "spot must be positive", "spot");
        }
        for (double p : prices) {
            if (!(p > 0.0)) {
                throw new QfError("E_DOMAIN", "prices must be positive", "futures");
            }
        }
        int n = expiries.length;
        double[] x = new double[n];
        double[] per = new double[n];
        double[] q = new double[n];
        for (int i = 0; i < n; i++) {
            double fc = prices[i] * carry(f, expiries[i], b, 0.0);
            x[i] = spot - fc;
            per[i] = i == 0 ? x[i] : x[i] - x[i - 1];
            q[i] = -Math.log(fc / spot) / f.time(expiries[i]);
        }
        return new Implied(x, per, q);
    }

    /** Root in [-0.5, 0.5] of a monotone function; E_NOT_BRACKETED when the ends share a sign. */
    private static double bracketed(DoubleUnaryOperator g) {
        double lo = g.applyAsDouble(-0.5);
        double hi = g.applyAsDouble(0.5);
        if (Double.isNaN(lo) || Double.isNaN(hi) || Math.signum(lo) == Math.signum(hi) && lo != 0.0) {
            throw new QfError("E_NOT_BRACKETED", "no solution in [-0.5, 0.5]");
        }
        DoubleUnaryOperator dec = lo > 0 || hi < 0 ? g : v -> -g.applyAsDouble(v);
        return Bonds.solveDecreasing(dec, 0.0, -0.5, 0.5);
    }

    public static double impliedBorrow(double spot, Curve f, List<Div> divs, LocalDate expiry, double forward) {
        Finite.check("spot", spot);
        Finite.check("forward", forward);
        if (!expiry.isAfter(f.asOf())) {
            throw new QfError("E_DATE_ORDER", "expiry is not after as_of", "expiry");
        }
        return bracketed(b -> forward(spot, f, b, 0.0, divs, expiry) - forward);
    }

    public record Basis(double fair, double basis, double impliedSpread) {}

    public static Basis futuresBasis(double spot, Curve f, double b, double s, List<Div> divs, LocalDate expiry,
                                     double price) {
        Finite.check("spot", spot);
        Finite.check("b", b);
        Finite.check("s", s);
        Finite.check("price", price);
        if (!expiry.isAfter(f.asOf())) {
            throw new QfError("E_DATE_ORDER", "expiry is not after as_of", "expiry");
        }
        double fair = forward(spot, f, b, s, divs, expiry);
        double implied = bracketed(x -> forward(spot, f, b, x, divs, expiry) - price);
        return new Basis(fair, price - fair, implied);
    }

    public record Constituent(String id, double shares, double price, List<Div> dividends) {}

    public record IndexDivs(double level, List<LocalDate> exDates, double[] points, double[] periodPoints,
                            double[] basis) {}

    public static IndexDivs indexDividends(double divisor, List<Constituent> cs, LocalDate[] starts, LocalDate[] ends,
                                           double[] implied) {
        Finite.check("divisor", divisor);
        Finite.check("implied", implied);
        if (!(divisor > 0.0)) {
            throw new QfError("E_DOMAIN", "divisor must be positive", "divisor");
        }
        for (int i = 0; i < starts.length; i++) {
            if (ends[i].isBefore(starts[i])) {
                throw new QfError("E_DATE_ORDER", "period end before start", "periods");
            }
        }
        if (starts.length != implied.length) {
            throw new QfError("E_INPUT", "periods and implied_period_points differ in length", "periods");
        }
        double level = 0.0;
        TreeMap<LocalDate, Double> pts = new TreeMap<>();
        for (Constituent c : cs) {
            level += c.shares() * c.price();
            for (Div d : c.dividends()) {
                pts.merge(d.exDate(), c.shares() * d.amount(), Double::sum);
            }
        }
        List<LocalDate> dates = new ArrayList<>(pts.keySet());
        double[] points = new double[dates.size()];
        for (int i = 0; i < points.length; i++) {
            points[i] = pts.get(dates.get(i)) / divisor;
        }
        double[] period = new double[starts.length];
        double[] basis = new double[starts.length];
        for (int k = 0; k < starts.length; k++) {
            double sum = 0.0;
            for (int i = 0; i < points.length; i++) {
                if (!dates.get(i).isBefore(starts[k]) && !dates.get(i).isAfter(ends[k])) {
                    sum += pts.get(dates.get(i));
                }
            }
            period[k] = sum / divisor;
            basis[k] = implied[k] - period[k];
        }
        return new IndexDivs(level / divisor, dates, points, period, basis);
    }

    public record Rebalance(double level, double newDivisor, double[] weights) {}

    private static void unique(List<Constituent> cs, String key) {
        Set<String> ids = new HashSet<>();
        for (Constituent c : cs) {
            if (!ids.add(c.id())) {
                throw new QfError("E_INPUT", "duplicate id " + c.id(), key);
            }
        }
    }

    public static Rebalance rebalance(double divisor, List<Constituent> old, List<Constituent> neu) {
        Finite.check("divisor", divisor);
        unique(old, "constituents");
        unique(neu, "new_constituents");
        if (!(divisor > 0.0)) {
            throw new QfError("E_DOMAIN", "divisor must be positive", "divisor");
        }
        double cap = 0.0;
        for (Constituent c : old) {
            cap += c.shares() * c.price();
        }
        double level = cap / divisor;
        double newCap = 0.0;
        for (Constituent c : neu) {
            newCap += c.shares() * c.price();
        }
        double[] w = new double[neu.size()];
        for (int i = 0; i < w.length; i++) {
            w[i] = neu.get(i).shares() * neu.get(i).price() / newCap;
        }
        return new Rebalance(level, newCap / level, w);
    }

    public record Action(double factor, double exPrice, double shares, double strike) {}

    public static Action corporateAction(String action, double p, double shares, double strike, Double ratio,
                                         Double m, Double k, Double amount) {
        Finite.check("p", p);
        Finite.check("shares", shares);
        Finite.check("strike", strike);
        double f;
        switch (action) {
            case "SPLIT", "REVERSE_SPLIT" -> {
                if (!(ratio > 0.0)) {
                    throw new QfError("E_DOMAIN", "ratio must be positive", "ratio");
                }
                f = 1.0 / ratio;
            }
            case "RIGHTS" -> {
                if (!(m > 0.0) || !(k > 0.0)) {
                    throw new QfError("E_DOMAIN", "new_per_old and subscription_price must be positive");
                }
                f = (p + m * k) / (1.0 + m) / p;
            }
            case "SPECIAL_DIVIDEND" -> {
                if (!(amount > 0.0) || !(amount < p)) {
                    throw new QfError("E_DOMAIN", "amount must be in (0, cum_price)", "amount");
                }
                f = (p - amount) / p;
            }
            default -> throw new QfError("E_SCHEMA", "unknown action", "action");
        }
        return new Action(f, f * p, shares / f, f * strike);
    }

    public record Trs(double equityLeg, double fundingLeg, double pv) {}

    public static Trs trs(double spot, Curve f, double b, List<Div> divs, LocalDate start, LocalDate end, double s0,
                          double n, double spread, boolean receiveEquity, Double current) {
        Finite.check("spot", spot);
        Finite.check("b", b);
        Finite.check("s0", s0);
        Finite.check("n", n);
        Finite.check("spread", spread);
        if (!end.isAfter(start)) {
            throw new QfError("E_DATE_ORDER", "end is not after start", "end");
        }
        if (start.isBefore(f.asOf()) && current == null) {
            throw new QfError("E_INPUT", "current_rate is needed once the period has started", "current_rate");
        }
        double dEnd = f.discount(end);
        double divSum = 0.0;
        for (Div d : divs) {
            if (d.exDate().isAfter(f.asOf()) && !d.exDate().isAfter(end)) {
                divSum += d.amount();
            }
        }
        double equity = n * dEnd * (forward(spot, f, b, 0.0, divs, end) + divSum - s0);
        double alpha = ChronoUnit.DAYS.between(start, end) / 360.0;
        double r = current != null ? current : (f.discount(start) / dEnd - 1.0) / alpha;
        double funding = n * s0 * (r + spread) * alpha * dEnd;
        return new Trs(equity, funding, (receiveEquity ? 1.0 : -1.0) * (equity - funding));
    }
}
