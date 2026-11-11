# Java 25 implementation

Stages A to G (released as v0.7.0) and stage I waves 1 to 4d (hedging, target v0.8.0) of QuantForge, written from the specifications. It uses JDK 25
final features only, and has no runtime dependencies; JUnit is for tests only.

```bash
mvn -B test
mvn -B package -DskipTests
java -jar target/quantforge-cli.jar version
```

From the repository root, after packaging:

```bash
python conformance/runner/runner.py --impl java
```

`org.quantforge.core` holds the maths. `org.quantforge.cli` holds the JSON contract and the test-function registry.
Stage B adds `curves` (schedules, curves, product models), `pricing` (instruments, pricing models, valuations),
`calibration`, `risk` and `hedging`.
Stage I adds the hedge solvers to `hedging`: `LeastSquaresHedge` (the constrained QP, by a dual active-set method in
the null space of the equalities, and the integer-lot search by ellipsoid enumeration) and `HedgeRatios` (minimum
variance, Greek neutralisation, beta futures, residual report), then `CreditHedge` (CDS hedges on the stage D ISDA
legs), `CorrelationHedge` (Margrabe exchange options and vanillas) and `CrossAssetHedge` (equity and key rates).
Wave 4 adds hedge costs and the frontier to `LeastSquaresHedge`, `DynamicHedge` (delta-hedge backtest and
effectiveness), `InstrumentSelection` and `Slippage`. The `cli.OpsHedge*` classes map them to the `hedge.*` verbs.
`SobolData.java` carries the direction numbers as code, because the CLI reads no file for its numbers.

`GoldenSuiteTest` runs every golden case in process. Spec questions are in `SPEC_QUESTIONS.md`.

The other packages under `org/quantforge/` are empty placeholders for later stages. No benchmark has been run.
