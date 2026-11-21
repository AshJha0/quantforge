# K-3 adapters and simulated feeds: developer guide

Everything on this page is simulated; not a certified implementation; not connected to any venue. Spec: [`specifications/12-platform/adapters.md`](../../specifications/12-platform/adapters.md) (0.2.0). Rulings: [`specifications/stage-k-rulings-k3.md`](../../specifications/stage-k-rulings-k3.md) (KR-270 to KR-283, confirmed 2026-11-20). Open items: [known issues](../known-issues.md), rows KI-K3-*.

## What is here and why

The numerical libraries compute. An adapter carries their inputs and outputs through a piece of infrastructure: a message bus, a database, a metrics store. Its test is a round trip: write the 10,000 records of `datasets/adapters/records-10000.jsonl`, read them back, and compare one SHA-256 over their canonical form. The feed codecs are tested at the byte level against fixtures built by hand from the spec. Both live outside the library trees (ADR-0006: services last), and a repo gate shows that no library imports them.

| You want to | Look at |
|---|---|
| decode or encode a simulated feed message | `platform/python/quantforge_adapters/feeds/` (`fix`, `itch`, `ouch`, `fast`, `mold`) |
| see the bytes and how they were derived | `datasets/feeds/<format>/<name>.bin` and `.json`; spec section 3 |
| run a round trip | `python -m quantforge_adapters.smoke <adapter>`; spec section 1.3 |
| change an image | `platform/compose/images.lock` first, then the compose file; spec section 2.1 |
| see what CI runs | `.github/workflows/adapters.yml` |

## Running the local tests (Windows or Linux, no Docker)

The adapter package is a separate distribution (`platform/python/pyproject.toml`). The quickest way to run its tests is from the library environment, which already has `pytest` and `hypothesis`:

```
cd python
export PYTHONUTF8=1 PYTHONPATH=../platform/python
uv run --with pyarrow==26.0.1 python -m pytest -q ../platform/python/tests
```

On 2026-11-20 this gave 115 passed in 132 s (measured; local laptop, not the acceptance machine). Without `--with pyarrow` the two Arrow tests are skipped. The two tests that compare with the library (`test_canonical_matches_the_library`, `test_records_regenerate_from_the_library_rng`) need the library environment; in CI's Python 3.13 environment they are skipped and the job says so.

Lint and types, from `platform/python`: `uv run --project ../../python python -m ruff check .`, `... ruff format --check .`, `... mypy quantforge_adapters` (strict).

What the local tests cover and what they do not: every codec, the records and the hash, the planted faults, the smoke driver's logic, the REST, Flight and Prometheus-exporter services run in process, and fakes standing in for PostgreSQL, ClickHouse, Kafka and the gRPC transport. They do not start any container. The container runs exist only in GitHub Actions and are **untested until the first run of `adapters.yml`** (KI-K3-CI).

## Decoding a fixture: a worked example

Plain idea: a QF-ITCH-S Add Order is 36 bytes at fixed offsets, so decoding is slicing.

```python
from pathlib import Path
from quantforge_adapters.feeds import itch
msg = itch.decode(Path("datasets/feeds/itch/add_order_1.bin").read_bytes())
# {'type': 'A', 'locate': 1, 'tracking': 0, 'timestamp': 34200000000000, 'order_ref': 1,
#  'side': 'B', 'shares': 100, 'stock': 'QFSIM   ', 'price': 1012500}
assert itch.encode(msg) == Path("datasets/feeds/itch/add_order_1.bin").read_bytes()
```

The timestamp is bytes 5 to 10, `1f 1a ce d9 f0 00` = 34,200,000,000,000 ns = 09:30:00; the price is bytes 32 to 35, `00 0f 73 14` = 1,012,500 = 101.2500 with four implied decimals (spec 3.2). Change byte 19 (the side) to `Q` and `decode` raises `FeedError` with code `E_FIELD`; cut the message to 35 bytes and the code is `E_TRUNCATED`. Decoders raise nothing but `FeedError`, and every encoding is canonical: anything that decodes re-encodes to the same bytes (KR-276), which the fuzz tests check on 12,000 mutated inputs per run.

## How CI runs the containers

`adapters.yml` runs on pull requests that touch `platform/**`, the feed or record datasets, `tools/adapters/**` or the workflow itself; weekly on Tuesday at 04:41 UTC; and by hand. Jobs:

| Job | What it does |
|---|---|
| `adapters-codecs` | fixtures current; all local tests with `pyarrow`; ruff; mypy |
| `libraries-without-services` | `tools/check_adapter_deps.py` after its planted faults; the Python library installed with `uv sync --locked` and every `quantforge_core` module imported, with no adapter module loaded; the Java library packaged |
| `adapter-smoke-<adapter>` (9) | `docker compose up --wait`; write; for Kafka, PostgreSQL and ClickHouse restart the store; read; hash; planted faults; result file uploaded as an artefact |
| `adapter-smoke-multicast` | sender and two listeners on a bridge network; then the same with packet 37 dropped, which must be reported as the gap `[361, 370]` |

A result file `benchmarks/results/k3/<adapter>.json` holds `n_sent`, `n_read`, `store_count`, `h_sent`, `h_read`, the verdict, the planted-fault outcomes and the image digests. The driver exits 0 only on `PASS` with every planted fault giving its expected verdict.

## Adding an adapter

1. Read the image's licence on the project's own page; record the URL and date in spec section 2.1. Read its index digest from the registry and add `name:tag@sha256:...` to `images.lock` in its own commit.
2. Write `platform/compose/<name>/compose.yaml` with a health check, ports bound to `127.0.0.1`, and the pinned reference.
3. Add a class with `write`, `read`, `count` to `adapters.py`, taking its client as an argument; add it to `smoke.make` and `ADAPTERS`.
4. Add a fake-backed test to `tests/test_adapters.py` that runs `smoke.smoke` end to end, and the adapter to the workflow matrix.
5. Update the spec table, the known-issues rows and the CHANGELOG.

## Limits

- A round trip proves the bytes survive the store, not how it behaves under load or failure (that is K-6).
- Prometheus carries a reduced record `{seq, value}`; its hash covers that reduction only.
- UDP multicast can drop packets on a busy runner; a drop is a fail, reported as a gap, never hidden.
- The formats are not any venue's or standard's; a test passing here says nothing about a real gateway.
