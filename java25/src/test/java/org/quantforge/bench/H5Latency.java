package org.quantforge.bench;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.SplittableRandom;
import java.util.function.DoubleSupplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.execution.Execution;
import org.quantforge.execution.Execution.*;
import org.quantforge.pricing.Pricing;
import org.quantforge.vol.Black;

/**
 * H-5 p50/p99 harness ({@code specifications/10-execution/library-interfaces.md} section 3). Not a test: run with
 * {@code java -cp target/classes;target/test-classes org.quantforge.bench.H5Latency [examplesDir]}. Prints one JSON
 * object. Thread safety: not safe to share; single-threaded main.
 */
public final class H5Latency {
    private static double sink;

    private record Row(String id, double p50, double p99, int batch) {}

    private static long[] sample(DoubleSupplier f, int warm, int n, int batch) {
        for (int i = 0; i < warm; i++) sink += f.getAsDouble();
        long[] t = new long[n];
        for (int i = 0; i < n; i++) {
            long a = System.nanoTime();
            for (int j = 0; j < batch; j++) sink += f.getAsDouble();
            t[i] = (System.nanoTime() - a);
        }
        Arrays.sort(t);
        return t;
    }

    private static double rank(long[] sorted, double q) {
        return sorted[(int) Math.ceil(q * sorted.length) - 1];
    }

    private static Row run(String id, DoubleSupplier f, int n, int batch) {
        double[] p50 = new double[5], p99 = new double[5];
        for (int r = 0; r < 5; r++) {
            long[] t = sample(f, 20_000, n, batch);
            p50[r] = rank(t, 0.50) / batch;
            p99[r] = rank(t, 0.99) / batch;
        }
        Arrays.sort(p50);
        Arrays.sort(p99);
        return new Row(id, p50[2], p99[2], batch);
    }

    public static void main(String[] args) throws Exception {
        SplittableRandom rng = new SplittableRandom(20261118L);
        double[] profile = new double[390];
        for (int i = 0; i < profile.length; i++) profile[i] = 0.5 + rng.nextDouble();
        AcParams ac = new AcParams(1e6, 5, 100, 0.95, 0.0625, 2.5e-6, 2.5e-7);
        List<Fill> fills = new ArrayList<>();
        for (int i = 0; i < 1000; i++) fills.add(new Fill(1 + rng.nextInt(100), 100 + rng.nextDouble()));
        double[] fq = fills.stream().mapToDouble(Fill::quantity).toArray();
        double[] fp = fills.stream().mapToDouble(Fill::price).toArray();
        double fx = Arrays.stream(fq).sum();

        String dir = args.length > 0 ? args[0] : "../examples";
        String text = Files.readString(Path.of(dir, "ois_bootstrap_sofr.json"));
        Conventions.RateIndex conv = Conventions.overnight(field(text, "convention"));
        LocalDate asOf = LocalDate.parse(field(text, "as_of"));
        List<Ois.Quote> quotes = new ArrayList<>();
        Matcher m = Pattern.compile("[{]\"tenor\":\"([^\"]+)\",\"rate\":([-0-9.eE]+)[}]").matcher(text);
        while (m.find()) quotes.add(new Ois.Quote(m.group(1), Double.parseDouble(m.group(2)), null, null));
        Curve curve = Ois.bootstrap(conv, asOf, quotes, Curve.Interpolation.LOG_LINEAR_DF, CurveSolver.Method.SEQUENTIAL, null).curve();
        Pricing.OisTrade trade = new Pricing.OisTrade(conv, "5Y", 0.035, 1_000_000.0, Pricing.Side.PAY);
        Black.Option opt = new Black.Option(Black.Model.BLACK_76, Black.phi(Black.OptionType.CALL), 105.0, 1.0, 100.0, 0.0, 0.0, 1.0, 0.0);
        double price = Black.price(opt, 0.2);

        long[] clock = new long[10_000];
        for (int i = 0; i < clock.length; i++) { long a = System.nanoTime(); clock[i] = System.nanoTime() - a; }
        Arrays.sort(clock);

        List<Row> rows = List.of(
            run("E1", () -> Execution.twap(1_000_003, 100, Execution.Mode.UNITS)[0], 100_000, 1),
            run("E2", () -> Execution.vwap(1_000_003, profile, Execution.Mode.UNITS)[0], 100_000, 1),
            run("E3", () -> Execution.acTrajectory(ac, 1e-6).objective(), 100_000, 1),
            run("E4", () -> Execution.shortfall(Side.BUY, 100, 100.2, 100.5, fx, fq, fp, 0, 100.4).total(), 100_000, 1),
            run("E5", () -> Execution.asQuotes(100, 3, 0.1, 2, 0.5, 1.5).bid(), 100_000, 100),
            run("E6", () -> Execution.impactSqrt(1e5, 1e7, 0.02, 0.5), 100_000, 100),
            run("B1*", () -> Ois.bootstrap(conv, asOf, quotes, Curve.Interpolation.LOG_LINEAR_DF, CurveSolver.Method.SEQUENTIAL, null).curve().hashCode(), 10_000, 1),
            run("B2*", () -> Pricing.ois(trade, curve, null).hashCode(), 100_000, 1),
            run("B3", () -> Black.implied(opt, price), 100_000, 1));

        StringBuilder sb = new StringBuilder("{\"machine\":\"local Windows laptop, not the acceptance machine\",\"java\":\"")
            .append(System.getProperty("java.version")).append("\",\"clock_overhead_ns_p50\":").append(clock[5000])
            .append(",\"unit\":\"ns per call, median of 5 repeats\",\"rows\":[");
        for (int i = 0; i < rows.size(); i++) {
            Row r = rows.get(i);
            sb.append(i == 0 ? "" : ",").append(String.format("{\"id\":\"%s\",\"p50\":%.1f,\"p99\":%.1f,\"batch\":%d}", r.id(), r.p50(), r.p99(), r.batch()));
        }
        System.out.println(sb.append("],\"sink\":").append(sink != 0).append("}"));
    }

    private static String field(String text, String key) {
        Matcher m = Pattern.compile("\"" + key + "\":\"([^\"]+)\"").matcher(text);
        if (!m.find()) throw new IllegalStateException("missing " + key);
        return m.group(1);
    }
}
