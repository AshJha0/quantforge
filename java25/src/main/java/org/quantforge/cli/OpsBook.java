package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.book.Book;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.FactorAttribution;

/** Stage F slice F5: the book domain and use case 4. Inputs are read before the gate. */
final class OpsBook {
    private OpsBook() {}

    private static final int MAX_LIST = 100_000;

    static void register(Map<String, Function<In, Out>> table) {
        table.put("book.lifecycle.apply", in -> {
            List<In> ps = in.objects("positions");
            in.limit(ps.size() > MAX_LIST, "positions");
            List<Book.Position> positions = new ArrayList<>();
            for (In p : ps) {
                positions.add(new Book.Position(p.string("instrument"), p.real("quantity"), p.real("average_cost")));
            }
            List<In> es = in.objects("events");
            in.limit(es.size() > MAX_LIST, "events");
            List<Book.Event> events = new ArrayList<>();
            for (In e : es) {
                LocalDate date = e.date("date");
                Book.EventType type = e.choice("type", Book.EventType.class);
                events.add(switch (type) {
                    case TRADE -> new Book.Event(date, type, e.string("instrument"), e.real("quantity"),
                            e.real("price"), null, null, null, null, null, null);
                    case FIXING -> new Book.Event(date, type, null, null, null, e.string("index"), e.real("value"),
                            null, null, null, null);
                    case EXPIRY -> new Book.Event(date, type, e.string("instrument"), null,
                            e.real("settlement_price"), null, null, null, null, null, null);
                    case DEFAULT -> new Book.Event(date, type, e.string("instrument"), null,
                            e.real("recovery_price"), null, null, null, null, null, null);
                    case ROLL -> new Book.Event(date, type, null, null, null, null, null, e.string("from"),
                            e.string("to"), e.real("from_price"), e.real("to_price"));
                });
            }
            in.gate();
            Book.Lifecycle r = Book.apply(positions, events);
            List<Map<String, Object>> po = new ArrayList<>();
            for (Book.Position p : r.positions()) {
                po.add(Operations.out("instrument", p.instrument(), "quantity", p.quantity(), "average_cost",
                        p.averageCost()).outputs());
            }
            List<Map<String, Object>> rp = new ArrayList<>();
            r.realized().forEach((k, v) -> rp.add(Operations.out("instrument", k, "pnl", v).outputs()));
            List<Map<String, Object>> fx = new ArrayList<>();
            for (Book.Fixing f : r.fixings()) {
                fx.add(Operations.out("index", f.index(), "date", f.date().toString(), "value", f.value()).outputs());
            }
            return Operations.out("positions", po, "realized_pnl", rp, "total_realized", r.totalRealized(),
                    "fixings", fx);
        });
        table.put("book.marks.resolve", in -> {
            LocalDate asOf = in.date("as_of");
            List<String> instruments = in.strings("instruments");
            long maxAge = in.integer("max_age_days");
            double threshold = in.real("ipv_threshold");
            List<In> ss = in.objects("sources");
            in.limit(ss.size() > MAX_LIST, "sources");
            List<Book.Source> sources = new ArrayList<>();
            for (In s : ss) {
                List<Book.Quote> quotes = new ArrayList<>();
                for (In q : s.objects("quotes")) {
                    quotes.add(new Book.Quote(q.string("instrument"), q.date("date"), q.real("price")));
                }
                sources.add(new Book.Source(s.string("name"), quotes));
            }
            Map<String, Double> ipv = new HashMap<>();
            if (in.hasKey("ipv")) {
                for (In q : in.objects("ipv")) {
                    ipv.put(q.string("instrument"), q.real("price"));
                }
            }
            in.gate();
            List<Map<String, Object>> marks = new ArrayList<>();
            for (Book.Mark m : Book.resolve(asOf, instruments, sources, maxAge, ipv, threshold)) {
                marks.add(Operations.out("instrument", m.instrument(), "price", m.price(), "source", m.source(),
                        "status", m.status(), "age_days", m.ageDays(), "ipv_diff", m.ipvDiff(),
                        "ipv_breach", m.ipvBreach()).outputs());
            }
            return Operations.out("marks", marks);
        });
        table.put("usecase.factor_attribution", in -> {
            double[] y = in.reals("portfolio_returns");
            double[][] f = in.anyMatrix("factor_returns");
            List<String> names = in.strings("factor_names");
            in.gate();
            if (names.isEmpty()) {
                throw new QfError("E_INPUT", "no factors", "factor_names");
            }
            FactorAttribution.Result r = FactorAttribution.attribute(y, f, names.size());
            return Operations.out("alpha", r.alpha(), "betas", r.betas(), "r_squared", r.rSquared(),
                    "contributions", r.contributions(), "mean_return", r.meanReturn(),
                    "residual_vol", r.residualVol(), "beta_se", r.betaSe());
        });
    }
}
