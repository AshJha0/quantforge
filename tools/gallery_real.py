"""Real-data page for the Curves gallery (plan 11.5.3): the US Treasury par curve with sanity bands.

Used by tools/build_gallery.py. Standard library only and no financial logic: the bootstrap is a CLI call,
and the bands are comparisons from tools/workflows/sanity_bands.json. The inputs are a dated snapshot in
docs/curves/data/real-usd-treasury.json, so --check stays deterministic. `--refresh-real` fetches a new one.
Treasury par yields are a US government work. The SOFR fixing carries the NY Fed notice, which goes with the page.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "workflows"))
import common  # noqa: E402
import eod_curves  # noqa: E402
import sanity  # noqa: E402

SLUG = "real-usd-treasury"
LABEL = eod_curves.CURVE_LABEL


class Checks:
    def __init__(self):
        self.checks = []

    def check(self, name, level, ok, detail):
        self.checks.append({"check": name, "level": level, "ok": bool(ok), "detail": detail})


def fetch_inputs():
    year = dt.date.today().year
    ust = eod_curves.treasury(common.fetch(common.source_url("us-treasury-par-yields", year)))
    sf = eod_curves.sofr(common.fetch(common.source_url("nyfed-sofr", year)))
    return {"as_of": ust[-1][0], "quotes": ust[-1][1], "previous": {"as_of": ust[-2][0], "quotes": ust[-2][1]},
            "sofr": [list(x) for x in sf[-2:]], "fetched": dt.date.today().isoformat()}


def boot_case(inputs):
    return common.case("real", "rates.ois.bootstrap", {"convention": "SOFR", "as_of": inputs["as_of"], "quotes": inputs["quotes"],
                                                        "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"})


def run(lang, inputs, call_batch):
    """call_batch(lang, cases) -> list of results, as build_gallery.batch."""
    return call_batch(lang, [boot_case(inputs)])[0]["outputs"]


def bands(inputs, reference):
    c = Checks()
    sanity.check_quotes(c, "Par quotes", inputs["quotes"], inputs["previous"]["quotes"])
    sanity.check_fixings(c, "SOFR", [tuple(x) for x in inputs["sofr"]])
    rows = sanity.check_curve(c, "Curve", inputs["as_of"], reference["pillars"])
    sanity.check_front_end(c, "Front end", inputs["sofr"][-1][1], inputs["quotes"][0]["rate"])
    return c.checks, rows


def page(d, chart, table, status_versions):
    inputs, ref = d["inputs"], d["reference"]
    checks, rows = bands(inputs, ref)
    as_of = inputs["as_of"]
    cap = f"Real data: US Treasury par yields, {as_of}. {LABEL}"
    qt = [common.years(r[0], as_of) for r in rows]
    zero = chart("Zero rates against input par yields", "Years from as-of date", "Rate, %", [
        {"name": "Zero rate (cc)", "colour": 1, "shape": "line", "pts": [(t, r[3] * 100) for t, r in zip(qt, rows)]},
        {"name": "Par yield", "colour": 2, "shape": "points", "pts": [(t, q["rate"] * 100, f"{q['tenor']}: {q['rate'] * 100:.2f}%")
                                                                   for t, q in zip(qt, inputs["quotes"])]}], cap)
    steps, prev = [], 0.0
    for t, r in zip(qt, rows):
        steps += [(prev, r[4] * 100), (t, r[4] * 100)]
        prev = t
    fwd = chart("Forward rate between pillars", "Years from as-of date", "Rate, %", [
        {"name": "Forward (cc)", "colour": 1, "shape": "line", "pts": steps}], cap)
    moves = {q["tenor"]: (q["rate"] - p["rate"]) * 1e4 for q, p in zip(inputs["quotes"], inputs["previous"]["quotes"]) if q["tenor"] == p["tenor"]}
    band_rows = [[x["check"], x["level"], "ok" if x["ok"] else "**NOT OK**", x["detail"]] for x in checks]
    pillar_rows = [[r[0], f"{t:.3f}", f"{q['rate'] * 100:.2f}", f"{r[2]:.8f}", f"{r[3] * 100:.4f}", f"{r[4] * 100:.4f}", f"{moves.get(q['tenor'], 0):+.0f}"]
                   for t, r, q in zip(qt, rows, inputs["quotes"])]
    failed = sum(1 for x in checks if not x["ok"] and x["level"] == "fail")
    return f"""# Real data: US Treasury curve with sanity bands

<p class="note">Status: Implemented, not Validated. This page uses <strong>real public data</strong>, unlike the rest of the gallery. {LABEL} Par yields are fitted, not traded: this shows a working pipeline on real inputs, not a tradable curve. Nothing is traded.</p>

Snapshot of {as_of} (fetched {inputs['fetched']}), bootstrapped from commit `{d['meta']['commit']}` by {status_versions}. Four-language agreement: largest discount-factor gap {d['agreement']:.2e}. Bands: {len(checks)} checks, {failed} failed.

## Why bands

The bands in [`tools/workflows/sanity_bands.json`](../../tools/workflows/sanity_bands.json) are wide on purpose. They catch a broken feed, a wrong unit or a failed build, not a market move. The same checks run every business day in workflow (a), `tools/workflows/eod_curves.py`, which writes a dated report to branch `forward-log`.

{zero}

{fwd}

## Pillars

{table(['Pillar', 't (y)', 'Par yield (%)', 'Discount factor', 'Zero, cc (%)', 'Forward to pillar (%)', 'Day move (bp)'], pillar_rows)}

## Band checks

{table(['Check', 'Level', 'Result', 'Detail'], band_rows)}

## Limits

- Treasury par yields are bootstrapped as SOFR OIS par rates. The Treasury curve has a different credit, liquidity and day-count basis from SOFR swaps, so these are not SOFR discount factors.
- 1.5-month yields are left out, because the bootstrap takes standard tenors only.
- One date. The daily workflow keeps the history; this page is refreshed by hand with `python tools/build_gallery.py --refresh-real`.

## Data notices

- Source: US Department of the Treasury.
- {common.SOURCES['nyfed-sofr']['notice']}
"""
