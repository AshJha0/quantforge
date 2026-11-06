package org.quantforge.core;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/** Market-data quote checks (data-checks.md). Never changes a price, never drops a quote. */
public final class DataChecks {
    private DataChecks() {}

    public record Quote(String instrumentId, long eventTime, Double bid, Double ask, String sourceStatus) {}

    public record Settings(long asOf, long staleAfterSeconds, Double maxRelativeSpread, boolean positiveOnly,
                           double outlierThreshold, long outlierMinHistory, Map<String, double[]> history) {}

    public record Checked(String instrumentId, String quoteStatus, List<String> qualityFlags) {}

    private static double median(double[] v) {
        double[] s = v.clone();
        Arrays.sort(s);
        int n = s.length;
        return n % 2 == 1 ? s[n / 2] : (s[n / 2 - 1] + s[n / 2]) / 2.0;
    }

    private static boolean outlier(double mid, double[] h, Settings cfg) {
        if (h == null || h.length < cfg.outlierMinHistory()) {
            return false;
        }
        double med = median(h);
        double[] dev = new double[h.length];
        for (int i = 0; i < h.length; i++) {
            dev[i] = Math.abs(h[i] - med);
        }
        double mad = median(dev);
        return mad != 0.0 && Math.abs(mid - med) / (1.4826 * mad) > cfg.outlierThreshold();
    }

    public static List<Checked> check(List<Quote> quotes, Settings cfg) {
        if (cfg.staleAfterSeconds() <= 0) {
            throw new QfError("E_INPUT", "stale_after_seconds must be positive", "stale_after_seconds");
        }
        if (cfg.maxRelativeSpread() != null && cfg.maxRelativeSpread() <= 0.0) {
            throw new QfError("E_INPUT", "max_relative_spread must be positive", "max_relative_spread");
        }
        if (cfg.outlierThreshold() <= 0.0) {
            throw new QfError("E_INPUT", "outlier_threshold must be positive", "outlier_threshold");
        }
        if (cfg.outlierMinHistory() < 3) {
            throw new QfError("E_INPUT", "outlier_min_history must be at least 3", "outlier_min_history");
        }
        List<Checked> out = new ArrayList<>(quotes.size());
        for (Quote q : quotes) {
            if (q.eventTime() > cfg.asOf()) {
                throw new QfError("E_INPUT", "event_time is after as_of", "quotes");
            }
            out.add(checkOne(q, cfg));
        }
        return out;
    }

    private static Checked checkOne(Quote q, Settings cfg) {
        List<String> flags = new ArrayList<>();
        Double bid = q.bid();
        Double ask = q.ask();
        boolean nonPositive = cfg.positiveOnly() && ((bid != null && bid <= 0.0) || (ask != null && ask <= 0.0));
        if (bid == null || ask == null) {
            if (bid == null) {
                flags.add("MISSING_BID");
            }
            if (ask == null) {
                flags.add("MISSING_ASK");
            }
            if (nonPositive) {
                flags.add("NON_POSITIVE");
            }
            return new Checked(q.instrumentId(), "MISSING", flags);
        }
        boolean crossed = bid > ask;
        boolean stale = cfg.asOf() - q.eventTime() > cfg.staleAfterSeconds();
        double mid = (bid + ask) / 2.0;
        if (crossed) {
            flags.add("CROSSED");
        }
        if (bid.doubleValue() == ask.doubleValue()) {
            flags.add("LOCKED");
        }
        if (stale) {
            flags.add("STALE");
        }
        if (cfg.maxRelativeSpread() != null && !crossed && mid != 0.0
                && (ask - bid) / Math.abs(mid) > cfg.maxRelativeSpread()) {
            flags.add("WIDE_SPREAD");
        }
        if (nonPositive) {
            flags.add("NON_POSITIVE");
        }
        if (!crossed && outlier(mid, cfg.history().get(q.instrumentId()), cfg)) {
            flags.add("OUTLIER");
        }
        String status = crossed ? "CROSSED" : stale ? "STALE" : q.sourceStatus();
        return new Checked(q.instrumentId(), status, flags);
    }
}
