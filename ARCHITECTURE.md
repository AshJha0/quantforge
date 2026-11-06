# Architecture

QuantForge is one repository holding four isolated implementations and the neutral parts around them. The plain idea: a spec says what must be true, the oracle says what the answer is, and a runner that knows no finance compares each language's answer with it. Detail is in `architecture/`; decisions are in `architecture/decisions/`; diagrams are in `docs/diagrams/`.

| Part | Role | May depend on |
|---|---|---|
| `specifications/` | What must be true | Nothing |
| `oracle/` | Expected results, from outside sources and hand cases | Specs, outside libraries. Tests only |
| `datasets/` | Schemas and golden files | Oracle output |
| `conformance/` | Neutral runner and tolerances | Golden files and each CLI's JSON. No financial logic |
| `java25/`, `cpp26/`, `python/`, `rust/` | Four equal implementations | Specs only. Never each other, never the oracle |
| `tools/` | Recorder and forward log | No financial logic |

## Rules that shape it

- No language is a reference. The oracle is the source of golden results.
- No shared code, FFI or generated maths between implementations.
- The only interface that counts is the CLI: case JSON in, result JSON out.
- Libraries first, services last. Infrastructure arrives as local adapters in stage K.
- Trading is simulated only. There are no live orders.

The specification remains a shared-error risk: four builds and a hand case can share one misreading. That is why outside libraries are used wherever a licence allows, and why a human review closes the project. Until that review, validation is self-assessment.

Stage A builds domain 01 only. Services, `infra/` and the other domains do not exist yet.
