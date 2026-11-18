//! Stage H paper trading verbs (`specifications/10-execution/paper-trading.md`, HR-42 to HR-55).
//! Simulated only: no verb reaches a network or a venue (HR-42).
use crate::input::{Inputs, schema};
use crate::ops::{Outcome, plain};
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::paper::{self, DayInputs, GENESIS};

fn object<'a>(i: &Inputs<'a>, k: &str) -> Result<&'a Json> {
    match i.req(k)? {
        o @ Json::Obj(_) => Ok(o),
        _ => Err(schema(k, "expected an object")),
    }
}

fn string<'a>(i: &Inputs<'a>, k: &str) -> Result<&'a Json> {
    match i.opt(k) {
        Some(v) => Ok(v),
        None => i.str(k).map(|_| &Json::Null),
    }
}

crate::ops::registry! {
(op, i)
    "paper.book.apply_fill" => {
        let fills = i.array("fills")?;
        let zero = Json::Str("0".into());
        let (pos, avg) = (i.opt("position").unwrap_or(&zero), i.opt("avg_cost").unwrap_or(&zero));
        i.gate()?;
        plain(paper::book_case(fills, i.opt("cash"), pos, avg)?)
    },
    "paper.book.end_of_day" => {
        let cash_open = string(i, "cash_open")?;
        let fills = match i.opt("fills") {
            Some(_) => i.array("fills")?,
            None => &[],
        };
        let zero = Json::Str("0".into());
        let days = i.int_or("days", 1)?;
        let r = |k: &str| i.opt(k).unwrap_or(&zero);
        let d = DayInputs {
            cash_open,
            fills,
            position_open: r("position_open"),
            avg_cost_open: i.opt("avg_cost_open"),
            prev_close: i.opt("prev_close"),
            close: i.opt("close"),
            days,
            rates: [r("cash_rate"), r("debit_rate"), r("borrow_rate")],
        };
        i.gate()?;
        plain(paper::day_case(&d)?)
    },
    "paper.pretrade.check" => {
        let order = object(i, "order")?;
        let ref_price = string(i, "ref_price")?;
        let zero = Json::Str("0".into());
        let position = i.opt("position").unwrap_or(&zero);
        i.str("cash")?;
        let cash = i.req("cash")?;
        let orders_today = i.int_or("orders_today", 0)?;
        let limits = object(i, "limits")?;
        i.gate()?;
        plain(paper::pretrade_case(order, ref_price, position, cash, orders_today, limits)?)
    },
    "paper.ledger.append" => {
        let seq = i.int("seq")?;
        let (ts, kind) = (i.str("ts")?, i.str("kind")?);
        let body = object(i, "body")?;
        let prev = match i.opt("prev") {
            Some(_) => i.str("prev")?,
            None => "",
        };
        let prev = if prev.is_empty() { GENESIS } else { prev };
        i.gate()?;
        plain(paper::ledger_append(seq, ts, kind, body, prev)?)
    },
    "paper.ledger.verify" => {
        let text = i.str("text")?;
        i.gate()?;
        plain(paper::ledger_verify(text))
    },
    "paper.session.run" => {
        let cash = string(i, "cash")?;
        let (limits, lit) = (object(i, "limits")?, object(i, "lit")?);
        let script = i.array("script")?;
        let dark = match i.opt("dark") {
            Some(_) => Some(object(i, "dark")?),
            None => None,
        };
        i.gate()?;
        plain(paper::session_case(cash, limits, lit, script, dark)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use quantforge_core::json::parse;

    /// HR-42 / acceptance A5: a live order is never placed. The runner reads this code as "not
    /// implemented", so the case is pinned here rather than in the golden file (pt_h-0018).
    #[test]
    fn live_mode_is_e_unsupported_operation() {
        let inp = parse(
            r#"{"order":{"side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101","mode":"live"},
            "ref_price":"100","position":"0","cash":"10000","orders_today":0,
            "limits":{"max_order_qty":"10","max_notional":"1000","max_abs_position":"5",
            "price_band":"0.05","max_orders_per_day":3,"kill_switch":false,"allow_short":true}}"#,
        )
        .expect("json")
        .0;
        let r = dispatch("paper.pretrade.check", &Inputs::new(&inp)).expect("registered");
        assert!(r.is_err_and(|e| e.code == "E_UNSUPPORTED_OPERATION"));
        let s = parse(
            r#"{"cash":"10000","limits":{"max_order_qty":"10","max_notional":"1000",
            "max_abs_position":"5","price_band":"0.05","max_orders_per_day":3},
            "lit":{"tick_size":"0.5","lot_size":"1","fee_schedule":{"maker_rebate":"0","taker_fee":"0"}},
            "script":[{"op":"SUBMIT","ts":"t","order":{"order_id":"O1","symbol":"X","side":"BUY",
            "type":"MARKET","quantity":"1","mode":"live"},"snapshot":{"bids":[["99","1"]],"asks":[["101","1"]]}}]}"#,
        )
        .expect("json")
        .0;
        let r = dispatch("paper.session.run", &Inputs::new(&s)).expect("registered");
        assert!(r.is_err_and(|e| e.code == "E_UNSUPPORTED_OPERATION"));
    }
}
