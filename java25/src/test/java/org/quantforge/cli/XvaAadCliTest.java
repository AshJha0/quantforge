package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.risk.Xva;
import org.quantforge.risk.XvaAad;

/**
 * {@code xva.sens.aad} (06-risk/xva-aad-adjustments.md, KR-262 to KR-268): every aadadj_k golden at its own
 * tolerance, the KR-230 error order, and identities of the backward pass on 1,000 seeded random requests (bucket
 * entries sum to the flat entry, recovery entries are -value / (1 - R), spread entries are value / spread, profile
 * entries of a linear output reproduce it).
 */
class XvaAadCliTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden", "stage_k", "aadadj_k.json");

    private static Map<?, ?> run(Object inputs) {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("schema_version", "1.0");
        env.put("case_id", "c");
        env.put("operation", "xva.sens.aad");
        env.put("inputs", inputs);
        StringBuilder b = new StringBuilder();
        Json.write(b, env);
        return (Map<?, ?>) Json.parse(Main.handle(b.toString()).json()).value();
    }

    private static double num(Object o) {
        return ((Json.Number) o).value();
    }

    private static void close(Object a, Object e, String path) {
        if (e instanceof Map<?, ?> me) {
            Map<?, ?> ma = (Map<?, ?>) a;
            assertEquals(me.keySet(), ma.keySet(), path);
            for (Object k : me.keySet()) {
                close(ma.get(k), me.get(k), path + "." + k);
            }
        } else if (e instanceof List<?> le) {
            List<?> la = (List<?>) a;
            assertEquals(le.size(), la.size(), path);
            for (int i = 0; i < le.size(); i++) {
                close(la.get(i), le.get(i), path + "[" + i + "]");
            }
        } else {
            double x = num(a);
            double y = num(e);
            assertTrue(Math.abs(x - y) <= 1e-12 + 1e-10 * Math.max(Math.abs(x), Math.abs(y)), path + " " + x + " " + y);
        }
    }

    @Test
    void registered() {
        assertNotNull(Operations.find("xva.sens.aad"));
        assertEquals(15, XvaAad.keys(true, true).size());
        assertEquals(XvaAad.BASE_KEYS, XvaAad.keys(false, false));
    }

    @Test
    void everyGolden() throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD)).value();
        int ok = 0;
        int err = 0;
        for (Object c : (List<?>) doc.get("cases")) {
            Map<?, ?> cs = (Map<?, ?>) c;
            Map<?, ?> exp = (Map<?, ?>) cs.get("expected");
            Map<?, ?> res = run(cs.get("inputs"));
            String id = (String) cs.get("case_id");
            if ("ok".equals(exp.get("status"))) {
                assertEquals("ok", res.get("status"), id + " " + res);
                close(res.get("outputs"), exp.get("outputs"), id);
                ok++;
            } else {
                assertEquals("error", res.get("status"), id);
                assertEquals(exp.get("error_code"), ((Map<?, ?>) res.get("error")).get("code"), id);
                err++;
            }
        }
        assertEquals(13, ok);
        assertEquals(24, err);
    }

    private static double sum(double[] x) {
        double s = 0;
        for (double v : x) {
            s += v;
        }
        return s;
    }

    private static boolean near(double a, double b, double tol) {
        return Math.abs(a - b) <= tol * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
    }

    /** Identities that hold for every request, on 1,000 seeded random requests (seed 20261120). */
    @Test
    void identitiesOnRandomRequests() {
        Random rng = new Random(20261120L);
        for (int c = 0; c < 1000; c++) {
            int n = 1 + rng.nextInt(6);
            double[] t = new double[n];
            double[] df = new double[n];
            double[] ee = new double[n];
            double[] ene = new double[n];
            double[] im = new double[n];
            double[] cap = new double[n];
            double acc = 0;
            double scale = Math.pow(10, -3 + 9 * rng.nextDouble());
            for (int i = 0; i < n; i++) {
                acc += 0.01 + 3 * rng.nextDouble();
                t[i] = acc;
                df[i] = 0.3 + 0.75 * rng.nextDouble();
                ee[i] = rng.nextDouble() < 0.15 ? 0.0 : scale * rng.nextDouble();
                ene[i] = rng.nextDouble() < 0.15 ? 0.0 : -scale * rng.nextDouble();
                im[i] = scale * rng.nextDouble();
                cap[i] = scale * rng.nextDouble();
            }
            double hc = rng.nextBoolean() ? 0.0 : 0.6 * rng.nextDouble();
            double hb = rng.nextBoolean() ? 0.0 : 0.1 * rng.nextDouble();
            double rc = 0.999999 * rng.nextDouble();
            double rb = 0.99 * rng.nextDouble();
            double sb = 0.03 * rng.nextDouble();
            double sl = 0.03 * rng.nextDouble();
            double ims = 0.02 * rng.nextDouble();
            double hur = 0.15 * rng.nextDouble();
            boolean excl = rng.nextBoolean();
            XvaAad.Request r = new XvaAad.Request(t, df, ee, ene, hc, rc, hb, rb, sb, sl, excl, im, ims, cap, hur);
            double[] v = Xva.adjustments(t, df, ee, ene, hc, rc, hb, rb, sb, sl, excl, im, ims, cap, hur);
            Map<String, Map<String, Object>> g = XvaAad.gradient(r, XvaAad.keys(true, true));
            String[] outs = {"cva", "dva", "fca", "fba", "fva", "mva", "kva"};
            for (String o : outs) {
                Map<String, Object> row = g.get(o);
                for (String name : new String[] {"counterparty", "own"}) {
                    double flat = (Double) row.get(name + ".hazard_rate");
                    double[] bk = (double[]) row.get(name + ".hazard_buckets");
                    assertTrue(near(flat, sum(bk), 1e-11), o + " " + name + " " + flat + " " + sum(bk));
                }
            }
            assertTrue(near((Double) g.get("cva").get("counterparty.recovery"), -v[0] / (1 - rc), 1e-12));
            assertTrue(near((Double) g.get("dva").get("own.recovery"), -v[1] / (1 - rb), 1e-12));
            if (sb > 0) {
                assertTrue(near((Double) g.get("fca").get("funding.borrow_spread") * sb, v[2], 1e-12));
            }
            assertTrue(near((Double) g.get("mva").get("im_spread") * ims, v[5], 1e-12));
            double[] gk = (double[]) g.get("kva").get("capital");
            double lin = 0;
            for (int i = 0; i < n; i++) {
                lin += gk[i] * cap[i];
            }
            assertTrue(near(lin, v[6], 1e-12), "kva linear in capital");
            double[] ge = (double[]) g.get("cva").get("ee");
            lin = 0;
            for (int i = 0; i < n; i++) {
                lin += ge[i] * ee[i];
            }
            assertTrue(near(lin, v[0], 1e-12), "cva linear in ee");
        }
    }

    @Test
    void wrtRules() {
        Map<String, Object> base = new LinkedHashMap<>();
        base.put("times", List.of(1.0));
        base.put("discount_factors", List.of(1.0));
        base.put("ee", List.of(1.0));
        base.put("ene", List.of(-1.0));
        base.put("counterparty", Map.of("hazard_rate", 0.01, "recovery", 0.4));
        base.put("own", Map.of("hazard_rate", 0.01, "recovery", 0.4));
        base.put("funding", Map.of("borrow_spread", 0.0, "lend_spread", 0.0, "exclude_dva_overlap", false));
        List<Object> bad = new ArrayList<>();
        bad.add(List.of());
        bad.add(List.of("ee", "ee"));
        bad.add(List.of("im"));
        bad.add(List.of("capital"));
        for (Object w : bad) {
            Map<String, Object> req = new LinkedHashMap<>();
            req.put("operation", "xva.adjustments.value");
            req.put("inputs", base);
            req.put("wrt", w);
            Map<?, ?> res = run(req);
            assertEquals("E_INPUT", ((Map<?, ?>) res.get("error")).get("code"), String.valueOf(w));
        }
        Map<String, Object> req = new LinkedHashMap<>();
        req.put("operation", "xva.adjustments.value");
        req.put("inputs", base);
        req.put("wrt", List.of("ene", "own.recovery"));
        Map<?, ?> g = (Map<?, ?>) ((Map<?, ?>) run(req).get("outputs")).get("gradient");
        assertEquals(List.of("own.recovery", "ene"), new ArrayList<>(((Map<?, ?>) g.get("dva")).keySet()));
    }
}
