//! Stage K wave 1 verbs (PROPOSED rulings KR-1 to KR-14, `specifications/stage-k-rulings-w1.md`;
//! contract table "Stage K wave 1 operations"). Error order HR-66: the reads here are `E_SCHEMA`;
//! the core then applies structural `E_INPUT`, `E_DOMAIN` (the F-2 finite rule first),
//! value-dependent `E_INPUT` and `E_LIMIT`, in that order. The generic gate sizes and the
//! dispatcher's F-2 override are skipped for these verbs (`STAGE_K_OPS`), as the stage K
//! sizes are checked last, in the core.

/// The six operation names, for the dispatcher's stage K path.
pub const STAGE_K_OPS: &[&str] = &[
    "core.store.bitemporal_query",
    "curve.bootstrap.par_annual",
    "curve.incremental.update",
    "calib.trigger.check",
    "risk.intraday.delta_gamma_bound",
    "num.richardson.check",
];

pub mod core {
    use crate::input::{Inputs, schema};
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::{Json, obj};
    use quantforge_core::stage_k::{self as sk, BiRecord};
    use quantforge_core::store::check_range;
    use quantforge_core::time::format_instant;

    /// One record. `value` and `valid_to` are required keys; `valid_to` may be null (open).
    fn record(raw: &Json) -> Result<BiRecord> {
        if !matches!(raw, Json::Obj(_)) {
            return Err(schema("records", "a record is not an object"));
        }
        let (Some(value), Some(_)) = (raw.get("value"), raw.get("valid_to")) else {
            return Err(schema("records", "a record has no value or no valid_to"));
        };
        let r = Inputs::new(raw);
        let sequence = r.int("sequence")?;
        let series_id = r.str("series_id")?;
        if sequence < 1 || series_id.is_empty() {
            return Err(schema("records", "bad sequence or series_id in a record"));
        }
        Ok(BiRecord {
            sequence,
            series_id: series_id.to_string(),
            valid_from: r.instant("valid_from")?,
            valid_to: r
                .opt("valid_to")
                .map(|_| r.instant("valid_to"))
                .transpose()?,
            knowledge_time: r.instant("knowledge_time")?,
            value: value.clone(),
            deleted: r.bool_or("deleted", false)?,
        })
    }

    fn row(w: &BiRecord) -> Result<Json> {
        check_range(
            [w.valid_from, w.knowledge_time]
                .into_iter()
                .chain(w.valid_to),
        )?;
        Ok(obj([
            ("sequence", w.sequence.into()),
            ("valid_from", format_instant(w.valid_from).into()),
            ("valid_to", w.valid_to.map(format_instant).into()),
            ("knowledge_time", format_instant(w.knowledge_time).into()),
            ("value", w.value.clone()),
        ]))
    }

    crate::ops::registry! {
    (op, i)
        "core.store.bitemporal_query" => {
            let log = i
                .array("records")?
                .iter()
                .map(record)
                .collect::<Result<Vec<_>>>()?;
            let series_id = i.str("series_id")?;
            let (k, v) = (i.instant("knowledge_as_of")?, i.instant("valid_at")?);
            let (status, winner) = sk::bitemporal_query(&log, series_id, k, v)?;
            let row = winner.map(row).transpose()?;
            plain(obj([("status", status.name().into()), ("row", row.into())]))
        }
    }
}

pub mod curve {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::obj;
    use quantforge_core::stage_k as sk;

    crate::ops::registry! {
    (op, i)
        "curve.bootstrap.par_annual" => {
            let quotes = i.reals("quotes")?;
            plain(obj([("discount_factors", sk::par_annual(&quotes)?.into())]))
        },
        "curve.incremental.update" => {
            let pq = i.reals("previous_quotes")?;
            let pd = i.reals("previous_discount_factors")?;
            let nq = i.reals("new_quotes")?;
            let u = sk::incremental_update(&pq, &pd, &nq)?;
            plain(obj([
                ("discount_factors", u.discount_factors.into()),
                ("first_changed_index", u.first_changed_index.map(|j| j as i64).into()),
                ("recomputed", (u.recomputed as i64).into()),
            ]))
        }
    }
}

pub mod calib {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::obj;
    use quantforge_core::stage_k as sk;

    crate::ops::registry! {
    (op, i)
        "calib.trigger.check" => {
            let changes = i.reals("changes")?;
            let (x_ref, x_now) = (i.f64("x_ref")?, i.f64("x_now")?);
            let (d, k) = (i.f64("days_since")?, i.f64("k")?);
            let t = sk::trigger_check(&changes, x_ref, x_now, d, k)?;
            plain(obj([
                ("fire", t.fire.into()),
                ("sigma", t.sigma.into()),
                ("threshold", t.threshold.into()),
                ("false_alarm_rate", t.false_alarm_rate.into()),
            ]))
        }
    }
}

pub mod risk {
    use crate::input::Inputs;
    use crate::ops::micro::est::rows;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::obj;
    use quantforge_core::stage_k::{self as sk, ZeroPosition};

    crate::ops::registry! {
    (op, i)
        "risk.intraday.delta_gamma_bound" => {
            let positions = rows(i, "positions")?
                .iter()
                .map(|p| {
                    Ok(ZeroPosition {
                        notional: p.f64("notional")?,
                        maturity: p.f64("maturity")?,
                        yield_: p.f64("yield")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let shift = i.f64("shift")?;
            let r = sk::delta_gamma_bound(&positions, shift)?;
            plain(obj([
                ("estimate_pnl", r.estimate_pnl.into()),
                ("bound", r.bound.into()),
                ("label", sk::LABEL.into()),
            ]))
        }
    }
}

pub mod num {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::obj;
    use quantforge_core::stage_k as sk;

    crate::ops::registry! {
    (op, i)
        "num.richardson.check" => {
            let values = i.reals("values")?;
            let (ratio, p) = (i.f64("ratio")?, i.f64("assumed_order")?);
            let r = sk::richardson_check(&values, ratio, p)?;
            plain(obj([
                ("status", r.status.into()),
                ("observed_order", r.observed_order.into()),
                ("extrapolated", r.extrapolated.into()),
            ]))
        }
    }
}

#[cfg(test)]
#[path = "stagek_tests.rs"]
mod tests;
