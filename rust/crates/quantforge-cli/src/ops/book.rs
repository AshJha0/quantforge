//! `book.*` operations (stage F, F5): read the inputs, call the library, shape the outputs.
use super::eq::items;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::book;
use quantforge_core::book::Event;
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "book.lifecycle.apply" => {
            let opening = items(i, "positions")?
                .iter()
                .map(|p| Ok((p.str("instrument")?.to_string(), p.f64("quantity")?, p.f64("average_cost")?)))
                .collect::<Result<Vec<_>>>()?;
            let events = items(i, "events")?
                .iter()
                .map(|e| {
                    let s = |k: &str| e.str(k).map(str::to_string);
                    let ev = match e.str("type")? {
                        "TRADE" => Event::Trade { instrument: s("instrument")?, quantity: e.f64("quantity")?, price: e.f64("price")? },
                        "FIXING" => Event::Fixing { index: s("index")?, value: e.f64("value")? },
                        "EXPIRY" => Event::Expiry { instrument: s("instrument")?, price: e.f64("settlement_price")? },
                        "DEFAULT" => Event::Default { instrument: s("instrument")?, price: e.f64("recovery_price")? },
                        "ROLL" => Event::Roll {
                            from: s("from")?,
                            to: s("to")?,
                            from_price: e.f64("from_price")?,
                            to_price: e.f64("to_price")?,
                        },
                        _ => return e.fail("type", "unknown event type"),
                    };
                    Ok((e.date("date")?, ev))
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let b = book::apply(&opening, &events)?;
            let pos: Vec<Json> = b
                .positions
                .iter()
                .map(|(k, (q, a))| obj([("instrument", k.as_str().into()), ("quantity", (*q).into()), ("average_cost", (*a).into())]))
                .collect();
            let pnl: Vec<Json> = b
                .realized
                .iter()
                .map(|(k, v)| obj([("instrument", k.as_str().into()), ("pnl", (*v).into())]))
                .collect();
            let total: f64 = b.realized.values().sum();
            let fx: Vec<Json> = b
                .fixings
                .iter()
                .map(|((k, d), v)| obj([("index", k.as_str().into()), ("date", d.to_string().into()), ("value", (*v).into())]))
                .collect();
            plain(obj([
                ("positions", Json::Arr(pos)),
                ("realized_pnl", Json::Arr(pnl)),
                ("total_realized", total.into()),
                ("fixings", Json::Arr(fx)),
            ]))
        },
        "book.marks.resolve" => {
            let as_of = i.date("as_of")?;
            let instruments: Vec<String> = i
                .array("instruments")?
                .iter()
                .map(|v| match v {
                    Json::Str(s) => Ok(s.clone()),
                    _ => i.fail("instruments", "expected strings"),
                })
                .collect::<Result<_>>()?;
            let sources = items(i, "sources")?
                .iter()
                .map(|s| {
                    let quotes = items(s, "quotes")?
                        .iter()
                        .map(|q| Ok((q.str("instrument")?.to_string(), q.date("date")?, q.f64("price")?)))
                        .collect::<Result<Vec<_>>>()?;
                    Ok(book::Source { name: s.str("name")?.to_string(), quotes })
                })
                .collect::<Result<Vec<_>>>()?;
            let max_age = i.int("max_age_days")?;
            let ipv = match i.opt("ipv") {
                None | Some(Json::Null) => Vec::new(),
                Some(_) => items(i, "ipv")?
                    .iter()
                    .map(|p| Ok((p.str("instrument")?.to_string(), p.f64("price")?)))
                    .collect::<Result<Vec<_>>>()?,
            };
            let th = i.f64_or("ipv_threshold", 0.0)?;
            i.gate()?;
            let marks = book::resolve(as_of, &instruments, &sources, max_age, &ipv, th)?;
            let rows: Vec<Json> = marks
                .into_iter()
                .map(|m| {
                    obj([
                        ("instrument", m.instrument.into()),
                        ("price", m.price.into()),
                        ("source", m.source.map_or(Json::Null, Json::Str)),
                        ("status", m.status.into()),
                        ("age_days", m.age_days.map_or(Json::Null, Into::into)),
                        ("ipv_diff", m.ipv_diff.into()),
                        ("ipv_breach", Json::Bool(m.ipv_breach)),
                    ])
                })
                .collect();
            plain(obj([("marks", Json::Arr(rows))]))
        }
}
