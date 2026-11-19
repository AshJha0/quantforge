# Stage K rulings, daily curve run lane

Proposed by lane k-curve-daily, 2026-11-19, for plan item K-11; not normative until the stage K coordinator confirms them. They govern `12-platform/daily-curve-run.md` and `tools/curve_daily/`. A separate file from the other stage K lanes so branches merge without conflict. Append-only; an amendment is a new row that names the row it amends. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

| # | Point | Ruling |
|---|---|---|
| KR-90 | Data terms | Sources: Treasury daily par yield CSV (the recorder's URL) and the Fed Board's `feds200628.csv`. Pages read 2026-11-19 (spec, Sources). Neither source states rules for automated fetching; the Fed's data are public domain with citation; Treasury's own reuse terms were not found. Rows therefore hold only fitted parameters, fit diagnostics, derived fitted zero rates and SHA-256 hashes of the inputs; no source row or file is committed, uploaded or printed by the scheduled job. Both attributions are in every input record |
| KR-91 | Inputs | Thirteen Treasury tenors (1, 2, 3, 4, 6 months; 1, 2, 3, 5, 7, 10, 20, 30 years); other columns ignored; a missing or unreadable cell of the thirteen is a failed fit, never a smaller fit |
| KR-92 | Fed input | `SVENY01` to `SVENY30` only, for consistency rows |
| KR-93 | Calendar | Library calendar `USGS` through `core.calendar.is_business_day`, as the paper ledger (KR-73); not `tools/recorder/holidays.txt` |
| KR-94 | Due | Business day D is due from 23:00:00 UTC on D |
| KR-95 | On time | A DAY row is on time if written no later than 19:30:00 UTC on the next business day; otherwise late. The verifier recomputes the label |
| KR-96 | Settling, late window, gaps, holdout | A date is settled by a DAY row `ok`, `fit_failed` or `holdout_blocked`, or a GAP row; `stale_input` and `fetch_failed` are retried. An unsettled date may be fitted late until 19:30 UTC on the fifth business day after its next business day, then becomes a GAP, never filled later. The first run starts at the latest due day, no back-fill. A date inside any prereg holdout window (`research/holdout_scan.py` `windows()`) gets a `holdout_blocked` row and no input is read |
| KR-97 | Par bonds | Per tenor a semi-annual bond with coupon the par yield, maturity D plus the tenor in months (day clamped to month end), settlement D, priced by `bond.price.from_yield` at its own yield |
| KR-98 | Weights | `1 / MD^2` with MD the modified duration from the same call, so the price objective is close to squared yield errors. Added after the first live dry run showed 70.58 bp at 1 month unweighted; recorded in the spec as a change made after seeing data |
| KR-99 | Fit | `bond.fit.nelson_siegel` over the 40-value tau grid 0.25 to 10 years (H-20 A3 grid); lowest objective, ties to the smaller tau; a tau that fails is listed with its code; all failing is `fit_failed` with the first code |
| KR-100 | Zeros and errors | Zero rates from 30 zero-coupon probe bonds at weight 0 in the same operation, checked bit-identical to the fit (`E_PROBE_MISMATCH` otherwise); fit errors through `bond.yield.from_price`. Fit flag (informational): RMSE at most 10 bp and largest error at most 25 bp, reason in the spec |
| KR-101 | Consistency check | Our zero rates minus the Fed's at 1 to 30 years, labelled "consistency check, not proof"; `within` when RMSE at most 15 bp and largest at most 40 bp, else `outside`; fixed in `config.json` (commit 7440c936) before any real-day run, reason in the spec; pending until the Fed posts the date; `unavailable` with a reason if the Fed skips it or after 30 days |
| KR-102 | Row format | `qf-curve-daily/1`; kinds GENESIS, DAY, GAP, CONSISTENCY; canonical bytes as HR-45; genesis holds the whole configuration. A change of configuration or fields needs a new format string and a new ledger |
| KR-103 | Chain and anchors | `prev`/`hash` SHA-256 chain; OpenTimestamps anchors on branch `curve-daily-anchors` after each push; every held anchor must match before a push |
| KR-104 | Verification | `verify_chain.py verify` reasons as listed in the spec, first failure only, never repairs; each has a planted-fault test (plan 14.10 rule 1) |
| KR-105 | Rebuild | `verify_chain.py rebuild` refits one ok day from a file copy whose SHA-256 matches and requires the fit to be equal |
| KR-106 | Site stub | `tools/curve_daily/site_page.py` renders the latest settled fit from `summary.json` with its labels; no existing page calls it until the dashboard lane wires it |
| KR-107 | Exit codes | `run_day.py`: 0 done; 1 refused, nothing written; 2 rows written and one records a problem (GAP, failed fetch or fit, stale input, holdout block), so the scheduled run turns red after pushing |
