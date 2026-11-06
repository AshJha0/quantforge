# ADR: Oracle for expected results

## Status
Accepted

## Decision
Expected results live in `oracle/`. They come from analytic and hand cases, or from outside libraries such as QuantLib, Strata, the ISDA CDS model and Open Source Risk Engine once each licence is checked. They never come from one of the four implementations.

## Consequences
The specification remains a shared-error risk: all four implementations and a hand case can share one misreading. Validation reports stay self-assessment until the human review at the end of the project, and say so.
