"""Prometheus exporter for the K-3 smoke: 10,000 gauges k3_value{seq="n"} = record body value.

Values are written with Python repr (the shortest string that round-trips to the same binary64).

    python -m quantforge_adapters.services.exporter --records datasets/adapters/records-10000.jsonl [--port 9108]
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quantforge_adapters.records import Record, load


def exposition(rows: list[Record]) -> bytes:
    lines = ["# HELP k3_value K-3 round-trip value (simulated)", "# TYPE k3_value gauge"]
    lines += [f'k3_value{{seq="{r["seq"]}"}} {float(r["body"]["value"])!r}' for r in rows]
    return ("\n".join(lines) + "\n").encode("ascii")


def make_server(rows: list[Record], host: str = "0.0.0.0", port: int = 9108) -> ThreadingHTTPServer:
    body = exposition(rows)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            ok = self.path == "/metrics"
            data = body if ok else b"not found\n"
            self.send_response(200 if ok else 404)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--port", type=int, default=9108)
    a = ap.parse_args()
    make_server(load(a.records), port=a.port).serve_forever()


if __name__ == "__main__":
    main()
