# Stage K rulings, daily curve run lane

**Status: CONFIRMED 2026-11-19 by the stage K coordinator lane (branch k-r1), KR-91 to KR-107; KR-90 binds only together with KR-109, which corrects its last sentence.** Results in "Confirmation" at the end.

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
| KR-109 | Attribution (amends KR-90's last sentence; stage K coordinator lane, integration 2026-11-19) | KR-90 says "Both attributions are in every input record" and the spec says every row names both. The code writes each source's attribution in the record that uses that source: a DAY row's `input` carries the Treasury attribution, a CONSISTENCY row's `gsw` carries the Fed's, the GENESIS row's `config` holds both, and a record that used no source data (failed fetch, unreadable file, GAP) carries the URL and no attribution. That is the binding rule: the citation goes with the data used. The site stub names both sources on every page |

## Confirmation (stage K coordinator lane, 2026-11-19)

Checked against `12-platform/daily-curve-run.md`, `tools/curve_daily/curve_core.py`, `run_day.py`, `verify_chain.py`, `config.json`, `site_page.py`, `python/tests/test_curve_daily.py` and `.github/workflows/curve-daily.yml` (evidence class read; the 23 tests are the measured check).

| # | Result | Note |
|---|---|---|
| KR-90 | **Not confirmed as written** | Its last sentence does not match the code (`curve_core.py` writes the Treasury attribution only in DAY inputs, the Fed's only in CONSISTENCY rows, none in failed-fetch inputs). Not edited; KR-109 corrects it and binds with it. The rest of KR-90 (sources, terms read, hashes not rows) matches |
| KR-91 to KR-97 | Confirmed | Thirteen tenors; schedule (due after 23:00 UTC); on time "no later than" 19:30 UTC as written (<=; amended by KR-111 to strictly before, as paper KR-82); late limit five business days; month-end clamp |
| KR-98 | Confirmed | Weights 1/MD^2, added in eff76a68 after 7440c936 and after one real day was seen, as the ruling and the spec disclose |
| KR-99 to KR-101 | Confirmed | 40-value tau grid, ties to the smaller tau; fit flag 10 / 25 bp; consistency tolerance 15 / 40 bp in `config.json` at 7440c936 before any real-day run; `outside` recorded, never dropped (the 2026-11-13 dry run is a recorded miss) |
| KR-102 to KR-107 | Confirmed | Row format, chain and anchors, verifier, rebuild, site stub, exit codes 0 / 1 / 2 |
| KR-109 | Confirmed | Written at integration |
| KR-111 | Confirmed | Written at integration |
| KR-111 | On time at the boundary (amends KR-95; stage K coordinator lane, integration 2026-11-19) | KR-95 said "no later than 19:30:00 UTC" (on time at 19:30:00 exactly); the paper ledger's KR-82, fixed first (commit 44ea219c, 12:12 UTC, against acb80745, 13:40 UTC), says "started before 19:30:00 UTC". The two daily jobs now use one rule, the paper's: on time strictly before 19:30:00 UTC on the next business day; 19:30:00 is late. `curve_core.py` compares with `<` in the writer and the verifier; `test_cutoff_boundary_second` in both test files checks 19:29:59 (on time) and 19:30:00 (late). No ledger exists yet, so no row is relabelled. The late window of KR-96 is unchanged |
