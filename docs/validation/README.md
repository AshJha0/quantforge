# Validation evidence pack

Every curve in the [Curves gallery](../curves/README.md) is at Implemented, not Validated. The project's rule (ROADMAP.md, "Stage status") is that only an independent human review moves a curve to Validated. This folder does not move any row. It gathers the evidence so that review is quick: one checklist per curve, each ending in a blank sign-off block.

## What the pack holds

| Part | Where | What it shows |
|---|---|---|
| One checklist per curve | `docs/validation/<curve>.md` (29 pages, one per gallery row) | Spec, rulings, golden counts by source, outside-library share, the gallery's own oracle paragraph and limits, the real-data result, open questions, sign-off block |
| Outside-library checks added by the pack | `oracle/python/outside_validation.py`, `oracle/OUTSIDE_VALIDATION.json` | QuantLib 1.44 on the golden inputs, every compared output at the case's own tolerance |
| Real-data round trip | `tools/validation/reconcile_official.py`, `docs/validation/data/real-data.json` | SONIA and SOFR bootstraps against published fitted curves; pass or fail only |
| AI review packet | [`docs/validation/ai-review/`](ai-review/README.md) (one self-contained prompt per curve, about 30,000 characters or less) | Spec text, rulings, golden cases, evidence and questions for an outside model with no repository access; its answer is filed as a labelled "AI review" section, never as the sign-off |
| Page generator | `tools/validation/build_checklists.py` (`--check` for staleness) | Reads the counts from the gallery data and the goldens, so a page cannot drift from them |

## Outside-library checks (option C)

Before the pack, four stage B and C curves had value cases with no outside library in `verified_by`. Each check runs QuantLib on the golden's own inputs; a case is tagged only if every compared output agrees at its tolerance class (`conformance/tolerances/policy.yaml`). No golden value changed: the only golden field touched is `verified_by` (observed: `git diff` shows only those arrays).

| Curve | Before (v0.9.0) | After | Library object | Not covered, and why |
|---|---|---|---|---|
| GBPUSD FX forward | 0 of 11 | 11 of 11 | `FxForward.fairForwardRate`, `DiscountingFxForwardEngine` | none |
| Equity forward | 0 of 4 | 2 of 4 | `AnalyticDividendEuropeanEngine`, forward by put-call parity | `-0012`: disagreement on a dividend dated on `as_of` (below); `-0014`: expiry on `as_of`, nothing to price |
| SVI smile | 1 of 2 | 2 of 2 | `SviSmileSection` | `g` by central differences on the library variance, checked at 1e-6 |
| SSVI surface | 0 of 3 | 3 of 3 | `SviSmileSection` per slice, through the raw-SVI form of an SSVI slice | no library has SSVI; the two arbitrage flags are arithmetic on the parameters |

All figures are observed from `oracle/OUTSIDE_VALIDATION.json`. Stages B and C are outside the R6-13 share table (`oracle/OUTSIDE_SHARES.md` covers D to J), so that table and the golden totals (`tools/check_case_total.py`) do not change.

One disagreement, reported and left for the reviewer: `equity_forward-0012` has a dividend with `ex_date` equal to `as_of`. The spec ignores it (`specifications/02-curves/equity-forward.md`, "Dividends with `ex_date <= as_of` ... are ignored"); QuantLib's engine counts a dividend dated on the evaluation date. With that dividend removed, QuantLib agrees on all four outputs (observed, `probe_without_as_of_dividend_pass` in the register). This is a boundary convention, not an arithmetic error, but it is a ruling a reviewer should confirm.

The stage D to J curves with no outside library (funding, financing term structures, liquidity) were not extended in this pack. Their checklists say why and what could be done.

## Real-data reconciliation (option B)

Free data has no SOFR or SONIA swap quotes (stage D data survey, LEARN.md), so the round trip takes its quotes from a published fitted curve: QuantLib `MakeOIS` prices par rates on the published curve, QuantForge `rates.ois.bootstrap` rebuilds the curve from them, and the pillars are compared with the published curve. The tolerance, 0.5 bp on the zero rate at every pillar, was stated in the script before the first run.

| Curve | Published curve | Standard tenors | Every-year tenors | Between pillars |
|---|---|---|---|---|
| SONIA | Bank of England fitted OIS curve, 2026-11-16 | pass at 0.5 bp | pass at 0.01 bp | not compared (method difference) |
| SOFR | Fed staff GSW Treasury zero curve, 2026-11-13 | pass at 0.5 bp | pass at 0.5 bp, fails 0.1 bp | not compared (method difference) |

Observed from `docs/validation/data/real-data.json` (Python CLI). Method differences (derived): QuantForge interpolates log-linearly in the discount factor between pillars, while GSW is a Svensson fit and the BoE curve a spline; so coupon dates that fall between sparse pillars (7Y, 10Y, ...) carry a small gap, and the every-year set removes it. SOFR's remaining gap comes from the two-day stub between `as_of` and the spot date, which no quote covers. The GSW curve is a Treasury curve and a staff research product, not an official statistical release, so the SOFR result tests the bootstrap on a real curve shape, not SOFR levels. BoE values are Bank copyright for internal use: no value is published here, only pass or fail at the stated tiers.

To rerun (QuantLib in the oracle venv, the CLI on the host):

```bash
UV_PROJECT_ENVIRONMENT=~/qf-oracle-venv uv sync --project oracle/python
```

```bash
<oracle python> tools/validation/reconcile_official.py quotes --gsw feds200628.csv --boe latest-yield-curve-data.zip --work <scratch dir>
```

```bash
python tools/validation/reconcile_official.py compare --work <scratch dir> --out docs/validation/data/real-data.json
```

## How a review works

1. The reviewer reads the checklist, the spec and the rulings it names, and ticks the boxes under "What to check".
2. The reviewer answers the open questions, in the checklist or in a linked issue.
3. The reviewer fills the sign-off block: name, date, verdict, conditions. A verdict of Validated, signed by a named person, is what moves the gallery row; the row is changed in a separate commit that links the signed checklist.

## AI review

An AI review is a useful second opinion: it can recheck formulas, rerun scripts and look for gaps a single author missed. It may be attached to a checklist as a separate section headed "AI review", stating the model, the date and what it checked. It is never counted as the sign-off and never moves a row, because it shares the failure modes of the tools that built the evidence and is not accountable for the verdict.
