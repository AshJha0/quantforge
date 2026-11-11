"""The one helper the tutorial scripts share: `connect` returns `call(operation, inputs)`.

With no arguments it runs each operation in this process through the Python package
(`quantforge_core`, the same entry point as the `quantforge` command). With a command line, such as
`rust/target/release/quantforge`, it sends each case to that build's `batch` command instead
(specifications/cli-contract.md). Either way `call` returns the case's `outputs` object, so every
tutorial prints the same lines whichever implementation answers. Standard library only.
"""
import json
import shutil
import subprocess


def _case(operation, inputs):
    return {"schema_version": "1.0", "case_id": operation, "operation": operation, "inputs": inputs}


def connect(argv):
    if not argv:
        from quantforge_core.cli.main import run_case  # needs `uv run --project python`

        def call(operation, inputs):
            return _checked(run_case(json.dumps(_case(operation, inputs))))
        return call
    cli = [shutil.which(argv[0]) or argv[0], *argv[1:], "batch"]  # finds quantforge.exe on Windows

    def call(operation, inputs):
        line = json.dumps(_case(operation, inputs)) + "\n"
        p = subprocess.run(cli, input=line, capture_output=True, text=True, check=True)
        [result] = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        return _checked(result)
    return call


def _checked(result):
    if result["status"] != "ok":
        raise SystemExit(f"{result['case_id']}: {result['error']}")
    return result["outputs"]
