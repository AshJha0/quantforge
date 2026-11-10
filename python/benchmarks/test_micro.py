"""Microbenchmarks: bootstrap, swap_pv, implied_vol (ids match the other languages)."""

import json
from datetime import date
from pathlib import Path

from quantforge_core import black, ois

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "ois_bootstrap_sofr.json"


def _inputs():
    i = json.loads(EXAMPLE.read_text())["inputs"]
    quotes = [ois.Quote(q["tenor"], q["rate"]) for q in i["quotes"]]
    return i["convention"], date.fromisoformat(i["as_of"]), quotes, i["interpolation"], i["method"]


def test_bootstrap(qf_bench):
    conv, as_of, quotes, interp, method = _inputs()
    qf_bench("bootstrap", lambda: ois.bootstrap(conv, as_of, quotes, interp, method))


def test_swap_pv(qf_bench):
    conv, as_of, quotes, interp, method = _inputs()
    data, _ = ois.bootstrap(conv, as_of, quotes, interp, method)
    trade = ois.OisTrade(conv, "5Y", 0.035, 10_000_000.0, "PAY")
    qf_bench("swap_pv", lambda: ois.pv(data, trade))


def test_implied_vol(qf_bench):
    o = black.Option(black.BLACK_76, "CALL", 105.0, 1.0, 100.0, discount_factor=1.0)
    target = black.price(o, 0.2)
    assert abs(black.implied(o, target) - 0.2) < 1e-8
    qf_bench("implied_vol", lambda: black.implied(o, target))
