# Python implementation

One of four equal implementations; it is not a reference for the others.

Stages A and B, on Python 3.15.2, written from the specs in `specifications/` and `specifications/cli-contract.md`.

Install: `uv sync`

Test: `uv run ruff check .` and `uv run pytest`

Conformance, from the repository root: `python conformance/runner/runner.py --impl python`

The interpreter is pinned in `.python-version` and dependencies in `uv.lock`. NumPy is used only for
symmetric eigenvalues and condition numbers. SciPy is a dev dependency, for second checks in the tests.

`quantforge_core` holds one module per spec, for stages A and B. `quantforge_core/cli` holds
the `quantforge` command, the input decoding, and the test function registry. The other `quantforge_*`
folders are empty placeholders for later stages.

Open questions on the specs, and the choices made where one was silent, are in `SPEC_QUESTIONS.md`.
