"""Bytes, outside time evidence and workflow files of the two daily jobs (audit C of 2026-11-19; rulings KR-200
to KR-214). Fast, with no fit and no ledger run, so the `python-daily-jobs-bytes` job can run it by itself on the
ubuntu runner image that will write the real rows.

- canonical bytes: the pinned rows of tools/paper_daily/canonical_selftest.py, and a planted change of
  serialisation shown failing;
- anchor evidence: a real anchor of this repository's forward log is followed through its OpenTimestamps proof
  to a real Bitcoin block header; every way of faking a time is shown failing;
- the two workflow files and the schedule, as text.

No market data is in this file."""

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import daily_jobs_support as support
import pytest

ROOT = Path(__file__).resolve().parents[2]
selftest = support.load(
    "canonical_selftest", ROOT / "tools" / "paper_daily" / "canonical_selftest.py"
)
evidence = support.evidence
WF = ROOT / ".github" / "workflows"
PAPER = (WF / "paper-ledger.yml").read_text(encoding="utf-8")
CURVE = (WF / "curve-daily.yml").read_text(encoding="utf-8")
RECORDER = (WF / "recorder.yml").read_text(encoding="utf-8")

# ------------------------------------------------------------------ canonical bytes (KR-208)


def test_canonical_bytes_and_hashes_are_the_pinned_ones() -> None:
    assert selftest.check() == []
    assert (
        selftest.imports_the_jobs_need()
    )  # the modules the scheduled tools load, and the prereg windows


def test_the_pins_are_literal_bytes_not_recomputed() -> None:
    """The small rows are pinned as whole lines, so the test does not depend on the code it checks: the line is
    the SHA-256 preimage with the hash put back in."""
    for job in ("paper", "curve"):
        ln = selftest.PINS[f"{job}.small.line"]
        assert ln.isascii() and "\n" not in ln and ", " not in ln and '": ' not in ln
        rec = json.loads(ln)
        assert list(rec) == sorted(rec) and rec["seq"] == 7 and isinstance(rec["seq"], int)
        body = {k: v for k, v in rec.items() if k != "hash"}
        again = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert (
            hashlib.sha256(again.encode("ascii")).hexdigest()
            == rec["hash"]
            == selftest.PINS[f"{job}.small.hash"]
        )
    both = (
        selftest.PINS["paper.small.line"] + "\n" + selftest.PINS["curve.small.line"] + "\n"
    ).encode("ascii")
    assert hashlib.sha256(both).hexdigest() == selftest.PINS["file.sha256"]


@pytest.mark.parametrize(
    "fault", ["separators", "key order", "non-ascii", "float repr", "decimal form"]
)
def test_a_planted_change_of_serialisation_fails_the_pins(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """Plan 14.10 rule 1: each way a platform or a refactor could change the bytes makes the pin test fail."""
    paper, curve = selftest.paper, selftest.curve

    def dumps(rec: dict[str, Any], **kw: Any) -> str:
        return json.dumps(
            rec, **{"sort_keys": True, "separators": (",", ":"), "ensure_ascii": True, **kw}
        )

    if fault == "separators":
        monkeypatch.setattr(paper, "line", lambda rec: dumps(rec, separators=(", ", ": ")))
    elif fault == "key order":
        monkeypatch.setattr(curve, "line", lambda rec: dumps(rec, sort_keys=False))
    elif fault == "non-ascii":
        monkeypatch.setattr(paper, "line", lambda rec: dumps(rec, ensure_ascii=False))
    elif fault == "float repr":
        monkeypatch.setattr(curve, "fstr", lambda x: f"{x:.12g}")
    else:
        monkeypatch.setattr(paper, "plain", lambda d: str(d))
    try:
        bad = selftest.check()
    except UnicodeEncodeError, AssertionError:
        return  # the non-ASCII line cannot even be written as the ledger file
    assert bad, fault


def test_times_and_dates_have_one_spelling() -> None:
    """A row time is exactly YYYY-MM-DDTHH:MM:SSZ in both tools; anything else is refused."""
    for core in (selftest.paper, selftest.curve):
        t = core.instant("2027-01-04T23:45:00Z")
        assert (
            t == dt.datetime(2027, 1, 4, 23, 45, tzinfo=dt.UTC)
            and core.stamp(t) == "2027-01-04T23:45:00Z"
        )
        assert (
            core.stamp(dt.datetime(2027, 1, 5, 1, 45, tzinfo=dt.timezone(dt.timedelta(hours=2))))
            == "2027-01-04T23:45:00Z"
        )
        for bad in (
            "2027-1-4T23:45:00Z",
            "2027-01-04 23:45:00Z",
            "2027-01-04T23:45:00+00:00",
            "2027-01-04T23:45:00.5Z",
            "2027-01-04T23:45:00z",
            "2027-01-04T23:45:60Z",
            "٢٠٢٧-01-04T23:45:00Z",
            "",
        ):
            with pytest.raises(ValueError):
                core.instant(bad)


# ------------------------------------------------------------------ anchor evidence (KR-200 to KR-202)

FIX = json.loads(
    (ROOT / "tools" / "paper_daily" / "testdata" / "forward_log_anchor.json").read_text(
        encoding="utf-8"
    )
)
ANCHOR, PROOF = bytes.fromhex(FIX["anchor_hex"]), bytes.fromhex(FIX["proof_hex"])
HEADERS = {str(FIX["height"]): FIX["header_hex"]}


def test_a_real_anchor_is_followed_to_a_real_bitcoin_block() -> None:
    """Measured, not constructed: an anchor the recorder stamped on 2026-11-13 at 03:30:46 UTC, its upgraded
    proof, and block 975631. The proof's path ends at the header's Merkle root, the header meets its own target
    and the production floor, and its time is 04:20:34 UTC the same day."""
    assert evidence.heights(PROOF, ANCHOR) == [FIX["height"]] == [975631]
    kinds = [a[0] for a in evidence.attestations(PROOF, ANCHOR)]
    assert kinds.count("bitcoin") == 1 and "pending" in kinds
    t = evidence.attested_time(PROOF, ANCHOR, HEADERS)
    assert t == FIX["block_time"] == 1794543634
    assert (
        dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        == "2026-11-13T04:20:34Z"
    )
    made = dt.datetime(2026, 11, 13, 3, 30, 46, tzinfo=dt.UTC)  # the anchor's own name
    assert 0 < t - made.timestamp() < 3600
    assert (
        evidence.attested_time(PROOF, ANCHOR, {}) is None
    )  # no header supplied: no evidence, not an error


def test_every_way_of_faking_the_block_time_fails() -> None:
    with pytest.raises(evidence.EvidenceError, match="different file"):
        evidence.attested_time(PROOF, ANCHOR + b" ", HEADERS)
    # one flipped bit anywhere in the proof: an error, or no evidence, or (outside the path to the block) the
    # same time; never a different time
    refused = 0
    for at in range(len(evidence.MAGIC), len(PROOF)):
        flipped = bytearray(PROOF)
        flipped[at] ^= 1
        try:
            got = evidence.attested_time(bytes(flipped), ANCHOR, HEADERS)
        except evidence.EvidenceError:
            refused += 1
            continue
        assert got in (None, FIX["block_time"]), at
    assert refused > 300
    h = bytearray.fromhex(FIX["header_hex"])
    later = bytes(h[:68]) + (FIX["block_time"] - 86400).to_bytes(4, "little") + bytes(h[72:])
    with pytest.raises(evidence.EvidenceError, match="proof-of-work"):  # the time moved a day back
        evidence.attested_time(PROOF, ANCHOR, {"975631": later.hex()})
    with pytest.raises(evidence.EvidenceError, match="80 bytes"):
        evidence.attested_time(PROOF, ANCHOR, {"975631": FIX["header_hex"][:-2]})
    with pytest.raises(evidence.EvidenceError, match="not hex"):
        evidence.attested_time(PROOF, ANCHOR, {"975631": "zz" * 80})
    # a home-made header that holds the right Merkle root and any time one likes: it meets its own, easy target
    # and is refused by the floor; with the floor lifted (tests only) it would be believed
    root = next(a[2] for a in evidence.attestations(PROOF, ANCHOR) if a[0] == "bitcoin")
    home_made = support.header_for(root, 1700000000)
    with pytest.raises(evidence.EvidenceError, match="floor"):
        evidence.attested_time(PROOF, ANCHOR, {"975631": home_made})
    assert (
        evidence.attested_time(PROOF, ANCHOR, {"975631": home_made}, support.EASY_TARGET)
        == 1700000000
    )
    # the real header is within the floor by a wide margin, and the floor is far above an easy chain's target
    bits = int.from_bytes(bytes.fromhex(FIX["header_hex"])[72:76], "little")
    target = (bits & 0x7FFFFF) << (8 * ((bits >> 24) - 3))
    assert (
        target < evidence.MAX_TARGET // 4 and evidence.MAX_TARGET == 1 << 180 < support.EASY_TARGET
    )


def test_malformed_proofs_are_errors_and_pending_proofs_are_no_evidence() -> None:
    data = b"anchor"
    pending, _ = support.proof_for(data, None)
    assert (
        evidence.attested_time(pending, data, {}) is None and evidence.heights(pending, data) == []
    )
    good, root = support.proof_for(data, 800123)
    hdr = {"800123": support.header_for(root, 1800000000)}
    assert evidence.attested_time(good, data, hdr, support.EASY_TARGET) == 1800000000
    for bad in (
        b"",
        good[:40],
        good + b"\x00",
        good.replace(evidence.MAGIC, b"\x00" * len(evidence.MAGIC)),
        good[: len(evidence.MAGIC)] + b"\x02" + good[len(evidence.MAGIC) + 1 :],
    ):
        with pytest.raises(evidence.EvidenceError):
            evidence.attested_time(bad, data, hdr, support.EASY_TARGET)
    # an operation a Bitcoin path does not use (0x02, SHA-1) is passed through, not guessed at: what lies under
    # it is no evidence; a tag that is not an operation at all is an error
    at = len(evidence.MAGIC) + 2 + 32
    through = good[:at] + b"\x02" + good[at:]
    assert [a[0] for a in evidence.attestations(through, data)] == ["pending"]
    assert evidence.attested_time(through, data, hdr, support.EASY_TARGET) is None
    with pytest.raises(evidence.EvidenceError, match="not known"):
        evidence.attestations(good[:at] + b"\x55" + good[at:], data)


def test_proven_before_takes_the_earliest_covering_block_and_the_margin() -> None:
    anchors = [("a.json", 5), ("b.json", 9), ("c.json", 9)]
    times: dict[str, int | None] = {"a.json": 1000, "b.json": None, "c.json": 5000}
    assert evidence.MARGIN_SECONDS == 7200
    assert evidence.proven_before(4, 1000 + 7201, anchors, times) == (True, "a.json", 1000)
    assert evidence.proven_before(4, 1000 + 7200, anchors, times)[0] is False  # strictly before
    ok, why, _ = evidence.proven_before(5, 10**9, anchors, times)  # a.json covers lines 0 to 4 only
    assert ok and why == "c.json"
    ok, why, _ = evidence.proven_before(8, 10**9, [("b.json", 9)], times)
    assert not ok and "pending" in why
    ok, why, _ = evidence.proven_before(9, 10**9, anchors, times)
    assert not ok and "no anchor covers" in why


# ------------------------------------------------------------------ the workflow files, as text


def run_scripts(wf: str) -> str:
    """Every line that belongs to a `run:` block or a one-line `run:`."""
    out, inside, indent = [], False, 0
    for ln in wf.splitlines():
        stripped = ln.lstrip()
        if inside and stripped and len(ln) - len(stripped) <= indent:
            inside = False
        if inside:
            out.append(ln)
        elif stripped.startswith("run:"):
            indent = len(ln) - len(stripped)
            inside = stripped.rstrip().endswith("|")
            out.append(ln)
    return "\n".join(out)


def crons(wf: str) -> list[tuple[int, int, str]]:
    return [
        (int(h), int(m), dow) for m, h, dow in re.findall(r"cron: '(\d+) (\d+) \* \* ([\d-]+)'", wf)
    ]


@pytest.mark.parametrize(
    ("wf", "ledger", "anchors"),
    [
        (PAPER, "paper-ledger", "paper-ledger-anchors"),
        (CURVE, "curve-daily", "curve-daily-anchors"),
    ],
)
def test_workflow_guards_inputs_and_pushes(wf: str, ledger: str, anchors: str) -> None:
    uses = [ln.split("uses:")[1].strip() for ln in wf.splitlines() if "uses:" in ln]
    assert uses and all(u in RECORDER and len(u.split("@")[1].split()[0]) == 40 for u in uses)
    assert (
        "permissions:\n  contents: write\nconcurrency:" in wf and "cancel-in-progress: false" in wf
    )
    assert "pull_request" not in wf
    # KA-C26 and KA-C5: this repository only, main only; the commit recorded is the one checked out
    assert (
        "    if: github.repository == 'AshJha0/quantforge' && github.ref == 'refs/heads/main'\n"
        in wf
    )
    scripts = run_scripts(wf)
    assert "GITHUB_SHA" not in wf and scripts.count("git -C code rev-parse HEAD") == 1
    assert '--commit "$commit"' in scripts
    # no expression is pasted into a shell line: inputs and secrets reach the scripts through `env:` only
    assert "${{" not in scripts
    assert "DRY_RUN: ${{ inputs.dry_run && 'true' || 'false' }}" in wf
    # KA-C1: named files only, the anchor step makes no second anchor for a head, and cannot run after a failed push
    assert "git add -A" not in scripts and "git add ." not in scripts
    assert "--if-uncovered" in scripts and "if: steps.push.outcome == 'success'" in wf
    pushes = [ln.strip() for ln in scripts.splitlines() if "git push" in ln]
    assert (
        len(pushes) == 2
        and pushes[0] == f"git push origin {ledger}"
        and f"git push origin {anchors}" in pushes[1]
    )
    assert "--force" not in wf and "push -f" not in wf
    assert "printf '* -text\\n' > ledger/.gitattributes" in scripts
    assert scripts.count("continue-on-error") == 0 and wf.count("continue-on-error: true") == 2
    assert "OUTCOMES: run=${{ steps.run.outcome }} anchor=${{ steps.anchor.outcome }}" in wf


def test_the_paper_workflow_commits_only_the_ledger_and_follows_the_recorder() -> None:
    scripts = run_scripts(PAPER)
    assert "git add -- ledger/ledger.jsonl ledger/summary.json" in scripts
    # KA-C1: a commit only when the ledger itself changed; the result that holds the anchor count stays in the
    # runner's temporary folder, and the summary kept on the branch follows from the rows alone
    assert "if git diff --cached --quiet -- ledger/ledger.jsonl README.md; then" in scripts
    assert (
        '--summary "$RUNNER_TEMP/paper_summary.json" --ledger-summary ledger/ledger/summary.json'
        in scripts
    )
    assert "if git diff --cached --quiet -- ledger/curves.jsonl README.md; then" in run_scripts(
        CURVE
    )
    # KA-C4: SOURCE checked before every push
    assert "--forward-log fwd/actions/log.jsonl --summary" in scripts
    assert "git -C fwd remote remove origin" in scripts
    # the trigger that follows the recorder is written down and withheld with the schedule (see the test below)
    assert (
        "  #   workflow_run:\n  #     workflows: [Recorder]\n  #     types: [completed]\n" in PAPER
    )
    assert RECORDER.startswith("name: Recorder\n")
    assert "Source: US Department of the Treasury." in PAPER


@pytest.mark.parametrize("wf", [PAPER, CURVE])
def test_daily_job_schedule_restored_at_release(wf: str) -> None:
    """Triggers were withheld (2026-11-19) until audit findings KA-C1, C2, C3, C9, C11, C12 were closed; restored
    at the v0.10.1 release (2026-11-20) after the follow-up different-model audit was clean and the coordinator
    confirmed KR-200 to KR-214, KR-254 and KR-255. Manual runs stay available."""
    code = [ln.split("#")[0] for ln in wf.splitlines()]
    assert any(ln.strip() == "schedule:" for ln in code)
    assert sum("cron:" in ln for ln in code) >= 2
    assert any(ln.strip() == "workflow_dispatch:" for ln in code)
    assert "schedule restored at the v0.10.1 release" in wf
    assert "KR-200 to KR-214" in wf


def test_the_curve_workflow_cites_both_sources_in_the_branch_readme() -> None:
    cfg = selftest.curve.load_config()
    scripts = run_scripts(CURVE)
    assert "git add -- ledger/curves.jsonl ledger/summary.json" in scripts
    assert "US Department of the Treasury" in cfg["treasury"]["attribution"]
    assert "Board of Governors of the Federal Reserve System" in cfg["gsw"]["attribution"]
    readme = next(ln for ln in scripts.splitlines() if "> ledger/README.md" in ln)
    assert (
        "US Department of the Treasury" in readme
        and "Board of Governors of the Federal Reserve System" in readme
    )
    assert (
        "can be worked back" in readme and "no source rows" not in CURVE.lower()
    )  # KA-C11: said plainly


# Measured 2026-11-19 from `gh run list` start times of the scheduled runs of recorder.yml and
# daily-workflows.yml, 2026-11-09 to 2026-11-19 (n = 24): hours between the cron time and the run's start.
DELAY_MIN, DELAY_MAX = 3.4, 9.0
RECORDER_EVENING_LATEST = (
    23.5 + 5.7
)  # the 23:30 slot, n = 8, largest delay 5.67 h: 05:12 UTC next day
ATTEST_MAX = (
    1.6  # hours from an anchor to its Bitcoin block, n = 16 forward-log anchors, largest 1.58 h
)
MARGIN = 2.0  # anchor_evidence.MARGIN_SECONDS
CUTOFF = 19.5  # on_time_cutoff_utc of both configurations, next business day


@pytest.mark.parametrize(("wf", "name"), [(PAPER, "paper"), (CURVE, "curve")])
def test_every_schedule_slot_lands_on_time_under_the_measured_delays(wf: str, name: str) -> None:
    """KA-C12, KR-206: no slot is a `second chance` that can only produce a late row. For each cron slot, the
    whole measured range of start delays must leave the row, its Bitcoin block and the margin before the cut-off."""
    assert evidence.MARGIN_SECONDS == MARGIN * 3600
    for core in (selftest.paper, selftest.curve):
        assert core.load_config()["on_time_cutoff_utc"] == "19:30:00"
    slots = crons(wf)
    assert len(slots) >= 2
    for hour, minute, dow in slots:
        start = hour + minute / 60
        evening = (
            start >= 12
        )  # a slot late on business day D itself; the others run on the morning after
        assert dow == ("1-5" if evening else "2-6"), (name, hour, minute, dow)
        first = (
            start + DELAY_MIN - (24 if evening else 0)
        )  # hours after midnight UTC of the next day
        last = start + DELAY_MAX - (24 if evening else 0)
        assert last + ATTEST_MAX + MARGIN < CUTOFF, (
            name,
            hour,
            minute,
            "lands too close to the cut-off",
        )
        if name == "paper":  # needs the recorder's evening run to have written the curve
            assert first > RECORDER_EVENING_LATEST - 24, (
                name,
                hour,
                minute,
                "can land before the recorder",
            )
        else:  # must not start before the day is due (23:00 UTC on D)
            assert start + (24 if not evening else 0) >= 23, (name, hour, minute)
    if name == "curve":
        assert len(slots) == 3


def test_the_audited_second_chance_slots_fail_the_same_check() -> None:
    """Plan 14.10 rule 1: the schedule check is shown failing on the slots the audit found (KA-C12)."""
    daytime_min = 6.2  # the 14:30 and 15:00 UTC slots, n = 16: smallest delay measured
    for hour, minute in (
        (15, 10),
        (14, 15),
    ):  # paper-ledger.yml and curve-daily.yml at the audited commit
        start = hour + minute / 60
        assert not start + DELAY_MAX + ATTEST_MAX + MARGIN < CUTOFF
        assert start + daytime_min > CUTOFF  # after the cut-off on every day measured
    assert (
        40 / 60 + DELAY_MIN < RECORDER_EVENING_LATEST - 24
    )  # the audited 00:40 slot could land before the recorder


def test_the_linux_bytes_job_exists() -> None:
    py = (WF / "python.yml").read_text(encoding="utf-8")
    job = py[py.index("  daily-jobs-bytes:") :]
    assert "runs-on: ubuntu-24.04" in job and "name: python-daily-jobs-bytes" in job
    assert (
        "uv run pytest tests/test_daily_jobs_bytes.py tests/test_paper_daily.py::test_goldens_pl_k -q"
        in job
    )
    assert "python3 ../tools/paper_daily/canonical_selftest.py" in job


def test_heights_lists_the_headers_a_verifier_must_supply(tmp_path: Path) -> None:
    """`verify_ledger.py heights` and `verify_chain.py heights`: block heights named by the proofs, and the
    anchors with no Bitcoin attestation yet."""
    headers: dict[str, str] = {}
    for name, height in (("a.json", 800001), ("b.json", None), ("c.json", 800007)):
        p = tmp_path / name
        p.write_bytes(name.encode())
        support.stamp(p, height, None if height is None else 1800000000, headers)
    (tmp_path / "d.json").write_bytes(b"an anchor whose stamp failed: no proof file")
    need, pending = evidence.needed_heights(tmp_path)
    assert need == [800001, 800007] and pending == ["b.json", "d.json"]
    times = evidence.anchor_times(tmp_path, headers, support.EASY_TARGET)
    assert times == {"a.json": 1800000000, "b.json": None, "c.json": 1800000000, "d.json": None}
    assert evidence.load_headers(support.write_headers(tmp_path / "h.txt", headers)) == headers
    (tmp_path / "bad.txt").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(evidence.EvidenceError):
        evidence.load_headers(tmp_path / "bad.txt")


def test_each_tool_resolves_its_own_modules_in_a_fresh_interpreter() -> None:
    """Both tool folders hold a `run_day.py`, and the curve verifier also reads the paper folder for the shared
    evidence module. Started as scripts (as the workflows start them), each must import its own folder's files.
    Found by running the revised curve verifier by hand on 2026-11-19: it had picked up the paper `run_day`."""
    import subprocess
    import sys

    tools = ROOT / "tools"
    probes = {
        "curve_daily/verify_chain.py": ("run_day", "core"),
        "curve_daily/run_day.py": ("core",),
        "paper_daily/verify_ledger.py": ("core",),
        "paper_daily/run_day.py": ("core", "fl"),
    }
    for script, names in probes.items():
        folder, stem = script.split("/")[0], script.split("/")[1][:-3]
        code = (
            f"import sys; sys.path.insert(0, r'{tools / folder}'); import {stem} as m; "
            f"print(*[getattr(m, n).__file__ for n in {names!r}], sep=chr(10))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        files = [Path(x) for x in out.stdout.split()]
        assert len(files) == len(names)
        for name, f in zip(names, files, strict=True):
            want = "forward-log" if name == "fl" else folder
            assert f.parent.name == want, (script, name, f)
    assert hasattr(
        support.load("curve_verify_chain_probe", tools / "curve_daily" / "verify_chain.py"),
        "anchored_timing",
    )
