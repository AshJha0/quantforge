# Stage K perf lane: Java implied_vol bench gate (stop note, 2026-11-21)

Branch `k-v1-perf` from `k-v1` 4c3b25fb. No PR, no merge. No gate, baseline, threshold or bench workflow was touched.

## The problem

The CI bench gate (`bench.yml`, job `bench (java)`, `tools/bench_gate.py`, 1.5x of the stored baseline) failed on
PR #65: Java `implied_vol` at 1,648 to 1,749 ns/op against a baseline of 991 (read: bench.yml runs 44943881062 and
44946623051).

## What the bench times

`java25/src/jmh/java/org/quantforge/bench/MicroBench.java`, `implied_vol()`: `Black.implied(option, price)` for a
Black-76 call, forward 100, strike 105, one year, price at vol 0.2. That reaches `Black.solve`, lognormal branch
(read).

## Cause of each step

Step 1 (about 900 to about 1,263 ns, at 5e4facc9). Commit 511f0cdb (KR-341) is the only change on the timed path
in 1d5e5890..5e4facc9 (read: `git diff --stat` shows `Black.java` and `Sabr.java` only; Sabr is not on the path).
It did two things:

1. Added `identified()`, which after the loop evaluated V(v) again, vega again and two more N() terms, all values
   the solver had in hand. With the closing `priced` check that is one redundant price evaluation plus about two
   more N() calls and a density (read).
2. Changed the Newton step to Newton on ln V. From the start v = 0.5 this overshoots to v = 4.3e-4, takes a
   bisection step and needs 11 iterations where plain Newton needed 7 on this input (measured: a standalone
   replica of both loops on the bench input). This is the bug fix itself and is inherent.

Step 2 (about 1,263 to 1,648 to 1,749 ns, at 22e23ecd and 4c3b25fb). No change on the timed path: in
1e16a034..4c3b25fb the Java main tree changed only `cli/OpsXva.java` and `paper/Paper.java`, and the JMH source and
`pom.xml` did not change (read: `git diff --stat`). This step is runner variance, not code (inferred). The other Java
benches rose about 1.15x in the same runs (from the brief).

## What was changed

- `Black.solveLognormal` (lognormal branch of `solve` when t > 0): the same floating-point expressions in the same
  order, each evaluated once. ln(F/K) and sqrt(T) are hoisted, vega reuses n(d1) from the price, and the closing
  `priced` / `collapsed` checks and the KR-341 identification check share one price evaluation and its N() terms.
  The normal model and t = 0 keep the old loop.
- `Normal.cdf(x, n)`: cdf(x) with the density passed in. Bitwise the same as `cdf(x)` because `pdf` takes |x| first;
  used only when |phi| = 1.
- `BlackSolveFusedTest`: the pre-change solver kept verbatim as a reference; 4000 seeded random cases (phi 1, -1,
  0.5; refusal cases included) must give the same double bits or the same error code and message. Also a bitwise
  check of `cdf(x, pdf(x))` against `cdf(x)`, tails and NaN included.

## Measurements (local laptop, not the acceptance machine)

JMH, `-f 2 -wi 3 -i 5 -w 1 -r 1`, avgt, implied_vol only. Compare ratios, not absolute numbers.

| build | ns/op | ratio to 4c3b25fb |
|---|---|---|
| Black.java at 1d5e5890 (before KR-341) | 2,150 | 0.54 |
| 4c3b25fb (before this lane) | 4,068 and 3,935 | 1.00 |
| first change only (one closing evaluation) | 3,190 | 0.80 |
| both changes (this branch) | 2,837 | 0.71 |

Projection to CI (inferred): 0.71 x 1,749 = about 1,240 ns, 1.25x the baseline of 991, under the 1.5x gate but not
far under. The remaining gap to the pre-KR-341 time is the extra Newton iterations of the KR-341 ruling (11 against
7 on this input), which cannot be removed without changing the iterates and so possibly the output.

## Verification

- `cd java25 && mvn -B -Pcoverage verify`: BUILD SUCCESS, 1100 tests, 0 failures, 1 skipped, coverage gate passed
  (measured, local laptop).
- `mvn -B -DskipTests package` then `python conformance/runner/runner.py --impl java`: 16,652 cases, 16,652 pass,
  0 fail, 0 not implemented (measured, local laptop).
- CI: `gh workflow run bench.yml --ref k-v1-perf` dispatched; result in the section below if it finished before the
  stop.

## CI bench run

CI_RESULT

## For the coordinator

- The KR-341 iteration count is an inherent cost (about 1.3x on this input on the laptop after this change). If the
  gate is tight on a noisy runner, that is the cost to record, not something to tune away.
- Step 2 has no code cause on the timed path.
