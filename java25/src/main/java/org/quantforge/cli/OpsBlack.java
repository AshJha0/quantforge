package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;

/** vol.option.* */
final class OpsBlack {
    private OpsBlack() {}

    private static void absent(In in, String... keys) {
        for (String k : keys) {
            if (in.hasKey(k)) {
                throw new QfError("E_SCHEMA", k + " does not belong to this model", k);
            }
        }
    }

    static Black.Option option(In in) {
        Black.Model model = in.choice("model", Black.Model.class);
        double phi = Black.phi(in.choice("option_type", Black.OptionType.class));
        double strike = in.real("strike");
        double t = in.real("expiry_years");
        switch (model) {
            case BLACK_SCHOLES -> {
                absent(in, "forward", "discount_factor", "shift");
                return new Black.Option(model, phi, strike, t, in.real("spot"), in.real("rate"), in.real("yield"), 0.0, 0.0);
            }
            case BLACK_76 -> {
                absent(in, "spot", "rate", "yield");
                double shift = in.hasKey("shift") ? in.real("shift") : 0.0;
                return new Black.Option(model, phi, strike, t, in.real("forward"), 0.0, 0.0, in.real("discount_factor"), shift);
            }
            default -> {
                absent(in, "spot", "rate", "yield", "shift");
                return new Black.Option(model, phi, strike, t, in.real("forward"), 0.0, 0.0, in.real("discount_factor"), 0.0);
            }
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("vol.option.price", in -> {
            Black.Option o = option(in);
            double vol = in.real("vol");
            in.gate();
            o.check(vol);
            return Operations.out("price", Black.price(o, vol), "forward", o.forward());
        });
        table.put("vol.option.implied", in -> {
            Black.Option o = option(in);
            double price = in.real("price");
            in.gate();
            return Operations.out("vol", Black.implied(o, price));
        });
    }
}
