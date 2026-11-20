"""gRPC service for the K-3 smoke: unary /qf.k3.Run/Run, raw bytes in and out (no .proto; generic handler).

Request: the record as UTF-8 JSON text. Response: snapshot_id, LF, canonical form.

    python -m quantforge_adapters.services.grpc_server [--port 50051]
"""

import argparse
from concurrent import futures
from typing import Any

from quantforge_adapters.services.snapshot import hash_document

SERVICE, METHOD = "qf.k3.Run", "Run"


def handle(request: bytes, context: Any = None) -> bytes:
    form, sid = hash_document(request.decode("utf-8"))
    return (sid + "\n" + form).encode("utf-8")


def main() -> None:
    import grpc

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=50051)
    port = ap.parse_args().port
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    handler = grpc.method_handlers_generic_handler(
        SERVICE, {METHOD: grpc.unary_unary_rpc_method_handler(handle)}
    )
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
