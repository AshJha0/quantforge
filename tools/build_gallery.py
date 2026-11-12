#!/usr/bin/env python3
"""Builds the Curves gallery in docs/curves/ from real CLI runs. Standard library only.

    python tools/build_gallery.py           # runs all four CLIs, rewrites data and pages
    python tools/build_gallery.py --check   # reruns the Python CLI, changes nothing
    python tools/build_gallery.py --refresh-real  # also fetches a new real-data snapshot (gallery_real.py)
    python tools/build_gallery.py --evidence-only # recounts golden evidence after golden-only changes; no CLI runs
    python tools/build_gallery.py --stage-e-only  # runs only the stage E pages, keeping other committed data

Commands come from conformance/runner/implementations.json, so the CLIs must be built first. This
file holds no financial logic: it sends cases, stores what comes back and draws it. Its only sums
are curve time, (date - as_of) / 365, unit changes (to percent and bp) and differences between
outputs. Pages are a pure function of docs/curves/data/*.json, so --check can also rebuild them.

Exit status: 0 done or check passed; 1 check failed or a CLI failed.
"""
import argparse
import calendar
import datetime as dt
import hashlib
import html
import json
import math
import os
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import resolve_command  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
import gallery_real  # noqa: E402
import gallery_pnl  # noqa: E402
import gallery_r2  # noqa: E402
import gallery_e  # noqa: E402
import gallery_f  # noqa: E402
import gallery_i  # noqa: E402

OUT = ROOT / "docs" / "curves"
DATA = OUT / "data"
LANGS = ("java", "cpp", "python", "rust")
NAMES = {"java": "Java", "cpp": "C++", "python": "Python", "rust": "Rust"}
# Tolerance class `interpolation` for curve data; the use case 2 limit for risk figures.
TOL = {"curve": (1e-10, 1e-8), "risk": (1e-2, 1e-6)}
SYNTHETIC = "Synthetic inputs, not market data."


# ---- running the CLIs ---------------------------------------------------------------------------

def call(lang, verb, text=""):
    # QF_IMPLEMENTATIONS overrides the file, e.g. for CLIs built in WSL (docs/developer-guides/r1-infra.md).
    config = Path(os.environ.get("QF_IMPLEMENTATIONS", ROOT / "conformance/runner/implementations.json"))
    impls = json.loads(config.read_text(encoding="utf-8"))
    base, cwd = resolve_command(impls[lang])
    p = subprocess.run(base + [verb], cwd=cwd, input=text.encode("utf-8"), capture_output=True, timeout=300)
    if p.returncode != 0:
        raise SystemExit(f"{lang} {verb} exited {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:500]}")
    return p.stdout.decode("utf-8")


def batch(lang, cases):
    """Sends cases in one process and returns their results, requiring status ok on each."""
    text = "".join(json.dumps(c, separators=(",", ":")) + "\n" for c in cases)
    rows = [json.loads(line) for line in call(lang, "batch", text).splitlines() if line.strip()]
    if len(rows) != len(cases):
        raise SystemExit(f"{lang}: sent {len(cases)} cases, got {len(rows)} results")
    for row in rows:
        if row.get("status") != "ok":
            raise SystemExit(f"{lang}: {row}")
    return rows


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


# ---- dates --------------------------------------------------------------------------------------

def add_months(day, months):
    y, m = divmod(day.year * 12 + day.month - 1 + months, 12)
    m += 1
    return dt.date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def years(date, as_of):
    return (dt.date.fromisoformat(date) - dt.date.fromisoformat(as_of)).days / 365


def grid_dates(as_of, last, pillars):
    """Quarterly dates plus every pillar, so no forward interval crosses a node."""
    start, end = dt.date.fromisoformat(as_of), dt.date.fromisoformat(last)
    days, k = set(pillars), 1
    while add_months(start, 3 * k) < end:
        days.add(add_months(start, 3 * k).isoformat())
        k += 1
    return sorted(days)


# ---- one curve ----------------------------------------------------------------------------------

def read_example(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def example_hash(name):
    return "sha256:" + hashlib.sha256(json.dumps(read_example(name), sort_keys=True).encode()).hexdigest()


def curve_series(lang, as_of, interpolation, pillars, day_count, dates=None):
    curve = {"as_of": as_of, "interpolation": interpolation, "pillars": pillars}
    dates = dates or grid_dates(as_of, pillars[-1]["date"], [p["date"] for p in pillars])
    cases = [case("grid", "rates.curve.discount", {"curve": curve, "dates": dates})]
    edges = [as_of] + dates
    cases += [case(f"fwd{i}", "rates.curve.forward", {"curve": curve, "start": a, "end": b, "day_count": day_count})
              for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    rows = batch(lang, cases)
    out = rows[0]["outputs"]
    return {"dates": dates, "discount_factors": out["discount_factors"], "zero_rates": out["zero_rates"],
            "forwards": [r["outputs"]["forward"] for r in rows[1:]]}


def bumped(inputs):
    new = json.loads(json.dumps(inputs))
    for q in new["quotes"]:
        q["rate"] += 0.0001
    return new


def rates_curve(lang, spec):
    example = read_example(spec["example"])
    inputs = example["inputs"]
    base = batch(lang, [example])[0]
    bump = batch(lang, [case("bump", example["operation"], bumped(inputs))])[0]
    series = curve_series(lang, inputs["as_of"], inputs["interpolation"], base["outputs"]["pillars"], spec["day_count"])
    up = curve_series(lang, inputs["as_of"], inputs["interpolation"], bump["outputs"]["pillars"], spec["day_count"],
                      series["dates"])
    res = {"pillars": base["outputs"]["pillars"], "max_repricing_error": base["diagnostics"].get("max_repricing_error"),
           **series, "bumped_zero_rates": up["zero_rates"]}
    if spec.get("risk"):
        out = batch(lang, [read_example(spec["risk"])])[0]["outputs"]
        res["risk"] = {k: out[k] for k in ("pv", "dv01", "key_rate", "residual_key_rate", "hedge_units")}
    return res


def fx_curve(lang, spec):
    example = read_example(spec["example"])
    inputs = example["inputs"]
    spot = batch(lang, [case("spot", "fx.spot_date", {"pair": inputs["pair"], "trade_date": inputs["as_of"]})])
    spot_date = spot[0]["outputs"]["spot_date"]
    start = dt.date.fromisoformat(spot_date)
    dates = [add_months(start, 3 * k).isoformat() for k in range(1, 41)]
    rows = batch(lang, [case(d, example["operation"], {**inputs, "value_date": d}) for d in dates])
    implied = batch(lang, [read_example(spec["implied"])])[0]["outputs"]["nodes"]
    return {"spot_date": spot_date, "dates": dates, "forwards": [r["outputs"]["forward"] for r in rows],
            "points": [r["outputs"]["points"] for r in rows], "implied": implied}


def flat(res, key):
    if key == "pillars":
        return [p["discount_factor"] for p in res["pillars"]]
    if key == "implied":
        return [n["basis_bp"] for n in res["implied"]]
    if key == "key_rate":
        return res["risk"]["key_rate"]
    return res[key]


def agreement(results, spec):
    keys = {"rates": [("pillars", "Pillar discount factors"), ("discount_factors", "Grid discount factors"),
                      ("zero_rates", "Zero rates"), ("forwards", "Forward rates"),
                      ("bumped_zero_rates", "Zero rates after +1 bp")],
            "fx": [("forwards", "Forward outrights"), ("points", "Forward points"), ("implied", "Basis, bp")]}[spec["kind"]]
    if spec.get("risk"):
        keys = keys + [("key_rate", "Key-rate DV01")]
    rows = []
    for key, label_text in keys:
        cols = [flat(results[lang], key) for lang in LANGS]
        rows.append({"output": label_text, "count": len(cols[0]),
                     "largest_difference": max(max(v) - min(v) for v in zip(*cols)),
                     "last": {lang: col[-1] for lang, col in zip(LANGS, cols)}})
    return rows


# ---- evidence, read from the golden files -------------------------------------------------------

def evidence(spec):
    op, convention = spec["golden_operation"], spec.get("convention")
    counts, total = {}, 0
    for path in sorted((ROOT / "datasets/golden/stage_b").glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            if c["operation"] != op or c["expected"].get("status") != "ok":
                continue
            if convention and c["inputs"].get("convention") != convention:
                continue
            key = f"{path.stem}: {', '.join(c['verified_by'])}"
            counts[key] = counts.get(key, 0) + 1
            total += 1
    return {"operation": op, "cases": total, "by_source": counts}


# ---- what the gallery covers --------------------------------------------------------------------

CURVES = {
    "sonia-ois": {
        "kind": "rates", "title": "SONIA OIS curve", "short": "SONIA OIS", "example": "ois_bootstrap.json",
        "day_count": "ACT_365F", "risk": "usecase_rates_hedge.json", "convention": "SONIA",
        "golden_operation": "rates.ois.bootstrap", "spec": "ois-curves.md",
        "idea": "SONIA is the sterling overnight rate. An overnight indexed swap (OIS) pays a fixed rate against that rate compounded daily, so a set of OIS quotes says what sterling paid later is worth today. The curve is whatever set of discount factors makes every quoted swap worth zero.",
        "formula": "Par rate `K = F / A`, with annuity `A = sum alpha_i D(p_i)` and floating leg `F = sum (D(s_i)/D(e_i) - 1) D(p_i)`. The solve finds `D` so that `K_j(curve) = quote_j` for every quote `j`. Here spot lag and payment lag are 0, the fixed leg is annual, and the day count is `ACT_365F`.",
        "oracle": "Pillars are compared with QuantLib `OISRateHelper` curves, and swap PVs with QuantLib and with Strata's swap pricer on the same curve. Strata's calibrator has not been run, so no curve here was built by it. The target is 1e-9 on pillars; the oracle's measured gap to QuantLib is within 2e-11 (`specifications/02-curves/stage-b-targets.md`).",
        "limits": ["Exact repricing shows the solve works. It would do so on any coherent quotes, and says nothing about fit to a market.",
                   "Log-linear interpolation of discount factors gives flat forwards between pillars, so the forward chart is a staircase by construction.",
                   "No meeting-date steps, turn-of-year effects, or lookback, lockout and observation shift: those are stage D."],
    },
    "sofr-ois": {
        "kind": "rates", "title": "SOFR OIS curve (minimal)", "short": "SOFR OIS (minimal)", "example": "ois_bootstrap_sofr.json",
        "day_count": "ACT_360", "convention": "SOFR", "golden_operation": "rates.ois.bootstrap", "spec": "ois-curves.md",
        "idea": "SOFR is the US dollar overnight secured rate. The method is the same as for SONIA, with dollar conventions: trades start two business days out and pay two business days after each period ends. This is the minimal SOFR of stage B. Full SOFR is stage D.",
        "formula": "As for SONIA: `K = F / A`, `F = sum (D(s_i)/D(e_i) - 1) D(p_i)`, solved so that every quote reprices. Spot lag 2, payment lag 2, annual fixed leg, `ACT_360`. The floating leg is never telescoped to `D(s_0) - D(e_n)`: with a payment lag that form is wrong, by about 1.1e-4 per unit on 10Y.",
        "oracle": "As for SONIA: QuantLib for pillars, QuantLib and Strata's pricer for swap PVs, and Strata's calibrator not run. Target and measured gap are in `specifications/02-curves/stage-b-targets.md`.",
        "limits": ["Each pillar sits at the swap's last payment date, so pillar dates fall after the plain tenor date.",
                   "The first pillar is about two weeks out, and the segment back to the as-of date has no quote of its own.",
                   "Log-linear interpolation gives a staircase of forwards. Exact repricing says nothing about a market."],
    },
    "usd-term-3m": {
        "kind": "rates", "title": "USD-TERM-3M projection curve", "short": "USD-TERM-3M projection", "example": "projection_bootstrap.json",
        "day_count": "ACT_360", "golden_operation": "rates.projection.bootstrap", "spec": "projection-and-fra.md",
        "idea": "Multi-curve means forecasting a rate on one curve and discounting on another. This curve forecasts a three-month term rate, while the SOFR curve discounts. The index `USD-TERM-3M` is itself synthetic: it exists to test multi-curve code, and no market index is implied.",
        "formula": "Deposits and FRAs: model rate `(P(s)/P(e) - 1)/alpha`, with `P` the projection curve. Swaps: par rate `F/A`, with `A = sum alpha_i D(e_i)` on the fixed leg and `F = sum (P(s_j)/P(e_j) - 1) D(e_j)` on the quarterly floating leg. `D` stays fixed, and `P` is solved so that each quote reprices.",
        "oracle": "Pillars are compared with QuantLib `DepositRateHelper`, `FraRateHelper` and `SwapRateHelper` with exogenous discounting, and the oracle's measured gap is within 1e-10. The tenor basis operation has hand replay only. On an as-of date that is not a business day QuantLib disagrees with itself, so those dates have no outside check.",
        "limits": ["The discount curve in the example file is the stored SOFR curve, the same values as the golden SOFR case. It does not change in the +1 bp chart: only the projection quotes move.",
                   "The curve stops at 10Y, its last quote.",
                   "The first pillar is three months after spot, so the segment before it has no quote of its own."],
    },
    "gbpusd-fx-forward": {
        "kind": "fx", "title": "GBPUSD FX forward curve", "short": "GBPUSD FX forward", "example": "fx_forward_outright.json",
        "implied": "fx_curve_implied.json", "golden_operation": "fx.forward.outright", "spec": "fx.md",
        "idea": "A rate of 1.28 means 1 GBP costs 1.28 USD. Holding sterling for a year and holding dollars for a year must come to the same thing once the forward is fixed, so the forward follows from spot and the two discount curves.",
        "formula": "`F(T) = S A(T) / B(T)`, with `A(T) = D_base(T)/D_base(sp)`, `B(T) = D_quote(T)/D_quote(sp)` and `sp` the spot date. Points are `(F - S)/pip`, with a pip of 0.0001.",
        "oracle": "Per `specifications/stage-b-rulings.md`, outright points are analytic formulas with no outside library. QuantLib checks the spot dates, implied ratios (`FxSwapRateHelper`), and forward PV and delta (`FxForward`, a different operation from the one charted here). Basis is analytic.",
        "limits": ["The value dates charted are plain quarterly dates from spot, some of which may not be business days. `fx.forward.outright` does not require one.",
                   "The input forward points are constructed to exercise the basis calculation. They have the opposite sign to the curve forwards, which is why the basis is near 75 bp. No market is implied.",
                   "Basis here is taken straight from quotes. A curve built from basis swaps is stage D."],
    },
}

# Curves named in the plan's stage rows that have no page. Stage from the plan.
# Stage D curves are in STAGE_D below, each with a planned page.
# Each row: name, status, stage, evidence. A Planned row must not name an operation that exists in
# specifications/name-map.json; tools/test_tools.py and quality_gate check this against the README table.
PLANNED = [
    ("Financing term structures", "Partly done", "D",
     "Repo financing is done (`repo.forward`, `repo.implied_rate` and the implied financing spread; see the repo row). "
     "Ruling D22 keeps borrow and financing as flat rates over the funding curve; financing term structures are not yet scheduled"),
    ("Liquidity curves", "Planned", "H", "None yet"),
]

# Stage D curves. Each gets a page: a planned page until `cli` names a CLI operation and a renderer
# is registered for its `kind`, then the renderer's page. Text here is plain description, no numbers.
STAGE_D = {
    "ois-full": {"kind": "stage-d", "title": "OIS curves: full SOFR, ESTR and SONIA", "short": "Full SOFR, ESTR, SONIA OIS", "cli": "rates.ois.bootstrap", "examples": {"rates.ois.bootstrap": "estr_ois_d.json", "rates.ois.compound_dated": "real_sofr_compound_2026_10.json"},
                 "real": {"real_sofr_compound_2026_10.json": "Real data: SOFR fixings from 2026-09-21 to 2026-11-05, from the Federal Reserve Bank of New York markets API, fetched 2026-11-07, converted from percent to decimal (the only modification). The SOFR data is subject to the Terms of Use posted at newyorkfed.org; the New York Fed does not endorse this use, and SOFR is calculated using data licensed from DTCC Solutions LLC."},
                 "shows": "Discount factors and forwards, with meeting-date steps and observation conventions, and compounding of published overnight fixings. The ESTR payment lag of 2 days is a library choice, from Strata 2.12.78, not a market standard; TP ICAP terms use 1 (ruling R1-2)."},
    "bond-fit": {"kind": "stage-d", "title": "Bond and sovereign curve fits", "short": "Bond and sovereign fits", "cli": "bond.fit.nelson_siegel", "examples": {"bond.fit.nelson_siegel": "bond_fit_ns_d.json"},
                 "shows": "A fitted yield curve against bond yields, with residuals per bond."},
    "repo": {"kind": "stage-d", "title": "Repo and special repo curves", "short": "Repo and special repo", "cli": "repo.forward", "examples": {"repo.forward": "repo_forward_d.json"},
             "shows": "General collateral repo rates by term, and specials against them."},
    "cross-currency": {"kind": "stage-d", "title": "Cross-currency basis curves", "short": "Cross-currency", "cli": "fx.xccy.bootstrap", "examples": {"fx.xccy.bootstrap": "xccy_bootstrap_d.json"},
                       "shows": "Basis by tenor and the FX forwards it implies, on a synthetic constant-notional basis swap, not a market-implied curve. The market's mark-to-market resetting swap is edge-case register row E13, out of scope until stage F (ruling R1-1)."},
    "cds": {"kind": "stage-d", "title": "Credit curves and ISDA CDS", "short": "Credit and ISDA CDS", "cli": "credit.cds.bootstrap", "examples": {"credit.cds.bootstrap": "cds_bootstrap_d.json"},
            "shows": "Survival probabilities and hazard rates from CDS quotes. Every credit operation needs a `LOG_LINEAR_DF` discount curve, the ISDA flat-forward rule; anything else is `E_INPUT` (ruling R1-4)."},
    "dividend-borrow": {"kind": "stage-d", "title": "Dividend and borrow curves", "short": "Dividend and borrow", "cli": "eq.dividend.implied", "examples": {"eq.dividend.implied": "dividend_implied_d.json", "eq.borrow.implied": "borrow_implied_d.json"},
                        "shows": "Dividend schedules and borrow cost by term, and their effect on equity forwards."},
    "inflation": {"kind": "stage-d", "title": "Inflation curves, with seasonality", "short": "Inflation, with seasonality", "cli": "infl.curve.cpi", "examples": {"infl.curve.cpi": "inflation_cpi_d.json"},
                  "shows": "Forward index levels with and without the seasonal adjustment."},
    "caps-swaptions": {"kind": "stage-d", "title": "Cap surface and swaption cube", "short": "Caps and swaptions", "cli": "rates.cap.price", "examples": {"rates.cap.price": "cap_price_d.json", "rates.swaption.price": "swaption_price_d.json"},
                       "shows": "Cap volatilities by strike and expiry, and swaption volatilities by expiry, tenor and strike. The conventions are stylised: a synthetic term index, no fixing lag and an annual 30/360 fixed leg (ruling R1-5)."},
    "commodities": {"kind": "stage-d", "title": "Commodity forward curves, with seasonality and storage carry", "short": "Commodity forwards", "cli": "cmdty.curve.forward", "examples": {"cmdty.curve.forward": "commodity_forward_d.json", "cmdty.storage.carry": "commodity_carry_d.json"},
                    "shows": "Forward prices by delivery month, with seasonality and carry shown apart."},
    "sector-rating": {"kind": "stage-d", "title": "Sector and rating curves", "short": "Sector and rating curves", "golden": "stage_d", "cli": "credit.curve.composite", "examples": {"credit.curve.composite": "credit_composite_d.json"},
                      "shows": "A sector or rating curve built as the weighted average of constituent CDS spread curves, times a rating multiplier (`scale`, 1 for the sector itself), then bootstrapped to survival probabilities with the ISDA rules (`specifications/04-pricing/credit.md`). The constituents and weights are synthetic."},
    "funding": {"kind": "stage-d", "stage": "F", "golden": "stage_f", "title": "Funding curve", "short": "Funding curve", "cli": "rates.funding.curve", "examples": {"rates.funding.curve": "funding_curve_f.json"},
                "shows": "Unsecured funding: the OIS curve times a spread factor, `D_f(t) = D_ois(t) exp(-integral of s)`, with the spread `s` piecewise flat between the dates of simple ACT/360 funding quotes. It discounts uncollateralised cash flows and feeds FVA (`specifications/02-curves/joint-solve-and-funding.md`)."},
    "mbs": {"kind": "stage-d", "title": "MBS prepayment and valuation curves", "short": "MBS", "cli": "mbs.cashflows", "examples": {"mbs.cashflows": "mbs_cashflows_d.json"},
            "shows": "Prepayment speeds by month and the resulting cash flows."},
}

# Renderer hooks: kind -> function(slug, spec, data) returning page text. A language session that ships a
# stage D CLI adds its renderer with @renderer("kind") and sets `cli` above.
RENDERERS = {}


def renderer(kind):
    def register(fn):
        RENDERERS[kind] = fn
        return fn
    return register


def is_live(spec):
    return bool(spec.get("cli")) and spec["kind"] in RENDERERS


def planned_page(slug, spec):
    return f"""# {spec['title']}

<p class="note">Status: Planned, stage D (in progress). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it will show

{spec['shows']}

## When this page fills in

When a CLI operation for this curve exists in all four languages, `tools/build_gallery.py` gets a renderer for kind `{spec['kind']}` and this page is generated from real CLI output, like the stage B and C pages. See [the gallery index](README.md).
"""


# ---- charts -------------------------------------------------------------------------------------

W, H, ML, MR, MT, MB = 480, 300, 54, 14, 46, 46
COLOUR = {1: "var(--c1)", 2: "var(--c2)"}


def ticks(lo, hi, n=5):
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    return [round(i * step, 10) for i in range(math.floor(lo / step), math.ceil(hi / step) + 1)]


def label(v):
    return f"{v:.10g}"


def frame(title, xlabel, ylabel, x_ticks, y_ticks, sx, sy, legend, xtext=None):
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}, synthetic data" xmlns="http://www.w3.org/2000/svg" '
           'style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor">',
           f'<text x="{ML}" y="15" style="font-weight:600;font-size:13px">{html.escape(title)}</text>']
    for v in y_ticks:
        y = sy(v)
        out.append(f'<line x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:var(--line)"/>')
        out.append(f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end">{label(v)}</text>')
    for v in x_ticks:
        out.append(f'<text x="{sx(v):.1f}" y="{H - MB + 16}" text-anchor="middle">{xtext(v) if xtext else label(v)}</text>')
    out.append(f'<text x="{(ML + W - MR) / 2}" y="{H - 10}" text-anchor="middle">{html.escape(xlabel)}</text>')
    out.append(f'<text transform="translate(12 {(MT + H - MB) / 2}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    out.append(f'<text x="{W - MR}" y="{H - 10}" text-anchor="end" style="font-style:italic">synthetic</text>')
    x = ML
    for name, colour, shape in legend:
        if shape == "line":
            out.append(f'<line x1="{x}" x2="{x + 16}" y1="29" y2="29" style="stroke:{COLOUR[colour]};stroke-width:2"/>')
        elif shape == "bar":
            out.append(f'<rect x="{x}" y="24" width="14" height="10" rx="2" style="fill:{COLOUR[colour]}"/>')
        else:
            out.append(f'<circle cx="{x + 8}" cy="29" r="4" style="fill:{COLOUR[colour]}"/>')
        out.append(f'<text x="{x + 21}" y="33">{html.escape(name)}</text>')
        x += 30 + 6.2 * len(name)
    return out


def chart(title, xlabel, ylabel, series, caption, y_zero=False, x_lo=0):
    """series: dicts of name, colour, shape (line or points), pts [(x, y)] or [(x, y, tip)]."""
    xs = [p[0] for s in series for p in s["pts"]]
    ys = [p[1] for s in series for p in s["pts"]] + ([0] if y_zero else [])
    x_ticks, y_ticks = ticks(x_lo, max(xs)), ticks(min(ys), max(ys))

    def sx(v):
        return ML + (v - x_ticks[0]) / (x_ticks[-1] - x_ticks[0]) * (W - ML - MR)

    def sy(v):
        return H - MB - (v - y_ticks[0]) / (y_ticks[-1] - y_ticks[0]) * (H - MB - MT)

    legend = [(s["name"], s["colour"], "dot" if s["shape"] == "points" else "line") for s in series]
    out = frame(title, xlabel, ylabel, x_ticks, y_ticks, sx, sy, legend if len(series) > 1 else [])
    for s in series:
        c = COLOUR[s["colour"]]
        if s["shape"] == "points":
            for p in s["pts"]:
                tip = f"<title>{html.escape(p[2])}</title>" if len(p) > 2 else ""
                out.append(f'<circle cx="{sx(p[0]):.1f}" cy="{sy(p[1]):.1f}" r="4" style="fill:{c};stroke:var(--bg);stroke-width:1">{tip}</circle>')
            continue
        path = " ".join(f"{sx(p[0]):.1f},{sy(p[1]):.1f}" for p in s["pts"])
        out.append(f'<polyline points="{path}" style="fill:none;stroke:{c};stroke-width:2;stroke-linejoin:round"/>')
    return wrap(out, caption)


def smile_chart(title, expiries, caption, xlabel="Strike"):
    """expiries: [{"name", "strikes", "vols"}] taken from CLI output. Refuses empty or ragged input."""
    if not expiries:
        raise ValueError("no CLI output to chart")
    series = []
    for i, e in enumerate(expiries):
        if not e["strikes"] or len(e["strikes"]) != len(e["vols"]):
            raise ValueError(f"smile {e.get('name')}: strikes and vols must be equal length and non-empty")
        series.append({"name": e["name"], "colour": 1 + i % 2, "shape": "line", "pts": list(zip(e["strikes"], e["vols"]))})
    lo = min(p[0] for s in series for p in s["pts"])
    return chart(title, xlabel, "Implied volatility", series, caption, x_lo=lo)


def surface_svg(title, strikes, expiries, vols, caption, axis="Strike (darker is higher volatility)"):
    """Heat grid, one cell per (expiry, strike), shaded by the value read from CLI output. vols[i][j] is expiry i, strike j."""
    if not strikes or not expiries or len(vols) != len(expiries) or any(len(r) != len(strikes) for r in vols):
        raise ValueError("surface grid must be non-empty and match strikes x expiries")
    flat_v = [v for r in vols for v in r]
    lo, hi = min(flat_v), max(flat_v)
    cw, ch = (W - ML - MR) / len(strikes), (H - MB - MT) / len(expiries)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" xmlns="http://www.w3.org/2000/svg">',
           f'<text x="{ML}" y="20" style="fill:var(--ink);font-size:14px;font-weight:600">{html.escape(title)}</text>']
    for i, row in enumerate(vols):
        y = MT + i * ch
        out.append(f'<text x="{ML - 6}" y="{y + ch / 2 + 4:.1f}" text-anchor="end" style="fill:var(--ink);font-size:11px">{html.escape(str(expiries[i]))}</text>')
        for j, v in enumerate(row):
            a = 0.15 + 0.85 * ((v - lo) / (hi - lo) if hi > lo else 0.5)
            out.append(f'<rect x="{ML + j * cw:.1f}" y="{y:.1f}" width="{cw:.1f}" height="{ch:.1f}" style="fill:var(--c1);fill-opacity:{a:.2f};stroke:var(--bg)">'
                       f'<title>{html.escape(str(expiries[i]))}, strike {strikes[j]:g}: {v:.6g}</title></rect>')
    for j, k in enumerate(strikes):
        out.append(f'<text x="{ML + (j + .5) * cw:.1f}" y="{H - MB + 16}" text-anchor="middle" style="fill:var(--ink);font-size:11px">{k:g}</text>')
    out.append(f'<text x="{(ML + W - MR) / 2}" y="{H - 8}" text-anchor="middle" style="fill:var(--ink);font-size:12px">{html.escape(axis)}</text>')
    return wrap(out, caption)


def bars(title, ylabel, labels, values, marks, caption):
    y_ticks = ticks(min(values + marks + [0]), max(values + marks))
    step = (W - ML - MR) / len(labels)

    def sy(v):
        return H - MB - (v - y_ticks[0]) / (y_ticks[-1] - y_ticks[0]) * (H - MB - MT)

    def sx(i):
        return ML + (i + 0.5) * step

    out = frame(title, "Quote tenor", ylabel, range(len(labels)), y_ticks, sx, sy,
                [("Before hedge", 1, "bar"), ("After hedge", 2, "dot")], xtext=lambda i: labels[i])
    for i, (v, m) in enumerate(zip(values, marks)):
        top, base = sy(max(v, 0)), sy(min(v, 0))
        out.append(f'<rect x="{sx(i) - 9:.1f}" y="{top:.1f}" width="18" height="{base - top:.1f}" style="fill:var(--c1)"><title>{labels[i]}: {v:.4f}</title></rect>')
        out.append(f'<circle cx="{sx(i):.1f}" cy="{sy(m):.1f}" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>{labels[i]} after hedge: {m:.4f}</title></circle>')
    return wrap(out, caption)


def wrap(parts, caption):
    return '<div class="chart">' + "".join(parts) + f"</svg><p>{html.escape(caption)}</p></div>"


# ---- pages --------------------------------------------------------------------------------------

def quote_name(q):
    if "tenor" in q:
        return q["tenor"]
    if q["type"] == "DEPOSIT":
        return f"Deposit {q['months']}M"
    if q["type"] == "FRA":
        return f"FRA {q['start_months']}x{q['start_months'] + 3}"
    return f"Swap {q['months']}M"


def table(head, rows):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def status_block(d):
    versions = ", ".join(f"{NAMES[k]} {v['implementation_version']} ({v['toolchain']})" for k, v in d["meta"]["cli"].items())
    return ('<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. '
            "Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>\n\n"
            f"Generated on {d['meta']['date']} from commit `{d['meta']['commit']}`, by {versions}, on one Windows machine.")


def agreement_block(d):
    rows = [[r["output"], r["count"]] + [repr(r["last"][k]) for k in LANGS] + [f"{r['largest_difference']:.3g}"] for r in d["agreement"]]
    return ("Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.\n\n"
            + table(["Output", "Values", "Last value: Java", "C++", "Python", "Rust", "Largest difference, any value"], rows))


def evidence_block(d, spec):
    e = d["evidence"]
    rows = [[k.split(": ")[0], k.split(": ")[1], v] for k, v in sorted(e["by_source"].items())]
    return (f"{spec['oracle']}\n\nGolden cases for `{e['operation']}` with an `ok` result"
            + (f" and convention {spec['convention']}" if spec.get("convention") else "")
            + f": {e['cases']}, counted from `verified_by` in `datasets/golden/stage_b/`. All four builds passed them locally, which is self-assessment.\n\n"
            + table(["Suite", "Verified by", "Cases"], rows)
            + "\n\nLimits:\n\n" + "\n".join(f"- {x}" for x in spec["limits"]))


def how_block(spec, slug):
    ex = spec["example"]
    more = {"rates": "The charts then send the pillars to `rates.curve.discount` and `rates.curve.forward` on a grid of quarterly dates plus every pillar.",
            "fx": "The gallery sends this case once per quarterly value date, changing only `value_date`, and sends "
                  f"[`examples/{spec.get('implied')}`](../../examples/{spec.get('implied')}) to `fx.curve.implied` for the basis."}[spec["kind"]]
    return (f"Input file: [`examples/{ex}`](../../examples/{ex}). Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:\n\n"
            f"```bash\nrust/target/release/quantforge run < examples/{ex}\n```\n\n{more} To rebuild every page, with all four CLIs built:\n\n"
            f"```bash\npython tools/build_gallery.py\n```\n\nRaw numbers: [`docs/curves/data/{slug}.json`](data/{slug}.json).")


def rates_page(slug, spec, d):
    ref, inputs = d["reference"], d["inputs"]
    as_of, quotes = inputs["as_of"], inputs["quotes"]
    t = [years(x, as_of) for x in ref["dates"]]
    pillars = ref["pillars"]
    pt = [years(p["date"], as_of) for p in pillars]
    at = dict(zip(ref["dates"], ref["zero_rates"]))
    cap = f"{SYNTHETIC} As of {as_of}. From the Python CLI; exact values are in the tables and data file."
    qpts = [(a, q["rate"] * 100, f"{quote_name(q)}: {q['rate'] * 100:.4f}%") for a, q in zip(pt, quotes)]
    df = chart("Discount factors", "Years from as-of date", "Discount factor", [
        {"name": "Curve", "colour": 1, "shape": "line", "pts": [(0, 1.0)] + list(zip(t, ref["discount_factors"]))},
        {"name": "Solved pillars", "colour": 2, "shape": "points", "pts": [(a, p["discount_factor"], p["date"]) for a, p in zip(pt, pillars)]}], cap)
    zero = chart("Zero rates, continuous", "Years from as-of date", "Rate, %", [
        {"name": "Zero rate", "colour": 1, "shape": "line", "pts": [(a, b * 100) for a, b in zip(t, ref["zero_rates"])]},
        {"name": "Input quotes", "colour": 2, "shape": "points", "pts": qpts}], cap)
    steps, prev = [], 0.0
    for a, f in zip(t, ref["forwards"]):
        steps += [(prev, f * 100), (a, f * 100)]
        prev = a
    fwd = chart(f"Simple forward rates, {spec['day_count']}", "Years from as-of date", "Rate, %", [
        {"name": "Forward between grid dates", "colour": 1, "shape": "line", "pts": steps},
        {"name": "Input quotes", "colour": 2, "shape": "points", "pts": qpts}], cap)
    bump = [(a, (u - z) * 1e4) for a, z, u in zip(t, ref["zero_rates"], ref["bumped_zero_rates"])]
    bchart = chart("Zero-rate change for +1 bp on every quote", "Years from as-of date", "Change, bp", [
        {"name": "Change", "colour": 1, "shape": "line", "pts": bump}], cap, y_zero=True)
    rows = [[quote_name(q), p["date"], f"{a:.4f}", f"{q['rate'] * 100:.4f}", repr(p["discount_factor"]), f"{at[p['date']] * 100:.6f}"]
            for q, p, a in zip(quotes, pillars, pt)]
    in_rows = [[quote_name(q), f"{q['rate'] * 100:.4f}"] for q in quotes]
    extra = ""
    if "risk" in ref:
        r = ref["risk"]
        chartk = bars("Key-rate DV01 of the use case 2 trade", "GBP per bp", [q["tenor"] for q in quotes], r["key_rate"], r["residual_key_rate"],
                      f"{SYNTHETIC} 6Y payer, notional 10,000,000, hedged with 5Y and 7Y par swaps. Nothing is traded.")
        extra = ("\n\n### Key-rate DV01\n\nFrom [`examples/usecase_rates_hedge.json`](../../examples/usecase_rates_hedge.json), use case 2. "
                 f"A 6Y trade sits between the 5Y and 7Y quotes, so its risk lands in those two buckets. DV01 is {r['dv01']:.4f}, and hedge units are "
                 f"{r['hedge_units'][0]:.4f} and {r['hedge_units'][1]:.4f}. The hedge sums have no outside source (`specifications/04-pricing/use-cases.md`).\n\n{chartk}")
    extra_in = f" The discount curve is the stored SOFR curve, {len(inputs['discount']['pillars'])} pillars." if "discount" in inputs else ""
    return f"""# {spec['title']}

{status_block(d)}

## What it is

{spec['idea']}

Formally: {spec['formula']} Spec: `specifications/02-curves/{spec['spec']}`.

## Inputs

As of {as_of}. Interpolation `{inputs['interpolation']}`.{extra_in} All rates are synthetic.

{table(['Quote', 'Rate, %'], in_rows)}

## How to generate it

{how_block(spec, slug)}

## Charts

Quotes are par or period rates, so they are marked for reference and need not sit on a zero or forward line.

{df}

{zero}

{fwd}

### +1 bp scenario

Every quote is raised by 1 bp, the CLI rebuilds the curve, and the change in zero rate is taken at each grid date.

{bchart}{extra}

## Pillars

Largest repricing error reported by the Python CLI: {ref['max_repricing_error']}.

{table(['Quote', 'Pillar date', 'Years', 'Quote, %', 'Discount factor', 'Zero rate, %'], rows)}

## Four-language agreement

{agreement_block(d)}

## Oracle evidence and limits

{evidence_block(d, spec)}
"""


def fx_page(slug, spec, d):
    ref, inputs, implied_in = d["reference"], d["inputs"], d["implied_inputs"]
    as_of, spot = inputs["as_of"], inputs["spot"]
    t = [years(x, ref["spot_date"]) for x in ref["dates"]]
    nodes = ref["implied"]
    nt = [years(n["value_date"], ref["spot_date"]) for n in nodes]
    quoted = [q["points"] for q in implied_in["points"]]
    cap = f"{SYNTHETIC} As of {as_of}, spot {spot}. From the Python CLI; exact values are in the tables and data file."
    tips = [f"{q['tenor']}: {q['points']} points" for q in implied_in["points"]]
    fwd = chart("GBPUSD forward outright", "Years from spot date", "USD per GBP", [
        {"name": "Curve forward", "colour": 1, "shape": "line", "pts": [(0, spot)] + list(zip(t, ref["forwards"]))},
        {"name": "Input quotes", "colour": 2, "shape": "points", "pts": [(a, spot + p * 0.0001, c) for a, p, c in zip(nt, quoted, tips)]}], cap)
    pts = chart("GBPUSD forward points", "Years from spot date", "Points (pips)", [
        {"name": "Curve points", "colour": 1, "shape": "line", "pts": [(0, 0.0)] + list(zip(t, ref["points"]))},
        {"name": "Input quotes", "colour": 2, "shape": "points", "pts": list(zip(nt, quoted, tips))}], cap)
    basis = chart("Quote-driven basis", "Years from spot date", "Basis, bp", [
        {"name": "Basis", "colour": 2, "shape": "points", "pts": [(a, n["basis_bp"], n["value_date"]) for a, n in zip(nt, nodes)]}], cap, y_zero=True)
    rows = [[x, repr(f), f"{p:.4f}"] for i, (x, f, p) in enumerate(zip(ref["dates"], ref["forwards"], ref["points"])) if i % 4 == 3]
    nrows = [[q["tenor"], n["value_date"], q["points"], repr(n["implied_ratio"]), f"{n['basis_bp']:.4f}"] for q, n in zip(implied_in["points"], nodes)]
    return f"""# {spec['title']}

{status_block(d)}

## What it is

{spec['idea']}

Formally: {spec['formula']} Spec: `specifications/02-curves/{spec['spec']}`.

## Inputs

Pair {inputs['pair']}, spot {spot} (synthetic), as of {as_of}, spot date {ref['spot_date']}. Base curve: {len(inputs['base_curve']['pillars'])} sterling pillars, the curve on the [SONIA page](sonia-ois.md). Quote curve: {len(inputs['quote_curve']['pillars'])} dollar pillars, the curve on the [SOFR page](sofr-ois.md). Largest gap between the pillars stored in this file and those pages: {d['curve_gap']:.3g}.

## How to generate it

{how_block(spec, slug)}

## Charts

{fwd}

{pts}

{basis}

There is no +1 bp chart here: the FX operations take finished curves, so a bump belongs to the curve pages.

## Pillars

Yearly rows from the quarterly grid:

{table(['Value date', 'Forward', 'Points'], rows)}

Input forward-point quotes and what they imply:

{table(['Tenor', 'Value date', 'Input points', 'Implied ratio', 'Basis, bp'], nrows)}

## Four-language agreement

{agreement_block(d)}

## Oracle evidence and limits

{evidence_block(d, spec)}
"""


def index_page(all_data):
    any_d = next(iter(all_data.values()))
    rows = []
    for slug, spec in CURVES.items():
        e = all_data[slug]["evidence"]
        outside = sum(v for k, v in e["by_source"].items() if "quantlib" in k or "strata" in k)
        ev = f"{e['cases']} golden cases for `{e['operation']}`, {outside} with an outside library in `verified_by`"
        rows.append([f"[{spec['short']}]({slug}.md)", "Implemented, not Validated", "B", ev])
    for slug, spec in VOLS.items():
        e = all_data[slug]["evidence"]
        outside = sum(v for k, v in e["by_source"].items() if "quantlib" in k or "strata" in k)
        rows.append([f"[{spec['short']}]({slug}.md)", "Implemented, not Validated", "C",
                     f"{e['cases']} golden cases for {', '.join('`' + o + '`' for o in e['operations'])}, {outside} with an outside library in `verified_by`"])
    for slug, spec in STAGE_D.items():
        live = is_live(spec) and slug in all_data
        ev = "None yet"
        if live:
            e = all_data[slug]["evidence"]
            ev = f"{e['cases']} golden case{'s' if e['cases'] != 1 else ''}"
            if spec.get("golden"):  # newer pages name the operation and the outside-library share, like stages B, C and F
                outside = sum(v for k, v in e["by_source"].items() if "quantlib" in k or "strata" in k)
                ev += f" for {', '.join('`' + o + '`' for o in e['operations'])}, {outside} with an outside library in `verified_by`"
        rows.append([f"[{spec['short']}]({slug}.md)", "Implemented, not Validated" if live else "Planned", spec.get("stage", "D"), ev])
    for slug, spec in gallery_e.STAGE_E.items():
        live = gallery_e.is_live(spec) and slug in all_data
        n = all_data[slug]["evidence"]["cases"] if live else 0
        rows.append([f"[{spec['short']}]({slug}.md)", "Implemented, not Validated" if live else "Planned", "E",
                     f"{n} golden case{'s' if n != 1 else ''}" if live else "None yet"])
    if gallery_f.SLUG in all_data:
        e = all_data[gallery_f.SLUG]["evidence"]
        rows.append([f"[Five interpolation methods]({gallery_f.SLUG}.md)", "Implemented, not Validated", "F",
                     f"{e['cases']} golden cases for `{e['operation']}`, {e['outside']} reproduced by an outside library"])
    if gallery_i.SLUG in all_data:
        e = all_data[gallery_i.SLUG]["evidence"]
        rows.append([f"[Hedging against trading costs]({gallery_i.SLUG}.md)", "Implemented, not Validated", "I",
                     f"{sum(r['cases'] for r in e['suites'][:2])} golden cases for `hedge.qp.solve` with costs and `hedge.frontier.solve`, "
                     f"{sum(r['outside'] for r in e['suites'][:2])} reproduced by an outside library"])
    rows += [[name, status, stage, ev] for name, status, stage, ev in PLANNED]
    real = ""
    if gallery_real.SLUG in all_data:
        real = ("\n## Real data\n\n"
                f"[US Treasury curve with sanity bands]({gallery_real.SLUG}.md): a page built from real public data, "
                f"snapshot of {all_data[gallery_real.SLUG]['inputs']['as_of']}. The same bands run daily in workflow (a).\n")
        if gallery_pnl.SLUG in all_data:
            real += (f"\n[P&L explain and calibration stability]({gallery_pnl.SLUG}.md): full revaluation against key-rate explain "
                     "over real daily Treasury moves, and day-to-day calibration diagnostics. Runs daily in `tools/workflows/keyrate_explain.py`.\n")
        real += (f"\n[Calibration stability]({gallery_r2.CALIB}.md): seven calibrations under seeded noise in four languages, synthetic inputs. "
                 f"[Rich/cheap screen]({gallery_r2.RICH}.md): workflow (b), blocked on data until a price source is cleared.\n")
    return f"""# Curves

A curve says what one unit paid on a future date is worth today, or what a rate or price is expected to be on that date. Pricing, risk and hedging all read from curves, so a mistake here reaches everything else. Formally, a discount curve is a function `D(t)` with `D(0) = 1`, stored as dated pillars plus a rule for the dates in between (`specifications/02-curves/curve-framework.md`).

<p class="note">Every number and chart here comes from a real run of the four command-line builds. All inputs are synthetic, so these pages show the method, not a market, except the one Real data page below. Every page in the table is at Implemented, not Validated, unless its row says otherwise: validation is self-assessment until the human review at the end of the project. Nothing is traded, and trading in this project is simulated only.</p>

Generated on {any_d['meta']['date']} from commit `{any_d['meta']['commit']}`.

## Status of every curve in the plan

An outside library in `verified_by` means QuantLib or Strata. The other cases have hand or replay sources, which can share a misreading with the spec. Each page gives the breakdown. The papers and standards behind each curve are cited in its spec and collected in [References](../references.md).

{table(['Curve', 'Status', 'Stage', 'Evidence'], rows)}
{real}
## How the gallery is built

`tools/build_gallery.py` runs the CLIs and writes these pages and `docs/curves/data/`. CI reruns the Python CLI and fails if a committed number moves by more than {TOL['curve'][0]:g} plus {TOL['curve'][1]:g} relative, or {TOL['risk'][0]:g} plus {TOL['risk'][1]:g} relative for risk figures. See [the guide](../developer-guides/curves-gallery.md).
"""


def render_all(all_data):
    pages = {"README.md": index_page(all_data)}
    for slug, spec in CURVES.items():
        make = rates_page if spec["kind"] == "rates" else fx_page
        pages[f"{slug}.md"] = make(slug, spec, all_data[slug])
    for slug, spec in VOLS.items():
        pages[f"{slug}.md"] = vol_page(slug, spec, all_data[slug])
    for slug, spec in STAGE_D.items():
        live = is_live(spec) and slug in all_data
        pages[f"{slug}.md"] = RENDERERS[spec["kind"]](slug, spec, all_data[slug]) if live else planned_page(slug, spec)
    this = types.SimpleNamespace(LANGS=LANGS, status_block=status_block, table=table)
    for slug, spec in gallery_e.STAGE_E.items():
        pages[f"{slug}.md"] = gallery_e.page(slug, spec, all_data.get(slug), this)
    if gallery_f.SLUG in all_data:
        pages[f"{gallery_f.SLUG}.md"] = gallery_f.page(all_data[gallery_f.SLUG], table, gallery_e.lines, status_block, LANGS)
    if gallery_i.SLUG in all_data:
        pages[f"{gallery_i.SLUG}.md"] = gallery_i.page(all_data[gallery_i.SLUG], table, gallery_e.lines, status_block)
    if gallery_real.SLUG in all_data:
        d = all_data[gallery_real.SLUG]
        versions = ", ".join(f"{NAMES[k]} {v['implementation_version']}" for k, v in d["meta"]["cli"].items())
        pages[f"{gallery_real.SLUG}.md"] = gallery_real.page(d, chart, table, versions)
    if gallery_pnl.SLUG in all_data:
        d = all_data[gallery_pnl.SLUG]
        versions = ", ".join(f"{NAMES[k]} {v['implementation_version']}" for k, v in d["meta"]["cli"].items())
        pages[f"{gallery_pnl.SLUG}.md"] = gallery_pnl.page(d, chart, table, versions)
    calib = DATA / f"{gallery_r2.CALIB}.json"
    if calib.is_file():
        pages[f"{gallery_r2.CALIB}.md"] = gallery_r2.calib_page(json.loads(calib.read_text(encoding="utf-8")), table, bars)
    pages[f"{gallery_r2.RICH}.md"] = gallery_r2.rich_page(table)
    return pages


# ---- stage C pages: equity forward and volatility ----------------------------------------------

STAGE_C = ROOT / "datasets" / "golden" / "stage_c"

VOLS = {
    "equity-forward": {
        "title": "Equity forward with discrete dividends", "short": "Equity forward, discrete dividends",
        "examples": {"main": "eq_forward_dividends.json"}, "golden": ["eq.forward.outright"], "spec": "smile-and-surface.md",
        "idea": "A forward price is what you would agree today to pay for a share on a later date. Holding the share until then costs funding and earns any dividends, and a borrow cost applies if the share is shorted, so the forward is spot adjusted for all three. A dividend paid before the expiry takes value out of the share, so it lowers the forward.",
        "formula": "The forward is spot less the present value of dividends paid on or before expiry, carried to expiry on the funding and borrow curves. The CLI returns the forward, the discount factor, the carry factor and the present value of the dividends.",
        "oracle": "Per `specifications/05-volatility/stage-c-targets.md`, the forward is checked against a rolled route that steps between dividends one at a time, and against a plan check case. No outside library prices an equity forward here: the cases are hand and analytic.",
        "limits": ["Each curve has one pillar, so funding and borrow rates are constant. Curve shape is not exercised.",
                   "Three dividends with fixed cash amounts. Dividend curves and forecasting are stage D.",
                   "The chart moves only the expiry. Spot, curves and dividends stay as in the input file."],
    },
    "svi-smile": {
        "title": "SVI smile", "short": "SVI smile", "examples": {"main": "svi_smile.json"}, "golden": ["vol.svi.evaluate"],
        "spec": "smile-and-surface.md",
        "idea": "An implied volatility smile shows how the volatility that reproduces option prices changes with strike at one expiry. SVI is a five-number formula for total variance, volatility squared times time, as a function of log-moneyness `k = ln(K/F)`. This page evaluates one SVI smile and checks whether it admits a butterfly arbitrage, meaning a negative density.",
        "formula": "Total variance `w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))`, implied volatility `sqrt(w / T)`. The butterfly condition is that the function `g(k)` stays non-negative.",
        "oracle": "SVI evaluation is compared with QuantLib `SviSmileSection` and with a published counterexample, a smile that looks fine and still admits arbitrage. The measured gap to QuantLib is within 1e-12 (`specifications/05-volatility/stage-c-targets.md`).",
        "limits": ["One expiry and one hand-chosen parameter set. Nothing here is fitted to quotes; the SVI fit has its own golden cases.",
                   "Log-moneyness is the horizontal axis, because the SVI input is log-moneyness and no forward is needed.",
                   "`butterfly_free` is a check at the grid points only, not a proof for all strikes."],
    },
    "ssvi-surface": {
        "title": "SSVI surface", "short": "SSVI surface", "examples": {"main": "ssvi_surface.json"}, "golden": ["vol.ssvi.evaluate"],
        "spec": "smile-and-surface.md",
        "idea": "A surface is a smile at every expiry. SSVI builds one from three shape numbers and the at-the-money total variance `theta` of each expiry, with simple conditions for freedom from calendar and butterfly arbitrage.",
        "formula": "`w(k, theta) = theta / 2 * (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2))`, with `phi` a decreasing function of `theta` set by `eta` and `gamma`. The CLI returns total variance for each `theta` and each log-moneyness, plus two flags.",
        "oracle": "SSVI evaluation has analytic cases only, including the check that total variance at `k = 0` equals `theta` (1e-15). No outside library evaluates SSVI here (`specifications/05-volatility/stage-c-targets.md`).",
        "limits": ["The grid is total variance against `theta`, because the SSVI operation takes `theta` and not calendar time. Expiry in years is not an input.",
                   "The flags are checks at the grid points. A wider grid could find a violation this one does not.",
                   "One parameter set, chosen by hand."],
    },
    "sabr": {
        "title": "SABR smile, density and arbitrage-free form", "short": "SABR",
        "examples": {"hagan": "sabr_hagan.json", "density": "sabr_density.json", "arbfree": "sabr_arbfree.json"},
        "golden": ["vol.sabr.hagan", "vol.sabr.density", "vol.sabr.arbfree"], "spec": "sabr.md",
        "idea": "SABR is a stochastic-volatility model whose smile has a closed-form approximation, Hagan's formula. The approximation can fail far from the money or at long expiries, where it implies a negative density. A density check finds those strikes, and the arbitrage-free form solves the same model on a numerical grid so that the density cannot go negative.",
        "formula": "Hagan's formula gives the implied volatility from `forward`, `strike`, `expiry`, `alpha`, `beta`, `rho` and `nu`. The density is the second derivative of the call price in strike, taken with a step `h_strike`. The arbitrage-free form uses `cells` grid points, `cells_below` of them below the forward, and `steps` time steps.",
        "oracle": "Hagan volatilities are compared with QuantLib 1.44, and with Strata 2.12.78 on 18 of the golden cases. The density has replay cases only. The arbitrage-free form is compared with QuantLib's CEV engine at `nu = 0` and, coarsely, with `NoArbSabrSmileSection`, a different model of the floor. Targets and measured gaps are in `specifications/05-volatility/stage-c-targets.md`.",
        "limits": ["The density input is the golden long-expiry case: 20 years, forward 2%. The formula gives a negative density at most of these strikes. That is the point of the chart, and it does not say how SABR behaves at market parameters.",
                   "The arbitrage-free form has a method error against Hagan where Hagan is safe. Mass, mean and absorbed mass are reported, and it is not a fit.",
                   "Three separate inputs with different parameters, so the charts are not comparable with each other."],
    },
}


def golden_c(ops):
    counts, total = {}, 0
    for path in sorted(STAGE_C.glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            if c["operation"] not in ops or c["expected"].get("status") != "ok":
                continue
            key = f"{c['operation']}: {', '.join(c['verified_by'])}"
            counts[key] = counts.get(key, 0) + 1
            total += 1
    return {"operations": ops, "cases": total, "by_source": counts}


def vol_run(lang, slug, spec):
    exs = {k: read_example(v) for k, v in spec["examples"].items()}
    res = {k: batch(lang, [e])[0]["outputs"] for k, e in exs.items()}
    if slug == "equity-forward":
        inp = exs["main"]["inputs"]
        dates = [add_months(dt.date.fromisoformat(inp["as_of"]), m).isoformat() for m in range(1, 13)]
        rows = batch(lang, [case(d, "eq.forward.outright", {**inp, "expiry": d}) for d in dates])
        res["series"] = {"dates": dates, "forward": [r["outputs"]["forward"] for r in rows],
                         "pv_dividends": [r["outputs"]["pv_dividends"] for r in rows]}
    return res


def flatten(v):
    if isinstance(v, bool):
        return []
    if isinstance(v, (int, float)):
        return [float(v)]
    if isinstance(v, list):
        return [x for e in v for x in flatten(e)]
    if isinstance(v, dict):
        return [x for e in v.values() for x in flatten(e)]
    return []


def vol_agreement(results):
    rows = []
    for run, outs in results["python"].items():
        for key in outs:
            cols = [flatten(results[lang][run][key]) for lang in LANGS]
            if not cols[0]:
                flags = [results[lang][run][key] for lang in LANGS]
                rows.append({"output": f"{run}: {key}", "count": 1, "largest_difference": 0.0 if len(set(map(str, flags))) == 1 else None,
                             "last": dict(zip(LANGS, flags))})
                continue
            rows.append({"output": f"{run}: {key}", "count": len(cols[0]),
                         "largest_difference": max(max(v) - min(v) for v in zip(*cols)),
                         "last": {lang: col[-1] for lang, col in zip(LANGS, cols)}})
    return rows


def vol_charts(slug, d):
    ref, ins = d["reference"], d["inputs"]
    cap = f"{SYNTHETIC} From the Python CLI; exact values are in the tables and data file."
    if slug == "equity-forward":
        s = ref["series"]
        t = [years(x, ins["main"]["as_of"]) for x in s["dates"]]
        return [chart("Forward price against expiry", "Years from as-of date", "Forward price", [
                    {"name": "Forward", "colour": 1, "shape": "line", "pts": [(0, ins["main"]["spot"])] + list(zip(t, s["forward"]))}], cap),
                chart("Present value of dividends against expiry", "Years from as-of date", "Present value", [
                    {"name": "Dividends", "colour": 1, "shape": "line", "pts": [(0, 0.0)] + list(zip(t, s["pv_dividends"]))}], cap, y_zero=True)]
    if slug == "svi-smile":
        k, o = ins["main"]["log_moneyness"], ref["main"]
        return [smile_chart("SVI implied volatility", [{"name": "Smile", "strikes": k, "vols": o["implied_vol"]}], cap, xlabel="Log-moneyness"),
                chart("SVI total variance", "Log-moneyness", "Total variance", [
                    {"name": "w(k)", "colour": 1, "shape": "line", "pts": list(zip(k, o["total_variance"]))}], cap, x_lo=min(k)),
                chart("Butterfly function g(k)", "Log-moneyness", "g", [
                    {"name": "g", "colour": 1, "shape": "line", "pts": list(zip(k, o["g"]))}], cap, y_zero=True, x_lo=min(k))]
    if slug == "ssvi-surface":
        i, o = ins["main"], ref["main"]
        return [surface_svg("SSVI total variance", i["log_moneyness"], [f"theta {t:g}" for t in i["thetas"]], o["total_variance"], cap,
                            axis="Log-moneyness (darker is higher total variance)")]
    h, de, af = ref["hagan"], ref["density"], ref["arbfree"]
    return [smile_chart("Hagan SABR smile", [{"name": "Hagan", "strikes": ins["hagan"]["strikes"], "vols": h["vols"]}], cap),
            chart("Hagan density, long expiry", "Strike", "Density", [
                {"name": "Density", "colour": 1, "shape": "line", "pts": list(zip(ins["density"]["strikes"], de["density"]))}], cap,
                y_zero=True, x_lo=min(ins["density"]["strikes"])),
            smile_chart("Arbitrage-free SABR smile", [{"name": "Arbitrage-free", "strikes": ins["arbfree"]["strikes"], "vols": af["vols"]}], cap)]


def num_table(d, slug):
    ref, ins = d["reference"], d["inputs"]
    f = lambda v: repr(v) if isinstance(v, float) else str(v)
    if slug == "equity-forward":
        s = ref["series"]
        return table(["Expiry", "Forward", "PV of dividends"], [[a, f(b), f(c)] for a, b, c in zip(s["dates"], s["forward"], s["pv_dividends"])]) \
            + "\n\nInput file result: " + ", ".join(f"`{k}` {f(v)}" for k, v in ref["main"].items()) + "."
    if slug == "svi-smile":
        o = ref["main"]
        return table(["Log-moneyness", "Total variance", "Implied vol", "g"], [[k, f(w), f(v), f(g)] for k, w, v, g in
                     zip(ins["main"]["log_moneyness"], o["total_variance"], o["implied_vol"], o["g"])]) \
            + f"\n\nMinimum g: {f(o['min_g'])}. Butterfly free at these points: {o['butterfly_free']}."
    if slug == "ssvi-surface":
        o, i = ref["main"], ins["main"]
        return table(["theta"] + [f"k={k:g}" for k in i["log_moneyness"]], [[t] + [f"{x:.6g}" for x in row] for t, row in zip(i["thetas"], o["total_variance"])]) \
            + f"\n\nButterfly free: {o['butterfly_free']}. Calendar free: {o['calendar_free']}."
    h, de, af = ref["hagan"], ref["density"], ref["arbfree"]
    return ("Hagan volatilities:\n\n" + table(["Strike", "Volatility"], [[k, f(v)] for k, v in zip(ins["hagan"]["strikes"], h["vols"])])
            + "\n\nDensity check (Hagan, 20 years):\n\n" + table(["Strike", "Density"], [[k, f(v)] for k, v in zip(ins["density"]["strikes"], de["density"])])
            + f"\n\nMinimum density {f(de['min_density'])}; negative density found: {de['negative_density']}.\n\nArbitrage-free form:\n\n"
            + table(["Strike", "Call price", "Volatility"], [[k, f(c), f(v)] for k, c, v in zip(ins["arbfree"]["strikes"], af["call_prices"], af["vols"])])
            + f"\n\nMass {f(af['mass'])}, mean {f(af['mean'])}, absorbed {f(af['absorbed'])}, minimum density {f(af['min_density'])}.")


def vol_page(slug, spec, d):
    ex = spec["examples"]
    files = "\n".join(f"- [`examples/{v}`](../../examples/{v})" for v in ex.values())
    first = next(iter(ex.values()))
    e = d["evidence"]
    ev_rows = [[k.split(": ")[1], k.split(": ")[0], v] for k, v in sorted(e["by_source"].items())]
    ag = [[r["output"], r["count"]] + [repr(r["last"][k]) for k in LANGS]
          + ["flags differ" if r["largest_difference"] is None else f"{r['largest_difference']:.3g}"] for r in d["agreement"]]
    charts = "\n\n".join(vol_charts(slug, d))
    ops = ", ".join(f"`{o}`" for o in e["operations"])
    return f"""# {spec['title']}

{status_block(d)}

## What it is

{spec['idea']}

Formally: {spec['formula']} Spec: `specifications/05-volatility/{spec['spec']}`.

## Inputs

{SYNTHETIC} The input files are:

{files}

They use the parameters of golden cases, so the same numbers are checked against the oracle elsewhere.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/{first}
```

To rebuild every gallery page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/{slug}.json`](data/{slug}.json).

## Charts

{charts}

## Numbers

{num_table(d, slug)}

## Four-language agreement

Each CLI built these numbers on its own, from the same input files. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

{table(["Output", "Values", "Last value: Java", "C++", "Python", "Rust", "Largest difference, any value"], ag)}

## Oracle evidence and limits

{spec['oracle']}

Golden cases with an `ok` result for {ops}: {e['cases']}, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

{table(["Verified by", "Operation", "Cases"], ev_rows)}

Limits:

{chr(10).join("- " + x for x in spec["limits"])}

{SYNTHETIC}
"""


# ---- stage D pages: one generic renderer over every operation's outputs -------------------------

STAGE_D_GOLDEN = ROOT / "datasets" / "golden" / "stage_d"


def golden_d(ops, folder="stage_d"):
    counts, total = {}, 0
    for path in sorted((ROOT / "datasets" / "golden" / folder).glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            if c["operation"] not in ops or c["expected"].get("status") != "ok":
                continue
            key = f"{c['operation']}: {', '.join(c['verified_by'])}"
            counts[key] = counts.get(key, 0) + 1
            total += 1
    return {"operations": list(ops), "cases": total, "by_source": counts}


def d_run(lang, spec):
    return {op: batch(lang, [read_example(f)])[0]["outputs"] for op, f in spec["examples"].items()}


def d_series(outs):
    """Numeric lists with three or more values, and lists of dated records, as chartable series."""
    found = []
    for key, v in outs.items():
        if isinstance(v, list) and len(v) >= 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            found.append((key, [(i + 1, float(x)) for i, x in enumerate(v)], "Index"))
        elif isinstance(v, list) and len(v) >= 3 and all(isinstance(x, dict) for x in v):
            for field in v[0]:
                if all(isinstance(x.get(field), (int, float)) and not isinstance(x.get(field), bool) for x in v):
                    found.append((f"{key}: {field}", [(i + 1, float(x[field])) for i, x in enumerate(v)], f"{key} number"))
    return [f for f in found if max(y for _, y in f[1]) - min(y for _, y in f[1]) > 1e-12 * max(1.0, max(abs(y) for _, y in f[1]))]


def d_value(v):
    if isinstance(v, list):
        return f"{len(v)} values" if v else "none"
    return f"`{v!r}`"


@renderer("stage-d")
def stage_d_page(slug, spec, d):
    parts = []
    for op, outs in d["reference"].items():
        ex = spec["examples"][op]
        rows = [[f"`{k}`", d_value(v)] for k, v in outs.items()]
        charts = "\n\n".join(chart(name, xlabel, name, [{"name": name, "colour": 1, "shape": "line", "pts": pts}],
                                   f"{name}, Python CLI, from examples/{ex}. {'Real data, see the label above.' if ex in spec.get('real', {}) else SYNTHETIC}")
                             for name, pts, xlabel in d_series(outs)[:3])
        label = spec.get("real", {}).get(ex, SYNTHETIC)
        parts.append(f"""### `{op}`

**{"Real data" if ex in spec.get("real", {}) else "Synthetic"}.** {label}

Input: [`examples/{ex}`](../../examples/{ex}). Command: `quantforge batch < examples/{ex}` (wrap as one line).

{table(['Output', 'Python value'], rows)}

{charts}
""")
    agree = [[r["output"], r["count"]] + [repr(r["last"][k]) if not isinstance(r["last"][k], (list, dict)) else "list" for k in LANGS]
             + ["differ" if r["largest_difference"] is None else f"{r['largest_difference']:.3g}"] for r in d["agreement"]]
    ev = d["evidence"]
    ev_rows = [[k, n] for k, n in sorted(ev["by_source"].items())]
    return f"""# {spec['title']}

{status_block(d)}

## What it is

{spec['shows']} Stage {spec.get('stage', 'D')}.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

{''.join(parts)}
## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

{table(['Output', 'Values', 'Last value: Java', 'C++', 'Python', 'Rust', 'Largest difference, any value'], agree)}

## Oracle evidence and limits

{ev['cases']} golden cases with status ok in `datasets/golden/{spec.get('golden', 'stage_d')}` for {', '.join('`' + o + '`' for o in ev['operations'])}, by `verified_by`:

{table(['Operation: sources', 'Cases'], ev_rows)}

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
"""


# ---- generate and check -------------------------------------------------------------------------

def run_curve(lang, spec):
    return (rates_curve if spec["kind"] == "rates" else fx_curve)(lang, spec)


def generate_real(meta, refresh):
    path = DATA / f"{gallery_real.SLUG}.json"
    inputs = gallery_real.fetch_inputs() if refresh or not path.is_file() else json.loads(path.read_text(encoding="utf-8"))["inputs"]
    results = {lang: gallery_real.run(lang, inputs, batch) for lang in LANGS}
    gap = max(abs(a["discount_factor"] - b["discount_factor"]) for lang in LANGS
              for a, b in zip(results[lang]["pillars"], results["python"]["pillars"]))
    d = {"meta": meta, "inputs": inputs, "reference": results["python"], "agreement": gap}
    path.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    return d


def generate_pnl(meta, refresh):
    path = DATA / f"{gallery_pnl.SLUG}.json"
    inputs = gallery_pnl.fetch_inputs() if refresh or not path.is_file() else json.loads(path.read_text(encoding="utf-8"))["inputs"]
    results = {lang: gallery_pnl.run(lang, inputs) for lang in LANGS}
    d = {"meta": meta, "inputs": inputs, "reference": results["python"], "agreement": gallery_pnl.agreement(results)}
    path.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    return d


def committed_slugs():
    return list(CURVES) + list(VOLS) + [s for s, spec in STAGE_D.items() if is_live(spec) and (DATA / f"{s}.json").is_file()] \
        + [s for s, spec in gallery_e.STAGE_E.items() if gallery_e.is_live(spec) and (DATA / f"{s}.json").is_file()]         + ([gallery_f.SLUG] if (DATA / f"{gallery_f.SLUG}.json").is_file() else []) \
        + ([gallery_i.SLUG] if (DATA / f"{gallery_i.SLUG}.json").is_file() else [])


def refresh_evidence():
    """Recounts golden evidence for every page from datasets/golden and re-renders. No CLI runs and no change to run data,
    so it is the fix when only goldens were added: the run data stays as committed, and --check still compares it."""
    all_data = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in committed_slugs()}
    for extra in (gallery_real.SLUG, gallery_pnl.SLUG):
        if (DATA / f"{extra}.json").is_file():
            all_data[extra] = json.loads((DATA / f"{extra}.json").read_text(encoding="utf-8"))
    changed = []
    for slug, d in all_data.items():
        if slug in CURVES:
            new = evidence(CURVES[slug])
        elif slug in VOLS:
            new = golden_c(VOLS[slug]["golden"])
        elif slug in STAGE_D:
            new = golden_d(STAGE_D[slug]["examples"], STAGE_D[slug].get("golden", "stage_d"))
        elif slug in gallery_e.STAGE_E:
            new = gallery_e.golden(gallery_e.STAGE_E[slug]["examples"])
        else:
            continue
        if d["evidence"] != new:
            d["evidence"] = new
            changed.append(slug)
            (DATA / f"{slug}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    for name, text in render_all(all_data).items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"evidence recounted; changed: {', '.join(changed) or 'none'}")
    return 0


def e_run(lang, spec):
    return gallery_e.run_cube(lang, spec, batch, read_example) if spec.get("runner") == "cube" else d_run(lang, spec)


def generate_e(meta, all_data):
    """Runs the four CLIs for every live stage E page and writes its data file."""
    for slug, spec in gallery_e.STAGE_E.items():
        if not gallery_e.is_live(spec):
            continue
        results = {lang: e_run(lang, spec) for lang in LANGS}
        for op in spec["examples"]:
            gallery_e.shape(spec, read_example(spec["examples"][op])["inputs"], results["python"][op])
        d = {"meta": {**meta, "example_hashes": {v: example_hash(v) for v in spec["examples"].values()}},
             "inputs": {op: read_example(f)["inputs"] for op, f in spec["examples"].items()},
             "reference": results["python"], "agreement": vol_agreement(results), "evidence": gallery_e.golden(spec["examples"])}
        all_data[slug] = d
        (DATA / f"{slug}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")


def generate_f(meta, all_data):
    results = {lang: gallery_f.run(lang, batch, read_example) for lang in LANGS}
    d = {"meta": {**meta, "example_hashes": {gallery_f.EXAMPLE: example_hash(gallery_f.EXAMPLE)}},
         "inputs": read_example(gallery_f.EXAMPLE)["inputs"], "reference": results["python"],
         "agreement": gallery_f.agreement(results, LANGS), "against_golden": gallery_f.against_golden(results["python"]),
         "evidence": gallery_f.evidence()}
    all_data[gallery_f.SLUG] = d
    (DATA / f"{gallery_f.SLUG}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")


def generate_i(meta, all_data):
    results = {lang: gallery_i.run(lang, batch, read_example) for lang in LANGS}
    d = {"meta": {**meta, "example_hashes": {gallery_i.EXAMPLE: example_hash(gallery_i.EXAMPLE)}},
         "inputs": read_example(gallery_i.EXAMPLE)["inputs"], "example_case": gallery_i.EXAMPLE_CASE, "reference": results["python"],
         "agreement": gallery_i.agreement(results, LANGS), "against_golden": gallery_i.against_golden(results["python"], gallery_i.EXAMPLE_CASE),
         "evidence": gallery_i.evidence()}
    all_data[gallery_i.SLUG] = d
    (DATA / f"{gallery_i.SLUG}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")


def generate(refresh_real=False, real_only=False, stage_e_only=False, stage_f_only=False, stage_i_only=False):
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    meta = {"commit": commit, "date": dt.date.today().isoformat(), "reference_language": "python", "tolerance": TOL,
            "data": "synthetic", "cli": {lang: json.loads(call(lang, "version")) for lang in LANGS}}
    DATA.mkdir(parents=True, exist_ok=True)
    all_data = {}
    if stage_i_only:  # keep every other page's committed data; run the stage I page and re-render
        all_data = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in committed_slugs() if s != gallery_i.SLUG}
        for extra in (gallery_real.SLUG, gallery_pnl.SLUG):
            all_data[extra] = json.loads((DATA / f"{extra}.json").read_text(encoding="utf-8"))
        generate_i(meta, all_data)
        for name, text in render_all(all_data).items():
            (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"stage I page written to {OUT}")
        return 0
    if stage_f_only:  # keep every other page's committed data; run the stage F page and re-render
        all_data = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in committed_slugs() if s != gallery_f.SLUG}
        for extra in (gallery_real.SLUG, gallery_pnl.SLUG):
            all_data[extra] = json.loads((DATA / f"{extra}.json").read_text(encoding="utf-8"))
        generate_f(meta, all_data)
        for name, text in render_all(all_data).items():
            (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"stage F page written to {OUT}")
        return 0
    if stage_e_only:  # keep every other page's committed data; run the stage E pages and re-render
        all_data = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in committed_slugs() if s not in gallery_e.STAGE_E}
        for extra in (gallery_real.SLUG, gallery_pnl.SLUG):
            all_data[extra] = json.loads((DATA / f"{extra}.json").read_text(encoding="utf-8"))
        generate_e(meta, all_data)
        for name, text in render_all(all_data).items():
            (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"stage E pages written to {OUT}")
        return 0
    if real_only:  # keep every synthetic page's committed data; rebuild only the real-data page and the index
        all_data = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in committed_slugs()}
        all_data[gallery_real.SLUG] = generate_real({**meta, "data": "real"}, refresh_real)
        all_data[gallery_pnl.SLUG] = generate_pnl({**meta, "data": "real"}, refresh_real)
        for name in ("README.md", f"{gallery_real.SLUG}.md", f"{gallery_pnl.SLUG}.md"):
            (OUT / name).write_text(render_all(all_data)[name], encoding="utf-8", newline="\n")
        print(f"real-data page written to {OUT}")
        return 0
    for slug, spec in CURVES.items():
        results = {lang: run_curve(lang, spec) for lang in LANGS}
        example = read_example(spec["example"])
        d = {"meta": {**meta, "example": f"examples/{spec['example']}", "example_hash": example_hash(spec["example"])},
             "inputs": example["inputs"], "reference": results["python"], "agreement": agreement(results, spec),
             "evidence": evidence(spec)}
        if spec["kind"] == "fx":
            d["implied_inputs"] = read_example(spec["implied"])["inputs"]
            pairs = [("base_curve", "sonia-ois"), ("quote_curve", "sofr-ois")]
            d["curve_gap"] = max(abs(a["discount_factor"] - b["discount_factor"]) for key, other in pairs
                                 for a, b in zip(example["inputs"][key]["pillars"], all_data[other]["reference"]["pillars"]))
        all_data[slug] = d
        (DATA / f"{slug}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    for slug, spec in VOLS.items():
        results = {lang: vol_run(lang, slug, spec) for lang in LANGS}
        inputs = {k: read_example(v)["inputs"] for k, v in spec["examples"].items()}
        d = {"meta": {**meta, "examples": {k: f"examples/{v}" for k, v in spec["examples"].items()},
                      "example_hashes": {v: example_hash(v) for v in spec["examples"].values()}},
             "inputs": inputs, "reference": results["python"], "agreement": vol_agreement(results), "evidence": golden_c(spec["golden"])}
        all_data[slug] = d
        (DATA / f"{slug}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    for slug, spec in STAGE_D.items():
        if not is_live(spec):
            continue
        results = {lang: d_run(lang, spec) for lang in LANGS}
        d = {"meta": {**meta, "example_hashes": {v: example_hash(v) for v in spec["examples"].values()}},
             "inputs": {op: read_example(f)["inputs"] for op, f in spec["examples"].items()},
             "reference": results["python"], "agreement": vol_agreement(results), "evidence": golden_d(spec["examples"], spec.get("golden", "stage_d"))}
        all_data[slug] = d
        (DATA / f"{slug}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    generate_e(meta, all_data)
    generate_f(meta, all_data)
    generate_i(meta, all_data)
    for name, text in render_all(all_data).items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(all_data)} pages of data, {len(all_data) + 1} pages written to {OUT}")
    return 0


def compare(a, b, path, bad):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            bad.append(f"{path}: keys differ")
        for k in a.keys() & b.keys():
            compare(a[k], b[k], f"{path}/{k}", bad)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            bad.append(f"{path}: length {len(a)} against {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}/{i}", bad)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        absolute, relative = TOL["risk" if "/risk/" in path else "curve"]
        if abs(a - b) > absolute + relative * max(abs(a), abs(b)):
            bad.append(f"{path}: committed {a!r}, now {b!r}")
    elif a != b:
        bad.append(f"{path}: committed {a!r}, now {b!r}")


def check():
    bad, all_data = [], {}
    for slug, spec in CURVES.items():
        d = json.loads((DATA / f"{slug}.json").read_text(encoding="utf-8"))
        all_data[slug] = d
        if d["meta"]["example_hash"] != example_hash(spec["example"]):
            bad.append(f"{slug}: {spec['example']} changed")
        compare(d["reference"], run_curve("python", spec), slug, bad)
        if d["evidence"] != evidence(spec):
            bad.append(f"{slug}: golden evidence changed")
    for slug, spec in VOLS.items():
        d = json.loads((DATA / f"{slug}.json").read_text(encoding="utf-8"))
        all_data[slug] = d
        for v in spec["examples"].values():
            if d["meta"]["example_hashes"].get(v) != example_hash(v):
                bad.append(f"{slug}: {v} changed")
        compare(d["reference"], vol_run("python", slug, spec), slug, bad)
        if d["evidence"] != golden_c(spec["golden"]):
            bad.append(f"{slug}: golden evidence changed")
    for slug, spec in STAGE_D.items():
        if not is_live(spec):
            continue
        d = json.loads((DATA / f"{slug}.json").read_text(encoding="utf-8"))
        all_data[slug] = d
        for v in spec["examples"].values():
            if d["meta"]["example_hashes"].get(v) != example_hash(v):
                bad.append(f"{slug}: {v} changed")
        compare(d["reference"], d_run("python", spec), slug, bad)
        if d["evidence"] != golden_d(spec["examples"], spec.get("golden", "stage_d")):
            bad.append(f"{slug}: golden evidence changed")
    for slug, spec in gallery_e.STAGE_E.items():
        if not gallery_e.is_live(spec):
            continue
        path = DATA / f"{slug}.json"
        if not path.is_file():
            bad.append(f"{slug}: live (cli set) but no committed data; run tools/build_gallery.py")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        all_data[slug] = d
        for v in spec["examples"].values():
            if d["meta"]["example_hashes"].get(v) != example_hash(v):
                bad.append(f"{slug}: {v} changed")
        compare(d["reference"], e_run("python", spec), slug, bad)
        if d["evidence"] != gallery_e.golden(spec["examples"]):
            bad.append(f"{slug}: golden evidence changed")
    path = DATA / f"{gallery_f.SLUG}.json"
    if path.is_file():
        d = json.loads(path.read_text(encoding="utf-8"))
        all_data[gallery_f.SLUG] = d
        if d["meta"]["example_hashes"].get(gallery_f.EXAMPLE) != example_hash(gallery_f.EXAMPLE):
            bad.append(f"{gallery_f.SLUG}: {gallery_f.EXAMPLE} changed")
        compare(d["reference"], gallery_f.run("python", batch, read_example), gallery_f.SLUG, bad)
        if d["evidence"] != gallery_f.evidence():
            bad.append(f"{gallery_f.SLUG}: golden evidence changed")
    path = DATA / f"{gallery_i.SLUG}.json"
    if path.is_file():
        d = json.loads(path.read_text(encoding="utf-8"))
        all_data[gallery_i.SLUG] = d
        if d["meta"]["example_hashes"].get(gallery_i.EXAMPLE) != example_hash(gallery_i.EXAMPLE):
            bad.append(f"{gallery_i.SLUG}: {gallery_i.EXAMPLE} changed")
        compare(d["reference"], gallery_i.run("python", batch, read_example), gallery_i.SLUG, bad)
        if d["evidence"] != gallery_i.evidence():
            bad.append(f"{gallery_i.SLUG}: golden evidence changed")
    d = json.loads((DATA / f"{gallery_real.SLUG}.json").read_text(encoding="utf-8"))
    all_data[gallery_real.SLUG] = d
    compare(d["reference"], gallery_real.run("python", d["inputs"], batch), gallery_real.SLUG, bad)
    d = json.loads((DATA / f"{gallery_pnl.SLUG}.json").read_text(encoding="utf-8"))
    all_data[gallery_pnl.SLUG] = d
    now = gallery_pnl.run("python", d["inputs"])  # P&L in USD at the risk tolerance; calibration at the curve tolerance
    compare(d["reference"]["explain"], now["explain"], gallery_pnl.SLUG + "/risk/explain", bad)
    compare(d["reference"]["calibration"], now["calibration"], gallery_pnl.SLUG + "/calibration", bad)
    for name, text in render_all(all_data).items():
        path = OUT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            bad.append(f"{name}: page differs from its data")
    for row in bad[:40]:
        print("DIFF", row)
    print(f"{len(all_data)} entries checked against the Python CLI; {len(bad)} differences")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="rerun the Python CLI and compare with committed data")
    ap.add_argument("--refresh-real", action="store_true", help="fetch a new real-data snapshot before generating")
    ap.add_argument("--real-only", action="store_true", help="rebuild only the real-data page and the index")
    ap.add_argument("--evidence-only", action="store_true", help="recount golden evidence and re-render; no CLI runs")
    ap.add_argument("--stage-e-only", action="store_true", help="run only the stage E pages; keep other committed data")
    ap.add_argument("--stage-f-only", action="store_true", help="run only the stage F page; keep other committed data")
    ap.add_argument("--stage-i-only", action="store_true", help="run only the stage I page; keep other committed data")
    a = ap.parse_args()
    if a.evidence_only:
        return refresh_evidence()
    return check() if a.check else generate(a.refresh_real, a.real_only, a.stage_e_only, a.stage_f_only, a.stage_i_only)


if __name__ == "__main__":
    sys.exit(main())
