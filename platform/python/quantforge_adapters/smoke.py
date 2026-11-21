"""K-3 smoke driver (adapters.md 1.3, 1.4): write, read back, compare one content hash, run the planted faults.

    python -m quantforge_adapters.smoke <adapter> --phase write|read|all [--out benchmarks/results/k3]

Exit codes: 0 PASS; 1 COUNT, HASH or BYPASS; 2 a planted fault did not give its verdict; 3 UNPINNED.
Containers run on GitHub Actions only (adapters.md SC-2); the workflow is .github/workflows/adapters.yml.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from quantforge_adapters import LABEL
from quantforge_adapters import adapters as ad
from quantforge_adapters.records import Record, Verdict, content_hash, load, verdict

ROOT = Path(__file__).resolve().parents[3]
RECORDS = ROOT / "datasets" / "adapters" / "records-10000.jsonl"
COMPOSE = ROOT / "platform" / "compose"
PINNED = re.compile(r"^\s*image:\s*[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}\s*$")
ADAPTERS = (
    "rest",
    "grpc",
    "arrow-ipc",
    "arrow-flight",
    "kafka",
    "postgres",
    "clickhouse",
    "prometheus",
    "aeron",
)
# Every planted fault and the verdict it must give (adapters.md 1.4). "bypass" needs a store count query.
PLANTS = {
    "drop": "COUNT",
    "duplicate": "COUNT",
    "byte": "HASH",
    "float": "HASH",
    "reorder": "PASS",
    "bypass": "BYPASS",
}


def check_pinned(compose_file: Path) -> list[str]:
    """Image digests of a compose file; raises Verdict(UNPINNED) on any image line that is not pinned."""
    digests = []
    for line in compose_file.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*image:", line):
            if not PINNED.match(line):
                raise Verdict("UNPINNED", f"{compose_file.name}: {line.strip()}")
            digests.append(line.split("image:", 1)[1].strip())
    return digests


def apply_plant(plant: str, rows: list[Record], count: int | None) -> tuple[list[Record], int | None]:
    rows = [json.loads(json.dumps(r)) for r in rows]
    if plant == "drop":
        del rows[len(rows) // 2]
    elif plant == "duplicate":
        rows.append(rows[len(rows) // 3])
    elif plant == "byte":
        r = rows[len(rows) // 2]
        body = r.get("body", r)
        key = next(k for k, v in sorted(body.items()) if isinstance(v, str))  # StopIteration: no string field
        body[key] = body[key][:-1] + ("0" if body[key][-1] != "0" else "1")
    elif plant == "float":
        r = rows[len(rows) // 4]
        target = r.get("body", r)
        target["value"] = math.nextafter(float(target["value"]), math.inf)
    elif plant == "reorder":
        rows[0], rows[-1] = rows[-1], rows[0]
    elif plant == "bypass":
        count = (count if count is not None else len(rows)) - 1
    else:
        raise ValueError(plant)
    return rows, count


def run_plants(sent: list[Record], read: list[Record], count: int | None) -> dict[str, str]:
    out = {}
    for plant, expected in PLANTS.items():
        if plant == "bypass" and count is None:
            out[plant] = "not applicable: no store count query"
            continue
        try:
            rows, c = apply_plant(plant, read, count)
        except StopIteration:
            out[plant] = "not applicable: the read records have no string field"
            continue
        try:
            got = verdict(sent, rows, store_count=c)
        except Verdict as v:
            got = v.code
        out[plant] = "ok" if got == expected else f"WRONG: gave {got}, expected {expected}"
    return out


def make(adapter: str, work: Path) -> ad.Adapter:
    env = os.environ.get
    if adapter == "rest":
        return ad.Rest(env("K3_REST_URL", "http://localhost:8080"))
    if adapter == "grpc":
        return ad.Grpc(env("K3_GRPC_TARGET", "localhost:50051"))
    if adapter == "arrow-ipc":
        return ad.ArrowIpc(work / "k3.arrow")
    if adapter == "arrow-flight":
        return ad.ArrowFlight(env("K3_FLIGHT_URL", "grpc://localhost:8815"))
    if adapter == "kafka":
        return ad.Kafka(env("K3_KAFKA", "localhost:9092"))
    if adapter == "postgres":
        return ad.Postgres(host=env("K3_PG_HOST", "localhost"))
    if adapter == "clickhouse":
        return ad.ClickHouse(env("K3_CH_URL", "http://localhost:8123"))
    if adapter == "prometheus":
        return ad.Prometheus(env("K3_PROM_URL", "http://localhost:9090"))
    if adapter == "aeron":
        return ad.Aeron(work / "aeron")
    raise SystemExit(f"unknown adapter {adapter}; one of {ADAPTERS}")


def smoke(a: ad.Adapter, phase: str, sent: list[Record], digests: list[str], out: Path | None) -> int:
    """The driver body, separate from main() so tests run it against in-process fakes."""
    started = time.monotonic()
    if phase in ("write", "all"):
        a.write(sent)
        if phase == "write":
            print(f"{a.name}: wrote {len(sent)}")
            return 0
    expected = ad.Prometheus.reduce(sent) if a.name == "prometheus" else sent
    read = a.read()
    count = a.count()
    try:
        result = verdict(expected, read, store_count=count)
    except Verdict as v:
        result = v.code
    plants = run_plants(expected, read, count) if result == "PASS" else {}
    doc: dict[str, Any] = {
        "adapter": a.name,
        "n_sent": len(sent),
        "n_read": len(read),
        "store_count": count,
        "verdict": result,
        "plants": plants,
        "image_digests": digests,
        "wall_s": round(time.monotonic() - started, 3),
        "host": os.environ.get("K3_HOST_LABEL", "GitHub Actions runner"),
        "label": LABEL,
    }
    try:
        doc["h_sent"] = content_hash(expected)
        doc["h_read"] = content_hash(read)
    except Verdict:
        doc["h_read"] = None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{a.name}.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("adapter", "n_read", "store_count", "verdict", "plants")}))
    if result != "PASS":
        return 1
    return 2 if any(v != "ok" and not v.startswith("not applicable") for v in plants.values()) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("adapter", choices=ADAPTERS)
    ap.add_argument("--phase", choices=("write", "read", "all"), default="all")
    ap.add_argument("--records", type=Path, default=RECORDS)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmarks" / "results" / "k3")
    ap.add_argument("--work", type=Path, default=ROOT / "platform" / "compose" / "work")
    a = ap.parse_args(argv)
    compose = COMPOSE / a.adapter.split("-")[0] / "compose.yaml"
    try:
        digests = check_pinned(compose) if compose.exists() else []
    except Verdict as v:
        print(v)
        return 3
    a.work.mkdir(parents=True, exist_ok=True)  # a fresh checkout has no work directory (first CI run, PR #62)
    return smoke(make(a.adapter, a.work), a.phase, load(a.records), digests, a.out)


if __name__ == "__main__":
    sys.exit(main())
