# ADR: Immutable input snapshots and provenance

## Status
Accepted

## Decision
Calculations should be replayable from versioned input snapshots and explicit model/configuration versions.

## Consequences
Input data lineage and configuration hashes are first-class result metadata. Sensitive or licensed data must not be committed to public fixtures.
