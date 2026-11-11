# Python implementation

One of four equal implementations; it is not a reference for the others.

Stages A to G, and stage I wave 1 (hedge solvers), on Python 3.15.2, written from the specs in `specifications/` and `specifications/cli-contract.md`.

Install: `uv sync`

Test: `uv run ruff check .` and `uv run pytest`

Conformance, from the repository root: `python conformance/runner/runner.py --impl python`

The interpreter is pinned in `.python-version` and dependencies in `uv.lock`. NumPy is used for symmetric
eigenvalues and condition numbers, and in `hedge_solvers` for the SVD, QR and least-squares steps. SciPy is a dev dependency, for second checks in the tests.

`quantforge_core` holds one module per domain spec (curves, bonds, credit, caps_swaptions, variance and
so on), never named by stage. `quantforge_core/cli` holds the `quantforge` command and the input
decoding. Each `cli/ops_<domain>.py` registers its verbs with `registry.op`, and the verb table
(`quantforge operations`) is generated from that registry. The other `quantforge_*` folders are
empty placeholders.

Open questions on the specs, and the choices made where one was silent, are in `SPEC_QUESTIONS.md`.
