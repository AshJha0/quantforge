package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.EquityForward;

/** eq.forward.* */
final class OpsForward {
    private OpsForward() {}

    static final int MAX_LIST = 100;

    /** The inputs of eq.forward.outright as read. */
    record Input(double spot, LocalDate asOf, LocalDate expiry, StageB.CurveInput funding, StageB.CurveInput borrow,
                 List<EquityForward.Dividend> dividends) {
        EquityForward.Result solve() {
            if (spot <= 0.0) {
                throw new QfError("E_DOMAIN", "spot is not positive", "spot");
            }
            Curve f = funding.build();
            Curve b = borrow == null ? null : borrow.build();
            return EquityForward.outright(spot, asOf, expiry, f, b, dividends);
        }
    }

    static Input read(In in) {
        double spot = in.real("spot");
        LocalDate asOf = in.date("as_of");
        LocalDate expiry = in.date("expiry");
        StageB.CurveInput funding = StageB.curve(in, "funding_curve");
        StageB.CurveInput borrow = in.anyValue("borrow_curve") == null ? null : StageB.curve(in, "borrow_curve");
        List<In> list = in.objects("dividends");
        in.limit(list.size() > MAX_LIST, "dividends");
        List<EquityForward.Dividend> dividends = new ArrayList<>();
        for (In d : list) {
            dividends.add(new EquityForward.Dividend(d.date("ex_date"), d.real("amount")));
        }
        return new Input(spot, asOf, expiry, funding, borrow, dividends);
    }

    static List<EquityForward.Quote> quotes(In in) {
        List<In> list = in.objects("quotes");
        in.limit(list.size() > MAX_LIST, "quotes");
        List<EquityForward.Quote> out = new ArrayList<>();
        for (In q : list) {
            out.add(new EquityForward.Quote(q.real("strike"), q.real("call_bid"), q.real("call_ask"), q.real("put_bid"),
                    q.real("put_ask")));
        }
        return out;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("eq.forward.outright", in -> {
            Input i = read(in);
            in.gate();
            EquityForward.Result r = i.solve();
            return Operations.out("forward", r.forward(), "discount_factor", r.discountFactor(), "carry_factor",
                    r.carryFactor(), "pv_dividends", r.pvDividends());
        });
        table.put("eq.forward.flat", in -> {
            double spot = in.real("spot");
            double rate = in.real("rate");
            double borrow = in.real("borrow");
            double expiry = in.real("expiry_years");
            List<In> list = in.objects("dividends");
            in.limit(list.size() > MAX_LIST, "dividends");
            double[] t = new double[list.size()];
            double[] a = new double[t.length];
            for (int i = 0; i < t.length; i++) {
                t[i] = list.get(i).real("time_years");
                a[i] = list.get(i).real("amount");
            }
            in.gate();
            return Operations.out("forward", EquityForward.flat(spot, rate, borrow, expiry, t, a));
        });
        table.put("eq.forward.parity", in -> {
            List<EquityForward.Quote> q = quotes(in);
            Double d = in.nullableReal("discount_factor");
            in.gate();
            EquityForward.Parity p = EquityForward.parity(q, d);
            return Operations.out("forward", p.forward(), "discount_factor", p.discountFactor(), "max_residual",
                    p.maxResidual(), "outside_spread", p.outsideSpread());
        });
    }
}
