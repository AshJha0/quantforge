# Java 25 implementation

Stages A and B of QuantForge, written from the specifications. It uses JDK 25
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
`SobolData.java` carries the direction numbers as code, because the CLI reads no file for its numbers.

`GoldenSuiteTest` runs every golden case in process. Spec questions are in `SPEC_QUESTIONS.md`.

The other packages under `org/quantforge/` are empty placeholders for later stages. No benchmark has been run.
