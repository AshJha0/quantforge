# Cookbook

Short recipes. Commands run from the repository root.

## Run the conformance suite for one language

```bash
python conformance/runner/runner.py --impl rust
```

Add `--suite daycount` for one suite. Build the implementation first, as its README says.

## Send one case by hand

Put a case in `case.json`, as in `specifications/cli-contract.md`, then pipe it to `quantforge run`.

## Regenerate golden files

See `oracle/README.md`. Never edit a golden file by hand, and never produce one from an implementation.

## Record public data

```bash
python tools/recorder/record.py
```

## Check the forward log

```bash
python tools/forward-log/forward_log.py verify
```

## Add a test case

Add it to a generator in `oracle/python/`, naming what verified it in `verified_by`, then regenerate. If it settles a silent point, add a line to `specifications/01-core/rulings.md`.
