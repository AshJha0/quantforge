package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.hedging.Slippage;

/** Stage I wave 4d: hedge slippage ({@code 08-hedging/hedge-slippage.md}), rulings I-36 to I-38. */
final class OpsHedgeSlippage {
    private OpsHedgeSlippage() {}

    private static final int MAX_ORDERS = 10_000;
    private static final long MAX_FILLS = 1_000_000;

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.slippage.report", OpsHedgeSlippage::report);
    }

    private static Map<String, Object> costs(Slippage.Costs c, boolean perOrder) {
        Map<String, Object> m = new LinkedHashMap<>();
        if (perOrder) {
            m.put("filled_quantity", c.filledQuantity());
            m.put("average_price", c.averagePrice()); // null when nothing was filled (I-37)
        }
        m.put("execution_cost", c.executionCost());
        m.put("opportunity_cost", c.opportunityCost());
        m.put("shortfall", c.shortfall());
        m.put("model_cost", c.modelCost());
        m.put("slippage", c.slippage());
        return m;
    }

    private static Out report(In in) {
        List<In> orderIn = in.objects("orders");
        List<Slippage.Order> orders = new ArrayList<>();
        long fills = 0;
        for (In o : orderIn) {
            List<Slippage.Fill> fl = new ArrayList<>();
            for (In f : o.objects("fills")) {
                fl.add(new Slippage.Fill(f.real("quantity"), f.real("price")));
            }
            fills += fl.size();
            orders.add(new Slippage.Order(o.real("quantity"), o.real("decision_price"), o.real("final_price"),
                    o.real("half_spread"), o.real("impact"), fl));
        }
        in.limit(orderIn.size() > MAX_ORDERS, "orders");
        in.limit(fills > MAX_FILLS, "fills");
        in.gate();
        Slippage.Report r = Slippage.report(orders);
        List<Object> per = new ArrayList<>();
        for (Slippage.Costs c : r.orders()) {
            per.add(costs(c, true));
        }
        return Operations.out("orders", per, "total", costs(r.total(), false));
    }
}
