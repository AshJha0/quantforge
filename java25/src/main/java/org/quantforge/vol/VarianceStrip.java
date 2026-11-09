package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.quantforge.core.QfError;

/** Variance swaps by DDKZ replication, realized variance, and the VIX-style index (variance-swaps.md,
 * vix-index.md, rulings E-B3 to E-B6). */
public final class VarianceStrip {
    private VarianceStrip() {}

    public static final double MINUTES_30D = 43200.0;
    public static final double MINUTES_YEAR = 525600.0;

    /** Weights of the DDKZ walk: strikes in walk order plus one extension strike, which gets no weight. */
    static double[] weights(double[] walk, double s0, double t) {
        double[] w = new double[walk.length - 1];
        double prev = 0.0;
        for (int j = 0; j < w.length; j++) {
            double s = Math.abs(f(walk[j + 1], s0, t) - f(walk[j], s0, t)) / Math.abs(walk[j + 1] - walk[j]);
            w[j] = s - prev;
            prev = s;
        }
        return w;
    }

    private static double f(double k, double s0, double t) {
        return 2.0 / t * ((k - s0) / s0 - Math.log(k / s0));
    }

    public interface VolOf {
        double vol(double strike);
    }

    /** Fair variance with the drift term that keeps q (ruling E-B3). Strike lists are checked by the caller. */
    public static double fairVariance(double s0, double r, double q, double t, double[] puts, double[] calls,
                                      VolOf vols, double dk) {
        Finite.check("s0", s0);
        Finite.check("r", r);
        Finite.check("q", q);
        Finite.check("t", t);
        Finite.check("puts", puts);
        Finite.check("calls", calls);
        Finite.check("dk", dk);
        double d = Math.exp(-r * t);
        double fwd = s0 * Math.exp((r - q) * t);
        double[] up = calls.clone();
        Arrays.sort(up);
        double[] callWalk = Arrays.copyOf(up, up.length + 1);
        callWalk[up.length] = up[up.length - 1] + dk;
        double[] down = puts.clone();
        Arrays.sort(down);
        double[] putWalk = new double[down.length + 1];
        for (int i = 0; i < down.length; i++) {
            putWalk[i] = down[down.length - 1 - i];
        }
        putWalk[down.length] = down[0] - dk;
        double pi = 0.0;
        double[] wc = weights(callWalk, s0, t);
        for (int j = 0; j < wc.length; j++) {
            pi += wc[j] * Black.lognormal(1.0, fwd, callWalk[j], t, d, vols.vol(callWalk[j]));
        }
        double[] wp = weights(putWalk, s0, t);
        for (int j = 0; j < wp.length; j++) {
            pi += wp[j] * Black.lognormal(-1.0, fwd, putWalk[j], t, d, vols.vol(putWalk[j]));
        }
        return 2.0 / t * ((r - q) * t - (fwd / s0 - 1.0)) + pi / d;
    }

    /** (A/m) sum ln(p_i/p_{i-1})^2: no mean, divisor m (ruling E-B4). */
    public static double realizedVariance(double[] p, double periodsPerYear) {
        Finite.check("p", p);
        Finite.check("periodsPerYear", periodsPerYear);
        int m = p.length - 1;
        double s = 0.0;
        for (int i = 1; i <= m; i++) {
            double x = Math.log(p[i] / p[i - 1]);
            s += x * x;
        }
        return periodsPerYear / m * s;
    }

    /** A strike's quotes. A {@code null} quote (ruling F-15) is NaN here; the CLI maps JSON null to it. */
    public record Quote(double strike, double callBid, double callAsk, double putBid, double putAsk) {
        boolean callNull() {
            return Double.isNaN(callBid) || Double.isNaN(callAsk);
        }

        boolean putNull() {
            return Double.isNaN(putBid) || Double.isNaN(putAsk);
        }

        double callMid() {
            return (callBid + callAsk) / 2.0;
        }

        double putMid() {
            return (putBid + putAsk) / 2.0;
        }
    }

    public record Term(double forward, double k0, double variance, double[] strikesUsed, double years) {}

    /** One term of the VIX method, checks in the order of vix-index.md. */
    public static Term term(long minutes, double rate, List<Quote> strip) {
        Finite.check("rate", rate);
        if (minutes < 1) {
            throw new QfError("E_INPUT", "minutes_to_expiry must be at least 1", "minutes_to_expiry");
        }
        List<Quote> q = new ArrayList<>(strip);
        q.sort((a, b) -> Double.compare(a.strike(), b.strike()));
        if (q.size() < 3) {
            throw new QfError("E_INPUT", "need at least 3 strikes", "strip");
        }
        for (int i = 1; i < q.size(); i++) {
            if (q.get(i).strike() == q.get(i - 1).strike()) {
                throw new QfError("E_INPUT", "repeated strike", "strip");
            }
        }
        for (Quote x : q) {
            if (x.callBid() > x.callAsk() || x.putBid() > x.putAsk()) {
                throw new QfError("E_INPUT", "a bid is above its ask", "strip");
            }
        }
        for (Quote x : q) {
            if (x.callBid() < 0.0 || x.callAsk() < 0.0 || x.putBid() < 0.0 || x.putAsk() < 0.0) {
                throw new QfError("E_DOMAIN", "a quote is negative", "strip");
            }
        }
        double t = minutes / MINUTES_YEAR;
        double growth = Math.exp(rate * t);
        Quote star = null;
        for (Quote x : q) {
            if (x.callNull() || x.putNull()) {
                continue; // ruling F-15: only strikes with both sides quoted are candidates
            }
            if (star == null || Math.abs(x.callMid() - x.putMid()) < Math.abs(star.callMid() - star.putMid())) {
                star = x;
            }
        }
        if (star == null) {
            throw new QfError("E_INPUT", "no strike has both a call and a put quote", "strip");
        }
        double fwd = star.strike() + growth * (star.callMid() - star.putMid());
        int i0 = -1;
        for (int i = 0; i < q.size(); i++) {
            if (q.get(i).strike() <= fwd) {
                i0 = i;
            }
        }
        if (i0 < 0) {
            throw new QfError("E_INPUT", "no strike at or below the forward", "strip");
        }
        if (q.get(i0).callNull() || q.get(i0).putNull()) {
            throw new QfError("E_INPUT", "the K0 call or put has a null quote", "strip");
        }
        List<double[]> chosen = new ArrayList<>(); // {strike, Q}
        int zeros = 0;
        for (int i = i0 - 1; i >= 0; i--) {
            Quote x = q.get(i);
            if (x.putNull()) {
                continue; // removed from the put walk before it starts
            }
            if (x.putBid() == 0.0) {
                if (++zeros >= 2) {
                    break;
                }
                continue;
            }
            zeros = 0;
            chosen.addFirst(new double[] {x.strike(), x.putMid()});
        }
        Quote atm = q.get(i0);
        chosen.add(new double[] {atm.strike(), (atm.callMid() + atm.putMid()) / 2.0});
        zeros = 0;
        for (int i = i0 + 1; i < q.size(); i++) {
            Quote x = q.get(i);
            if (x.callNull()) {
                continue;
            }
            if (x.callBid() == 0.0) {
                if (++zeros >= 2) {
                    break;
                }
                continue;
            }
            zeros = 0;
            chosen.add(new double[] {x.strike(), x.callMid()});
        }
        int n = chosen.size();
        if (chosen.getFirst()[0] == atm.strike() || chosen.getLast()[0] == atm.strike()) {
            // methodology v5.0 3(a)(iii): every OTM put or every OTM call excluded (ruling E-B15)
            throw new QfError("E_INPUT", "no out-of-the-money put or no out-of-the-money call is selected", "strip");
        }
        double sum = 0.0;
        double[] used = new double[n];
        for (int i = 0; i < n; i++) {
            double k = chosen.get(i)[0];
            used[i] = k;
            double dk;
            if (i == 0) {
                dk = chosen.get(1)[0] - k;
            } else if (i == n - 1) {
                dk = k - chosen.get(n - 2)[0];
            } else {
                dk = (chosen.get(i + 1)[0] - chosen.get(i - 1)[0]) / 2.0;
            }
            sum += dk / (k * k) * chosen.get(i)[1];
        }
        double k0 = atm.strike();
        double c = fwd / k0 - 1.0;
        double variance = 2.0 / t * growth * sum - c * c / t;
        return new Term(fwd, k0, variance, used, t);
    }

    /** 30-day index from two terms (ruling E-B6). Minutes are checked by the caller. */
    public static double index(long n1, Term near, long n2, Term next) {
        double bracket = near.years() * near.variance() * (n2 - MINUTES_30D) / (n2 - n1)
                + next.years() * next.variance() * (MINUTES_30D - n1) / (n2 - n1);
        if (bracket < 0.0) {
            throw new QfError("E_DOMAIN", "negative variance in time");
        }
        return 100.0 * Math.sqrt(bracket * MINUTES_YEAR / MINUTES_30D);
    }
}
