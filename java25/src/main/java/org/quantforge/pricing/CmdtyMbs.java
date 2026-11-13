package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Commodity curves and storage carry (commodity.md, D29); MBS pass-throughs (mbs.md, D30). */
public final class CmdtyMbs {
    private CmdtyMbs() {}

    /** Month indexes {@code k}, quote prices; checks in the spec's order. */
    public static double[] forwards(long[] k, double[] prices, double[] season, long[] months) {
        Finite.check("prices", prices);
        Finite.check("season", season);
        if (k.length == 0) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        for (int i = 1; i < k.length; i++) {
            if (k[i] <= k[i - 1]) {
                throw new QfError("E_INPUT", "quote months must increase", "quotes");
            }
        }
        for (double p : prices) {
            if (!(p > 0.0)) {
                throw new QfError("E_DOMAIN", "prices must be positive", "quotes");
            }
        }
        if (season != null && season.length != 12) {
            throw new QfError("E_INPUT", "seasonality needs 12 terms", "seasonality");
        }
        double[] l = new double[k.length];
        for (int i = 0; i < l.length; i++) {
            l[i] = Math.log(prices[i]) - sigma(season, k[i]);
        }
        double[] out = new double[months.length];
        for (int j = 0; j < out.length; j++) {
            long m = months[j];
            if (m < k[0] || m > k[k.length - 1]) {
                throw new QfError("E_OUT_OF_RANGE", "month outside the quoted range", "months");
            }
            int i = 0;
            while (i < k.length - 1 && m > k[i + 1]) {
                i++;
            }
            double v = i == k.length - 1 || m == k[i] ? l[i]
                    : l[i] + (l[i + 1] - l[i]) * (m - k[i]) / (double) (k[i + 1] - k[i]);
            out[j] = Math.exp(v + sigma(season, m));
        }
        return out;
    }

    private static double sigma(double[] season, long k) {
        return season == null ? 0.0 : season[(int) (k % 12)];
    }

    public record Carry(double[] yields, double[] values, boolean[] arbitrage) {}

    public static Carry carry(Curve f, LocalDate[] dates, double[] prices, double u) {
        Finite.check("prices", prices);
        Finite.check("u", u);
        if (dates.length < 2) {
            throw new QfError("E_INPUT", "need at least two forwards", "forwards");
        }
        LocalDate previous = f.asOf();
        for (LocalDate d : dates) {
            if (!d.isAfter(previous)) {
                throw new QfError("E_INPUT", "forward dates must increase from as_of", "forwards");
            }
            previous = d;
        }
        if (!(u >= 0.0)) {
            throw new QfError("E_DOMAIN", "storage_cost must not be negative", "storage_cost");
        }
        for (double p : prices) {
            if (!(p > 0.0)) {
                throw new QfError("E_DOMAIN", "prices must be positive", "forwards");
            }
        }
        int n = dates.length - 1;
        double[] y = new double[n];
        double[] v = new double[n];
        boolean[] arb = new boolean[n];
        for (int i = 0; i < n; i++) {
            double dt = ChronoUnit.DAYS.between(dates[i], dates[i + 1]) / 365.0;
            double d0 = f.discount(dates[i]);
            double d1 = f.discount(dates[i + 1]);
            double r = Math.log(d0 / d1) / dt;
            y[i] = r + u - Math.log(prices[i + 1] / prices[i]) / dt;
            v[i] = d1 * prices[i + 1] - d0 * prices[i] * Math.exp(u * dt);
            arb[i] = v[i] > 0.0;
        }
        return new Carry(y, v, arb);
    }

    public record Pool(double balance, double wac, double net, long wam, long age, boolean psa, double rate) {}

    public record Flows(double[] balance, double[] interest, double[] scheduled, double[] prepayment, double wal) {}

    public static Flows cashflows(Pool p) {
        if (p.wam() >= 1 && p.wam() <= 1200 && p.age() >= 0 && !(p.wac() > 0.0)) {
            throw new QfError("E_DOMAIN", "wac must be positive", "pool"); // Before net <= wac (mbs_d-0011).
        }
        if (p.wam() < 1 || p.wam() > 1200 || p.age() < 0 || p.net() > p.wac()) {
            throw new QfError("E_INPUT", "wam >= 1, age >= 0 and net_coupon <= wac", "pool");
        }
        if (!(p.wac() > 0.0) || !(p.balance() > 0.0)) {
            throw new QfError("E_DOMAIN", "wac and balance must be positive", "pool");
        }
        if (p.psa() ? !(p.rate() >= 0.0) : !(p.rate() >= 0.0 && p.rate() < 1.0)) {
            throw new QfError("E_DOMAIN", "prepayment rate or speed out of range", "pool");
        }
        if (p.psa()) { // ruling R6-7.1: a PSA speed that reaches CPR 1 in any month is outside the model
            for (long k = 1; k <= p.wam(); k++) {
                if (Math.min((p.age() + k) / 30.0, 1.0) * 0.06 * p.rate() / 100.0 >= 1.0) {
                    throw new QfError("E_DOMAIN", "PSA speed gives a monthly CPR of 1 or more", "pool");
                }
            }
        }
        int n = (int) p.wam();
        double r = p.wac() / 12.0;
        double[] b = new double[n];
        double[] in = new double[n];
        double[] sp = new double[n];
        double[] pp = new double[n];
        double bal = p.balance();
        double wal = 0.0;
        for (int k = 1; k <= n; k++) {
            b[k - 1] = bal;
            double cpr = p.psa() ? Math.min((p.age() + k) / 30.0, 1.0) * 0.06 * p.rate() / 100.0 : p.rate();
            double smm = cpr >= 1.0 ? 1.0 : -Math.expm1(Math.log1p(-cpr) / 12.0);
            int left = n - k + 1;
            double sched = k == n ? bal : bal * r / -Math.expm1(-left * Math.log1p(r)) - bal * r;
            double pre = k == n ? 0.0 : smm * (bal - sched);
            in[k - 1] = bal * p.net() / 12.0;
            sp[k - 1] = sched;
            pp[k - 1] = pre;
            wal += k / 12.0 * (sched + pre);
            bal = bal - sched - pre;
        }
        return new Flows(b, in, sp, pp, wal / p.balance());
    }

    public record Price(double price, double duration, double wal) {}

    public static Price price(Pool p, double y, long delay) {
        Finite.check("y", y);
        if (delay < 0) {
            throw new QfError("E_INPUT", "delay_days must not be negative", "delay_days");
        }
        Flows f = cashflows(p);
        if (!(1.0 + y / 12.0 > 0.0)) {
            throw new QfError("E_DOMAIN", "1 + y/12 must be positive", "yield");
        }
        double lnV = -Math.log1p(y / 12.0);
        double pv = 0.0;
        double dur = 0.0;
        for (int k = 1; k <= f.balance().length; k++) {
            double cf = f.interest()[k - 1] + f.scheduled()[k - 1] + f.prepayment()[k - 1];
            double t = k + delay / 30.0;
            double x = cf * Math.exp(t * lnV);
            pv += x;
            dur += t / 12.0 * x * Math.exp(lnV);
        }
        return new Price(100.0 * pv / p.balance(), dur / pv, f.wal());
    }
}
