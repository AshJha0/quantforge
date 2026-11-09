//! `cmdty.*` operations: read the inputs, call the library, shape the outputs.
use super::eq::items;
use super::infl::month_of;
use super::rates::curve_input;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::curve::Curve;
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::stage_d3;

super::registry! {
(op, i)
        "cmdty.curve.forward" => {
            let mut q = Vec::new();
            for x in items(i, "quotes")? {
                let Some(m) = month_of(x.str("month")?) else {
                    return x.fail("month", "expected YYYY-MM");
                };
                q.push((m, x.f64("price")?));
            }
            let s = match i.0.get("seasonality") {
                None => return i.fail("seasonality", "is required"),
                Some(Json::Null) => None,
                _ => Some(i.reals("seasonality")?),
            };
            let mut months = Vec::new();
            for v in i.array("months")? {
                match v.as_str().and_then(month_of) {
                    Some(m) => months.push(m),
                    None => return i.fail("months", "expected YYYY-MM"),
                }
            }
            i.gate()?;
            let f = stage_d3::commodity_forwards(&q, s.as_deref(), &months)?;
            plain(obj([("forwards", f.into())]))
        },
        "cmdty.storage.carry" => {
            let f = curve_input(i, "funding")?;
            let mut fw = Vec::new();
            for x in items(i, "forwards")? {
                fw.push((x.date("date")?, x.f64("price")?));
            }
            let u = i.f64("storage_cost")?;
            i.gate()?;
            let (y, c, a) = stage_d3::storage_carry(&Curve::new(&f)?, &fw, u)?;
            let a: Vec<Json> = a.into_iter().map(Json::Bool).collect();
            plain(obj([
                ("convenience_yields", y.into()),
                ("carry_values", c.into()),
                ("arbitrage", a.into()),
            ]))
        }
}
