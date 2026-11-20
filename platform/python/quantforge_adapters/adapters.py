"""K-3 adapters (adapters.md 2.2): each writes the 10,000 records into one piece of infrastructure and reads
them back. Client libraries are imported lazily, and every adapter takes its client (or HTTP function) as an
argument so the non-container logic is unit-tested with in-process fakes (tests/test_adapters.py).

Simulated; not a certified implementation; not connected to any venue.
"""

import base64
import io
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from quantforge_adapters.records import Record, canon, canonical, from_canon, snapshot_id

Http = Callable[[str, str, bytes | None, dict[str, str]], bytes]


def urllib_http(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (URLs are the compose services)
        data: bytes = resp.read()
        return data


class Adapter(Protocol):
    name: str

    def write(self, rows: list[Record]) -> None: ...

    def read(self) -> list[Record]: ...

    def count(self) -> int | None: ...


def json_text(r: Record) -> str:
    """The document the REST and gRPC services receive: JSON text (the canonical form is not JSON)."""
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


class SnapshotMismatch(Exception):
    pass


# ---- REST and gRPC: the service is the store (no restart; phase "all") -------------------------------------

class Rest:
    name = "rest"

    def __init__(self, base: str, http: Http = urllib_http) -> None:
        self.base, self.http = base.rstrip("/"), http
        self.got: list[Record] = []

    def write(self, rows: list[Record]) -> None:
        self.got = []
        for r in rows:
            body = json.dumps({"document_text": json_text(r)}).encode()
            resp = json.loads(self.http("POST", self.base + "/v1/run", body, {"Content-Type": "application/json"}))
            if resp["snapshot_id"] != snapshot_id(r):
                raise SnapshotMismatch(f"seq {r['seq']}: {resp['snapshot_id']}")
            self.got.append(from_canon(resp["canonical"]))

    def read(self) -> list[Record]:
        return self.got

    def count(self) -> int | None:
        return None


class Grpc:
    name = "grpc"

    def __init__(self, target: str, channel: Any = None) -> None:
        if channel is None:
            import grpc

            channel = grpc.insecure_channel(target)
        self.call = channel.unary_unary("/qf.k3.Run/Run")
        self.got: list[Record] = []

    def write(self, rows: list[Record]) -> None:
        self.got = []
        for r in rows:
            sid, _, form = bytes(self.call(json_text(r).encode(), timeout=30)).decode().partition("\n")
            if sid != snapshot_id(r):
                raise SnapshotMismatch(f"seq {r['seq']}: {sid}")
            self.got.append(from_canon(form))

    def read(self) -> list[Record]:
        return self.got

    def count(self) -> int | None:
        return None


# ---- Arrow ------------------------------------------------------------------------------------------------

def _to_table(rows: list[Record]) -> Any:
    import pyarrow as pa

    return pa.table({"seq": pa.array([r["seq"] for r in rows], pa.int64()),
                     "kind": pa.array([r["kind"] for r in rows], pa.utf8()),
                     "body": pa.array([canonical(r["body"]) for r in rows], pa.utf8())})


def _from_table(table: Any) -> list[Record]:
    cols = table.to_pydict()
    return [{"seq": s, "kind": k, "body": from_canon(b)} for s, k, b in zip(cols["seq"], cols["kind"], cols["body"],
                                                                          strict=True)]


class ArrowIpc:
    name = "arrow-ipc"

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, rows: list[Record]) -> None:
        import pyarrow as pa

        table = _to_table(rows)
        with pa.OSFile(str(self.path), "wb") as sink, pa.ipc.new_file(sink, table.schema) as w:
            w.write_table(table)

    def read(self) -> list[Record]:
        import pyarrow as pa

        with pa.memory_map(str(self.path), "r") as src:
            return _from_table(pa.ipc.open_file(src).read_all())

    def count(self) -> int | None:
        import pyarrow as pa

        with pa.memory_map(str(self.path), "r") as src:
            return int(pa.ipc.open_file(src).read_all().num_rows)


class ArrowFlight:
    name = "arrow-flight"
    KEY = b"k3"

    def __init__(self, location: str, client: Any = None) -> None:
        if client is None:
            import pyarrow.flight as fl

            client = fl.connect(location)
        self.client = client

    def write(self, rows: list[Record]) -> None:
        import pyarrow.flight as fl

        table = _to_table(rows)
        writer, _ = self.client.do_put(fl.FlightDescriptor.for_path(self.KEY), table.schema)
        writer.write_table(table)
        writer.close()

    def read(self) -> list[Record]:
        import pyarrow.flight as fl

        return _from_table(self.client.do_get(fl.Ticket(self.KEY)).read_all())

    def count(self) -> int | None:
        return None


# ---- Kafka ------------------------------------------------------------------------------------------------

class Kafka:
    name = "kafka"
    TOPIC = "k3"

    def __init__(self, bootstrap: str, producer: Any = None, consumer_factory: Any = None) -> None:
        self.bootstrap = bootstrap
        self.producer = producer
        self.consumer_factory = consumer_factory

    def _consumer(self) -> Any:
        if self.consumer_factory is not None:
            return self.consumer_factory()
        from kafka import KafkaConsumer, TopicPartition

        c = KafkaConsumer(bootstrap_servers=self.bootstrap, enable_auto_commit=False, consumer_timeout_ms=10_000)
        tp = TopicPartition(self.TOPIC, 0)
        c.assign([tp])
        c.seek_to_beginning(tp)
        return c

    def write(self, rows: list[Record]) -> None:
        producer = self.producer
        if producer is None:
            from kafka import KafkaProducer

            producer = KafkaProducer(bootstrap_servers=self.bootstrap, acks="all", linger_ms=5)
        for r in rows:
            producer.send(self.TOPIC, key=str(r["seq"]).encode(), value=canon(r), partition=0)
        producer.flush()

    def read(self) -> list[Record]:
        consumer = self._consumer()
        out: list[Record] = []
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            batch = consumer.poll(timeout_ms=1000)
            for msgs in batch.values():
                out += [from_canon(m.value) for m in msgs]
            if not batch and out:
                break
        consumer.close()
        return out

    def count(self) -> int | None:
        consumer = self._consumer()
        n = int(consumer.end_offsets(list(consumer.assignment())).popitem()[1])
        consumer.close()
        return n


# ---- PostgreSQL -------------------------------------------------------------------------------------------

class Postgres:
    name = "postgres"
    CREATE = "CREATE TABLE IF NOT EXISTS k3 (seq bigint PRIMARY KEY, kind text NOT NULL, body jsonb NOT NULL)"

    def __init__(self, connect: Callable[[], Any] | None = None, host: str = "localhost", port: int = 5432) -> None:
        if connect is None:
            def connect() -> Any:
                import pg8000.native

                return pg8000.native.Connection("k3", host=host, port=port, password="k3", database="k3")
        self.connect = connect

    @staticmethod
    def copy_payload(rows: list[Record]) -> str:
        """CSV for COPY: the body is canonical JSON text with numbers written back as JSON numbers."""
        buf = io.StringIO()
        for r in rows:
            body = json.dumps(r["body"], sort_keys=True, separators=(",", ":")).replace('"', '""')
            buf.write(f'{r["seq"]},{r["kind"]},"{body}"\n')
        return buf.getvalue()

    def write(self, rows: list[Record]) -> None:
        con = self.connect()
        con.run(self.CREATE)
        con.run("TRUNCATE k3")
        con.run("COPY k3 (seq, kind, body) FROM STDIN WITH (FORMAT csv)", stream=io.StringIO(self.copy_payload(rows)))
        con.close()

    def read(self) -> list[Record]:
        con = self.connect()
        rows = con.run("SELECT seq, kind, body::text FROM k3 ORDER BY seq")
        con.close()
        return [{"seq": int(s), "kind": k, "body": json.loads(b)} for s, k, b in rows]

    def count(self) -> int | None:
        con = self.connect()
        n = int(con.run("SELECT count(*) FROM k3")[0][0])
        con.close()
        return n


# ---- ClickHouse (HTTP interface, standard library) --------------------------------------------------------

class ClickHouse:
    name = "clickhouse"

    def __init__(self, url: str = "http://localhost:8123", user: str = "k3", password: str = "k3",
                 http: Http = urllib_http) -> None:
        self.url, self.http = url.rstrip("/"), http
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def q(self, sql: str, body: bytes | None = None) -> bytes:
        return self.http("POST", self.url + "/?query=" + urllib.parse.quote(sql), body, self.headers)

    def write(self, rows: list[Record]) -> None:
        self.q("CREATE TABLE IF NOT EXISTS k3 (seq UInt64, kind String, body String) ENGINE = MergeTree ORDER BY seq")
        self.q("TRUNCATE TABLE k3")
        payload = "".join(json.dumps({"seq": r["seq"], "kind": r["kind"], "body": canonical(r["body"])}) + "\n"
                          for r in rows).encode()
        self.q("INSERT INTO k3 FORMAT JSONEachRow", payload)

    def read(self) -> list[Record]:
        text = self.q("SELECT seq, kind, body FROM k3 ORDER BY seq FORMAT JSONEachRow").decode()
        out = []
        for line in text.splitlines():
            row = json.loads(line)
            out.append({"seq": int(row["seq"]), "kind": row["kind"], "body": from_canon(row["body"])})
        return out

    def count(self) -> int | None:
        return int(self.q("SELECT count() FROM k3").decode().strip())


# ---- Prometheus (HTTP API, standard library) --------------------------------------------------------------

class Prometheus:
    """Reduced records {seq, value} (adapters.md 2.2); the exporter is a compose service, so write is a no-op."""

    name = "prometheus"

    def __init__(self, url: str = "http://localhost:9090", http: Http = urllib_http, wait_s: float = 120) -> None:
        self.url, self.http, self.wait_s = url.rstrip("/"), http, wait_s

    @staticmethod
    def reduce(rows: list[Record]) -> list[Record]:
        return [{"seq": r["seq"], "value": float(r["body"]["value"])} for r in rows]

    def _query(self, expr: str) -> list[Any]:
        data = json.loads(self.http("GET", f"{self.url}/api/v1/query?query={urllib.parse.quote(expr)}", None, {}))
        if data.get("status") != "success":
            raise RuntimeError(f"query failed: {data}")
        result: list[Any] = data["data"]["result"]
        return result

    def write(self, rows: list[Record]) -> None:
        return

    def read(self) -> list[Record]:
        deadline = time.monotonic() + self.wait_s
        result = self._query("k3_value")
        while len(result) < 10_000 and time.monotonic() < deadline:
            time.sleep(2)
            result = self._query("k3_value")
        return [{"seq": int(s["metric"]["seq"]), "value": float(s["value"][1])} for s in result]

    def count(self) -> int | None:
        result = self._query("count(k3_value)")
        return int(float(result[0]["value"][1])) if result else 0


# ---- Aeron: the Java publisher and subscriber exchange files with the driver -------------------------------

class Aeron:
    """write: the canonical lines the Java publisher sends; read: the lines the Java subscriber received."""

    name = "aeron"

    def __init__(self, work: Path) -> None:
        self.work = work

    def write(self, rows: list[Record]) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        (self.work / "send.txt").write_bytes(b"".join(canon(r) + b"\n" for r in rows))

    def read(self) -> list[Record]:
        data = (self.work / "received.txt").read_bytes()
        return [from_canon(line) for line in data.split(b"\n") if line]

    def count(self) -> int | None:
        return None
