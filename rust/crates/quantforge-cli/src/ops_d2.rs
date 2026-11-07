//! Stage D wave 2 and 3 operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::tenor;
use crate::ops_b::{curve_input, items, sub};
use crate::ops_b::{interpolation, pillars_json, repricing};
use quantforge_core::bonds::{self, Bond, Frn};
use quantforge_core::conventions;
use quantforge_core::credit::{self, CdsTrade, Hazard};
use quantforge_core::curve::Curve;
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity_d::{self, Action, Constituent, Trs};
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::xccy::{self, Ndf, XccyTrade};

fn ex_dividends(i: &Inputs) -> Result<Vec<(Date, f64)>> {
    items(i, "dividends")?
        .iter()
        .map(|x| Ok((x.date("ex_date")?, x.f64("amount")?)))
        .collect()
}

fn constituents(i: &Inputs, k: &str, with_dividends: bool) -> Result<Vec<Constituent>> {
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

type HazardInput = (Date, Vec<(Date, f64)>);

fn hazard_input(i: &Inputs, k: &str) -> Result<HazardInput> {
    let h = sub(i, k)?;
    let mut p = Vec::new();
    for x in items(&h, "pillars")? {
        p.push((x.date("date")?, x.f64("survival")?));
    }
    Ok((h.date("as_of")?, p))
}

fn cds_quotes(i: &Inputs) -> Result<Vec<((i64, char), f64)>> {
    items(i, "quotes")?
        .iter()
        .map(|q| Ok((tenor(q, "tenor")?, q.f64("spread")?)))
        .collect()
}

fn credit_discount(c: &CurveInput) -> Result<(Curve, Vec<Date>)> {
    Ok((Curve::new(c)?, c.pillars.iter().map(|p| p.0).collect()))
}

fn survival_json(h: &Hazard) -> Json {
    let rows: Vec<Json> = h
        .pillars()
        .iter()
        .map(|(d, s)| obj([("date", d.to_string().into()), ("survival", (*s).into())]))
        .collect();
    rows.into()
}

/// A convention id that must be `want`: another known id is `E_INPUT`, an unknown one `E_SCHEMA`.
fn known_convention(i: &Inputs, k: &str, want: &str) -> Result<Result<()>> {
    let id = i.str(k)?;
    if id == want {
        Ok(Ok(()))
    } else if conventions::lookup(id).is_some() {
        Ok(fail("E_INPUT", format!("{k} must be {want}")))
    } else {
        i.fail(k, "unknown convention")
    }
}

pub(crate) fn bond_fields(b: &Inputs) -> Result<Bond> {
    let (m, c, f) = (b.date("maturity")?, b.f64("coupon")?, b.int("frequency")?);
    if ![1, 2, 4].contains(&f) {
        return b.fail("frequency", "must be 1, 2 or 4");
    }
    Ok(Bond::new(m, c, f))
}

fn bond(i: &Inputs) -> Result<Bond> {
    bond_fields(&sub(i, "bond")?)
}

/// Required key whose value may be `null`.
pub(crate) fn nullable_f64(i: &Inputs, k: &str) -> Result<Option<f64>> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        Some(Json::Null) => Ok(None),
        _ => Ok(Some(i.f64(k)?)),
    }
}

/// Optional, but `null` is `E_SCHEMA` (ruling D10).
pub(crate) fn optional_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    match i.0.get(k) {
        None => Ok(None),
        Some(Json::Null) => i.fail(k, "must not be null"),
        _ => Ok(Some(i.reals(k)?)),
    }
}

fn month_start(i: &Inputs, k: &str) -> Result<Date> {
    let s = i.str(k)?;
    match Date::parse(&format!("{s}-01")) {
        Some(d) if s.len() == 7 => Ok(d),
        _ => i.fail(k, "expected YYYY-MM"),
    }
}

fn price_json(dirty: f64, accrued: f64) -> Json {
    obj([
        ("dirty", dirty.into()),
        ("accrued", accrued.into()),
        ("clean", (dirty - accrued).into()),
    ])
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "bond.price.from_yield" => {
            let (b, s, y) = (bond(i)?, i.date("settlement")?, i.f64("yield")?);
            let p = bonds::price_from_yield(&b, s, y)?;
            plain(obj([
                ("dirty", p.dirty.into()),
                ("accrued", p.accrued.into()),
                ("clean", p.clean.into()),
                ("modified_duration", p.modified_duration.into()),
                ("macaulay_duration", p.macaulay_duration.into()),
                ("convexity", p.convexity.into()),
            ]))
        }
        "bond.yield.from_price" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, i.f64("clean_price")?);
            let (y, d, a) = bonds::yield_from_price(&b, s, c)?;
            plain(obj([
                ("yield", y.into()),
                ("dirty", d.into()),
                ("accrued", a.into()),
            ]))
        }
        "bond.price.from_curve" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            i.gate()?;
            let (d, a) = bonds::price_from_curve(&b, s, &Curve::new(&c)?)?;
            plain(price_json(d, a))
        }
        "bond.spread.z" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("clean_price")?;
            i.gate()?;
            let z = bonds::z_spread(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([("z_spread", z.into())]))
        }
        "bond.spread.asset_swap" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("dirty_price")?;
            i.gate()?;
            let (spread, annuity) = bonds::asset_swap(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([
                ("spread", spread.into()),
                ("annuity", annuity.into()),
            ]))
        }
        "bond.frn.price" => {
            let f = i.int("frequency")?;
            if ![1, 2, 4].contains(&f) {
                return i.fail("frequency", "must be 1, 2 or 4");
            }
            let n = Frn {
                settlement: i.date("settlement")?,
                maturity: i.date("maturity")?,
                frequency: f,
                current_rate: i.f64("current_rate")?,
                margin: i.f64("margin")?,
                discount_margin: i.f64("discount_margin")?,
            };
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            i.gate()?;
            let (dirty, a) = bonds::frn_price(&n, &Curve::new(&d)?, &Curve::new(&p)?)?;
            plain(price_json(dirty, a))
        }
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
        }
        "repo.implied_rate" => {
            let (b, s, e) = (bond(i)?, i.date("start")?, i.date("end")?);
            let (c, f) = (i.f64("clean_price")?, i.f64("forward_clean")?);
            let r = bonds::repo_implied_rate(&b, s, e, c, f)?;
            plain(obj([("repo_rate", r.into())]))
        }
        "bond.futures.conversion_factor" => {
            let (b, d) = (bond(i)?, month_start(i, "delivery_month")?);
            let cf = bonds::conversion_factor(&b, d, i.f64("notional_coupon")?)?;
            plain(obj([("conversion_factor", cf.into())]))
        }
        "bond.futures.basis" => {
            let (f, s, d, r) = (
                i.f64("futures_price")?,
                i.date("settlement")?,
                i.date("delivery")?,
                i.f64("repo_rate")?,
            );
            let mut list = Vec::new();
            for b in items(i, "bonds")? {
                let x = bond_fields(&b)?;
                list.push((x, b.f64("clean_price")?, b.f64("conversion_factor")?));
            }
            i.gate()?;
            let (out, ctd) = bonds::futures_basis(f, s, d, r, &list)?;
            let rows: Vec<Json> = out
                .iter()
                .map(|x| {
                    obj([
                        ("invoice", x.invoice.into()),
                        ("gross_basis", x.gross_basis.into()),
                        ("net_basis", x.net_basis.into()),
                        ("implied_repo", x.implied_repo.into()),
                    ])
                })
                .collect();
            plain(obj([("bonds", rows.into()), ("ctd", (ctd as i64).into())]))
        }
        "bond.fit.nelson_siegel" => {
            let (s, tau) = (i.date("settlement")?, i.f64("tau")?);
            let mut list = Vec::new();
            for b in items(i, "bonds")? {
                list.push((bond_fields(&b)?, b.f64("dirty_price")?));
            }
            let w = optional_reals(i, "weights")?;
            i.gate()?;
            let (beta, res) = bonds::fit_nelson_siegel(s, tau, &list, w.as_deref())?;
            plain(obj([
                ("betas", beta.to_vec().into()),
                ("residuals", res.into()),
            ]))
        }
        "fx.xccy.bootstrap" => {
            let (_, f) = (
                curve_input(i, "domestic")?,
                curve_input(i, "foreign_projection")?,
            );
            let dc = known_convention(i, "domestic_convention", "SOFR")?;
            let fc = known_convention(i, "foreign_convention", "ESTR")?;
            let s = i.date("start")?;
            let mut q = Vec::new();
            for x in items(i, "quotes")? {
                q.push((x.int("months")?, x.f64("spread")?));
            }
            let m = interpolation(i)?;
            i.gate()?;
            dc?;
            fc?;
            let r = xccy::bootstrap(&Curve::new(&f)?, s, &q, m)?;
            Ok(Outcome {
                outputs: pillars_json(&r.dates, &r.logs),
                diagnostics: repricing(r.max_repricing_error),
            })
        }
        "fx.xccy.pv" => {
            let d = curve_input(i, "domestic")?;
            let (fp, fd) = (
                curve_input(i, "foreign_projection")?,
                curve_input(i, "foreign_discount")?,
            );
            let spot = i.f64("spot")?;
            let t = sub(i, "trade")?;
            let trade = XccyTrade {
                start: t.date("start")?,
                months: t.int("months")?,
                foreign_notional: t.f64("foreign_notional")?,
                spread: t.f64("spread")?,
                receive_foreign: match t.str("side")? {
                    "RECEIVE_FOREIGN" => true,
                    "PAY_FOREIGN" => false,
                    _ => return t.fail("side", "unknown side"),
                },
            };
            i.gate()?;
            let (d, fp, fd) = (Curve::new(&d)?, Curve::new(&fp)?, Curve::new(&fd)?);
            let (pv, f, dl) = xccy::pv(&d, &fp, &fd, spot, &trade)?;
            plain(obj([
                ("pv", pv.into()),
                ("foreign_leg", f.into()),
                ("domestic_leg", dl.into()),
            ]))
        }
        "fx.ndf.pv" => {
            let (u, o) = (
                curve_input(i, "usd_curve")?,
                curve_input(i, "offshore_curve")?,
            );
            let spot = i.f64("spot")?;
            let t = sub(i, "trade")?;
            let trade = Ndf {
                fixing_date: t.date("fixing_date")?,
                payment_date: t.date("payment_date")?,
                strike: t.f64("strike")?,
                usd_notional: t.f64("usd_notional")?,
                buy: match t.str("side")? {
                    "BUY" => true,
                    "SELL" => false,
                    _ => return t.fail("side", "unknown side"),
                },
            };
            let fixing = nullable_f64(i, "fixing")?;
            i.gate()?;
            let (pv, f) = xccy::ndf_pv(&Curve::new(&u)?, &Curve::new(&o)?, spot, &trade, fixing)?;
            plain(obj([("pv", pv.into()), ("forward", f.into())]))
        }
        "credit.cds.price" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let h = hazard_input(i, "hazard")?;
            let r = i.f64("recovery")?;
            let x = sub(i, "trade")?;
            let trade = CdsTrade {
                maturity: x.date("maturity")?,
                coupon: x.f64("coupon")?,
                notional: x.f64("notional")?,
                buy: match x.str("side")? {
                    "BUY_PROTECTION" => true,
                    "SELL_PROTECTION" => false,
                    _ => return x.fail("side", "unknown side"),
                },
            };
            let digital = match i.str("payout")? {
                "STANDARD" => false,
                "DIGITAL" => true,
                _ => return i.fail("payout", "unknown payout"),
            };
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let h = Hazard::new(h.0, &h.1)?;
            let p = credit::price(t, &c, &pil, &h, r, &trade, digital)?;
            plain(obj([
                ("pv", p.pv.into()),
                ("upfront", p.upfront.into()),
                ("accrued", p.accrued.into()),
                ("par_spread", p.par_spread.into()),
                ("protection_leg", p.protection_leg.into()),
                ("rpv01", p.rpv01.into()),
            ]))
        }
        "credit.cds.bootstrap" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let (r, q) = (i.f64("recovery")?, cds_quotes(i)?);
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let h = credit::bootstrap(t, &c, &pil, r, &q)?;
            plain(obj([("pillars", survival_json(&h))]))
        }
        "credit.index.intrinsic" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let mut names = Vec::new();
            for n in items(i, "names")? {
                names.push((
                    hazard_input(&n, "hazard")?,
                    n.f64("recovery")?,
                    n.f64("weight")?,
                ));
            }
            let x = sub(i, "trade")?;
            let (m, cpn) = (x.date("maturity")?, x.f64("coupon")?);
            let quoted = i.f64("quoted_upfront")?;
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            if names.is_empty() {
                return fail("E_INPUT", "no names");
            }
            let mut built = Vec::new();
            for (h, r, w) in names {
                built.push((Hazard::new(h.0, &h.1)?, r, w));
            }
            let (ups, intrinsic) = credit::index_intrinsic(t, &c, &pil, &built, m, cpn)?;
            plain(obj([
                ("intrinsic_upfront", intrinsic.into()),
                ("basis", (quoted - intrinsic).into()),
                ("name_upfronts", ups.into()),
            ]))
        }
        "credit.curve.composite" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let r = i.f64("recovery")?;
            let mut cons = Vec::new();
            for c in items(i, "constituents")? {
                cons.push((cds_quotes(&c)?, c.f64("weight")?));
            }
            let scale = i.f64("scale")?;
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let spreads = credit::composite_spreads(&cons, scale)?;
            let h = credit::bootstrap(t, &c, &pil, r, &spreads)?;
            let s: Vec<f64> = spreads.iter().map(|x| x.1).collect();
            plain(obj([("spreads", s.into()), ("pillars", survival_json(&h))]))
        }
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
        }
        "eq.borrow.implied" => {
            let (s, f, dv) = (i.f64("spot")?, curve_input(i, "funding")?, ex_dividends(i)?);
            let (e, fw) = (i.date("expiry")?, i.f64("forward")?);
            i.gate()?;
            let b = equity_d::borrow_implied(s, &Curve::new(&f)?, &dv, e, fw)?;
            plain(obj([("borrow_rate", b.into())]))
        }
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
        }
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
        }
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
        }
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
        }
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
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
