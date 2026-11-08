package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;
import org.quantforge.vol.Heston;
import org.quantforge.vol.Slv;
import org.quantforge.vol.Surfaces;

/** Stage E2: Heston, Bates, Merton, SLV leverage (heston-family.md). */
final class StageE2 {
    private StageE2() {}

    private static Heston.Params heston(In in) {
        In h = in.object("heston");
        return new Heston.Params(h.real("v0"), h.real("kappa"), h.real("theta"), h.real("xi"), h.real("rho"));
    }

    private static Heston.Jumps jumps(In in) {
        In j = in.object("jumps");
        return new Heston.Jumps(j.real("intensity"), j.real("mean_log_jump"), j.real("log_jump_vol"));
    }

    private static void positive(double x, String key) {
        if (!(x > 0.0)) {
            throw new QfError("E_DOMAIN", key + " must be above 0", key);
        }
    }

    /** spot, expiry_years, rate, dividend_yield, option_type, strikes: shape before values. */
    private record Common(double spot, double t, double r, double q, boolean call, double[] strikes) {
        static Common read(In in) {
            Common c = new Common(in.real("spot"), in.real("expiry_years"), in.real("rate"), in.real("dividend_yield"),
                    in.choice("option_type", Black.OptionType.class) == Black.OptionType.CALL, in.reals("strikes"));
            in.limit(c.strikes.length > OpsForward.MAX_LIST, "strikes"); // C10 (ruling E-A35)
            return c;
        }

        void check() {
            if (strikes.length == 0) {
                throw new QfError("E_INPUT", "strikes is empty", "strikes");
            }
            positive(spot, "spot");
            positive(t, "expiry_years");
            for (double k : strikes) {
                positive(k, "strikes");
            }
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("vol.heston.price", in -> {
            Common c = Common.read(in);
            Heston.Params h = in.gate(heston(in));
            c.check();
            h.check();
            return Operations.out("prices", OpsSmile.list(Heston.prices(c.spot, c.t, c.r, c.q, c.call, c.strikes, h,
                    null)));
        });
        table.put("vol.bates.price", in -> {
            Common c = Common.read(in);
            Heston.Params h = heston(in);
            Heston.Jumps j = in.gate(jumps(in));
            c.check();
            h.check();
            j.check();
            return Operations.out("prices", OpsSmile.list(Heston.prices(c.spot, c.t, c.r, c.q, c.call, c.strikes, h,
                    j)));
        });
        table.put("vol.merton.price", in -> {
            Common c = Common.read(in);
            double vol = in.real("vol");
            Heston.Jumps j = in.gate(jumps(in));
            c.check();
            positive(vol, "vol");
            j.check();
            return Operations.out("prices", OpsSmile.list(Heston.merton(c.spot, c.t, c.r, c.q, c.call, c.strikes, vol,
                    j)));
        });
        table.put("vol.heston.cf", in -> {
            double t = in.real("expiry_years");
            Heston.Params h = heston(in);
            double[] u = in.reals("u");
            in.limit(u.length > OpsForward.MAX_LIST, "u"); // C10 (ruling E-A35)
            in.gate();
            if (u.length == 0) {
                throw new QfError("E_INPUT", "u is empty", "u");
            }
            positive(t, "expiry_years");
            h.check();
            for (double x : u) {
                if (!(x >= 0.0)) {
                    throw new QfError("E_DOMAIN", "u must not be negative", "u");
                }
            }
            List<Object> re = new ArrayList<>();
            List<Object> im = new ArrayList<>();
            for (double x : u) {
                Heston.C z = Heston.cf(new Heston.C(x, 0.0), t, h);
                re.add(z.re());
                im.add(z.im());
            }
            return Operations.out("re", re, "im", im);
        });
        table.put("vol.slv.leverage", in -> {
            double s = in.real("spot");
            double t = in.real("expiry_years");
            double r = in.real("rate");
            double q = in.real("dividend_yield");
            Heston.Params h = heston(in);
            List<Surfaces.Slice> slices = new ArrayList<>();
            for (In x : in.objects("slices")) {
                slices.add(new Surfaces.Slice(x.real("expiry_years"), OpsSmile.svi(x)));
            }
            In g = in.object("grid");
            Slv.Grid grid = new Slv.Grid(g.integer("nx"), g.integer("nv"), g.integer("nt"), g.real("x_min"),
                    g.real("x_max"), g.real("v_max"));
            in.limit(slices.size() > Surfaces.MAX_SLICES, "slices");
            in.limit(grid.overLimit(), "grid");
            in.gate();
            // all E_INPUT rules first, then E_DOMAIN, each in input order (ruling E-A37)
            Surfaces.checkSliceShape(slices);
            grid.checkShape(s);
            positive(s, "spot");
            positive(t, "expiry_years");
            h.check();
            Surfaces.checkSliceValues(slices);
            grid.checkValues();
            Slv.Result res = Slv.leverage(s, t, r, q, h, slices, grid);
            return Operations.out("x", OpsSmile.list(res.x()), "leverage", OpsSmile.list(res.leverage()), "mass",
                    res.mass());
        });
    }
}
