"""The non-container logic of every K-3 adapter, against in-process fakes (adapters.md 1.3, 1.4, 2.2, 3.5).

The real stores run only in .github/workflows/adapters.yml on GitHub Actions (SC-2); these tests show that the
driver, the mappings back to records, the hash and the planted faults behave, and nothing more.
"""

import csv
import io
import json
import threading
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quantforge_adapters import adapters as ad
from quantforge_adapters import multicast, smoke
from quantforge_adapters.records import Record, Verdict, load
from quantforge_adapters.services import exporter, grpc_server, rest_server

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "platform" / "compose"


@pytest.fixture(scope="module")
def rows() -> list[Record]:
    return load(ROOT / "datasets" / "adapters" / "records-10000.jsonl")


def _run(a: ad.Adapter, rows: list[Record], tmp_path: Path) -> dict[str, Any]:
    assert smoke.smoke(a, "all", rows, [], tmp_path) == 0
    doc: dict[str, Any] = json.loads((tmp_path / f"{a.name}.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "PASS" and doc["h_sent"] == doc["h_read"] and doc["n_read"] == 10_000
    assert all(v == "ok" or v.startswith("not applicable") for v in doc["plants"].values()), doc["plants"]
    return doc


def test_rest_against_the_real_service_in_process(rows: list[Record], tmp_path: Path) -> None:
    server = rest_server.make_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        _run(ad.Rest(f"http://127.0.0.1:{server.server_address[1]}"), rows, tmp_path)
    finally:
        server.shutdown()


def test_rest_service_rejects_bad_input() -> None:
    server = rest_server.make_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/run"
    try:
        for body in (b'{"document_text": "[1]"}', b'{"x": 1}', b'{"document_text": "{\\"a\\": NaN}"}'):
            req = urllib.request.Request(url, data=body, method="POST")
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(req)
            assert err.value.code == 400
    finally:
        server.shutdown()


class FakeChannel:
    def unary_unary(self, path: str) -> Any:
        assert path == "/qf.k3.Run/Run"
        return lambda req, timeout: grpc_server.handle(req)


def test_grpc_with_the_real_handler(rows: list[Record], tmp_path: Path) -> None:
    _run(ad.Grpc("unused", channel=FakeChannel()), rows, tmp_path)


def test_snapshot_mismatch_is_caught(rows: list[Record]) -> None:
    class Wrong:
        def unary_unary(self, path: str) -> Any:
            return lambda req, timeout: b"sha256:00\n" + req

    with pytest.raises(ad.SnapshotMismatch):
        ad.Grpc("unused", channel=Wrong()).write(rows[:1])


class FakeClickHouse:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, body: bytes | None, headers: dict[str, str]) -> bytes:
        assert headers["Authorization"].startswith("Basic ")
        sql = urllib.parse.unquote(url.split("?query=", 1)[1])
        if sql.startswith("INSERT"):
            self.rows = [json.loads(line) for line in (body or b"").decode().splitlines()]
        elif sql.startswith("TRUNCATE"):
            self.rows = []
        elif sql.startswith("SELECT count()"):
            return f"{len(self.rows)}\n".encode()
        elif sql.startswith("SELECT"):
            # ClickHouse quotes 64-bit integers in JSON output by default.
            return "".join(json.dumps({**r, "seq": str(r["seq"])}) + "\n"
                           for r in sorted(self.rows, key=lambda r: r["seq"])).encode()
        return b""


def test_clickhouse_with_a_fake_http_interface(rows: list[Record], tmp_path: Path) -> None:
    _run(ad.ClickHouse(http=FakeClickHouse()), rows, tmp_path)


def _go_float(text: str) -> str:
    """Prometheus writes sample values like Go strconv.FormatFloat(v, 'f', -1, 64): no exponent."""
    out = format(Decimal(repr(float(text))), "f")
    return out


def test_prometheus_with_the_real_exporter_and_a_fake_query_api(rows: list[Record], tmp_path: Path) -> None:
    server = exporter.make_server(rows, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    metrics = f"http://127.0.0.1:{server.server_address[1]}/metrics"

    def fake(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> bytes:
        text = urllib.request.urlopen(metrics).read().decode()
        series = []
        for line in text.splitlines():
            if line.startswith("k3_value{"):
                labels, value = line.rsplit(" ", 1)
                series.append({"metric": {"__name__": "k3_value", "seq": labels.split('"')[1]},
                               "value": [1.0, _go_float(value)]})
        expr = urllib.parse.unquote(url.split("query=", 1)[1])
        result = [{"metric": {}, "value": [1.0, str(len(series))]}] if expr.startswith("count(") else series
        return json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}}).encode()

    try:
        _run(ad.Prometheus(http=fake, wait_s=0), rows, tmp_path)
    finally:
        server.shutdown()


class FakePg:
    """Stores COPY rows; returns body::text the way jsonb prints it (its own key order, ', ' and ': ')."""

    table: dict[int, tuple[str, str]] = {}

    def run(self, sql: str, stream: Any = None) -> Any:
        if sql.startswith("TRUNCATE"):
            FakePg.table = {}
        elif sql.startswith("COPY"):
            for seq, kind, body in csv.reader(io.StringIO(stream.read())):
                obj = json.loads(body)
                keys = sorted(obj, key=lambda k: (len(k), k))  # jsonb orders keys by length, then bytes
                FakePg.table[int(seq)] = (kind, "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(obj[k])}"
                                                                   for k in keys) + "}")
        elif sql.startswith("SELECT count"):
            return [[len(FakePg.table)]]
        elif sql.startswith("SELECT"):
            return [[s, k, b] for s, (k, b) in sorted(FakePg.table.items())]
        return []

    def close(self) -> None:
        return


def test_postgres_with_a_fake_connection(rows: list[Record], tmp_path: Path) -> None:
    _run(ad.Postgres(connect=FakePg), rows, tmp_path)


class FakeKafka:
    def __init__(self) -> None:
        self.log: list[Any] = []
        self.polled = False

    def send(self, topic: str, key: bytes, value: bytes, partition: int) -> None:
        assert topic == "k3" and partition == 0
        self.log.append(type("M", (), {"key": key, "value": value})())

    def flush(self) -> None:
        return

    def consumer(self) -> Any:
        log = self.log

        class C:
            done = False

            def poll(self, timeout_ms: int) -> dict[str, list[Any]]:
                if C.done:
                    return {}
                C.done = True
                return {"tp": list(log)}

            def assignment(self) -> list[str]:
                return ["tp"]

            def end_offsets(self, tps: list[str]) -> dict[str, int]:
                return {"tp": len(log)}

            def close(self) -> None:
                return

        return C()


def test_kafka_with_a_fake_broker(rows: list[Record], tmp_path: Path) -> None:
    fk = FakeKafka()
    _run(ad.Kafka("unused", producer=fk, consumer_factory=fk.consumer), rows, tmp_path)


def test_aeron_file_exchange(rows: list[Record], tmp_path: Path) -> None:
    a = ad.Aeron(tmp_path / "aeron")
    a.write(rows)
    # Stand-in for the Java publisher and subscriber: the subscriber writes the payloads it received.
    (tmp_path / "aeron" / "received.txt").write_bytes((tmp_path / "aeron" / "send.txt").read_bytes())
    assert smoke.smoke(a, "read", rows, [], tmp_path) == 0


def test_arrow_ipc(rows: list[Record], tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    _run(ad.ArrowIpc(tmp_path / "k3.arrow"), rows, tmp_path)


def test_failing_store_gives_count_and_exit_1(rows: list[Record], tmp_path: Path) -> None:
    fk = FakeKafka()
    a = ad.Kafka("unused", producer=fk, consumer_factory=fk.consumer)
    a.write(rows)
    fk.log.pop()
    assert smoke.smoke(a, "read", rows, [], tmp_path) == 1
    assert json.loads((tmp_path / "kafka.json").read_text())["verdict"] == "COUNT"


# ---- compose files and the image lock ----------------------------------------------------------------------

def test_unpinned_image_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "compose.yaml"
    f.write_text("services:\n  db:\n    image: postgres:17\n", encoding="utf-8")
    with pytest.raises(Verdict) as err:
        smoke.check_pinned(f)
    assert err.value.code == "UNPINNED"


def test_every_compose_file_is_pinned_to_the_lock() -> None:
    lock = {}
    for line in (COMPOSE / "images.lock").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            ref = line.split()[0]
            lock[ref.split("@")[0]] = ref
    files = sorted(COMPOSE.glob("*/compose.yaml"))
    assert len(files) == 9
    for f in files:
        for ref in smoke.check_pinned(f):
            assert lock.get(ref.split("@")[0]) == ref, (f, ref)


# ---- multicast, in process ---------------------------------------------------------------------------------

def test_multicast_in_process(rows: list[Record]) -> None:
    results = multicast.run_in_process(rows)
    assert multicast.judge(multicast.sender_hash(rows), results, None) == "PASS"
    assert results[0]["h_bytes"] == results[1]["h_bytes"]


def test_multicast_planted_drop_is_one_gap(rows: list[Record]) -> None:
    results = multicast.run_in_process(rows, drop_packet=37)
    assert results[0]["gaps"] == [(361, 370)]
    assert multicast.judge(multicast.sender_hash(rows), results, 37) == "PASS"
    assert multicast.judge(multicast.sender_hash(rows), results, None).startswith("FAIL")
