"""Tutorial 14: book lifecycle events, end-of-day marks, P&L explain.

  uv run --project python python examples/tutorials/t14_book.py         # Python
  python examples/tutorials/t14_book.py rust/target/release/quantforge  # or any other build

It sends the three cases of docs/getting-started/tutorial-14-book.md through examples/tutorials/qf.py,
to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys

from qf import runner

OPENING = [{"instrument": "SPX-C-6000", "quantity": 5.0, "average_cost": 42.0},
           {"instrument": "BOND-X", "quantity": 1000.0, "average_cost": 0.97}]
EVENTS = [
    {"date": "2026-11-02", "type": "TRADE", "instrument": "UST10", "quantity": 100.0, "price": 99.5},
    {"date": "2026-11-02", "type": "FIXING", "index": "SOFR", "value": 0.0431},
    {"date": "2026-11-03", "type": "TRADE", "instrument": "UST10", "quantity": 50.0, "price": 100.25},
    {"date": "2026-11-04", "type": "TRADE", "instrument": "UST10", "quantity": -120.0, "price": 100.5},
    {"date": "2026-11-20", "type": "DEFAULT", "instrument": "BOND-X", "recovery_price": 0.38},
    {"date": "2026-12-18", "type": "EXPIRY", "instrument": "SPX-C-6000", "settlement_price": 57.25},
]
SOURCES = [
    {"name": "VENDOR_A", "quotes": [{"instrument": "UST10", "date": "2026-11-10", "price": 99.75},
                                    {"instrument": "SPX", "date": "2026-11-07", "price": 6012.5}]},
    {"name": "VENDOR_B", "quotes": [{"instrument": "BUND10", "date": "2026-11-10", "price": 131.2},
                                    {"instrument": "UST10", "date": "2026-11-10", "price": 99.8},
                                    {"instrument": "SPX", "date": "2026-11-09", "price": 6020.0},
                                    {"instrument": "ILLIQ", "date": "2026-11-01", "price": 88.0}]},
]
MARKS = {"as_of": "2026-11-10", "instruments": ["UST10", "BUND10", "SPX", "ILLIQ"], "sources": SOURCES,
         "max_age_days": 3, "ipv": [{"instrument": "UST10", "price": 99.7}, {"instrument": "BUND10", "price": 130.0}],
         "ipv_threshold": 0.005}
TENORS = ["1W", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
RATES = [0.0387, 0.0386, 0.0383, 0.0377, 0.0365, 0.035, 0.0345, 0.035, 0.036, 0.0375, 0.039, 0.0395, 0.0385]
EXPLAIN = {"as_of": "2026-11-06", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF",
           "quotes_start": [{"tenor": t, "rate": r} for t, r in zip(TENORS, RATES)],
           "quotes_end": [{"tenor": t, "rate": r + 0.0001} for t, r in zip(TENORS, RATES)],
           "product": {"kind": "OIS", "trade": {"convention": "SOFR", "tenor": "2Y", "fixed_rate": 0.0345,
                                                "notional": 25_000_000.0, "side": "RECEIVE"}},
           "bump_bp": 1.0}


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    after, marks, x = batch(cli, [
        case("t14-life", "book.lifecycle.apply", {"positions": OPENING, "events": EVENTS}),
        case("t14-marks", "book.marks.resolve", MARKS),
        case("t14-explain", "risk.pnl.explain", EXPLAIN)])
    for p in after["positions"]:
        print(f"hold {p['instrument']} {p['quantity']:.0f} @ {p['average_cost']:.4f}")
    for r in after["realized_pnl"]:
        print(f"realised {r['instrument']:<10} {r['pnl']:10.2f}")
    print(f"realised total {after['total_realized']:.2f}, fixings kept {len(after['fixings'])}")
    for m in marks["marks"]:
        price = "-" if m["price"] is None else f"{m['price']:.2f} from {m['source']}"
        diff = "-" if m["ipv_diff"] is None else f"{m['ipv_diff']:+.6f}"
        print(f"mark {m['instrument']:<6} {m['status']:<8} {price:<20} ipv {diff} breach {m['ipv_breach']}")
    print(f"full P&L    {x['full_pnl']:.2f}")
    print(f"risk P&L    {x['risk_pnl']:.2f}")
    print(f"unexplained {x['unexplained']:.2f} (threshold {x['threshold']:.2f}) explained {x['explained']}")


if __name__ == "__main__":
    main(sys.argv[1:])
