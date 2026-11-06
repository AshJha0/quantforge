"""Commands, envelope handling and exit codes (specifications/cli-contract.md)."""
import json
import math
import platform
import re
import sys
from typing import Any

from .. import __version__, strictjson
from ..errors import QfError
from .operations import OPERATIONS, execute

CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
MAX_CASE_DEPTH = 80
_ENVELOPE_KEYS = {"schema_version", "case_id", "operation", "inputs"}
_SCHEMA_VERSION = re.compile(r"[0-9]+\.[0-9]+")
_OPERATION = re.compile(r"[a-z0-9_]+(\.[a-z0-9_]+)+")


def _error(case_id: str, code: str, message: str, field: str | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return {
        "schema_version": SCHEMA_VERSION, "case_id": case_id, "status": "error", "error": error,
    }


def _all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_all_finite(v) for v in value.values())
    if isinstance(value, list):
        return all(_all_finite(v) for v in value)
    return True


def _check_envelope(document: Any) -> None:
    if not isinstance(document, dict):
        raise QfError("E_SCHEMA", "a case must be an object")
    if set(document) != _ENVELOPE_KEYS:
        raise QfError("E_SCHEMA", "the case must hold exactly the envelope keys")
    version, case_id = document["schema_version"], document["case_id"]
    if not isinstance(version, str) or _SCHEMA_VERSION.fullmatch(version) is None:
        raise QfError("E_SCHEMA", "bad schema_version", "schema_version")
    if not isinstance(case_id, str) or not case_id:
        raise QfError("E_SCHEMA", "bad case_id", "case_id")
    operation = document["operation"]
    if not isinstance(operation, str) or _OPERATION.fullmatch(operation) is None:
        raise QfError("E_SCHEMA", "bad operation", "operation")
    if not isinstance(document["inputs"], dict):
        raise QfError("E_SCHEMA", "inputs must be an object", "inputs")


def run_case(text: str) -> dict[str, Any]:
    """Runs one case document. A bug in the core is not caught here: it is exit code 70."""
    case_id = "unknown"
    try:
        strictjson.check_depth(text, MAX_CASE_DEPTH)
        document, overflowed = strictjson.parse(text)
        if isinstance(document, dict):
            found = document.get("case_id")
            if isinstance(found, str) and found:
                case_id = found
        _check_envelope(document)
        if overflowed:
            raise QfError("E_SCHEMA", "a number overflows binary64")
        if document["operation"] not in OPERATIONS:
            raise QfError("E_UNSUPPORTED_OPERATION", f"{document['operation']} is not in this build")
        result = execute(document["operation"], document["inputs"])
    except QfError as e:
        return _error(case_id, e.code, e.message, e.field)
    except (ArithmeticError, ValueError) as e:
        # math raises where IEEE arithmetic would give NaN or infinity.
        return _error(case_id, "E_NON_FINITE", f"a result would not be finite: {e}")
    outputs, diagnostics = result if isinstance(result, tuple) else (result, {})
    if not _all_finite(outputs):
        return _error(case_id, "E_NON_FINITE", "a result would not be finite")
    return {
        "schema_version": SCHEMA_VERSION, "case_id": case_id, "status": "ok",
        "outputs": outputs, "diagnostics": diagnostics,
    }


def _decode_and_run(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _error("unknown", "E_PARSE", "input is not UTF-8")
    return run_case(text)


def _write(value: Any) -> None:
    # ASCII escapes keep one result on one line for any reader, and are still UTF-8 JSON.
    line = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    sys.stdout.buffer.write(line.encode("ascii") + b"\n")
    sys.stdout.buffer.flush()


def _run() -> int:
    result = _decode_and_run(sys.stdin.buffer.read())
    _write(result)
    return 0 if result["status"] == "ok" else 2


def _batch() -> int:
    for line in sys.stdin.buffer:
        _write(_decode_and_run(line))
    return 0


def _version() -> int:
    _write(
        {
            "language": "python",
            "implementation_version": __version__,
            "contract_version": CONTRACT_VERSION,
            "toolchain": f"CPython {platform.python_version()}",
        }
    )
    return 0


def _operations() -> int:
    _write(sorted(OPERATIONS))
    return 0


COMMANDS = {"run": _run, "batch": _batch, "version": _version, "operations": _operations}


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 1 or args[0] not in COMMANDS:
        print("usage: quantforge run|batch|version|operations", file=sys.stderr)
        return 64
    try:
        return COMMANDS[args[0]]()
    except Exception as e:  # noqa: BLE001 - the contract's internal fault
        print(f"internal fault: {e!r}", file=sys.stderr)
        return 70


if __name__ == "__main__":
    sys.exit(main())
