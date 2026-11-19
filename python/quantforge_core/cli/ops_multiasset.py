"""Stage H multi-asset verbs H-22, H-23, H-24 (specifications/09-microstructure/asset-conventions.md,
specifications/10-execution/auction.md, fx-rfq-venue.md, rates-futures-venue.md)."""

from typing import Any

from .inputs import Inputs
from .registry import core, op


@op("micro.eq.round_price")
def micro_eq_round_price(i: Inputs) -> Any:
    return core.multiasset.eq_round_price(dict(i.raw))


@op("micro.eq.fee_check")
def micro_eq_fee_check(i: Inputs) -> Any:
    return core.multiasset.eq_fee_check(dict(i.raw))


@op("micro.eq.settle_date")
def micro_eq_settle_date(i: Inputs) -> Any:
    return core.multiasset.eq_settle_date(dict(i.raw))


@op("exec.sim.auction.uncross")
def exec_sim_auction_uncross(i: Inputs) -> Any:
    return core.multiasset.auction_uncross(dict(i.raw))


@op("micro.fx.pip_value")
def micro_fx_pip_value(i: Inputs) -> Any:
    return core.multiasset.fx_pip_value(dict(i.raw))


@op("micro.fx.spot_date")
def micro_fx_spot_date(i: Inputs) -> Any:
    return core.multiasset.fx_spot_date(dict(i.raw))


@op("exec.sim.fx.stream")
def exec_sim_fx_stream(i: Inputs) -> Any:
    return core.multiasset.fx_stream(dict(i.raw))


@op("exec.sim.fx.request")
def exec_sim_fx_request(i: Inputs) -> Any:
    return core.multiasset.fx_request(dict(i.raw))


@op("micro.rates.parse_32nds")
def micro_rates_parse_32nds(i: Inputs) -> Any:
    return core.multiasset.rates_parse_32nds(dict(i.raw))


@op("micro.rates.format_32nds")
def micro_rates_format_32nds(i: Inputs) -> Any:
    return core.multiasset.rates_format_32nds(dict(i.raw))


@op("micro.rates.tick_value")
def micro_rates_tick_value(i: Inputs) -> Any:
    return core.multiasset.rates_tick_value(dict(i.raw))


@op("micro.rates.bond_price")
def micro_rates_bond_price(i: Inputs) -> Any:
    return core.multiasset.rates_bond_price(dict(i.raw))


@op("micro.rates.bill_price")
def micro_rates_bill_price(i: Inputs) -> Any:
    return core.multiasset.rates_bill_price(dict(i.raw))


@op("exec.sim.fut.to_ticks")
def exec_sim_fut_to_ticks(i: Inputs) -> Any:
    return core.multiasset.fut_to_ticks(dict(i.raw))


@op("exec.sim.fut.to_text")
def exec_sim_fut_to_text(i: Inputs) -> Any:
    return core.multiasset.fut_to_text(dict(i.raw))


@op("exec.sim.fut.pnl")
def exec_sim_fut_pnl(i: Inputs) -> Any:
    return core.multiasset.fut_pnl(dict(i.raw))


@op("exec.sim.fut.variation")
def exec_sim_fut_variation(i: Inputs) -> Any:
    return core.multiasset.fut_variation(dict(i.raw))


@op("exec.sim.fut.run")
def exec_sim_fut_run(i: Inputs) -> Any:
    return core.multiasset.fut_run(dict(i.raw))


@op("micro.eq.round_lot")
def micro_eq_round_lot(i: Inputs) -> Any:
    return core.multiasset.eq_round_lot(dict(i.raw))


@op("micro.rates.bond_yield")
def micro_rates_bond_yield(i: Inputs) -> Any:
    return core.multiasset.rates_bond_yield(dict(i.raw))
