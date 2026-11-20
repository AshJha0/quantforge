"""REST service for the K-3 smoke: POST /v1/run {"document_text": ...} -> {"canonical", "snapshot_id"}.

python -m quantforge_adapters.services.rest_server [--port 8080]
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from quantforge_adapters.services.snapshot import hash_document

MAX_BODY = 1 << 20


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/run":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY:
            self._send(413, {"error": "body size"})
            return
        try:
            req = json.loads(self.rfile.read(length))
            form, sid = hash_document(req["document_text"])
        except (ValueError, KeyError, TypeError) as exc:
            self._send(400, {"error": str(exc)[:200]})
            return
        self._send(200, {"canonical": form, "snapshot_id": sid})

    def log_message(self, format: str, *args: object) -> None:
        return


def make_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    make_server(port=ap.parse_args().port).serve_forever()


if __name__ == "__main__":
    main()
