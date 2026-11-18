# Review request: Market impact curves: square-root and Obizhaeva-Wang (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: H. Evidence line from the project's curve table: Implemented on `stage-h` (v0.10.0, unreleased), all four languages; `imp_h` 9 goldens (4 value, all blind re-derived); not calibrated.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. No free library implements the square-root law or Obizhaeva-Wang; all 4 value cases in `imp_h` are blind re-derived (DR-H2), and imp_h-0001 and -0002 check arithmetic on the stated form only.

## Spec



## Golden cases

None found by operation name: answer "cannot check" for values.

## Outside-library evidence and limits (from the project's own page)

None stated.

## Real-data reconciliation

- Not calibrated: the impact coefficient Y is an input. The crypto calibration (H-1) is a pilot on partial recorded days with no conclusions in v0.10.0.

## Rulings that name this curve's operations

None found by operation name.
