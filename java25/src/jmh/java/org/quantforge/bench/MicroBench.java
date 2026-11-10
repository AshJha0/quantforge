package org.quantforge.bench;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.openjdk.jmh.annotations.*;
import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.pricing.Pricing;
import org.quantforge.vol.Black;

/** G2 microbenchmarks. QF_BENCH_INJECT_NS adds a busy-wait of that many ns to every op. */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@State(Scope.Benchmark)
@Fork(1)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
public class MicroBench {
    private static final long INJECT = inject();

    private Conventions.RateIndex conv;
    private LocalDate asOf;
    private List<Ois.Quote> quotes;
    private Curve curve;
    private Pricing.OisTrade trade;
    private Black.Option option;
    private double price;

    private static long inject() {
        String s = System.getenv("QF_BENCH_INJECT_NS");
        if (s == null) return 0;
        try { return Long.parseLong(s.trim()); } catch (NumberFormatException e) { return 0; }
    }

    private static void spin() {
        if (INJECT <= 0) return;
        long end = System.nanoTime() + INJECT;
        while (System.nanoTime() < end) { Thread.onSpinWait(); }
    }

    @Setup
    public void setup() throws Exception {
        String dir = System.getProperty("qf.examples", "../examples");
        String text = Files.readString(Path.of(dir, "ois_bootstrap_sofr.json"));
        conv = Conventions.overnight(field(text, "convention"));
        asOf = LocalDate.parse(field(text, "as_of"));
        quotes = new ArrayList<>();
        Matcher m = Pattern.compile("[{]\"tenor\":\"([^\"]+)\",\"rate\":([-0-9.eE]+)[}]").matcher(text);
        while (m.find()) quotes.add(new Ois.Quote(m.group(1), Double.parseDouble(m.group(2)), null, null));
        if (quotes.size() != 13) throw new IllegalStateException("expected 13 quotes, got " + quotes.size());
        curve = build().curve();
        trade = new Pricing.OisTrade(conv, "5Y", 0.035, 1_000_000.0, Pricing.Side.PAY);
        option = new Black.Option(Black.Model.BLACK_76, Black.phi(Black.OptionType.CALL), 105.0, 1.0, 100.0, 0.0, 0.0, 1.0, 0.0);
        price = Black.price(option, 0.2);
    }

    private static String field(String text, String key) {
        Matcher m = Pattern.compile("\"" + key + "\":\"([^\"]+)\"").matcher(text);
        if (!m.find()) throw new IllegalStateException("missing " + key);
        return m.group(1);
    }

    private CurveSolver.Solved build() {
        return Ois.bootstrap(conv, asOf, quotes, Curve.Interpolation.LOG_LINEAR_DF, CurveSolver.Method.SEQUENTIAL, null);
    }

    @Benchmark
    public Object bootstrap() { spin(); return build(); }

    @Benchmark
    public Object swap_pv() { spin(); return Pricing.ois(trade, curve, null); }

    @Benchmark
    public double implied_vol() { spin(); return Black.implied(option, price); }
}
