"""Starts the Python `quantforge` CLI for the K-6 soak and capacity scripts. Holds no financial logic.

Why it exists: on Windows the `python.exe` of a virtual environment is a small launcher that starts the real
interpreter as a child, so the process the harness starts is not the one doing the work. This entry point writes
its own process id to the file named by QF_SOAK_PIDFILE, so the sampler watches the right process on every platform.

Planted fault (rule 1, KR-218): with QF_SOAK_LEAK=1 it keeps 1 KiB alive for every 100 cases, so the analyser can be
shown flagging a leak. The library itself is untouched; the leak lives only in this harness file.
"""

import os
import sys

from quantforge_core.cli import main as cli

_pidfile = os.environ.get("QF_SOAK_PIDFILE")
if _pidfile:
    with open(_pidfile, "w", encoding="ascii") as f:
        f.write(str(os.getpid()))

if os.environ.get("QF_SOAK_LEAK") == "1":
    _kept: list[bytearray] = []
    _count = [0]
    _real = cli._decode_and_run

    def _leaky(data: bytes):  # type: ignore[no-untyped-def]
        _count[0] += 1
        if _count[0] % 100 == 0:
            _kept.append(bytearray(1024))
        return _real(data)

    cli._decode_and_run = _leaky  # type: ignore[assignment]

sys.argv[0] = "quantforge"
sys.exit(cli.main())
