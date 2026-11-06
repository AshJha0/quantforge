# ADR: Monorepo

## Status
Accepted

## Decision
Use one repository with language-specific implementation roots and shared specifications, data contracts, fixtures and tooling.

## Rationale
Cross-language changes and conformance are easier to review atomically.

## Consequences
CI should support path filtering and per-domain ownership. Keep package boundaries strict.
