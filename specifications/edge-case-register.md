# Edge-case register

Version 1.0.0, 2026-11-07. Plan 11.2.2. Maintained every stage: a stage that adds an operation adds or updates rows here before its handover.

Each row is a real-world edge case. It is either **pinned**: named golden cases that all four languages pass, or **out of scope**: with the reason and the stage that would bring it in. "All four languages" means the stage D builds in the language worktrees, checked by the spec session on 2026-11-07. New cases are in suite `stage_d/edge_d`, written by `oracle/python/gen_r1_edge.py`.

| # | Edge case | State | Golden cases | Notes |
|---|---|---|---|---|
| E1 | Negative and zero rates | Pinned | Negative yields: the `bonds_d` price cases at -0.20% (`bonds_d-0003`, `bonds_d-0007`, ...) and the `outside_d` price cases at -0.50%; near zero, the `outside_d` cases at +0.01%. Zero yield: `edge_d-0001`, `edge_d-0002`. Negative fixings: `edge_d-0003` to `edge_d-0005`. All-zero fixings: `edge_d-0006` to `edge_d-0008`. Negative zero rates on a curve (D > 1): `edge_d-0009` | Bond, compounding and curve cases are also re-priced in QuantLib (`oracle/outside_register.json`). `E_DOMAIN` only where `1 + y/f <= 0` (`bonds_d` invalid cases) |
| E2 | Month end, leap day, stub periods | Pinned | Leap-day and end-of-month maturities: `outside_d-0001` to `outside_d-0021` (2028-02-29), the 2030-04-30, 2032-08-31 and 2045-02-28 bonds in `outside_d`. Stubs: `schedule_deep-0001` to `schedule_deep-0048`. Day counts over 29 February: `daycount-0001` onwards (stage A) | Settlement on a coupon date (accrued 0): the 2033-11-09 bond in `outside_d` |
| E3 | Holiday calendar changed after trade date | Out of scope | | Calendars are rule tables in `01-core/calendars.md`, not dated versions, so a build has one calendar at a time. A change (for example a new US federal holiday) is a spec change, with goldens regenerated. Dated calendar versions belong with the as-of data store in stage K. Calendar provenance and an expiry test are in `01-core/calendar-provenance.md` |
| E4 | Missing or republished fixings (SOFR revisions) | Pinned | Missing fixing: `compound_d-0022` (`E_INPUT`). Two values for one date: `compound_d-0029` (`E_INPUT`) | A revision is a new fixings list from the caller. The library never picks between two values. Keeping both versions, with times, is the as-of store's job (`01-core/asof-store.md`, stage A suites `store`, `store_a4` and `store_rulings`) |
| E5 | US T+1 settlement (2024-05-28) | Out of scope | | No operation derives settlement from a trade date: every bond, repo and equity operation takes the settlement date as an input. A settlement-lag convention would be added with trade capture in stage F |
| E6 | IBOR cessation dates | Pinned in part | Fallback rates after cessation: `compound_d-0031` to `compound_d-0034` | The ISDA spread adjustments fixed on 2021-03-05 are pinned. Cessation dates themselves are not modelled: the caller asks for the fallback rate. Pre-cessation IBOR projection stays the stage B projection curve |
| E7 | CPI rebasing; index lag at month boundaries | Lag pinned; rebasing out of scope | First and last day of a month: `edge_d-0015` (30 Nov), `edge_d-0016` (1 Dec), `edge_d-0017` (31 Dec). Mid-month: `inflation_d-0010`, `inflation_d-0011` | Rebasing: `base_ref_cpi` and the fixings are inputs on one base. Rebasing a series is a data step, not a pricing rule; it would come with real CPI data in the R3 inflation study |
| E8 | CDS default inside an accrual period; succession events | Accrual on default pinned; default and succession out of scope | Accrual on default inside every premium period: `credit_d-0004` to `credit_d-0008` and the `credit.cds.price` cases in `outside_d`, all re-priced in QuantLib's ISDA engine | Default settlement, auctions and succession need event handling and trade lifecycle: stage F (book) and G (credit models) |
| E9 | Ex-dividend between trade and settlement | Out of scope | | `04-pricing/bonds.md` has no ex-dividend period, so gilt-style ex-dividend trading is not priced. Equity dividends are inputs to `eq.*` forwards. Stage E adds discrete dividends to equity options; a bond ex-dividend rule needs a spec change first |
| E10 | Daylight-saving cut-offs | Pinned | `time-0104`, `time-0105`, `time-0106` (gap and overlap), and the `time` suite's 123 cases, checked against `zoneinfo` at 2,717,520 instants | |
| E11 | Very long maturities | Pinned | 2055 bond: `bonds_d-0017` to `bonds_d-0020`; 2053 bond in `outside_d`; 30Y OIS: `ois_d-0020` and `ois_deep-0020` onwards; 20Y swaptions in `outside_d` | Curves extrapolate flat-forward past the last pillar; long cases stay inside the pillars |
| E12 | Near-zero vol and time | Pinned | Zero: `black-0045`, `black-0047` (vol 0), `black-0046`, `black-0048` (time 0); `greeks-0044`, `greeks-0045` (`E_DOMAIN`). Near zero: `edge_d-0010`, `edge_d-0011` (vol 1e-6), `edge_d-0012`, `edge_d-0013` (one day), `edge_d-0014` (at the money, vol 1e-6) | Inputs chosen so the price is intrinsic value to far below tolerance, or a smooth at-the-money value, so no case depends on erfc rounding in the tail |
| E13 | Mark-to-market resetting cross-currency basis swap (the market EUR/USD instrument) | Out of scope | | `fx.xccy.*` is a synthetic constant-notional swap (ruling R1-1). The MTM-reset variant, with the USD notional reset each period at the FX forward, needs a new operation or a `notional_reset` input; planned with stage F trade capture. Until then no stage D result is a market xccy-implied curve |
| E14 | US bond market early close on Good Friday | Pinned | `edge_d-0018` to `edge_d-0021` (business-day status, 2023, 2024, 2026, 2027), `edge_d-0022` (adding a business day lands on 2026-04-03), `edge_d-0023`, `edge_d-0024` (SOFR compounding across Good Friday 2026, which has no SOFR fixing) | Ruling R1-6: an early close is a business day. Years from SIFMA in `datasets/calendar_provenance.json`; future years are holidays until SIFMA publishes. SOFR compounding still skips every Good Friday, since no SOFR is published |

## Stage E edge cases, spec B (E4, E6, E7, E8)

Numbered EB so spec A's block can be added without renumbering. Pinned means named golden cases; the language builds have not yet run them.

| # | Edge case | State | Golden cases | Notes |
|---|---|---|---|---|
| EB1 | GARCH at the stationarity edge | Pinned | `alpha + beta = 1` likelihood: `garch_e-0008` (`alpha = 0.3, beta = 0.7`); forecast refused: `garch_e-0023` (`E_DOMAIN`). `alpha = 0`: `garch_e-0007`; forecast with `alpha = beta = 0`: `garch_e-0022` | The likelihood exists for an integrated process; the long-run variance does not |
| EB2 | All-zero returns | Pinned | `garch_e-0016` (`E_DOMAIN`) | A numeric initial variance with zero returns is valid |
| EB3 | Variance swap with dividends | Pinned | `q != 0`: `varswap_e-0007`, `varswap_e-0008` | QuantLib's engine drops `q`; ruling E-B3 |
| EB4 | Negative rate in replication | Pinned | `varswap_e-0006` (`r = -0.5%`) | |
| EB5 | Coarse strike strip | Pinned | Density grid `varswap_e-0009` to `varswap_e-0020` | Shows the strip bias; the spec prices the strip given and never fills strikes |
| EB6 | VIX zero bids: isolated and consecutive | Pinned | `vix_e-0002`, `vix_e-0003`, `vix_e-0005`, `vix_e-0006` | An isolated zero is skipped; two in a row stop the walk; strikes beyond are excluded (checked) |
| EB7 | VIX forward between strikes, K0 below the at-the-money strike | Pinned | `vix_e-0001` (F = 99.9, K0 = 95) | |
| EB8 | VIX term outside 30 days | Pinned | `vix_e-0016` (`E_INPUT`) | No extrapolation, ruling E-B6 |
| EB13 | VIX near or next term exactly 30 days | Pinned | `vix_e-0009` (`N1 = 43200`), `vix_e-0010` (`N2 = 43200`) | Weights 1 and 0 |
| EB14 | Unsorted strip; zero bid at the ATM strike; no OTM puts | Pinned | `vix_e-0017`, `vix_e-0018`, `vix_e-0021` (`E_INPUT`) | Ruling E-B15 against Cboe v5.0 3(a) |
| EB15 | Correlation matrix already valid | Pinned | `corr_e-0010`, `corr_e-0012`, `corr_e-0018` | Nearest returns the input |
| EB16 | Correlation with an entry near -1 after repair | Pinned | `corr_e-0020` | |
| EB17 | Implied correlation exactly 1 (equal vols, index vol equal) | Pinned | `corr_e-0032` | Not clipped (E-B20) |
| EB9 | Swaption exactly on a cube node | Pinned | `ratesvol_e-0001` to `ratesvol_e-0005`, `ratesvol_e-0009`, `ratesvol_e-0012` | Parameters equal the node's; checks the time axis |
| EB10 | Cap quotes with calendar arbitrage | Pinned | `ratesvol_e-0023` (`E_ARBITRAGE`) | Ruling E-B10: rejected, not clipped |
| EB11 | Zero-strike inflation floor | Pinned | Bachelier YoY floor at 0%: `ratesvol_e-0042`; ZC floor at 0% (`strike_ratio = 1`): `ratesvol_e-0046`; Black YoY floor at 0%: `ratesvol_e-0044` (`E_DOMAIN`) | Deflation protection |
| EB12 | Implied vol with premium below intrinsic | Pinned | `ratesvol_e-0038` (`E_DOMAIN`) | |

## Rules for adding a row

- A row is pinned only by golden cases that every language passes. Name them by `case_id`.
- Out of scope needs a reason and the stage that would bring it in.
- A new case avoids libm-tail and iteration-path sensitivity, as `oracle/README.md` asks.
