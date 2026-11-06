# Python implementation

One of four equal implementations; it is not a reference for the others.

Install: `uv sync`

Test: `uv run ruff check .` and `uv run pytest`

Conformance, from the repository root: `python conformance/runner/runner.py --impl python`

The interpreter is pinned in `.python-version` and dependencies in `uv.lock`. NumPy is used only for
symmetric eigenvalues. SciPy is a dev dependency, for second checks in the tests.

`quantforge_core` holds one module per spec in `specifications/01-core/`. `quantforge_core/cli` holds
the `quantforge` command, the input decoding, and the test function registry.

21 golden cases disagree with the spec text. They are listed in `SPEC_QUESTIONS.md`, with the other
choices made where a spec was silent.
