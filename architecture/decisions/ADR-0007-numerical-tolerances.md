# ADR: Domain-specific numerical tolerances

## Status
Accepted

## Decision
Use explicit absolute and relative tolerances per calculation and test class.

## Consequences
Each tolerance must be justified by conditioning, algorithm, precision and intended use. Do not hide material differences with loose tolerances.
