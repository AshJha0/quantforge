//! `eq.*` operations: read the inputs, call the library, shape the outputs.
use super::fx::nullable_f64;
use super::rates::curve_input;
use super::rates::present;
use super::rates::sub;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::curve::Curve;
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity;
use quantforge_core::equity::Outright;
use quantforge_core::equity::ParityQuote;
use quantforge_core::equity_d;
use quantforge_core::equity_d::Action;
use quantforge_core::equity_d::Constituent;
use quantforge_core::equity_d::Trs;
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "eq.forward.outright" => {
            let f = forward_inputs(i)?;
            i.gate()?;
            let r = outright(&f)?;
            plain(obj([
                ("forward", r.forward.into()),
                ("discount_factor", r.discount_factor.into()),
                ("carry_factor", r.carry_factor.into()),
                ("pv_dividends", r.pv_dividends.into()),
            ]))
        },
        "eq.forward.flat" => {
            let mut d = Vec::new();
            for v in items(i, "dividends")? {
                d.push((v.f64("time_years")?, v.f64("amount")?));
            }
            let (s, r, b, t) = (
                i.f64("spot")?,
                i.f64("rate")?,
                i.f64("borrow")?,
                i.f64("expiry_years")?,
            );
            i.gate()?;
            plain(obj([("forward", equity::flat(s, r, b, t, &d)?.into())]))
        },
        "eq.forward.parity" => {
            present(i, "discount_factor")?;
            let q = parity_quotes(i)?;
            let d = i.opt_f64("discount_factor")?;
            i.gate()?;
            let r = equity::parity(&q, d)?;
            plain(obj([
                ("forward", r.forward.into()),
                ("discount_factor", r.discount_factor.into()),
                ("max_residual", r.max_residual.into()),
                ("outside_spread", r.outside_spread.into()),
            ]))
        },
        "eq.dividend.implied" => {
            let (s, f, b) = (
                i.f64("spot")?,
                curve_input(i, "funding")?,
                i.f64("borrow_rate")?,
            );
            let mut fut = Vec::new();
            for x in items(i, "futures")? {
                fut.push((x.date("expiry")?, x.f64("price")?));
            }
            i.gate()?;
            let r = equity_d::dividend_implied(s, &Curve::new(&f)?, b, &fut)?;
            plain(obj([
                ("pv_dividends", r.pv_dividends.into()),
                ("period_pv_dividends", r.period_pv_dividends.into()),
                ("dividend_yields", r.dividend_yields.into()),
            ]))
        },
        "eq.borrow.implied" => {
            let (s, f, dv) = (i.f64("spot")?, curve_input(i, "funding")?, ex_dividends(i)?);
            let (e, fw) = (i.date("expiry")?, i.f64("forward")?);
            i.gate()?;
            let b = equity_d::borrow_implied(s, &Curve::new(&f)?, &dv, e, fw)?;
            plain(obj([("borrow_rate", b.into())]))
        },
        "eq.futures.basis" => {
            let (s, f) = (i.f64("spot")?, curve_input(i, "funding")?);
            let (b, sp, dv) = (
                i.f64("borrow_rate")?,
                i.f64("financing_spread")?,
                ex_dividends(i)?,
            );
            let (e, p) = (i.date("expiry")?, i.f64("futures_price")?);
            i.gate()?;
            let (fair, basis, implied) =
                equity_d::futures_basis(s, &Curve::new(&f)?, b, sp, &dv, e, p)?;
            plain(obj([
                ("fair_price", fair.into()),
                ("basis", basis.into()),
                ("implied_financing_spread", implied.into()),
            ]))
        },
        "eq.index.dividends" => {
            let d = i.f64("divisor")?;
            let cs = constituents(i, "constituents", true)?;
            let mut periods = Vec::new();
            for p in items(i, "periods")? {
                periods.push((p.date("start")?, p.date("end")?));
            }
            let implied = i.reals("implied_period_points")?;
            i.gate()?;
            let r = equity_d::index_dividends(d, &cs, &periods, &implied)?;
            let ex: Vec<Json> = r.ex_dates.iter().map(|d| d.to_string().into()).collect();
            plain(obj([
                ("level", r.level.into()),
                ("ex_dates", ex.into()),
                ("points", r.points.into()),
                ("period_points", r.period_points.into()),
                ("basis", r.basis.into()),
            ]))
        },
        "eq.index.rebalance" => {
            let d = i.f64("divisor")?;
            let (old, new) = (
                constituents(i, "constituents", false)?,
                constituents(i, "new_constituents", false)?,
            );
            i.gate()?;
            let (l, nd, w) = equity_d::rebalance(d, &old, &new)?;
            plain(obj([
                ("level", l.into()),
                ("new_divisor", nd.into()),
                ("weights", w.into()),
            ]))
        },
        "eq.corporate_action.adjust" => {
            let a = match i.str("action")? {
                "SPLIT" | "REVERSE_SPLIT" => Action::Split(i.f64("ratio")?),
                "RIGHTS" => Action::Rights {
                    m: i.f64("new_per_old")?,
                    k: i.f64("subscription_price")?,
                },
                "SPECIAL_DIVIDEND" => Action::SpecialDividend(i.f64("amount")?),
                _ => return i.fail("action", "unknown action"),
            };
            let (p, n, k) = (i.f64("cum_price")?, i.f64("shares")?, i.f64("strike")?);
            let (f, ex, ns, ks) = equity_d::corporate_action(a, p, n, k)?;
            plain(obj([
                ("factor", f.into()),
                ("ex_price", ex.into()),
                ("adjusted_shares", ns.into()),
                ("adjusted_strike", ks.into()),
            ]))
        },
        "eq.trs.pv" => {
            let (s, f) = (i.f64("spot")?, curve_input(i, "funding")?);
            let (b, dv) = (i.f64("borrow_rate")?, ex_dividends(i)?);
            let t = sub(i, "trade")?;
            let trade = Trs {
                start: t.date("start")?,
                end: t.date("end")?,
                initial_price: t.f64("initial_price")?,
                shares: t.f64("shares")?,
                spread: t.f64("spread")?,
                receive_equity: match t.str("side")? {
                    "RECEIVE_EQUITY" => true,
                    "PAY_EQUITY" => false,
                    _ => return t.fail("side", "unknown side"),
                },
            };
            let r = nullable_f64(i, "current_rate")?;
            i.gate()?;
            let (e, fl, pv) = equity_d::trs_pv(s, &Curve::new(&f)?, b, &dv, &trade, r)?;
            plain(obj([
                ("equity_leg", e.into()),
                ("funding_leg", fl.into()),
                ("pv", pv.into()),
            ]))
        }
}

pub(crate) fn items<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| match v {
            Json::Obj(_) => Ok(Inputs::new(v)),
            _ => i.fail(k, "expected objects"),
        })
        .collect()
}

pub(crate) struct ForwardInputs {
    pub(crate) spot: f64,
    pub(crate) as_of: Date,
    pub(crate) expiry: Date,
    pub(crate) funding: CurveInput,
    pub(crate) borrow: Option<CurveInput>,
    pub(crate) dividends: Vec<(Date, f64)>,
}

pub(crate) fn forward_inputs(i: &Inputs) -> Result<ForwardInputs> {
    present(i, "borrow_curve")?;
    let mut dividends = Vec::new();
    for d in items(i, "dividends")? {
        dividends.push((d.date("ex_date")?, d.f64("amount")?));
    }
    Ok(ForwardInputs {
        spot: i.f64("spot")?,
        as_of: i.date("as_of")?,
        expiry: i.date("expiry")?,
        funding: curve_input(i, "funding_curve")?,
        borrow: i
            .opt("borrow_curve")
            .map(|_| curve_input(i, "borrow_curve"))
            .transpose()?,
        dividends,
    })
}

pub(crate) fn outright(f: &ForwardInputs) -> Result<Outright> {
    equity::outright(
        f.spot,
        f.as_of,
        f.expiry,
        &f.funding,
        f.borrow.as_ref(),
        &f.dividends,
    )
}

pub(crate) fn parity_quotes(i: &Inputs) -> Result<Vec<ParityQuote>> {
    items(i, "quotes")?
        .iter()
        .map(|q| {
            Ok(ParityQuote {
                strike: q.f64("strike")?,
                call_bid: q.f64("call_bid")?,
                call_ask: q.f64("call_ask")?,
                put_bid: q.f64("put_bid")?,
                put_ask: q.f64("put_ask")?,
            })
        })
        .collect()
}

pub(crate) fn ex_dividends(i: &Inputs) -> Result<Vec<(Date, f64)>> {
    items(i, "dividends")?
        .iter()
        .map(|x| Ok((x.date("ex_date")?, x.f64("amount")?)))
        .collect()
}

pub(crate) fn constituents(i: &Inputs, k: &str, with_dividends: bool) -> Result<Vec<Constituent>> {
    items(i, k)?
        .iter()
        .map(|c| {
            Ok(Constituent {
                id: c.str("id")?.to_string(),
                shares: c.f64("shares")?,
                price: c.f64("price")?,
                dividends: if with_dividends {
                    ex_dividends(c)?
                } else {
                    Vec::new()
                },
            })
        })
        .collect()
}
