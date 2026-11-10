package org.quantforge.cli;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;
import org.quantforge.vol.FxSmile;

/** Stage E3: FX smile (fx-smile.md). */
final class OpsFxSmile {
    private OpsFxSmile() {}

    private static FxSmile.Market market(In in) {
        return new FxSmile.Market(in.real("spot"), in.real("expiry_years"), in.real("domestic_rate"),
                in.real("foreign_rate"));
    }

    private static double phi(In in) {
        return Black.phi(in.choice("option_type", Black.OptionType.class));
    }

    private static void positive(double x, String key) {
        if (!(x > 0.0)) {
            throw new QfError("E_DOMAIN", key + " must be above 0", key);
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("fx.option.price", in -> {
            FxSmile.Market m = market(in);
            double k = in.real("strike");
            double v = in.real("vol");
            double phi = phi(in);
            double n = in.gate(in.real("notional"));
            FxSmile.checkMarket(m, v);
            positive(k, "strike");
            positive(n, "notional");
            FxSmile.Price p = FxSmile.price(m, k, v, phi, n);
            return Operations.out("price", p.price(), "premium_pct_foreign", p.premiumPctForeign(), "forward",
                    p.forward(), "delta", p.delta(), "gamma", p.gamma(), "vega", p.vega());
        });
        table.put("fx.delta.from_strike", in -> {
            FxSmile.Market m = market(in);
            double k = in.real("strike");
            double v = in.real("vol");
            double phi = in.gate(phi(in));
            FxSmile.checkMarket(m, v);
            positive(k, "strike");
            Map<String, Object> d = new LinkedHashMap<>();
            for (FxSmile.DeltaType t : FxSmile.DeltaType.values()) {
                d.put(t.name(), FxSmile.delta(m, k, v, phi, t));
            }
            return Operations.out("deltas", d);
        });
        table.put("fx.delta.to_strike", in -> {
            FxSmile.Market m = market(in);
            double v = in.real("vol");
            double phi = phi(in);
            double delta = in.real("delta");
            FxSmile.DeltaType t = in.gate(in.choice("delta_type", FxSmile.DeltaType.class));
            FxSmile.checkMarket(m, v);
            return Operations.out("strike", FxSmile.strike(m, delta, v, phi, t));
        });
        table.put("fx.atm.strike", in -> {
            FxSmile.Market m = market(in);
            double v = in.real("vol");
            FxSmile.AtmType a = in.choice("atm_type", FxSmile.AtmType.class);
            FxSmile.DeltaType t = in.gate(in.choice("delta_type", FxSmile.DeltaType.class));
            FxSmile.checkMarket(m, v);
            return Operations.out("strike", FxSmile.atmStrike(m, v, a, t));
        });
        table.put("fx.smile.from_quotes", in -> {
            FxSmile.Market m = market(in);
            double atm = in.real("atm_vol");
            double rr = in.real("rr");
            double bf = in.real("bf");
            double delta = in.real("delta");
            FxSmile.DeltaType t = in.choice("delta_type", FxSmile.DeltaType.class);
            FxSmile.AtmType a = in.gate(in.choice("atm_type", FxSmile.AtmType.class));
            FxSmile.checkMarket(m, atm);
            if (!(delta > 0.0 && delta < 0.5)) {
                throw new QfError("E_DOMAIN", "delta must be in (0, 0.5)", "delta");
            }
            double cv = atm + bf + rr / 2.0;
            double pv = atm + bf - rr / 2.0;
            positive(cv, "call_vol");
            positive(pv, "put_vol");
            return Operations.out("atm_strike", FxSmile.atmStrike(m, atm, a, t), "call_vol", cv, "put_vol", pv,
                    "call_strike", FxSmile.strike(m, delta, cv, 1.0, t), "put_strike",
                    FxSmile.strike(m, -delta, pv, -1.0, t));
        });
    }
}
