"""Stage H paper trading verbs (specifications/10-execution/paper-trading.md, HR-42 to HR-55).
Simulated only: no verb reaches a network or a venue (HR-42)."""

from typing import Any

from .inputs import Inputs
from .registry import core, op


def _opt(i: Inputs, key: str, default: Any = None) -> Any:
    return i.raw[key] if i.has(key) else default


@op("paper.book.apply_fill")
def paper_book_apply_fill(i: Inputs) -> Any:
    return core.paper.book_case(
        i.array("fills"), _opt(i, "cash"), _opt(i, "position", "0"), _opt(i, "avg_cost", "0")
    )


@op("paper.book.end_of_day")
def paper_book_end_of_day(i: Inputs) -> Any:
    return core.paper.day_case(
        _opt(i, "cash_open") if i.has("cash_open") else i.string("cash_open"),
        i.array("fills") if i.has("fills") else [],
        _opt(i, "position_open", "0"),
        _opt(i, "avg_cost_open"),
        _opt(i, "prev_close"),
        _opt(i, "close"),
        i.opt_integer("days", 1),
        _opt(i, "cash_rate", "0"),
        _opt(i, "debit_rate", "0"),
        _opt(i, "borrow_rate", "0"),
    )


@op("paper.pretrade.check")
def paper_pretrade_check(i: Inputs) -> Any:
    return core.paper.pretrade_case(
        dict(i.object("order").raw),
        _opt(i, "ref_price") if i.has("ref_price") else i.string("ref_price"),
        _opt(i, "position", "0"),
        i.string("cash"),
        i.opt_integer("orders_today", 0),
        dict(i.object("limits").raw),
    )


@op("paper.ledger.append")
def paper_ledger_append(i: Inputs) -> Any:
    return core.paper.record_case(
        i.integer("seq"),
        i.string("ts"),
        i.string("kind"),
        dict(i.object("body").raw),
        i.opt_string("prev") or "0" * 64,
    )


@op("paper.ledger.verify")
def paper_ledger_verify(i: Inputs) -> Any:
    return core.paper.verify_case(i.string("text"))


@op("paper.session.run")
def paper_session_run(i: Inputs) -> Any:
    return core.paper_fills.session_case(
        _opt(i, "cash") if i.has("cash") else i.string("cash"),
        dict(i.object("limits").raw),
        dict(i.object("lit").raw),
        i.array("script"),
        dict(i.object("dark").raw) if i.has("dark") else None,
    )
