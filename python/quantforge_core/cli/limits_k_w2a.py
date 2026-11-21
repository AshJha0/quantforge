"""Input sizes of the stage K wave 2 lane A verbs whose lists exceed the generic MAX_ARRAY (KR-67).

`check` runs at the gate, after every E_SCHEMA check and before the finite rule (HR-122 order). It
returns True when it has handled the operation (the generic array caps are then skipped), False to
leave the operation to the generic caps of limits.py. Hooked into `limits.check_limits` by the
coordinator: program/STAGE_K_W2A_HANDOVER.md."""

from collections.abc import Mapping
from typing import Any

from ..errors import QfError

MAX_PNL = 1_000_000  # KR-67: P&L points per list
MAX_LIST = 100_000  # KR-67: everything else


def _over(key: str, limit: int) -> QfError:
    return QfError("E_LIMIT", f"{key} is above its limit of {limit}", key)


def _cap(raw: Mapping[str, Any], key: str, limit: int) -> None:
    value = raw.get(key)
    if isinstance(value, list) and len(value) > limit:
        raise _over(key, limit)


def check(operation: str, raw: Mapping[str, Any]) -> bool:
    if operation == "risk.frtb.pla":
        _cap(raw, "hpl", MAX_PNL)
        _cap(raw, "rtpl", MAX_PNL)
        return True
    if operation == "risk.frtb.ima.es_lh":
        _cap(raw, "es_t", MAX_LIST)
        _cap(raw, "sigma", MAX_LIST)
        _cap(raw, "pnl", MAX_LIST)
        for k, lst in enumerate(raw.get("pnl") or []):
            if isinstance(lst, list) and len(lst) > MAX_PNL:
                raise _over(f"pnl/{k}", MAX_PNL)
        return True
    return False
