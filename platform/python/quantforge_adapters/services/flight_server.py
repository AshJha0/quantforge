"""Arrow Flight service for the K-3 smoke: keeps each uploaded table in memory by descriptor path.

python -m quantforge_adapters.services.flight_server [--port 8815]
"""

import argparse
from typing import Any


def make_server(location: str) -> Any:
    import pyarrow.flight as fl

    class Server(fl.FlightServerBase):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__(location)
            self.tables: dict[bytes, Any] = {}

        def do_put(self, context: Any, descriptor: Any, reader: Any, writer: Any) -> None:
            self.tables[descriptor.path[0]] = reader.read_all()

        def do_get(self, context: Any, ticket: Any) -> Any:
            return fl.RecordBatchStream(self.tables[ticket.ticket])

    return Server()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8815)
    make_server(f"grpc://0.0.0.0:{ap.parse_args().port}").serve()


if __name__ == "__main__":
    main()
