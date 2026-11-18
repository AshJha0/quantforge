# Review request: Almgren-Chriss efficient frontier (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: H. Evidence line from the project's curve table: Implemented on `stage-h` (v0.10.0, unreleased), all four languages; `ac_h` 10 goldens (5 value: 1 also against the paper's printed figure, 3 counted blind re-derived).

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. No free library implements Almgren-Chriss; the outside check is a blind second-lane re-derivation or [AC00]'s printed kappa (DR-H2), 3 of 5 value cases in `ac_h` (`oracle/OUTSIDE_SHARES.md`). Is a blind re-derivation from the same paper independent enough?

## Spec



## Golden cases

None found by operation name: answer "cannot check" for values.

## Outside-library evidence and limits (from the project's own page)

None stated.

## Real-data reconciliation

- Not applicable: a model curve on assumed parameters, not a market curve (HR-10).

## Rulings that name this curve's operations

None found by operation name.
