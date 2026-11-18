# Validation evidence pack

This folder gathers the evidence behind each curve in the [Curves gallery](../curves/README.md): one checklist per curve. Owner decision 2026-11-18: there is no second review, human or otherwise, and the gallery carries no per-curve validation status. The pack states what has been checked and how; it does not certify a curve. All inputs are synthetic except the real-data round trip below, and nothing is traded.

## What the pack holds

| Part | Where | What it shows |
|---|---|---|
| One checklist per curve | `docs/validation/<curve>.md` (29 pages, one per gallery row) | Spec, rulings, golden counts by source, outside-library share, the gallery's own oracle paragraph and limits, the real-data result, open questions, a "What to check" list |
| Outside-library checks added by the pack | `oracle/python/outside_validation.py`, `oracle/OUTSIDE_VALIDATION.json` | QuantLib 1.44 on the golden inputs, every compared output at the case's own tolerance |
| Real-data round trip | `tools/validation/reconcile_official.py`, `docs/validation/data/real-data.json` | SONIA and SOFR bootstraps against published fitted curves; pass or fail only |
| AI review packet | [`docs/validation/ai-review/`](ai-review/README.md) (one self-contained prompt per curve, about 30,000 characters or less) | Spec text, rulings, golden cases, evidence and questions for an outside model with no repository access; its answer is filed as a labelled "AI review" section and checked against the repository before anything is acted on |
| How to use the pack | [HOW-TO-REVIEW.md](HOW-TO-REVIEW.md) | Rebuilding the pack and running the optional AI check |
| Page generator | `tools/validation/build_checklists.py` (`--check` for staleness) | Reads the counts from the gallery data and the goldens, so a page cannot drift from them |

## Outside-library checks (option C)

Before the pack, four stage B and C curves had value cases with no outside library in `verified_by`. Each check runs QuantLib on the golden's own inputs; a case is tagged only if every compared output agrees at its tolerance class (`conformance/tolerances/policy.yaml`). No golden value changed: the only golden field touched is `verified_by` (observed: `git diff` shows only those arrays).

| Curve | Before (v0.9.0) | After | Library object | Not covered, and why |
|---|---|---|---|---|
| GBPUSD FX forward | 0 of 11 | 11 of 11 | `FxForward.fairForwardRate`, `DiscountingFxForwardEngine` | none |
| Equity forward | 0 of 4 | 2 of 4 | `AnalyticDividendEuropeanEngine`, forward by put-call parity | `-0012`: disagreement on a dividend dated on `as_of` (below); `-0014`: expiry on `as_of`, nothing to price |
| SVI smile | 1 of 2 | 2 of 2 | `SviSmileSection` | `g` by central differences on the library variance, checked at 1e-6 |
| SSVI surface | 0 of 3 | 3 of 3 | `SviSmileSection` per slice, through the raw-SVI form of an SSVI slice | no library has SSVI; the two arbitrage flags are arithmetic on the parameters |
| Funding curve (round 2) | 0 of 3 | 3 of 3 | OIS `DiscountCurve`, `InterestRate(Simple)`, log-linear ratio curve (row FUND.RATIO, `oracle/outside_register_f.json`) | none |
| Financing term structures (round 2) | 0 of 13 | 13 of 13 | `LinearInterpolation` on the cumulative quantities, `InterestRate(Simple)`; outputs arithmetic, so library-primitive (`oracle/OUTSIDE_J.json`) | none |
| Liquidity curves (round 2) | 0 of 7 | 0 of 7 | scipy `brentq` agrees on the optimal horizon and minimum cost for all 7, but no library computes the cost curve, so not counted | all 7: the rest is the spec's arithmetic |
| Coupon schedules, M24 (H-19) | 0 of 54 | 53 of 54 | `Schedule` (Backward, ModifiedFollowing), `Calendar.advance` for payment dates | `rulings_b` B1: QuantLib refuses the degenerate schedule (end adjusts back onto start); the spec's rule 4 gives an empty schedule |

All figures are observed from `oracle/OUTSIDE_VALIDATION.json`. Stages B and C are outside the R6-13 share table (`oracle/OUTSIDE_SHARES.md` covers D to J), so that table and the golden totals (`tools/check_case_total.py`) do not change. The stage D checks added in H-19 (2026-11-18) are counted in `oracle/outside_register.json` and the REPORT.md coverage table instead (stage D 71.9%, 470 of 654).

One disagreement, settled by ruling C18 (owner, 2026-11-18; `specifications/stage-c-rulings.md`): `equity_forward-0012` has a dividend with `ex_date` equal to `as_of`. The spec ignores it (`specifications/02-curves/equity-forward.md`, "Dividends with `ex_date <= as_of` ... are ignored"); QuantLib's engine counts a dividend dated on the evaluation date. With that dividend removed, QuantLib agrees on all four outputs (observed, `probe_without_as_of_dividend_pass` in the register). This is a boundary convention, not an arithmetic error, and the ruling records the choice.

Round 2 (2026-11-18) added the funding, financing and liquidity rows above. The R6-13 shares moved: stage F value cases 53.0% to 53.7%, stage J 61.3% to 67.5% (observed, `oracle/OUTSIDE_SHARES.md`).

## Real-data reconciliation (option B)

Free data has no SOFR, SONIA or ESTR swap quotes (stage D data survey, LEARN.md), so the round trip takes its quotes from a published fitted curve: QuantLib `MakeOIS` prices par rates on the published curve, QuantForge `rates.ois.bootstrap` rebuilds the curve from them, and the pillars are compared with the published curve. The tolerance, 0.5 bp on the zero rate at every pillar, was stated in the script before the first run.

| Curve | Published curve | Standard tenors | Every-year tenors | Between pillars |
|---|---|---|---|---|
| SONIA | Bank of England fitted OIS curve, 2026-11-16 | pass at 0.5 bp | pass at 0.01 bp | not compared (method difference) |
| SOFR | Fed staff GSW Treasury zero curve, 2026-11-13 | pass at 0.5 bp | pass at 0.5 bp, fails 0.1 bp | not compared (method difference) |
| ESTR | ECB euro area AAA government curve (Svensson parameters), 2026-11-16 | pass at 0.5 bp | pass at 0.5 bp (thin margin at the 1M pillar), fails 0.1 bp | not compared (method difference) |

Observed from `docs/validation/data/real-data.json` (Python CLI). Method differences (derived): QuantForge interpolates log-linearly in the discount factor between pillars, while GSW is a Svensson fit and the BoE curve a spline; so coupon dates that fall between sparse pillars (7Y, 10Y, ...) carry a small gap, and the every-year set removes it. SOFR's remaining gap comes from the two-day stub between `as_of` and the spot date, which no quote covers. The GSW curve is a Treasury curve and a staff research product, not an official statistical release, and the ECB curve is a government bond curve, so the SOFR and ESTR results test the bootstrap on a real curve shape, not SOFR or ESTR levels; ESTR's two-day stub is the same effect as SOFR's. BoE values are Bank copyright for internal use: no value is published here, only pass or fail at the stated tiers.

Inputs, all free with no sign-up: `https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv`; the Bank of England zip at the URL in `tools/workflows/boe_curves.py`; and the ECB series `https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.<KEY>?lastNObservations=1&format=csvdata` for KEY in BETA0, BETA1, BETA2, BETA3, TAU1, TAU2, SR_1Y, SR_10Y, saved as `ecb_<KEY>.csv`.

To rerun (QuantLib in the oracle venv, the CLI on the host):

```bash
UV_PROJECT_ENVIRONMENT=~/qf-oracle-venv uv sync --project oracle/python
```

```bash
<oracle python> tools/validation/reconcile_official.py quotes --gsw feds200628.csv --boe latest-yield-curve-data.zip --ecb <folder with ecb_*.csv> --work <scratch dir>
```

```bash
python tools/validation/reconcile_official.py compare --work <scratch dir> --out docs/validation/data/real-data.json
```

## How the checklists are used

Each checklist lists the spec, the rulings, the golden sources, the outside-library share, the real-data result and the open questions for one curve, and ends with a "What to check" list for anyone reading the evidence. Everything below the line `<!-- Hand-filled below this line ... -->` is kept when the pages are rebuilt, so any AI review section or note goes there. No checklist, and nothing in this folder, changes the gallery table: `tools/build_gallery.py` writes that table from the gallery data alone.

## AI review

An AI review is an optional extra check: a model can recheck formulas and look for gaps a single author missed. It may be attached to a checklist as a separate section headed "AI review", stating the model, the date and what it checked. Its findings count only once checked against the spec or golden they quote, because the model shares the failure modes of the tools that built the evidence and can be confidently wrong.
