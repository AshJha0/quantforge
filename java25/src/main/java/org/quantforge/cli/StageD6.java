package org.quantforge.cli;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.Bonds;
import org.quantforge.pricing.Inflation;

/** Stage D wave 3, D6: inflation curves and linkers. */
final class StageD6 {
    private StageD6() {}

    private static final Pattern MONTH = Pattern.compile("\\d{4}-(0[1-9]|1[0-2])");

    static YearMonth month(String text, String key) {
        if (!MONTH.matcher(text).matches()) {
            throw new QfError("E_SCHEMA", key + " must be YYYY-MM", key);
        }
        return YearMonth.parse(text);
    }

    /** Curve fields as read; checks wait for {@link #build()}. */
    private record CurveIn(YearMonth base, double cpi, long[] years, double[] rates, double[] season) {
        Inflation.CpiCurve build() {
            return new Inflation.CpiCurve(base, cpi, years, rates, season);
        }
    }

    private static CurveIn curve(In c) {
        YearMonth base = month(c.string("base_month"), "base_month");
        double cpi = c.real("base_cpi");
        List<In> q = c.objects("quotes");
        c.limit(q.size() > 100, "quotes");
        long[] y = new long[q.size()];
        double[] r = new double[y.length];
        for (int i = 0; i < y.length; i++) {
            y[i] = q.get(i).integer("years");
            r[i] = q.get(i).real("rate");
        }
        Object s = c.anyValue("seasonality");
        double[] season = s == null ? null : c.reals("seasonality");
        return new CurveIn(base, cpi, y, r, season);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("infl.curve.cpi", in -> {
            CurveIn c = curve(in);
            List<String> months = in.strings("months");
            in.limit(months.size() > 10_000, "months");
            long[] k = new long[months.size()];
            for (int i = 0; i < k.length; i++) {
                k[i] = Inflation.index(month(months.get(i), "months"));
            }
            in.gate();
            Inflation.CpiCurve curve = c.build();
            if (k.length == 0) {
                throw new QfError("E_INPUT", "no months", "months");
            }
            double[] out = new double[k.length];
            for (int i = 0; i < k.length; i++) {
                out[i] = curve.cpi(k[i]);
            }
            return Operations.out("cpi", out);
        });
        table.put("infl.zcis.pv", in -> {
            CurveIn c = curve(in.object("curve"));
            StageB.CurveInput d = StageB.curve(in, "discount");
            In t = in.object("trade");
            long years = t.integer("years");
            double k = t.real("fixed_rate");
            double n = t.real("notional");
            String side = t.string("side");
            if (!side.equals("RECEIVE_INFLATION") && !side.equals("PAY_INFLATION")) {
                throw new QfError("E_SCHEMA", "unknown side", "side");
            }
            LocalDate pay = t.date("payment_date");
            in.gate();
            Inflation.Zcis r = Inflation.zcis(c.build(), d.build(), years, k, n, side.equals("RECEIVE_INFLATION"), pay);
            return Operations.out("index_ratio", r.indexRatio(), "pv", r.pv());
        });
        table.put("infl.linker.price", in -> {
            Bonds.Bond b = StageD2.bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            double y = in.real("real_yield");
            double base = in.real("base_ref_cpi");
            List<In> fx = in.objects("cpi_fixings");
            in.limit(fx.size() > 10_000, "cpi_fixings");
            Map<Long, Double> fixings = new HashMap<>();
            for (In f : fx) {
                long m = Inflation.index(month(f.string("month"), "month"));
                if (fixings.put(m, f.real("value")) != null) {
                    throw new QfError("E_INPUT", "two fixings for one month", "cpi_fixings");
                }
            }
            in.gate();
            Inflation.Linker r = Inflation.linker(b, s, y, base, fixings);
            return Operations.out("ref_cpi", r.refCpi(), "index_ratio", r.ratio(), "real_clean", r.realClean(),
                    "real_accrued", r.realAccrued(), "nominal_clean", r.nominalClean(),
                    "nominal_accrued", r.nominalAccrued());
        });
        table.put("infl.linker.price_curve", in -> {
            Bonds.Bond b = StageD2.bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            double base = in.real("base_ref_cpi");
            CurveIn c = curve(in.object("curve"));
            StageB.CurveInput d = StageB.curve(in, "discount");
            in.gate();
            return Operations.out("nominal_dirty", Inflation.linkerCurve(b, s, base, c.build(), d.build()));
        });
    }
}
