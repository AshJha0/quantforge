package org.quantforge.core;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Time-series operations (statistics-and-time-series.md). */
public final class TimeSeries {
    private TimeSeries() {}

    public enum ReturnKind { SIMPLE, LOG }

    public enum RollingStatistic { MEAN, STDEV }

    public enum Frequency { WEEK, MONTH }

    public record Ar1(double constant, double phi, double sigma) {}

    public record Resampled(List<LocalDate> dates, List<Double> values) {}

    public static double[] returns(double[] p, ReturnKind kind) {
        Finite.check("p", p);
        if (p.length < 2) {
            throw new QfError("E_INPUT", "need at least 2 prices", "prices");
        }
        for (double v : p) {
            if (v <= 0.0) {
                throw new QfError("E_DOMAIN", "price is not positive", "prices");
            }
        }
        double[] r = new double[p.length - 1];
        for (int i = 1; i < p.length; i++) {
            r[i - 1] = kind == ReturnKind.SIMPLE ? p[i] / p[i - 1] - 1.0 : Math.log(p[i] / p[i - 1]);
        }
        return r;
    }

    public static Double[] rolling(double[] x, long window, RollingStatistic stat) {
        Finite.check("x", x);
        if (window < 2 || window > x.length) {
            throw new QfError("E_INPUT", "window must be from 2 to n", "window");
        }
        int w = (int) window;
        Double[] out = new Double[x.length];
        for (int end = w; end <= x.length; end++) {
            double[] part = Arrays.copyOfRange(x, end - w, end);
            out[end - 1] = stat == RollingStatistic.MEAN
                    ? Statistics.mean(part)
                    : Math.sqrt(Statistics.sumSquares(Statistics.centered(part)) / (w - 1));
        }
        return out;
    }

    public static double[] ewmaVariance(double[] r, double lambda) {
        Finite.check("r", r);
        Finite.check("lambda", lambda);
        if (r.length < 1) {
            throw new QfError("E_INPUT", "need at least 1 return", "returns");
        }
        if (!(lambda > 0.0 && lambda < 1.0)) {
            throw new QfError("E_DOMAIN", "lambda outside (0, 1)", "lambda");
        }
        double[] v = new double[r.length];
        v[0] = r[0] * r[0];
        for (int t = 1; t < r.length; t++) {
            v[t] = lambda * v[t - 1] + (1.0 - lambda) * r[t] * r[t];
        }
        return v;
    }

    public static double[] autocorrelation(double[] x, long maxLag) {
        Finite.check("x", x);
        if (maxLag < 1 || maxLag >= x.length) {
            throw new QfError("E_INPUT", "max_lag must be from 1 to n - 1", "max_lag");
        }
        double[] d = Statistics.centered(x);
        double denom = Statistics.sumSquares(d);
        if (Statistics.constant(x)) {
            throw new QfError("E_DOMAIN", "zero variance", "x");
        }
        double[] acf = new double[(int) maxLag];
        for (int k = 1; k <= maxLag; k++) {
            double s = 0.0;
            for (int t = k; t < x.length; t++) {
                s += d[t] * d[t - k];
            }
            acf[k - 1] = s / denom;
        }
        return acf;
    }

    public static double ljungBox(double[] x, long maxLag) {
        Finite.check("x", x);
        double[] acf = autocorrelation(x, maxLag);
        double n = x.length;
        double s = 0.0;
        for (int k = 1; k <= maxLag; k++) {
            s += acf[k - 1] * acf[k - 1] / (n - k);
        }
        return n * (n + 2.0) * s;
    }

    public static Ar1 ar1(double[] x) {
        Finite.check("x", x);
        if (x.length < 4) {
            throw new QfError("E_INPUT", "need at least 4 values", "x");
        }
        double[] lag = Arrays.copyOfRange(x, 0, x.length - 1);
        double[] now = Arrays.copyOfRange(x, 1, x.length);
        Statistics.Ols f = Statistics.fit(lag, now, x.length - 3);
        return new Ar1(f.alpha(), f.beta(), Math.sqrt(f.sse() / (x.length - 3)));
    }

    private static long bucket(LocalDate d, Frequency f) {
        return f == Frequency.MONTH
                ? d.getYear() * 12L + d.getMonthValue()
                : d.minusDays(d.getDayOfWeek().getValue() - 1L).toEpochDay();
    }

    public static Resampled resampleLast(List<LocalDate> dates, List<Double> values, Frequency f) {
        if (dates.size() != values.size()) {
            throw new QfError("E_INPUT", "lengths differ");
        }
        for (int i = 1; i < dates.size(); i++) {
            if (!dates.get(i).isAfter(dates.get(i - 1))) {
                throw new QfError("E_INPUT", "dates not strictly increasing", "dates");
            }
        }
        List<LocalDate> outDates = new ArrayList<>();
        List<Double> outValues = new ArrayList<>();
        long current = Long.MIN_VALUE;
        for (int i = 0; i < dates.size(); i++) {
            if (values.get(i) == null) {
                continue;
            }
            long b = bucket(dates.get(i), f);
            if (b == current) {
                outDates.set(outDates.size() - 1, dates.get(i));
                outValues.set(outValues.size() - 1, values.get(i));
            } else {
                current = b;
                outDates.add(dates.get(i));
                outValues.add(values.get(i));
            }
        }
        return new Resampled(outDates, outValues);
    }

    public static List<Double> forwardFill(List<Double> values, long limit) {
        if (limit < 1) {
            throw new QfError("E_INPUT", "limit must be at least 1", "limit");
        }
        List<Double> out = new ArrayList<>(values.size());
        int lastIndex = -1;
        for (int i = 0; i < values.size(); i++) {
            Double v = values.get(i);
            if (v != null) {
                lastIndex = i;
                out.add(v);
            } else if (lastIndex >= 0 && i - lastIndex <= limit) {
                out.add(values.get(lastIndex));
            } else {
                out.add(null);
            }
        }
        return out;
    }
}
