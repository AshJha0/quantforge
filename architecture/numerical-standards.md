# Numerical standards

- Use explicit units and currency types at public boundaries.
- Avoid implicit conversions between decimal rates, percentages and basis points.
- Document floating-point assumptions and conditioning.
- Prefer stable formulations over algebraically compact but unstable expressions.
- Check finite inputs and outputs; define behaviour for NaN and infinity.
- Root finders must report convergence, iteration count, residual and termination reason.
- Optimisers must report objective, gradient/step diagnostics, constraints and termination status.
- Interpolation and extrapolation policies must be explicit.
- Use absolute and relative error together: `|a-b| <= abs_tol + rel_tol * max(|a|, |b|)`.
- Tolerances are domain- and algorithm-specific; do not use one global tolerance.
- Deterministic tests must control seeds, ordering and time.
- Parallel reductions may change floating-point summation order; document reproducibility level.
- Do not silently clamp invalid inputs unless the specification explicitly requires it.
