"""Gallery page: P&L explain and calibration stability on real Treasury moves (R2). Used by tools/build_gallery.py.

Standard library only and no financial logic: tools/workflows/pnl_explain.py makes the CLI calls, and this file
draws what comes back. Inputs are a committed snapshot in docs/curves/data/pnl-explain.json (US Treasury par
yields are a US government work), so --check reruns the Python CLI offline. `--refresh-real` fetches a new snapshot.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "workflows"))
import common  # noqa: E402
import eod_curves  # noqa: E402
import pnl_explain  # noqa: E402

SLUG = "pnl-explain"
DAYS, TRADES = 10, 10


def fetch_inputs():
    year = dt.date.today().year
    rows = eod_curves.treasury(common.fetch(common.source_url("us-treasury-par-yields", year)))
    if len(rows) < DAYS + 1:
        rows = eod_curves.treasury(common.fetch(common.source_url("us-treasury-par-yields", year - 1))) + rows
    rows = rows[-(DAYS + 1):]
    tenors = set.intersection(*[{q["tenor"] for q in qs} for _, qs in rows])
    return {"history": [[d, [q for q in qs if q["tenor"] in tenors]] for d, qs in rows], "trades": TRADES,
            "fetched": dt.date.today().isoformat()}


def run(lang, inputs):
    hist = [(d, qs) for d, qs in inputs["history"]]
    trades, days, res = pnl_explain.run(hist, inputs["trades"], lang)
    bad = [k for k, v in res.items() if v["status"] != "ok"]
    if bad:
        raise SystemExit(f"{lang}: {len(bad)} cases failed, first {bad[0]}: {res[bad[0]]}")
    s = pnl_explain.summarise(trades, days, res)
    for d in s["explain"]:
        d.pop("trades")  # per-trade rows stay in the daily report; the page shows the book
    return s


def agreement(results):
    """Largest difference from Python across languages, per quantity."""
    ref, out = results["python"], {}
    for lang, s in results.items():
        if lang == "python":
            continue
        out[lang] = {
            "pnl_usd": max(max(abs(a[k] - b[k]) for k in ("full", "explained")) for a, b in zip(s["explain"], ref["explain"])),
            "condition": max(abs(a["condition"] - b["condition"]) for a, b in zip(s["calibration"], ref["calibration"])),
            "betas": max(max(abs(x - y) for x, y in zip(a["betas"], b["betas"])) for a, b in zip(s["calibration"], ref["calibration"])),
        }
    return out


def page(d, chart, table, versions):
    inputs, ref = d["inputs"], d["reference"]
    ex, cal = ref["explain"], ref["calibration"]
    lim = pnl_explain.LIMITS
    xs = list(range(1, len(ex) + 1))
    labels = ", ".join(f"{i} = {e['to']}" for i, e in zip(xs, ex))
    cap = f"Real data: US Treasury par yields, moves to {ex[-1]['to']}. {eod_curves.CURVE_LABEL} Synthetic sample book."
    pnl = chart("Book P&L per daily move: full revaluation against risk-based explain", "Move number", "USD", [
        {"name": "Full revaluation", "colour": 1, "shape": "points", "pts": [(x, e["full"], f"{e['from']} → {e['to']}: {e['full']:,.0f}") for x, e in zip(xs, ex)]},
        {"name": "Key-rate explain", "colour": 2, "shape": "points", "pts": [(x, e["explained"], f"{e['explained']:,.0f}") for x, e in zip(xs, ex)]}],
        cap, y_zero=True, x_lo=1)
    unexp = chart("Unexplained P&L as a share of full P&L", "Move number", "Percent", [
        {"name": "Unexplained / full", "colour": 1, "shape": "points",
         "pts": [(x, 100 * abs(e["unexplained"]) / max(abs(e["full"]), 1.0), f"{e['unexplained']:,.0f} USD") for x, e in zip(xs, ex)]}],
        cap, y_zero=True, x_lo=1)
    betas = chart("Robust Nelson-Siegel slope and curvature by day (level is in the table)", "Day number", "Percent", [
        {"name": f"β{i}", "colour": i, "shape": "line", "pts": [(j, c["betas"][i] * 100) for j, c in enumerate(cal, 1)]} for i in (1, 2)],
        cap, x_lo=1)
    ag = d["agreement"]
    ag_rows = [[lang, f"{v['pnl_usd']:.2e}", f"{v['condition']:.2e}", f"{v['betas']:.2e}"] for lang, v in sorted(ag.items())]
    ex_rows = [[f"{e['from']} → {e['to']}", f"{e['largest_move_bp']:+.1f}", f"{e['full']:,.0f}", f"{e['explained']:,.0f}", f"{e['unexplained']:,.0f}",
                f"{abs(e['unexplained']) / max(abs(e['full']), 1):.2%}"] for e in ex]
    cal_rows = [[c["date"], f"{c['condition']:.2f}", " / ".join(f"{b * 100:.3f}" for b in c["betas"]), f"{c['beta_step'] * 1e4:.1f}",
                 c["outliers"], f"{c['max_residual'] * 1e4:.1f}"] for c in cal]
    worst = max(abs(e["unexplained"]) / max(abs(e["full"]), 1.0) for e in ex)
    return f"""# Real data: P&L explain and calibration stability

<p class="note">Status: Implemented, not Validated. This page uses <strong>real public data</strong>: daily US Treasury par curves. {eod_curves.CURVE_LABEL} The swap book is synthetic, and nothing is traded. The thresholds are provisional until the R2 spec sets them.</p>

Snapshot of {len(ex)} daily moves from {ex[0]['from']} to {ex[-1]['to']} (fetched {inputs['fetched']}), {inputs['trades']} swaps from `tools/workflows/sample_book.py`, run from commit `{d['meta']['commit']}` by {versions}. Largest unexplained share: {worst:.2%}.

## What P&L explain tests

A desk checks every day that risk times the market move gives back the P&L from full revaluation (plan 11.2.1). If it doesn't, either the risk or the pricing is wrong. For each move from day t to day t+1:

- full = PV on the curve built from day t+1 quotes, minus PV on the curve from day t quotes, both as of day t;
- explained = the sum over key rates of key-rate DV01 on day t, times the quote move in bp;
- unexplained = full minus explained. Second-order terms (convexity, cross-gamma) are what remain on a clean run.

Both curves of a pair are as of day t, so the trade does not age: this is the market-move P&L, and theta is out of scope. The same check runs daily on 20 moves and 20 trades in `tools/workflows/pnl_explain.py`, with provisional thresholds of {lim['explain']['book_rel']:.0%} of full P&L plus {lim['explain']['book_abs_per_dv01']} × book DV01 ([`pnl_explain.json`](../../tools/workflows/pnl_explain.json)).

{pnl}

{unexp}

Move numbers: {labels}.

{table(['Move', 'Largest quote move (bp)', 'Full (USD)', 'Explained (USD)', 'Unexplained (USD)', 'Unexplained / full'], ex_rows)}

## Calibration stability

Each day, the curve's calibration report gives the condition number of the Jacobian of pillar zero rates against quotes (`calib.curve_report`); a large number means the quotes barely pin a pillar. A robust Nelson-Siegel fit (`calib.curve.robust`, tau 2, Huber delta 5 bp) to the day's zero rates shows how much a smooth summary of the curve moves from day to day. Nelson-Siegel parameters are poorly identified, so a large step with small residuals means a flat objective, not a broken curve. Outliers are the maturities the Huber loss down-weights.

{betas}

{table(['Date', 'Condition number', 'β0 / β1 / β2 (%)', 'Largest β step (bp)', 'Outliers', 'Largest residual (bp)'], cal_rows)}

## Four-language agreement

Largest difference from the Python CLI over every move and day.

{table(['Language', 'Book P&L (USD)', 'Condition number', 'Nelson-Siegel β'], ag_rows)}

## Limits

- The curve is a proxy: Treasury par yields are bootstrapped as SOFR OIS par rates. Real SOFR swap moves would differ.
- Ten moves on one snapshot. The daily job keeps the longer record, on branch `forward-log`.
- The thresholds are infra's provisional numbers, not a spec.
- Theta and carry are out of scope, by construction.

## Data notices

- Source: US Department of the Treasury.
"""
