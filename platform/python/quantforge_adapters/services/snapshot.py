"""The `core.snapshot.hash` behaviour served by the REST and gRPC services (KR-283).

Same result as quantforge_core.snapshot.hash_document for the documents the smoke sends (JSON objects): the
canonical form without a top-level snapshot_id key, and "sha256:" + its SHA-256.
"""

import hashlib
import json
from typing import Any

from quantforge_adapters.records import canonical


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def hash_document(text: str) -> tuple[str, str]:
    doc = json.loads(text, parse_constant=_reject_constant)
    if not isinstance(doc, dict):
        raise ValueError("the top level is not an object")
    form = canonical({k: v for k, v in doc.items() if k != "snapshot_id"})
    return form, "sha256:" + hashlib.sha256(form.encode("utf-8")).hexdigest()
