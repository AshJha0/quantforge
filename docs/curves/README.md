# Curves

A curve says what one unit paid on a future date is worth today, or what a rate or price is expected to be on that date. Pricing, risk and hedging all read from curves, so a mistake here reaches everything else. Formally, a discount curve is a function `D(t)` with `D(0) = 1`, stored as dated pillars plus a rule for the dates in between (`specifications/02-curves/curve-framework.md`).

<p class="note">Every number and chart here comes from a real run of the four command-line builds. All inputs are synthetic, so these pages show the method, not a market, except the one Real data page below. Every page in the table is at Implemented, not Validated, unless its row says otherwise: validation is self-assessment until the human review at the end of the project. Nothing is traded, and trading in this project is simulated only.</p>

Generated on 2026-11-07 from commit `8dddd58`.

## Status of every curve in the plan

An outside library in `verified_by` means QuantLib or Strata. The other cases have hand or replay sources, which can share a misreading with the spec. Each page gives the breakdown. The papers and standards behind each curve are cited in its spec and collected in [References](../references.md).

| Curve | Status | Stage | Evidence |
|---|---|---|---|
| [SONIA OIS](sonia-ois.md) | Implemented, not Validated | B | 18 golden cases for `rates.ois.bootstrap`, 17 with an outside library in `verified_by` |
| [SOFR OIS (minimal)](sofr-ois.md) | Implemented, not Validated | B | 16 golden cases for `rates.ois.bootstrap`, 16 with an outside library in `verified_by` |
| [USD-TERM-3M projection](usd-term-3m.md) | Implemented, not Validated | B | 6 golden cases for `rates.projection.bootstrap`, 5 with an outside library in `verified_by` |
| [GBPUSD FX forward](gbpusd-fx-forward.md) | Implemented, not Validated | B | 11 golden cases for `fx.forward.outright`, 0 with an outside library in `verified_by` |
| [Equity forward, discrete dividends](equity-forward.md) | Implemented, not Validated | C | 4 golden cases for `eq.forward.outright`, 0 with an outside library in `verified_by` |
| [SVI smile](svi-smile.md) | Implemented, not Validated | C | 2 golden cases for `vol.svi.evaluate`, 1 with an outside library in `verified_by` |
| [SSVI surface](ssvi-surface.md) | Implemented, not Validated | C | 3 golden cases for `vol.ssvi.evaluate`, 0 with an outside library in `verified_by` |
| [SABR](sabr.md) | Implemented, not Validated | C | 32 golden cases for `vol.sabr.hagan`, `vol.sabr.density`, `vol.sabr.arbfree`, 26 with an outside library in `verified_by` |
| [Full SOFR, ESTR, SONIA OIS](ois-full.md) | Implemented, not Validated | D | 81 golden cases |
| [Bond and sovereign fits](bond-fit.md) | Implemented, not Validated | D | 2 golden cases |
| [Repo and special repo](repo.md) | Implemented, not Validated | D | 4 golden cases |
| [Cross-currency](cross-currency.md) | Implemented, not Validated | D | 1 golden case |
| [Credit and ISDA CDS](cds.md) | Implemented, not Validated | D | 5 golden cases |
| [Dividend and borrow](dividend-borrow.md) | Implemented, not Validated | D | 4 golden cases |
| [Inflation, with seasonality](inflation.md) | Implemented, not Validated | D | 2 golden cases |
| [Caps and swaptions](caps-swaptions.md) | Implemented, not Validated | D | 22 golden cases |
| [Commodity forwards](commodities.md) | Implemented, not Validated | D | 4 golden cases |
| [Sector and rating curves](sector-rating.md) | Implemented, not Validated | D | 2 golden cases for `credit.curve.composite`, 2 with an outside library in `verified_by` |
| [Funding curve](funding.md) | Implemented, not Validated | F | 3 golden cases for `rates.funding.curve`, 0 with an outside library in `verified_by` |
| [MBS](mbs.md) | Implemented, not Validated | D | 3 golden cases |
| [Implied vol surface](vol-surface.md) | Implemented, not Validated | E | 2 golden cases |
| [Local volatility](local-vol.md) | Implemented, not Validated | E | 2 golden cases |
| [Swaption cube](swaption-cube.md) | Implemented, not Validated | E | 42 golden cases |
| [Vol term structure](vol-term-structure.md) | Implemented, not Validated | E | 7 golden cases |
| [Five interpolation methods](interpolation-methods.md) | Implemented, not Validated | F | 47 golden cases for `rates.curve.inspect`, 36 reproduced by an outside library |
| [Hedging against trading costs](hedging-costs.md) | Implemented, not Validated | I | 33 golden cases for `hedge.qp.solve` with costs and `hedge.frontier.solve`, 15 reproduced by an outside library |
| Financing term structures | Partly done | D | Repo financing is done (`repo.forward`, `repo.implied_rate` and the implied financing spread; see the repo row). Ruling D22 keeps borrow and financing as flat rates over the funding curve; financing term structures are not yet scheduled |
| Liquidity curves | Planned | H | None yet |

## Real data

[US Treasury curve with sanity bands](real-usd-treasury.md): a page built from real public data, snapshot of 2026-11-06. The same bands run daily in workflow (a).

[P&L explain and calibration stability](pnl-explain.md): full revaluation against key-rate explain over real daily Treasury moves, and day-to-day calibration diagnostics. Runs daily in `tools/workflows/keyrate_explain.py`.

[Calibration stability](calib-stability.md): seven calibrations under seeded noise in four languages, synthetic inputs. [Rich/cheap screen](rich-cheap.md): workflow (b), blocked on data until a price source is cleared.

## How the gallery is built

`tools/build_gallery.py` runs the CLIs and writes these pages and `docs/curves/data/`. CI reruns the Python CLI and fails if a committed number moves by more than 1e-10 plus 1e-08 relative, or 0.01 plus 1e-06 relative for risk figures. See [the guide](../developer-guides/curves-gallery.md).
