//! `repo.*` operations: read the inputs, call the library, shape the outputs.
use super::bond::bond;
use super::fx::nullable_f64;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::bonds;
use quantforge_core::error::Result;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "repo.forward" => {
            let (b, s, e) = (bond(i)?, i.date("start")?, i.date("end")?);
            let (c, r) = (i.f64("clean_price")?, i.f64("repo_rate")?);
            let g = nullable_f64(i, "gc_rate")?;
            let f = bonds::repo_forward(&b, s, e, c, r, g)?;
            plain(obj([
                ("dirty", f.dirty.into()),
                ("forward_dirty", f.forward_dirty.into()),
                ("forward_clean", f.forward_clean.into()),
                ("interest", f.interest.into()),
                ("special_spread", f.special_spread.into()),
                ("specialness_value", f.specialness_value.into()),
            ]))
        },
        "repo.implied_rate" => {
            let (b, s, e) = (bond(i)?, i.date("start")?, i.date("end")?);
            let (c, f) = (i.f64("clean_price")?, i.f64("forward_clean")?);
            let r = bonds::repo_implied_rate(&b, s, e, c, f)?;
            plain(obj([("repo_rate", r.into())]))
        }
}
