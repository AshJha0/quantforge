# Contributing

## Required workflow
1. Select an issue with explicit scope and acceptance criteria.
2. Read the relevant domain specification and ADRs.
3. Add or update tests before changing model behaviour.
4. Implement independently in the target language, from the spec alone. No language is a reference, and golden values come only from `oracle/`.
5. Run formatting, static analysis, unit tests and relevant conformance tests.
6. Add benchmark evidence when performance is affected.
7. Update documentation, limitations and changelog.
8. Open a PR linking the issue and attach test evidence.

## Pull request checklist
- [ ] Mathematical specification reviewed and unchanged or updated.
- [ ] Inputs, outputs, units and conventions are explicit.
- [ ] Normal, boundary, invalid and numerical stress cases tested.
- [ ] Determinism and reproducibility verified.
- [ ] Cross-language fixtures updated where applicable.
- [ ] CLI changes pass `python conformance/runner/batch_check.py --impl <lang>` as well as the golden runner.
- [ ] Independent expected values or external reference evidence supplied.
- [ ] Performance impact measured where relevant.
- [ ] Limitations and unsupported cases documented.
- [ ] No licensed or sensitive market data committed without permission.

## Definition of done
A feature is not complete because the happy-path example works. It must meet its domain's acceptance criteria and `program/definition-of-done.md`.
