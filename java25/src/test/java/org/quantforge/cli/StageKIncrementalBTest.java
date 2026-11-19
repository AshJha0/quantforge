package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Conventions;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Jumps;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Projection;

/**
 * K-4b on the stage B production bootstrap (incremental-update.md, Acceptance, third line; KR-5): on 10,000 quote moves
 * over every sequential stage B instrument set, {@code bootstrapIncremental} equals a full rebuild to 1e-12 relative and
 * the copied pillars are bit-identical to the cache. The sets and the move plan are those of the Python test
 * (test_stage_k_w1.py); the random part draws from java.util.Random(20261119).
 */
class StageKIncrementalBTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden");
    private static final double BP = 1e-4;

    /** One instrument set: OIS (convention, jumps) or projection (discount curve, index). */
    private record Set(String id, Conventions.RateIndex ois, Jumps jumps, Curve discount, Conventions.RateIndex ix,
                       LocalDate asOf, Curve.Interpolation interp, List<Object> quotes) {
        boolean isOis() {
            return ois != null;
        }

        CurveSolver.Solved solve(List<Object> q) {
            return isOis()
                    ? Ois.bootstrap(ois, asOf, oisQuotes(q), interp, CurveSolver.Method.SEQUENTIAL, null, jumps)
                    : Projection.bootstrap(discount, ix, asOf, termQuotes(q), interp);
        }

        CurveSolver.Incremental incremental(List<Object> prev, double[] factors, List<Object> next) {
            return isOis()
                    ? Ois.bootstrapIncremental(ois, asOf, oisQuotes(prev), factors, oisQuotes(next), interp, jumps)
                    : Projection.bootstrapIncremental(discount, ix, asOf, termQuotes(prev), factors, termQuotes(next),
                    interp);
        }
    }

    @SuppressWarnings("unchecked")
    private static List<Ois.Quote> oisQuotes(List<Object> q) {
        return (List<Ois.Quote>) (List<?>) q;
    }

    @SuppressWarnings("unchecked")
    private static List<Projection.Quote> termQuotes(List<Object> q) {
        return (List<Projection.Quote>) (List<?>) q;
    }

    private static Object shift(Object q, double d) {
        if (q instanceof Ois.Quote o) {
            return o.rate() != null ? new Ois.Quote(o.tenor(), o.rate() + d, null, null)
                    : new Ois.Quote(o.tenor(), null, o.bid() + d, o.ask() + d);
        }
        Projection.Quote p = (Projection.Quote) q;
        return new Projection.Quote(p.type(), p.months(), p.rate() + d);
    }

    private static List<Set> sets() throws IOException {
        List<Set> out = new ArrayList<>();
        String[][] files = {{"stage_b", "ois"}, {"stage_b", "projection"}, {"stage_b", "projection_deep"},
            {"stage_d", "ois_d"}};
        for (String[] f : files) {
            Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD.resolve(f[0]).resolve(f[1] + ".json"))).value();
            for (Object o : (List<?>) doc.get("cases")) {
                Map<?, ?> c = (Map<?, ?>) o;
                Map<?, ?> i = (Map<?, ?>) c.get("inputs");
                String op = (String) c.get("operation");
                Map<?, ?> expected = (Map<?, ?>) c.get("expected");
                String interp = (String) i.get("interpolation");
                Object method = i.get("method");
                if (!op.endsWith(".bootstrap") || !"ok".equals(expected.get("status"))
                        || (method != null && !"SEQUENTIAL".equals(method))
                        || !("LOG_LINEAR_DF".equals(interp) || "LINEAR_ZERO".equals(interp))
                        || i.containsKey("tension") || i.containsKey("step_end")) {
                    continue;
                }
                In in = new In(i);
                String id = (String) c.get("case_id");
                if ("rates.ois.bootstrap".equals(op)) {
                    out.add(new Set(id, Conventions.overnight(in.string("convention")), OpsLinear.jumps(in, false),
                            null, null, in.date("as_of"), Curve.Interpolation.valueOf(interp),
                            new ArrayList<>(OpsLinear.quotes(in))));
                } else if ("rates.projection.bootstrap".equals(op)) {
                    Curve d = OpsLinear.curve(in, "discount").build();
                    Conventions.RateIndex ix = Conventions.term(in.string("index"));
                    List<Object> q = new ArrayList<>(OpsLinear.termQuotes(in, "quotes"));
                    for (Curve.Interpolation m : List.of(Curve.Interpolation.LOG_LINEAR_DF,
                            Curve.Interpolation.LINEAR_ZERO)) {
                        out.add(new Set(id + "/" + m, null, Jumps.NONE, d, ix, in.date("as_of"), m, q));
                    }
                }
            }
        }
        return out;
    }

    private record Move(Set set, String kind, List<Object> prev, List<Object> next) {}

    private static List<Move> moves(List<Set> sets, int total, long seed) {
        List<Move> out = new ArrayList<>();
        for (Set s : sets) {
            List<Object> base = s.quotes();
            int n = base.size();
            out.add(new Move(s, "none", base, base));
            for (int j = 0; j < n; j++) {
                List<Object> q = new ArrayList<>(base);
                q.set(j, shift(base.get(j), BP));
                out.add(new Move(s, j == 0 ? "single_first" : j == n - 1 ? "single_last" : "single_middle", base, q));
            }
            List<Object> both = new ArrayList<>(base);
            both.set(0, shift(base.get(0), -BP));
            both.set(n - 1, shift(base.get(n - 1), -BP));
            out.add(new Move(s, "multi_first_and_last", base, both));
            List<Object> all = new ArrayList<>();
            for (Object q : base) {
                all.add(shift(q, 2 * BP));
            }
            out.add(new Move(s, "multi_all", base, all));
        }
        Random rnd = new Random(seed);
        while (out.size() < total) {
            Set s = sets.get(rnd.nextInt(sets.size()));
            List<Object> base = s.quotes();
            int n = base.size();
            List<Object> prev = new ArrayList<>();
            for (Object q : base) {
                prev.add(rnd.nextBoolean() ? shift(q, (rnd.nextDouble() * 2 - 1) * 50 * BP) : q);
            }
            List<Integer> idx = new ArrayList<>();
            for (int k = 0; k < n; k++) {
                idx.add(k);
            }
            java.util.Collections.shuffle(idx, rnd);
            idx = new ArrayList<>(idx.subList(0, 1 + rnd.nextInt(n)));
            java.util.Collections.sort(idx);
            List<Object> next = new ArrayList<>(prev);
            for (int k : idx) {
                double size = (0.01 + rnd.nextDouble() * 24.99) * BP;
                next.set(k, shift(prev.get(k), rnd.nextBoolean() ? size : -size));
            }
            int first = idx.getFirst();
            String where = first == 0 ? "first" : first == n - 1 ? "last" : "middle";
            out.add(new Move(s, (idx.size() > 1 ? "multi_" : "single_") + where, prev, next));
        }
        return out;
    }

    @Test
    void incrementalEqualsRebuildOnStageB() throws IOException {
        List<Set> sets = sets();
        assertTrue(sets.size() >= 20, "sets " + sets.size());
        List<Move> moves = moves(sets, 10_000, 20261119L);
        assertEquals(10_000, moves.size());
        double worst = 0.0;
        int bitEqual = 0;
        TreeMap<String, Integer> kinds = new TreeMap<>();
        for (Move m : moves) {
            Set s = m.set();
            double[] cache = s.solve(m.prev()).curve().discountFactors();
            CurveSolver.Incremental inc = s.incremental(m.prev(), cache, m.next());
            CurveSolver.Solved full = s.solve(m.next());
            double[] got = inc.solved().curve().discountFactors();
            double[] want = full.curve().discountFactors();
            int n = m.next().size();
            Integer first = null;
            for (int k = 0; k < n && first == null; k++) {
                if (!m.prev().get(k).equals(m.next().get(k))) {
                    first = k;
                }
            }
            assertEquals(first, inc.firstChangedIndex(), s.id() + " " + m.kind());
            assertEquals(first == null ? 0 : n - first, inc.recomputed());
            int j = first == null ? n : first;
            for (int k = 0; k < j; k++) {
                assertEquals(Double.doubleToRawLongBits(cache[k]), Double.doubleToRawLongBits(got[k]), s.id());
            }
            boolean same = inc.solved().maxRepricingError() == full.maxRepricingError();
            for (int k = 0; k < n; k++) {
                double rel = Math.abs(got[k] - want[k]) / Math.max(Math.abs(want[k]), 1e-300);
                worst = Math.max(worst, rel);
                assertTrue(rel <= 1e-12, s.id() + " " + m.kind() + " pillar " + k + ": " + got[k] + " " + want[k]);
                same &= Double.doubleToRawLongBits(got[k]) == Double.doubleToRawLongBits(want[k]);
            }
            bitEqual += same ? 1 : 0;
            kinds.merge(m.kind(), 1, Integer::sum);
        }
        StringBuilder k = new StringBuilder("{");
        kinds.forEach((a, b) -> k.append(k.length() > 1 ? ", " : "").append('"').append(a).append("\": ").append(b));
        org.quantforge.risk.StageKEvidence.write("incremental_property_stage_b_patched", "{\"cases\": " + moves.size()
                + ", \"instrument_sets\": " + sets.size() + ", \"kinds\": " + k + "}"
                + ", \"max_relative_difference\": " + worst + ", \"bit_identical_to_full_rebuild\": " + bitEqual
                + ", \"copied_pillars_bit_identical\": true, \"seed\": \"java.util.Random(20261119)\"}");
        assertEquals(moves.size(), bitEqual);
    }

    @Test
    void incrementalErrorsAndTenorChange() throws IOException {
        List<Set> sets = sets();
        Set s = sets.stream().filter(Set::isOis).findFirst().orElseThrow();
        List<Object> q = s.quotes();
        double[] f = s.solve(q).curve().discountFactors();
        double[] stale = f.clone();
        stale[stale.length - 1] = Math.nextUp(stale[stale.length - 1]);
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> s.incremental(q, stale, q)).code());
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> s.incremental(q, f, q.subList(0, q.size() - 1)))
                .code());
        double[] shorter = java.util.Arrays.copyOf(f, f.length - 1);
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> s.incremental(q, shorter, q)).code());
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> Ois.bootstrapIncremental(s.ois(), s.asOf(),
                oisQuotes(q), f, oisQuotes(q), Curve.Interpolation.MONOTONE_CONVEX, Jumps.NONE)).code());
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> Ois.bootstrapIncremental(s.ois(), s.asOf(),
                List.of(), new double[0], List.of(), s.interp(), Jumps.NONE)).code());
        CurveSolver.Incremental none = s.incremental(q, f, q);
        assertNull(none.firstChangedIndex());
        assertEquals(0, none.recomputed());
        assertArrayEquals(f, none.solved().curve().discountFactors());
        // a changed tenor is a changed instrument: its pillar and every later one are solved again
        Ois.Quote last = (Ois.Quote) q.getLast();
        assertEquals("30Y", last.tenor());
        List<Object> longer = new ArrayList<>(q);
        longer.set(q.size() - 1, new Ois.Quote("25Y", last.rate(), last.bid(), last.ask()));
        CurveSolver.Incremental t = s.incremental(q, f, longer);
        assertEquals(q.size() - 1, t.firstChangedIndex());
        assertEquals(1, t.recomputed());
        Set p = sets.stream().filter(x -> !x.isOis()).findFirst().orElseThrow();
        double[] pf = p.solve(p.quotes()).curve().discountFactors();
        double[] bad = pf.clone();
        bad[0] = 0.5;
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> p.incremental(p.quotes(), bad, p.quotes())).code());
    }
}
