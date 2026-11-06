//! Stage B operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use quantforge_core::calendar::parse_tenor;
use quantforge_core::calib::{self, FitInputs};
use quantforge_core::conventions::{self, FxPair, Overnight, TERM_INDEX};
use quantforge_core::curve::{Curve, CurveInput, Interpolation, SolveMethod};
use quantforge_core::dates::Date;
use quantforge_core::error::{Result, fail};
use quantforge_core::fx::{self, FxLeg, FxMarket};
use quantforge_core::hedge;
use quantforge_core::json::{Json, obj};
use quantforge_core::ois::{self, OisCurveProblem, OisQuote, OisTrade};
use quantforge_core::projection::{self, ProjectionQuote};
use quantforge_core::risk;
use quantforge_core::schedule;
use quantforge_core::units;

fn sub<'a>(i: &Inputs<'a>, k: &str) -> Result<Inputs<'a>> {
    let v = i.req(k)?;
    if !matches!(v, Json::Obj(_)) {
        return i.fail(k, "expected an object");
    }
    Ok(Inputs::new(v))
}

fn items<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| match v {
            Json::Obj(_) => Ok(Inputs::new(v)),
            _ => i.fail(k, "expected objects"),
        })
        .collect()
}

fn interpolation(i: &Inputs) -> Result<Interpolation> {
    match Interpolation::parse(i.str("interpolation")?) {
        Some(v) => Ok(v),
        None => i.fail("interpolation", "unknown interpolation"),
    }
}

fn curve_input(i: &Inputs, k: &str) -> Result<CurveInput> {
    let c = sub(i, k)?;
    let mut pillars = Vec::new();
    for p in items(&c, "pillars")? {
        pillars.push((p.date("date")?, p.f64("discount_factor")?));
    }
    Ok(CurveInput {
        as_of: c.date("as_of")?,
        interpolation: interpolation(&c)?,
        pillars,
    })
}

fn tenor(i: &Inputs, k: &str) -> Result<(i64, char)> {
    tenor_text(i, k, i.str(k)?)
}

fn tenor_text(i: &Inputs, k: &str, s: &str) -> Result<(i64, char)> {
    match parse_tenor(s) {
        Some(t) => Ok(t),
        None => i.fail(k, "malformed tenor"),
    }
}

fn overnight(i: &Inputs, k: &str) -> Result<Overnight> {
    match conventions::overnight(i.str(k)?) {
        Some(c) => Ok(c),
        None => i.fail(k, "unknown convention"),
    }
}

fn index(i: &Inputs) -> Result<()> {
    if i.str("index")? != TERM_INDEX {
        return i.fail("index", "unknown index");
    }
    Ok(())
}

fn pair(i: &Inputs) -> Result<FxPair> {
    match conventions::fx_pair(i.str("pair")?) {
        Some(p) => Ok(p),
        None => i.fail("pair", "unknown pair"),
    }
}

fn ois_quotes(i: &Inputs) -> Result<Vec<OisQuote>> {
    items(i, "quotes")?
        .iter()
        .map(|q| {
            let t = tenor(q, "tenor")?;
            let (bid, ask) = match q.opt_f64("rate")? {
                Some(r) => (r, r),
                None => (q.f64("bid")?, q.f64("ask")?),
            };
            Ok(OisQuote { tenor: t, bid, ask })
        })
        .collect()
}

fn side(i: &Inputs, yes: &str, no: &str) -> Result<bool> {
    let s = i.str("side")?;
    if s == yes {
        Ok(true)
    } else if s == no {
        Ok(false)
    } else {
        i.fail("side", "unknown side")
    }
}

fn ois_trade(i: &Inputs) -> Result<OisTrade> {
    let t = sub(i, "trade")?;
    Ok(OisTrade {
        convention: overnight(&t, "convention")?,
        tenor: tenor(&t, "tenor")?,
        fixed_rate: t.f64("fixed_rate")?,
        notional: t.f64("notional")?,
        pay: side(&t, "PAY", "RECEIVE")?,
    })
}

fn snapshot_id(i: &Inputs) -> Result<Option<String>> {
    let id = i.opt("snapshot_id").map(|_| i.str("snapshot_id"));
    Ok(id.transpose()?.map(str::to_string))
}

fn pillars_json(dates: &[Date], logs: &[f64]) -> Json {
    let rows: Vec<Json> = dates
        .iter()
        .zip(logs)
        .map(|(d, l)| {
            obj([
                ("date", d.to_string().into()),
                ("discount_factor", l.exp().into()),
            ])
        })
        .collect();
    obj([("pillars", rows.into())])
}

fn repricing(e: f64) -> Json {
    obj([("max_repricing_error", e.into())])
}

fn fx_market_input(i: &Inputs) -> Result<(FxPair, f64, Date, CurveInput, CurveInput)> {
    Ok((
        pair(i)?,
        i.f64("spot")?,
        i.date("as_of")?,
        curve_input(i, "base_curve")?,
        curve_input(i, "quote_curve")?,
    ))
}

type FxInput = (FxPair, f64, Date, CurveInput, CurveInput);

fn fx_market(m: FxInput) -> Result<FxMarket> {
    if m.1 <= 0.0 {
        return fail("E_DOMAIN", "spot must be positive");
    }
    Ok(FxMarket {
        pair: m.0,
        spot: m.1,
        as_of: m.2,
        base: Curve::new(&m.3)?,
        quote: Curve::new(&m.4)?,
    })
}

fn fx_leg(t: &Inputs) -> Result<FxLeg> {
    Ok(FxLeg {
        notional_base: t.f64("notional_base")?,
        strike: t.f64("strike")?,
        value_date: t.date("value_date")?,
        buy: side(t, "BUY", "SELL")?,
    })
}

fn opt_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    i.opt(k).map(|_| i.reals(k)).transpose()
}

fn calib_fit(i: &Inputs) -> Result<Outcome> {
    let model = match i.str("model")? {
        "LINEAR" => calib::Model::Linear,
        "EXPONENTIAL" => calib::Model::Exponential,
        "NELSON_SIEGEL" => calib::Model::NelsonSiegel,
        "ROSENBROCK" => calib::Model::Rosenbrock,
        _ => return i.fail("model", "unknown model"),
    };
    let method = match i.str("method")? {
        "GAUSS_NEWTON" => calib::Method::GaussNewton,
        "LEVENBERG_MARQUARDT" => calib::Method::LevenbergMarquardt,
        "BFGS" => calib::Method::Bfgs,
        _ => return i.fail("method", "unknown method"),
    };
    let f = FitInputs {
        model,
        x: opt_reals(i, "x")?.unwrap_or_default(),
        y: opt_reals(i, "y")?.unwrap_or_default(),
        start: i.reals("start")?,
        method,
        weights: opt_reals(i, "weights")?,
        regularisation: i.f64_or("regularisation", 0.0)?,
        prior: opt_reals(i, "prior")?,
        lower: opt_reals(i, "lower")?,
        upper: opt_reals(i, "upper")?,
        max_iter: i.int_or("max_iter", 1000)?,
    };
    let report = i.bool_or("report_parameters", true)?;
    i.gate()?;
    let r = calib::fit(&f)?;
    let objective = ("objective", r.objective.into());
    Ok(Outcome {
        outputs: if report {
            obj([("parameters", r.parameters.into()), objective])
        } else {
            obj([objective])
        },
        diagnostics: obj([
            ("iterations", r.iterations.into()),
            ("status", r.status.into()),
            ("residuals", r.residuals.into()),
        ]),
    })
}

fn projection_quotes(i: &Inputs) -> Result<Vec<ProjectionQuote>> {
    items(i, "quotes")?
        .iter()
        .map(|q| {
            let rate = q.f64("rate")?;
            Ok(match q.str("type")? {
                "DEPOSIT" => ProjectionQuote::Deposit {
                    months: q.int("months")?,
                    rate,
                },
                "FRA" => ProjectionQuote::Fra {
                    start_months: q.int("start_months")?,
                    rate,
                },
                "SWAP" => ProjectionQuote::Swap {
                    months: q.int("months")?,
                    rate,
                },
                _ => return q.fail("type", "unknown quote type"),
            })
        })
        .collect()
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "core.units.convert" => {
            let (v, a, b) = (i.f64("value")?, i.str("from")?, i.str("to")?);
            plain(obj([("value", units::convert(v, a, b)?.into())]))
        }
        "core.units.add_money" => {
            let (a, b) = (sub(i, "a")?, sub(i, "b")?);
            let (ax, ac) = (a.str("amount")?, a.str("currency")?);
            let (bx, bc) = (b.str("amount")?, b.str("currency")?);
            let (amount, currency) = units::add_money(ax, ac, bx, bc)?;
            plain(obj([
                ("amount", amount.into()),
                ("currency", currency.into()),
            ]))
        }
        "core.units.round_money" => {
            let (x, c) = (i.str("amount")?, i.str("currency")?);
            let (amount, currency) = units::round_money(x, c)?;
            plain(obj([
                ("amount", amount.into()),
                ("currency", currency.into()),
            ]))
        }
        "core.conventions.lookup" => match conventions::lookup(i.str("id")?) {
            Some(r) => plain(r),
            None => i.fail("id", "unknown convention"),
        },
        "rates.schedule.generate" => {
            let (s, e) = (i.date("start")?, i.date("end")?);
            let f = i.int("frequency_months")?;
            if ![1, 2, 3, 4, 6, 12].contains(&f) {
                return i.fail("frequency_months", "not listed");
            }
            let c = i.calendar("calendar")?;
            let eom = match i.req("end_of_month")? {
                Json::Bool(b) => *b,
                _ => return i.fail("end_of_month", "expected a boolean"),
            };
            let lag = i.int("payment_lag")?;
            let rows: Vec<Json> = schedule::generate(s, e, f, &c, eom, lag)?
                .iter()
                .map(|p| {
                    obj([
                        ("start", p.start.to_string().into()),
                        ("end", p.end.to_string().into()),
                        ("payment", p.payment.to_string().into()),
                    ])
                })
                .collect();
            plain(obj([("periods", rows.into())]))
        }
        "rates.curve.discount" => {
            let c = curve_input(i, "curve")?;
            let dates = i.dates("dates")?;
            i.gate()?;
            let c = Curve::new(&c)?;
            let d = dates.iter().map(|d| c.discount(*d));
            let d = d.collect::<Result<Vec<_>>>()?;
            let z = dates.iter().map(|d| c.zero_rate(*d));
            let z = z.collect::<Result<Vec<_>>>()?;
            plain(obj([
                ("discount_factors", d.into()),
                ("zero_rates", z.into()),
            ]))
        }
        "rates.curve.forward" => {
            let c = curve_input(i, "curve")?;
            let (s, e, dc) = (i.date("start")?, i.date("end")?, i.str("day_count")?);
            i.gate()?;
            let f = Curve::new(&c)?.forward(s, e, dc)?;
            plain(obj([("forward", f.into())]))
        }
        "rates.ois.bootstrap" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let method = match i.str("method")? {
                "SEQUENTIAL" => SolveMethod::Sequential,
                "GLOBAL" => SolveMethod::Global,
                _ => return i.fail("method", "unknown method"),
            };
            i.gate()?;
            let p = OisCurveProblem::new(&c, t, &q, m)?;
            let s = p.solve(&p.mids, method)?;
            Ok(Outcome {
                outputs: pillars_json(&s.dates, &s.logs),
                diagnostics: repricing(s.max_repricing_error),
            })
        }
        "rates.ois.compound" => {
            let r = i.reals("rates")?;
            let mut days = Vec::new();
            for v in i.array("days")? {
                match v.as_int() {
                    Some(n) => days.push(n),
                    None => return i.fail("days", "expected integers"),
                }
            }
            let b = i.int("denominator")?;
            if b != 360 && b != 365 {
                return i.fail("denominator", "not listed");
            }
            plain(obj([(
                "compounded_rate",
                ois::compound(&r, &days, b)?.into(),
            )]))
        }
        "rates.ois.pv" => {
            let (c, t, id) = (curve_input(i, "curve")?, ois_trade(i)?, snapshot_id(i)?);
            i.gate()?;
            let (v, par, a) = ois::pv(&Curve::new(&c)?, &t, id)?;
            plain(obj([
                ("valuation", v.to_json()),
                ("par_rate", par.into()),
                ("annuity", a.into()),
            ]))
        }
        "rates.projection.bootstrap" => {
            let d = curve_input(i, "discount")?;
            index(i)?;
            let (t, q, m) = (i.date("as_of")?, projection_quotes(i)?, interpolation(i)?);
            i.gate()?;
            let s = projection::bootstrap(&Curve::new(&d)?, t, &q, m)?;
            Ok(Outcome {
                outputs: pillars_json(&s.dates, &s.logs),
                diagnostics: repricing(s.max_repricing_error),
            })
        }
        "rates.swap.pv" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let t = sub(i, "trade")?;
            index(&t)?;
            let (m, k, n) = (
                t.int("tenor_months")?,
                t.f64("fixed_rate")?,
                t.f64("notional")?,
            );
            let (pay, id) = (side(&t, "PAY", "RECEIVE")?, snapshot_id(i)?);
            i.gate()?;
            let (d, p) = (Curve::new(&d)?, Curve::new(&p)?);
            let (v, par) = projection::swap_pv(&d, &p, m, k, n, pay, id)?;
            plain(obj([("valuation", v.to_json()), ("par_rate", par.into())]))
        }
        "rates.fra.pv" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let t = sub(i, "trade")?;
            index(&t)?;
            let (s, k, n) = (t.date("start")?, t.f64("fixed_rate")?, t.f64("notional")?);
            let (pay, id) = (side(&t, "PAY", "RECEIVE")?, snapshot_id(i)?);
            i.gate()?;
            let (d, p) = (Curve::new(&d)?, Curve::new(&p)?);
            let (v, f) = projection::fra_pv(&d, &p, s, k, n, pay, id)?;
            plain(obj([
                ("valuation", v.to_json()),
                ("forward_rate", f.into()),
            ]))
        }
        "rates.basis.spread" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            index(i)?;
            let m = i.int("tenor_months")?;
            i.gate()?;
            let s = projection::basis_spread(&Curve::new(&d)?, &Curve::new(&p)?, m)?;
            plain(obj([("spread", s.into())]))
        }
        "fx.spot_date" => {
            let (p, t) = (pair(i)?, i.date("trade_date")?);
            plain(obj([(
                "spot_date",
                fx::spot_date(&p, t)?.to_string().into(),
            )]))
        }
        "fx.forward.outright" => {
            let m = fx_market_input(i)?;
            let v = i.date("value_date")?;
            let (f, p) = fx_market(m)?.outright(v)?;
            plain(obj([("forward", f.into()), ("points", p.into())]))
        }
        "fx.forward.pv" => {
            let m = fx_market_input(i)?;
            let l = fx_leg(&sub(i, "trade")?)?;
            let m = fx_market(m)?;
            let (pv, delta) = m.leg(&l)?;
            let v = m.valuation(pv, "FX_FORWARD_DISCOUNTING");
            plain(obj([
                ("valuation", v.to_json()),
                ("fx_delta", delta.into()),
            ]))
        }
        "fx.swap.pv" => {
            let m = fx_market_input(i)?;
            let t = sub(i, "trade")?;
            let (n, far_buy) = (t.f64("notional_base")?, far_side(&t)?);
            let near = FxLeg {
                notional_base: n,
                strike: t.f64("near_rate")?,
                value_date: t.date("near_date")?,
                buy: !far_buy,
            };
            let far = FxLeg {
                notional_base: n,
                strike: t.f64("far_rate")?,
                value_date: t.date("far_date")?,
                buy: far_buy,
            };
            let m = fx_market(m)?;
            let ((a, b), (c, d)) = (m.leg(&near)?, m.leg(&far)?);
            let v = m.valuation(a + c, "FX_SWAP_DISCOUNTING");
            plain(obj([
                ("valuation", v.to_json()),
                ("fx_delta", (b + d).into()),
            ]))
        }
        "fx.curve.implied" => {
            let m = fx_market_input(i)?;
            let mut points = Vec::new();
            for p in items(i, "points")? {
                points.push((tenor(&p, "tenor")?, p.f64("points")?));
            }
            let rows: Vec<Json> = fx_market(m)?
                .implied(&points)?
                .into_iter()
                .map(|(d, r, b)| {
                    obj([
                        ("value_date", d.to_string().into()),
                        ("implied_ratio", r.into()),
                        ("basis_bp", b.into()),
                    ])
                })
                .collect();
            plain(obj([("nodes", rows.into())]))
        }
        "calib.fit" => calib_fit(i),
        "calib.check_bid_ask" => {
            let (f, b, a) = (i.reals("fitted")?, i.reals("bid")?, i.reals("ask")?);
            let rows: Vec<Json> = calib::check_bid_ask(&f, &b, &a)?
                .into_iter()
                .map(|(k, s, d)| {
                    obj([
                        ("index", k.into()),
                        ("side", s.into()),
                        ("distance", d.into()),
                    ])
                })
                .collect();
            plain(obj([("breaches", rows.into())]))
        }
        "calib.curve_report" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            i.gate()?;
            let r = risk::curve_report(&c, t, &q, m)?;
            Ok(Outcome {
                outputs: obj([
                    ("jacobian", r.jacobian.into()),
                    ("condition_number", r.condition_number.into()),
                ]),
                diagnostics: obj([
                    ("status", "CONVERGED".into()),
                    ("max_repricing_error", r.max_repricing_error.into()),
                ]),
            })
        }
        "risk.ois.dv01" => {
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let trade = ois_trade(i)?;
            i.gate()?;
            let (d, k) = risk::ois_dv01(t, &q, m, &trade)?;
            plain(obj([("dv01", d.into()), ("key_rate", k.into())]))
        }
        "risk.cashflows" => {
            let mut flows = Vec::new();
            for c in items(i, "cashflows")? {
                flows.push((c.f64("t")?, c.f64("amount")?));
            }
            let (p, d, c) = risk::cashflows(&flows, i.f64("yield")?)?;
            plain(obj([
                ("pv", p.into()),
                ("duration", d.into()),
                ("convexity", c.into()),
            ]))
        }
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
        }
        "hedge.spread_cost" => {
            let (q, h) = (i.reals("quantities")?, i.reals("half_spreads")?);
            plain(obj([("cost", hedge::spread_cost(&q, &h)?.into())]))
        }
        "usecase.fx_hedge" => {
            let m = fx_market_input(i)?;
            let mut book = Vec::new();
            for t in items(i, "book")? {
                book.push(fx_leg(&t)?);
            }
            let s = i.f64("half_spread")?;
            let [pv, delta, hedge, residual, cost] = fx::hedge_book(&fx_market(m)?, &book, s)?;
            plain(obj([
                ("pv", pv.into()),
                ("fx_delta", delta.into()),
                ("hedge_spot_base", hedge.into()),
                ("residual_delta", residual.into()),
                ("hedge_cost", cost.into()),
            ]))
        }
        "usecase.rates_hedge" => {
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let trade = ois_trade(i)?;
            let mut tenors = Vec::new();
            for v in i.array("hedge_tenors")? {
                match v.as_str() {
                    Some(s) => tenors.push(tenor_text(i, "hedge_tenors", s)?),
                    None => return i.fail("hedge_tenors", "expected strings"),
                }
            }
            let (u, h) = (i.f64("hedge_unit_notional")?, i.f64("half_spread_bp")?);
            i.gate()?;
            let r = risk::rates_hedge(t, &q, m, &trade, &tenors, u, h)?;
            plain(obj([
                ("pv", r.pv.into()),
                ("dv01", r.dv01.into()),
                ("key_rate", r.key_rate.into()),
                ("hedge_units", r.hedge_units.into()),
                ("residual_key_rate", r.residual_key_rate.into()),
                ("hedge_cost", r.hedge_cost.into()),
            ]))
        }
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}

fn far_side(t: &Inputs) -> Result<bool> {
    match t.str("far_side")? {
        "BUY" => Ok(true),
        "SELL" => Ok(false),
        _ => t.fail("far_side", "unknown side"),
    }
}
