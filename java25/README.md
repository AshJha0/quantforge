# Java 25 implementation

Stage A of QuantForge, written from `specifications/01-core/` and `specifications/cli-contract.md`. It uses JDK 25
final features only, and has no runtime dependencies.

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
`SobolData.java` carries the direction numbers as code, because the CLI reads no file for its numbers.

`GoldenSuiteTest` runs every golden case in process except `limits-0011`, which fails in the neutral runner. Its
outcome depends on rounding, and it is question 13 in `SPEC_QUESTIONS.md`, with the other open questions.

Use primitive arrays and measured allocation-aware designs in numerical hot paths. Do not assume virtual threads
improve CPU-bound numerical kernels.
