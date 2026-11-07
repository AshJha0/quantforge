package org.quantforge.cli;

import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.pricing.EquityForward;
import org.quantforge.pricing.Pricing;
import org.quantforge.vol.Black;
import org.quantforge.vol.Greeks;

/** risk.vol.greeks, risk.vol.bump_greeks, vol.equity.price */
final class OpsGreeks {
    private OpsGreeks() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.vol.greeks", in -> {
            Black.Option o = OpsBlack.option(in);
            double vol = in.real("vol");
            in.gate();
            Greeks.Analytic g = Greeks.analytic(o, vol);
            return Operations.out("price", g.price(), "delta", g.delta(), "gamma", g.gamma(), "vega", g.vega(), "theta",
                    g.theta(), "rho", g.rho(), "vanna", g.vanna(), "volga", g.volga());
        });
        table.put("risk.vol.bump_greeks", in -> {
            Black.Option o = OpsBlack.option(in);
            double vol = in.real("vol");
            in.gate();
            Greeks.Bumped g = Greeks.bumped(o, vol);
            return Operations.out("delta", g.delta(), "gamma", g.gamma(), "vega", g.vega(), "vanna", g.vanna(), "volga",
                    g.volga());
        });
        table.put("vol.equity.price", in -> {
            OpsForward.Input i = OpsForward.read(in);
            double phi = Black.phi(in.choice("option_type", Black.OptionType.class));
            double strike = in.real("strike");
            double vol = in.real("vol");
            double q = in.real("quantity");
            double sign = in.choice("side", Pricing.FxSide.class) == Pricing.FxSide.BUY ? 1.0 : -1.0;
            String currency = in.string("currency");
            String snapshot = in.hasKey("snapshot_id") ? in.string("snapshot_id") : null;
            in.gate();
            EquityForward.Result r = i.solve();
            double t = java.time.temporal.ChronoUnit.DAYS.between(i.asOf(), i.expiry()) / 365.0;
            if (t == 0.0 || vol <= 0.0 || strike <= 0.0 || q <= 0.0) {
                throw new QfError("E_DOMAIN", "expiry, vol, strike or quantity");
            }
            double f = r.forward();
            double d = r.discountFactor();
            double c = r.carryFactor();
            double root = Math.sqrt(t);
            double d1 = (Math.log(f / strike) + vol * vol * t / 2.0) / (vol * root);
            double n = Normal.pdf(d1);
            double pv = sign * q * Black.lognormal(phi, f, strike, t, d, vol);
            Pricing.Valuation v = new Pricing.Valuation(pv, currency, "BLACK_76_EQUITY", snapshot, "EQUITY_FORWARD", i.asOf());
            return Operations.out("valuation", v.toJson(), "forward", f,
                    "delta", sign * q * d * phi * Normal.cdf(phi * d1) / c,
                    "gamma", sign * q * d * n / (f * vol * root * c * c),
                    "vega", sign * q * d * f * n * root);
        });
    }
}
