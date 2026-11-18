//! Stage H multi-asset verbs H-22, H-23, H-24 (`specifications/09-microstructure/asset-conventions.md`,
//! `specifications/10-execution/auction.md`, `fx-rfq-venue.md`, `rates-futures-venue.md`). Each takes
//! the raw inputs object; the core functions parse and check in the reference order (HR-66).
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::multiasset as ma;

/// Runs `f`; a schema error outranks the per-array size gate (`E_LIMIT`), as in the other verbs.
fn call(i: &Inputs, f: fn(&Json) -> Result<Json>) -> Result<Outcome> {
    let r = f(i.0);
    if let Err(e) = &r
        && e.code == "E_SCHEMA"
    {
        return Err(e.clone());
    }
    i.gate()?;
    plain(r?)
}

pub mod micro {
    use super::{Inputs, Outcome, Result, call, ma};

    crate::ops::registry! {
    (op, i)
        "micro.eq.round_price" => call(i, ma::eq_round_price),
        "micro.eq.fee_check" => call(i, ma::eq_fee_check),
        "micro.eq.round_lot" => call(i, ma::eq_round_lot),
        "micro.eq.settle_date" => call(i, ma::eq_settle_date),
        "micro.fx.pip_value" => call(i, ma::fx_pip_value),
        "micro.fx.spot_date" => call(i, ma::fx_spot_date),
        "micro.rates.parse_32nds" => call(i, ma::rates_parse_32nds),
        "micro.rates.format_32nds" => call(i, ma::rates_format_32nds),
        "micro.rates.tick_value" => call(i, ma::rates_tick_value),
        "micro.rates.bond_price" => call(i, ma::rates_bond_price),
        "micro.rates.bill_price" => call(i, ma::rates_bill_price),
    }
}

pub mod exec {
    use super::{Inputs, Outcome, Result, call, ma};

    crate::ops::registry! {
    (op, i)
        "exec.sim.auction.uncross" => call(i, ma::auction_uncross),
        "exec.sim.fx.stream" => call(i, ma::fx_stream),
        "exec.sim.fx.request" => call(i, ma::fx_request),
        "exec.sim.fut.to_ticks" => call(i, ma::fut_to_ticks),
        "exec.sim.fut.to_text" => call(i, ma::fut_to_text),
        "exec.sim.fut.pnl" => call(i, ma::fut_pnl),
        "exec.sim.fut.variation" => call(i, ma::fut_variation),
        "exec.sim.fut.run" => call(i, ma::fut_run),
    }
}
