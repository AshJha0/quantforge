# Known issues: open audit findings

This page lists every open Critical or Major finding of the different-model audits of stage K round 1 (three audits, 2026-11-19, by a model that did not write the audited work; plan rule 14.10-5). It is the register that the spec "Limits" sections point to. Older known issues are in the [README](../README.md#known-issues).

**State of the code.** Stage K round 1 is merged to `main` and is **not released**: there is no `v0.10.1` tag, and none is made until the findings below are closed or ruled. Evidence class of every row: measured or read by the auditor, as stated in the audit; rows marked "re-measured" were also checked by the project.

Plain reading: each row says what is wrong in one sentence, with the size where one was measured. "Open, fix in progress" means no fix is merged.

## Open

| Id | Severity | Operation or file | What is wrong | Status |
|---|---|---|---|---|
| KA-C9 | Critical | daily curve run, `tools/curve_daily/curve_core.py` | The chain can deadlock: if a date stays unsettled while a later date gets a row, the next retry writes a row the verifier refuses (`ORDER`), and every later run is refused too. Reproduced by the auditor on synthetic days. | open, fix in progress; the job is not scheduled |
| KA-C1 | Major | `.github/workflows/paper-ledger.yml` | Every run would commit and anchor even with no new row, because the summary file holds a count that changes on each run. | open, fix in progress; not scheduled |
| KA-C2 | Major | paper ledger, `tools/paper_daily/paper_core.py` | The "on time" label rests on the writing run's own clock; nothing outside ties a row to its time, so the 20-day count is self-declared unless anchors are checked. | open, fix in progress; not scheduled |
| KA-C3 | Major | paper ledger gate, `verify_ledger.py --require-days 20` | The gate command as written checks no anchors, and with `--no-cli` it skips the calendar checks. | open, fix in progress; not scheduled |
| KA-C4 | Major | paper ledger | No check reads the forward log, so the link from a ledger row to its recorded source row is declared, not verified. | open, fix in progress |
| KA-C5 | Major | both daily workflows | The commit recorded in a row can differ from the commit of the code that ran. | open, fix in progress |
| KA-C10 | Major | daily curve run | A download that is not the data file (for example a maintenance page) is recorded as a failed fit, which is final, so one bad page loses the day for good. | open, fix in progress |
| KA-C11 | Major | daily curve run, spec and rows | The row's per-tenor errors let anyone recover the 13 published par yields exactly, while the spec says no source row is published; the paper ledger takes the opposite position on the same data. | open, fix in progress; not scheduled |
| KA-C12 | Major | both daily workflows | Scheduled runs on GitHub land hours late (the recorder's own runs: 3.5 to 8 hours, 2026-11-10 to 2026-11-19), so the "second chance" run would miss the on-time cut-off and not count. | open, fix in progress; not scheduled |
| KA-C13 | Major | paper ledger rebuild | Old rows are rebuilt with the current code, so a later additive change to an operation's outputs would make every old row fail. | open, fix in progress |
| KA-C18 | Major | outside-check shares, `tools/outside_shares.py` | Cases checked against a figure printed in a Basel text are counted although only part of their outputs is checked, at print precision. By the strict reading SA-CCR is 7 of 16, backtesting 11 of 24 and stage K 50 of 87 (57.5%), under the 60% floor; as counted they are 12 of 16, 23 of 24 and 78 of 87. Both figures are generated (`oracle/OUTSIDE_SHARES.md`). Re-measured. | open, under review: needs a ruling |
| KA-C20 | Major | E1 gate, `tools/check_e1_coverage.py`, ruling KR-112 | The exemption ignores any Real in any `E_SCHEMA` golden of an exempt operation, whatever caused the error, and no golden sends a non-finite token to `risk.frtb.backtest.zone` or `.desk`. | open, fix in progress |
| KA-A1 | Major | `cli-contract.md`, wave 1 operations | The error order stated for the wave 1 operations (`E_LIMIT` checked last) contradicts the contract's general rule (`E_LIMIT` straight after `E_SCHEMA`). | open, fix in progress |
| KA-A2 | Major | `core.store.bitemporal_query` | The spec allows 1,000,000 records while the general limit on any input array is 100,000. | open, fix in progress |
| KA-A3 | Major | SA-CCR (`saccr_k`), ruling KR-34 | Volatility hedging sets follow the caller's label where CRE52.45 to 52.47 fix their construction: two offsetting equity variance swaps give 320 against 195.96 under the Basel text. | open, fix in progress |
| KA-A4 | Major | recalibration trigger, output `false_alarm_rate` | It reports the rate for a known volatility, 0.27% at `k` = 3, where the true rate with a window of 4 changes is 5.8% (21 times higher). | open, fix in progress |
| KA-A5 | Major | recalibration trigger, zero sigma | A constant window such as `[0.1, 0.1, 0.1]` gives sigma 1.7e-17 and no error, so the trigger fires on any move; whether a constant window is caught depends on rounding. | open, fix in progress |
| KA-A6 | Major | `risk.intraday.delta_gamma_bound` | In binary64 the bound can be exceeded for moves below about 1e-7: the error is 1.40 times the bound at 1e-8 and 21.6 times at 1e-9 (absolute size about 1e-17 on a million). | open, fix in progress |
| KA-A16 | Major | FRTB backtesting probabilities | The binomial sum drifts as `observations` grows: relative error about 1e-10 at 100,000 and 7e-10 at 1,000,000 in the Python build, against the 1e-12 claimed; the C++ and Rust builds use a different recurrence and differ from Python at that size. | open, fix in progress |
| KA-B1, KA-B2, KA-B3 | Critical, Major, Major | Bermudan ladder, `method` `CN_RANNACHER_SMOOTHED` | **The R6 use restriction stays for both methods: not for hedging.** The new method's evidence is on the three cases it was developed on and at 201/100 only; at 101/50 two of them miss 1% (-1.53%, +1.49%); on a deep in-the-money receiver d/da is 7% to 9% off. Re-measured (`program/k8_audit_response/`). | restriction stays (KR-113); lifting it needs an out-of-sample acceptance, to be written, in a later point release |

## Closed

| Id | What was wrong | Closed by |
|---|---|---|
| KA-B1 to KA-B3 (the lift) | The restriction had been lifted for `CN_RANNACHER_SMOOTHED` without naming a grid, on in-sample evidence. | Lift withdrawn before release: ruling KR-113, commits 296bb471 and 0d2e7040 |
| KA-B4, KA-B5, KA-B6 | H-9 R2 rules: "exactly one" against "at least one" candidate; spec items not amended by later rulings; window-selection options unchecked. | Branch `k-h9-fu` (HR-134 builder, HR-135), merge commit b48b85df |
| KA-C17 | The README status block said K-8 misses its acceptance while other pages said the restriction was lifted. | `tools/site_facts.json` now states the KR-113 position; README regenerated (the commit that added this page) |

Minor findings are tracked in the audit responses, not here.
