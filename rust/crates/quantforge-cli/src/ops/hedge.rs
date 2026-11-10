//! `hedge.*` operations: read the inputs, call the library, shape the outputs.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::hedge;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "hedge.solve" => {
            let (a, b) = (i.matrix("a")?, i.reals("b")?);
            let (w, c, l) = (i.reals("weights")?, i.reals("costs")?, i.f64("lambda")?);
            i.gate()?;
            let h = hedge::solve_hedge(&a, &b, &w, &c, l)?;
            plain(obj([
                ("x", h.x.into()),
                ("residual", h.residual.into()),
                ("objective", h.objective.into()),
            ]))
        },
        "hedge.spread_cost" => {
            let (q, h) = (i.reals("quantities")?, i.reals("half_spreads")?);
            i.gate()?;
            plain(obj([("cost", hedge::spread_cost(&q, &h)?.into())]))
        }
}
