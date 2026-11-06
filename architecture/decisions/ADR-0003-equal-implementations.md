# ADR: Four equal implementations

## Status
Accepted. Replaces the starter's Python model decision.

## Decision
Java, C++, Python and Rust are equal. Each is written from the specification in a separate clean-room session. They share no code, FFI or generated maths, and no language is the reference. Proven numerical libraries are allowed for linear algebra and general solvers; financial logic is not shared.

## Consequences
Agreement between languages never proves correctness. Expected values come from `oracle/`; see ADR-0009.
