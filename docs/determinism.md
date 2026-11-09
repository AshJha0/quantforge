# Determinism: what is bit-exact, what is within tolerance, and why

The plain idea: QuantForge runs the same maths in four languages on three operating systems. Some answers come out identical to the last bit everywhere. Others differ in the last few digits, and the project says in advance by how much. This page says which is which and why, so a difference you see is either expected and bounded, or a bug.

Formally, every conformance case names one tolerance class in `conformance/tolerances/policy.yaml`. There is no global default (ADR-0007). Two classes are exact; the rest compare with `|a - e| <= absolute + relative * max(|a|, |e|)`. `conformance/tolerances/money.md` restates each class as money on a 10m notional.

## Bit-exact

These must agree to the bit, on every language and platform. A difference is a bug.

| What | Why it can be exact | Where |
|---|---|---|
| Dates, calendars, schedules, enums, integers, booleans, error codes | No rounding at all | class `date_and_convention` |
| Random integers (SplitMix64 seeding, xoshiro256**) and stream jumps | Wrapping 64-bit integer arithmetic, defined bit by bit | `specifications/01-core/rng.md`, class `bit_exact` |
| Uniforms `u = ((x >> 12) + 0.5) * 2^-52` | 52 bits plus one half is exact in binary64, and the scaling is by a power of two | `rng.md`, "Uniforms" |
| Sobol points | Integer direction numbers, XOR, then the same exact scaling | `specifications/01-core/sobol.md` |
| Snapshot hash | SHA-256 over one canonical byte form; numbers written as their binary64 bits in hex | `specifications/01-core/snapshot-hash.md` |
| A `batch` result against `run` on the same line | Same code path, no state between lines | `specifications/cli-contract.md`, rule BT4 |

## Within tolerance

Everything else that involves real arithmetic is compared within its class. The reasons, from the most common:

1. **Elementary functions are not correctly rounded.** `exp`, `log`, `pow` and the trigonometric functions come from each language's maths library. IEEE 754-2019 (clause 9.2) recommends correctly rounded versions but does not require them, so glibc, the Microsoft C runtime, Apple's libm, the JVM's `StrictMath` and Rust's platform libm may differ by an ulp. Normals from Wichura's AS 241 use `log` and `sqrt`, which is why `rng.md` says they "agree to a few ulps, not to the bit".
2. **Different but proven algorithms.** The specs fix what is computed and to what accuracy, not always how. Calibrations may use different solvers, so class `calibration` judges the repricing error, not the fitted parameters. Root finders stop on their own tolerance (class `root_finding`).
3. **Summation order.** Floating-point addition is not associative (Goldberg 1991). Where order matters, the spec fixes it: Monte Carlo sums run in path order, and a parallel build must reduce in that same order (`specifications/01-core/monte-carlo.md`). The Python build routes such sums through `ordered_sum` for the same reason.
4. **Fused multiply-add.** A compiler that fuses `a * b + c` rounds once instead of twice. The C++ build compiles with `-ffp-contract=off` and never `-ffast-math` (`cpp26/CMakeLists.txt`). Java has been strict IEEE by default since JDK 17 (JEP 306). Rust and Python do not contract by default.

So a curve bootstrapped in four languages agrees to about 15 significant digits, not to the last bit (LEARN, "Curve bootstrap"), and that is inside its class. [Tutorial 1](getting-started/tutorial-1-swap.md) prints 12 digits of a discount factor and 4 decimals of PV and DV01, which all four builds reproduce exactly at that precision.

## Monte Carlo

A Monte Carlo price is checked two ways (`policy.yaml`, class `monte_carlo`): against the true value within `z` reported standard errors, and, because the draws are fixed by `rng.md`, against the oracle's own run of the same draws within class `common_rng` (1e-9). Integer draws are bit-exact; the price is not, because the normals and the payoff use `exp` and `log` (reason 1).

**Planned (stage F, item E9).** A fixed-seed Monte Carlo hash golden: the SHA-256 of a fixed-seed path set's integer draws and uniforms, which must be identical on Linux, Windows and macOS. The spec lane supplies the golden; this section will name its case and the cross-platform run that checked it. Cross-platform conformance on pull requests that touch core maths is also planned. Today `cross-platform.yml` runs weekly and by hand.

## When you see a difference

- An exact class differs: a bug, in the build or in the spec. Report it with the case id.
- A tolerance class differs beyond its limit: a bug, or a tolerance that was set too tight. The class comment in `policy.yaml` gives the reasoning to check against; do not widen it without a reason that ADR-0007 would accept.
- Two runs of one build on one machine differ: a bug: `architecture/numerical-standards.md` requires deterministic code to control seeds, ordering and time.

## Sources

- IEEE 754-2019, *Standard for Floating-Point Arithmetic*, clause 9.2 (recommended correctly rounded operations).
- Goldberg, D., "What every computer scientist should know about floating-point arithmetic", *ACM Computing Surveys* 23(1), 1991.
- OpenJDK JEP 306, "Restore always-strict floating-point semantics", JDK 17.
- Wichura, M. J., "Algorithm AS 241: the percentage points of the normal distribution", *Applied Statistics* 37(3), 1988.
- Project: ADR-0007, `conformance/tolerances/policy.yaml`, `specifications/01-core/rng.md`, `sobol.md`, `snapshot-hash.md`, `monte-carlo.md`.
