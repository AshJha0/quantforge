# Data availability

Per plan section 8, corrected by the stage B data survey of 2026-11-06, which is a reading of published terms and not legal advice. Each source's terms must be recorded in a manifest before use. Questions for the Bank of England, and the DTCC and DMO terms, are the owner's.

| Item | Status | Data | Notes |
|---|---|---|---|
| Overnight compounding, OIS floating leg accrual | Real | SONIA, SOFR, ESTR | Check against published compounded indices. An arithmetic check, not curve validation |
| Interpolation leave-one-out | Real, fitted data | BoE, ECB, Treasury curve nodes | Fitted, not quotes. Errors measure their smoothing, so report as interpolation tests only |
| FX spot series, spot-based hedging P&L | Real | ECB, Fed H.10; BoE spot for local use | H.10 is recorded from the release page's XML zip, which does not depend on the Fed's download tool |
| GBP/USD covered parity and forward points, 1979 to mid-2021 | Real, conditional | BoE `XUDLDS*`, `XUDLDF*`, with same-period rates | Subject to the Bank's licence answer. Local only. Noisy at short tenors. Ends 30 Jun 2021. Fix a held-out range first. Do not call the inferred basis market basis |
| Multi-instrument SOFR curve from one day of traded prices | Conditional, exploratory | Swap repository trades | Only if terms and access clear. Trade-derived, not quotes |
| SONIA OIS global solve from quotes | Labelled synthetic | None free. BoE curve may give a realistic shape, with a label | Never treat BoE fitted curves as quotes |
| SOFR swap curve from quotes | Labelled synthetic | As above | |
| Term swap curves, FRA and futures strips, convexity | Labelled synthetic | No usable settlements | CME and ICE terms rule them out |
| FX forwards after June 2021, other pairs | Labelled synthetic | None found | |
| Cross-currency basis, multi-curve FX | Labelled synthetic | None found | |
| Bid/ask fit | Labelled synthetic | None found | |
| Solver, repricing and QuantLib targets | Not data-dependent | Same quotes both sides | |
| Later stages: gilt RV, option surfaces, FX vol, swaptions, inflation swaps, credit, borrow, order books | Method test or labelled synthetic, as before | Gilts: DMO terms unread | Not resurveyed here |
| VaR, ES | Conditional | ECB, Fed series | FRED is no longer a source |

FRED is dropped: its terms bar storing content, and it needs a key. Terms, source by source, are in `oracle/LICENCES.md`.

## Circularity warnings

- BoE OIS and gilt, ECB and Treasury curves are model output. Turning them into pseudo par quotes and bootstrapping them back only shows the code inverts a smooth curve. A Treasury par curve is the same case.
- Comparing our curve with the Bank's needs the same inputs, which are not published, so a gap cannot be attributed.
- Deriving forwards from rates, then testing against those rates, is an identity. Use independently sourced forwards and rates.
- Do not fit to a period and test on it.

A 250-day record cannot exist inside the build, so v1.0 verdicts stay "conditionally approved".
