# Curves

A curve says what one unit paid on a future date is worth today, or what a rate or price is expected to be on that date. Pricing, risk and hedging all read from curves, so a mistake here reaches everything else. Formally, a discount curve is a function `D(t)` with `D(0) = 1`, stored as dated pillars plus a rule for the dates in between (`specifications/02-curves/curve-framework.md`).

<p class="note">Every number and chart here comes from a real run of the four command-line builds. All inputs are synthetic, so these pages show the method, not a market, except the one Real data page below. The Evidence column says how each curve is checked. Nothing is traded, and trading in this project is simulated only.</p>

Generated on 2026-11-07 from commit `8dddd58`.

## Every curve in the plan

An outside library in `verified_by` means QuantLib or Strata. The other cases have hand or replay sources, which can share a misreading with the spec. Each page gives the breakdown. The papers and standards behind each curve are cited in its spec and collected in [References](../references.md).

| Curve | Stage | Evidence |
|---|---|---|
| [SONIA OIS](sonia-ois.md) | B | 18 golden cases for `rates.ois.bootstrap`, 17 with an outside library in `verified_by` |
| [SOFR OIS (minimal)](sofr-ois.md) | B | 16 golden cases for `rates.ois.bootstrap`, 16 with an outside library in `verified_by` |
| [USD-TERM-3M projection](usd-term-3m.md) | B | 6 golden cases for `rates.projection.bootstrap`, 5 with an outside library in `verified_by` |
| [GBPUSD FX forward](gbpusd-fx-forward.md) | B | 11 golden cases for `fx.forward.outright`, 11 with an outside library in `verified_by` |
| [Equity forward, discrete dividends](equity-forward.md) | C | 4 golden cases for `eq.forward.outright`, 2 with an outside library in `verified_by` |
| [SVI smile](svi-smile.md) | C | 2 golden cases for `vol.svi.evaluate`, 2 with an outside library in `verified_by` |
| [SSVI surface](ssvi-surface.md) | C | 3 golden cases for `vol.ssvi.evaluate`, 3 with an outside library in `verified_by` |
| [SABR](sabr.md) | C | 32 golden cases for `vol.sabr.hagan`, `vol.sabr.density`, `vol.sabr.arbfree`, 26 with an outside library in `verified_by` |
| [Full SOFR, ESTR, SONIA OIS](ois-full.md) | D | 81 golden cases |
| [Bond and sovereign fits](bond-fit.md) | D | 2 golden cases |
| [Repo and special repo](repo.md) | D | 4 golden cases |
| [Cross-currency](cross-currency.md) | D | 1 golden case |
| [Credit and ISDA CDS](cds.md) | D | 6 golden cases |
| [Dividend and borrow](dividend-borrow.md) | D | 4 golden cases |
| [Inflation, with seasonality](inflation.md) | D | 2 golden cases |
| [Caps and swaptions](caps-swaptions.md) | D | 22 golden cases |
| [Commodity forwards](commodities.md) | D | 4 golden cases |
| [Sector and rating curves](sector-rating.md) | D | 2 golden cases for `credit.curve.composite`, 2 with an outside library in `verified_by` |
| [Funding curve](funding.md) | F | 3 golden cases for `rates.funding.curve`, 3 with an outside library in `verified_by` |
| [Financing term structures](financing-term.md) | J | 13 golden cases for `repo.term.curve`, `eq.forward.term_financed`, 13 with an outside library in `verified_by` |
| [Liquidity curves](liquidity.md) | J | 7 golden cases for `liq.curve.cost`, 0 with an outside library in `verified_by` |
| [MBS](mbs.md) | D | 3 golden cases |
| [Implied vol surface](vol-surface.md) | E | 2 golden cases |
| [Local volatility](local-vol.md) | E | 2 golden cases |
| [Swaption cube](swaption-cube.md) | E | 42 golden cases |
| [Vol term structure](vol-term-structure.md) | E | 7 golden cases |
| [Five interpolation methods](interpolation-methods.md) | F | 47 golden cases for `rates.curve.inspect`, 36 reproduced by an outside library |
| [Hedging against trading costs](hedging-costs.md) | I | 33 golden cases for `hedge.qp.solve` with costs and `hedge.frontier.solve`, 15 reproduced by an outside library |
| [Research workflow: backtest to PBO](research-workflow.md) | J | 83 golden cases for the backtest, purged CV and research statistics, 31 reproduced by an outside library; synthetic prices, a teaching example |
| [Almgren-Chriss efficient frontier](ac-frontier.md) | H | Implemented (v0.10.0), all four languages; `ac_h` 10 goldens (5 value: 1 also against the paper's printed figure, 3 counted blind re-derived) |
| [Market impact curves: square-root and Obizhaeva-Wang](impact-curves.md) | H | Implemented (v0.10.0), all four languages; `imp_h` 9 goldens (4 value, all blind re-derived); not calibrated |
| [Intraday volume profile (VWAP input)](volume-profile.md) | H | Implemented (v0.10.0), all four languages; `exec.schedule.vwap` cases in `sched_h` (blind re-derived) |
| [Walk-the-book cost curves (crypto venue, recorded)](walk-the-book.md) | H | Planned; research item H-1(b), no result yet; crypto venue, not equities or rates; aggregates only |

Stage J wave 3 (historical scenario stress, interpolation backtests, drift detectors) has no gallery page: those operations take a curve, a smile or a series rather than build a curve, so they are worked through in [Tutorial 33](../getting-started/tutorial-33-stress-test-and-watch-for-drift.md) instead.

## Real data

[US Treasury curve with sanity bands](real-usd-treasury.md): a page built from real public data, snapshot of 2026-11-06. The same bands run daily in workflow (a).

[Calibration stability](calib-stability.md): seven calibrations under seeded noise in four languages, synthetic inputs. [Rich/cheap screen](rich-cheap.md): workflow (b), blocked on data until a price source is cleared.

[Validation evidence pack](../validation/README.md): one evidence checklist per row of the table above, the outside-library checks behind it, and a round trip of the SONIA and SOFR bootstraps against published fitted curves.

## Risk and capital term structures

Some risk and capital figures are themselves functions of tenor or time: a regulator's risk weight per tenor, an exposure profile over a trade's life, a supervisory duration. This section lists only what is built and released today; it has no chart yet, and nothing here is a gallery row.

| Term structure | What it is | Where (released) | Evidence |
|---|---|---|---|
| FRTB GIRR delta risk weights | Regulator's weight per tenor vertex: 1.7% at 0.25Y and 0.5Y, 1.6% at 1Y, 1.3% at 2Y, 1.2% at 3Y, 1.1% from 5Y to 30Y (MAR21.42 Table 1) | `risk.frtb.girr_delta`, `specifications/06-risk/frtb-sa-girr.md`, stage F | regulator text, read in stage F; goldens re-derived under the stage F rule |
| Key-rate DV01 ladder | Sensitivity of a position to each curve tenor, money per basis point | `risk.ois.dv01` and the R2 key-rate operations, `specifications/06-risk/par-and-key-rate.md` | goldens; see [Tutorial 1](../getting-started/tutorial-1-swap.md) |
| Exposure profile under Hull-White | Expected exposure EE(t) and the deflated quantile `deflated_pfe_q(t)` over a swap portfolio's life; the quantile is of deflated value, not PFE as a desk reads it (R6-5.1) | `xva.exposure.portfolio_hw`, `specifications/06-risk/xva-exposure-portfolio.md`, stage G | 80 of 96 value cases within 3 Monte Carlo standard errors of ORE 1.8.17 (`oracle/OUTSIDE_SHARES.md`) |

Not shown here until released (stage K): SA-CCR supervisory duration and maturity factors (built in all four builds and merged on the integration branch `k-r1`, not released), FRTB internal-model liquidity horizons (wave 2, specification only), and the sensitivity-based margin's tenor weights, which use placeholder weights from a stated rule.

## How the gallery is built

`tools/build_gallery.py` runs the CLIs and writes these pages and `docs/curves/data/`. CI reruns the Python CLI and fails if a committed number moves by more than 1e-10 plus 1e-08 relative, or 0.01 plus 1e-06 relative for risk figures. See [the guide](../developer-guides/curves-gallery.md).
