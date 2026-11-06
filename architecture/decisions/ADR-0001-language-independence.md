# ADR: Independent language implementations

## Status
Accepted

## Decision
Python, C++26, Java 25 and Rust independently implement quantitative domain logic. They share specifications, schemas, fixtures and conformance rules, not runtime calculation code.

## Rationale
This avoids hidden runtime coupling and makes language comparisons meaningful.

## Consequences
Duplicate implementation effort is intentional. Mathematical parity must be established through common test vectors and independently verified expected values.
