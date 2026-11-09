package org.quantforge.cli;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.RatesVol;

/** Stage E4: rates and inflation vol (rates-vol-cube.md). */
final class StageE4 {
    private StageE4() {}

    private static boolean normal(In in) {
        return switch (in.string("model")) {
            case "BLACK_76" -> false;
            case "BACHELIER" -> true;
            default -> throw new QfError("E_SCHEMA", "model must be BLACK_76 or BACHELIER", "model");
        };
    }

    private static boolean first(In in, String key, String a, String b) {
        String v = in.string(key);
        if (v.equals(a)) {
            return true;
        }
        if (v.equals(b)) {
            return false;
        }
        throw new QfError("E_SCHEMA", key + " must be " + a + " or " + b, key);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("rates.swaption.price_cube", in -> {
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput p = StageB.curve(in, "projection");
            In c = in.object("cube");
            RatesVol.Cube cube = new RatesVol.Cube(c.integers("expiries_months"), c.integers("tenors_months"),
                    c.anyMatrix("alpha"), c.anyMatrix("beta"), c.anyMatrix("rho"), c.anyMatrix("nu"));
            In t = in.object("trade");
            boolean payer = first(t, "type", "PAYER", "RECEIVER");
            long expiry = t.integer("expiry_months");
            long tenor = t.integer("tenor_months");
            double k = t.real("strike");
            double n = t.real("notional");
            in.gate();
            RatesVol.CubePrice r = RatesVol.priceCube(d.build(), p.build(), cube, payer, expiry, tenor, k, n);
            return Operations.out("price", r.price(), "forward_rate", r.forward(), "annuity", r.annuity(), "vol",
                    r.vol(), "sabr", Map.of("alpha", r.sabr().alpha(), "beta", r.sabr().beta(), "rho",
                            r.sabr().rho(), "nu", r.sabr().nu()));
        });
        table.put("rates.cap.strip", in -> {
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput p = StageB.curve(in, "projection");
            boolean normal = normal(in);
            long start = in.integer("start_months");
            double k = in.real("strike");
            long[] tenors = in.integers("cap_tenors_months");
            double[] flat = in.reals("flat_vols");
            double n = in.real("notional");
            in.gate();
            RatesVol.Strip s = RatesVol.strip(d.build(), p.build(), normal, start, k, tenors, flat, n);
            return Operations.out("caplet_vols", OpsSmile.list(s.capletVols()), "cap_prices",
                    OpsSmile.list(s.capPrices()));
        });
        table.put("rates.bondfut.option_price", in -> {
            double phi = first(in, "type", "CALL", "PUT") ? 1.0 : -1.0;
            double f = in.real("futures_price");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double df = in.real("discount_factor");
            double vol = in.real("vol");
            double size = in.gate(in.real("contract_size"));
            double price = RatesVol.futuresOption(phi, f, k, t, df, vol);
            return Operations.out("price", price, "contract_value", price * size / 100.0);
        });
        table.put("rates.bondfut.implied_vol", in -> {
            double phi = first(in, "type", "CALL", "PUT") ? 1.0 : -1.0;
            double f = in.real("futures_price");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double df = in.real("discount_factor");
            double premium = in.real("premium");
            double y = in.real("ctd_yield");
            double dm = in.gate(in.real("ctd_modified_duration"));
            double[] v = RatesVol.futuresImpliedVol(phi, f, k, t, df, premium, y, dm);
            return Operations.out("price_vol", v[0], "yield_vol", v[1]);
        });
        table.put("infl.cap.yoy_price", in -> {
            boolean normal = normal(in);
            boolean cap = first(in, "type", "CAP", "FLOOR");
            double k = in.real("strike");
            double n = in.real("notional");
            List<In> ps = in.objects("periods");
            RatesVol.YoyPeriod[] periods = new RatesVol.YoyPeriod[ps.size()];
            for (int i = 0; i < periods.length; i++) {
                In q = ps.get(i);
                periods[i] = new RatesVol.YoyPeriod(q.real("accrual"), q.real("discount_factor"),
                        q.real("yoy_forward"), q.real("expiry_years"), q.real("vol"));
            }
            in.gate();
            double[] c = RatesVol.yoyCaplets(normal, cap, k, n, periods);
            double sum = 0.0;
            for (double x : c) {
                sum += x;
            }
            return Operations.out("caplets", OpsSmile.list(c), "price", sum);
        });
        table.put("infl.cap.zc_price", in -> {
            boolean normal = normal(in);
            boolean cap = first(in, "type", "CAP", "FLOOR");
            double f = in.real("forward_index_ratio");
            double years = in.real("years");
            double k = in.real("strike");
            double df = in.real("discount_factor");
            double vol = in.real("vol");
            double n = in.gate(in.real("notional"));
            double[] r = RatesVol.zcCap(normal, cap, f, years, k, df, vol, n);
            return Operations.out("price", r[0], "strike_ratio", r[1]);
        });
    }
}
