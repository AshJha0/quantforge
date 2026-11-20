"""Unexpected skips fail the run (K-9 review finding 21).

A skipped test is reported (pytest `-ra`) but used to pass silently: test_goldens_stage_d.py skipped in CI for
months. Every skip reason must contain one of the lines of tests/expected_skips.txt; any other skip turns the
session's exit status to 1 and names the test.
"""

from pathlib import Path

import pytest

_EXPECTED = [
    line.strip()
    for line in (Path(__file__).parent / "expected_skips.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
_unexpected: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped and not hasattr(report, "wasxfail"):
        reason = str(report.longrepr[-1]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
        if not any(e in reason for e in _EXPECTED):
            _unexpected.append(f"{report.nodeid}: {reason}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _unexpected and exitstatus == 0:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if _unexpected:
        terminalreporter.section("unexpected skips (tests/expected_skips.txt)")
        for line in _unexpected:
            terminalreporter.write_line(line)
