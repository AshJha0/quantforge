package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.DoubleUnaryOperator;
import java.util.function.Function;
import org.quantforge.core.AsOfStore;
import org.quantforge.core.Calendars;
import org.quantforge.core.Compounding;
import org.quantforge.core.CosPricer;
import org.quantforge.core.DataChecks;
import org.quantforge.core.DayCount;
import org.quantforge.core.Integration;
import org.quantforge.core.Json;
import org.quantforge.core.Interpolation;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.MonotoneConvex;
import org.quantforge.core.MonteCarlo;
import org.quantforge.core.Normal;
import org.quantforge.core.PdeEngine;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;
import org.quantforge.core.RootFinders;
import org.quantforge.core.SnapshotHash;
import org.quantforge.core.Sobol;
import org.quantforge.core.Statistics;
import org.quantforge.core.TimeSeries;
import org.quantforge.core.TimeZones;

/** Maps operation names to the core. All input reading comes before any rule check, as the contract orders. */
final class Operations {
    private Operations() {}

    record Out(Map<String, Object> outputs, Map<String, Object> diagnostics) {}

    private static final Map<String, Function<In, Out>> TABLE = new TreeMap<>();

    static {
        dates();
        numerics();
        statistics();
        engines();
        store();
        StageB.register(TABLE);
        OpsForward.register(TABLE);
        OpsBlack.register(TABLE);
        OpsGreeks.register(TABLE);
    }

    static Set<String> names() {
        return TABLE.keySet();
    }

    static Function<In, Out> find(String name) {
        return TABLE.get(name);
    }

    static Out out(Object... keysAndValues) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i < keysAndValues.length; i += 2) {
            m.put((String) keysAndValues[i], keysAndValues[i + 1]);
        }
        return new Out(m, Map.of());
    }

    private static Out withDiagnostics(Out o, Object... keysAndValues) {
        return new Out(o.outputs(), out(keysAndValues).outputs());
    }

    private static List<String> text(List<LocalDate> dates) {
        return dates.stream().map(LocalDate::toString).toList();
    }

    private static void dates() {
        TABLE.put("core.daycount.year_fraction", Operations::yearFraction);
        TABLE.put("core.calendar.is_business_day", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            return out("is_business_day", Calendars.isBusinessDay(cal, in.date("date")));
        });
        TABLE.put("core.calendar.holidays", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            return out("dates", text(Calendars.holidays(cal, in.integer("year"))));
        });
        TABLE.put("core.calendar.adjust", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            LocalDate d = in.date("date");
            return out("date", Calendars.adjust(cal, d, in.choice("convention", Calendars.Convention.class)).toString());
        });
        TABLE.put("core.calendar.add_business_days", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            LocalDate d = in.date("date");
            long days = in.integer("days");
            in.limit(Math.abs(days) > 30_000, "days");
            in.gate();
            return out("date", Calendars.addBusinessDays(cal, d, days).toString());
        });
        TABLE.put("core.calendar.business_days_between", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            LocalDate start = in.date("start");
            return out("count", Calendars.businessDaysBetween(cal, start, in.date("end")));
        });
        TABLE.put("core.calendar.add_tenor", in -> {
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            LocalDate d = in.date("date");
            String tenor = in.string("tenor");
            Calendars.Convention c = in.choice("convention", Calendars.Convention.class);
            return out("date", Calendars.addTenor(cal, d, tenor, c, in.bool("end_of_month")).toString());
        });
        TABLE.put("core.compounding.discount_factor", in -> {
            double rate = in.real("rate");
            double t = in.real("t");
            return out("discount_factor", Compounding.discountFactor(rate, t, basis(in)));
        });
        TABLE.put("core.compounding.convert", in -> {
            double rate = in.real("rate");
            double t = in.real("t");
            Compounding.Basis from = basis(in.object("from"));
            Compounding.Basis to = basis(in.object("to"));
            return out("rate", Compounding.convert(rate, t, from, to));
        });
        TABLE.put("core.snapshot.hash", in -> {
            SnapshotHash.Result r = SnapshotHash.hash(in.string("document_text"));
            return out("canonical", r.canonical(), "snapshot_id", r.snapshotId());
        });
        TABLE.put("core.time.utc_offset", in -> {
            TimeZones.Zone z = TimeZones.Zone.of(in.string("zone"));
            return out("offset_seconds", TimeZones.utcOffset(z, in.instant("instant")));
        });
        TABLE.put("core.time.to_local", in -> {
            TimeZones.Zone z = TimeZones.Zone.of(in.string("zone"));
            return out("local", TimeZones.toLocal(z, in.instant("instant")));
        });
        TABLE.put("core.time.to_instant", in -> {
            TimeZones.Zone z = TimeZones.Zone.of(in.string("zone"));
            var local = TimeZones.parseLocal(in.string("local"));
            TimeZones.Overlap o = in.has("overlap") ? in.choice("overlap", TimeZones.Overlap.class) : null;
            return out("instant", TimeZones.toInstant(z, local, o));
        });
        TABLE.put("core.time.business_date", in -> {
            long instant = in.instant("instant");
            TimeZones.Zone z = TimeZones.Zone.of(in.string("zone"));
            String cutoff = in.string("cutoff");
            TimeZones.checkCutoff(cutoff);
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            return out("date", TimeZones.businessDate(instant, z, cutoff, cal).toString());
        });
        TABLE.put("core.data.check_quotes", Operations::checkQuotes);
    }

    private static Out yearFraction(In in) {
        DayCount.Convention c = in.choice("convention", DayCount.Convention.class);
        LocalDate start = in.date("start");
        LocalDate end = in.date("end");
        Integer frequency = null;
        LocalDate refStart = null;
        LocalDate refEnd = null;
        LocalDate termination = null;
        Calendars.Id calendar = null;
        if (c == DayCount.Convention.ACT_ACT_ICMA || c == DayCount.Convention.ACT_365L) {
            frequency = frequency(in);
        }
        if (c == DayCount.Convention.ACT_ACT_ICMA) {
            refStart = in.date("ref_start");
            refEnd = in.date("ref_end");
        }
        if (c == DayCount.Convention.THIRTY_E_360_ISDA) {
            termination = in.date("termination");
        }
        if (c == DayCount.Convention.BUS_252) {
            calendar = in.choice("calendar", Calendars.Id.class);
        }
        DayCount.Extras x = new DayCount.Extras(frequency, refStart, refEnd, termination, calendar);
        return out("year_fraction", DayCount.yearFraction(c, start, end, x));
    }

    private static int frequency(In in) {
        long f = in.integer("frequency");
        if (f != 1 && f != 2 && f != 3 && f != 4 && f != 6 && f != 12) {
            throw new QfError("E_SCHEMA", "frequency not listed", "frequency");
        }
        return (int) f;
    }

    private static Compounding.Basis basis(In in) {
        Compounding.Kind k = in.choice("compounding", Compounding.Kind.class);
        return new Compounding.Basis(k, k == Compounding.Kind.PERIODIC ? frequency(in) : 0);
    }

    private static Out checkQuotes(In in) {
        long asOf = in.instant("as_of");
        List<DataChecks.Quote> quotes = new ArrayList<>();
        for (In q : in.objects("quotes")) {
            String id = q.string("instrument_id");
            long eventTime = q.instant("event_time");
            String status = q.string("quote_status");
            if (!status.equals("FIRM") && !status.equals("INDICATIVE")) {
                throw new QfError("E_SCHEMA", "input quote_status must be FIRM or INDICATIVE", "quote_status");
            }
            quotes.add(new DataChecks.Quote(id, eventTime, q.nullableReal("bid"), q.nullableReal("ask"), status));
        }
        Map<String, double[]> history = new HashMap<>();
        if (in.has("history")) {
            In h = in.object("history");
            for (String k : h.keys()) {
                history.put(k, h.reals(k));
            }
        }
        DataChecks.Settings cfg = new DataChecks.Settings(asOf, in.integer("stale_after_seconds"),
                in.realOrNull("max_relative_spread"), in.bool("positive_only", false),
                in.real("outlier_threshold", 5.0), in.integer("outlier_min_history", 5), history);
        in.gate();
        List<Map<String, Object>> results = new ArrayList<>();
        for (DataChecks.Checked c : DataChecks.check(quotes, cfg)) {
            results.add(out("instrument_id", c.instrumentId(), "quote_status", c.quoteStatus(),
                    "quality_flags", c.qualityFlags()).outputs());
        }
        return out("results", results);
    }

    private static int stream(In in) {
        long s = in.integer("stream", 0);
        if (s < 0 || s > 1023) {
            throw new QfError("E_SCHEMA", "stream out of range", "stream");
        }
        return (int) s;
    }

    private static int count(In in) {
        long c = in.atMost("count", 100_000);
        if (c < 1) {
            throw new QfError("E_SCHEMA", "count below 1", "count");
        }
        return (int) Math.min(c, 100_000);
    }

    /** Reads the common inputs of the seeded generators and positions a generator after {@code skip}. */
    private static Rng seededAfterSkip(In in) {
        long seed = in.u64("seed");
        int stream = stream(in);
        long skip = in.integer("skip", 0);
        if (skip < 0) {
            throw new QfError("E_SCHEMA", "skip is negative", "skip");
        }
        in.limit(skip > 10_000_000L, "skip");
        in.gate();
        Rng rng = Rng.seeded(seed, stream);
        for (long i = 0; i < skip; i++) {
            rng.nextLong();
        }
        return rng;
    }

    private static List<String> u64Text(Rng rng, int n) {
        List<String> v = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            v.add(Long.toUnsignedString(rng.nextLong()));
        }
        return v;
    }

    private static RootFinders.Tolerances tolerances(In in) {
        RootFinders.Tolerances t = new RootFinders.Tolerances(in.real("x_tol", 1e-12), in.real("f_tol", 0.0),
                in.atMost("max_iter", 200, 100_000));
        in.gate();
        return t;
    }

    private static Out rootOut(RootFinders.Result r) {
        return withDiagnostics(out("root", r.root()), "iterations", r.iterations(), "residual", r.residual(),
                "termination", r.termination().name());
    }

    private static void numerics() {
        TABLE.put("core.rng.next_u64", in -> {
            int n = count(in);
            return out("values", u64Text(seededAfterSkip(in), n));
        });
        TABLE.put("core.rng.uniforms", in -> {
            int n = count(in);
            Rng rng = seededAfterSkip(in);
            double[] v = new double[n];
            for (int i = 0; i < n; i++) {
                v[i] = rng.nextUniform();
            }
            return out("values", v);
        });
        TABLE.put("core.rng.normals", in -> {
            int n = count(in);
            Rng rng = seededAfterSkip(in);
            double[] v = new double[n];
            for (int i = 0; i < n; i++) {
                v[i] = rng.nextNormal();
            }
            return out("values", v);
        });
        TABLE.put("core.rng.inverse_normal", in -> {
            double[] p = in.reals("p");
            double[] z = new double[p.length];
            for (int i = 0; i < p.length; i++) {
                if (!(p[i] > 0.0 && p[i] < 1.0)) {
                    throw new QfError("E_DOMAIN", "p outside (0, 1)", "p");
                }
                z[i] = Rng.ppnd16(p[i]);
            }
            return out("z", z);
        });
        TABLE.put("core.rng.set_state_next_u64", in -> {
            long[] state = in.u64s("state", 4);
            int n = count(in);
            in.gate();
            if ((state[0] | state[1] | state[2] | state[3]) == 0) {
                throw new QfError("E_INPUT", "all-zero state", "state");
            }
            return out("values", u64Text(Rng.fromState(state), n));
        });
        TABLE.put("core.sobol.points", Operations::sobol);
        TABLE.put("core.root.bisection", in -> {
            TestFunctions.Pair p = TestFunctions.root(in.string("function"));
            return rootOut(RootFinders.bisection(p.f(), in.real("a"), in.real("b"), tolerances(in)));
        });
        TABLE.put("core.root.brent", in -> {
            TestFunctions.Pair p = TestFunctions.root(in.string("function"));
            return rootOut(RootFinders.brent(p.f(), in.real("a"), in.real("b"), tolerances(in)));
        });
        TABLE.put("core.root.newton", in -> {
            TestFunctions.Pair p = TestFunctions.root(in.string("function"));
            if (in.has("a") != in.has("b")) {
                throw new QfError("E_SCHEMA", "a and b must be given together");
            }
            return rootOut(RootFinders.newton(p.f(), p.df(), in.real("x0"), in.realOrNull("a"), in.realOrNull("b"),
                    tolerances(in)));
        });
        TABLE.put("core.integrate.trapezoid", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            return out("value", Integration.trapezoid(f, in.real("a"), in.real("b"), in.gate(in.atMost("n", 10_000_000))));
        });
        TABLE.put("core.integrate.simpson", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            return out("value", Integration.simpson(f, in.real("a"), in.real("b"), in.gate(in.atMost("n", 10_000_000))));
        });
        TABLE.put("core.integrate.gauss_legendre", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            return out("value", Integration.gaussLegendre(f, in.real("a"), in.real("b"), in.integer("n")));
        });
        TABLE.put("core.integrate.adaptive_simpson", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            return out("value", Integration.adaptiveSimpson(f, in.real("a"), in.real("b"), in.real("tol", 1e-10),
                    in.gate(in.atMost("max_depth", 50, 60))));
        });
        TABLE.put("core.integrate.gauss_kronrod", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            Integration.Adaptive r = Integration.gaussKronrod(f, in.real("a"), in.real("b"), in.real("tol", 1e-10),
                    in.gate(in.atMost("max_intervals", 500, 10_000)));
            return withDiagnostics(out("value", r.value()), "error_estimate", r.errorEstimate());
        });
        TABLE.put("core.interp.evaluate", Operations::interpolate);
        TABLE.put("core.interp.monotone_convex", in -> {
            MonotoneConvex.Result r = MonotoneConvex.evaluate(in.reals("t"), in.reals("r"), in.reals("at"),
                    in.gate(in.bool("positive", false)));
            return out("forwards", r.forwards(), "zero_rates", r.zeroRates());
        });
        TABLE.put("core.diff.central", in -> {
            DoubleUnaryOperator f = TestFunctions.plain(in.string("function"));
            double x = in.real("x");
            double h = in.real("h");
            long order = in.integer("order");
            if (order != 1 && order != 2) {
                throw new QfError("E_SCHEMA", "order not listed", "order");
            }
            if (!(h > 0.0)) {
                throw new QfError("E_INPUT", "need h > 0", "h");
            }
            double up = f.applyAsDouble(x + h);
            double down = f.applyAsDouble(x - h);
            return out("value", order == 1 ? (up - down) / (2.0 * h)
                    : (up - 2.0 * f.applyAsDouble(x) + down) / (h * h));
        });
        TABLE.put("core.linalg.solve", in -> out("x", LinearAlgebra.solve(in.matrix("a"), in.gate(in.reals("b")))));
        TABLE.put("core.linalg.cholesky", in -> out("l", LinearAlgebra.cholesky(in.gate(in.matrix("a")))));
        TABLE.put("core.linalg.eigen_symmetric", in -> out("values", LinearAlgebra.eigenSymmetric(in.gate(in.matrix("a")))));
    }

    private static Out sobol(In in) {
        long dimensions = in.integer("dimensions");
        long count = in.integer("count");
        long skip = in.integer("skip", 0);
        in.limit(In.productOver(count, dimensions, 100_000) || skip > 10_000_000L, "count");
        in.gate();
        if (dimensions < 1 || dimensions > Sobol.MAX_DIMENSIONS || count < 1 || skip < 0) {
            throw new QfError("E_INPUT", "dimensions, count or skip out of range");
        }
        Sobol s = new Sobol((int) dimensions, skip);
        double[][] points = new double[(int) count][(int) dimensions];
        for (double[] p : points) {
            s.next(p);
        }
        return out("points", points);
    }

    private static Out interpolate(In in) {
        String name = in.string("method");
        Interpolation.Method method = In.parseEnum("method", name.toUpperCase(java.util.Locale.ROOT), Interpolation.Method.class);
        if (!name.equals(method.name().toLowerCase(java.util.Locale.ROOT))) {
            throw new QfError("E_SCHEMA", "method not listed", "method");
        }
        double[] x = in.reals("x");
        double[] y = in.reals("y");
        double[] at = in.reals("at");
        double start = 0.0;
        double end = 0.0;
        double tension = 0.0;
        if (method == Interpolation.Method.CUBIC_CLAMPED) {
            start = in.real("slope_start");
            end = in.real("slope_end");
        }
        if (method == Interpolation.Method.TENSION) {
            tension = in.real("tension");
        }
        in.gate();
        Interpolation.Result r = Interpolation.evaluate(method, x, y, at, new Interpolation.Params(start, end, tension));
        return r.derivatives() == null ? out("values", r.values()) : out("values", r.values(), "derivatives", r.derivatives());
    }

    private static void statistics() {
        TABLE.put("core.stats.normal", in -> {
            double[] x = in.reals("x");
            double[] pdf = new double[x.length];
            double[] cdf = new double[x.length];
            for (int i = 0; i < x.length; i++) {
                pdf[i] = Normal.pdf(x[i]);
                cdf[i] = Normal.cdf(x[i]);
            }
            return out("pdf", pdf, "cdf", cdf);
        });
        TABLE.put("core.stats.summary", in -> {
            Statistics.Summary s = Statistics.summary(in.reals("x"));
            return out("count", s.count(), "mean", s.mean(), "variance", s.variance(), "stdev", s.stdev(),
                    "skewness", s.skewness(), "excess_kurtosis", s.excessKurtosis(), "min", s.min(), "max", s.max());
        });
        TABLE.put("core.stats.quantile", in -> out("values", Statistics.quantile(in.reals("x"), in.gate(in.reals("p")))));
        TABLE.put("core.stats.covariance", in -> {
            Statistics.Covariance c = Statistics.covariance(in.reals("x"), in.reals("y"));
            return out("covariance", c.covariance(), "correlation", c.correlation());
        });
        TABLE.put("core.stats.ols", in -> {
            Statistics.Ols o = Statistics.ols(in.reals("x"), in.reals("y"));
            return out("alpha", o.alpha(), "beta", o.beta(), "r_squared", o.rSquared(), "se_alpha", o.seAlpha(),
                    "se_beta", o.seBeta());
        });
        TABLE.put("core.ts.returns", in -> {
            double[] p = in.reals("prices");
            return out("returns", TimeSeries.returns(p, in.choice("kind", TimeSeries.ReturnKind.class)));
        });
        TABLE.put("core.ts.rolling", in -> {
            double[] x = in.reals("x");
            long w = in.atMost("window", 1000);
            return out("values", TimeSeries.rolling(x, w, in.gate(in.choice("statistic", TimeSeries.RollingStatistic.class))));
        });
        TABLE.put("core.ts.ewma_variance", in -> out("variance", TimeSeries.ewmaVariance(in.reals("returns"), in.real("lambda"))));
        TABLE.put("core.ts.autocorrelation", in -> out("acf", TimeSeries.autocorrelation(in.reals("x"), in.gate(in.atMost("max_lag", 1000)))));
        TABLE.put("core.ts.ljung_box", in -> out("statistic", TimeSeries.ljungBox(in.reals("x"), in.gate(in.atMost("max_lag", 1000)))));
        TABLE.put("core.ts.ar1", in -> {
            TimeSeries.Ar1 a = TimeSeries.ar1(in.reals("x"));
            return out("constant", a.constant(), "phi", a.phi(), "sigma", a.sigma());
        });
        TABLE.put("core.ts.resample_last", in -> {
            List<LocalDate> d = in.dates("dates");
            List<Double> v = in.nullableReals("values");
            TimeSeries.Resampled r = TimeSeries.resampleLast(d, v, in.choice("frequency", TimeSeries.Frequency.class));
            return out("dates", text(r.dates()), "values", r.values());
        });
        TABLE.put("core.ts.forward_fill", in -> {
            List<Double> v = in.nullableReals("values");
            return out("values", TimeSeries.forwardFill(v, in.integer("limit")));
        });
    }

    /** Reads the log. Limits and the log's rule checks wait until every input of the case has been read. */
    private static List<AsOfStore.Entry> log(In in) {
        List<AsOfStore.Entry> log = new ArrayList<>();
        for (In r : in.objects("records")) {
            long sequence = r.integer("sequence");
            String series = r.string("series_id");
            if (sequence < 1 || series.isEmpty()) {
                throw new QfError("E_SCHEMA", "need sequence >= 1 and a non-empty series_id", "records");
            }
            if (Json.hasLoneSurrogate(r.raw())) {
                throw new QfError("E_SCHEMA", "lone surrogate in a record", "records");
            }
            Object value = r.anyValue("value");
            for (Object field : r.raw().values()) {
                in.limit(Json.depth(field) > SnapshotHash.MAX_DEPTH, "records");
            }
            log.add(new AsOfStore.Entry(sequence, series, r.instant("event_time"), r.instant("knowledge_time"),
                    value, r.bool("deleted", false), r.raw()));
        }
        return log;
    }

    /** Runs after all reads: limits, then log checks, then the year limit on records and on {@code others}. */
    private static void checkStore(In in, List<AsOfStore.Entry> log, List<Long> others) {
        in.gate();
        AsOfStore.checkLog(log);
        others.forEach(AsOfStore::checkInstant);
    }

    private static void store() {
        TABLE.put("core.store.query_as_of", in -> {
            List<AsOfStore.Entry> log = log(in);
            long asOf = in.instant("as_of");
            String series = in.has("series_id") ? in.string("series_id") : null;
            Long from = in.has("event_from") ? in.instant("event_from") : null;
            Long to = in.has("event_to") ? in.instant("event_to") : null;
            List<Long> others = new ArrayList<>(List.of(asOf));
            if (from != null) {
                others.add(from);
            }
            if (to != null) {
                others.add(to);
            }
            checkStore(in, log, others);
            if (from != null && to != null && from > to) {
                throw new QfError("E_DATE_ORDER", "event_from is after event_to", "event_to");
            }
            List<Map<String, Object>> rows = new ArrayList<>();
            for (AsOfStore.Entry e : AsOfStore.view(log, asOf)) {
                if ((series == null || series.equals(e.seriesId())) && (from == null || e.eventTime() >= from)
                        && (to == null || e.eventTime() <= to)) {
                    rows.add(AsOfStore.row(e));
                }
            }
            return out("rows", rows);
        });
        TABLE.put("core.store.latest", in -> {
            List<AsOfStore.Entry> log = log(in);
            long asOf = in.instant("as_of");
            String series = in.string("series_id");
            checkStore(in, log, List.of(asOf));
            AsOfStore.Entry last = null;
            for (AsOfStore.Entry e : AsOfStore.view(log, asOf)) {
                if (series.equals(e.seriesId())) {
                    last = e; // The view is ordered by event time within a series.
                }
            }
            return out("row", last == null ? null : AsOfStore.row(last));
        });
        TABLE.put("core.store.snapshot", in -> {
            List<AsOfStore.Entry> log = log(in);
            long asOf = in.instant("as_of");
            checkStore(in, log, List.of(asOf));
            SnapshotHash.Result r = AsOfStore.snapshot(log, asOf);
            return out("canonical", r.canonical(), "snapshot_id", r.snapshotId());
        });
        TABLE.put("core.store.replay", in -> {
            List<AsOfStore.Entry> log = log(in);
            List<Long> checkpoints = in.instants("checkpoints");
            in.limit(checkpoints.size() > 1000 || In.productOver(log.size(), checkpoints.size(), 10_000_000L), "checkpoints");
            checkStore(in, log, checkpoints);
            for (int i = 1; i < checkpoints.size(); i++) {
                if (checkpoints.get(i) < checkpoints.get(i - 1)) {
                    throw new QfError("E_INPUT", "checkpoints out of order", "checkpoints");
                }
            }
            List<Map<String, Object>> snapshots = new ArrayList<>();
            for (long c : checkpoints) {
                snapshots.add(out("as_of", TimeZones.formatInstant(c), "row_count", AsOfStore.view(log, c).size(),
                        "snapshot_id", AsOfStore.snapshot(log, c).snapshotId()).outputs());
            }
            return out("snapshots", snapshots, "head", AsOfStore.chain(log).head());
        });
        TABLE.put("core.store.chain", in -> {
            List<AsOfStore.Entry> log = log(in);
            checkStore(in, log, List.of());
            AsOfStore.Chain c = AsOfStore.chain(log);
            return out("head", c.head(), "hashes", c.hashes());
        });
    }

    private enum Option { CALL, PUT }

    private enum ModelName { BLACK_SCHOLES, HESTON }

    private static void engines() {
        TABLE.put("core.pde.bs_european", in -> {
            boolean call = in.choice("option", Option.class) == Option.CALL;
            long space = in.integer("space_steps");
            long time = in.integer("time_steps");
            in.limit(In.productOver(space, time, 10_000_000L), "space_steps");
            PdeEngine.Result r = PdeEngine.solve(new PdeEngine.Inputs(call, in.real("spot"), in.real("strike"),
                    in.real("r"), in.real("q"), in.real("sigma"), in.real("t"), space, time, in.real("width", 6.0),
                    in.gate(in.integer("rannacher_steps", 2))));
            return withDiagnostics(out("price", r.price(), "delta", r.delta(), "gamma", r.gamma()), "grid_h", r.gridH());
        });
        TABLE.put("core.mc.gbm_european", in -> {
            boolean call = in.choice("option", Option.class) == Option.CALL;
            long paths = in.integer("paths");
            long steps = in.integer("steps", 1);
            in.limit(In.productOver(paths, steps, 1_000_000L), "paths");
            MonteCarlo.Result r = MonteCarlo.price(new MonteCarlo.Inputs(call, in.real("spot"), in.real("strike"),
                    in.real("r"), in.real("q"), in.real("sigma"), in.real("t"), paths, steps, in.u64("seed"),
                    stream(in), in.gate(in.choice("method", MonteCarlo.Method.class))));
            return out("price", r.price(), "stderr", r.stderr());
        });
        TABLE.put("core.cos.european", in -> {
            boolean call = in.choice("option", Option.class) == Option.CALL;
            In m = in.object("model");
            CosPricer.Model model = m.choice("name", ModelName.class) == ModelName.BLACK_SCHOLES
                    ? new CosPricer.BlackScholes(m.real("sigma"))
                    : new CosPricer.Heston(m.real("v0"), m.real("kappa"), m.real("theta"), m.real("sigma"), m.real("rho"));
            CosPricer.Result r = CosPricer.price(new CosPricer.Inputs(call, in.real("spot"), in.real("strike"),
                    in.real("r"), in.real("q"), in.real("t"), model, in.atMost("terms", 100_000),
                    in.gate(in.real("truncation"))));
            return withDiagnostics(out("price", r.price()), "a", r.a(), "b", r.b());
        });
    }
}
