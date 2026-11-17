# Question bank 12: Four-language engineering and verification

This set is about how QuantForge knows its numbers are right, and how far that knowledge goes. It is for a newcomer who wants to understand why four implementations and an oracle are worth the trouble, and for an engineer who wants the exact rules: tolerance classes, error codes, the CLI contract, rulings, mutation testing, fuzzing and determinism. Answers give the plain idea, then the rule as the project states it, then a worked example where numbers help. Counts quoted here are read from repository files (evidence `spec` or `design`) and, with the computed examples, are re-checked by `docs/question-bank/verify/v12_engineering_verification.py`. Levels: foundation, practitioner, advanced.

Main sources: [ARCHITECTURE](../../ARCHITECTURE.md), [conformance](../../conformance/README.md), [oracle](../../oracle/README.md), the [CLI contract](../../specifications/cli-contract.md), [determinism](../determinism.md) and [golden case figures](../case-figures.md).

## Four implementations and an oracle

### Q12.1 Why does QuantForge have four equal implementations, and why is none of them the reference?

*Level: foundation. Evidence: design. Source: [ARCHITECTURE](../../ARCHITECTURE.md), [conformance](../../conformance/README.md)*

Writing the same maths independently in four languages (Java 25, C++26, Python and Rust) catches mistakes that one implementation would hide: an ambiguity in a spec shows up as two builds disagreeing. If one build were the reference, its bugs would become the definition of correct.

The rules in ARCHITECTURE: no language is a reference, and the oracle is the source of golden results; no shared code, FFI or generated maths between implementations; implementations depend on the specs only, never on each other or on the oracle; the only interface that counts is the CLI, case JSON in and result JSON out.

The cost is four builds of everything. The benefit is that each golden case is checked by four independent readings of the spec, through a runner that knows no finance. The pitfall is to think this proves the spec right: it does not (Q12.3).

### Q12.2 What is the oracle, and what may it not do?

*Level: foundation. Evidence: design. Source: [oracle](../../oracle/README.md), [ARCHITECTURE](../../ARCHITECTURE.md)*

The oracle is the code in `oracle/` that writes the expected results, the golden cases, from outside sources (QuantLib, OpenGamma Strata, mpmath, NumPy, SciPy, ORE and others) and hand cases. It is used by tests only.

Two rules hold it apart: no implementation may import or call anything in `oracle/`, and golden values never come from the four implementations. Generators stop with an error when their sources disagree, apart from differences recorded in the specs, and each case's `verified_by` lists the sources that agreed with it. Many generators work at 50 digits or in exact rational arithmetic.

The oracle runs on its own pinned Python (3.12), separate from the Python implementation. Regenerating everything takes about three minutes with `run_all.py`. Because expected values come only from here, a build can never pass by agreeing with itself.

### Q12.3 Four builds agree with each other on every case. Why is that not proof that they are right?

*Level: practitioner. Evidence: design. Source: [conformance](../../conformance/README.md), [oracle](../../oracle/README.md), [ARCHITECTURE](../../ARCHITECTURE.md)*

Because all four were written from the same spec, and a misreading in the spec is shared by all of them. The conformance README says it plainly: agreement between languages proves nothing alone.

Passing means a build matches the oracle within tolerance. That is stronger, but it has the same gap where a case has only hand or replay sources: one author wrote both the spec and the check, so they can share a misreading. ARCHITECTURE calls the specification "a shared-error risk" and gives the two defences: outside libraries wherever a licence allows, and a human review that closes the project. Until that review, validation is self-assessment, and no model is marked Validated in the model inventory.

The practical reading of a green run: the four builds implement the spec as the oracle understands it. Whether the spec is the right finance is a separate question, answered best by the outside-library share (Q12.27).

### Q12.4 What is in a golden case record?

*Level: foundation. Evidence: spec. Source: [conformance](../../conformance/README.md), [CLI contract](../../specifications/cli-contract.md)*

Each golden file has `suite`, `spec`, `spec_version`, `generator` and `reviewer`. Each case has a `case_id`, an `operation`, the `inputs`, the `expected` status with its outputs or error code, a `tolerance_class`, `verified_by` (the sources that agreed), `tags` and optional `extra_checks`.

The runner strips `expected` before sending the case, so an implementation sees only what a user would send: `schema_version`, `case_id`, `operation` and `inputs`. Golden cases live in `datasets/golden/**/*.json` and are written only by `oracle/`.

A non-money output can carry its own class through `output_classes` (ruling E-B14), so a fitted parameter and a price in the same case are each judged on a suitable scale. Missing outputs are never silently ignored: extra keys and missing keys are both failures.

### Q12.5 How does the runner decide that a number matches, and what does "no global default" mean?

*Level: practitioner. Evidence: computed; spec; design. Source: [conformance](../../conformance/README.md), [determinism](../determinism.md)*

Each case names a tolerance class, and the class sets an absolute and a relative limit. A scalar passes when

`abs(actual - expected) <= absolute + relative * max(abs(actual), abs(expected))`.

Exact classes allow no difference. There is no global default (ADR-0007): a case without a class cannot be judged, so every tolerance is a decision someone wrote down with a reason in `conformance/tolerances/policy.yaml`.

**Worked example.** Class `root_finding` has absolute `1e-10` and relative `1e-10`. With expected 1 and actual `1 + 1.5e-10`, the limit is 2.00000000015e-10 and the difference 1.5e-10, so the case passes. An actual of `1 + 2.5e-10` would fail.

The policy file defines 19 classes, from `bit_exact` and `date_and_convention` (exact) to `monte_carlo`. `conformance/tolerances/money.md` restates each class as money on a 10m notional, which is how to judge whether a tolerance is too loose.

## Kinds of case

### Q12.6 How many golden cases are there, and what are the three classes?

*Level: foundation. Evidence: spec. Source: [golden case figures](../case-figures.md)*

The golden set has three kinds of case. Value-checked cases (`ok`) compare numbers within a stated tolerance. Error cases check only the error code. Invariance cases come in pairs: a `same_as` case checks that a build answers two related inputs the same way, and its `any` base case passes on any finite answer.

From `docs/case-figures.md` (generated by `tools/case_figures.py`, checked in `repo-gates`): 7,653 value-checked cases, 5,347 error cases and 2,514 invariance cases (1,257 pairs), 15,514 cases in all, across 13 suite directories. At contract 1.14.0 every build passed all 15,315 then in the set (2026-11-14); stage J wave 3 (88), the curves lane (51) the hedge rank-cut fix (4) and the hedge sign-state and selection fixes (5), the minimum-variance constant-series fix (3) and the E1 completion `e1_j` (48) added 199 at contract 1.15.0. On the merged stage J tree every build passed all 15,514 (2026-11-15).

The value-checked count leads the headline on purpose (Q12.7).

### Q12.7 Why does the project lead with the value-checked count rather than the total?

*Level: practitioner. Evidence: spec; design. Source: [golden case figures](../case-figures.md), [Outside shares](../../oracle/OUTSIDE_SHARES.md)*

Because a build that answered every case with an error code would pass every error case and no value-checked case. Error cases test that bad inputs are refused with the right code, which matters, but they say nothing about whether the numbers are right.

The split is uneven by stage: `stage_f` has 472 value-checked cases against 3,462 error cases and 1,063 invariance pairs, because it added the finite-input rules, which are tested mostly by error cases. A total of 15,514 would overstate the numeric evidence.

The same reasoning moved the outside-check floor (R6-13, owner decision D6): the 60% floor is measured over value-checked cases only, with error and invariance cases a separate evidence class outside the denominator. The old all-case share is shown beside the new one so the change is visible.

### Q12.8 What does an invariance case test that a value-checked case cannot?

*Level: practitioner. Evidence: spec. Source: [golden case figures](../case-figures.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

A property that holds without a known answer. Some outputs have no outside reference value, but there is still something that must be true: two inputs that mean the same thing must give the same answer. An invariance pair encodes that: the `any` base case passes on any finite answer, and the `same_as` case passes only if the build's answer equals its answer to the base.

All of them are in `stage_f` (1,063 pairs) and `stage_g_e1` (194 pairs), 1,257 pairs in all, written by `oracle/python/gen_stage_f_e1.py` for plan item E1. They pin the negative-zero rule F-3: for each operation, a Real input set to `+0.0` is the `any` anchor and the same input set to `-0.0` must give the `same_as` answer. The same generator writes NaN and infinity variants of each input, which are error cases expecting `E_DOMAIN`.

The limit is stated by construction: an invariance pair can be passed by a build that is consistently wrong. It catches inconsistency, not error, so it is counted apart from the value-checked cases and never used to claim accuracy.

### Q12.9 How many error codes does the CLI contract define, and in what order are checks made?

*Level: foundation. Evidence: spec. Source: [CLI contract](../../specifications/cli-contract.md)*

The contract's error table lists 20 codes, the same in all four languages, from `E_PARSE` to `E_INFEASIBLE` (added in contract 1.11.0, ruling I-1). A case that expects an error passes only on the exact code. `error.message` is free text and not compared; `error.field` is optional and not compared.

Order of checks: `E_PARSE`, then `E_SCHEMA`, then `E_LIMIT` (with the text-size and depth exceptions of `01-core/limits.md`), then the rule checks in the order the operation's spec lists them. When one case breaks two rules, the first listed wins.

The order is what makes error cases comparable across languages: without it, a case breaking two rules could fairly return either code. Each operation's spec lists its checks in order for the same reason. `E_UNSUPPORTED_OPERATION` is counted as "not implemented", never as a pass.

### Q12.10 What is the difference between `E_INPUT`, `E_DOMAIN` and `E_NON_FINITE`?

*Level: practitioner. Evidence: spec. Source: [CLI contract](../../specifications/cli-contract.md), [R6 rulings](../../specifications/r6-rulings.md)*

`E_INPUT` is a well-formed input that breaks a rule of the operation: knots not strictly increasing, an array too short, two lengths that should match and do not. `E_DOMAIN` is a value outside the mathematical domain: the log of a negative number, a negative volatility, a weight at or below zero. `E_NON_FINITE` is a result that would be NaN or infinite, including an intermediate that overflows from finite inputs.

Ruling R6-8.1 is firm on the last: an overflow from finite inputs is never a crash and never `E_DOMAIN`. A non-finite input is different: since stage F a Real input may be the string `"NaN"`, `"Infinity"` or `"-Infinity"`, and every operation refuses a non-finite input first (rulings F-1 to F-4, the finite rule F-2, as `E_DOMAIN`).

The distinction matters to a caller: `E_INPUT` means fix the shape of the request, `E_DOMAIN` means the value is impossible, `E_NON_FINITE` means the request was valid but the answer does not exist in binary64.

## Rulings

### Q12.11 What is a ruling, and how are rulings recorded?

*Level: foundation. Evidence: spec; design. Source: [Stage I rulings](../../specifications/stage-i-rulings.md), [R6 rulings](../../specifications/r6-rulings.md), [specifications](../../specifications/README.md)*

A ruling is a written decision on a question the spec left open: a convention, a tie rule, a tolerance, an error code, an order of operations. Writing it down means four builds can implement the same answer, and a reader can see why the spec says what it says.

Rulings live in files named `*rulings*.md` under `specifications/`; there are 16 at that level (the stage files from B to J, some split into parts, stage J with wave 3 and curves lane files, and the R1, R2 and R6 rounds), plus `01-core/rulings.md`. Each spec page lists its questions in a "Spec questions and rulings" table and cites rulings by number, for example I-7 for integer ties or J-14 for the PSR domain. The rulings file is normative for its stage, and R6's file says it is append-only.

A new ruling never silently rewrites an old one: it amends it by number, and the spec page gains an "Amendments after the builds" section saying what changed.

### Q12.12 Why do some rulings arrive after the builds, and what does a typical amendment look like?

*Level: advanced. Evidence: spec; design. Source: [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Stage I rulings](../../specifications/stage-i-rulings.md)*

Because four independent builds find ambiguities that one author reading his own spec does not. When two builds disagree on a case, either one has a bug or the spec allowed both answers; in the second case a ruling closes the gap.

Example: ruling I-31 defined `E_DOMAIN` for the effectiveness statistics by exact tests (`sum(x) = 0`, a zero variance). In floating point, a constant-spot backtest gives sums near but not exactly zero, so builds could disagree. Ruling I-43 replaced the exact tests with relative ones (`|sum(x)| <= 1e-12 sum|x|`, `var(x) <= 1e-20 var(y)`), and case `hedgebt_i-0016` pins that a constant-spot backtest is `E_DOMAIN` in every build.

Other examples in the hedge specs: I-44 (a tolerance on a negative hedged variance), I-46 and R6-11.3 (the feasibility tolerance), R6-6.2 (scaling before singularity tests). Each amendment is pinned by a golden case, so the fix cannot drift.

## The conformance harness

### Q12.13 What does the conformance runner do, and why does it know no finance?

*Level: foundation. Evidence: design. Source: [conformance](../../conformance/README.md), [ARCHITECTURE](../../ARCHITECTURE.md)*

The runner sends each golden case, with the expected values removed, to a language's `quantforge` CLI and compares what comes back with the expected values under the case's tolerance class. It uses only the Python standard library and holds no financial logic.

Keeping finance out of the runner means it cannot be a fifth implementation that quietly fixes up answers, and it cannot share a misreading with the builds. It only knows JSON, tolerance classes and error codes.

Each run writes `conformance/reports/NAME.json` (git-ignored) and prints pass, fail and not-implemented counts per suite. A case an implementation does not support is reported as not implemented, and the run does not pass. Commands per language are in `conformance/runner/implementations.json`, e.g. `python conformance/runner/runner.py --impl rust`.

### Q12.14 How is the runner itself tested?

*Level: practitioner. Evidence: design. Source: [conformance](../../conformance/README.md)*

A runner that always says "pass" would make every build look perfect, so the runner has its own tests. `python conformance/runner/test_runner.py` runs it against `stub_cli.py`, a fake CLI that replays golden values and injects faults: wrong numbers, wrong error codes, missing or extra outputs, crashes.

The test checks that each fault is reported as a failure of the right kind. Without it, a bug in the comparison (for example, treating a missing key as a pass) would hide real failures in all four builds at once.

Batch-mode framing is checked separately by `conformance/runner/batch_check.py` against fixtures in `datasets/batch/streams.json`, which sit outside `datasets/golden/` because they test the stream, not an operation. The same idea, testing the test, recurs in the A5 harness self-test and in the mutation tests (Q12.15).

## Mutation testing and fuzzing

### Q12.15 What does mutation testing measure, and what scores has QuantForge recorded?

*Level: practitioner. Evidence: computed; spec. Source: [Python mutation runner](../../conformance/mutation/README_python.md), [Test infrastructure](../developer-guides/test-infrastructure.md)*

Mutation testing changes the code on purpose (swap `+` for `-`, `<` for `<=`, drop a minus sign) and checks that the tests notice. A mutant that survives points at code the tests do not really check. The score is killed over killed plus survived, with unviable mutants left out.

Each language uses its own tool: PIT for Java (unit tests), `cpp_mutants.py` for C++ (golden cases as the test), mutmut and cargo-mutants for Python and Rust, with `golden_mutants.py` scoring a sample against the golden cases too. On Windows, Python uses `python_sampled_mutants.py`, a seeded module-scoped sampler.

**Worked example.** The Python credit profile, seed 20261111, 90 sampled mutants: 52 killed on the first run (57.8%), 77 killed after adding `test_credit_kills.py` (85.6%). The stage E pooled CI score was 84.3% (2,360 killed, 439 survived). The stage D target is 80%.

A sampled score can be several points out; the guides say so next to each figure.

### Q12.16 Why are some surviving mutants deliberately left alive?

*Level: advanced. Evidence: spec; design. Source: [Python mutation runner](../../conformance/mutation/README_python.md), [CLI contract](../../specifications/cli-contract.md), [Test infrastructure](../developer-guides/test-infrastructure.md)*

Because killing them would need a test that is wrong to have. Two kinds are left alive on purpose, each listed with its reason.

Message-text mutants: the CLI contract fixes the error `code` and `field`, not the message, which is free text and not compared. A test pinning the message would block every later rewording, so the tests pin codes and fields instead.

Equivalent mutants: changing an iteration cap or a bracket growth factor gives the same answer on every input the spec allows, because the solve converges long before the cap and any bracket containing the root gives the same root to the solver tolerance. No test can kill a mutant that does not change behaviour.

Of the 13 survivors of the credit rerun (Q12.15), 8 were caps or bracket factors, 4 changed only message text or an unreachable branch's code string, and 1 was a real gap, closed by a new test afterwards. Survivors are classified as equivalent by the author, with a second reviewer's sign-off scheduled.

### Q12.17 How do golden cases double as mutation tests for the specs themselves?

*Level: advanced. Evidence: spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [oracle](../../oracle/README.md)*

Each generator also checks that its golden cases would catch plausible wrong implementations. The spec pages list the mutants caught; for wave 1 of the hedge solvers: bounds ignored (the free solution clipped instead of re-solved), weights dropped, ridge ignored, naive rounding for integer lots, the population divisor for sample variances, the `e^{-qT}` factor dropped from delta, and round half to even for beta futures.

This is a check on the test data rather than the code: if a golden set cannot tell the right formula from a common wrong one, it is too weak, whatever the builds score. `oracle/MUTANTS.md` and `MUTANTS_C.md` record the same check for the tolerances of earlier stages.

The design point: a passing case is only evidence if a wrong answer would fail it. Listing the caught mutants makes that claim checkable, case by case.

### Q12.18 What does the fuzzer check, and how is a finding reproduced?

*Level: foundation. Evidence: design. Source: [conformance](../../conformance/README.md)*

`conformance/fuzz/fuzz_cli.py --impl NAME --seconds 60` damages golden inputs and raw bytes and sends them through the same CLI each language ships. It does not know the right answers; it checks that the CLI behaves: a clean exit, one result per input, the right result shape, and a known error code.

A failing batch is replayed one input at a time, and each finding is written with its input to `conformance/reports/fuzz/NAME.jsonl`. Rerun with the same `--seed` to get the same inputs. Recorded runs: seed 13 for 60 seconds per language at stage C and seed 17 at stage D found nothing.

Fuzzing finds crashes, hangs and wrong error handling, which goldens rarely reach because goldens are written by someone thinking about valid inputs. The R1 acceptance line is Python fuzzing at 50,000 or more inputs a minute through batch mode.

## Determinism

### Q12.19 Which results must agree to the last bit in every language, and why can they?

*Level: foundation. Evidence: spec. Source: [determinism](../determinism.md), [Snapshot hash](../../specifications/01-core/snapshot-hash.md)*

Those with no rounding, or with rounding defined bit by bit: dates, calendars, schedules, enums, integers, booleans and error codes; random integers (SplitMix64 seeding, xoshiro256**) and stream jumps, which are wrapping 64-bit integer arithmetic; uniforms `u = ((x >> 12) + 0.5) * 2^-52`, exact in binary64 because the scaling is a power of two; Sobol points (integer direction numbers and XOR, then the same scaling); the snapshot hash; and a `batch` result against `run` on the same line.

A difference in any of these is a bug, in the build or in the spec. The classes are `date_and_convention` and `bit_exact`.

Normals are not on the list: they use `log` and `sqrt` (Wichura's AS 241), so they "agree to a few ulps, not to the bit". A Monte Carlo price is therefore checked within class `common_rng` (`1e-9`) against the oracle's run of the same draws, not to the bit.

### Q12.20 Why do most real-valued results differ in the last few digits across languages?

*Level: practitioner. Evidence: spec; literature. Source: [determinism](../determinism.md)*

`docs/determinism.md` gives four reasons, most common first.

1. Elementary functions are not correctly rounded. IEEE 754-2019 clause 9.2 recommends correctly rounded `exp`, `log` and `pow` but does not require them, so glibc, the Microsoft runtime, Apple's libm, the JVM's `StrictMath` and Rust's libm can differ by an ulp.
2. Different but proven algorithms. Specs fix what is computed and to what accuracy, not always how; calibrations are judged on repricing error (class `calibration`), root finders on their tolerance (`root_finding`).
3. Summation order. Floating-point addition is not associative [Goldberg 1991]; where order matters the spec fixes it, e.g. Monte Carlo sums in path order.
4. Fused multiply-add rounds once instead of twice.

So a curve bootstrapped in four languages agrees to about 15 significant digits, inside its class. A difference beyond the class is a bug or a tolerance set too tight; the class comment gives the reasoning to check against.

### Q12.21 What does QuantForge do about fused multiply-add and summation order?

*Level: advanced. Evidence: spec; design. Source: [determinism](../determinism.md), [CLI contract](../../specifications/cli-contract.md)*

Both can change the last bits of a result without any bug in the maths, so the contract controls them where it can.

FMA: the C++ conformance builds compile with `-ffp-contract=off` and never `-ffast-math` (`cpp26/CMakeLists.txt`). Java has been strict IEEE by default since JDK 17 (JEP 306). Rust and Python do not contract by default.

Summation: the contract's numeric rules say sums run in array order unless a spec says otherwise, including any parallel sum. A parallel Monte Carlo build must reduce in path order, and the Python build routes such sums through `ordered_sum`. Baum-Welch sums run over ascending indices for the same reason.

Run-to-run: two runs of one build on one machine must give identical output. A difference there is always a bug, because `architecture/numerical-standards.md` requires deterministic code to control seeds, ordering and time, and no CLI command reads the clock, the environment or any file for its numbers.

### Q12.22 What is the fixed-seed Monte Carlo hash, and what would it catch?

*Level: practitioner. Evidence: spec. Source: [determinism](../determinism.md), [RNG](../../specifications/01-core/rng.md)*

A fingerprint of the random number stream. `datasets/golden/core/mc_hash.json` holds 4,096 xoshiro256** integer draws and the matching uniforms for seed 20261112 on streams 0, 1 and 7, every case `bit_exact`. `oracle/MC_HASH_E9.json` records the SHA-256 of each case (integers as decimal strings, uniforms as `float.hex`, one per line).

`tools/check_mc_hash.py` recomputes the hashes in the `repo-gates` workflow and shows a one-ulp change being caught. Because `cross-platform.yml` runs every golden on Linux, Windows and macOS, a green run means the hashes are identical on all three.

It would catch a change to the generator, the seeding, the jump, or the uniform conversion on any platform, including one that moves a single draw by one ulp. The page is honest about its status: until the first green cross-platform run on the R6 branch, it is "built but not yet proven".

## Snapshots, JSON and the CLI

### Q12.23 How is a snapshot hash computed so that four languages get the same hash?

*Level: foundation. Evidence: computed; spec. Source: [Snapshot hash](../../specifications/01-core/snapshot-hash.md)*

Plain JSON text cannot be hashed across languages, because each formats numbers differently. So the hash is taken over a canonical byte form with one spelling per value: no white space; numbers as `#` and the 16 hex digits of their binary64 bits; strings with control characters escaped as lower-case `\u00xx`; object keys sorted by their UTF-8 bytes. Then `snapshot_id = "sha256:" + hex SHA-256` of those bytes, with a top-level `snapshot_id` key removed first.

**Worked example.** The spec's document `{"b":1,"a":[true,null,"x\n"]}` has canonical form `{"a":[true,null,"x\u000a"],"b":#3ff0000000000000}` and `snapshot_id` `sha256:e2a9827c85ed6943e16cfd35b1d983b906af5257d9cccc10bb1a251300147cce`.

The canonical form is single-source (defined only by the oracle's `canon`), with the SHA-256 checked against the NIST `abc` vector and the system `sha256sum`. Both outputs are compared exactly.

### Q12.24 Do `1`, `1.0` and `1e0` hash the same in a snapshot, and what about `-0.0`?

*Level: practitioner. Evidence: computed; spec. Source: [Snapshot hash](../../specifications/01-core/snapshot-hash.md)*

Yes. All three parse to the same binary64 value, and the canonical form writes the bits, not the text, so each becomes `#3ff0000000000000`. Negative zero is written as positive zero, `#0000000000000000`.

**Worked example.** `{"x":1}`, `{"x":1.0}` and `{"x":1e0}` all give `sha256:fe071958f961c5458dbaffc776c4f70259cce2bd6ecaf9349f138ec606dc5d99`. `{"x":-0.0}` gives the canonical form `{"x":#0000000000000000}`. `{"x":0.1}` gives `{"x":#3fb999999999999a}`, the nearest double to 0.1.

The consequence: every number in a snapshot is a binary64. An integer that needs more than 53 bits, such as a large quantity, must be stored as a string, or two different quantities could hash the same. Strings are not Unicode-normalised, so two visually identical strings in different normal forms hash differently.

### Q12.25 What does strict JSON mean in the QuantForge contract?

*Level: practitioner. Evidence: spec. Source: [CLI contract](../../specifications/cli-contract.md), [Snapshot hash](../../specifications/01-core/snapshot-hash.md)*

Many JSON readers are lenient in ways that would let the four builds read the same text differently. The contract removes the leniency.

A duplicate key at any depth is `E_PARSE`. NaN and infinity never appear in JSON: a number that overflows binary64, such as `1e400`, is `E_SCHEMA`, and a non-finite output becomes `E_NON_FINITE`. Since stage F a non-finite Real input can be sent only as the strings `"NaN"`, `"Infinity"` or `"-Infinity"`, and is refused first. A Real is parsed to the nearest binary64 and written so it reads back to the same binary64 (shortest round-trip form preferred). 64-bit unsigned values are decimal strings, because JSON readers lose bits above `2^53`. Missing is `null`, never zero and never omitted.

Output is UTF-8 with no byte order mark. Negative zero may be written as `-0.0` or `0.0`, and the runner treats them as equal. Nesting beyond 64 levels is `E_LIMIT`.

### Q12.26 What commands and exit codes does every `quantforge` CLI support?

*Level: foundation. Evidence: spec. Source: [CLI contract](../../specifications/cli-contract.md)*

Each implementation builds one executable called `quantforge`. Commands: `run` (one case on stdin, one result on stdout), `batch` and its alias `--batch` (JSON Lines in, one result per line out, in order), `version` (language, implementation version, `contract_version` 1.15.0, toolchain) and `operations` (the sorted operation names the build supports).

Exit codes: 0 for an `ok` result from `run`, or a normally ended `batch`, `version` or `operations`; 2 for an `error` result from `run`; 64 for an unknown command or bad arguments, with empty stdout; 70 for an internal fault. Any other exit code, or a timeout, is a crash.

A malformed case is still a result: `run` writes status `error` with `E_PARSE` or `E_SCHEMA` and exits 2, using `case_id: "unknown"` if none can be read. Anything for humans goes to stderr, which the runner ignores.

### Q12.27 What does batch mode guarantee, line by line?

*Level: practitioner. Evidence: computed; spec. Source: [CLI contract](../../specifications/cli-contract.md)*

Batch mode exists because a JVM start per case would dominate run time. Its rules BT1 to BT8 make it as trustworthy as `run`.

Every input line gives exactly one result line, in order, even an empty, non-UTF-8 or non-JSON line, which is `E_PARSE` with `case_id: "unknown"` (BT3). A CR before the LF is removed, so CRLF input works (BT1); output lines end in a single LF, never CRLF, and are flushed before the next input line is read (BT6). The stream exits 0 when stdin ends, whatever each case's status (BT8).

**Worked example.** BT5 caps a line at 16,777,216 bytes, which is `2^24`. A longer line is `E_LIMIT` decided on its length without parsing, and the stream continues with the next line.

The optional `--timings` flag adds `diagnostics.elapsed_ns` and changes nothing else; the runner never compares `diagnostics`.

### Q12.28 Why must a batch result equal the `run` result bit for bit, and what does "no state" rule out?

*Level: advanced. Evidence: spec; design. Source: [CLI contract](../../specifications/cli-contract.md), [determinism](../determinism.md)*

BT4: a line is parsed with the same checks, in the same order, as `run`, and its result equals the `run` result key for key and bit for bit. BT7: no state carries from one line to the next, not caches that change a number, not error state, not the random state. Reordering the lines reorders the results and changes nothing else.

Without these rules, a golden run in batch mode could pass because of something an earlier case left behind: a warmed cache that changes an iteration path, a random stream that continued instead of restarting. The test of the code would then depend on the order of the test cases.

That is why "a `batch` result against `run` on the same line" is on the determinism page's bit-exact list: it is the same code path with no state between lines, so there is no reason for even one bit to differ. It also lets the daily workflows send many cases to one `quantforge --batch` process and still test exactly the code the goldens test.

## Outside evidence

### Q12.29 What is the outside-library share, and what floor must each stage meet?

*Level: practitioner. Evidence: computed; spec; design. Source: [Outside shares](../../oracle/OUTSIDE_SHARES.md), [R6 rulings](../../specifications/r6-rulings.md)*

It is the share of a stage's value-checked cases whose every compared output was also produced by an outside library, independently of the oracle's own reference. It is the main defence against a shared misreading of the spec (Q12.3).

The floor (R6-13, owner decision D6) is 60% of the stage's value-checked cases, with error and invariance cases outside the denominator and generated sweeps shown separately. A case counts only as `library-object` (a library's own pricing or estimation object, such as a QuantLib engine or an ORE simulation) or `library-primitive` (NumPy or SciPy numerics applied to a different formulation of the same problem), and only if every compared output is checked. A `reimplementation` (the spec formula written again around a library call) does not count, nor does a published worked example alone. `independent-rederivation` is added in the floor column for stage F and shown apart.

**Worked example.** Stage I: 102 of 153 value cases are `library-primitive`, a library-only share of 66.7%. Stage J: 14 `library-object` plus 116 `library-primitive` = 130 of 212 at v0.9.0, which is 0.6132 (130 of 215 = 0.6047 after the v0.9.1 fuzz-fix cases); the generated table prints it as 61.3% (the 20 curves lane value cases and the 6 hedge fix value cases have no outside library, ruling J-C-9; wave 3 counts 31 of its 56). Both meet the floor.

The table is generated by `tools/outside_shares.py`, so the figures cannot be edited by hand.

### Q12.30 Some suites have no outside reference at all. How does QuantForge handle them?

*Level: advanced. Evidence: spec; design. Source: [Outside shares](../../oracle/OUTSIDE_SHARES.md), [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Hedge slippage](../../specifications/08-hedging/hedge-slippage.md)*

It names them and says why. The outside-shares report has a table of value classes with no free outside reference: `hedgeint_i` (no free library solves integer least squares with these constraints, so exact rational enumeration is the oracle), `hedgebeta_i` (arithmetic on given betas; Hull's worked example is a textbook check), `hedgeres_i` (arithmetic on the hedge solve's own outputs) and `hedgeslip_i` (no free library computes implementation shortfall).

For such suites the oracle uses a second method of its own instead: for `hedgeint_i`, an exhaustive search in exact rational arithmetic plus a float search over a box with the same tie rule; for `hedgeslip_i`, exact rational arithmetic with the identities `shortfall = execution + opportunity` asserted on every order.

That is weaker evidence than an outside library, and the project says so: these cases are self-assessment until the human review. Naming them stops a high overall share from hiding the suites where it is zero.
