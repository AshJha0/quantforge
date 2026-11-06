# Curves

A curve says what one unit paid on a future date is worth today, or what a rate or price is expected to be on that date. Pricing, risk and hedging all read from curves, so a mistake here reaches everything else. Formally, a discount curve is a function `D(t)` with `D(0) = 1`, stored as dated pillars plus a rule for the dates in between (`specifications/02-curves/curve-framework.md`).

<p class="note">Every number and chart here comes from a real run of the four command-line builds. All inputs are synthetic, so these pages show the method, not a market. Stage B is at Implemented, not Validated: validation is self-assessment until the human review at the end of the project. Nothing is traded, and trading in this project is simulated only.</p>

Generated on 2026-11-06 from commit `c2379f1`.

## Status of every curve in the plan

An outside library in `verified_by` means QuantLib or Strata. The other cases have hand or replay sources, which can share a misreading with the spec. Each page gives the breakdown.

| Curve | Status | Stage | Evidence |
|---|---|---|---|
| [SONIA OIS](sonia-ois.md) | Implemented, not Validated | B | 18 golden cases for `rates.ois.bootstrap`, 17 with an outside library in `verified_by` |
| [SOFR OIS (minimal)](sofr-ois.md) | Implemented, not Validated | B | 16 golden cases for `rates.ois.bootstrap`, 16 with an outside library in `verified_by` |
| [USD-TERM-3M projection](usd-term-3m.md) | Implemented, not Validated | B | 6 golden cases for `rates.projection.bootstrap`, 5 with an outside library in `verified_by` |
| [GBPUSD FX forward](gbpusd-fx-forward.md) | Implemented, not Validated | B | 11 golden cases for `fx.forward.outright`, 0 with an outside library in `verified_by` |
| Equity spot and parity-implied forward, discrete dividends | Planned | C | None yet |
| Dividend curves | Planned | D | None yet |
| Borrow curves | Planned | D | None yet |
| Financing curves | Planned | D | None yet |
| Full SOFR | Planned | D | None yet |
| ESTR | Planned | D | None yet |
| Sovereign fits | Planned | D | None yet |
| Repo and special repo | Planned | D | None yet |
| Inflation, with seasonality | Planned | D | None yet |
| Cross-currency | Planned | D | None yet |
| Credit and ISDA CDS | Planned | D | None yet |
| Sector and rating curves | Planned | D | None yet |
| Commodity forward curves, with seasonality and storage carry | Planned | D | None yet |
| Swaption cube and cap surface | Planned | E | None yet |
| Funding curve | Planned | F | None yet |
| Liquidity curves | Planned | H | None yet |

## How the gallery is built

`tools/build_gallery.py` runs the CLIs and writes these pages and `docs/curves/data/`. CI reruns the Python CLI and fails if a committed number moves by more than 1e-10 plus 1e-08 relative, or 0.01 plus 1e-06 relative for risk figures. See [the guide](../developer-guides/curves-gallery.md).
