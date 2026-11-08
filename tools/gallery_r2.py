"""Gallery pages for R2: calibration stability and the rich/cheap screen. Used by tools/build_gallery.py.

Calibration stability renders from docs/curves/data/calib-stability.json, the JSON twin of a full run of
tools/workflows/calib_stability.py (200 draws, four languages). That run takes minutes, so --check only confirms the
page matches its data; refresh with `python tools/workflows/calib_stability.py --impls python java cpp rust` and
copy the JSON in. The rich/cheap page is a status page until a price source is cleared (rich_cheap.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "workflows"))
import rich_cheap  # noqa: E402

CALIB = "calib-stability"
RICH = "rich-cheap"
NAMES = {"C1": "OIS bootstrap, LOG_LINEAR_DF", "C2": "OIS bootstrap, LINEAR_ZERO", "C3": "Bond Nelson-Siegel fit", "C4": "Smoothing spline",
         "C5": "Robust Nelson-Siegel", "C6": "SVI smile", "C7": "SABR smile"}
TH = {"C1": {"S3": 3, "S7": "1e-12"}, "C2": {"S3": 3, "S7": "1e-12"}, "C3": {"S3": 2, "S7": "rms_0 + 1.5a"}, "C4": {"S3": 5}, "C5": {"S3": 5, "S6": 0.95},
      "C6": {"S3": 10, "S7": "rms_0 + 1.5a (vol)"}, "C7": {"S3": 10, "S7": "rms_0 + 1.5a (vol)"}}


def g(x, f="{:.3g}"):
    return "—" if x is None else f.format(x)


def calib_page(d, table, bars):
    res, langs = d["results"], d["impls"]
    rows = []
    for cid in NAMES:
        for lang in langs:
            r = res[lang][cid]
            v = r.get("verdict", {})
            fails = [k for k, ok in v.items() if not ok]
            rows.append([cid, NAMES[cid], lang, f"`{r['case']}`", "same" if r.get("S1") else "**differs**", "agree" if r.get("S2") else "**differ**",
                         g(r.get("S3")), g((r.get("S4") or {}).get("largest")), ", ".join(g(x, "{:.2g}") for x in r["S5"]) if r.get("S5") else "",
                         g(r.get("S6"), "{:.2f}"), g(r.get("S7"), "{:.2e}") if r.get("S7") is not None else r.get("S7_note", ""),
                         "PASS" if not fails else "FAIL: " + ", ".join(fails)])
    ref = langs[0]
    amp = bars("Noise amplification A (S3), first language", "A, output per input unit", list(NAMES),
               [res[ref][cid].get("S3") or 0.0 for cid in NAMES], [TH[cid]["S3"] for cid in NAMES],
               f"Synthetic golden inputs; seed {d['seed']}, {d['draws']} draws. Marks are the spec's provisional S3 thresholds.")
    th_rows = [[cid, NAMES[cid]] + [str(TH[cid].get(k, "")) for k in ("S3", "S6", "S7")] for cid in NAMES]
    fails = sum(1 for r in rows if r[-1] != "PASS")
    return f"""# Calibration stability

<p class="note">Status: Implemented, not Validated. <strong>Synthetic inputs; stability of the method, not of any market.</strong> The thresholds are the spec's provisional ones, and this is the first run, so a failure is a finding about the threshold or the method, reported as it is.</p>

From `tools/workflows/calib_stability.py` (spec `specifications/03-calibration/stability.md`), run on {d['as_of']} with {', '.join(langs)}: seed {d['seed']}, {d['draws']} noise draws per calibration from the library's own generator (`core.rng.normals`, stream = calibration number). {fails} of {len(rows)} rows fail a judged metric.

## What is measured

| # | Metric |
|---|---|
| S1 | The same case twice in one batch, and again in a new process, gives bit-identical outputs |
| S2 | Each language's base outputs agree with the first language's within the golden tolerance |
| S3 | Noise amplification: the largest standard deviation of the output over the draws, divided by the noise amplitude |
| S4 | The largest output move for a one-input bump, per unit of bump |
| S5 | For the bond fit and SABR, each parameter's standard deviation over its base value (reported, never judged) |
| S6 | For the robust fit, the share of draws keeping the base outlier set |
| S7 | The worst repricing error of the fitted model against the noisy inputs |

{amp}

## Results

{table(['Cal', 'Method', 'Language', 'Base case', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'Verdict'], rows)}

## Thresholds (provisional)

{table(['Cal', 'Method', 'S3 at most', 'S6 at least', 'S7 at most'], th_rows)}

## Reading the run

- **Rulings applied (`specifications/r2-rulings.md`).** R2-A7: Gaussian noise `N(0, a^2)`. The amplitudes are 0.1 bp for rates, 0.0001 for vol and 0.001 per 100 for prices, and A is in the spec's units: bp per bp for C1, C2, C4 and C5; price per price for C3 (model prices of the input bonds, R2-A9); total variance per 0.0001 of vol for C6; vol per vol for C7. R2-A2: S7 for the least-squares fits (C3, C6, C7) is the pooled RMS repricing error, which must be at most `rms_0 + 1.5 a`, where `rms_0` is the noise-free fit's RMS. C1 and C2 keep a 1e-12 solve tolerance.
- **C6 noise on vol.** SVI calibration takes total variance and no expiry, so the noise goes on `sqrt(total variance)`, which is vol at T = 1. That reading is infra's and is stated here.
- **C3 (ruling R2-A9).** C3 is judged on the op's own outputs, the model prices of the input bonds (market plus residual), in price per price, with A at most 2. No formula is evaluated in the tool. C3 was rerun in all four languages after the ruling; the other calibrations are from the full run.
- **An earlier run under the original thresholds** failed S7 on C3, C6 and C7. That is what led to ruling R2-A2.

## Limits

- Golden inputs only, so this is the stability of the method on clean, synthetic cases. Market-data stability is the daily key-rate explain job's calibration section.
- One seed. Other draws would move the numbers slightly; the thresholds carry the margin.
"""


def rich_page(table):
    return f"""# Rich/cheap screen (workflow b)

<p class="note">Status: Specified, implemented, and <strong>blocked on data</strong>. {rich_cheap.LABEL}</p>

Workflow (b) screens Treasuries and gilts against a Nelson-Siegel curve fitted to the day's prices (`specifications/04-pricing/workflow-b-rich-cheap.md`). The job, `tools/workflows/rich_cheap.py`, runs daily, but it has no prices to screen yet: both free sources refuse automated use.

## Why it is blocked

{table(['Source', 'Finding (terms checked 2026-11-07)'], rich_cheap.BLOCKED)}

Until a source is cleared, the daily run writes a dated BLOCKED report. If a person downloads price files and places them in `--data`, the job runs the screen, but it publishes only residuals and ranks, never prices.

## What the screen does

1. Settlement T+1 on the market's calendar (`core.calendar.add_business_days`, USGS or GBLO).
2. Universe filters: fixed-coupon nominal bonds with at least 1 year to maturity. Gilts in their ex-dividend period, 7 business days before a coupon, are dropped (edge register E9).
3. Market yield and dirty price from `bond.yield.from_price`, and modified duration from `bond.price.from_yield`. Then a Nelson-Siegel fit with `tau` = 2.5 (`bond.fit.nelson_siegel`), weighted by 1/D_mod² (ruling R2-A5, after GSW 2007 and Anderson-Sleath 2001). US on-the-run and first off-the-run issues in each auction tenor (2, 3, 5, 7, 10, 20 and 30 years) get weight 0, but their residuals are still reported (R2-A6). They are identified from Fiscal Data's open auction API, which is free to use without restriction. No gilt is excluded. The residuals are model minus market dirty price.
4. Yield residual in bp: market yield minus the yield at market clean plus residual. Positive means cheap. A z-score is computed against the bond's own trailing 60 days, once 20 days exist.
5. Ranks within the 1-3, 3-7, 7-15 and 15+ year buckets, with the five cheapest and five richest bonds marked.

No page of results exists until a source is cleared. A study of whether the residuals mean-revert would be an R3 preregistration, not this workflow.
"""
