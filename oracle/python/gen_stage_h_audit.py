"""Stage H audit goldens (`rule_h`): the behaviours the different-model audit of 2026-11-19 found unstated
or stated two ways, pinned for all four builds. Rulings HR-121 to HR-129,
`specifications/stage-h-rulings-audit.md`.

Every expected value is written here by hand from the ruling, or computed below with mpmath from the
formula; none is taken from an implementation. Value cases marked blind were re-derived by a second model
from the rules and inputs only (packets 3 and 4, 2026-11-19, `program/STAGE_H_BLIND_AUDIT.md`).

    cd oracle/python && uv run python -W ignore gen_stage_h_audit.py
"""
import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite

G = "oracle/python/gen_stage_h_audit.py"
SPEC = "specifications/stage-h-rulings-audit.md"
REC = "program/STAGE_H_BLIND_AUDIT.md"
mp.mp.dps = 60


def blind(packet):
    return ["hand", f"blind-rederivation (DR-H2, {REC}, packet {packet}): MATCH"]


LIT_LABEL = "simulated venue; not a real exchange"
DARK_LABEL = "simulated venue; not a real dark pool"
AC = {"quantity": 1000000.0, "horizon": 5.0, "n_steps": 5, "sigma": 0.95, "epsilon": 0.0625, "eta": 2.5e-06,
      "gamma": 2.5e-07}
AS = {"mid": 100.0, "inventory": 2.0, "risk_aversion": 0.1, "sigma": 2.0, "time_left": 1.0, "k": 1.5}
PAIR = {"leg_b": {"side": "SELL", "price": 0.2}, "pair_mode": "CASH_BALANCED", "n_buckets": 1, "mode": "UNITS"}
AUC = {"phase": "OPEN", "ref_price": "10.00", "tick_size": "0.01"}
NO_CROSS = [{"id": "b", "limit": "10.00", "qty": 100, "side": "BUY"},
            {"id": "s", "limit": "10.01", "qty": 100, "side": "SELL"}]
ZERO_FEES = {"maker_rebate": "0", "taker_fee": "0"}


def lit(events):
    return {"tick_size": "0.01", "lot_size": "10", "events": events, "fee_schedule": ZERO_FEES}


def new(**kw):
    return dict({"id": "B1", "op": "NEW", "price": "100", "qty": "20", "side": "BUY", "trader": "T1",
                 "type": "LIMIT"}, **kw)


def dark(events):
    return {"config": {"firm_delay": 0, "lot_size": "10", "p_firm": "1", "penalty_events": 2, "seed": 1,
                       "tick_size": "0.01"},
            "events": [{"ask": "100.10", "bid": "100.00", "op": "BOOK"}] + events}


FIRM_B = {"id": "B1", "kind": "FIRM", "op": "NEW", "qty": "100", "side": "BUY"}
PT = {"order": {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101"}, "ref_price": "100",
      "position": "0", "cash": "10000", "orders_today": 0,
      "limits": {"max_order_qty": "10", "max_notional": "1000", "max_abs_position": "5", "price_band": "0.05",
                 "max_orders_per_day": 3, "kill_switch": False, "allow_short": True}}

# Arrival with kappa N = 800 (HR-125): x_j = X sinh(kappa (N - j)) / sinh(kappa N), evaluated with mpmath;
# sinh(800) overflows binary64, so a direct evaluation would be inf / inf.
_K, _N, _X = mp.mpf(200), 4, mp.mpf(1000)
_HOLD = [_X * mp.sinh(_K * (_N - j)) / mp.sinh(_K * _N) for j in range(_N + 1)]
ARRIVAL = [float(_HOLD[j] - _HOLD[j + 1]) for j in range(_N)]

# (description, operation, inputs, expected outputs, tolerance class, verified_by)
VALUES = [
    ("HR-121: POV whole units, p v / (1 - p) = 0.03 x 97 / 0.97 = 3 exactly; binary64 gives 2.9999999999999996, "
     "which is snapped to 3 before the floor", "exec.schedule.pov",
     {"quantity": 1000, "participation": 0.03, "market_volume": [97.0], "mode": "UNITS"},
     {"slices": [3], "filled": 3, "residual": 997}, "date_and_convention", blind(3)),
    ("HR-121: close whole units, p_c V_c = 0.57 x 100 = 57 exactly (binary64 56.99999999999999); the other "
     "9,943 split over two equal buckets by largest remainder, 4,972 then 4,971", "exec.algo.close",
     {"quantity": 10000, "close_volume": 100, "auction_participation": 0.57, "profile": [1, 1], "mode": "UNITS"},
     {"auction_quantity": 57, "slices": [4972, 4971]}, "date_and_convention", blind(3)),
    ("HR-121: pair leg B at an exact half, C P_A / P_B = 0.3 / 0.2 = 1.5 (binary64 1.4999999999999998) rounds "
     "half up to 2; imbalance 0.3 - 0.4", "exec.algo.pair",
     dict(PAIR, leg_a={"side": "BUY", "quantity": 1, "price": 0.3}),
     {"quantity_b": 2, "slices_a": [1], "slices_b": [2], "cash_imbalance": [-0.1]}, "simple_analytic", blind(3)),
    ("HR-121: pair leg B at an exact half that binary64 represents, 5 x 0.7 / 1.0 = 3.5, rounds half up to 4; "
     "imbalance 3.5 - 4.0", "exec.algo.pair",
     dict(PAIR, leg_a={"side": "BUY", "quantity": 5, "price": 0.7}, leg_b={"side": "SELL", "price": 1.0}),
     {"quantity_b": 4, "slices_a": [5], "slices_b": [4], "cash_imbalance": [-0.5]}, "simple_analytic", blind(3)),
    ("HR-124: AC with sigma = 0 and lambda > 0: y = 0, so the trajectory is linear and kappa = 0; "
     "E = 125,000 + 62,500 + 475,000 as ac_h-0001, V = 0", "exec.ac.trajectory",
     dict(AC, sigma=0.0, risk_aversion=1e-6),
     {"holdings": [1000000.0, 800000.0, 600000.0, 400000.0, 200000.0, 0.0],
      "trades": [200000.0, 200000.0, 200000.0, 200000.0, 200000.0], "kappa": 0.0, "expected_cost": 662500.0,
      "variance": 0.0, "objective": 662500.0}, "simple_analytic", blind(4)),
    ("HR-125: arrival with kappa N = 800, where sinh overflows binary64: slices X e^(-200 (j - 1)) (1 - e^(-200)) "
     "to rounding, from mpmath", "exec.algo.arrival",
     {"quantity": 1000, "n_buckets": 4, "urgency": 200.0, "mode": "CONTINUOUS"}, {"slices": ARRIVAL},
     "simple_analytic", blind(4)),
    ("HR-125: the same in whole units: everything trades in the first bucket", "exec.algo.arrival",
     {"quantity": 1000, "n_buckets": 4, "urgency": 200.0, "mode": "UNITS"}, {"slices": [1000, 0, 0, 0]},
     "date_and_convention", blind(4)),
    ("HR-126: shortfall with no fills and a benchmark VWAP: nothing executed, so delay, execution and "
     "vwap_slippage are 0; opportunity 1,000 x (101 - 100) = 1,000 = 100 bp of 1,000 x 100", "exec.tca.shortfall",
     {"side": "BUY", "decision_price": 100.0, "arrival_price": 100.1, "end_price": 101.0, "order_quantity": 1000.0,
      "fills": [], "fees": 0.0, "benchmark_vwap": 100.15},
     {"delay": 0.0, "execution": 0.0, "opportunity": 1000.0, "total": 1000.0, "total_bps": 100.0,
      "vwap_slippage": 0.0}, "simple_analytic", blind(4)),
    ("HR-127: auction with both sides present and no cross (buy 10.00, sell 10.01): the maximum volume is 0, "
     "so there is no auction: price null, both orders residual", "exec.sim.auction.uncross",
     dict(AUC, orders=NO_CROSS),
     {"cancelled": [], "fills": [], "imbalance": 0, "label": LIT_LABEL, "price": None,
      "residual": [{"id": "b", "limit": "10.00", "qty": 100, "side": "B"},
                   {"id": "s", "limit": "10.01", "qty": 100, "side": "S"}], "volume": 0},
     "date_and_convention", blind(4)),
    ("HR-128: MODIFY of an id that is not open is rejected UNKNOWN_ID and changes nothing", "exec.sim.lit.run",
     lit([new(), {"op": "MODIFY", "id": "ZZ", "qty": "10"}]),
     {"book": {"asks": [], "bids": [{"display_qty": "20", "hidden_qty": "0", "id": "B1", "price": "100", "seq": 1}]},
      "cancelled": [], "conservation": {"B1": {"cancelled": "0", "filled": "0", "rejected": "0", "resting": "20",
                                               "submitted": "20"}},
      "fees": {}, "fills": [], "label": LIT_LABEL, "mbp": {"asks": [], "bids": [["100", "20"]]},
      "rejects": [{"id": "ZZ", "reason": "UNKNOWN_ID"}]}, "date_and_convention", ["hand"]),
    ("HR-129: dark pool min_qty defaults to one lot (lot_size 10): a 10-share sell meets the default and "
     "fills 10 at the mid 100.05, leaving 90 of the buy", "exec.sim.dark.run",
     dark([FIRM_B, {"id": "S1", "kind": "FIRM", "op": "NEW", "qty": "10", "side": "SELL"}]),
     {"fills": [{"buy_id": "B1", "price": "100.05", "qty": "10", "sell_id": "S1", "seq": 1}], "invitations": [],
      "label": DARK_LABEL, "resting": [{"id": "B1", "open_qty": "90", "seq": 1, "side": "BUY"}],
      "suspensions": []}, "date_and_convention", ["hand"]),
]

TWAP = {"quantity": 1000, "n_buckets": 3, "mode": "UNITS"}
ARR = {"quantity": 5, "n_buckets": 4, "urgency": 0.0, "mode": "CONTINUOUS"}
# (description, operation, inputs, error code). Order of checks, HR-122: E_SCHEMA; E_LIMIT for a size limit on
# the input; the F-2 finite rule (E_DOMAIN); structural E_INPUT; E_DOMAIN.
ERRORS = [
    ("HR-122: a size limit (200,000 buckets) before a structural error (negative quantity)", "exec.schedule.twap",
     dict(TWAP, n_buckets=200000, quantity=-5), "E_LIMIT"),
    ("HR-122: a size limit before a non-finite value", "exec.schedule.twap",
     {"quantity": "NaN", "n_buckets": 200000, "mode": "CONTINUOUS"}, "E_LIMIT"),
    ("HR-122: a non-finite value (F-2) before a structural error (0 buckets)", "exec.schedule.twap",
     {"quantity": "NaN", "n_buckets": 0, "mode": "CONTINUOUS"}, "E_DOMAIN"),
    ("HR-122: POV, an empty volume list (structural) before participation outside (0, 1)", "exec.schedule.pov",
     {"quantity": 1000, "participation": 1.5, "market_volume": [], "mode": "UNITS"}, "E_INPUT"),
    ("HR-122: AC, N < 1 (structural) before sigma < 0", "exec.ac.trajectory",
     dict(AC, n_steps=0, sigma=-1.0, risk_aversion=0.0), "E_INPUT"),
    ("HR-122: AC, X <= 0 (structural) before T <= 0", "exec.ac.trajectory",
     dict(AC, quantity=0.0, horizon=0.0, risk_aversion=0.0), "E_INPUT"),
    ("HR-122: frontier, an empty list (structural) before sigma < 0", "exec.ac.frontier",
     dict(AC, sigma=-1.0, risk_aversions=[]), "E_INPUT"),
    ("HR-122: arrival, a size limit before a negative urgency", "exec.algo.arrival",
     dict(ARR, n_buckets=200000, urgency=-1.0), "E_LIMIT"),
    ("HR-122: arrival, a non-positive quantity (structural) before a negative urgency", "exec.algo.arrival",
     dict(ARR, quantity=-5, urgency=-1.0), "E_INPUT"),
    ("HR-123: AC risk_aversion < 0", "exec.ac.trajectory", dict(AC, risk_aversion=-1e-6), "E_DOMAIN"),
    ("HR-123: frontier with an empty risk_aversions list", "exec.ac.frontier", dict(AC, risk_aversions=[]),
     "E_INPUT"),
    ("HR-123: frontier with a negative risk aversion", "exec.ac.frontier", dict(AC, risk_aversions=[1e-6, -1.0]),
     "E_DOMAIN"),
    ("HR-123: AS sigma < 0", "micro.mm.as_quotes", dict(AS, sigma=-2.0), "E_DOMAIN"),
    ("HR-123: AS time_left < 0", "micro.mm.as_quotes", dict(AS, time_left=-1.0), "E_DOMAIN"),
    ("HR-123: VWAP with a negative weight", "exec.schedule.vwap",
     {"quantity": 1000.0, "profile": [1.0, -2.0, 3.0], "mode": "CONTINUOUS"}, "E_DOMAIN"),
    ("HR-123: VWAP with an all-zero profile", "exec.schedule.vwap",
     {"quantity": 1000.0, "profile": [0.0, 0.0], "mode": "CONTINUOUS"}, "E_DOMAIN"),
    ("HR-123: VWAP whole units with a fractional quantity", "exec.schedule.vwap",
     {"quantity": 1000.5, "profile": [1.0, 2.0], "mode": "UNITS"}, "E_INPUT"),
    ("HR-123: POV whole units with a fractional quantity", "exec.schedule.pov",
     {"quantity": 1000.5, "participation": 0.2, "market_volume": [1000.0], "mode": "UNITS"}, "E_INPUT"),
    ("HR-123: TWAP with 0 buckets", "exec.schedule.twap", dict(TWAP, n_buckets=0), "E_INPUT"),
    ("HR-127: an auction limit off the tick grid", "exec.sim.auction.uncross",
     dict(AUC, orders=[{"id": "b", "limit": "10.005", "qty": 100, "side": "BUY"}]), "E_DOMAIN"),
    ("HR-128: a lit order quantity that is not a multiple of lot_size", "exec.sim.lit.run", lit([new(qty="15")]),
     "E_DOMAIN"),
    ("HR-128: an iceberg display_qty off the lot grid", "exec.sim.lit.run",
     lit([new(type="ICEBERG", display_qty="5")]), "E_DOMAIN"),
    ("HR-128: MODIFY to a quantity off the lot grid", "exec.sim.lit.run",
     lit([new(), {"op": "MODIFY", "id": "B1", "qty": "15"}]), "E_DOMAIN"),
    ("HR-128: MODIFY to quantity 0", "exec.sim.lit.run", lit([new(), {"op": "MODIFY", "id": "B1", "qty": "0"}]),
     "E_DOMAIN"),
    ("HR-129: a dark order quantity off the lot grid", "exec.sim.dark.run",
     dark([dict(FIRM_B, qty="15")]), "E_DOMAIN"),
    ("HR-129: a dark order with min_qty above its quantity", "exec.sim.dark.run",
     dark([FIRM_B, {"id": "S1", "kind": "FIRM", "op": "NEW", "qty": "10", "side": "SELL", "min_qty": "20"}]),
     "E_DOMAIN"),
    ("HR-123: a currency outside the eight ranked ones of HR-88 (pip value)", "micro.fx.pip_value",
     {"notional": "1000000", "pair": "USDMXN"}, "E_INPUT"),
    ("HR-123: a currency outside the eight ranked ones of HR-88 (spot date)", "micro.fx.spot_date",
     {"holidays": {}, "pair": "USDMXN", "trade_date": "2026-11-16"}, "E_INPUT"),
    ("HR-122 exception: paper.pretrade.check reports an unknown side as E_INPUT (paper-trading.md, Errors)", "paper.pretrade.check",
     dict(PT, order=dict(PT["order"], side="HOLD")), "E_INPUT"),
]


def build():
    s = Suite("rule_h", SPEC, G)
    for desc, op, inp, exp, cls, ver in VALUES:
        s.add(op, inp, exp, cls=cls, verified=ver, tags=["stage_h", "audit"],
              description=desc + ("" if len(ver) > 1 else "; not blind"))
    for desc, op, inp, code in ERRORS:
        s.add(op, inp, error=code, cls="date_and_convention", verified=["hand"], tags=["stage_h", "audit", "error"],
              description=desc)
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_h"
    build().write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
