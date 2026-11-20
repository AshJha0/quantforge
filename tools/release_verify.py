#!/usr/bin/env python3
"""Verifies the assets of a published release (plan 14.8 K-7, check RE2, ruling KR-223, confirmed 2026-11-20; not met until the first tag run).

    gh release download v1.0.0 --repo AshJha0/quantforge --dir assets
    python tools/release_verify.py --dir assets --repo AshJha0/quantforge --out attest.json
    python tools/release_verify.py --self-test

Plain idea: the release workflow signs a build-provenance attestation for every asset. Anyone can check one with
`gh attestation verify FILE --repo AshJha0/quantforge`, which fails unless GitHub holds a signed attestation whose
subject digest equals the file's SHA-256 and which was made in this repository. A check that has never failed proves
little, so the script also changes one byte of a copy of the first asset and requires the verification of that copy
to fail.

Formal statement. Exit 0 if and only if all of these hold: the folder has at least one asset; it holds a CycloneDX
SBOM (`*.cdx.json`) and `SHA256SUMS`; every line of `SHA256SUMS` matches its file and every asset is listed in it;
`gh attestation verify` exits 0 on every asset; and it exits non-zero on the tampered copy. The JSON written to
--out has one row per asset: name, sha256, verdict (`verified` or `FAILED`), plus the tampered-copy row.

What it does not show: that the code is correct. An attestation says which workflow at which commit built the file.

Standard library only; `gh` must be on PATH (it is on GitHub-hosted runners) unless --gh names another command.
"""
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(gh, path, repo):
    p = subprocess.run(gh + ["attestation", "verify", str(path), "--repo", repo], capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def check(folder, repo, gh):
    folder = Path(folder)
    assets = sorted(p for p in folder.iterdir() if p.is_file())
    rows, problems = [], []
    if not assets:
        return rows, ["no assets in the folder"]
    if not any(p.name.endswith(".cdx.json") for p in assets):
        problems.append("no CycloneDX SBOM (*.cdx.json) among the assets")
    sums = folder / "SHA256SUMS"
    if not sums.is_file():
        problems.append("no SHA256SUMS among the assets")
    else:
        listed = {}
        for line in sums.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                listed[name.strip().lstrip("*")] = digest
        for p in assets:
            if p.name == "SHA256SUMS":
                continue
            if p.name not in listed:
                problems.append(f"{p.name}: not listed in SHA256SUMS")
            elif listed[p.name] != sha256(p):
                problems.append(f"{p.name}: SHA-256 differs from SHA256SUMS")
    for p in assets:
        ok, log = verify(gh, p, repo)
        rows.append({"asset": p.name, "sha256": sha256(p), "verdict": "verified" if ok else "FAILED"})
        if not ok:
            problems.append(f"{p.name}: gh attestation verify failed: {log[-300:]}")
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / ("tampered-" + assets[0].name)
        shutil.copyfile(assets[0], bad)
        data = bytearray(bad.read_bytes())
        if data:
            data[-1] ^= 0x01
        else:
            data = bytearray(b"\x00")
        bad.write_bytes(bytes(data))
        ok, _ = verify(gh, bad, repo)
        rows.append({"asset": bad.name, "sha256": sha256(bad), "verdict": "verified" if ok else "FAILED",
                     "planted_fault": "last byte of a copy of the first asset flipped; must fail"})
        if ok:
            problems.append("the tampered copy verified: the verification is not checking the digest")
    return rows, problems


STUB = """import hashlib, json, sys
allowed = set(json.load(open(sys.argv[1])))
path = sys.argv[4]
sys.exit(0 if hashlib.sha256(open(path, 'rb').read()).hexdigest() in allowed else 1)
"""


def self_test():
    """Runs the checks against a stub `gh` that accepts only digests on an allow-list, with planted faults."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def make(name, files, allow):
            d = tmp / name
            d.mkdir()
            for n, b in files.items():
                (d / n).write_bytes(b)
            if "SHA256SUMS" not in files:
                (d / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in files.items()),
                                              encoding="utf-8")
            digests = [hashlib.sha256((d / n).read_bytes()).hexdigest() for n in allow]
            (tmp / f"{name}.allow").write_text(json.dumps(digests), encoding="utf-8")
            (tmp / "stub.py").write_text(STUB, encoding="utf-8")
            return d, [sys.executable, str(tmp / "stub.py"), str(tmp / f"{name}.allow")]

        files = {"quantforge-cli-1.0.0.tar.gz": b"cli", "quantforge-1.0.0.cdx.json": b"{}"}
        d, gh = make("good", files, list(files) + ["SHA256SUMS"])
        if check(d, "o/r", gh)[1]:
            failures.append(f"good release reported problems: {check(d, 'o/r', gh)[1]}")
        cases = {
            "an asset with no attestation": make("unattested", files, ["quantforge-1.0.0.cdx.json", "SHA256SUMS"]),
            "no SBOM": make("nosbom", {"quantforge-cli-1.0.0.tar.gz": b"cli"}, ["quantforge-cli-1.0.0.tar.gz", "SHA256SUMS"]),
        }
        d2, gh2 = make("badsum", files, list(files) + ["SHA256SUMS"])
        (d2 / "quantforge-cli-1.0.0.tar.gz").write_bytes(b"cl1")
        cases["an asset that differs from SHA256SUMS"] = (d2, gh2)
        d3, _ = make("tamperpass", files, [])
        cases["a verifier that accepts anything (tampered copy passes)"] = (d3, [sys.executable, "-c", "import sys; sys.exit(0)"])
        for name, (folder, g) in cases.items():
            if not check(folder, "o/r", g)[1]:
                failures.append(f"planted fault not caught: {name}")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"self-test: the good release passes and {len(cases)} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    ap.add_argument("--repo", default="AshJha0/quantforge")
    ap.add_argument("--out")
    ap.add_argument("--gh", default="gh", help="the gh command (default gh)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.dir:
        ap.error("--dir or --self-test")
    rows, problems = check(a.dir, a.repo, shlex.split(a.gh))
    if a.out:
        Path(a.out).write_text(json.dumps({"repo": a.repo, "rows": rows, "problems": problems}, indent=1) + "\n",
                               encoding="utf-8")
    for r in rows:
        print(f"{r['verdict']:9} {r['asset']}")
    for p in problems:
        print(f"release-verify: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
