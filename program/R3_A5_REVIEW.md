# R3-01 amendment 5: second read (2026-11-14)

Reader: a separate Claude subagent (Opus 5.5), read-only, given the draft, `program/R3_NOTES.md`, `research/r3_runner.py`, `quantforge_core/bonds.py` and `calendars.py`. It used R3-01 in-sample yields up to 2012-12-31 only, opened no holdout file and computed no fly, z-score or return. Not a human check.

## The check (re-run independently by the reader)

Closed-form par DV01 `(1 - (1 + y/2)^(-2n)) / y / 10^4` against `price_from_yield` (`modified_duration x dirty / 100 / 10^4`), every in-sample business day from 2000-01-03 to 2012-12-31, tenors 2Y/5Y/10Y: 9,756 leg-days; 9,747 within relative 1e-9 (median 4e-15); 6 (2008-02-28, 2012-02-28) differ up to 1.37e-3 from the library's month-end roll of a 28 February maturity in a leap year (largest at 2Y, falling with tenor, as that cause implies); 3 (2000-02-28) refused by the library. `MIN_YEAR = 2000` confirmed. Counts match the draft.

## Findings

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | ok | Formula, `y = 0` limit `n/10^4`, unit per unit notional per bp correct | - |
| 2 | ok | Not tunable to outcomes: textbook form, equals the library to 1e-9 where both define the same bond; no R3-01 outcome computed | - |
| 3 | minor | `par_dv01_closed` cited but not yet in the runner | Added to `research/r3_runner.py` in the signing commit |
| 4 | minor | This review file did not exist | Written before signing |
| 5 | minor | Deviation note cited without path | Full path `research/DEVIATION-2026-11-14-a4-dv01-wording.md` |
| 6 | minor | Textbook citations by chapter name, no number | Kept by name: the signer could not verify chapter numbers without the books; stated here |

Verdict: no blockers. Signed as amendment 5 after fixes 3-5.

## Addendum (2026-11-14, after signing): full citations for finding 6

Amendment 5 is signed and is not edited. These are the full citations its chapter names refer to. The books were not opened; the chapter numbers and titles below are recalled and must be confirmed against a copy before anyone relies on them.

- Tuckman, B. and Serrat, A., *Fixed Income Securities: Tools for Today's Markets*, 3rd ed., Wiley, 2011. "The chapter on DV01, duration and convexity" is chapter 4, "DV01, Duration, and Convexity". "The chapter on curve trades" (amendment 4, R3-01 item 1) is chapter 6, "Empirical Approaches to Risk Metrics and Hedging", where the 50:50 butterfly is set against regression weights.
- Fabozzi, F. J., *Bond Markets, Analysis, and Strategies*, 8th ed., Pearson, 2013. "The chapter on measuring interest-rate risk" is chapter 4, "Bond Price Volatility" (edition chosen as the one recalled; numbering differs between editions).

Both are listed in `specifications/11-research/research-statistics.md` (sources `[TS11]`, `[Fab13]`) and so in `docs/references.md`, marked not opened.
